"""Local-only Comfy bridge. Provider keys never enter workflows or GET responses."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import secrets
import time
from urllib.parse import urlsplit

from aiohttp import web

from . import settings
from .client import CRUNClient, CRUNError
from .effects import normalize_catalog
from .tools import list_tools
from .version import VERSION

_NONCE = secrets.token_urlsafe(32)
_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
        mapped = getattr(address, "ipv4_mapped", None)
        return bool(address.is_loopback or (mapped and mapped.is_loopback))
    except ValueError:
        return False


def check_local_request(request, *, nonce: bool = True) -> None:
    """Reject remote peers, DNS rebinding, cross-origin writes, and forged requests."""
    peer = str(request.remote or "")
    host = urlsplit(f"http://{request.host}").hostname or ""
    if not _loopback(peer) or not _loopback(host):
        raise web.HTTPForbidden(text="CRUN Next connection settings are local-only.")
    origin = request.headers.get("Origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request.host.lower():
            raise web.HTTPForbidden(text="Cross-origin CRUN Next requests are not allowed.")
    if nonce and not hmac.compare_digest(request.headers.get("X-CRUN-Nonce", ""), _NONCE):
        raise web.HTTPForbidden(text="Refresh CRUN Next before performing this action.")


def _json(payload, *, status: int = 200):
    return web.json_response(payload, status=status, headers=_HEADERS)


async def _body(request) -> dict:
    if request.content_length is not None and request.content_length > 65536:
        raise ValueError("Request is too large.")
    # A hard read bound also covers chunked transfer without Content-Length.
    chunks, size = [], 0
    async for chunk in request.content.iter_chunked(8192):
        size += len(chunk)
        if size > 65536:
            raise ValueError("Request is too large.")
        chunks.append(chunk)
    raw = b"".join(chunks)
    import json

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def _route(handler):
    async def wrapped(request):
        try:
            check_local_request(request, nonce=handler.__name__ != "status")
            return await handler(request)
        except web.HTTPException as exc:
            return _json({"ok": False, "error": exc.text}, status=exc.status)
        except (ValueError, TypeError):
            return _json({"ok": False, "error": "Invalid request. Check the selected provider and fields."}, status=400)
        except CRUNError as exc:
            # CRUNError messages are sanitized in the provider client.
            return _json({"ok": False, "error": str(exc)}, status=502)
        except Exception:
            return _json({"ok": False, "error": "CRUN Next could not complete this action. Check local storage and connection."}, status=500)

    return wrapped


@_route
async def status(request):
    return _json({"ok": True, "version": VERSION, **settings.public_status(), "nonce": _NONCE})


@_route
async def credentials(request):
    body = await _body(request)
    key = body.get("api_key")
    if not isinstance(key, str) or not key.strip() or len(key) > 4096:
        raise ValueError("Invalid key.")
    await asyncio.to_thread(settings.save_api_key, key)
    return _json({"ok": True, **settings.public_status()})


@_route
async def clear_credentials(request):
    await asyncio.to_thread(settings.clear_api_key)
    return _json({"ok": True, **settings.public_status()})


@_route
async def connection(request):
    balance = await asyncio.to_thread(lambda: CRUNClient().get_balance())
    print(f"[CRUN Next] Account balance: {balance:g} CRUN credits (live check)")
    return _json({"ok": True, "balance": balance, "checked_at": int(time.time())})


@_route
async def effects_catalog(request):
    body = await _body(request)
    provider = body.get("provider")
    if provider not in {"kling", "bytedance", "vidu"}:
        raise ValueError("Unsupported provider.")
    payload = await asyncio.to_thread(lambda: CRUNClient().list_effects(provider))
    cards = normalize_catalog(provider, payload)
    return _json({"ok": True, "provider": provider, "cards": cards, "fetched_at": int(time.time())})


@_route
async def tools(request):
    return _json({"ok": True, "tools": list_tools()})


def register_routes(routes):
    """Register once per route table; do not open a second HTTP server."""
    if getattr(routes, "_crun_next_registered", False):
        return
    for method, path, handler in [
        ("get", "/crun-next/status", status),
        ("post", "/crun-next/credentials", credentials),
        ("post", "/crun-next/credentials/clear", clear_credentials),
        ("post", "/crun-next/connection", connection),
        ("post", "/crun-next/effects/catalog", effects_catalog),
        ("get", "/crun-next/tools", tools),
    ]:
        getattr(routes, method)(path)(handler)
    routes._crun_next_registered = True
