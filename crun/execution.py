"""Schema-aware payload preparation and an explicit, budgeted media task gate.

Import, preparation, catalog discovery and workflows' default mode cannot submit
a paid job. No file is uploaded by this module: media inputs are explicit URLs.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any

from .client import CRUNClient, CRUNError
from .settings import settings_path

_LOCK = threading.RLock()


def validate(value: Any, schema: dict, path: str = "input") -> list[str]:
    """Validate common JSON Schema controls; unresolved refs are not invented."""
    if not isinstance(schema, dict):
        return []
    errors = []
    if "$ref" in schema:
        return [f"{path}: unresolved definition; review the API documentation."]
    if value is None and schema.get("nullable") is True:
        return []
    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants:
        outcomes = [validate(value, variant, path) for variant in variants]
        matches = sum(not outcome for outcome in outcomes)
        if not matches or ("oneOf" in schema and matches != 1):
            errors.append(f"{path}: must match a documented input variant.")
    for subschema in schema.get("allOf", []):
        errors.extend(validate(value, subschema, path))
    kind = schema.get("type")
    if isinstance(kind, list):
        if not any(not validate(value, {**schema, "type": choice}, path) for choice in kind):
            errors.append(f"{path}: incorrect type.")
        return errors
    type_checks = {
        "string": lambda: isinstance(value, str),
        "boolean": lambda: isinstance(value, bool),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        "object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
        "null": lambda: value is None,
    }
    if kind in type_checks and not type_checks[kind]():
        return errors + [f"{path}: expected {kind}."]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: choose a documented option.")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: does not match the required constant.")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value or value[key] is None or value[key] == "":
                errors.append(f"{path}.{key}: required.")
        for key, item in value.items():
            if key in properties:
                errors.extend(validate(item, properties[key], f"{path}.{key}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            errors.append(f"{path}: incorrect number of items.")
        items = schema.get("items", {})
        for index, item in enumerate(value):
            errors.extend(validate(item, items, f"{path}[{index}]"))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            errors.append(f"{path}: incorrect text length.")
        if isinstance(schema.get("pattern"), str):
            try:
                if re.search(schema["pattern"], value) is None:
                    errors.append(f"{path}: does not match the documented text format.")
            except re.error:
                errors.append(f"{path}: documented text format could not be validated.")
        if schema.get("format") in {"uri", "url"}:
            from .effects import _https_url
            if not _https_url(value):
                errors.append(f"{path}: a public HTTPS URL is required.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            errors.append(f"{path}: outside the documented range.")
    return errors


def build_payload(entry: dict, inputs: dict) -> tuple[dict, list[str]]:
    if not isinstance(inputs, dict):
        raise ValueError("Model inputs must be an object.")
    schema = entry.get("request_schema") or entry.get("input_schema") or entry.get("inputs") or {}
    properties = schema.get("properties", {})
    template = deepcopy(entry.get("payload_template") or {})
    model = entry.get("model")
    if "input" in properties:
        template["input"] = deepcopy(inputs)
        if model:
            template["model"] = model
    else:
        template.update(deepcopy(inputs))
        if model and ("model" in properties or "model" in template):
            template["model"] = model
    for key, field in properties.items():
        if key not in template:
            if "const" in field:
                template[key] = deepcopy(field["const"])
            elif "default" in field:
                template[key] = deepcopy(field["default"])
    # No stale callback/test destination from a provider example.
    template.pop("callback_url", None)
    template.pop("callBackUrl", None)
    errors = validate(template, schema, "request")
    # Body examples are not authority for hidden model selectors.
    if "input" in properties and not model:
        errors.append("request.model: exact CRUN model ID is unavailable.")
    return template, errors


def _record(record: dict) -> None:
    """Keep recoverable IDs, not prompts/reference URLs or credentials."""
    with _LOCK:
        path = settings_path().parent / "tasks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        current = []
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(current, list):
                    raise ValueError("Invalid task journal format")
            except (OSError, ValueError):
                raise CRUNError("Task journal cannot be read; repair it before submitting another paid job.") from None
        current.append(record)
        descriptor, temp = tempfile.mkstemp(dir=path.parent, prefix=".tasks-", suffix=".tmp")
        try:
            os.chmod(temp, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(current[-2000:], stream, ensure_ascii=False)
            os.replace(temp, path)
        finally:
            Path(temp).unlink(missing_ok=True)


def run_entry(entry: dict, inputs: dict, mode: str, allow_paid_generation: bool = False, max_credits: float = 0) -> dict:
    if mode not in {"prepare", "estimate", "generate"}:
        raise ValueError("Select prepare, estimate or generate.")
    payload, errors = build_payload(entry, inputs)
    result = {"mode": mode, "entry_id": entry.get("id"), "model": entry.get("model"), "payload": payload,
              "task_id": "", "credits": -1.0, "credit_state": "unavailable", "status": "draft", "errors": errors,
              "warnings": ["Native file upload is not implemented here. Supply valid public media URLs."]}
    if mode == "prepare":
        return result
    if errors:
        raise ValueError("Invalid model input: " + "; ".join(errors[:12]))
    supported = entry.get("method", "POST").upper() == "POST" and entry.get("endpoint") == "/api/v1/client/job/CreateTask" and isinstance(payload.get("input"), dict) and isinstance(payload.get("model"), str)
    if not supported or entry.get("generation_supported") is False:
        raise ValueError("This operation has a dedicated protocol. It is available for preparation, not execution in this release.")
    if mode == "generate":
        if allow_paid_generation is not True:
            raise ValueError("Paid generation is not armed. Enable it explicitly after reviewing the inputs.")
        if isinstance(max_credits, bool) or not isinstance(max_credits, (int, float)) or not math.isfinite(max_credits) or max_credits <= 0:
            raise ValueError("Set a positive estimated-credit ceiling before generating.")
    client = CRUNClient()
    quote = client.estimate_credits(payload["model"], payload["input"])
    result.update(credits=quote["credits"], credit_state="estimate", status="estimated", provisional=quote["estimated"])
    if mode == "estimate":
        return result
    if quote["credits"] > max_credits:
        raise ValueError("The current estimate exceeds your credit ceiling. No task was submitted.")
    result["warnings"].append("The ceiling checks the estimate, not a provider-enforced final spending cap.")
    if client.get_balance() < quote["credits"]:
        raise ValueError("Insufficient CRUN balance for the current estimate. No task was submitted.")
    # Journal a preflight marker before submission; no credentials or input media.
    marker = {"entry_id": entry.get("id"), "model": payload["model"], "created_at": int(time.time()), "status": "submitting"}
    _record(marker)
    task_id = client.create_task(payload["model"], payload["input"])
    receipt = {**marker, "status": "submitted", "task_id": task_id, "quoted_credits": quote["credits"]}
    try:
        _record(receipt)
    except Exception:
        # Provider accepted the job: retain the ID in the node's normal output.
        result["warnings"].append("Task accepted, but local journal save failed. Keep the task ID and do not resubmit.")
    result.update(task_id=task_id, status="submitted", credit_state="estimate")
    print(f"[CRUN Next] Task submitted once: {task_id}; estimated credits: {quote['credits']:g}. Inspect the same task for actual cost.")
    return result
