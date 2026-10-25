"""Setup utilities and offline registration of schema-aware CRUN nodes."""

from __future__ import annotations

import json
import math

from .crun.client import CRUNClient
from .crun.effects import build_effect_plan, normalize_catalog
from .crun.settings import public_status
from .crun.tools import list_tools


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _parse(value, expected):
    if not isinstance(value, str) or len(value) > 32768:
        raise ValueError("JSON input must be text below 32 KiB.")
    parsed = json.loads(value)
    if not isinstance(parsed, expected):
        raise ValueError(f"Expected a JSON {expected.__name__}.")
    return parsed


class CRUNConnectionStatus:
    CATEGORY = "CRUN Next/Setup"
    FUNCTION = "check"
    RETURN_TYPES = ("BOOLEAN", "STRING")
    RETURN_NAMES = ("configured", "status_json")
    DESCRIPTION = "Check local configuration only. Enter your key in Settings → CRUN Next, not in a node."
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def check(self):
        data = public_status()
        return {"ui": {"text": [_json(data)]}, "result": (data["configured"], _json(data))}


class CRUNCredits(CRUNConnectionStatus):
    RETURN_TYPES = ("FLOAT", "STRING")
    RETURN_NAMES = ("balance", "receipt_json")
    DESCRIPTION = "Explicitly fetch current CRUN balance. Read-only; no generation."

    def check(self):
        balance = CRUNClient().get_balance()
        data = {"provider": "crun", "balance": balance, "scope": "account", "source": "live"}
        print(f"[CRUN Next] Account balance: {balance:g} CRUN credits (live check)")
        return {"ui": {"text": [_json(data)]}, "result": (balance, _json(data))}


class CRUNEffectsCatalog(CRUNConnectionStatus):
    CATEGORY = "CRUN Next/Effects"
    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("catalog_json", "template_count")
    DESCRIPTION = "Fetch the selected provider's effect-template catalog. No effects are executed."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"provider": (["kling", "bytedance", "vidu"],)}}

    def check(self, provider):
        cards = normalize_catalog(provider, CRUNClient().list_effects(provider))
        return {"ui": {"text": [f"{len(cards)} {provider} effect templates. Browse them in CRUN Next Studio."]}, "result": (_json(cards), len(cards))}


class CRUNEstimateCredits(CRUNConnectionStatus):
    CATEGORY = "CRUN Next/Utility"
    RETURN_TYPES = ("FLOAT", "BOOLEAN", "STRING")
    RETURN_NAMES = ("credits", "provisional", "estimate_json")
    DESCRIPTION = "Estimate cost using the CRUN estimate endpoint. Does not create or run a task. Use documented CRUN model IDs."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("STRING", {"default": ""}), "input_json": ("STRING", {"default": "{}", "multiline": True})}}

    def check(self, model, input_json):
        data = CRUNClient().estimate_credits(model, _parse(input_json, dict))
        credits = float(data["credits"])
        if not math.isfinite(credits) or credits < 0:
            raise ValueError("CRUN returned an invalid credit estimate.")
        provisional = bool(data.get("estimated", True))
        return {"ui": {"text": [_json(data)]}, "result": (credits, provisional, _json(data))}


class CRUNInspectTask(CRUNConnectionStatus):
    CATEGORY = "CRUN Next/Utility"
    RETURN_TYPES = ("STRING", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = ("status", "credits", "credit_state", "task_json")
    DESCRIPTION = "Inspect an existing CRUN media task. Credits are reserved while pending/running and actual after success/failed. Does not submit a task."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"task_id": ("STRING", {"default": ""})}}

    def check(self, task_id):
        data = CRUNClient().get_task(task_id)
        status = str(data.get("status", "unknown"))
        amount = data.get("credits")
        state = "actual" if status in {"success", "failed"} else "reserved" if status in {"pending", "running"} else "unknown"
        if amount is None:
            credits, state = -1.0, "unavailable"
        else:
            if isinstance(amount, bool):
                raise ValueError("CRUN returned invalid task credits.")
            credits = float(amount)
            if not math.isfinite(credits) or credits < 0:
                raise ValueError("CRUN returned invalid task credits.")
        print(f"[CRUN Next] Task status: {status}; {state} credits: {credits:g}")
        return {"ui": {"text": [_json(data)]}, "result": (status, credits, state, _json(data))}


class CRUNPrepareEffectPlan:
    CATEGORY = "CRUN Next/Effects"
    FUNCTION = "prepare"
    RETURN_TYPES = ("CRUN_EFFECT_PLAN", "STRING")
    RETURN_NAMES = ("draft_plan", "plan_json")
    DESCRIPTION = "Prepare a draft effect payload offline. Does NOT validate entitlement, upload images, estimate costs or execute generation."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"provider": (["kling", "bytedance", "vidu"],), "template_id": ("STRING", {"default": ""}), "image_urls_json": ("STRING", {"default": "[]", "multiline": True}), "options_json": ("STRING", {"default": "{}", "multiline": True})}}

    def prepare(self, provider, template_id, image_urls_json, options_json):
        plan = build_effect_plan(provider, template_id, _parse(image_urls_json, list), _parse(options_json, dict))
        return (plan, _json(plan))


class CRUNToolsCatalog(CRUNConnectionStatus):
    CATEGORY = "CRUN Next/AI Tools"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("tools_json",)
    DESCRIPTION = "List catalog-backed CRUN AI Tools and documentation. Individual Tools nodes are in the Nodes menu, defaulting to offline preparation."

    def check(self):
        data = list_tools()
        return {"ui": {"text": [f"{len(data)} catalog-backed AI Tools. Find individual options under CRUN Next / AI Tools; workflows start in prepare mode."]}, "result": (_json(data),)}


NODE_CLASS_MAPPINGS = {
    "CRUN_Next_Connection_Status": CRUNConnectionStatus,
    "CRUN_Next_Credits": CRUNCredits,
    "CRUN_Next_Effects_Catalog": CRUNEffectsCatalog,
    "CRUN_Next_Estimate_Credits": CRUNEstimateCredits,
    "CRUN_Next_Inspect_Task": CRUNInspectTask,
    "CRUN_Next_Prepare_Effect_Plan": CRUNPrepareEffectPlan,
    "CRUN_Next_AI_Tools_Catalog": CRUNToolsCatalog,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CRUN_Next_Connection_Status": "CRUN • Connection Status",
    "CRUN_Next_Credits": "CRUN • Credits",
    "CRUN_Next_Effects_Catalog": "CRUN • Effects Catalog",
    "CRUN_Next_Estimate_Credits": "CRUN • Estimate Credits (No Generation)",
    "CRUN_Next_Inspect_Task": "CRUN • Inspect Existing Task",
    "CRUN_Next_Prepare_Effect_Plan": "CRUN • Prepare Effect Plan (Draft)",
    "CRUN_Next_AI_Tools_Catalog": "CRUN • AI Tools Catalog",
}

# Bundled/cached metadata only. Node registration must never contact CRUN.
from .generated_nodes import generated_mappings
_generated_classes, _generated_names = generated_mappings()
NODE_CLASS_MAPPINGS.update(_generated_classes)
NODE_DISPLAY_NAME_MAPPINGS.update(_generated_names)

from .family_nodes import family_node_mappings
_family_classes, _family_names = family_node_mappings()
NODE_CLASS_MAPPINGS.update(_family_classes)
NODE_DISPLAY_NAME_MAPPINGS.update(_family_names)

from .result_nodes import NODE_CLASS_MAPPINGS as _result_classes, NODE_DISPLAY_NAME_MAPPINGS as _result_names
NODE_CLASS_MAPPINGS.update(_result_classes)
NODE_DISPLAY_NAME_MAPPINGS.update(_result_names)

# Keep stable catalog IDs for existing workflows while presenting family nodes
# in the normal creative categories. Effects and AI Tools remain direct entries.
for _class in _generated_classes.values():
    if _class.CRUN_ENTRY.get("kind") not in {"effect", "tool"}:
        _class.CATEGORY = _class.CATEGORY.replace("CRUN Next/", "CRUN Next/Advanced/Catalog/", 1)
