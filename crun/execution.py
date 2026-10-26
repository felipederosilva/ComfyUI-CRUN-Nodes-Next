"""Schema-aware preparation and explicit media actions with an optional cap.

Import, preparation, catalog discovery and workflows' default mode cannot submit
a paid job. Estimate/Generate authorize their necessary reference uploads;
Generate explicitly authorizes one paid submission after balance checks.
"""
from __future__ import annotations

from copy import deepcopy
import json
import hashlib
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
from .preflight import configuration_errors

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


def _native_inputs(entry: dict, inputs: dict, native_media: list | None):
    """Encode and validate all references locally before any provider action."""
    if not native_media:
        return deepcopy(inputs), [], []
    from .media import image_batch_to_pngs, mask_batch_to_images
    schema = entry.get("inputs") or entry.get("input_schema") or {}
    properties = schema.get("properties", {})
    if isinstance(properties.get("input"), dict):
        properties = properties["input"].get("properties", {})
    values = deepcopy(inputs)
    groups, encoded, metadata = {}, [], []
    sockets = {item.get("socket") for item in native_media}
    if "last_frame" in sockets and "first_frame" not in sockets:
        raise ValueError("Connect a first_frame before using last_frame.")
    for item in native_media:
        wire, socket = item["wire_name"], item["socket"]
        if wire not in properties:
            raise ValueError("This model does not support the connected image input.")
        if wire not in groups and values.get(wire) not in (None, "", [], {}):
            raise ValueError(f"{wire}: choose native image connections or URL input, not both.")
        image = mask_batch_to_images(item["value"]) if item["kind"] == "mask" else item["value"]
        pngs = image_batch_to_pngs(image)
        shape = tuple(image.shape)
        height, width, channels = shape[-3:]
        hashes = [hashlib.sha256(data).hexdigest() for data in pngs]
        info = {"count": len(pngs), "height": int(height), "width": int(width), "channels": int(channels), "sha256": hashes,
                "upload_required": True, "placeholders": [f"https://crun-next.invalid/local/{value}.png" for value in hashes]}
        if not item["many"] and info["count"] != 1:
            raise ValueError(f"{socket}: connect exactly one image; use separate reference sockets for frame pairs.")
        groups.setdefault(wire, []).extend(info["placeholders"])
        metadata.append({**info, "socket": socket, "wire_name": wire, "kind": item["kind"]})
        encoded.append({"wire_name": wire, "pngs": pngs})
    primary = next((info for info in metadata if info["socket"] in {"image", "first_frame"}), None)
    mask = next((info for info in metadata if info["kind"] == "mask"), None)
    if primary and mask and (mask["width"], mask["height"]) != (primary["width"], primary["height"]):
        raise ValueError("The mask must match the connected image dimensions; resize it explicitly first.")
    for wire, references in groups.items():
        field = properties[wire]
        array_field = field.get("type") == "array" or isinstance(field.get("type"), list) and "array" in field["type"] or any(branch.get("type") == "array" for branch in field.get("oneOf", []) + field.get("anyOf", []) if isinstance(branch, dict))
        if array_field:
            values[wire] = references
        elif len(references) == 1:
            values[wire] = references[0]
        else:
            raise ValueError(f"{wire}: this model accepts exactly one image.")
    return values, encoded, metadata


def run_entry(entry: dict, inputs: dict, mode: str, allow_paid_generation: bool = False, max_credits: float = 0, *, native_media: list | None = None, allow_upload: bool = False) -> dict:
    if mode not in {"prepare", "estimate", "generate"}:
        raise ValueError("Select prepare, estimate or generate.")
    if mode != "prepare" and "https://crun-next.invalid/" in json.dumps(inputs):
        raise ValueError("Local preparation placeholders cannot be sent to CRUN. Connect the original images or supply actual public reference URLs.")
    prepared_inputs, encoded_media, media_info = _native_inputs(entry, inputs, native_media)
    payload, errors = build_payload(entry, prepared_inputs)
    result = {"mode": mode, "entry_id": entry.get("id"), "model": entry.get("model"), "payload": payload,
              "task_id": "", "credits": -1.0, "credit_state": "unavailable", "status": "draft", "errors": errors,
              "warnings": [], "native_media": media_info, "credit_limit": max_credits,
              "quoted_at": None, "balance_before": None}
    if media_info:
        result["warnings"].append("Connected images remain local in prepare mode. Selecting estimate or generate uploads the references needed for that action.")
    if mode == "prepare":
        return result
    if errors:
        raise ValueError("Invalid model input: " + "; ".join(errors[:12]))
    supported = entry.get("method", "POST").upper() == "POST" and entry.get("endpoint") == "/api/v1/client/job/CreateTask" and isinstance(payload.get("input"), dict) and isinstance(payload.get("model"), str)
    if not supported or entry.get("generation_supported") is False:
        raise ValueError("This operation has a dedicated protocol. It is available for preparation, not execution in this release.")
    # The selected action is the intent. Legacy checkbox arguments remain in
    # the signature so existing workflows load, but are no longer extra gates.
    missing = configuration_errors(mode, mode == "generate", max_credits, allow_upload=True, has_native_media=bool(encoded_media))
    if missing:
        raise ValueError("CRUN setup incomplete: " + " ".join(missing) + " No CRUN request was made.")
    client = CRUNClient()
    if encoded_media:
        from .media import upload_pngs
        uploaded = {}
        for item in encoded_media:
            uploaded.setdefault(item["wire_name"], []).extend(upload_pngs(client, item["pngs"], allow_upload=True))
        for wire, urls in uploaded.items():
            prepared_inputs[wire] = urls if isinstance(prepared_inputs[wire], list) else urls[0]
        payload, errors = build_payload(entry, prepared_inputs)
        if errors:
            raise ValueError("Uploaded reference validation failed; no task submitted: " + "; ".join(errors[:12]))
        result["payload"] = payload
        result["warnings"] = ["Connected references were uploaded for the selected action. CRUN upload URLs are temporary."]
        for info in result["native_media"]:
            info["upload_required"] = False
    quote = client.estimate_credits(payload["model"], payload["input"])
    result.update(credits=quote["credits"], credit_state="estimate", status="estimated", provisional=quote["estimated"], quoted_at=int(time.time()))
    limit_label = f"{max_credits:g} CRUN credits" if max_credits > 0 else "none (optional cap disabled)"
    print(f"[CRUN Next] Quote for {payload['model']}: {quote['credits']:g} CRUN credits; optional generation limit: {limit_label}.")
    if max_credits > 0:
        result["warnings"].append("The optional credit limit checks the estimate, not a provider-enforced final spending cap.")
    if mode == "estimate":
        return result
    if max_credits > 0 and quote["credits"] > max_credits:
        message = (f"CRUN quotes {quote['credits']:g} credits; your limit is {max_credits:g} credits. "
                   "No generation was submitted. Choose a higher limit only if you approve this quote.")
        result.update(status="budget_blocked")
        result["errors"].append(message)
        print(f"[CRUN Next] {message}")
        return result
    balance = client.get_balance()
    result["balance_before"] = balance
    if balance < quote["credits"]:
        message = (f"CRUN quotes {quote['credits']:g} credits; your available balance is {balance:g} credits. "
                   "No generation was submitted because the balance is insufficient.")
        result.update(status="insufficient_balance")
        result["errors"].append(message)
        print(f"[CRUN Next] {message}")
        return result
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
