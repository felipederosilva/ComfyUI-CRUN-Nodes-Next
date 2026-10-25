import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const sourceUrl = new URL("../web/crun_next.js", import.meta.url);
const source = await readFile(sourceUrl, "utf8");
const requests = [];
let definition;
const publicState = { configured: true, source: "saved", key_hint: "••••abcd", nonce: "fake-test-nonce", version: "0.2.0", validation_state: "connected", last_balance: 0, checked_at: 1700000000, balance_checked_at: 1700000000 };

class Element {
    constructor(tagName, document) {
        this.tagName = tagName;
        this.document = document;
        this.children = [];
        this.attributes = {};
        this.listeners = {};
        this.dataset = {};
        this.value = "";
        this.textContent = "";
        this.className = "";
        this.classList = { toggle() {} };
    }
    append(...children) {
        for (const child of children) { child.parentElement = this; this.children.push(child); }
    }
    replaceChildren(...children) { this.children = []; this.append(...children); }
    setAttribute(key, value) { this.attributes[key] = value; }
    addEventListener(name, action) { (this.listeners[name] ||= []).push(action); }
    async trigger(name, event = {}) {
        for (const callback of this.listeners[name] || []) {
            await callback({ target: this, preventDefault() {}, stopPropagation() {}, ...event });
        }
    }
    focus() { this.document.activeElement = this; }
    select() { this.selected = true; }
    showModal() { this.open = true; }
    close() { this.open = false; }
    remove() {
        if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    }
    insertBefore(child, before) {
        child.parentElement = this;
        this.children.splice(this.children.indexOf(before), 0, child);
    }
    querySelector(selector) { return all(this).find(item => item !== this && item.className.split(" ").includes(selector.slice(1))) || null; }
}

function all(element) { return [element, ...element.children.flatMap(all)]; }

const document = {
    activeElement: null,
    createElement(tagName) { return new Element(tagName, this); },
    getElementById(id) { return [...all(this.body), ...all(this.head)].find(item => item.id === id) || null; },
};
document.body = new Element("body", document);
document.head = new Element("head", document);
globalThis.document = document;
globalThis.__crunTestApp = {
    registerExtension(value) { definition = value; },
    extensionManager: { setting: { async set() {} } },
};
globalThis.__crunTestApi = {
    async fetchApi(path, options) {
        requests.push({ path, ...options });
        let payload = { ok: true };
        if (path.endsWith("/status")) payload = { ok: true, ...publicState };
        if (path.endsWith("/connection")) payload = { ok: true, balance: 0 };
        if (path.endsWith("/effects/catalog")) payload = { ok: true, cards: [{ id: "test-effect", provider: "kling", name: "<img src=x onerror=alert(1)>", category: "Test", required_images: 2, credits: 0, preview_url: "https://cdn.example.com/preview.mp4" }] };
        if (path.endsWith("/tools")) payload = { ok: true, tools: [{ id: "upscale", name: "Upscale", category: "Image", description: "Provider utility", documentation_url: "https://docs.crun.ai/ai-tools/image-upscale", status: "node_available", node_menu: "CRUN Next/AI Tools/CRUN", input_schema: { type: "object", properties: { image_url: { type: "string" } }, required: ["image_url"] } }] };
        if (path.endsWith("/models") || path.endsWith("/models/refresh")) payload = { ok: true, entries: [
            { id: "test-image", model: "google/test-image", title: "Test Image", provider: "Google", kind: "image", method: "POST", endpoint: "/documented", inputs: { type: "object", properties: { prompt: { type: "string" }, aspect_ratio: { type: "string", enum: ["16:9", "1:1"] } }, required: ["prompt"] }, documentation_url: "https://docs.crun.ai/models/google/test-image" },
            { id: "test-video", model: "kling/test-video", title: "Test Video", provider: "Kling", kind: "video", inputs: { type: "object", properties: { first_frame: { type: "string" } } } },
        ], summary: { entry_count: 2, unique_model_count: 2 }, refreshed_at: 1700000000 };
        return { ok: true, async json() { return payload; } };
    },
};
const executable = source
    .replace(/^import \{ app \}.*$/m, "const app = globalThis.__crunTestApp;")
    .replace(/^import \{ api \}.*$/m, "const api = globalThis.__crunTestApi;")
    .replaceAll("import.meta.url", JSON.stringify(sourceUrl.href));
const ui = await import(`data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`);
const tick = () => new Promise(resolve => setImmediate(resolve));
const button = label => all(document.body).find(item => item.tagName === "button" && item.textContent === label);

test("credits preserve zero and do not invent a balance", () => {
    assert.equal(ui.formatCredits(0), "0 credits");
    assert.equal(ui.formatCredits("1234.5"), "1,234.5 credits");
    for (const value of [null, undefined, "", false, -1, NaN, "unknown", [], {}]) assert.equal(ui.formatCredits(value), "Not available");
});

test("resolution-tier catalog costs stay distinct", () => {
    assert.equal(ui.formatEffectCredits([{ resolution: "480p", credits: 166.5 }, { resolution: "720p", credits: 200 }]), "480p: 166.5 credits · 720p: 200 credits");
    assert.equal(ui.formatEffectCredits([]), "Not available");
    assert.equal(ui.formatEffectCredits(0), "0 credits");
});

test("remote previews reject executable URLs and private endpoints", () => {
    assert.equal(ui.safeRemoteUrl("https://cdn.example.com/a.mp4"), "https://cdn.example.com/a.mp4");
    for (const value of ["javascript:alert(1)", "data:text/html,test", "http://example.com/a", "https://localhost/a", "https://127.0.0.1/a", "https://10.1.2.3/a", "https://172.31.1.1/a", "https://[::ffff:127.0.0.1]/a", "https://user:pass@example.com/a"]) assert.equal(ui.safeRemoteUrl(value), null);
});

test("effects search and plan preparation are local and non executable", () => {
    const cards = [{ id: "a", provider: "kling", name: "Orbit", category: "Camera", required_images: 2 }, { id: "b", name: "Paint" }];
    assert.deepEqual(ui.filterEffects(cards, " camera "), [cards[0]]);
    assert.equal(ui.filterEffects(cards, "not present").length, 0);
    const plan = ui.effectPlan(cards[0]);
    assert.equal(plan.execution, "prepare_only");
    assert.equal(plan.execution_enabled, false);
    assert.equal(plan.required_images, 2);
    assert.deepEqual(plan.inputs.image_urls, []);
    assert.equal(ui.effectPlan(cards[1]).required_images, null);
});

test("Comfy registration has no persisted credential setting", () => {
    assert.equal(definition.name, "CRUN.Next.Workspace");
    assert.equal(definition.settings.length, 5);
    assert.equal(definition.settings.filter(setting => typeof setting.type === "function").length, 4);
    assert.equal(definition.settings.find(setting => setting.id === "CRUNNext.Workspace.Open").type, "boolean");
    assert.equal(definition.commands[0].id, "CRUNNext.OpenWorkspace");
    assert.equal(/localStorage|sessionStorage|innerHTML|console\.log/.test(source), false);
    assert.equal(/CreateTask|create_task/.test(source), false);
});

test("workspace uses ephemeral key entry and explicit catalog requests", async () => {
    const prior = new Element("button", document);
    document.body.append(prior);
    prior.focus();
    const beforeOpen = requests.length;
    ui.openCrunWorkspace();
    await tick();
    assert.equal(requests.length, beforeOpen + 1);
    assert.equal(requests.at(-1).path, "/crun-next/status");
    const password = document.getElementById("crun-api-key-entry");
    assert.equal(password.type, "password");
    password.value = "fake-test-key-never-use";
    await button("Save key locally").trigger("click");
    assert.equal(password.value, "");
    const saved = requests.find(request => request.path.endsWith("/credentials"));
    assert.equal(saved.headers["X-CRUN-Nonce"], "fake-test-nonce");
    assert.equal(JSON.parse(saved.body).api_key, "fake-test-key-never-use");
    assert.equal(requests.some(request => request.path.includes("fake-test-key")), false);
    await button("Check connection & balance").trigger("click");
    assert.equal(all(document.body).some(item => item.textContent === "0 credits"), true);
    await button("AI Effects").trigger("click");
    assert.equal(requests.some(request => request.path.endsWith("/effects/catalog")), false);
    await button("Fetch catalog").trigger("click");
    assert.equal(all(document.body).some(item => item.tagName === "video"), false);
    assert.equal(all(document.body).some(item => item.textContent === "<img src=x onerror=alert(1)>"), true);
    await button("Load preview").trigger("click");
    assert.equal(all(document.body).find(item => item.tagName === "video").src, "https://cdn.example.com/preview.mp4");
    await button("Prepare plan").trigger("click");
    assert.equal(all(document.body).some(item => item.tagName === "textarea" && item.readOnly), true);
    await button("AI Tools").trigger("click");
    await tick();
    assert.equal(all(document.body).some(item => item.textContent === "COMFY NODE AVAILABLE · DEFAULT PREPARE"), true);
    await button("Inspect tool inputs").trigger("click");
    const toolSchema = all(document.body).find(item => item.attributes["aria-label"] === "Documented tool input schema");
    assert.deepEqual(JSON.parse(toolSchema.value).required, ["image_url"]);
    password.value = "unsaved-fake-key";
    await button("Close").trigger("click");
    assert.equal(password.value, "");
    assert.equal(document.activeElement, prior);
    assert.equal(document.getElementById("crun-api-key-entry"), null);
});

test("saved connection is historical and an unknown balance is not zero", () => {
    assert.match(ui.connectionText(publicState), /Previously verified.*last check/);
    assert.equal(ui.connectionText({ configured: false }), "No API key saved");
    assert.equal(ui.connectionText({ configured: true, validation_state: "saved" }), "Key saved · not checked");
});

test("model availability distinguishes authenticated inventory from docs and execution", () => {
    const listed = ui.modelAvailabilityText({ availability: "listed_in_authenticated_llm_catalog" }, "2026-10-25T15:00:00+00:00");
    assert.match(listed, /Listed in last authenticated LLM inventory/);
    assert.match(listed, /execution not tested/);
    assert.match(listed, /checked/);
    assert.doesNotMatch(listed, /not verified/);
    const unlisted = ui.modelAvailabilityText({ availability: "not_listed_in_current_llm_catalog" });
    assert.match(unlisted, /Not listed in last authenticated LLM inventory/);
    assert.match(unlisted, /not an execution failure/);
    assert.equal(ui.modelAvailabilityText({ availability: "documented_not_account_verified" }), "Documentation only · account availability not verified");
    assert.equal(ui.modelAvailabilityText({}), "Documentation only · account availability not verified");
});

test("native settings key renderer bypasses Comfy's persisted setter", async () => {
    let setterCalls = 0;
    const setting = definition.settings.find(item => item.id === "CRUNNext.Connection.APIKeyEntry");
    const row = setting.type("API key", () => { setterCalls++; }, "", {});
    document.body.append(row);
    await tick();
    const input = all(row).find(item => item.tagName === "input");
    input.value = "fake-key-native-settings";
    await all(row).find(item => item.tagName === "button" && item.textContent === "Save key").trigger("click");
    assert.equal(input.value, "");
    assert.equal(setterCalls, 0);
    assert.equal(JSON.parse(requests.findLast(request => request.path.endsWith("/credentials")).body).api_key, "fake-key-native-settings");
    const savedRow = definition.settings.find(item => item.id === "CRUNNext.Connection.SavedKey").type();
    const balanceRow = definition.settings.find(item => item.id === "CRUNNext.Connection.CreditBalance").type();
    document.body.append(savedRow, balanceRow);
    await tick();
    assert.equal(all(savedRow).some(item => item.textContent.includes("••••abcd")), true);
    assert.equal(all(balanceRow).some(item => item.textContent.includes("Last known balance: 0 credits") && item.textContent.includes("not a live balance")), true);
    row.remove(); savedRow.remove(); balanceRow.remove();
});

test("Models tab reads cached definitions, filters and inspects exact input schema", async () => {
    ui.openCrunWorkspace("models");
    await tick();
    assert.equal(requests.some(request => request.path === "/crun-next/models"), true);
    const panel = document.getElementById("crun-panel-models");
    assert.equal(all(panel).some(item => item.textContent === "Test Image"), true);
    const search = all(panel).find(item => item.attributes["aria-label"] === "Search model catalog");
    search.value = "aspect_ratio";
    await search.trigger("input");
    assert.equal(all(panel).some(item => item.textContent === "Test Video"), false);
    await all(panel).find(item => item.textContent === "Inspect inputs").trigger("click");
    const schema = all(panel).find(item => item.attributes["aria-label"] === "Documented model input schema");
    assert.deepEqual(JSON.parse(schema.value).required, ["prompt"]);
    await button("Refresh public model definitions").trigger("click");
    assert.equal(requests.at(-1).path, "/crun-next/models/refresh");
    assert.equal(requests.at(-1).method, "POST");
    await button("Close").trigger("click");
});

test("launcher setup does not contact CRUN or the local backend", () => {
    const count = requests.length;
    definition.setup();
    definition.setup();
    assert.equal(requests.length, count);
    assert.equal(all(document.body).filter(item => item.id === "crun-next-launcher").length, 1);
});
