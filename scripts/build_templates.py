"""Build one safe Comfy workflow for every bundled model/effect/tool option."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generated_nodes import generated_mappings, load_effect_entries, node_id_for, image_bindings, _input_schema
from creative_nodes import creative_mappings, media_node_id, output_kind

NATIVE = {"IMAGE", "MASK", "VIDEO", "AUDIO"}


def bundled_entries() -> list[dict]:
    """Pin distributed templates to reviewed bundled data, never a user cache."""
    source = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    models = source["entries"]
    return models + load_effect_entries(base_entries=models)


def _filename(entry: dict) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "-", str(entry.get("title") or entry["model"])).strip("-").lower()[:58] or "option"
    digest = hashlib.sha256(str(entry["id"]).encode()).hexdigest()[:12]
    return f"{name}-{digest}.json"


def node_fields(node_type):
    """Match Comfy widget order while serializing only real native input ports."""
    widget_values, inputs = [], []
    for section in ("required", "optional"):
        for name, spec in node_type.INPUT_TYPES().get(section, {}).items():
            kind = spec[0]
            options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if isinstance(kind, str) and (kind in NATIVE or options.get("forceInput")):
                inputs.append({"name": name, "type": kind, "link": None, "slot_index": len(inputs)})
                continue
            value = options.get("default", kind[0] if isinstance(kind, list) and kind else False if kind == "BOOLEAN" else 0 if kind in ("INT", "FLOAT") else "")
            widget_values.append(value)
            if options.get("control_after_generate"):
                widget_values.append("fixed")
    return widget_values, inputs


def source_requirements(entry, node_type, profile=None, task=""):
    """Connect the documented minimum, with one practical edit/reference image."""
    definition = node_type.INPUT_TYPES()
    native = {name: spec[0] for section in ("required", "optional") for name, spec in definition.get(section, {}).items() if isinstance(spec[0], str) and spec[0] in NATIVE}
    schema = _input_schema(entry)
    fields = schema.get("properties", {})
    required = set(schema.get("required", []))
    bindings = {item["socket"]: item for item in image_bindings(entry)}
    supported = profile.get("inputs", {}) if profile is not None else native
    selected, wires = [], {}
    for name, kind in native.items():
        if name not in supported:
            continue
        binding = bindings.get(name, {})
        wire = binding.get("wire_name", name)
        wires.setdefault(wire, []).append(name)
    for wire, names in wires.items():
        field = fields.get(wire, {})
        minimum = field.get("minItems", 0)
        minimum = minimum if isinstance(minimum, int) and not isinstance(minimum, bool) else 0
        # An optional array's minItems applies only when it is supplied. It is
        # not a reason to preconnect otherwise optional video/audio references.
        if wire not in required:
            continue
        # IMAGE batches satisfy an array through one port; separate first/last
        # or fixed Effect sockets each represent one ordered item.
        if len(names) > 1:
            count = max(1, minimum)
            selected.extend(names[:count])
        else:
            selected.extend(names)
    images = [name for name in native if name in supported and native[name] == "IMAGE"]
    preferred = next((name for name in ("first_frame", "reference_images", "image", "face_image", "image_1") if name in images), None)
    if not any(native[name] == "IMAGE" for name in selected) and preferred and not any(native[name] == "VIDEO" for name in selected):
        selected.append(preferred)
    if task == "First & Last Frames to Video" and "last_frame" in native and "last_frame" in supported and "last_frame" not in selected:
        selected.append("last_frame")
    if entry.get("model") == "image-inpaint" and "mask" in native and "mask" not in selected:
        selected.append("mask")  # The alternative boxs JSON is not the default painted-mask recipe.
    return [(name, native[name], bindings.get(name, {})) for name in dict.fromkeys(selected)]


def native_workflow(entry, node_type, display_name, node_id, note, metadata, sources):
    values, inputs = node_fields(node_type)
    outputs = [{"name": name, "type": kind, "links": None, "slot_index": index} for index, (name, kind) in enumerate(zip(node_type.RETURN_NAMES, node_type.RETURN_TYPES))]
    creative_kind = getattr(node_type, "CRUN_CREATIVE_KIND", None)
    graph_node = {"id": 1, "type": node_id, "pos": [440, 130], "size": [510, 700], "flags": {}, "order": 1, "mode": 0,
                  "inputs": inputs, "outputs": outputs, "properties": {"Node name for S&R": node_id}, "widgets_values": values, "title": display_name}
    nodes, links = [graph_node], []

    def link(source, source_slot, target, target_slot, kind):
        identifier = len(links) + 1
        nodes[source - 1]["outputs"][source_slot].setdefault("links", [])
        if nodes[source - 1]["outputs"][source_slot]["links"] is None:
            nodes[source - 1]["outputs"][source_slot]["links"] = []
        nodes[source - 1]["outputs"][source_slot]["links"].append(identifier)
        nodes[target - 1]["inputs"][target_slot]["link"] = identifier
        links.append([identifier, source, source_slot, target, target_slot, kind])

    def loader(kind, title, position):
        node_type = {"IMAGE": "LoadImage", "MASK": "LoadImage", "VIDEO": "LoadVideo", "AUDIO": "LoadAudio"}[kind]
        identifier = len(nodes) + 1
        ports = [("IMAGE", "IMAGE"), ("MASK", "MASK")] if kind in {"IMAGE", "MASK"} else [(kind, kind)]
        nodes.append({"id": identifier, "type": node_type, "pos": [30, 130 + position * 350], "size": [340, 280], "flags": {}, "order": 0, "mode": 0,
                      "inputs": [], "outputs": [{"name": name, "type": port, "links": None, "slot_index": i} for i, (name, port) in enumerate(ports)],
                      "properties": {"Node name for S&R": node_type}, "widgets_values": ["", "image"] if kind in {"IMAGE", "MASK"} else [""], "title": title})
        if kind == "MASK":
            mask_id = len(nodes) + 1
            nodes.append({"id": mask_id, "type": "ImageToMask", "pos": [40, 420 + position * 350], "size": [310, 90], "flags": {}, "order": 0, "mode": 0,
                          "inputs": [{"name": "image", "type": "IMAGE", "link": None}],
                          "outputs": [{"name": "MASK", "type": "MASK", "links": None, "slot_index": 0}],
                          "properties": {"Node name for S&R": "ImageToMask"}, "widgets_values": ["red"], "title": "Black/white edit mask"})
            link(identifier, 0, mask_id, 0, "IMAGE")
            return mask_id
        return identifier

    source_index = 0
    schema_fields = _input_schema(entry).get("properties", {})
    for name, kind, binding in sources:
        count = schema_fields.get(binding.get("wire_name", name), {}).get("minItems", 1) if kind == "IMAGE" and binding.get("many") else 1
        count = max(1, min(count, 8)) if isinstance(count, int) and not isinstance(count, bool) else 1
        source = None
        for reference in range(count):
            current = loader(kind, "Choose " + name.replace("_", " ") + (f" {reference + 1}" if count > 1 else ""), source_index)
            source_index += 1
            if source is None:
                source = current
            else:
                batch_id = len(nodes) + 1
                nodes.append({"id": batch_id, "type": "ImageBatch", "pos": [50, 100 + source_index * 350], "size": [300, 100], "flags": {}, "order": 0, "mode": 0,
                              "inputs": [{"name": "image1", "type": "IMAGE", "link": None}, {"name": "image2", "type": "IMAGE", "link": None}],
                              "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": None, "slot_index": 0}], "properties": {"Node name for S&R": "ImageBatch"}, "widgets_values": []})
                link(source, 0, batch_id, 0, "IMAGE")
                link(current, 0, batch_id, 1, "IMAGE")
                source = batch_id
        target_slot = next(index for index, port in enumerate(inputs) if port["name"] == name)
        link(source, 0, 1, target_slot, kind)
    preview_type = None
    if creative_kind:
        preview_type = {"image": "PreviewImage", "video": "SaveVideo", "audio": "PreviewAudio"}[creative_kind]
        media = creative_kind.upper()
        identifier = len(nodes) + 1
        nodes.append({"id": identifier, "type": preview_type, "pos": [1000, 130], "size": [480, 380], "flags": {}, "order": 2, "mode": 0,
                      "inputs": [{"name": {"image": "images", "video": "video", "audio": "audio"}[creative_kind], "type": media, "link": None}],
                      "outputs": [] if creative_kind == "image" else [{"name": creative_kind, "type": media, "links": None, "slot_index": 0}],
                      "properties": {"Node name for S&R": preview_type}, "widgets_values": ["video/CRUN", "auto", "auto"] if creative_kind == "video" else []})
        link(1, 0, identifier, 0, media)
    note_id = len(nodes) + 1
    nodes.append({"id": note_id, "type": "Note", "pos": [30, 60], "size": [340, 620], "flags": {"collapsed": True}, "order": 3, "mode": 0,
                  "properties": {}, "widgets_values": [note], "title": "Workflow guide — expand for instructions", "color": "#263341", "bgcolor": "#17232d"})
    metadata.update({"default_mode": "prepare", "native_inputs_connected": [name for name, _, _ in sources], "preview_node": preview_type,
                     "result_node": None, "node_type": node_id, "workflow_type": "creative_native_media" if creative_kind else "advanced_api_preparation", "generation_tested": False})
    return {"last_node_id": note_id, "last_link_id": len(links), "nodes": nodes, "links": links, "groups": [], "config": {},
            "extra": {"ds": {"scale": 0.8, "offset": [20, 20]}, "crun_next": metadata}, "version": 0.4}


def workflow_for(entry: dict, node_type: type, display_name: str) -> dict:
    creative_kind = getattr(node_type, "CRUN_CREATIVE_KIND", None)
    node_id = media_node_id(entry) if creative_kind else node_id_for(entry)
    note = (
        "CRUN NEXT — NATIVE MEDIA WORKFLOW\n\n"
        "START: Action=prepare, optional cap=0, Take=0. No upload, provider request or generation occurs in Prepare.\n"
        "Choose local media in the connected Load nodes. Native inputs keep their documented roles; URL/JSON fallbacks remain Advanced.\n"
        "Estimate uploads references and displays the current quote. Generate submits once, waits and returns native media directly to Preview/Save.\n"
        "The same settings and Take resume/reuse their existing task. Increase Take only to intentionally request a new paid generation.\n"
        "After a timeout, keep the task ID and resume it; do not create a replacement automatically.\n"
        "The optional positive cap stays under Advanced; 0 disables it. Actual credits and remaining balance are separate from estimates.\n"
        "Enter your API key only in Settings > CRUN Next, never in this graph.\n\n"
        f"Option: {entry.get('title') or entry.get('model')}\nModel: {entry.get('model')}\n"
        f"Documentation: {entry.get('documentation_url', 'https://docs.crun.ai/')}\n"
    )
    if entry.get("effect_template_id"):
        note += "\nThis Effect has a fixed identifier. Preserve image order; inspect provider instructions when image counts are unknown.\n"
    if entry.get("model") == "image-inpaint":
        note += "\nINPAINT MASK: choose a black/white mask with the same dimensions as the source image. ImageToMask uses its red channel; white marks the edit region. The optional boxs JSON is an alternative to this painted-mask workflow.\n"
    if not creative_kind:
        note = "ADVANCED API PREPARATION ONLY — NO FINISHED MEDIA ADAPTER\n\n" + note
        note += "\nThis recipe is an Advanced API draft, not a complete creative integration. LLM/3D or a dedicated unsupported protocol may require raw structured inputs. Keep Prepare; a listed API is not proof of live execution.\n"
        if entry.get("kind") == "effect":
            note += "\nThe provider has not established this Effect's output media format. It deliberately has no IMAGE/VIDEO preview contract until that result type is verified.\n"
    sources = source_requirements(entry, node_type)
    return native_workflow(entry, node_type, display_name, node_id, note, {"entry_id": entry["id"], "model": entry.get("model"), "output_kind": creative_kind}, sources)


def build_templates(output: Path | None = None, entries: list[dict] | None = None) -> dict:
    write_bundled_manifest = output is None
    output = output or ROOT / "example_workflows"
    entries = bundled_entries() if entries is None else entries
    classes, names = generated_mappings(entries)
    creative_classes, creative_names = creative_mappings(entries)
    classes.update(creative_classes)
    names.update(creative_names)
    manifest_entries = []
    catalog_record_coverage = []
    for entry in entries:
        node_id = media_node_id(entry) if output_kind(entry) else node_id_for(entry)
        group = "Effects" if entry.get("kind") == "effect" else "AI-Tools" if entry.get("kind") == "tool" else "Models"
        prefix = "Effect" if group == "Effects" else "Tool" if group == "AI-Tools" else "Model"
        output.mkdir(parents=True, exist_ok=True)
        filename = prefix + "-" + _filename(entry)
        path = output / filename
        workflow = workflow_for(entry, classes[node_id], names[node_id])
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        manifest_entries.append({"entry_id": entry["id"], "node_type": node_id, "model": entry["model"], "title": entry.get("title", entry["model"]), "group": group, "path": path.relative_to(output).as_posix(), "default_mode": "prepare", "generation_tested": False, "workflow_type": workflow["extra"]["crun_next"]["workflow_type"], "output_kind": output_kind(entry), "preview_node": workflow["extra"]["crun_next"]["preview_node"]})
        if entry.get("effect_template_id"):
            raw = entry.get("effect_metadata", {}).get("raw", {})
            records = raw.get("catalog_variants") or [raw]
            for record in records:
                canonical = json.dumps(record, sort_keys=True, ensure_ascii=False)
                catalog_record_coverage.append({
                    "provider": entry["provider"], "template_id": entry["effect_template_id"],
                    "category": str(record.get("category_name") or record.get("category") or record.get("TemplateType") or ""),
                    "record_hash": hashlib.sha256(canonical.encode()).hexdigest()[:16],
                    "path": path.relative_to(output).as_posix(),
                })
    manifest = {
        "schema_version": 1, "total_templates": len(manifest_entries), "groups": dict(Counter(item["group"] for item in manifest_entries)),
        "all_default_prepare": True, "contains_credentials": False, "entries": manifest_entries,
        "effect_catalog_records": len(catalog_record_coverage),
        "unique_effect_templates": sum(bool(entry.get("effect_template_id")) for entry in entries),
        "catalog_record_coverage": catalog_record_coverage,
    }
    output.mkdir(parents=True, exist_ok=True)
    if write_bundled_manifest:
        manifest_path = ROOT / "data" / "workflow_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    manifest = build_templates()
    print(json.dumps({key: value for key, value in manifest.items() if key not in {"entries", "catalog_record_coverage"}}))
