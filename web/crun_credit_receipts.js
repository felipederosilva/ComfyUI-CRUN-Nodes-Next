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

// Only local validator vocabulary enters the visible status. Raw provider
// exceptions can contain prompts, URLs or credentials and are never rendered.
const VALIDATION_MESSAGES = new Set([
    "required.", "choose a documented option.", "outside the documented range.",
    "incorrect number of items.", "incorrect text length.", "must match a documented input variant.",
    "does not match the required constant.", "does not match the documented text format.",
    "a public HTTPS URL is required.", "expected an object.",
    "provide at least one reference image or video.",
    "this model accepts at most one reference video.",
    "choose base_video or feature_video for the connected video.",
    "auto requires a reference video; choose 1:1, 16:9 or 9:16 for images only.",
    "use at most five images with video, or seven images without video.",
    "connect exactly one character image.", "connect exactly one motion reference video.",
    "choose image or video orientation.", "provide at least one image or video reference.",
    "each reference needs an image or video; voice alone is insufficient.",
    "use ten seconds or less when a reference video is included.",
    "reference width and height are below this model's documented minimum.",
    "reference width or height exceeds this model's documented maximum.",
    "reference aspect ratio is outside this model's documented limits.",
    "reference duration is outside this model's documented limits for the selected mode.",
    "reference frame rate is outside this model's documented limits.",
    "reference file exceeds this model's documented size limit.",
]);

function validationFeedback(result) {
    const raw = Array.isArray(result.validation_errors) ? result.validation_errors : result.mode === "prepare" && Array.isArray(result.errors) ? result.errors : [];
    const messages = [];
    for (const item of raw.slice(0, 12)) {
        if (typeof item !== "string" || item.length > 500 || /https?:|api[_ -]?key|bearer|password|token|[\r\n\u0000-\u001f]/i.test(item)) continue;
        const match = /^(?:request\.(?:input\.)?)?([a-z][a-z0-9_]*(?:\[\d+\])?(?:\.[a-z][a-z0-9_]*(?:\[\d+\])?)*):\s*(.+)$/.exec(item);
        if (!match || !(VALIDATION_MESSAGES.has(match[2]) || /^expected (?:string|integer|number|boolean|object|array|null)\.$/.test(match[2]))) continue;
        messages.push(`${match[1].replace(/_/g, " ")}: ${match[2]}`);
    }
    return { validationErrors: [...new Set(messages)], validationIssueCount: Math.min(raw.length, 1000) };
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
            status: ["draft", "estimated", "budget_blocked", "insufficient_balance", "submitted", "completed", "resumed", "failed", "validation_failed"].includes(result.status) ? result.status : "unknown",
            credits: amount(result.credits),
            actualCredits: amount(result.actual_credits),
            creditLimit: amount(result.credit_limit),
            balance: amount(result.balance_before ?? result.balance),
            creditsLeft: amount(result.credits_left ?? result.balance_after),
            balanceCheckedAt: quoteTime(result.balance_checked_at ?? result.completed_at),
            model: modelLabel(result.model),
            quotedAt: quoteTime(result.quoted_at),
            taskSubmitted: result.status === "submitted" && typeof result.task_id === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$/.test(result.task_id),
            taskKnown: typeof result.task_id === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$/.test(result.task_id),
            ...validationFeedback(result),
        };
    }
    return null;
}

export function formatCreditReceipt(receipt) {
    if (!receipt) return "CRUN CREDITS\nNo quote received by this node yet.\nUse Estimate to review the current cost, or Generate to submit the request.";
    if (receipt.mode === "prepare") {
        const lines = ["LOCAL PREPARATION", "Local preparation — no quote requested and no generation submitted."];
        if (receipt.validationIssueCount) {
            lines.push("Inputs need attention before estimating or generating.", ...receipt.validationErrors);
            if (!receipt.validationErrors.length) lines.push("Review the selected model's required inputs.");
        } else lines.push("Local input checks passed. Use Estimate for the current quote, or Generate to create media.");
        return lines.join("\n");
    }
    const format = value => value === null ? "unavailable" : `${new Intl.NumberFormat(undefined, { maximumSignificantDigits: 12 }).format(value)} CRUN credits`;
    const finished = ["completed", "resumed"].includes(receipt.status);
    const lines = [finished ? "CRUN RESULT" : "LAST CRUN ESTIMATE"];
    if (receipt.model) lines.push(`Model: ${receipt.model}`);
    lines.push(`Quote: ${format(receipt.credits)}`);
    lines.push(receipt.creditLimit === 0 ? "No optional credit cap" : receipt.creditLimit === null ? "Optional credit cap: not reported" : `Optional credit cap: ${format(receipt.creditLimit)}`);
    if (receipt.balance !== null) lines.push(`Balance at check: ${format(receipt.balance)}`);
    if (receipt.quotedAt) lines.push(`Quoted: ${receipt.quotedAt}`);
    if (finished) {
        lines.push(`Actual credits: ${format(receipt.actualCredits)}`);
        lines.push(`Credits left: ${format(receipt.creditsLeft)}`);
        if (receipt.balanceCheckedAt) lines.push(`Balance checked: ${receipt.balanceCheckedAt}`);
        lines.push(receipt.status === "resumed" ? "Existing result recovered. No replacement generation submitted." : "Media ready. Actual cost is the provider-reported task charge.");
        if (receipt.actualCredits === null) lines.push("Final task cost was not reported; the quote is not a confirmed charge.");
    } else if (receipt.status === "failed") {
        lines.push(receipt.taskKnown ? "Result could not be completed. Keep the task ID and resume the existing task; do not generate again." : "Request did not complete. Inspect the task state before submitting again.");
    } else if (receipt.status === "validation_failed" || receipt.validationIssueCount) {
        lines.push("Inputs need attention. No generation submitted.", ...receipt.validationErrors);
        if (!receipt.validationErrors.length) lines.push("Review the selected model's required inputs.");
    } else if (receipt.status === "budget_blocked" && receipt.creditLimit > 0) {
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

// Keep Comfy's overlay geometry tied to the node, including after resize and zoom.
function syncPanelWidth(node, widget, element) {
    const width = Number(node.size?.[0]);
    if (!widget || !Number.isFinite(width) || width <= 0) return;
    if (widget.width !== width) widget.width = width;
    element.style.maxWidth = `${Math.max(0, width - 20)}px`;
}

export function attachCreditReceipt(node) {
    if (receipts.has(node)) return receipts.get(node);
    if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return null;
    const element = document.createElement("div");
    element.style.cssText = "overflow:auto;box-sizing:border-box;width:100%;height:100%;overflow-wrap:anywhere;padding:9px 11px;border:1px solid #3b747d;border-radius:7px;background:#10252d;color:#d4eeee;white-space:pre-wrap;font:12px/1.45 sans-serif";
    element.setAttribute("role", "status");
    element.setAttribute("aria-label", "CRUN credit receipt");
    element.setAttribute("aria-live", "polite");
    element.textContent = formatCreditReceipt(null);
    const widget = node.addDOMWidget(WIDGET_NAME, "info", element, {
        serialize: false,
        onDraw(widget) { syncPanelWidth(node, widget, element); },
        afterResize(resizedNode) { syncPanelWidth(resizedNode, this, element); },
        hideOnZoom: false,
        getMinHeight: () => 105,
        getMaxHeight: () => 250,
    });
    if (widget) {
        syncPanelWidth(node, widget, element);
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
    state.element.style.borderColor = ["budget_blocked", "insufficient_balance", "failed", "validation_failed"].includes(receipt.status) || receipt.validationIssueCount ? "#d49a50" : "#3b747d";
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
