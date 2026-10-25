"""Public, schema-first CRUN catalog discovery. No generation or credential use.

Bundled/cache reads are local-only. Refresh is explicit and fetches a bounded
inventory from CRUN's public documentation host, without API authentication.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import requests

from .settings import settings_path

DOCS = "https://docs.crun.ai"
INDEX_URL = DOCS + "/llms.txt"
MODEL_INDEX_URL = DOCS + "/_llms/en/models.txt"
LLM_LIST_URL = DOCS + "/models/llm-list.md"
BUNDLED_PATH = Path(__file__).resolve().parents[1] / "data" / "catalog.json"
MAX_DOCUMENT_BYTES = 3 * 1024 * 1024
MAX_SCHEMA_PAGES = 300
_LOCK = threading.Lock()
_LOCAL = threading.local()
_LINK = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)(?::\s*(.*))?$", re.MULTILINE)
_PROVIDERS = {
    "google": "Google", "seedream": "ByteDance", "seedance": "ByteDance",
    "bytedance": "ByteDance", "flux": "Black Forest Labs", "qwen": "Alibaba",
    "wan": "Alibaba", "openai": "OpenAI", "grok-imagine": "xAI",
    "kling": "Kling", "vidu": "Vidu", "minimax": "MiniMax", "pixverse": "PixVerse",
    "agnes": "Agnes AI", "happyhorse": "Alibaba", "runway": "Runway",
    "hunyuan": "Tencent", "tripo": "Tripo", "prunaai": "PrunaAI",
    "z-image": "Alibaba", "sora2": "OpenAI",
}
_SKIP_PARTS = ("/common-api/", "/models/common/", "/asset-upload", "/asset-info", "/visual-validate", "task-info", "-template-list", "/detect-face-")


class CatalogError(RuntimeError):
    """Safe catalog failure, without request headers or user credentials."""


def cache_path() -> Path:
    return settings_path().parent / "catalog.json"


def _public_url(url: str) -> str:
    parsed = urlsplit(urljoin(DOCS + "/", url))
    if parsed.scheme != "https" or parsed.hostname != "docs.crun.ai" or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CatalogError("Catalog source must be a public CRUN documentation URL.")
    return parsed.geturl()


def _fetch(url: str) -> bytes:
    url = _public_url(url)
    session = getattr(_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        # Documentation downloads reject Python's default user agent on some
        # CDN routes. This is a normal public GET, not a provider API request.
        session.headers.update({"User-Agent": "Mozilla/5.0 CRUN-Next-Catalog/0.1", "Accept": "application/json, text/plain, text/markdown"})
        _LOCAL.session = session
    try:
        with session.get(url, timeout=(10, 35), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise CatalogError(f"Public documentation returned HTTP {response.status_code}.")
            data, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    raise CatalogError("Public documentation exceeds the safe size limit.")
                data.append(chunk)
            return b"".join(data)
    except requests.RequestException:
        raise CatalogError("Could not download public CRUN documentation.") from None


def parse_index(text: str) -> list[str]:
    urls = []
    for _, url, _ in _LINK.findall(text):
        parsed = urlsplit(urljoin(DOCS + "/", url))
        if parsed.path.endswith(".json") and not parsed.path.startswith("/zh/"):
            urls.append(_public_url(url))
    urls = list(dict.fromkeys(urls))
    if not urls:
        raise CatalogError("CRUN documentation index did not contain schemas.")
    if len(urls) > MAX_SCHEMA_PAGES:
        raise CatalogError("CRUN documentation inventory exceeds the safe page limit.")
    return urls


def parse_document_metadata(text: str) -> dict[str, dict[str, str]]:
    """Use documentation labels/headings, never infer wire model IDs here."""
    result, heading = {}, ""
    for line in text.splitlines():
        if line.startswith("### "):
            heading = line[4:].strip()
        match = _LINK.match(line)
        if not match:
            continue
        title, url, description = match.groups()
        if url.startswith(DOCS + "/") and url.endswith(".md"):
            result[url[:-3] + ".json"] = {"title": title, "description": (description or "")[:400], "section": heading}
    return result


def resolve_schema(schema: Any, document: dict, stack: tuple[str, ...] = (), depth: int = 0) -> Any:
    """Resolve local JSON pointers, with cycles and recursion bounded."""
    if depth > 45:
        return {"unresolved": True, "reason": "depth_limit"}
    if isinstance(schema, list):
        return [resolve_schema(value, document, stack, depth + 1) for value in schema]
    if not isinstance(schema, dict):
        return schema
    reference = schema.get("$ref")
    if reference:
        if not isinstance(reference, str) or not reference.startswith("#/") or reference in stack:
            return {"$ref": reference, "unresolved": True}
        target: Any = document
        try:
            for piece in reference[2:].split("/"):
                target = target[unquote(piece).replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            return {"$ref": reference, "unresolved": True}
        result = resolve_schema(target, document, (*stack, reference), depth + 1)
        if not isinstance(result, dict):
            return result
        result.update(resolve_schema({k: v for k, v in schema.items() if k != "$ref"}, document, stack, depth + 1))
        return result
    return {key: resolve_schema(value, document, stack, depth + 1) for key, value in schema.items()}


def _merged(schema: dict) -> dict:
    result = deepcopy(schema)
    for branch in schema.get("allOf", []):
        if not isinstance(branch, dict):
            continue
        branch = _merged(branch)
        result.setdefault("properties", {}).update(branch.get("properties", {}))
        result["required"] = sorted(set(result.get("required", [])) | set(branch.get("required", [])))
    return result


def _variants(schema: dict) -> list[dict]:
    schema = _merged(schema)
    alternatives = schema.get("oneOf") or schema.get("anyOf")
    if not isinstance(alternatives, list):
        return [schema]
    variants = []
    for alternative in alternatives:
        if not isinstance(alternative, dict):
            continue
        branch = {key: deepcopy(value) for key, value in schema.items() if key not in {"oneOf", "anyOf"}}
        props = deepcopy(branch.get("properties", {}))
        branch.update(_merged(alternative))
        props.update(branch.get("properties", {}))
        branch["properties"] = props
        branch["required"] = sorted(set(schema.get("required", [])) | set(alternative.get("required", [])))
        variants.append(branch)
    return variants or [schema]


def _model_ids(field: Any) -> list[str]:
    if not isinstance(field, dict):
        return []
    values = field.get("enum")
    if not isinstance(values, list):
        values = [field.get("const", field.get("default", field.get("example")))]
    for alternative in field.get("oneOf", []) + field.get("anyOf", []):
        values += _model_ids(alternative)
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", value)))


def _compact(value: Any) -> Any:
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if not isinstance(value, dict):
        return value
    allowed = {"type", "properties", "required", "default", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "minLength", "maxLength", "pattern", "format", "items", "oneOf", "anyOf", "allOf", "nullable", "additionalProperties", "$ref", "unresolved", "description", "title", "example", "examples"}
    result = {}
    for key, item in value.items():
        if key not in allowed:
            continue
        if key == "properties" and isinstance(item, dict):
            result[key] = {name: _compact(field) for name, field in item.items()}
        elif key == "description" and isinstance(item, str):
            result[key] = item[:400]
        else:
            result[key] = _compact(item)
    return result


def _classification(url: str, metadata: dict) -> tuple[str, str, str]:
    path = urlsplit(url).path
    pieces = path.strip("/").split("/")
    provider = _PROVIDERS.get(pieces[1], "CRUN") if len(pieces) > 1 else "CRUN"
    if path.startswith("/templates/"):
        provider = {"kling": "Kling", "bytedance": "ByteDance", "vidu": "Vidu"}.get(pieces[-1].split("-")[0], "CRUN")
        return "effect", "AI Effects", provider
    if path.startswith("/ai-tools/"):
        return "tool", "AI Tools", "CRUN"
    if path.startswith("/suno-api/"):
        return ("video", "Music", "Suno") if "generate-music-video" in path else ("music", "Music", "Suno")
    if "/llm/" in path:
        return "llm", "LLM", provider
    section = metadata.get("section", "").lower()
    if "image" in section:
        return "image", "Image", provider
    if "video" in section:
        return "video", "Video", provider
    if "audio" in section:
        return "audio", "Audio", provider
    if "3d" in section or (len(pieces) > 1 and pieces[1] in {"hunyuan", "tripo"}):
        return "3d", "3D", provider
    name = pieces[-1]
    if any(token in name for token in ("video", "lip-sync", "animate", "dreamactor", "motion-control", "hailuo", "v3-", "avatar", "sora-")):
        return "video", "Video", provider
    if "tts" in name:
        return "audio", "Audio", provider
    if "watermark" in name:
        return "tool", "AI Tools", provider
    return "image", "Image", provider


def _auth(spec: dict, operation: dict) -> list[str]:
    schemes = spec.get("components", {}).get("securitySchemes", {})
    result = []
    for choice in operation.get("security", spec.get("security", [])):
        for name in choice:
            definition = schemes.get(name, {})
            value = "bearer" if str(definition.get("scheme", "")).lower() == "bearer" else definition.get("name", name)
            if value not in result:
                result.append(str(value))
    return result


def _defaults(schema: Any, depth: int = 0) -> Any:
    """Only provider defaults, never sample URLs/prompts or guessed values."""
    if not isinstance(schema, dict) or depth > 12:
        return None
    if "default" in schema:
        return deepcopy(schema["default"])
    props = schema.get("properties")
    if not isinstance(props, dict):
        return None
    result = {}
    for key, field in props.items():
        value = _defaults(field, depth + 1)
        if value is not None:
            result[key] = value
    return result or None


def _contains_unresolved(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("unresolved") is True or any(_contains_unresolved(item) for item in value.values())
    return isinstance(value, list) and any(_contains_unresolved(item) for item in value)


def normalize_openapi(spec: dict, source_url: str, metadata: dict | None = None) -> list[dict[str, Any]]:
    """Extract documented wire IDs and compact model-specific parameter schemas."""
    metadata = metadata or {}
    source_url = _public_url(source_url)
    if any(part in urlsplit(source_url).path for part in _SKIP_PARTS) or "/models/llm/" in source_url:
        return []
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise CatalogError("Source is not an OpenAPI document with paths.")
    kind, group, provider = _classification(source_url, metadata)
    entries = []
    for endpoint, operations in spec["paths"].items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() != "post" or not isinstance(operation, dict):
                continue
            request_body = resolve_schema(operation.get("requestBody", {}), spec)
            body = request_body.get("content", {}).get("application/json", {}).get("schema")
            if not isinstance(body, dict):
                continue
            root = resolve_schema(body, spec)
            for variant in _variants(root):
                props = variant.get("properties", {})
                models: list[str | None] = _model_ids(props.get("model"))
                if not models and endpoint != "/api/v1/client/job/CreateTask" and isinstance(operation.get("operationId"), str):
                    # Some documented operations (e.g. Suno personas) have no
                    # wire-model field. Keep the operation, never invent an ID.
                    models = [None]
                for model in models:
                    inputs = _compact(props.get("input", {"type": "object", "properties": {key: value for key, value in props.items() if key not in {"model", "callback_url"}}, "required": [key for key in variant.get("required", []) if key not in {"model", "callback_url"}]}))
                    identity = f"{source_url}|{method}|{endpoint}|{model}"
                    entries.append({
                        "id": "crun-" + hashlib.sha256(identity.encode()).hexdigest()[:20],
                        "model": model,
                        "operation_id": operation.get("operationId", ""),
                        "model_id_available": model is not None,
                        "title": metadata.get("title") or spec.get("info", {}).get("title") or model,
                        "provider": provider, "kind": kind, "group": group,
                        "method": method.upper(), "endpoint": endpoint,
                        "auth": _auth(spec, operation), "protocols": ["media_task"],
                        "inputs": inputs, "input_schema": inputs,
                        "request_schema": _compact(variant),
                        "payload_template": {**({"model": model} if model is not None else {}), **({"input": _defaults(props.get("input")) or {}} if "input" in props else {})},
                        "root_defaults": _defaults(variant) or {},
                        "root_examples": deepcopy(request_body.get("content", {}).get("application/json", {}).get("examples", {})),
                        "generation_supported": endpoint == "/api/v1/client/job/CreateTask" and "input" in props and not _contains_unresolved(variant),
                        "documentation_url": source_url[:-5],
                        "schema_url": source_url,
                        "source": "public_openapi", "availability": "documented_not_account_verified",
                        "execution_enabled": False,
                    })
    # Distinct alternative schemas with the same identity remain visible as oneOf.
    merged = {}
    for entry in entries:
        if entry["id"] not in merged:
            merged[entry["id"]] = entry
        elif entry["inputs"] != merged[entry["id"]]["inputs"]:
            old = merged[entry["id"]]["inputs"]
            options = old.get("oneOf", []) if set(old) == {"oneOf"} else [old]
            options.append(entry["inputs"])
            merged[entry["id"]]["inputs"] = {"oneOf": options}
            merged[entry["id"]]["input_schema"] = merged[entry["id"]]["inputs"]
            merged[entry["id"]]["generation_supported"] = False
            merged[entry["id"]]["request_schema"] = {"oneOf": [merged[entry["id"]]["request_schema"], entry["request_schema"]]}
    return list(merged.values())


def parse_llm_table(text: str, chat_spec: dict | None = None) -> list[dict]:
    entries = []
    schema = {}
    if chat_spec:
        operation = chat_spec.get("paths", {}).get("/api/v1/chat/completions", {}).get("post", {})
        body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
        schema = _compact(resolve_schema(body, chat_spec))
        schema.get("properties", {}).pop("model", None)
        schema["required"] = [key for key in schema.get("required", []) if key != "model"]
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{1,255}", cells[0]) or cells[0] == "Model ID":
            continue
        model, provider = cells[:2]
        identity = "llm:" + model
        entries.append({
            "id": "crun-" + hashlib.sha256(identity.encode()).hexdigest()[:20],
            "model": model, "title": model, "provider": provider,
            "operation_id": "", "model_id_available": True,
            "kind": "llm", "group": "LLM", "method": "POST",
            "endpoint": "/api/v1/chat/completions", "auth": ["bearer", "x-api-key"],
            "protocols": ["chat_completions"], "inputs": deepcopy(schema), "input_schema": deepcopy(schema),
            "request_schema": {**deepcopy(schema), "properties": {**deepcopy(schema.get("properties", {})), "model": {"type": "string", "const": model}}},
            "payload_template": {"model": model}, "root_defaults": _defaults(schema) or {}, "root_examples": {},
            "generation_supported": False,
            "documentation_url": LLM_LIST_URL[:-3], "schema_url": DOCS + "/models/llm/chat-completions.json",
            "source": "public_llm_documentation", "availability": "documented_not_account_verified",
            "execution_enabled": False,
            "pricing_note": {"input_usd_per_million_tokens": cells[2].replace("\\", ""), "output_usd_per_million_tokens": cells[3].replace("\\", ""), "source": "documentation_snapshot_not_live_quote"},
        })
    if not entries:
        raise CatalogError("CRUN LLM documentation table did not contain model IDs.")
    return entries


def parse_live_llm_models(payload: dict) -> list[dict[str, str]]:
    """Parse only; callers must separately authorize credentialed GET /models."""
    if not isinstance(payload, dict) or payload.get("object") != "list" or not isinstance(payload.get("data"), list):
        raise CatalogError("CRUN live LLM model list has an unsupported shape.")
    result = []
    for item in payload["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", item["id"]):
            raise CatalogError("CRUN live LLM model list contains an invalid model ID.")
        result.append({"model": item["id"], "provider": str(item.get("owned_by", "CRUN")), "source": "authenticated_llm_catalog"})
    return result


def merge_live_models(snapshot: dict, records: list[dict]) -> dict:
    """Merge a separately authorized GET /models result without performing I/O.

    New live IDs get the shared documented chat parameter contract, never copied
    prices. Listed availability is not proof that a paid generation succeeded.
    This function returns data only; callers choose a private local cache path.
    """
    _validate_snapshot(snapshot)
    result = deepcopy(snapshot)
    entries = result["entries"]
    existing = {entry["model"]: entry for entry in entries if entry["kind"] == "llm"}
    live_ids = set()
    for record in records:
        model = record.get("model") if isinstance(record, dict) else None
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", model):
            raise CatalogError("Live LLM inventory contains an invalid model record.")
        live_ids.add(model)
        if model in existing:
            entry = existing[model]
        else:
            base = next(iter(existing.values()), None)
            entry = deepcopy(base) if base else parse_llm_table(f"| {model} | CRUN | unknown | unknown |")[0]
            entry.update({"id": "crun-" + hashlib.sha256(("llm:" + model).encode()).hexdigest()[:20], "model": model, "title": model, "provider": str(record.get("provider", "CRUN")), "source": "authenticated_llm_catalog", "documentation_url": DOCS + "/models/llm/quickstart", "payload_template": {"model": model}})
            entry.pop("pricing_note", None)
            entry.get("request_schema", {}).get("properties", {})["model"] = {"type": "string", "const": model}
            entries.append(entry)
            existing[model] = entry
        entry["availability"] = "listed_in_authenticated_llm_catalog"
        entry["account_catalog_listed"] = True
    for model, entry in existing.items():
        if model not in live_ids:
            entry["availability"] = "not_listed_in_current_llm_catalog"
            entry["account_catalog_listed"] = False
    entries.sort(key=lambda item: (item["kind"], item["provider"], item.get("model") or "", item["id"]))
    result["account_catalog_checked_at"] = datetime.now(timezone.utc).isoformat()
    result["account_llm_model_count"] = len(live_ids)
    result["summary"] = _summary(entries, result.get("errors", []), result.get("summary", {}).get("documentation_schema_count", 0), result.get("skipped_non_model_specs", []))
    return result


def _summary(entries: list[dict], errors: list[dict], spec_count: int, skipped: list[str]) -> dict:
    return {"entry_count": len(entries), "unique_model_count": len({entry["model"] for entry in entries if entry.get("model")}), "by_kind": dict(sorted(Counter(entry["kind"] for entry in entries).items())), "providers": sorted({entry["provider"] for entry in entries}), "documentation_schema_count": spec_count, "unresolved_count": len(errors), "skipped_non_model_spec_count": len(skipped)}


def _validate_snapshot(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("entries"), list) or not value["entries"]:
        raise CatalogError("Catalog snapshot is missing or invalid.")
    for entry in value["entries"]:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and entry[key] for key in ("id", "kind", "documentation_url")) or not (isinstance(entry.get("model"), str) and entry["model"] or entry.get("model") is None and isinstance(entry.get("operation_id"), str) and entry["operation_id"]):
            raise CatalogError("Catalog contains an invalid model record.")
    return value


def _read_snapshot(path: Path) -> dict:
    if path.stat().st_size > 30 * 1024 * 1024:
        raise CatalogError("Catalog snapshot exceeds the safe size limit.")
    return _validate_snapshot(json.loads(path.read_bytes().decode("utf-8-sig")))


def list_catalog() -> dict:
    """Read the newest valid local snapshot. Never use the network on UI open."""
    snapshots = []
    warnings = []
    for path in (BUNDLED_PATH, cache_path()):
        if not path.is_file():
            continue
        try:
            snapshots.append(_read_snapshot(path))
        except (OSError, ValueError, CatalogError):
            warnings.append("A local catalog snapshot was unreadable; a valid fallback was used.")
    if not snapshots:
        return {"schema_version": 1, "refreshed_at": None, "entries": [], "summary": _summary([], [], 0, []), "errors": [], "warnings": ["Catalog not loaded. Explicitly refresh public model definitions."]}
    result = deepcopy(max(snapshots, key=lambda value: (str(value.get("refreshed_at", "")), str(value.get("account_catalog_checked_at", "")))))
    result.setdefault("warnings", []).extend(warnings)
    return result


load_catalog = list_catalog


def _write_snapshot(value: dict, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, prefix=".catalog-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def save_catalog(snapshot: dict, *, destination: Path | str | None = None) -> None:
    """Persist already validated public/account catalog metadata, never a key."""
    _validate_snapshot(snapshot)
    _write_snapshot(snapshot, Path(destination) if destination is not None else cache_path())


def refresh_catalog(*, destination: Path | str | None = None, max_workers: int = 4) -> dict:
    """Explicit public GET-only refresh; no credentials, uploads or generation."""
    if not _LOCK.acquire(blocking=False):
        raise CatalogError("A catalog refresh is already running.")
    try:
        urls = parse_index(_fetch(INDEX_URL).decode("utf-8-sig"))
        metadata = parse_document_metadata(_fetch(MODEL_INDEX_URL).decode("utf-8-sig"))
        errors, skipped, entries = [], [], []
        chat_spec = None

        def fetch_spec(url):
            try:
                spec = json.loads(_fetch(url).decode("utf-8-sig"))
                return spec, normalize_openapi(spec, url, metadata.get(url))
            except (CatalogError, ValueError, TypeError, KeyError):
                raise CatalogError("Could not parse this public model definition.") from None

        for url in urls:
            if any(part in urlsplit(url).path for part in _SKIP_PARTS):
                skipped.append(url)
        fetch_urls = [url for url in urls if url not in skipped]
        with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 4))) as pool:
            tasks = {pool.submit(fetch_spec, url): url for url in fetch_urls}
            for task in as_completed(tasks):
                url = tasks[task]
                try:
                    spec, records = task.result()
                    if url.endswith("/models/llm/chat-completions.json"):
                        chat_spec = spec
                    if records:
                        entries.extend(records)
                    elif any(part in urlsplit(url).path for part in _SKIP_PARTS) or "/models/llm/" in url:
                        skipped.append(url)
                    else:
                        errors.append({"source": url, "stage": "normalization", "error": "No exact root model ID could be resolved; not inferred from page name."})
                except CatalogError as exc:
                    errors.append({"source": url, "stage": "download_or_parse", "error": str(exc)})
        try:
            entries.extend(parse_llm_table(_fetch(LLM_LIST_URL).decode("utf-8-sig"), chat_spec))
        except CatalogError as exc:
            errors.append({"source": LLM_LIST_URL, "stage": "llm_table", "error": str(exc)})
        entries = sorted(entries, key=lambda item: (item["kind"], item["provider"], item.get("model") or "", item["id"]))
        if not entries:
            raise CatalogError("Refresh produced no usable model definitions; the previous snapshot was retained.")
        result = {"schema_version": 1, "refreshed_at": datetime.now(timezone.utc).isoformat(), "source": "CRUN public documentation, not account availability", "sources": [INDEX_URL, MODEL_INDEX_URL, LLM_LIST_URL], "entries": entries, "summary": _summary(entries, errors, len(urls), skipped), "errors": sorted(errors, key=lambda item: item["source"]), "skipped_non_model_specs": sorted(skipped), "warnings": ["Preparation is offline by default. Compatible media tasks require explicit paid permission and a positive credit ceiling; paid execution has not been tested.", "LLM table is a documentation snapshot; authenticated GET /api/v1/models is the current availability authority."]}
        _validate_snapshot(result)
        _write_snapshot(result, Path(destination) if destination is not None else cache_path())
        return result
    finally:
        _LOCK.release()
