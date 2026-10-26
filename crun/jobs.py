"""Private, recoverable creative jobs. Never persist prompts, media URLs or keys."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from .client import CRUNError
from .settings import get_api_key, settings_path

LOCK = threading.RLock()
_OBSERVER = ContextVar("crun_submission_observer", default=None)
_FILE_LOCK_DEPTH = ContextVar("crun_job_file_lock_depth", default=0)


@contextmanager
def submission_lock():
    """One creator across threads AND Comfy processes sharing this config."""
    with LOCK:
        if _FILE_LOCK_DEPTH.get():
            yield
            return
        path = _path().with_name("creative-submit.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        acquired = False
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                raise CRUNError("Another CRUN submission is in progress. Wait, then run this same Take to resume it; no new task was submitted by this request.") from None
            token = _FILE_LOCK_DEPTH.set(1)
            try:
                yield
            finally:
                _FILE_LOCK_DEPTH.reset(token)
        finally:
            if acquired:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _path() -> Path:
    return settings_path().parent / "creative-jobs.json"


def request_key(payload: dict, take: int) -> str:
    key = get_api_key()
    if not key:
        raise CRUNError("Configure your CRUN API key in Settings before estimating or generating.")
    canonical = json.dumps({"payload": payload, "take": take}, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hmac.new(key.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _read() -> dict:
    path = _path()
    if not path.exists():
        return {}
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("jobs"), dict):
            raise ValueError()
        if any(not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) or not isinstance(value, dict) for key, value in data["jobs"].items()):
            raise ValueError()
        return data["jobs"]
    except (OSError, ValueError):
        raise CRUNError("Creative job history cannot be read. Repair it before generating; existing task IDs must remain recoverable.") from None


def find(key: str) -> dict | None:
    with LOCK:
        record = _read().get(key)
        if record is None:
            return None
        if not isinstance(record, dict) or record.get("status") not in {"preflight", "submitting", "submitted", "completed", "blocked"}:
            raise CRUNError("Creative job history contains an invalid record. Inspect existing tasks before generating.")
        task_id = record.get("task_id", "")
        if record.get("status") in {"submitted", "completed"} and not task_id:
            raise CRUNError("A paid job record is missing its task ID. Inspect CRUN Logs and use Resume existing task; no replacement task was submitted.")
        if task_id and (not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", task_id)):
            raise CRUNError("Creative job history contains an invalid task ID.")
        return dict(record)


def save(key: str, record: dict) -> None:
    with submission_lock():
        jobs = _read()
        allowed = {"status", "task_id", "model", "estimated_credits", "created_at", "completed_at"}
        safe = {name: value for name, value in record.items() if name in allowed}
        safe.setdefault("created_at", int(time.time()))
        jobs[key] = safe
        # Completed mappings are also paid-submission tombstones. Evicting one
        # would let the same Take create another task after a restart.
        encoded = json.dumps({"version": 1, "jobs": jobs}, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
            raise CRUNError("Creative job history is full. Preserve its task IDs before archiving it; no new task was submitted.")
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".creative-jobs-", suffix=".tmp")
        temporary = Path(name)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def observe(callback):
    token = _OBSERVER.set(callback)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def submission_starting() -> None:
    callback = _OBSERVER.get()
    if callback:
        callback("submitting", "")


def submission_received(task_id: str) -> None:
    callback = _OBSERVER.get()
    if callback:
        callback("submitted", task_id)
