import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/crun_credit_receipts.js", import.meta.url), "utf8");
let extension;
globalThis.__crunReceiptTestApp = { registerExtension(value) { extension = value; } };
const executable = source.replace(/^import \{ app \}.*$/m, "const app = globalThis.__crunReceiptTestApp;");
const ui = await import(`data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`);

class Element {
    constructor() { this.style = {}; this.attributes = {}; this.textContent = ""; this.removed = false; }
    setAttribute(name, value) { this.attributes[name] = value; }
    remove() { this.removed = true; }
}
globalThis.document = { createElement() { return new Element(); } };

function message(overrides = {}) {
    return { text: [JSON.stringify({ mode: "generate", model: "bytedance/seedance2-5-i2v", status: "budget_blocked", credits: 321.5, credit_limit: 100, quoted_at: 1700000000, task_id: "", ...overrides })] };
}

function makeNode() {
    return { widgets: [], dirty: 0, addDOMWidget(name, type, element, options) {
        const widget = { name, type, element, options };
        this.widgets.push(widget);
        return widget;
    }, setDirtyCanvas() { this.dirty++; } };
}

test("receipts apply to family and individual CRUN generation nodes without requests", () => {
    assert.equal(extension.name, "CRUN.Next.CreditReceipts");
    for (const name of ["CRUN_Next_Family_Seedance_Image_to_Video", "CRUN_Next_bytedance_seedance2_5_i2v_fixture"]) {
        assert.equal(ui.isCrunGenerationNode({ name, input: { required: { crun_mode: [] } } }), true);
    }
    assert.equal(ui.isCrunGenerationNode({ name: "CRUN_Next_Credits", input: {} }), false);
    assert.equal(ui.isCrunGenerationNode({ name: "OtherNode", input: { required: { crun_mode: [] } } }), false);
    assert.equal(/fetch\(|fetchApi|XMLHttpRequest|localStorage|innerHTML/.test(source), false);
});

test("budget block displays exact quote and limit together without claiming a charge", () => {
    const receipt = ui.parseCreditReceipt(message());
    const text = ui.formatCreditReceipt(receipt);
    assert.match(text, /321[.,]5 CRUN credits/);
    assert.match(text, /100 CRUN credits/);
    assert.match(text, /optional cap stopped this request/);
    assert.match(text, /No generation submitted/);
    assert.match(text, /set it to 0 under Advanced/);
    assert.match(text, /LAST CRUN ESTIMATE/);
    assert.match(text, /bytedance\/seedance2-5-i2v/);
    assert.doesNotMatch(text, /spent|charged|\$/i);
});

test("balance block shows the balance at the check, not a live or inferred remaining value", () => {
    const text = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ status: "insufficient_balance", credits: 12, credit_limit: 20, balance_before: 5 })));
    assert.match(text, /Quote: 12 CRUN credits/);
    assert.match(text, /Balance at check: 5 CRUN credits/);
    assert.match(text, /insufficient CRUN balance/);
    assert.doesNotMatch(text, /remaining|live balance/);
});

test("unknown, boolean, non-finite and negative amounts are unavailable while zero remains zero", () => {
    for (const value of [true, "5", -1, null]) {
        const text = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ credits: value, credit_limit: value })));
        assert.match(text, /Quote: unavailable/);
        assert.match(text, /cap: not reported/);
    }
    for (const numeric of ["1e999", "-1e999"]) {
        const text = ui.formatCreditReceipt(ui.parseCreditReceipt({ text: [`{"mode":"estimate","credits":${numeric}}`] }));
        assert.match(text, /Quote: unavailable/);
    }
    const zero = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ mode: "estimate", status: "estimated", credits: 0, credit_limit: 0 })));
    assert.match(zero, /Quote: 0 CRUN credits/);
    assert.match(zero, /No optional credit cap/);
    assert.doesNotMatch(zero, /unavailable/);
});

test("zero disables the optional cap and never reads as a mandatory generation block", () => {
    const quote = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ mode: "estimate", status: "estimated", credits: 321.5, credit_limit: 0 })));
    assert.match(quote, /No optional credit cap/);
    assert.match(quote, /Choose Generate/);
    assert.doesNotMatch(quote, /requires|positive|choose a generation limit|BLOCKED|stopped/);
    const submitted = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ status: "submitted", task_id: "fixture_task", credit_limit: 0 })));
    assert.match(submitted, /No optional credit cap/);
    assert.match(submitted, /Task submitted/);
    assert.doesNotMatch(submitted, /stopped|BLOCKED/);
    const inconsistent = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ status: "budget_blocked", credit_limit: 0 })));
    assert.doesNotMatch(inconsistent, /optional cap stopped|quote exceeds|zero blocks/);
});

test("prepare has no quote and submitted receipts distinguish estimates from final charges", () => {
    const prepare = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ mode: "prepare", status: "draft", credits: -1 })));
    assert.match(prepare, /Local preparation/);
    assert.doesNotMatch(prepare, /321|100|Quote:/);
    const submitted = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ status: "submitted", task_id: "fixture_task", credits: 22, credit_limit: 30 })));
    assert.match(submitted, /Task submitted/);
    assert.match(submitted, /not its final charge/);
    const missingId = ui.formatCreditReceipt(ui.parseCreditReceipt(message({ status: "submitted", task_id: "" })));
    assert.match(missingId, /Inspect CRUN Logs/);
    assert.doesNotMatch(missingId, /Task submitted/);
});

test("payload, prompts, URLs, raw errors and task IDs are not copied into the display receipt", () => {
    const receipt = ui.parseCreditReceipt(message({ model: "https://secret.example/private", payload: { prompt: "PRIVATE PROMPT", img_urls: ["https://private.example/reference"] }, errors: ["PRIVATE ERROR"], task_id: "private_task" }));
    assert.equal(receipt.model, null);
    const text = ui.formatCreditReceipt(receipt);
    assert.doesNotMatch(text + JSON.stringify(receipt), /PRIVATE|secret\.example|private\.example|private_task/);
    for (const value of [null, { text: ["not JSON"] }, { text: ["[]"] }, { text: ['{"balance":1}'] }]) assert.equal(ui.parseCreditReceipt(value), null);
});

test("widget is nonserialized, accessible, reused and never changes budgets or upload permissions", () => {
    const node = makeNode();
    node.widgets.push({ name: "crun_max_credits", value: 100 }, { name: "crun_allow_upload", value: false });
    const first = ui.attachCreditReceipt(node);
    assert.match(first.element.textContent, /No quote received/);
    assert.doesNotMatch(first.element.textContent, /Local preparation/);
    assert.equal(first.widget.serialize, false);
    assert.equal(first.widget.options.serialize, false);
    assert.equal(first.widget.options.hideOnZoom, false);
    assert.equal(first.element.attributes.role, "status");
    assert.equal(first.element.attributes["aria-live"], "polite");
    assert.equal(ui.updateCreditReceipt(node, message()), true);
    assert.equal(ui.attachCreditReceipt(node), first);
    assert.equal(ui.updateCreditReceipt(node, message({ credits: 444 })), true);
    assert.equal(node.widgets.filter(widget => widget.name === "crun_credit_receipt").length, 1);
    assert.match(first.element.textContent, /444 CRUN credits/);
    assert.equal(node.widgets[0].value, 100);
    assert.equal(node.widgets[1].value, false);
    assert.equal(ui.updateCreditReceipt(node, { text: ["unrelated"] }), false);
});

test("lifecycle wrappers preserve other extension callbacks and clean up their own widget", () => {
    function Node() { Object.assign(this, makeNode()); }
    Node.prototype.onNodeCreated = function () { this.created = true; return "created"; };
    Node.prototype.onExecuted = function () { this.executed = true; return "executed"; };
    Node.prototype.onRemoved = function () { this.removed = true; return "removed"; };
    extension.beforeRegisterNodeDef(Node, { name: "CRUN_Next_Family_Seedance", input: { required: { crun_mode: [] } } });
    const node = new Node();
    assert.equal(node.onNodeCreated(), "created");
    const state = ui.attachCreditReceipt(node);
    assert.equal(node.onExecuted(message()), "executed");
    assert.equal(node.executed, true);
    assert.match(state.element.textContent, /321[.,]5/);
    assert.equal(node.onRemoved(), "removed");
    assert.equal(node.removed, true);
    assert.equal(state.element.removed, true);
});
