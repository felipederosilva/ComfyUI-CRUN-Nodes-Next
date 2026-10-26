"""Build task-focused Studio workflow starters from the bundled model snapshot."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from family_nodes import family_catalog, family_node_mappings

NATIVE = {"IMAGE", "MASK", "VIDEO", "AUDIO"}


def bundled_families():
    snapshot = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8-sig"))
    return family_catalog(snapshot["entries"])


def _filename(family):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", family["family"] + "-" + family["task"]).strip("-")
    return "Studio-" + slug + ".json"


def workflow_for(family, node_type, display_name):
    definition = node_type.INPUT_TYPES()
    widget_values, inputs, native_names = [], [], []
    for specs in definition.values():
        for name, spec in specs.items():
            kind = spec[0]
            options = spec[1] if len(spec) > 1 else {}
            if isinstance(kind, str) and kind in NATIVE:
                native_names.append(name)
                inputs.append({"name": name, "type": kind, "link": None})
            else:
                widget_values.append(options.get("default", kind[0] if isinstance(kind, list) else ""))
    selected = definition["required"]["model"][1]["default"]
    profile = node_type.CRUN_PROFILES[selected]
    family_node = {"id": 1, "type": family["id"], "pos": [420, 120], "size": [500, 620],
                   "flags": {}, "order": 1, "mode": 0, "inputs": inputs,
                   "outputs": [{"name": "result_json", "type": "STRING", "links": None, "slot_index": 0},
                               {"name": "task_id", "type": "STRING", "links": None, "slot_index": 1},
                               {"name": "credits", "type": "FLOAT", "links": None, "slot_index": 2}],
                   "properties": {"Node name for S&R": family["id"]},
                   "widgets_values": widget_values, "title": display_name}
    nodes, links = [family_node], []
    # Connect real IMAGE sockets, never pretend a file path is a provider URL.
    supported_images = [name for name, metadata in profile["inputs"].items() if metadata["type"] == "IMAGE"]
    candidates = [name for name in ("first_frame", "reference_images", "image", "face_image") if name in supported_images]
    connected = candidates[:1]
    if family["task"] == "First & Last Frames to Video" and "last_frame" in supported_images:
        connected.append("last_frame")
    if "background_image" in supported_images and not connected:
        connected.append("background_image")
    for position, socket in enumerate(connected):
        node_id, link_id = position + 2, position + 1
        slot = native_names.index(socket)
        family_node["inputs"][slot]["link"] = link_id
        nodes.append({"id": node_id, "type": "LoadImage", "pos": [30, 120 + position * 380], "size": [320, 300],
                      "flags": {}, "order": 0, "mode": 0, "inputs": [],
                      "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [link_id], "slot_index": 0}, {"name": "MASK", "type": "MASK", "links": None, "slot_index": 1}],
                      "properties": {"Node name for S&R": "LoadImage"},
                      "widgets_values": ["", "image"], "title": "Choose " + socket.replace("_", " ")})
        links.append([link_id, node_id, 0, 1, slot, "IMAGE"])
    result_id, preview_id = len(nodes) + 1, len(nodes) + 2
    task_link, media_link = len(links) + 1, len(links) + 2
    image_result = family["kind"] == "image"
    media_type = "IMAGE" if image_result else "VIDEO"
    result_type = "CRUN_Next_Get_Image_Result" if image_result else "CRUN_Next_Get_Video_Result"
    family_node["outputs"][1]["links"] = [task_link]
    nodes.append({"id": result_id, "type": result_type, "pos": [980, 120], "size": [350, 200],
                  "flags": {}, "order": 2, "mode": 0,
                  "inputs": [{"name": "task_id", "type": "STRING", "link": task_link}],
                  "outputs": [{"name": "image" if image_result else "video", "type": media_type, "links": [media_link], "slot_index": 0},
                              {"name": "url", "type": "STRING", "links": None, "slot_index": 1},
                              {"name": "actual_credits", "type": "FLOAT", "links": None, "slot_index": 2},
                              {"name": "task_id", "type": "STRING", "links": None, "slot_index": 3}],
                  "properties": {"Node name for S&R": result_type}, "widgets_values": [0, 1200, 3.0]})
    preview_type = "PreviewImage" if image_result else "SaveVideo"
    nodes.append({"id": preview_id, "type": preview_type, "pos": [980, 370], "size": [460, 340],
                  "flags": {}, "order": 3, "mode": 0,
                  "inputs": [{"name": "images" if image_result else "video", "type": media_type, "link": media_link}],
                  "outputs": [] if image_result else [{"name": "video", "type": "VIDEO", "links": None, "slot_index": 0}],
                  "properties": {"Node name for S&R": preview_type},
                  # Current Comfy SaveVideo schema: filename_prefix, format
                  # DynamicCombo(auto), nested codec DynamicCombo(auto).
                  "widgets_values": [] if image_result else ["video/CRUN", "auto", "auto"]})
    links.extend([[task_link, 1, 1, result_id, 0, "STRING"], [media_link, result_id, 0, preview_id, 0, media_type]])
    title = family["family"] + " — " + family["task"]
    instructions = ["CRUN NEXT STUDIO — " + title,
                    "", "1. Select a model version in the model dropdown. Only its supported controls are shown.",
                    "2. Write the scene or edit instruction in prompt. Review the selected model's requirements."]
    if connected:
        instructions.append("3. Choose your source image in each connected Load Image node. Connections are native Comfy IMAGE inputs, not URL text.")
        if "Generate & Edit Image" == family["task"]:
            instructions.append("This starter is connected for IMAGE EDITING. Disconnect the image input for text-only image generation, when supported by the selected model.")
        if "reference_images" in connected:
            instructions.append("The reference_images socket accepts an IMAGE batch. Add an Image Batch node for multiple references; preserve their intended order and selected-model limits.")
        if "last_frame" in supported_images and "last_frame" not in connected:
            instructions.append("The default shot uses a first frame. Connect a second Load Image to last_frame only when that model supports it.")
    instructions += ["", "START: Action=prepare. The optional credit cap is disabled at 0.",
                     "Preparation runs locally and reports validation errors without uploads or provider charges.",
                     "Estimate uploads connected references and requests a price. Generate uploads them and submits a paid task.",
                     "The last quote is visible on the node. An optional positive credit cap can be set under Advanced; 0 disables it.",
                     "Never put an API key in this graph. Configure it under Settings > CRUN Next.",
                     "", "Default model: " + profile["model_id"], profile.get("capability_text", ""),
                     "Documentation: " + str(profile.get("documentation_url") or "https://docs.crun.ai/"),
                     "", "AFTER SUBMISSION: Get Result polls this same task ID, saves the provider result locally and passes native media to Preview Image / Save Video.",
                     "Prepare/estimate returns no task ID, so result retrieval and preview are blocked without network activity.",
                     "A timeout preserves the task ID: rerun Get Result, never automatically regenerate.",
                     "This starter is not evidence of a completed or tested paid generation."]
    note_id = len(nodes) + 1
    nodes.append({"id": note_id, "type": "Note", "title": "Studio guide — expand for instructions", "pos": [30, 60], "size": [320, 580], "flags": {"collapsed": True}, "order": 4, "mode": 0,
                  "properties": {}, "widgets_values": ["\n".join(instructions)], "color": "#263341", "bgcolor": "#17232d"})
    return {"last_node_id": note_id, "last_link_id": len(links), "nodes": nodes, "links": links, "groups": [], "config": {},
            "extra": {"ds": {"scale": 0.8, "offset": [20, 20]}, "crun_next": {"family_id": family["id"], "model": profile["model_id"], "default_mode": "prepare", "native_inputs_connected": connected, "result_node": result_type, "preview_node": preview_type, "generation_tested": False}}, "version": 0.4}


def build_templates(output=None, families=None):
    root_output = output is None
    output = Path(output) if output is not None else ROOT / "example_workflows"
    records = bundled_families() if families is None else families
    entries = [entry for family in records for entry in family["entries"]]
    classes, names = family_node_mappings(entries)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "family_templates": len(records), "model_variants": len(entries), "all_default_prepare": True, "contains_credentials": False, "entries": []}
    for record in records:
        path = output / _filename(record)
        workflow = workflow_for(record, classes[record["id"]], names[record["id"]])
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        manifest["entries"].append({"family_id": record["id"], "family": record["family"], "task": record["task"], "path": path.name, "models": [entry["model"] for entry in record["entries"]], "default_model": workflow["extra"]["crun_next"]["model"], "native_inputs_connected": workflow["extra"]["crun_next"]["native_inputs_connected"], "result_node": workflow["extra"]["crun_next"]["result_node"], "preview_node": workflow["extra"]["crun_next"]["preview_node"]})
    if root_output:
        (ROOT / "data" / "family_workflow_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    result = build_templates()
    print(json.dumps({key: value for key, value in result.items() if key != "entries"}))
