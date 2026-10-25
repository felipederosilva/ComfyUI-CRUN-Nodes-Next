"""Task-focused CRUN model families with a version dropdown and exact schemas.

This layer groups compatible creative operations. It does not merge their wire
contracts: execution is delegated to the node for the selected exact model.
Import and model selection use local metadata only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import re
from typing import Any

if __package__:
    from . import generated_nodes as generated
else:
    import generated_nodes as generated


PROVIDER_DEFAULT = "Use provider default"
_CONTROLS = ("crun_mode", "crun_allow_upload", "crun_allow_paid_generation", "crun_max_credits")
_ORDER = ("prompt", "negative_prompt", "resolution", "aspect_ratio", "duration", "audio", "generate_audio", "seed", "num_outputs", "n")
_TECHNICAL = {"byteplus_fallback", "direct_byteplus", "input_compliance", "output_compliance", "content_moderation", "moderation", "disable_safety_filter", "callback_url"}


def _operation(entry: dict) -> str:
    model = str(entry.get("model") or "")
    title = str(entry.get("title") or "").lower()
    suffixes = (("-video-edit", "Video Editing"), ("-motion-control", "Motion Control"), ("-f2v", "First & Last Frames to Video"), ("-r2v", "Reference to Video"), ("/r2v", "Reference to Video"), ("-i2v", "Image to Video"), ("/i2v", "Image to Video"), ("-t2v", "Text to Video"), ("/t2v", "Text to Video"))
    for suffix, operation in suffixes:
        if model.endswith(suffix):
            return operation
    if "storyboard" in model:
        return "Storyboard Video"
    if "animate-move" in model:
        return "Animate Motion"
    if "animate-replace" in model:
        return "Replace Character"
    if "avatar" in model:
        return "Talking Avatar"
    if "lip-sync" in model:
        return "Lip Sync"
    if "regeneration" in model:
        return "Regenerate Video"
    if model == "bytedance/dreamactor":
        return "Motion Control"
    if "image to image" in title or model.endswith("/i2i"):
        return "Image Editing"
    if "text to image" in title or model.endswith("/t2i"):
        return "Text to Image"
    if "video" == entry.get("kind"):
        schema = generated._input_schema(entry)
        props = schema.get("properties", {})
        if any(key in schema.get("required", []) for key in ("video_urls", "video_url")):
            return "Video Editing"
        if "img_urls" in props:
            return "Image to Video" if "img_urls" in schema.get("required", []) else "Text / Image to Video"
        if "video_urls" in props or "video_url" in props:
            return "Video Editing"
        return "Video"
    return "Generate & Edit Image" if any(key in generated._input_schema(entry).get("properties", {}) for key in ("img_urls", "image_url")) else "Text to Image"


def family_identity(entry: dict) -> tuple[str, str, str] | None:
    """Return stable family key, human family name, task from known model IDs."""
    model = str(entry.get("model") or "")
    if entry.get("kind") not in {"image", "video"} or not model or model.endswith("/template"):
        return None
    task = _operation(entry)
    rules = (
        ("bytedance/seedance", "Seedance"), ("bytedance/seedream", "Seedream"),
        ("google/nano-banana", "Nano Banana"), ("openai/gpt-image", "GPT Image"),
        ("qwen-image-edit", "Qwen Image Edit"), ("qwen-image", "Qwen Image"),
        ("wan/", "Wan"), ("flux-kontext", "Flux Kontext"), ("flux-", "Flux"),
        ("openai/sora2", "Sora"), ("google/veo", "Veo"),
        ("kling/", "Kling"), ("vidu/", "Vidu"), ("pixverse/", "PixVerse"),
        ("minimax/hailuo", "Hailuo"), ("minimax/h3", "MiniMax H3"),
        ("happyhorse-", "HappyHorse"), ("agnes/", "Agnes"), ("runway/", "Runway"),
        ("google/gemini-omni", "Gemini Omni"), ("grok-imagine", "Grok Imagine"),
        ("google/image-4", "Imagen"), ("z-image", "Z Image"),
        ("bytedance/dreamactor", "DreamActor"), ("prunaai/", "Pruna P Video"),
    )
    family = next((name for prefix, name in rules if model.startswith(prefix)), None)
    if family is None:
        # A singleton stays specific instead of being grouped solely by provider.
        family = re.sub(r"\b(?:Crun|API)\b", "", str(entry.get("title") or model), flags=re.I).strip()
    if family in {"Seedream", "Nano Banana", "GPT Image", "Flux", "Flux Kontext"}:
        task = "Generate & Edit Image"
    elif family == "Qwen Image Edit":
        task = "Image Editing"
    elif family == "Qwen Image":
        task = "Generate & Edit Image" if "img_urls" in generated._input_schema(entry).get("properties", {}) else "Text to Image"
    if model.startswith("suno/"):
        return None  # Dedicated music helpers do not belong in video generation.
    key = re.sub(r"[^A-Za-z0-9]+", "_", f"{family}_{task}").strip("_")
    return key, family, task


def _variant_label(entry: dict, family: str, task: str) -> str:
    model = str(entry["model"])
    leaf = model.rsplit("/", 1)[-1]
    leaf = re.sub(r"-(?:i2v|t2v|r2v|f2v|video-edit|motion-control)$", "", leaf)
    for prefix in ("seedance", "seedream-", "nano-banana-", "gpt-image-", "qwen-image-edit-", "qwen-image-", "happyhorse-", "grok-imagine-video-", "grok-imagine-image-", "veo", "flux-kontext-", "flux-", "gemini-omni-"):
        if leaf.startswith(prefix):
            leaf = leaf[len(prefix):]
            break
    leaf = re.sub(r"(?<=\d)-(?=\d)", ".", leaf)
    leaf = leaf.replace("-", " ").strip()
    label = leaf.title() or family
    replacements = {"I2V": "Image to Video", "T2V": "Text to Video", "R2V": "Reference to Video", "H3": "H3", "Q1": "Q1", "Q2": "Q2", "Q3": "Q3", "Q4": "Q4", "O1": "O1", "V3": "V3"}
    for old, replacement in replacements.items():
        label = re.sub(rf"\b{old}\b", replacement, label, flags=re.I)
    return label


def _variant_sort(entry: dict) -> tuple:
    model = str(entry["model"])
    normalized = re.sub(r"-v2$", "", model)
    numbers = tuple(int(value) for value in re.findall(r"\d+", normalized))
    return tuple(-value for value in numbers[:4]), model.endswith("-v2"), len(model), model


def family_catalog(entries: list[dict] | None = None) -> list[dict]:
    grouped: dict[str, dict] = {}
    for entry in generated._load_model_entries() if entries is None else entries:
        identity = family_identity(entry)
        if not identity:
            continue
        key, family, task = identity
        record = grouped.setdefault(key, {"id": "CRUN_Next_Family_" + key, "family": family, "task": task, "kind": entry["kind"], "provider": entry.get("provider", "CRUN"), "entries": []})
        record["entries"].append(deepcopy(entry))
    for record in grouped.values():
        record["entries"].sort(key=_variant_sort)
    return sorted(grouped.values(), key=lambda item: (item["kind"], item["family"], item["task"]))


def _empty(value: Any) -> bool:
    # Never compare tensor values with strings/lists: their equality is tensor-valued.
    return value is None or isinstance(value, str) and not value or isinstance(value, (list, dict)) and not value


def _same(value: Any, expected: Any) -> bool:
    if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
        return False
    try:
        return bool(value == expected)
    except (ValueError, TypeError):
        return False


def _profile(entry: dict, definition: dict) -> dict:
    schema_fields = {widget: (wire, schema, required) for widget, wire, schema, required in generated.field_definitions(entry)}
    bindings = getattr(generated, "image_bindings", lambda value: [])(entry)
    binding_by_socket = {binding["socket"]: binding for binding in bindings}
    input_schema = generated._input_schema(entry)
    url_widgets = {binding["wire_name"] for binding in bindings}
    fields, inputs = {}, {}
    for section, specs in definition.items():
        for name, spec in specs.items():
            kind = spec[0]
            options = deepcopy(spec[1] if len(spec) > 1 else {})
            if isinstance(kind, str) and kind in {"IMAGE", "MASK", "VIDEO", "AUDIO"}:
                binding = binding_by_socket.get(name, {})
                wire = binding.get("wire_name", name)
                field = input_schema.get("properties", {}).get(wire, {})
                inputs[name] = {"type": kind, "required": wire in input_schema.get("required", []), "wire_name": wire, "reference_min": field.get("minItems"), "reference_max": field.get("maxItems"), "tooltip": options.get("tooltip", "")}
                continue
            if name in _CONTROLS:
                continue
            wire, schema, required = schema_fields.get(name, (name, {}, section == "required"))
            if isinstance(kind, list):
                options["values"] = kind
            if not required and schema.get("default", "missing") is None and isinstance(kind, list):
                options["values"] = [PROVIDER_DEFAULT] + list(options["values"])
                options["default"] = PROVIDER_DEFAULT
            fields[name] = {"visible": True, "required": required, "type": "COMBO" if isinstance(kind, list) else kind, "options": options, "wire_name": wire, "advanced": wire in url_widgets or wire in _TECHNICAL, "schema_type": generated._field_type(schema)}
    counts = []
    for binding in bindings:
        field = generated._input_schema(entry).get("properties", {}).get(binding["wire_name"], {})
        maximum = field.get("maxItems")
        minimum = field.get("minItems")
        if maximum is not None:
            counts.append(f"{binding['socket']}: up to {maximum} image(s)" if binding.get("many") else f"{binding['socket']}: one image")
        elif minimum is not None:
            counts.append(f"{binding['socket']}: check documented reference limits")
    capability = "; ".join(dict.fromkeys(counts)) or "No native image reference is used by this model."
    return {"model_id": entry["model"], "title": entry.get("title", entry["model"]), "documentation_url": entry.get("documentation_url"), "fields": fields, "inputs": inputs, "description": generated._input_schema(entry).get("description", ""), "capability_text": capability, "generation_supported": entry.get("generation_supported", False)}


def _union_spec(name: str, specs: list[tuple], profiles: dict[str, dict]) -> tuple:
    first = deepcopy(specs[0])
    schema_types = {profile["fields"][name].get("schema_type") for profile in profiles.values() if name in profile["fields"]}
    if schema_types and schema_types <= {"integer", "number"}:
        kind = "FLOAT" if "number" in schema_types else "INT"
        numeric_options = [profile["fields"][name]["options"] for profile in profiles.values() if name in profile["fields"]]
        options = deepcopy(numeric_options[0])
        for key in ("values", "min", "max"):
            options.pop(key, None)
        lows, highs = [], []
        for current in numeric_options:
            if isinstance(current.get("min"), (int, float)):
                lows.append(current["min"])
            if isinstance(current.get("max"), (int, float)):
                highs.append(current["max"])
            values = current.get("values", [])
            try:
                if values:
                    lows.append(min(float(value) for value in values))
                    highs.append(max(float(value) for value in values))
            except (ValueError, TypeError):
                pass
        if len(lows) == len(numeric_options):
            options["min"] = min(lows)
        if len(highs) == len(numeric_options):
            options["max"] = max(highs)
        value = options.get("default", 0)
        options["default"] = int(value) if kind == "INT" else float(value)
        return kind, options
    if all(isinstance(spec[0], list) for spec in specs):
        values = []
        for profile in profiles.values():
            for value in profile.get("fields", {}).get(name, {}).get("options", {}).get("values", []):
                if value not in values:
                    values.append(value)
        options = deepcopy(first[1] if len(first) > 1 else {})
        default = next(profile["fields"][name]["options"].get("default") for profile in profiles.values() if name in profile["fields"])
        options["default"] = default if default in values else values[0]
        return values, options
    return first


def make_family_node(family: dict) -> type:
    entries = deepcopy(family["entries"])
    raw_labels = [_variant_label(entry, family["family"], family["task"]) for entry in entries]
    counts = Counter(raw_labels)
    labels = [label + (f" [{entry['model']}]" if counts[label] > 1 else "") for label, entry in zip(raw_labels, entries)]
    selected_entries = dict(zip(labels, entries))
    definitions = {label: generated.make_node(entry).INPUT_TYPES() for label, entry in selected_entries.items()}
    profiles = {label: _profile(entry, definitions[label]) for label, entry in selected_entries.items()}
    spec_sets: dict[str, list[tuple]] = defaultdict(list)
    control_specs, native_specs = {}, {}
    for label, definition in definitions.items():
        for section, specs in definition.items():
            for name, spec in specs.items():
                if name in _CONTROLS:
                    control_specs.setdefault(name, deepcopy(spec))
                elif isinstance(spec[0], str) and spec[0] in {"IMAGE", "MASK", "VIDEO", "AUDIO"}:
                    native_specs.setdefault(name, deepcopy(spec))
                else:
                    spec_sets[name].append(spec)
    union = {name: _union_spec(name, specs, profiles) for name, specs in spec_sets.items()}
    priority = {name: index for index, name in enumerate(_ORDER)}
    ordered = sorted(union, key=lambda name: (any(profile["fields"].get(name, {}).get("advanced") for profile in profiles.values()), priority.get(name, len(priority)), name))
    initial_defaults = {name: deepcopy(spec[1].get("default")) for name, spec in union.items() if len(spec) > 1}

    @classmethod
    def input_types(cls):
        required = {"model": (labels.copy(), {"default": labels[0], "tooltip": "Choose a model version. Controls and reference requirements follow its documented schema.", "crun_profiles": deepcopy(profiles), "crun_family": family["family"], "crun_task": family["task"]})}
        for name in ordered:
            required[name] = deepcopy(union[name])
        for name in _CONTROLS:
            if name in control_specs:
                required[name] = deepcopy(control_specs[name])
        result = {"required": required}
        if native_specs:
            result["optional"] = deepcopy(native_specs)
        return result

    def execute(self, model=labels[0], **kwargs):
        if model not in selected_entries:
            raise ValueError("Choose a model version from this family's dropdown.")
        entry = selected_entries[model]
        definition = definitions[model]
        supported = set().union(*(specs.keys() for specs in definition.values()))
        allowed = set(union) | set(control_specs) | set(native_specs)
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError("Unknown input for this family: " + ", ".join(sorted(unknown)))
        chosen = {}
        for name, value in kwargs.items():
            if name not in supported:
                if name in native_specs and not _empty(value):
                    raise ValueError(f"{name}: disconnect this reference; it is not supported by the selected model.")
                if name in union and not _empty(value) and not _same(value, initial_defaults.get(name)):
                    raise ValueError(f"{name}: not supported by the selected model; clear it or select a compatible version.")
                continue
            field_profile = profiles[model]["fields"].get(name, {})
            if isinstance(value, str) and value == PROVIDER_DEFAULT and PROVIDER_DEFAULT in field_profile.get("options", {}).get("values", []):
                continue
            schema_type = field_profile.get("schema_type")
            if isinstance(value, str) and schema_type in {"integer", "number"}:
                try:
                    converted = float(value)
                    if schema_type == "integer" and not converted.is_integer():
                        raise ValueError()
                    value = int(converted) if schema_type == "integer" else converted
                except (TypeError, ValueError, OverflowError):
                    raise ValueError(f"{name}: enter a valid {schema_type}.") from None
            chosen[name] = value
        return generated.make_node(entry)().execute(**chosen)

    kind = "Image" if family["kind"] == "image" else "Video"
    title = f"CRUN • {family['family']} — {family['task']}"
    return type(family["id"], (), {
        "CATEGORY": f"CRUN Next/{kind}/{family['family']}",
        "FUNCTION": "execute", "RETURN_TYPES": ("STRING", "STRING", "FLOAT"),
        "RETURN_NAMES": ("result_json", "task_id", "credits"), "OUTPUT_NODE": True,
        "DESCRIPTION": title + ". Select a version; only that model's documented controls apply. Native image references are uploaded only with explicit permission. Preparation stays offline.",
        "INPUT_TYPES": input_types, "execute": execute, "CRUN_FAMILY": deepcopy(family),
        "CRUN_PROFILES": deepcopy(profiles),
    })


def family_node_mappings(entries: list[dict] | None = None) -> tuple[dict[str, type], dict[str, str]]:
    classes, names = {}, {}
    for family in family_catalog(entries):
        classes[family["id"]] = make_family_node(family)
        names[family["id"]] = f"CRUN • {family['family']} — {family['task']}"
    return classes, names
