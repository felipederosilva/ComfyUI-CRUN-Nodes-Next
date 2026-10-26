"""Complete native-media workflow built on CRUN's single-submit transport."""
from __future__ import annotations

import json
import math
import re
import time

from . import jobs
from .client import CRUNClient, CRUNError


def blocked_media():
    try:
        from comfy_execution.graph import ExecutionBlocker
        return ExecutionBlocker(None)
    except ImportError:
        return None  # Metadata inspection outside Comfy cannot execute a sink.


def _number(value) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else -1.0


def _read_receipt(response: dict) -> dict:
    receipt = json.loads(response["result"][0])
    if receipt.get("mode") == "prepare":
        receipt["validation_errors"] = list(receipt.get("errors") or [])
    return receipt


def run_creative(delegate, inputs: dict, kind: str, *, take: int = 0, resume_task_id: str = "", result_index: int = 0,
                 timeout_seconds: int = 1200, poll_interval: float = 3) -> dict:
    if isinstance(take, bool) or not isinstance(take, int) or not 0 <= take <= 2147483647:
        raise ValueError("Take must be a nonnegative whole number.")
    if not isinstance(resume_task_id, str) or resume_task_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", resume_task_id):
        raise ValueError("Enter a valid existing task ID to resume.")
    if isinstance(result_index, bool) or not isinstance(result_index, int) or not 0 <= result_index < 100:
        raise ValueError("Result index must be between 0 and 99.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 7200:
        raise ValueError("Wait timeout must be between 0 and 7200 seconds.")
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or not math.isfinite(poll_interval) or not 1 <= poll_interval <= 30:
        raise ValueError("Polling interval must be between 1 and 30 seconds.")
    mode = inputs.get("crun_mode", "prepare")
    if mode not in {"prepare", "estimate", "generate"}:
        raise ValueError("Select Prepare, Estimate or Generate.")
    # Explicit recovery never requires old prompts or reference files, and never
    # uploads, quotes or creates a task. Prepare remains fully offline.
    if resume_task_id and mode != "prepare":
        receipt = {"mode": mode, "status": "resumed", "task_id": resume_task_id, "credits": -1,
                   "credit_limit": inputs.get("crun_max_credits", 0), "errors": [], "warnings": []}
        return _complete(receipt, kind, result_index, timeout_seconds, poll_interval)
    if mode != "generate":
        return _pack(_read_receipt(delegate(**inputs)), kind)

    prepared_inputs = {**inputs, "crun_mode": "prepare"}
    draft = _read_receipt(delegate(**prepared_inputs))
    if draft.get("errors"):
        draft["mode"] = mode
        draft["status"] = "failed"
        return _pack(draft, kind)
    key = jobs.request_key(draft.get("payload", {}), take)
    with jobs.submission_lock():
        saved = jobs.find(key)
        if saved and saved.get("task_id"):
            receipt = {**draft, "mode": mode, "status": "resumed", "task_id": saved["task_id"],
                       "credits": saved.get("estimated_credits", -1), "warnings": ["Reusing this take's existing task. Increase Take only to intentionally generate a new result."]}
        elif saved and saved.get("status") == "submitting":
            receipt = {**draft, "mode": mode, "status": "failed", "errors": [
                "The previous submission outcome is unknown. Inspect CRUN Logs and enter its task ID under Advanced to resume. No replacement task was submitted."]}
            return _pack(receipt, kind)
        else:
            state = {"status": "preflight", "model": draft.get("model"), "task_id": "", "created_at": int(time.time())}
            jobs.save(key, state)

            def observe(event, task_id):
                state["status"] = event
                if task_id:
                    state["task_id"] = task_id
                jobs.save(key, state)

            try:
                with jobs.observe(observe):
                    receipt = _read_receipt(delegate(**inputs))
            except Exception:
                # A known task ID remains usable even if a local journal write
                # failed. An ambiguous submission must never be retried here.
                if state.get("task_id"):
                    receipt = {**draft, "mode": mode, "status": "submitted", "task_id": state["task_id"],
                               "warnings": ["Task accepted; local receipt update failed. Keep this task ID."]}
                elif state["status"] == "submitting":
                    receipt = {**draft, "mode": mode, "status": "failed", "errors": [
                        "Submission outcome is unknown. Inspect CRUN Logs before retrying; no automatic replacement was submitted."]}
                    return _pack(receipt, kind)
                else:
                    state["status"] = "blocked"
                    jobs.save(key, state)
                    raise
            if not receipt.get("task_id"):
                state["status"] = "blocked"
                jobs.save(key, state)
                return _pack(receipt, kind)
            state.update(status="submitted", task_id=receipt["task_id"], estimated_credits=receipt.get("credits", -1))
            try:
                jobs.save(key, state)
            except CRUNError:
                receipt.setdefault("warnings", []).append("Task accepted; keep its ID because the local receipt update failed.")
    completed = _complete(receipt, kind, result_index, timeout_seconds, poll_interval)
    if completed["receipt"].get("status") in {"completed", "resumed"}:
        try:
            state = jobs.find(key) or {}
            state.update(status="completed", task_id=receipt["task_id"], completed_at=int(time.time()), estimated_credits=receipt.get("credits", -1))
            jobs.save(key, state)
        except CRUNError:
            pass  # The submitted record already retains the recoverable ID.
    return completed


def _complete(receipt, kind, index, timeout, interval):
    from .results import load_result_details
    task_id = receipt["task_id"]
    print(f"[CRUN Next] Loading task {task_id}; the same take will not submit a replacement.")
    try:
        details = load_result_details(task_id, kind=kind, result_index=index, timeout_seconds=timeout, poll_interval=interval)
    except CRUNError as error:
        receipt.update(status="failed", errors=[str(error)])
        return _pack(receipt, kind)
    receipt.update(status="resumed" if receipt.get("status") == "resumed" else "completed", actual_credits=details["actual_credits"], credit_state="actual",
                   local_path=details["local_path"], url=details["url"], errors=[])
    try:
        receipt["credits_left"] = CRUNClient().get_balance()
        receipt["balance_checked_at"] = int(time.time())
    except Exception:
        receipt["credits_left"] = -1
        receipt.setdefault("warnings", []).append("Media completed; remaining balance could not be refreshed.")
    print(f"[CRUN Next] Task {task_id} completed. Actual credits: {_number(receipt.get('actual_credits')):g}; remaining balance: {_number(receipt.get('credits_left')):g}.")
    return _pack(receipt, kind, details)


def _pack(receipt: dict, kind: str, details: dict | None = None) -> dict:
    media = details["media"] if details else blocked_media()
    common = (receipt.get("url", ""), str(receipt.get("task_id") or ""), _number(receipt.get("credits")),
              _number(receipt.get("actual_credits")), _number(receipt.get("credits_left")),
              json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))
    outputs = (media, details["mask"] if details else blocked_media(), *common) if kind == "image" else (media, *common)
    return {"ui": {"text": [common[-1]]}, "result": outputs, "receipt": receipt}
