"""Build task-focused Studio workflow starters from the bundled model snapshot."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from family_nodes import family_catalog
from creative_nodes import creative_mappings, studio_node_id
from scripts.build_templates import native_workflow, source_requirements

NATIVE = {"IMAGE", "MASK", "VIDEO", "AUDIO"}


def bundled_families():
    snapshot = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8-sig"))
    return family_catalog(snapshot["entries"])


def _filename(family):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", family["family"] + "-" + family["task"]).strip("-")
    return "Studio-" + slug + ".json"


def workflow_for(family, node_type, display_name):
    definition = node_type.INPUT_TYPES()
    selected = definition["required"]["model"][1]["default"]
    profile = node_type.CRUN_PROFILES[selected]
    entry = next(item for item in family["entries"] if item["model"] == profile["model_id"])
    sources = source_requirements(entry, node_type, profile=profile, task=family["task"])
    node_id = studio_node_id(family)
    instructions = [
        "CRUN NEXT STUDIO — " + family["family"] + " — " + family["task"], "",
        "1. Select the model version. Only the selected model's documented controls apply.",
        "2. Choose the local references in the connected Load nodes and write the scene/edit prompt.",
        "3. Use Prepare to review missing-input validation locally. Estimate uploads needed references and requests a quote.",
        "4. Generate submits once and returns native " + family["kind"].upper() + " directly to Preview/Save after completion.",
        "", "START: Action=prepare; optional credit cap=0; Take=0.",
        "An existing positive optional cap is always respected. Set a cap under Advanced if desired.",
        "The same settings and Take resume/reuse their existing task, including after restart. Increase Take only for an intentional new paid result.",
        "After a timeout, keep the task ID and resume retrieval. Never automatically generate a replacement.",
        "Enter the API key only through Settings > CRUN Next, never in this graph.",
        "", "Default model: " + profile["model_id"], profile.get("capability_text", ""),
        "Documentation: " + str(profile.get("documentation_url") or "https://docs.crun.ai/"),
    ]
    connected = [name for name, _, _ in sources]
    if family["task"] == "Generate & Edit Image" and connected:
        instructions.append("This starter is connected for IMAGE EDITING. Disconnect the image for text-only generation when the selected model supports it.")
    if "reference_images" in connected:
        instructions.append("Reference images use an IMAGE batch. Preserve the documented reference order and count; add Image Batch nodes for additional references.")
    if "last_frame" in profile["inputs"] and "last_frame" not in connected:
        instructions.append("This starter uses a first frame. Connect an optional last frame only when the selected model supports it.")
    instructions += ["", "Prepare/Estimate deliberately block the media sink; no fake image/video is passed downstream.",
                     "This starter is not evidence of an authorized, completed paid provider round trip."]
    return native_workflow(entry, node_type, display_name, node_id, "\n".join(instructions),
                           {"family_id": family["id"], "model": profile["model_id"], "output_kind": family["kind"]}, sources)


def build_templates(output=None, families=None):
    root_output = output is None
    output = Path(output) if output is not None else ROOT / "example_workflows"
    records = bundled_families() if families is None else families
    entries = [entry for family in records for entry in family["entries"]]
    classes, names = creative_mappings(entries)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "family_templates": len(records), "model_variants": len(entries), "all_default_prepare": True, "contains_credentials": False, "entries": []}
    for record in records:
        path = output / _filename(record)
        workflow = workflow_for(record, classes[studio_node_id(record)], names[studio_node_id(record)])
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        manifest["entries"].append({"family_id": record["id"], "node_type": studio_node_id(record), "family": record["family"], "task": record["task"], "path": path.name, "models": [entry["model"] for entry in record["entries"]], "default_model": workflow["extra"]["crun_next"]["model"], "native_inputs_connected": workflow["extra"]["crun_next"]["native_inputs_connected"], "result_node": workflow["extra"]["crun_next"]["result_node"], "preview_node": workflow["extra"]["crun_next"]["preview_node"]})
    if root_output:
        (ROOT / "data" / "family_workflow_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    result = build_templates()
    print(json.dumps({key: value for key, value in result.items() if key != "entries"}))
