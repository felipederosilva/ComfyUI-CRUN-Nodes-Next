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

test("creative Take stays visible while wrapper recovery and polling fields follow Advanced", () => {
    const data = definition();
    data.input.optional.take = ["INT", { default: 1, label: "Take" }];
    for (const [name, label] of [["resume_task_id", "Resume task ID"], ["result_index", "Result index"], ["timeout_seconds", "Wait timeout"], ["poll_interval", "Status interval"]]) {
        data.input.optional[name] = [name === "resume_task_id" ? "STRING" : "INT", { default: name === "resume_task_id" ? "" : 1, advanced: true, label }];
    }
    const node = makeNode();
    node.widgets.push(widget("take", 5), widget("resume_task_id", "saved_task", "text"), widget("result_index", 0), widget("timeout_seconds", 1200), widget("poll_interval", 3));
    ui.attachFamilyControls(node, data);
    assert.equal(byName(node, "take").hidden, undefined);
    assert.equal(byName(node, "take").label, "Take");
    assert.match(byName(node, "take").tooltip, /resume or reuse/);
    for (const name of ["resume_task_id", "result_index", "timeout_seconds", "poll_interval"]) assert.equal(byName(node, name).hidden, true);
    ui.toggleAdvancedControls(node);
    assert.equal(byName(node, "resume_task_id").hidden, false);
    assert.equal(byName(node, "resume_task_id").label, "Resume task ID");
    change(node, "model", "Seedance 2.0");
    assert.equal(byName(node, "take").value, 5);
    assert.equal(byName(node, "resume_task_id").value, "saved_task");
    ui.toggleAdvancedControls(node);
    assert.equal(byName(node, "resume_task_id").hidden, true);
    assert.equal(byName(node, "resume_task_id").value, "saved_task");
});

test("schema human labels apply within model profiles without changing wire names", () => {
    const data = definition();
    data.input.required.model[1].crun_profiles["Seedance 1.5 Pro"].fields.prompt.options.label = "Scene prompt";
    const node = makeNode();
    ui.attachFamilyControls(node, data);
    assert.equal(byName(node, "prompt").label, "Scene prompt *");
    assert.equal(byName(node, "prompt").name, "prompt");
    assert.equal(node.inputs[0].link, 1);
});

test("model changes update choices and reset to prepare while retaining an existing positive optional cap", () => {
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
    assert.equal(byName(node, "crun_max_credits").value, 99);
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

test("actions hide obsolete checkboxes and leave the optional cap in advanced controls", () => {
    const node = makeNode();
    ui.attachFamilyControls(node, definition());
    change(node, "crun_mode", "estimate");
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, true);
    assert.equal(byName(node, "crun_allow_upload").hidden, true);
    change(node, "crun_mode", "generate");
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, true);
    assert.equal(byName(node, "crun_max_credits").hidden, true);
    ui.toggleAdvancedControls(node);
    assert.equal(byName(node, "crun_allow_upload").hidden, true);
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, true);
    assert.equal(byName(node, "crun_max_credits").hidden, false);
    assert.equal(byName(node, "crun_max_credits").label, "Optional credit cap (0 = none)");
    change(node, "crun_mode", "prepare");
    assert.equal(byName(node, "crun_max_credits").hidden, false);
    assert.equal(byName(node, "crun_allow_upload").hidden, true);
    assert.match(node._crunCapabilityText, /Estimate uploads connected references and requests a price/);
    assert.match(node._crunCapabilityText, /Generate uploads references and creates a paid task/);
});

test("legacy model nodes get the same simple actions and advanced optional cap without changing saved values or sockets", () => {
    const node = makeNode();
    node.widgets = node.widgets.filter(widget => !["model", "duration", "resolution", "generate_audio"].includes(widget.name));
    byName(node, "crun_max_credits").value = 100;
    const technical = widget("byteplus_fallback", true, "toggle");
    node.widgets.push(technical);
    const data = { name: "CRUN_Next_Legacy_Example", input: { required: {
        prompt: ["STRING", { default: "" }], image_url: ["STRING", { default: "" }],
        crun_mode: [["prepare", "estimate", "generate"], { default: "prepare" }],
        crun_allow_upload: ["BOOLEAN", { default: false }], crun_allow_paid_generation: ["BOOLEAN", { default: false }],
        crun_max_credits: ["FLOAT", { default: 0 }], byteplus_fallback: ["BOOLEAN", { default: false }],
    }, optional: { first_frame: ["IMAGE", { crun_wire_name: "image_url", label: "First frame" }] } } };
    ui.attachLegacyControls(node, data);
    assert.equal(byName(node, "image_url").hidden, true);
    assert.equal(technical.hidden, true);
    assert.equal(byName(node, "crun_max_credits").hidden, true);
    assert.equal(byName(node, "crun_max_credits").value, 100);
    assert.equal(node.inputs[0].link, 1);
    assert.equal(node.inputs[0].label, "First frame");
    change(node, "crun_mode", "generate");
    assert.equal(byName(node, "crun_allow_upload").hidden, true);
    assert.equal(byName(node, "crun_allow_paid_generation").hidden, true);
    ui.toggleAdvancedControls(node);
    assert.equal(byName(node, "image_url").hidden, false);
    assert.equal(technical.hidden, false);
    assert.equal(technical.value, true);
    assert.equal(byName(node, "crun_max_credits").hidden, false);
    assert.equal(byName(node, "crun_max_credits").value, 100);
    extension.loadedGraphNode(node);
    assert.equal(byName(node, "crun_max_credits").value, 100);
});

test("legacy lifecycle hooks attach only to CRUN execution nodes and preserve widget serialization positions", () => {
    const data = { name: "CRUN_Next_Fixed_Model", input: definition().input };
    delete data.input.required.model;
    class Type {
        onNodeCreated() { Object.assign(this, makeNode()); this.widgets = this.widgets.filter(widget => widget.name !== "model"); }
    }
    extension.beforeRegisterNodeDef(Type, data);
    const node = new Type(); node.onNodeCreated();
    const names = node.widgets.map(widget => widget.name);
    byName(node, "crun_max_credits").value = 100;
    node.onConfigure();
    assert.deepEqual(node.widgets.map(widget => widget.name), names);
    assert.equal(byName(node, "crun_max_credits").value, 100);
    assert.equal(byName(node, "crun_allow_upload").hidden, true);
    class Other { onNodeCreated() { return "unchanged"; } }
    const original = Other.prototype.onNodeCreated;
    extension.beforeRegisterNodeDef(Other, { ...data, name: "Other_Plugin" });
    assert.equal(Other.prototype.onNodeCreated, original);
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
