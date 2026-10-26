import { app } from "../../scripts/app.js";

// Model profiles are bundled with the local node definition. Switching a model
// changes only the controls; it never uploads, estimates, submits, or unlinks media.
const states = new WeakMap();
const CONTROLS = new Set(["model", "crun_mode", "crun_allow_upload", "crun_allow_paid_generation", "crun_max_credits", "crun_model_help"]);
const OPTION_KEYS = ["values", "min", "max", "step", "step2", "round", "precision", "tooltip", "default"];
const TECHNICAL_FIELDS = new Set(["byteplus_fallback", "direct_byteplus", "input_compliance", "output_compliance", "content_moderation", "moderation", "disable_safety_filter", "callback_url"]);
const ACTION_HELP = "Prepare stays local. Estimate uploads connected references and requests a price. Generate uploads references and creates a paid task.";

function inputDefinitions(nodeData) {
    return { ...(nodeData?.input?.required || {}), ...(nodeData?.input?.optional || {}) };
}

export function familyProfiles(nodeData) {
    const definition = inputDefinitions(nodeData).model;
    const profiles = Array.isArray(definition) ? definition[1]?.crun_profiles : null;
    return profiles && typeof profiles === "object" && !Array.isArray(profiles) ? profiles : null;
}

function sameValue(first, second) {
    return Object.is(first, second) || (first !== undefined && second !== undefined && JSON.stringify(first) === JSON.stringify(second));
}

function cloneValue(value) {
    return value && typeof value === "object" ? JSON.parse(JSON.stringify(value)) : value;
}

function rememberWidget(widget, definition) {
    const options = definition?.[1] || {};
    return {
        type: widget.type,
        schemaType: definition?.[0],
        options: { ...widget.options },
        computeSize: widget.computeSize,
        label: widget.label,
        hidden: widget.hidden,
        defaultValue: Object.hasOwn(options, "default") ? cloneValue(options.default) : cloneValue(widget.value),
        display: widget.element?.style?.display,
        inputDisplay: widget.inputEl?.style?.display,
    };
}

function visibleWidget(widget, visible, base) {
    const converted = String(widget.type || "").startsWith("converted-widget");
    widget.hidden = !visible;
    widget.options ||= {};
    widget.options.hidden = !visible;
    if (!converted) {
        if (!visible) {
            widget.type = "hidden";
            widget.computeSize = () => [0, -4];
        } else {
            widget.type = base.type;
            widget.computeSize = base.computeSize;
        }
    }
    if (widget.element?.style) widget.element.style.display = visible ? (base.display || "") : "none";
    if (widget.inputEl?.style) widget.inputEl.style.display = visible ? (base.inputDisplay || "") : "none";
    widget.syncLiveVisibilityOptions?.();
}

function choices(field) {
    if (Array.isArray(field?.options?.values)) return field.options.values;
    return Array.isArray(field?.type) ? field.type : null;
}

export function valueFitsProfile(value, field) {
    const values = choices(field);
    if (values?.length) return values.some(option => sameValue(option, value));
    const kind = field?.type;
    if (["INT", "FLOAT", "number", "integer"].includes(kind)) {
        if (typeof value !== "number" || !Number.isFinite(value)) return false;
        if (["INT", "integer"].includes(kind) && !Number.isInteger(value)) return false;
        if (typeof field.options?.min === "number" && value < field.options.min) return false;
        if (typeof field.options?.max === "number" && value > field.options.max) return false;
    }
    if (["BOOLEAN", "boolean"].includes(kind) && typeof value !== "boolean") return false;
    return true;
}

function profileDefault(field, base) {
    if (Object.hasOwn(field.options || {}, "default")) return cloneValue(field.options.default);
    const values = choices(field);
    if (values?.length) return cloneValue(values[0]);
    if (valueFitsProfile(base.defaultValue, field)) return cloneValue(base.defaultValue);
    if (["INT", "FLOAT", "number", "integer"].includes(field.type)) return field.options?.min ?? 0;
    return ["BOOLEAN", "boolean"].includes(field.type) ? false : "";
}

function profileWidget(widget, field, base, visible) {
    visibleWidget(widget, visible, base);
    widget.options ||= {};
    for (const key of OPTION_KEYS) delete widget.options[key];
    const stableOptions = { ...base.options };
    for (const key of OPTION_KEYS) delete stableOptions[key];
    Object.assign(widget.options, stableOptions, field.options || {});
    widget.options.hidden = !visible;
    const converted = String(widget.type || "").startsWith("converted-widget");
    const values = choices(field);
    if (values?.length) {
        widget.options.values = values.map(cloneValue);
        if (!converted && visible) widget.type = "combo";
    } else if (!converted && visible) {
        if (["INT", "FLOAT", "number", "integer"].includes(field.type)) widget.type = "number";
        else if (["BOOLEAN", "boolean"].includes(field.type)) widget.type = "toggle";
        else if (["STRING", "string"].includes(field.type) && ["number", "combo", "toggle"].includes(widget.type)) widget.type = "text";
    }
    const integer = field.schema_type === "integer" || ["INT", "integer"].includes(field.type);
    const floating = field.schema_type === "number" || ["FLOAT", "number"].includes(field.type);
    if (integer || floating) {
        // Profile options are Python input-spec options; Comfy's runtime widgets
        // use step2 for the actual increment and legacy step at 10x that value.
        const specified = field.options?.step2 ?? field.options?.step;
        const increment = typeof specified === "number" && specified > 0 ? specified : integer ? 1 : base.schemaType === "FLOAT" && base.options?.step2 > 0 ? base.options.step2 : 0.01;
        widget.options.step2 = integer ? Math.max(1, Math.round(increment)) : increment;
        widget.options.step = widget.options.step2 * 10;
        widget.options.precision = integer ? 0 : field.options?.precision ?? (base.schemaType === "FLOAT" ? base.options?.precision : undefined) ?? Math.max(0, -Math.floor(Math.log10(increment)));
        widget.options.round = integer ? 1 : field.options?.round ?? Math.pow(10, -widget.options.precision);
    }
    widget.label = `${field.label || field.options?.label || base.options?.label || field.wire_name || widget.name}${field.required ? " *" : ""}`;
    widget.tooltip = field.options?.tooltip || base.options?.tooltip || "";
}

function linkedWidgetVisibility(widget, visible, state) {
    for (const linked of widget.linkedWidgets || []) {
        if (!state.base.has(linked)) state.base.set(linked, rememberWidget(linked));
        visibleWidget(linked, visible, state.base.get(linked));
        const values = linked.options?.values;
        // Seed control-after-generate still runs while hidden. Fixed keeps a
        // hidden, unsupported seed from being randomized into a non-default.
        if (!Array.isArray(values) || !values.includes("fixed") || !values.includes("randomize")) continue;
        if (!visible) {
            if (linked.value !== "fixed") state.linkedValues.set(linked, linked.value);
            linked.value = "fixed";
        } else if (state.linkedValues.has(linked)) {
            linked.value = state.linkedValues.get(linked);
            state.linkedValues.delete(linked);
        }
    }
}

function capabilityText(profile, warnings, changed) {
    const lines = [];
    if (profile.capability_text || profile.description) lines.push(profile.capability_text || profile.description);
    if (profile.model_id) lines.push(`Model: ${profile.model_id}`);
    if (profile.generation_supported === false) lines.push("This operation is currently prepare-only.");
    lines.push(ACTION_HELP);
    if (warnings.length) lines.push(...warnings);
    if (changed.length) lines.push(`Updated for this model: ${changed.join(", ")}. Review before generating.`);
    return lines.join("\n");
}

function drawHelp(node, state, text, warning = false) {
    node._crunCapabilityText = text;
    if (state.help) {
        state.help.textContent = text;
        state.help.style.borderColor = warning ? "#c99352" : "#3b747d";
        state.help.setAttribute("aria-live", "polite");
    }
}

function makeHelp(node, state) {
    if (typeof document === "undefined" || typeof node.addDOMWidget !== "function" || state.help) return;
    const element = document.createElement("div");
    element.style.cssText = "overflow:auto;box-sizing:border-box;width:100%;height:100%;padding:9px 11px;border-radius:7px;background:#10252d;color:#cce6e7;font:12px/1.45 sans-serif";
    const help = document.createElement("div");
    help.style.cssText = "white-space:pre-wrap;border-left:2px solid #3b747d;padding-left:8px";
    help.setAttribute("role", "status");
    const advanced = document.createElement("button");
    advanced.type = "button";
    advanced.textContent = "Show advanced controls";
    advanced.style.cssText = "margin-top:7px;padding:3px 7px;border:1px solid #3b747d;border-radius:4px;background:#17343c;color:#cce6e7;font:11px sans-serif;cursor:pointer";
    advanced.setAttribute("aria-expanded", "false");
    advanced.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        toggleAdvancedControls(node);
    });
    element.append(help, advanced);
    const widget = node.addDOMWidget("crun_model_help", "info", element, {
        serialize: false,
        getMinHeight: () => 112,
        getMaxHeight: () => 150,
        hideOnZoom: true,
    });
    if (widget) {
        widget.serialize = false;
        widget.options ||= {};
        widget.options.serialize = false;
    }
    state.help = help;
    state.advancedButton = advanced;
}

export function toggleAdvancedControls(node) {
    const state = states.get(node);
    if (!state) return;
    state.showAdvanced = !state.showAdvanced;
    if (state.advancedButton) {
        state.advancedButton.textContent = state.showAdvanced ? "Hide advanced controls" : "Show advanced controls";
        state.advancedButton.setAttribute("aria-expanded", String(state.showAdvanced));
    }
    refreshNodeControls(node, { reason: "advanced" });
}

function simpleExecutionControls(node, state) {
    for (const name of ["crun_allow_upload", "crun_allow_paid_generation"]) {
        const widget = node.widgets?.find(item => item.name === name);
        if (widget && state.base.has(widget)) visibleWidget(widget, false, state.base.get(widget));
    }
    const cap = node.widgets?.find(item => item.name === "crun_max_credits");
    if (cap && state.base.has(cap)) {
        visibleWidget(cap, state.showAdvanced, state.base.get(cap));
        cap.label = "Optional credit cap (0 = none)";
        cap.tooltip = "Optional ceiling for the estimated CRUN credits. Zero disables the optional cap; an existing positive cap is retained.";
    }
    const mode = node.widgets?.find(item => item.name === "crun_mode");
    if (mode) mode.label = "Action";
    const take = node.widgets?.find(item => item.name === "take");
    if (take) {
        take.label = "Take";
        take.tooltip = "Keep the same take to resume or reuse its result. Change the take only when you want another generation.";
    }
}

function refreshNodeControls(node, options = {}) {
    return states.get(node)?.kind === "legacy" ? applyLegacyControls(node) : applyFamilyProfile(node, options);
}

export function applyFamilyProfile(node, { reason = "refresh" } = {}) {
    const state = states.get(node);
    if (!state || state.applying) return null;
    const selector = node.widgets?.find(widget => widget.name === "model");
    const profile = selector && state.profiles[selector.value];
    if (!profile) {
        drawHelp(node, state, "This saved model is not in this node's current catalog. Select an available model before running.", true);
        return null;
    }
    state.applying = true;
    try {
        const changed = [];
        const warnings = [];
        const switchModel = reason === "model-change" && state.model !== selector.value;
        if (switchModel) {
            for (const [name, value] of [["crun_mode", "prepare"], ["crun_allow_upload", false], ["crun_allow_paid_generation", false]]) {
                const widget = node.widgets?.find(item => item.name === name);
                if (widget) widget.value = value;
            }
            warnings.push("Model changed: execution reset to prepare. Review the selected model before generating; your optional credit cap was retained.");
        }
        for (const widget of node.widgets || []) {
            if (CONTROLS.has(widget.name) || !state.managed.has(widget.name)) continue;
            const base = state.base.get(widget);
            if (!base) continue;
            const field = profile.fields?.[widget.name];
            if (!field || field.visible === false) {
                visibleWidget(widget, false, base);
                linkedWidgetVisibility(widget, false, state);
                if (!sameValue(widget.value, base.defaultValue)) {
                    widget.value = cloneValue(base.defaultValue);
                    changed.push(`${widget.name} cleared (unsupported)`);
                }
                continue;
            }
            profileWidget(widget, field, base, !field.advanced || state.showAdvanced);
            linkedWidgetVisibility(widget, !field.advanced || state.showAdvanced, state);
            if (!valueFitsProfile(widget.value, field)) {
                if (reason === "configure" || reason === "loaded") warnings.push(`Saved ${widget.name} is outside this model's supported choices/range; choose a supported value.`);
                else {
                    widget.value = profileDefault(field, base);
                    changed.push(widget.name);
                }
            }
        }
        // Creative completion/recovery controls belong to the wrapper rather
        // than a model profile. Respect their declared Advanced flag too.
        for (const widget of node.widgets || []) {
            if (!state.wrapperAdvanced.has(widget.name) || !state.base.has(widget)) continue;
            visibleWidget(widget, state.showAdvanced, state.base.get(widget));
            linkedWidgetVisibility(widget, state.showAdvanced, state);
        }
        simpleExecutionControls(node, state);
        const inputs = profile.inputs || {};
        for (const input of node.inputs || []) {
            if (!state.nativeInputs.has(input.name)) continue;
            const supported = inputs[input.name];
            const label = state.inputLabels.get(input.name) || input.name;
            input.label = supported ? `${supported.label || label}${supported.required ? " *" : ""}` : `${label} (unsupported by selected model)`;
            if (!supported && input.link !== null && input.link !== undefined) warnings.push(`Disconnect ${label}: this model does not accept that reference. Its link was preserved.`);
        }
        drawHelp(node, state, capabilityText(profile, warnings, changed), warnings.length > 0);
        state.model = selector.value;
        node.setDirtyCanvas?.(true, true);
        return { model: selector.value, warnings, changed };
    } finally {
        state.applying = false;
    }
}

export function attachFamilyControls(node, nodeData) {
    if (states.has(node)) return states.get(node);
    const profiles = familyProfiles(nodeData);
    if (!profiles) return null;
    const definitions = inputDefinitions(nodeData);
    const managed = new Set(Object.values(profiles).flatMap(profile => Object.keys(profile.fields || {})));
    const nativeInputs = new Set(Object.values(profiles).flatMap(profile => Object.keys(profile.inputs || {})));
    const wrapperAdvanced = new Set(Object.entries(definitions).filter(([name, spec]) => !managed.has(name) && spec?.[1]?.advanced).map(([name]) => name));
    const state = { kind: "family", profiles, managed, nativeInputs, wrapperAdvanced, base: new Map(), inputLabels: new Map(), linkedValues: new Map(), model: null, help: null, applying: false, showAdvanced: false, advancedButton: null };
    states.set(node, state);
    for (const widget of node.widgets || []) {
        state.base.set(widget, rememberWidget(widget, definitions[widget.name]));
        if (definitions[widget.name]?.[1]?.label) widget.label = definitions[widget.name][1].label;
    }
    for (const input of node.inputs || []) state.inputLabels.set(input.name, input.label || input.name);
    for (const name of ["model", "crun_mode"]) {
        const widget = node.widgets?.find(item => item.name === name);
        if (!widget) continue;
        const original = widget.callback;
        widget.callback = function () {
            const result = original?.apply(this, arguments);
            applyFamilyProfile(node, { reason: name === "model" ? "model-change" : "mode-change" });
            return result;
        };
    }
    makeHelp(node, state);
    applyFamilyProfile(node, { reason: "created" });
    if (!node.color) node.color = "#17424a";
    if (!node.bgcolor) node.bgcolor = "#17262d";
    node.setSize?.([Math.max(440, node.size?.[0] || 0), Math.max(320, node.size?.[1] || 0)]);
    return state;
}

export function applyLegacyControls(node) {
    const state = states.get(node);
    if (!state || state.kind !== "legacy") return null;
    for (const input of node.inputs || []) {
        if (state.nativeLabels.has(input.name)) input.label = state.nativeLabels.get(input.name);
    }
    for (const widget of node.widgets || []) {
        if (!state.advancedFields.has(widget.name) || !state.base.has(widget)) continue;
        visibleWidget(widget, state.showAdvanced, state.base.get(widget));
        linkedWidgetVisibility(widget, state.showAdvanced, state);
    }
    simpleExecutionControls(node, state);
    drawHelp(node, state, ACTION_HELP);
    node.setDirtyCanvas?.(true, true);
    return state;
}

export function attachLegacyControls(node, nodeData) {
    if (states.has(node)) return states.get(node);
    const definitions = inputDefinitions(nodeData);
    if (!definitions.crun_mode) return null;
    const mediaWires = new Set();
    for (const spec of Object.values(definitions)) {
        if (!["IMAGE", "MASK", "VIDEO", "AUDIO"].includes(spec?.[0])) continue;
        const options = spec[1] || {};
        const wire = options.crun_wire_name || /^Native (?:image|mask|video|audio) reference for ([A-Za-z0-9_]+)\./.exec(options.tooltip || "")?.[1];
        if (wire) mediaWires.add(wire);
    }
    const advancedFields = new Set();
    for (const [name, spec] of Object.entries(definitions)) {
        if (["IMAGE", "MASK", "VIDEO", "AUDIO"].includes(spec?.[0]) || CONTROLS.has(name)) continue;
        if (spec?.[1]?.advanced || TECHNICAL_FIELDS.has(name) || mediaWires.has(name) || mediaWires.has(name.replace(/_urls?$/, ""))) advancedFields.add(name);
    }
    const nativeLabels = new Map(Object.entries(definitions).filter(([, spec]) => ["IMAGE", "MASK", "VIDEO", "AUDIO"].includes(spec?.[0]) && spec?.[1]?.label).map(([name, spec]) => [name, spec[1].label]));
    const state = { kind: "legacy", advancedFields, nativeLabels, base: new Map(), linkedValues: new Map(), showAdvanced: false, help: null, advancedButton: null };
    states.set(node, state);
    for (const widget of node.widgets || []) {
        state.base.set(widget, rememberWidget(widget, definitions[widget.name]));
        if (definitions[widget.name]?.[1]?.label) widget.label = definitions[widget.name][1].label;
    }
    const mode = node.widgets?.find(item => item.name === "crun_mode");
    if (mode) {
        const original = mode.callback;
        mode.callback = function () {
            const result = original?.apply(this, arguments);
            applyLegacyControls(node);
            return result;
        };
    }
    makeHelp(node, state);
    applyLegacyControls(node);
    return state;
}

app.registerExtension({
    name: "CRUN.Next.ModelFamilies",
    beforeRegisterNodeDef(nodeType, nodeData) {
        const profiles = familyProfiles(nodeData);
        if (!profiles && !(String(nodeData?.name || "").startsWith("CRUN_") && inputDefinitions(nodeData).crun_mode)) return;
        const attach = profiles ? attachFamilyControls : attachLegacyControls;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            attach(this, nodeData);
            return result;
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = configure?.apply(this, arguments);
            attach(this, nodeData);
            refreshNodeControls(this, { reason: "configure" });
            return result;
        };
        const connections = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = connections?.apply(this, arguments);
            refreshNodeControls(this, { reason: "connections" });
            return result;
        };
    },
    loadedGraphNode(node) {
        refreshNodeControls(node, { reason: "loaded" });
    },
});
