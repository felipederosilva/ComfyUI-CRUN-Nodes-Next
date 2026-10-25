"""Offline, schema-aware Comfy nodes for every bundled CRUN option.

Definitions are produced from packaged metadata only. Importing this module,
opening the Nodes menu, or creating a workflow never contacts CRUN.
"""

from __future__ import annotations

from copy import deepcopy
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

if __package__:
    from .crun.effects import normalize_catalog
    from .crun.preflight import validate_node_inputs
else:
    from crun.effects import normalize_catalog
    from crun.preflight import validate_node_inputs


ROOT = Path(__file__).resolve().parent
EFFECTS_PATH = ROOT / "data" / "effects.json"
MODES = ["prepare", "estimate", "generate"]
CONTROL_MODE = "crun_mode"
CONTROL_ALLOW = "crun_allow_paid_generation"
CONTROL_BUDGET = "crun_max_credits"
CONTROL_UPLOAD = "crun_allow_upload"
_CONTROLS = {CONTROL_MODE, CONTROL_ALLOW, CONTROL_BUDGET, CONTROL_UPLOAD}


def run_entry(entry: dict, inputs: dict, mode: str, allow_paid_generation: bool = False, max_credits: float = 0, *, native_media=None, allow_upload=False) -> dict:
    """Lazy import keeps metadata inspection independent of execution clients."""
    if __package__:
        from .crun.execution import run_entry as execute
    else:
        from crun.execution import run_entry as execute
    return execute(entry, inputs, mode, allow_paid_generation=allow_paid_generation, max_credits=max_credits, native_media=native_media, allow_upload=allow_upload)


def _load_model_entries() -> list[dict]:
    if __package__:
        from .crun.catalog import load_catalog
    else:
        from crun.catalog import load_catalog
    snapshot = load_catalog()
    entries = snapshot.get("entries", []) if isinstance(snapshot, dict) else getattr(snapshot, "entries", [])
    return [deepcopy(entry) for entry in entries if isinstance(entry, dict)]


def _effect_entry(provider: str, card: dict, base_schema: dict | None = None) -> dict:
    count = card.get("required_images")
    image_schema: dict[str, Any] = {
        "type": "array", "items": {"type": "string", "format": "uri"},
        "description": "Ordered public HTTPS image references. Native Comfy media upload is not implemented yet.",
        "default": [],
    }
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        image_schema.update({"minItems": count, "maxItems": count})
    else:
        image_schema["minItems"] = 1
        image_schema["description"] += " Exact template image count is unknown; inspect the live template instructions."
    identifier_key, images_key = ("template", "images") if provider == "vidu" else ("template_id", "img_urls")
    properties = deepcopy((base_schema or {}).get("properties", {}))
    properties.update({
        identifier_key: {"type": "string", "const": str(card["id"]), "default": str(card["id"]), "description": "Fixed template selected by this node."},
        images_key: image_schema,
    })
    required = [identifier_key, images_key]
    if provider == "bytedance":
        prices = card.get("credits")
        resolutions = list(dict.fromkeys(item.get("resolution") for item in prices if isinstance(item, dict) and isinstance(item.get("resolution"), str) and item["resolution"])) if isinstance(prices, list) else []
        properties["resolution"] = {"type": "string", "description": "Resolution documented by this template's ConsumeItems."}
        if resolutions:
            properties["resolution"].update({"enum": resolutions, "default": resolutions[0]})
        required.append("resolution")
    elif provider == "vidu":
        properties["bgm"] = {"type": "boolean", "default": False, "description": "Background music; confirm support in this template's instructions."}
        ratios = card.get("raw", {}).get("aspect_ratio")
        if isinstance(ratios, list) and ratios and all(isinstance(ratio, str) for ratio in ratios):
            properties["aspect_ratio"] = {"type": "string", "enum": list(dict.fromkeys(ratios)), "default": ratios[0], "description": "Aspect ratios reported by this template's live catalog metadata."}
    identity = f"effect:{provider}:{card['id']}"
    schema = {"type": "object", "properties": properties, "required": required}
    return {
        "id": identity, "model": f"{provider}/template", "title": str(card.get("name") or card["id"]),
        "provider": {"kling": "Kling", "bytedance": "ByteDance", "vidu": "Vidu"}[provider],
        "kind": "effect", "group": "AI Effects", "endpoint": "/api/v1/client/job/CreateTask", "method": "POST",
        "auth": ["x-api-key"], "protocols": ["media_task"], "generation_supported": True,
        "inputs": schema, "input_schema": schema,
        "request_schema": {"type": "object", "properties": {"model": {"const": f"{provider}/template"}, "input": deepcopy(schema)}, "required": ["model", "input"]},
        "payload_template": {"model": f"{provider}/template", "input": {identifier_key: str(card["id"])}},
        "documentation_url": f"https://docs.crun.ai/templates/{provider}-template", "effect_template_id": str(card["id"]),
        "effect_metadata": deepcopy(card),
        "warnings": ["Exact image count is not machine-verified; inspect template instructions."] if count is None else [],
    }


def load_effect_entries(path: Path | None = None, base_entries: list[dict] | None = None) -> list[dict]:
    source = path or EFFECTS_PATH
    if not source.is_file():
        return []
    if source.stat().st_size > 30 * 1024 * 1024:
        raise ValueError("Bundled Effects metadata exceeds the supported size.")
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    base_by_model = {entry.get("model"): entry for entry in (base_entries or []) if isinstance(entry, dict)}
    result = []
    for provider, catalog in snapshot.get("providers", {}).items():
        if provider not in {"kling", "bytedance", "vidu"} or not isinstance(catalog, dict):
            continue
        cards = catalog.get("cards")
        if not isinstance(cards, list):
            cards = normalize_catalog(provider, {"templates": catalog.get("templates", [])})
        for card in cards:
            if isinstance(card, dict) and card.get("id"):
                base = base_by_model.get(f"{provider}/template")
                result.append(_effect_entry(provider, card, _input_schema(base) if base else None))
    return result


def all_entries() -> list[dict]:
    model_entries = _load_model_entries()
    entries = model_entries + load_effect_entries(base_entries=model_entries)
    by_id = {}
    for entry in entries:
        identifier = str(entry.get("id") or "")
        if identifier:
            by_id.setdefault(identifier, entry)
    return list(by_id.values())


def node_id_for(entry: dict) -> str:
    identity = str(entry.get("id") or entry.get("model") or "unknown")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(entry.get("model") or identity)).strip("_")[:56]
    if entry.get("effect_template_id"):
        slug = (slug + "_" + re.sub(r"[^A-Za-z0-9]+", "_", entry["effect_template_id"]))[:72]
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"CRUN_Next_{slug}_{digest}"


def _input_schema(entry: dict) -> dict:
    schema = deepcopy(entry.get("inputs") or entry.get("input_schema") or {})
    if not isinstance(schema, dict):
        schema = {}
    properties = schema.get("properties", {})
    if "model" in properties and isinstance(properties.get("input"), dict):
        schema = properties["input"]
    return _merge_object(schema)


def _merge_object(schema: dict) -> dict:
    result = deepcopy(schema)
    properties = dict(result.get("properties", {}))
    required = list(result.get("required", []))
    # A union remains provider-validated. Expose branch fields as optional rather
    # than incorrectly making all alternative required lists mandatory at once.
    for key in ("allOf", "oneOf", "anyOf"):
        for branch in schema.get(key, []) if isinstance(schema.get(key), list) else []:
            if not isinstance(branch, dict):
                continue
            merged = _merge_object(branch)
            for name, field in merged.get("properties", {}).items():
                properties.setdefault(name, field)
            if key == "allOf":
                required += merged.get("required", [])
    result["properties"] = properties
    result["required"] = list(dict.fromkeys(required))
    return result


def _field_type(field: dict) -> str:
    value = field.get("type")
    if isinstance(value, list):
        types = [item for item in value if item != "null"]
        value = types[0] if len(types) == 1 else None
    if value:
        return str(value)
    if isinstance(field.get("properties"), dict):
        return "object"
    for branch in field.get("anyOf", []) + field.get("oneOf", []):
        if isinstance(branch, dict) and branch.get("type") not in (None, "null"):
            return _field_type(branch)
    return "string"


def _default(field: dict, kind: str) -> Any:
    if "const" in field:
        return deepcopy(field["const"])
    if "default" in field and field["default"] is not None:
        return deepcopy(field["default"])
    enums = field.get("enum")
    if isinstance(enums, list) and enums:
        return deepcopy(next((item for item in enums if item is not None), enums[0]))
    if kind == "boolean":
        return False
    if kind in {"integer", "number"}:
        minimum = field.get("minimum", 0)
        minimum = minimum if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) else 0
        return int(minimum) if kind == "integer" else float(minimum)
    return [] if kind == "array" else {} if kind == "object" else ""


def _widget(field: dict) -> tuple:
    kind = _field_type(field)
    value = _default(field, kind)
    tooltip = str(field.get("description") or "")[:1200]
    enums = field.get("enum")
    if "const" in field:
        enums = [field["const"]]
    if isinstance(enums, list) and enums and all(isinstance(item, str) for item in enums):
        if value not in enums:
            value = enums[0]
        return (list(enums), {"default": value, "tooltip": tooltip})
    if isinstance(enums, list) and enums and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in enums):
        choices = [str(item) for item in enums]
        return (choices, {"default": str(value) if str(value) in choices else choices[0], "tooltip": tooltip})
    if kind == "boolean":
        return ("BOOLEAN", {"default": bool(value), "tooltip": tooltip})
    if kind in {"integer", "number"}:
        options = {"default": value, "tooltip": tooltip}
        for source, target in (("minimum", "min"), ("maximum", "max")):
            if isinstance(field.get(source), (int, float)) and not isinstance(field.get(source), bool):
                options[target] = field[source]
        if kind == "number":
            options["step"] = 0.01
        return ("INT" if kind == "integer" else "FLOAT", options)
    if kind in {"object", "array"}:
        return ("STRING", {"default": json.dumps(value, ensure_ascii=False), "multiline": True, "tooltip": (tooltip + " JSON input; no automatic media upload.").strip()})
    return ("STRING", {"default": str(value) if value is not None else "", "multiline": True, "tooltip": tooltip})


def field_definitions(entry: dict) -> list[tuple[str, str, dict, bool]]:
    schema = _input_schema(entry)
    fields = []
    native_sockets = {binding["socket"] for binding in image_bindings(entry)}
    for name, field in schema.get("properties", {}).items():
        if name in {"model", "callback_url", "stream"} or not isinstance(field, dict):
            continue
        widget_name = f"input_{name}" if name in _CONTROLS else name
        if widget_name in native_sockets:
            widget_name += "_urls"
        fields.append((widget_name, name, field, name in schema.get("required", [])))
    return fields


def _parse_field(value: Any, field: dict, name: str) -> Any:
    kind = _field_type(field)
    enums = field.get("enum")
    if isinstance(value, str) and isinstance(enums, list) and any(isinstance(item, (int, float)) and not isinstance(item, bool) for item in enums):
        value = next((item for item in enums if str(item) == value), value)
    if kind in {"array", "object"}:
        if isinstance(value, str):
            if len(value) > 1024 * 1024:
                raise ValueError(f"{name}: JSON input exceeds 1 MiB.")
            value = json.loads(value)
        expected = list if kind == "array" else dict
        if not isinstance(value, expected):
            raise ValueError(f"{name}: expected a JSON {kind}.")
    if "const" in field and value != field["const"]:
        raise ValueError(f"{name}: this node's template value is fixed.")
    return value


def image_bindings(entry: dict) -> list[dict]:
    """Only known image fields become sockets; video/audio URLs stay distinct."""
    properties = _input_schema(entry).get("properties", {})
    bindings = []
    model = str(entry.get("model") or "").lower()
    for wire, field in properties.items():
        # Some documented image arrays are alternatives to a single URL. Use
        # their actual array branch, without dropping the outer description.
        branches = field.get("oneOf", []) + field.get("anyOf", [])
        array_branch = next((branch for branch in branches if isinstance(branch, dict) and branch.get("type") == "array"), None)
        if array_branch is not None:
            field = {**field, **array_branch}
        kind = _field_type(field)
        if wire in {"img_urls", "image_urls", "images", "reference_images"} and kind == "array" and _field_type(field.get("items", {})) == "string":
            count = field.get("maxItems")
            description = str(field.get("description") or "").lower()
            if entry.get("effect_template_id") and isinstance(count, int) and 1 < count <= 8 and field.get("minItems") == count:
                for index in range(count):
                    bindings.append({"socket": f"image_{index + 1}", "wire_name": wire, "kind": "image", "many": False})
            elif "i2v" in model or "f2v" in model or entry.get("kind") == "video" and "r2v" not in model and "first frame" in description:
                bindings.append({"socket": "first_frame", "wire_name": wire, "kind": "image", "many": False})
                if isinstance(count, int) and count >= 2 and any(word in description for word in ("last frame", "last-frame", "end frame", "end-frame", "tail frame")):
                    bindings.append({"socket": "last_frame", "wire_name": wire, "kind": "image", "many": False})
            else:
                socket = "reference_images" if "r2v" in model or wire == "reference_images" or entry.get("effect_template_id") else "image"
                bindings.append({"socket": socket, "wire_name": wire, "kind": "image", "many": True})
        elif wire in {"image_url", "mask_url", "bg_image_url", "new_face"} and kind == "string":
            socket = {"image_url": "image", "mask_url": "mask", "bg_image_url": "background_image", "new_face": "face_image"}[wire]
            bindings.append({"socket": socket, "wire_name": wire, "kind": "mask" if wire == "mask_url" else "image", "many": False})
    # Never create two sockets with an ambiguous mapping.
    names = [binding["socket"] for binding in bindings]
    if len(names) != len(set(names)):
        raise ValueError("Ambiguous native image socket definition.")
    return bindings


def make_node(entry: dict) -> type:
    frozen = deepcopy(entry)
    fields = field_definitions(frozen)
    bindings = image_bindings(frozen)
    native_wires = {binding["wire_name"] for binding in bindings}
    group = str(frozen.get("group") or "Models").replace("/", " - ")
    provider = str(frozen.get("provider") or "CRUN").replace("/", " - ")
    category = f"CRUN Next/{group}/{provider}"
    description = (f"{frozen.get('title') or frozen.get('model')} — {frozen.get('model')}. "
                   "Prepare is offline. Estimate does not generate. Generate needs explicit permission and a positive budget. "
                   "Connect native IMAGE/MASK references where provided. Upload requires explicit permission; prepare stays offline. "
                   f"Documentation: {frozen.get('documentation_url', 'https://docs.crun.ai/')}")
    if not frozen.get("generation_supported", False):
        description += " This operation is prepare-only until its protocol is implemented."

    @classmethod
    def input_types(cls):
        required = {
            CONTROL_MODE: (MODES.copy(), {"default": "prepare"}),
            CONTROL_ALLOW: ("BOOLEAN", {"default": False, "tooltip": "Allow a paid generation only when mode=generate."}),
            CONTROL_BUDGET: ("FLOAT", {"default": 0.0, "min": 0.0, "step": 0.1, "tooltip": "Maximum CRUN credits for this task. Zero prevents generation."}),
        }
        optional = {}
        for widget_name, wire_name, schema, is_required in fields:
            if "const" in schema:
                continue  # Fixed template/model metadata is not an editable widget.
            (required if is_required else optional)[widget_name] = _widget(schema)
        if not fields:
            optional["advanced_input_json"] = ("STRING", {"default": "{}", "multiline": True, "tooltip": "No parameter schema was available. Consult documentation; prepare-only unless supported."})
        if bindings:
            optional[CONTROL_UPLOAD] = ("BOOLEAN", {"default": False, "tooltip": "Allow connected images/masks to be uploaded to CRUN when estimating or generating. Prepare never uploads."})
        for binding in bindings:
            optional[binding["socket"]] = ("MASK" if binding["kind"] == "mask" else "IMAGE", {"tooltip": f"Native {binding['kind']} reference for {binding['wire_name']}. Reference order is preserved. Use either native connections or the URL fallback for this field."})
        result = {"required": required}
        if optional:
            result["optional"] = optional
        return result

    def execute(self, crun_mode="prepare", crun_allow_paid_generation=False, crun_max_credits=0.0, crun_allow_upload=False, **kwargs):
        if crun_mode not in MODES:
            raise ValueError("Choose prepare, estimate or generate.")
        if not isinstance(crun_allow_paid_generation, bool):
            raise ValueError("Paid generation permission must be a boolean.")
        if not isinstance(crun_allow_upload, bool):
            raise ValueError("Upload permission must be a boolean.")
        if isinstance(crun_max_credits, bool) or not isinstance(crun_max_credits, (int, float)) or not math.isfinite(crun_max_credits) or crun_max_credits < 0:
            raise ValueError("Maximum credits must be a finite nonnegative number.")
        values = {}
        for widget_name, wire_name, field, required in fields:
            if "const" in field:
                if widget_name in kwargs and kwargs[widget_name] != field["const"]:
                    raise ValueError(f"{wire_name}: this node's template value is fixed.")
                values[wire_name] = deepcopy(field["const"])
                continue
            if widget_name not in kwargs:
                continue
            value = _parse_field(kwargs[widget_name], field, wire_name)
            if not required and value in ("", [], {}) and "default" not in field and "const" not in field:
                continue
            values[wire_name] = value
        if not fields and kwargs.get("advanced_input_json"):
            values = _parse_field(kwargs["advanced_input_json"], {"type": "object"}, "advanced_input_json")
        native_media = [{**binding, "value": kwargs[binding["socket"]]} for binding in bindings if kwargs.get(binding["socket"]) is not None]
        result = run_entry(frozen, values, crun_mode, allow_paid_generation=crun_allow_paid_generation, max_credits=float(crun_max_credits), native_media=native_media, allow_upload=crun_allow_upload)
        credits = result.get("credits")
        if isinstance(credits, bool) or not isinstance(credits, (int, float)) or not math.isfinite(credits):
            credits = -1.0
        task_id = result.get("task_id") or ""
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        return {"ui": {"text": [encoded]}, "result": (encoded, str(task_id), float(credits))}

    return type(node_id_for(frozen), (), {
        "CATEGORY": category, "FUNCTION": "execute", "RETURN_TYPES": ("STRING", "STRING", "FLOAT"),
        "RETURN_NAMES": ("result_json", "task_id", "credits"), "DESCRIPTION": description,
        "OUTPUT_NODE": True, "INPUT_TYPES": input_types, "execute": execute,
        "VALIDATE_INPUTS": classmethod(validate_node_inputs),
        "CRUN_ENTRY": frozen,
    })


def generated_mappings(entries: list[dict] | None = None) -> tuple[dict[str, type], dict[str, str]]:
    classes, names = {}, {}
    records = all_entries() if entries is None else entries
    title_counts = Counter(str(entry.get("title") or entry.get("model") or entry["id"]) for entry in records)
    for entry in records:
        node_id = node_id_for(entry)
        if node_id in classes:
            raise ValueError("Duplicate CRUN generated node identifier.")
        classes[node_id] = make_node(entry)
        title = str(entry.get("title") or entry.get("model") or node_id)
        if title_counts[title] > 1:
            selector = entry.get("effect_template_id") or entry.get("model") or entry.get("operation_id") or entry["id"]
            title += f" [{selector}]"
        names[node_id] = "CRUN • " + title
    return classes, names
