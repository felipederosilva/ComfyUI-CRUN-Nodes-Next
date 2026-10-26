"""Native-media creative nodes. Legacy submit-only contracts remain stable."""
from __future__ import annotations

from copy import deepcopy

if __package__:
    from . import generated_nodes as generated, family_nodes as families
    from .crun.creative import run_creative
else:
    import generated_nodes as generated
    import family_nodes as families
    from crun.creative import run_creative


def output_kind(entry: dict) -> str | None:
    kind, model = entry.get("kind"), str(entry.get("model") or "")
    if not entry.get("generation_supported"):
        return None
    if kind in {"image", "video", "audio"}:
        return kind
    if kind == "music":
        return "audio"
    if kind == "tool":
        return "video" if model.startswith(("video-", "gif-", "sora-watermark")) else "image"
    if kind == "effect":
        reported = entry.get("effect_metadata", {}).get("raw", {}).get("output_type")
        if model == "vidu/template" and reported not in {"image", "video"}:
            return None  # Generic/missing type cannot promise native video.
        return "image" if reported == "image" else "video"
    return None


def media_node_id(entry: dict) -> str:
    return generated.node_id_for(entry).replace("CRUN_Next_", "CRUN_Next_Media_", 1)


def studio_node_id(family: dict) -> str:
    return family["id"].replace("CRUN_Next_Family_", "CRUN_Next_Studio_", 1)


def make_creative_node(base, kind: str, node_id: str, title: str, category: str):
    definition = deepcopy(base.INPUT_TYPES())
    motion_ids = {"kling/v2-6-motion-control", "kling/v3-motion-control"}
    model_ids = {base.CRUN_ENTRY.get("model")} if hasattr(base, "CRUN_ENTRY") else {entry["model"] for entry in base.CRUN_FAMILY["entries"]}
    quality_labels = {"Standard (720p)": "std", "Professional (1080p)": "pro"} if model_ids and model_ids <= motion_ids else {}
    if quality_labels:
        reverse = {wire: label for label, wire in quality_labels.items()}
        for section in definition.values():
            if "mode" in section:
                spec = section["mode"]
                section["mode"] = (list(quality_labels), {**spec[1], "default": reverse.get(spec[1].get("default"), "Standard (720p)"), "label": "Output quality"})
        profiles = definition.get("required", {}).get("model", (None, {}))[1].get("crun_profiles", {})
        for profile in profiles.values():
            if "mode" in profile.get("fields", {}):
                field = profile["fields"]["mode"]
                field["label"] = "Output quality"
                field["options"]["values"] = list(quality_labels)
                field["options"]["default"] = reverse.get(field["options"].get("default"), "Standard (720p)")
    for section in definition.values():
        if "seed" in section and len(section["seed"]) > 1:
            section["seed"][1]["control_after_generate"] = False
        for name, spec in section.items():
            if isinstance(spec[0], str) and spec[0] in {"IMAGE", "MASK", "VIDEO", "AUDIO"}:
                spec[1]["lazy"] = True
    native_names = {name for section in definition.values() for name, spec in section.items()
                    if isinstance(spec[0], str) and spec[0] in {"IMAGE", "MASK", "VIDEO", "AUDIO"}}
    optional = definition.setdefault("optional", {})
    optional.update({
        "take": ("INT", {"default": 0, "min": 0, "max": 2147483647, "label": "Take", "tooltip": "The same settings and Take reuse their existing task, including after restart. Increase Take only to intentionally create a new paid result."}),
        "resume_task_id": ("STRING", {"default": "", "label": "Resume existing task", "advanced": True, "tooltip": "Recover an existing task without uploading or submitting. In Estimate/Generate this overrides generation; Prepare stays offline."}),
        "result_index": ("INT", {"default": 0, "min": 0, "max": 99, "advanced": True}),
        "timeout_seconds": ("INT", {"default": 1200, "min": 0, "max": 7200, "advanced": True}),
        "poll_interval": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 30.0, "advanced": True}),
    })
    types = ("IMAGE", "MASK") if kind == "image" else (kind.upper(),)
    names = ("image", "mask") if kind == "image" else (kind,)

    def execute(self, take=0, resume_task_id="", result_index=0, timeout_seconds=1200, poll_interval=3.0, **kwargs):
        if quality_labels and kwargs.get("mode") in quality_labels:
            kwargs["mode"] = quality_labels[kwargs["mode"]]
        response = run_creative(base().execute, kwargs, kind, take=take, resume_task_id=resume_task_id,
                                result_index=result_index, timeout_seconds=timeout_seconds, poll_interval=poll_interval)
        return {"ui": response["ui"], "result": response["result"]}

    def check_lazy_status(self, crun_mode="prepare", resume_task_id="", **kwargs):
        if resume_task_id and crun_mode != "prepare":
            return []
        return [name for name in native_names if name in kwargs and kwargs[name] is None]

    attributes = {
        "CATEGORY": category, "FUNCTION": "execute", "OUTPUT_NODE": False,
        "RETURN_TYPES": types + ("STRING", "STRING", "FLOAT", "FLOAT", "FLOAT", "STRING"),
        "RETURN_NAMES": names + ("url", "task_id", "estimated_credits", "actual_credits", "credits_left", "result_json"),
        "INPUT_TYPES": classmethod(lambda cls: deepcopy(definition)), "execute": execute,
        "check_lazy_status": check_lazy_status,
        "VALIDATE_INPUTS": classmethod(generated.validate_node_inputs),
        "DESCRIPTION": title + ". Returns native " + kind.upper() + " after the task completes. Connect to Preview/Save. Prepare stays local; Estimate uploads references and quotes; Generate submits once and waits. The same Take resumes its existing task. Increase Take for a new generation.",
        "CRUN_CREATIVE_KIND": kind,
    }
    if hasattr(base, "CRUN_ENTRY"):
        attributes["CRUN_ENTRY"] = base.CRUN_ENTRY
    if hasattr(base, "CRUN_FAMILY"):
        attributes["CRUN_FAMILY"] = base.CRUN_FAMILY
        attributes["CRUN_PROFILES"] = definition["required"]["model"][1]["crun_profiles"]
    return type(node_id, (), attributes)


def creative_mappings(entries=None):
    entries = generated.all_entries() if entries is None else entries
    classes, names = {}, {}
    raw_classes, raw_names = generated.generated_mappings(entries)
    for entry in entries:
        kind = output_kind(entry)
        if kind is None:
            continue
        old = generated.node_id_for(entry)
        node_id = media_node_id(entry)
        category = raw_classes[old].CATEGORY
        # Individual image/video options remain available under Advanced; their
        # task-family Studio node is the primary creative entry.
        if entry.get("kind") in {"image", "video"}:
            category = category.replace("CRUN Next/", "CRUN Next/Advanced/Individual Models/", 1)
        classes[node_id] = make_creative_node(raw_classes[old], kind, node_id, raw_names[old], category)
        names[node_id] = raw_names[old]
    for family in families.family_catalog(entries):
        base = families.make_family_node(family)
        node_id = studio_node_id(family)
        title = "CRUN • " + family["family"] + " — " + family["task"]
        classes[node_id] = make_creative_node(base, family["kind"], node_id, title, base.CATEGORY)
        names[node_id] = title
    return classes, names
