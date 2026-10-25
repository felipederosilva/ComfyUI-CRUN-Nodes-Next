"""Local-only CRUN credentials; never stored in a workflow or the node package.

Windows persistence uses DPAPI bound to the current Windows user. On other
platforms the secret is stored in an owner-readable file, not encrypted at rest.
An environment credential always takes precedence over a saved credential.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_IS_WINDOWS = os.name == "nt"
_LOCK = threading.RLock()
_FILENAME = "credentials.json"


class SettingsError(RuntimeError):
    """A credential storage failure whose message contains no secret data."""


def settings_path() -> Path:
    """Return the separate credential path without creating anything on read."""
    override = os.environ.get("CRUN_NEXT_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve() / _FILENAME
    try:
        import folder_paths  # type: ignore

        getter = getattr(folder_paths, "get_user_directory", None)
        if callable(getter):
            return Path(getter()) / "CRUN-Nodes-Next" / _FILENAME
    except (ImportError, AttributeError, OSError):
        pass
    if _IS_WINDOWS:
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "ComfyUI" / "CRUN-Nodes-Next" / _FILENAME
    root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "comfyui" / "crun-nodes-next" / _FILENAME


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    """Protect/decrypt using the OS API; never fall back to plaintext on Windows."""
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buffer = ctypes.create_string_buffer(data, len(data))
        incoming = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        outgoing = DataBlob()
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if decrypt:
            function = crypt32.CryptUnprotectData
            function.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.POINTER(DataBlob)]
            arguments = (ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
        else:
            function = crypt32.CryptProtectData
            function.argtypes = [ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.POINTER(DataBlob)]
            arguments = (ctypes.byref(incoming), "CRUN Nodes Next credential", None,
                         None, None, 1, ctypes.byref(outgoing))
        function.restype = wintypes.BOOL
        if not function(*arguments):
            raise SettingsError("Windows credential protection failed. No plaintext key was saved.")
        try:
            return ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(outgoing.pbData, ctypes.c_void_p))
    except SettingsError:
        raise
    except Exception:
        raise SettingsError("Windows credential protection is unavailable. No plaintext key was saved.") from None


def _validate_key(value: str) -> str:
    if not isinstance(value, str):
        raise SettingsError("Enter a valid CRUN API key.")
    value = value.strip()
    if not value or len(value) > 8192 or any(ord(character) < 32 for character in value):
        raise SettingsError("Enter a valid CRUN API key.")
    return value


def _environment_key() -> str:
    value = os.environ.get("CRUN_API_KEY", "").strip()
    return _validate_key(value) if value else ""


def _read_saved() -> str:
    path = settings_path()
    if not path.exists():
        return ""
    try:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("Credential file too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported version")
        credential = value["credential"]
        kind, content = credential["format"], credential["data"]
        if kind == "dpapi":
            if not _IS_WINDOWS:
                raise ValueError("DPAPI requires Windows")
            decoded = base64.b64decode(content, validate=True)
            return _validate_key(_dpapi(decoded, decrypt=True).decode("utf-8"))
        if kind == "owner-file" and not _IS_WINDOWS:
            if os.name == "posix":
                info = path.stat()
                if info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise ValueError("Unsafe permissions")
            return _validate_key(content)
        raise ValueError("Unsafe credential format")
    except Exception:
        raise SettingsError("Saved CRUN credential cannot be read. Re-enter your key in CRUN Next settings.") from None


def get_api_key() -> str:
    """Resolve credentials without network calls or filesystem mutations."""
    with _LOCK:
        return _environment_key() or _read_saved()


def save_api_key(value: str) -> None:
    """Save atomically. On Windows encryption must succeed before file creation."""
    key = _validate_key(value)
    if _IS_WINDOWS:
        credential = {"format": "dpapi", "data": base64.b64encode(_dpapi(key.encode("utf-8"), decrypt=False)).decode("ascii")}
    else:
        credential = {"format": "owner-file", "data": key}
    payload = json.dumps({"schema_version": 1, "credential": credential}, ensure_ascii=False)
    with _LOCK:
        temporary: str | None = None
        try:
            path = settings_path()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix=".crun-", suffix=".tmp", dir=path.parent)
            os.chmod(temporary, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            raise SettingsError("Could not save the CRUN credential. Check access to the local user configuration directory.") from None
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink(missing_ok=True)


def clear_api_key() -> None:
    """Remove only this extension's saved credential; never change environment."""
    with _LOCK:
        try:
            settings_path().unlink(missing_ok=True)
        except OSError:
            raise SettingsError("Could not remove the saved CRUN credential.") from None


def public_status() -> dict[str, Any]:
    """Safe connection state, with no reusable credential in the response."""
    with _LOCK:
        storage = "Windows DPAPI (current user)" if _IS_WINDOWS else "Owner-only local file (not encrypted)"
        try:
            environment = _environment_key()
            key = environment or _read_saved()
            source = "environment" if environment else ("saved" if key else "none")
            hint = "••••" + key[-4:] if len(key) >= 12 else ("••••" if key else "")
            return {"configured": bool(key), "source": source, "key_hint": hint,
                    "storage": "Environment variable" if environment else storage}
        except SettingsError:
            return {"configured": False, "source": "none", "key_hint": "", "storage": storage,
                    "error": "Saved or environment credential is unavailable. Re-enter a valid key."}
