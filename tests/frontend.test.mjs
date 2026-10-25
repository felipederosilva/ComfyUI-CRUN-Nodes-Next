import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const sourceUrl = new URL("../web/crun_next.js", import.meta.url);
const source = await readFile(sourceUrl, "utf8");
const requests = [];
let definition;

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
        if (path.endsWith("/status")) payload = { ok: true, configured: true, source: "saved", key_hint: "••••abcd", nonce: "fake-test-nonce", version: "0.1.0" };
        if (path.endsWith("/connection")) payload = { ok: true, balance: 0 };
        if (path.endsWith("/effects/catalog")) payload = { ok: true, cards: [{ id: "test-effect", provider: "kling", name: "<img src=x onerror=alert(1)>", category: "Test", required_images: 2, credits: 0, preview_url: "https://cdn.example.com/preview.mp4" }] };
        if (path.endsWith("/tools")) payload = { ok: true, tools: [{ id: "upscale", name: "Upscale", category: "Image", description: "Provider utility", documentation_url: "https://docs.crun.ai/ai-tools/image-upscale", status: "planned" }] };
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
    assert.equal(plan.execution, "disabled_in_skeleton");
    assert.equal(plan.required_images, 2);
    assert.deepEqual(plan.inputs.image_urls, []);
    assert.equal(ui.effectPlan(cards[1]).required_images, null);
});

test("Comfy registration has no persisted credential setting", () => {
    assert.equal(definition.name, "CRUN.Next.Workspace");
    assert.equal(definition.settings.length, 1);
    assert.equal(definition.settings[0].type, "boolean");
    assert.equal(definition.commands[0].id, "CRUNNext.OpenWorkspace");
    assert.equal(/localStorage|sessionStorage|innerHTML|console\.log/.test(source), false);
    assert.equal(/CreateTask|create_task/.test(source), false);
});

test("workspace uses ephemeral key entry and explicit catalog requests", async () => {
    const prior = new Element("button", document);
    document.body.append(prior);
    prior.focus();
    ui.openCrunWorkspace();
    await tick();
    assert.equal(requests.length, 1);
    assert.equal(requests[0].path, "/crun-next/status");
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
    assert.equal(all(document.body).some(item => item.textContent === "PLANNED · NOT RUNNABLE"), true);
    password.value = "unsaved-fake-key";
    await button("Close").trigger("click");
    assert.equal(password.value, "");
    assert.equal(document.activeElement, prior);
    assert.equal(document.getElementById("crun-api-key-entry"), null);
});

test("launcher setup does not contact CRUN or the local backend", () => {
    const count = requests.length;
    definition.setup();
    definition.setup();
    assert.equal(requests.length, count);
    assert.equal(all(document.body).filter(item => item.id === "crun-next-launcher").length, 1);
});
