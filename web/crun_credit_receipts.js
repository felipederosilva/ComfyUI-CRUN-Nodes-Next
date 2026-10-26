import { app } from "../../scripts/app.js";

// Receipts are display-only. They never enable uploads, change a budget, request
// a quote or submit a task. Their model/time labels describe the last response.
const receipts = new WeakMap();
const WIDGET_NAME = "crun_credit_receipt";

function amount(value) {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function modelLabel(value) {
    return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._/ -]{0,199}$/.test(value) ? value : null;
}

function quoteTime(value) {
    let date;
    if (typeof value === "number" && Number.isFinite(value) && value > 0) date = new Date(value * 1000);
    else if (typeof value === "string" && /^\d{4}-\d\d-\d\dT/.test(value) && value.length < 80) date = new Date(value);
    return date && Number.isFinite(date.getTime()) ? date.toLocaleString() : null;
}

export function isCrunGenerationNode(nodeData) {
    const fields = { ...(nodeData?.input?.required || {}), ...(nodeData?.input?.optional || {}) };
    return typeof nodeData?.name === "string" && nodeData.name.startsWith("CRUN_Next_") && Object.hasOwn(fields, "crun_mode");
}

export function parseCreditReceipt(message) {
    if (!Array.isArray(message?.text)) return null;
    for (const text of message.text) {
        if (typeof text !== "string" || text.length > 2 * 1024 * 1024) continue;
        let result;
        try { result = JSON.parse(text); } catch { continue; }
        if (!result || typeof result !== "object" || Array.isArray(result) || !["prepare", "estimate", "generate"].includes(result.mode)) continue;
        // Retain only display fields; payloads, prompts, error bodies, task IDs
        // and reference URLs never enter the widget's data or workflow state.
        return {
            mode: result.mode,
            status: ["draft", "estimated", "budget_blocked", "insufficient_balance", "submitted"].includes(result.status) ? result.status : "unknown",
            credits: amount(result.credits),
            creditLimit: amount(result.credit_limit),
            balance: amount(result.balance_before ?? result.balance),
            model: modelLabel(result.model),
            quotedAt: quoteTime(result.quoted_at),
            taskSubmitted: result.status === "submitted" && typeof result.task_id === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$/.test(result.task_id),
        };
    }
    return null;
}

export function formatCreditReceipt(receipt) {
    if (!receipt) return "CRUN CREDITS\nNo quote received by this node yet.\nUse Estimate to review the current cost, or Generate to submit the request.";
    if (receipt.mode === "prepare") return "CRUN CREDITS\nLocal preparation — no quote requested and no generation submitted.\nUse Estimate to review the current cost, or Generate to submit the request.";
    const format = value => value === null ? "unavailable" : `${new Intl.NumberFormat(undefined, { maximumSignificantDigits: 12 }).format(value)} CRUN credits`;
    const lines = ["LAST CRUN ESTIMATE"];
    if (receipt.model) lines.push(`Model: ${receipt.model}`);
    lines.push(`Quote: ${format(receipt.credits)}`);
    lines.push(receipt.creditLimit === 0 ? "No optional credit cap" : receipt.creditLimit === null ? "Optional credit cap: not reported" : `Optional credit cap: ${format(receipt.creditLimit)}`);
    if (receipt.balance !== null) lines.push(`Balance at check: ${format(receipt.balance)}`);
    if (receipt.quotedAt) lines.push(`Quoted: ${receipt.quotedAt}`);
    if (receipt.status === "budget_blocked" && receipt.creditLimit > 0) {
        lines.push("The optional cap stopped this request. No generation submitted.");
        lines.push("Adjust it or set it to 0 under Advanced.");
    } else if (receipt.status === "budget_blocked") {
        lines.push("No generation submitted. This receipt reports a block without an active optional cap.");
    } else if (receipt.status === "insufficient_balance") {
        lines.push("BLOCKED — insufficient CRUN balance. No generation submitted.");
    } else if (receipt.taskSubmitted) {
        lines.push("Task submitted. This is the estimate, not its final charge.");
    } else if (receipt.mode === "estimate") {
        lines.push("Estimate only — no generation submitted.");
        lines.push("Choose Generate to submit these settings.");
    } else {
        lines.push("Submission status unavailable. Inspect CRUN Logs before submitting again.");
    }
    return lines.join("\n");
}

export function attachCreditReceipt(node) {
    if (receipts.has(node)) return receipts.get(node);
    if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return null;
    const element = document.createElement("div");
    element.style.cssText = "overflow:auto;box-sizing:border-box;width:100%;height:100%;padding:9px 11px;border:1px solid #3b747d;border-radius:7px;background:#10252d;color:#d4eeee;white-space:pre-wrap;font:12px/1.45 sans-serif";
    element.setAttribute("role", "status");
    element.setAttribute("aria-label", "CRUN credit receipt");
    element.setAttribute("aria-live", "polite");
    element.textContent = formatCreditReceipt(null);
    const widget = node.addDOMWidget(WIDGET_NAME, "info", element, {
        serialize: false,
        hideOnZoom: false,
        getMinHeight: () => 190,
        getMaxHeight: () => 240,
    });
    if (widget) {
        widget.serialize = false;
        widget.options ||= {};
        widget.options.serialize = false;
    }
    const state = { element, widget, receipt: null };
    receipts.set(node, state);
    return state;
}

export function updateCreditReceipt(node, message) {
    const receipt = parseCreditReceipt(message);
    if (!receipt) return false;
    const state = attachCreditReceipt(node);
    if (!state) return false;
    state.receipt = receipt;
    state.element.textContent = formatCreditReceipt(receipt);
    state.element.style.borderColor = ["budget_blocked", "insufficient_balance"].includes(receipt.status) ? "#d49a50" : "#3b747d";
    node.setDirtyCanvas?.(true, true);
    return true;
}

app.registerExtension({
    name: "CRUN.Next.CreditReceipts",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isCrunGenerationNode(nodeData)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            attachCreditReceipt(this);
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            try { return executed?.apply(this, arguments); }
            finally { updateCreditReceipt(this, message); }
        };
        const removed = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            try { return removed?.apply(this, arguments); }
            finally {
                receipts.get(this)?.element.remove();
                receipts.delete(this);
            }
        };
    },
});
