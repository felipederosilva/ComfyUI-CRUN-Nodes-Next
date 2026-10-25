"""Read-only CRUN effect catalog adapters and non-executing draft plans.

CRUN exposes different catalog and request shapes for each effects provider.
This module deliberately has no network client and cannot create a paid task.
"""

from __future__ import annotations

from copy import deepcopy
import ipaddress
import math
from typing import Any
from urllib.parse import urlsplit


PROVIDERS = ("kling", "bytedance", "vidu")
DOCUMENTATION = {
    provider: f"https://docs.crun.ai/templates/{provider}-template"
    for provider in PROVIDERS
}


def _provider(value: str) -> str:
    if not isinstance(value, str) or value not in PROVIDERS:
        raise ValueError("Effect provider must be kling, bytedance or vidu.")
    return value


def _text(value: Any, fallback: str = "") -> str:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip()
    return fallback


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _count(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer() or not 1 <= number <= 100:
        return None
    return int(number)


def _https_url(value: Any) -> str | None:
    """Allow HTTPS assets, excluding credentials and obvious local addresses.

    This does not resolve DNS or fetch URLs; provider ingestion needs its own
    network policy when generation is implemented. In particular, this is not a
    guarantee that a hostname's DNS cannot change or point at a private network.
    """
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        return None
    value = value.strip()
    if len(value) > 8192:
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return None
        if parsed.port not in (None, 443):
            return None
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            # Reject shorthand/integer numeric IP representations as well.
            if "." not in host or host.replace(".", "").isdigit():
                return None
        return value
    except ValueError:
        return None


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        code = payload.get("code")
        if code is not None and code != 200:
            raise ValueError("CRUN effect catalog reports an unsuccessful response.")
        payload = payload.get("data", payload)
    if isinstance(payload, dict):
        if "templates" not in payload:
            raise ValueError("CRUN effect catalog has an unsupported response shape.")
        payload = payload["templates"]
    if not isinstance(payload, list):
        raise ValueError("CRUN effect catalog must contain a templates list.")
    return [entry for entry in payload if isinstance(entry, dict)]


def _first_explicit_count(entry: dict[str, Any]) -> int | None:
    for key in ("InputNum", "required_images", "image_count", "image_num"):
        if key in entry:
            return _count(entry[key])
    return None


def normalize_catalog(provider: str, payload: Any) -> list[dict[str, Any]]:
    """Normalize provider metadata without inventing costs or slot counts.

    Text is retained as text, including non-English names. Consumers must use
    textContent, not HTML interpretation. `raw` is an independent metadata copy.
    No covers/previews are fetched here. An unknown slot count remains None.
    """
    provider = _provider(provider)
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for entry in _rows(payload):
        if provider == "bytedance":
            identifier = _text(entry.get("TemplateId"))
            name = _text(entry.get("Title_en")) or _text(entry.get("Title"))
            category = _text(entry.get("category")) or _text(entry.get("TemplateType"))
            cover = entry.get("Cover")
            preview = entry.get("PreviewVideo")
            # Costs depend on resolution. Do not flatten this into a fabricated
            # single price or assume that the cheapest resolution is selected.
            pricing = []
            for item in entry.get("ConsumeItems", []) if isinstance(entry.get("ConsumeItems"), list) else []:
                if not isinstance(item, dict):
                    continue
                credit = _number(item.get("Credit"))
                if credit is not None:
                    pricing.append({"resolution": _text(item.get("Resolution")), "credits": credit})
            credits: Any = pricing or None
        elif provider == "kling":
            identifier = _text(entry.get("key"))
            name = _text(entry.get("name"))
            category = _text(entry.get("category"))
            cover = entry.get("cover_url")
            preview = entry.get("video_url")
            credits = _number(entry.get("credit"))
        else:
            # Vidu's generation request is verified, but catalog field aliases
            # are defensive until a live authenticated catalog is inspected.
            identifier = _text(entry.get("template")) or _text(entry.get("template_id")) or _text(entry.get("id"))
            name = _text(entry.get("name")) or _text(entry.get("title"))
            category = _text(entry.get("category_name")) or _text(entry.get("category"))
            cover = entry.get("cover_url", entry.get("cover"))
            preview = entry.get("video_url", entry.get("preview_url", entry.get("video")))
            credits = _number(entry.get("credits", entry.get("credit")))
        if not identifier:
            continue
        if identifier in seen:
            if provider == "vidu":
                existing = by_id[identifier]
                variants = existing["raw"].get("catalog_variants")
                if not isinstance(variants, list):
                    variants = [deepcopy(existing["raw"])]
                    existing["raw"]["catalog_variants"] = variants
                variants.append(deepcopy(entry))
                # Avoid presenting the first record's price as universal if the
                # provider ever returns different prices for a repeated ID.
                if credits != existing["credits"]:
                    existing["credits"] = None
            continue
        seen.add(identifier)
        cards.append({
            "id": identifier,
            "provider": provider,
            "name": name or identifier,
            "category": category or "Uncategorized",
            "cover_url": _https_url(cover),
            "preview_url": _https_url(preview),
            "credits": credits,
            "required_images": _first_explicit_count(entry),
            "raw": deepcopy(entry),
        })
        by_id[identifier] = cards[-1]
    return cards


def build_effect_plan(
    provider: str,
    template_id: str,
    image_urls: list[str],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare documented JSON only; never upload, submit, or charge anything.

    Options are intentionally narrow: optional `required_images` is local
    validation metadata, ByteDance accepts `resolution`, and Vidu accepts `bgm`.
    Complete per-template semantics must still be checked before paid execution.
    """
    provider = _provider(provider)
    if not isinstance(template_id, str) or not template_id.strip() or len(template_id) > 256:
        raise ValueError("Choose a valid effect template identifier.")
    template_id = template_id.strip()
    if any(ord(c) < 32 for c in template_id):
        raise ValueError("Template identifier must not contain control characters.")
    if not isinstance(image_urls, list) or len(image_urls) > 100:
        raise ValueError("Image URLs must be a list of at most 100 HTTPS URLs.")
    urls = [_https_url(url) for url in image_urls]
    if any(url is None for url in urls):
        raise ValueError("Image references must be public HTTPS URLs without credentials.")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Effect options must be an object.")
    allowed = {"required_images"}
    allowed.update({"bytedance": {"resolution"}, "vidu": {"bgm"}}.get(provider, set()))
    if set(options) - allowed:
        raise ValueError("Unsupported options for this effect provider.")
    required = _count(options.get("required_images"))
    if options.get("required_images") is not None and required is None:
        raise ValueError("Required image count must be a positive integer.")
    if required is not None and len(urls) != required:
        raise ValueError(f"This effect requires exactly {required} image reference(s).")
    warnings = ["Draft only. This utility does not execute Effects; use the individual template node for an explicitly armed submission."]
    if not urls:
        warnings.append("Add image references before estimating or running this effect.")
    if required is None:
        warnings.append("Image count is not verified; follow the selected template's live input instructions.")
    if provider == "vidu":
        inputs: dict[str, Any] = {"template": template_id, "images": urls}
        if "bgm" in options:
            if not isinstance(options["bgm"], bool):
                raise ValueError("Vidu bgm must be a boolean.")
            inputs["bgm"] = options["bgm"]
    else:
        inputs = {"template_id": template_id, "img_urls": urls}
        if provider == "bytedance":
            resolution = options.get("resolution")
            if resolution is None:
                warnings.append("Choose a supported resolution from the ByteDance catalog before execution.")
            elif not isinstance(resolution, str) or not resolution.strip() or len(resolution) > 24:
                raise ValueError("ByteDance resolution must be a catalog resolution string.")
            else:
                inputs["resolution"] = resolution.strip()
                warnings.append("Resolution must be checked against this template's live ConsumeItems.")
    return {
        "provider": provider,
        "template_id": template_id,
        "status": "draft",
        "execution_enabled": False,
        "ready_to_submit": False,
        "required_images": required,
        "documentation_url": DOCUMENTATION[provider],
        "payload": {"model": f"{provider}/template", "input": inputs},
        "warnings": warnings,
    }
