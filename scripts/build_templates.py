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

from generated_nodes import generated_mappings, load_effect_entries, node_id_for


def bundled_entries() -> list[dict]:
    """Pin distributed templates to reviewed bundled data, never a user cache."""
    source = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    models = source["entries"]
    return models + load_effect_entries(base_entries=models)


def _filename(entry: dict) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "-", str(entry.get("title") or entry["model"])).strip("-").lower()[:58] or "option"
    digest = hashlib.sha256(str(entry["id"]).encode()).hexdigest()[:12]
    return f"{name}-{digest}.json"


def workflow_for(entry: dict, node_type: type, display_name: str) -> dict:
    node_id = node_id_for(entry)
    definition = node_type.INPUT_TYPES()
    widget_values = []
    inputs = []
    slot = 0
    for section in ("required", "optional"):
        for name, spec in definition.get(section, {}).items():
            type_value = spec[0]
            options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if isinstance(type_value, str) and type_value in {"IMAGE", "MASK", "VIDEO", "AUDIO"}:
                inputs.append({"name": name, "type": type_value, "link": None, "slot_index": slot})
                slot += 1
                continue
            if isinstance(type_value, list):
                default = options.get("default", type_value[0] if type_value else "")
            else:
                default = options.get("default", False if type_value == "BOOLEAN" else 0 if type_value in {"INT", "FLOAT"} else "")
            widget_values.append(default)
            inputs.append({"name": name, "type": "COMBO" if isinstance(type_value, list) else type_value, "widget": {"name": name}, "link": None, "slot_index": slot})
            slot += 1
    note = (
        "CRUN NEXT — SAFE START\n\n"
        "This workflow defaults to PREPARE: no API request, upload or charge.\n"
        "Enter your API key only through Settings > CRUN Next, never in a workflow.\n"
        "Connect Load Image to native IMAGE references, or use Advanced URL fallbacks. Arrays/objects use JSON.\n"
        "PREPARE stays local. ESTIMATE uploads connected references and requests a price. GENERATE uploads references and submits a paid task.\n"
        "The optional credit cap is under Advanced: 0 disables it; a positive cap is respected. Review the visible quote receipt.\n"
        "Do not share private media links when publishing this workflow.\n\n"
        f"Option: {entry.get('title') or entry['model']}\n"
        f"Model: {entry['model']}\n"
        f"Documentation: {entry.get('documentation_url', 'https://docs.crun.ai/')}\n"
    )
    if entry.get("effect_template_id"):
        note += "\nEffects: the fixed template identifier belongs to this node. Preserve reference order; confirm any unknown slot counts in the provider instructions.\n"
    if not entry.get("generation_supported", False):
        note += "\nThis operation's generation protocol is not enabled yet. PREPARE remains available; do not interpret this template as tested execution.\n"
    workflow = {
        "last_node_id": 2, "last_link_id": 0,
        "nodes": [
            {"id": 1, "type": node_id, "pos": [570, 120], "size": [500, max(340, 190 + len(widget_values) * 48)], "flags": {}, "order": 0, "mode": 0,
             "inputs": inputs,
             "outputs": [{"name": "result_json", "type": "STRING", "links": None, "slot_index": 0}, {"name": "task_id", "type": "STRING", "links": None, "slot_index": 1}, {"name": "credits", "type": "FLOAT", "links": None, "slot_index": 2}],
             "properties": {"Node name for S&R": node_id}, "widgets_values": widget_values, "title": display_name},
            {"id": 2, "type": "Note", "pos": [50, 120], "size": [460, 480], "flags": {}, "order": 1, "mode": 0,
             "properties": {}, "widgets_values": [note], "color": "#263341", "bgcolor": "#17232d"},
        ],
        "links": [], "groups": [], "config": {},
        "extra": {"ds": {"scale": 0.8, "offset": [30, 30]}, "crun_next": {"entry_id": entry["id"], "model": entry["model"], "default_mode": "prepare", "generation_tested": False}},
        "version": 0.4,
    }
    native = [item for item in inputs if item['type'] == 'IMAGE']
    schema = entry.get('inputs') or entry.get('input_schema') or {}
    minimum = (schema.get('properties', {}).get('img_urls') or schema.get('properties', {}).get('images') or {}).get('minItems', 0)
    for source_index, target in enumerate(native):
        if target['name'] in {'background_image', 'face_image'} or target['name'] == 'last_frame' and minimum < 2:
            continue
        identifier = max(node['id'] for node in workflow['nodes']) + 1
        link = len(workflow['links']) + 1
        target['link'] = link
        load = {'id':identifier,'type':'LoadImage','pos':[50,650 + source_index*340],'size':[390,300],'flags':{},'order':source_index+2,'mode':0,
                'inputs':[], 'outputs':[{'name':'IMAGE','type':'IMAGE','links':[link],'slot_index':0},{'name':'MASK','type':'MASK','links':None,'slot_index':1}],
                'properties':{'Node name for S&R':'LoadImage'},'widgets_values':['','image'],'title':'Choose ' + target['name'].replace('_',' ')}
        workflow['nodes'].append(load)
        workflow['links'].append([link,identifier,0,1,target['slot_index'],'IMAGE'])
    workflow['last_node_id'] = max(node['id'] for node in workflow['nodes'])
    workflow['last_link_id'] = len(workflow['links'])
    return workflow


def build_templates(output: Path | None = None, entries: list[dict] | None = None) -> dict:
    write_bundled_manifest = output is None
    output = output or ROOT / "example_workflows"
    entries = bundled_entries() if entries is None else entries
    classes, names = generated_mappings(entries)
    manifest_entries = []
    catalog_record_coverage = []
    for entry in entries:
        node_id = node_id_for(entry)
        group = "Effects" if entry.get("kind") == "effect" else "AI-Tools" if entry.get("kind") == "tool" else "Models"
        prefix = "Effect" if group == "Effects" else "Tool" if group == "AI-Tools" else "Model"
        output.mkdir(parents=True, exist_ok=True)
        filename = prefix + "-" + _filename(entry)
        path = output / filename
        workflow = workflow_for(entry, classes[node_id], names[node_id])
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        manifest_entries.append({"entry_id": entry["id"], "node_type": node_id, "model": entry["model"], "title": entry.get("title", entry["model"]), "group": group, "path": path.relative_to(output).as_posix(), "default_mode": "prepare", "generation_tested": False})
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
