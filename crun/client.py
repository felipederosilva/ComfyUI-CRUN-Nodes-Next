"""Minimal non-generating CRUN API client for the 0.1.0 connection skeleton.

Only fixed documented endpoints are exposed. Requests never follow redirects,
retry automatically, or print provider response bodies containing private data.
"""
from __future__ import annotations

import math
import re
from typing import Any

import requests

from .settings import SettingsError, get_api_key

API_BASE = "https://api.crun.ai"
_EFFECT_PATHS = {"kling": "kling-templates", "bytedance": "bytedance-templates", "vidu": "vidu-templates"}


class CRUNError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def _credit_number(value: Any) -> float:
    if isinstance(value, bool):
        raise CRUNError("CRUN returned an invalid credit amount.")
    try:
        amount = float(value)
    except (ValueError, TypeError, OverflowError):
        raise CRUNError("CRUN returned an invalid credit amount.") from None
    if not math.isfinite(amount) or amount < 0:
        raise CRUNError("CRUN returned an invalid credit amount.")
    return amount


class CRUNClient:
    """Credentialed reads and the documented non-generating estimate endpoint."""

    def __init__(self, api_key: str | None = None, session: Any = None):
        try:
            key = get_api_key() if api_key is None else api_key
        except SettingsError:
            raise CRUNError("CRUN credential is unavailable. Re-enter it in CRUN Next settings.") from None
        if not isinstance(key, str) or not key.strip() or len(key) > 8192 or any(ord(c) < 32 for c in key):
            raise CRUNError("Configure a valid CRUN API key in Comfy Settings → CRUN Next.")
        self._api_key = key.strip()
        self.session = session if session is not None else requests.Session()

    def _request(self, method: str, path: str, *, params: dict | None = None, payload: dict | None = None) -> Any:
        try:
            response = self.session.request(
                method, API_BASE + path,
                headers={"x-api-key": self._api_key, "Accept": "application/json", "Content-Type": "application/json"},
                params=params, json=payload, timeout=(10, 60), allow_redirects=False,
            )
        except requests.Timeout:
            raise CRUNError("CRUN request timed out. No automatic retry was made.") from None
        except requests.RequestException:
            raise CRUNError("Could not reach CRUN. Check your connection and try again.") from None
        status = response.status_code
        if status in (401, 403):
            raise CRUNError("CRUN rejected the API key or its permissions.", status=status)
        if status == 429:
            raise CRUNError("CRUN rate limit reached. Wait before trying again.", status=status)
        if not 200 <= status < 300:
            raise CRUNError("CRUN returned an unsuccessful HTTP response.", status=status)
        try:
            body = response.json()
        except (ValueError, TypeError):
            raise CRUNError("CRUN returned an invalid JSON response.") from None
        if not isinstance(body, dict) or isinstance(body.get("code"), bool) or body.get("code") != 200:
            code = body.get("code") if isinstance(body, dict) else None
            code = code if isinstance(code, int) and not isinstance(code, bool) else None
            messages = {
                401: "CRUN rejected the API key.",
                402: "CRUN reports insufficient credits.",
                403: "CRUN rejected this API key's permissions.",
                422: "CRUN rejected the request parameters. Check the model documentation.",
                429: "CRUN rate limit reached. Wait before trying again.",
                455: "CRUN reports temporary service unavailability.",
            }
            raise CRUNError(messages.get(code, "CRUN returned an unsuccessful API response."), code=code, status=status)
        if "data" not in body:
            raise CRUNError("CRUN response is missing its data field.")
        return body["data"]

    def get_balance(self) -> float:
        data = self._request("GET", "/api/v1/client/account/balance")
        if not isinstance(data, dict) or "balance" not in data:
            raise CRUNError("CRUN response is missing the account balance.")
        return _credit_number(data["balance"])

    def get_task(self, task_id: str) -> dict[str, Any]:
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", task_id):
            raise CRUNError("Enter a valid existing CRUN task ID.")
        data = self._request("GET", "/api/v1/client/job/TaskInfo", params={"task_id": task_id})
        if not isinstance(data, dict):
            raise CRUNError("CRUN returned invalid task information.")
        return data

    def list_effects(self, provider: str) -> dict[str, Any]:
        if provider not in _EFFECT_PATHS:
            raise CRUNError("Choose a supported Effects provider: kling, bytedance or vidu.")
        data = self._request("GET", "/api/v1/client/job/" + _EFFECT_PATHS[provider])
        if isinstance(data, list):
            return {"templates": data, "total": len(data)}
        if not isinstance(data, dict):
            raise CRUNError("CRUN returned an invalid Effects catalog.")
        return data

    def estimate_credits(self, model: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(model, str) or not model.strip() or len(model) > 256 or any(ord(c) < 32 for c in model):
            raise CRUNError("Enter the exact documented CRUN model ID.")
        if not isinstance(input_payload, dict):
            raise CRUNError("Model input must be a JSON object.")
        data = self._request("POST", "/api/v1/client/job/estimate-credits", payload={"model": model.strip(), "input": input_payload})
        if not isinstance(data, dict) or not isinstance(data.get("estimated"), bool):
            raise CRUNError("CRUN returned an invalid credit estimate.")
        return {"credits": _credit_number(data.get("credits")), "estimated": data["estimated"]}
