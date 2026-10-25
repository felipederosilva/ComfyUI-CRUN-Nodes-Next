import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const source = await readFile(new URL("../web/crun_model_nodes.js", import.meta.url), "utf8");
let extension;
globalThis.__crunFamilyTestApp = { registerExtension(value) { extension = value; } };
const executable = source.replace(/^import \{ app \}.*$/m, "const app = globalThis.__crunFamilyTestApp;");
const ui = await import(`data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`);

function definition() {
    return { input: { required: {
        model: [["Seedance 1.5 Pro", "Seedance 2.0"], { default: "Seedance 1.5 Pro", crun_profiles: {
            "Seedance 1.5 Pro": {
                model_id: "seedance/1.5-i2v", capability_text: "Image to video · first frame · 4, 8 or 12 seconds",
                fields: {
                    prompt: { type: "STRING", required: true, wire_name: "prompt", options: { default: "", multiline: true } },
                    duration: { type: "COMBO", options: { values: ["4", "8", "12"], default: "4" } },
                    resolution: { type: "COMBO", options: { values: ["720p", "1080p"], default: "720p" } },
                    image_url: { type: "STRING", advanced: true, options: { default: "" } },
                },
                inputs: { first_frame: { type: "IMAGE", required: true, label: "First frame" } },
            },
            "Seedance 2.0": {
                model_id: "seedance/2.0-i2v", capability_text: "Image to video · first and optional last frame · 4–15 seconds",
                fields: {
                    prompt: { type: "STRING", required: true, options: { default: "", multiline: true } },
                    duration: { type: "INT", options: { min: 4, max: 15, default: 5 } },
                    resolution: { type: "COMBO", options: { values: ["480p", "720p"], default: "720p" } },
                    generate_audio: { type: "BOOLEAN", options: { default: true } },
                },
                inputs: { first_frame: { type: "IMAGE", required: true, label: "First frame" }, last_frame: { type: "IMAGE", required: false, label: "Last frame" } },
            },
        } }],
    }, optional: {
        prompt: ["STRING", { default: "" }], duration: ["INT", { default: 4 }], image_url: ["STRING", { default: "" }],
        resolution: [["720p", "1080p", "480p"], { default: "720p" }],
        generate_audio: ["BOOLEAN", { default: false }],
        crun_mode: [["prepare", "estimate", "generate"], { default: "prepare" }],
        crun_allow_upload: ["BOOLEAN", { default: false }],
        crun_allow_paid_generation: ["BOOLEAN", { default: false }],
        crun_max_credits: ["FLOAT", { default: 0 }],
    } } };
}

function widget(name, value, type = "number") {
    return { name, value, type, options: {}, computeSize() { return [100, 20]; } };
}

function makeNode() {
    return {
        widgets: [widget("model", "Seedance 1.5 Pro", "combo"), widget("prompt", "A fictional scene", "customtext"),
            widget("duration", 4), widget("resolution", "720p", "combo"), widget("generate_audio", false, "toggle"), widget("image_url", "", "text"),
            widget("crun_mode", "prepare", "combo"), widget("crun_allow_upload", false, "toggle"), widget("crun_allow_paid_generation", false, "toggle"), widget("crun_max_credits", 0)],
        inputs: [{ name: "first_frame", type: "IMAGE", link: 1 }, { name: "last_frame", type: "IMAGE", link: null }],
        size: [300, 300],
        setSize(size) { this.size = size; },
        setDirtyCanvas() {},
    };
}

const byName = (node, name) => node.widgets.find(widget => widget.name === name);
function change(node, name, value) {
    const field = byName(node, name);
    field.value = value;
    field.callback?.(value);
}

test("family extension is opt-in through bundled profiles and performs no network", () => {
    assert.equal(extension.name, "CRUN.Next.ModelFamilies");
    assert.equal(ui.familyProfiles({ input: { required: { model: [["generic"]] } } }), null);
    assert.ok(ui.familyProfiles(definition()));
    assert.equal(/fetch\(|fetchApi|XMLHttpRequest|CreateTask|localStorage|innerHTML/.test(source), false);
});

test("created node exposes only selected model controls, keeping native inputs", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    assert.equal(byName(node, "generate_audio").hidden, true);
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, true);
    assert.deepEqual(byName(node, "duration").options.values, ["4", "8", "12"]);
    assert.equal(byName(node, "duration").value, "4");
    assert.equal(node.inputs[0].link, 1);
    assert.equal(node.inputs[1].label, "last_frame (unsupported by selected model)");
    assert.match(node._crunCapabilityText, /seedance\/1.5-i2v/);
    assert.ok(node.size[0] >= 440);
});

test("model changes update ranges and dropdowns, visibly reset invalid values and disarm execution", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    change(node, "resolution", "1080p");
    change(node, "crun_mode", "generate");
    byName(node, "crun_allow_paid_generation").value = true;
    byName(node, "crun_allow_upload").value = true;
    byName(node, "crun_max_credits").value = 99;
    change(node, "model", "Seedance 2.0");
    assert.equal(byName(node, "duration").type, "number");
    assert.equal(byName(node, "duration").options.min, 4);
    assert.equal(byName(node, "duration").options.max, 15);
    assert.equal(byName(node, "resolution").value, "720p");
    assert.deepEqual(byName(node, "resolution").options.values, ["480p", "720p"]);
    assert.equal(byName(node, "generate_audio").hidden, false);
    assert.equal(byName(node, "crun_mode").value, "prepare");
    assert.equal(byName(node, "crun_allow_paid_generation").value, false);
    assert.equal(byName(node, "crun_allow_upload").value, false);
    assert.equal(byName(node, "crun_max_credits").value, 0);
    assert.equal(byName(node, "prompt").value, "A fictional scene");
    assert.match(node._crunCapabilityText, /execution reset to prepare/);
    assert.match(node._crunCapabilityText, /resolution/);
});

test("unsupported values clear to union default while reference links are preserved and explained", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    change(node, "model", "Seedance 2.0");
    change(node, "generate_audio", true);
    node.inputs[1].link = 88;
    change(node, "model", "Seedance 1.5 Pro");
    assert.equal(byName(node, "generate_audio").hidden, true);
    assert.equal(byName(node, "generate_audio").value, false);
    assert.equal(node.inputs[1].link, 88);
    assert.match(node._crunCapabilityText, /Disconnect last_frame/);
    assert.match(node._crunCapabilityText, /link was preserved/);
    assert.match(node._crunCapabilityText, /generate_audio cleared/);
});

test("workflow restore keeps supported values and flags invalid saved values without silent coercion", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    byName(node, "model").value = "Seedance 2.0";
    byName(node, "duration").value = 30;
    byName(node, "prompt").value = "Saved user's prompt";
    ui.applyFamilyProfile(node, { reason: "loaded" });
    assert.equal(byName(node, "duration").value, 30);
    assert.equal(byName(node, "prompt").value, "Saved user's prompt");
    assert.match(node._crunCapabilityText, /Saved duration is outside/);
    assert.equal(byName(node, "duration").options.max, 15);
});

test("mode change reveals paid controls only for explicit generation", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    change(node, "crun_mode", "estimate");
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, true);
    assert.equal(byName(node, "crun_allow_upload").hidden, false);
    change(node, "crun_mode", "generate");
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, false);
    assert.equal(byName(node, "crun_max_credits").hidden, false);
    change(node, "crun_mode", "prepare");
    assert.equal(byName(node, "crun_max_credits").hidden, true);
    assert.equal(byName(node, "crun_allow_upload").hidden, true);
});

test("advanced URL fallback controls stay secondary without hiding native image connectors", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    assert.equal(byName(node, "image_url").hidden, true);
    ui.toggleAdvancedControls(node);
    assert.equal(byName(node, "image_url").hidden, false);
    assert.equal(node.inputs[0].type, "IMAGE");
    assert.equal(node.inputs[0].link, 1);
    ui.toggleAdvancedControls(node);
    assert.equal(byName(node, "image_url").hidden, true);
});

test("integer profiles render whole seconds and float profiles restore fractional increments", () => {
    const data = definition();
    const profiles = data.input.required.model[1].crun_profiles;
    profiles["Seedance 1.5 Pro"].fields.duration = { type: "INT", schema_type: "integer", options: { min: 4, max: 12, default: 4 } };
    profiles["Seedance 2.0"].fields.duration = { type: "FLOAT", schema_type: "number", options: { min: 4, max: 15, step: 0.25, default: 5.25 } };
    data.input.optional.duration = ["FLOAT", { default: 4, step: 0.25 }];
    const node = makeNode();
    const duration = byName(node, "duration");
    duration.options = { precision: 3, step: 2.5, step2: 0.25, round: 0.001 };
    ui.attachFamilyControls(node, data);
    assert.equal(duration.options.precision, 0);
    assert.equal(duration.options.step2, 1);
    assert.equal(duration.options.step, 10);
    assert.equal(duration.options.round, 1);
    assert.equal(duration.value, 4);
    change(node, "model", "Seedance 2.0");
    assert.equal(duration.options.precision, 3);
    assert.equal(duration.options.step2, 0.25);
    assert.equal(duration.options.step, 2.5);
    assert.equal(duration.options.round, 0.001);
    duration.value = 8.25;
    change(node, "model", "Seedance 1.5 Pro");
    assert.equal(duration.options.precision, 0);
    assert.equal(duration.value, 4);
    assert.match(node._crunCapabilityText, /duration/);
});

test("hidden advanced seeds hide and pause their linked randomize control, then restore it", () => {
    const data = definition();
    data.input.required.model[1].crun_profiles["Seedance 1.5 Pro"].fields.seed = { type: "INT", advanced: true, options: { default: 0 } };
    data.input.optional.seed = ["INT", { default: 0 }];
    const node = makeNode();
    const seed = widget("seed", 0);
    const control = widget("control_after_generate", "randomize", "combo");
    control.options.values = ["fixed", "increment", "decrement", "randomize"];
    seed.linkedWidgets = [control];
    node.widgets.push(seed, control);
    ui.attachFamilyControls(node, data);
    assert.equal(control.hidden, true);
    assert.equal(control.value, "fixed");
    ui.toggleAdvancedControls(node);
    assert.equal(seed.hidden, false);
    assert.equal(control.hidden, false);
    assert.equal(control.type, "combo");
    assert.equal(control.value, "randomize");
    change(node, "model", "Seedance 2.0");
    assert.equal(seed.hidden, true);
    assert.equal(control.hidden, true);
    assert.equal(control.value, "fixed");
    assert.equal(node.inputs[0].link, 1);
});

test("lifecycle wrappers preserve earlier extension callbacks and reapply after configure", () => {
    const calls = [];
    class Type {
        onNodeCreated() { calls.push("created"); Object.assign(this, makeNode()); return "prior-result"; }
        onConfigure() { calls.push("configure"); byName(this, "model").value = "Seedance 2.0"; byName(this, "duration").value = 10; }
        onConnectionsChange() { calls.push("connections"); }
    }
    extension.beforeRegisterNodeDef(Type, definition());
    const node = new Type();
    assert.equal(node.onNodeCreated(), "prior-result");
    node.onConfigure();
    extension.loadedGraphNode(node);
    node.onConnectionsChange();
    assert.deepEqual(calls, ["created", "configure", "connections"]);
    assert.equal(byName(node, "duration").value, 10);
    assert.equal(byName(node, "generate_audio").hidden, false);
});

test("unknown saved model surfaces a useful error without changing links or choosing another model", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    byName(node, "model").value = "Model no longer listed";
    assert.equal(ui.applyFamilyProfile(node, { reason: "loaded" }), null);
    assert.equal(byName(node, "model").value, "Model no longer listed");
    assert.equal(node.inputs[0].link, 1);
    assert.match(node._crunCapabilityText, /not in this node's current catalog/);
});

test("every bundled family profile can switch without stale choices or broken reference connections", () => {
    const root = fileURLToPath(new URL("..", import.meta.url));
    const script = "import json; from pathlib import Path; from family_nodes import family_catalog,make_family_node; entries=json.loads(Path('data/catalog.json').read_text(encoding='utf-8'))['entries']; print(json.dumps([{'input':make_family_node(f).INPUT_TYPES()} for f in family_catalog(entries)]))";
    const result = spawnSync(process.env.PYTHON || "python", ["-c", script], { cwd: root, encoding: "utf8", maxBuffer: 8 * 1024 * 1024 });
    assert.equal(result.status, 0, result.stderr);
    const definitions = JSON.parse(result.stdout);
    assert.ok(definitions.length > 20);
    let profilesChecked = 0;
    for (const data of definitions) {
        const node = makeNode();
        node.widgets = [];
        node.inputs = [];
        for (const [name, spec] of Object.entries({ ...data.input.required, ...data.input.optional })) {
            const type = spec[0];
            const options = spec[1] || {};
            if (["IMAGE", "MASK", "AUDIO", "VIDEO"].includes(type)) {
                node.inputs.push({ name, type, link: 7 });
                continue;
            }
            const runtimeType = Array.isArray(type) ? "combo" : ["INT", "FLOAT"].includes(type) ? "number" : type === "BOOLEAN" ? "toggle" : "text";
            const value = options.default ?? (Array.isArray(type) ? type[0] : type === "BOOLEAN" ? false : ["INT", "FLOAT"].includes(type) ? 0 : "");
            node.widgets.push({ ...widget(name, value, runtimeType), options: { ...options, ...(Array.isArray(type) ? { values: type } : {}) } });
        }
        ui.attachFamilyControls(node, data);
        for (const model of Object.keys(ui.familyProfiles(data))) {
            change(node, "model", model);
            for (const [name, field] of Object.entries(ui.familyProfiles(data)[model].fields)) {
                const control = byName(node, name);
                assert.ok(control, `${model}: missing control ${name}`);
                const choices = field.options?.values;
                if (choices?.length && !field.advanced) assert.ok(choices.includes(control.value), `${model}: stale ${name} choice ${control.value}`);
            }
            assert.ok(node.inputs.every(input => input.link === 7), "Changing a model must never remove references");
            profilesChecked++;
        }
    }
    assert.ok(profilesChecked > 100);
});
