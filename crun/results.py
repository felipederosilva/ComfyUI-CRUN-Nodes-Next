"""Recover existing CRUN tasks into durable native Comfy media, never submit."""
from __future__ import annotations

import hashlib
import ipaddress
import math
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time
from urllib.parse import urlsplit

import requests

from .client import CRUNClient, CRUNError
from .effects import _https_url

MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_IMAGE_PIXELS = 64 * 1024 * 1024


def _interrupt() -> None:
    # The running Comfy host already loaded this module. Do not initialize its
    # GPU/runtime merely because an offline helper is inspected or tested.
    model_management = sys.modules.get("comfy.model_management")
    check = getattr(model_management, "throw_exception_if_processing_interrupted", None)
    if callable(check):
        check()


def wait_for_task(client, task_id: str, *, timeout_seconds: int = 1200,
                  poll_interval: float = 3) -> dict:
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", task_id):
        raise ValueError("Enter or connect a valid existing CRUN task ID.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 7200:
        raise ValueError("Task wait timeout must be between 0 and 7200 seconds.")
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or not math.isfinite(poll_interval) or not 1 <= poll_interval <= 30:
        raise ValueError("Polling interval must be between 1 and 30 seconds.")
    deadline = time.monotonic() + timeout_seconds
    while True:
        _interrupt()
        try:
            record = client.get_task(task_id)
        except CRUNError:
            raise CRUNError(f"Could not inspect task {task_id}. Keep this ID and retry result retrieval; no replacement generation was submitted.") from None
        if not isinstance(record, dict) or (record.get("task_id") is not None and record["task_id"] != task_id):
            raise CRUNError(f"CRUN returned mismatched information for task {task_id}. No replacement generation was submitted.")
        state = record.get("status")
        if state == "success":
            return record
        if state == "failed":
            raise CRUNError(f"Task {task_id} failed. Inspect the same task in CRUN Logs; no replacement generation was submitted.")
        if state not in {"pending", "running"}:
            raise CRUNError(f"Task {task_id} has an unsupported status. Keep this ID for recovery; no replacement generation was submitted.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CRUNError(f"Task {task_id} is still {state}. Result wait timed out; keep this ID and run Get Result again. No replacement generation was submitted.")
        time.sleep(min(poll_interval, remaining))


def _public_download_url(url: str) -> str:
    if not _https_url(url) or urlsplit(url).hostname == "crun-next.invalid":
        raise CRUNError("Result URL must be public HTTPS media, not a local placeholder.")
    host = urlsplit(url).hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Private destination")
    except (OSError, ValueError):
        raise CRUNError("Result media host could not be verified as a public destination.") from None
    return url


def _output_directory() -> Path:
    try:
        import folder_paths
        return Path(folder_paths.get_output_directory()) / "CRUNResults"
    except ImportError:
        from .settings import settings_path
        return settings_path().parent / "results"


def download_to_output(url: str, *, kind: str) -> Path:
    """Bounded streaming GET without account headers, redirects or retries."""
    if kind not in {"image", "video"}:
        raise ValueError("Choose image or video media.")
    url = _public_download_url(url)
    maximum = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
    directory = _output_directory()
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".crun-result-", suffix=".part")
    temporary = Path(name)
    digest = hashlib.sha256()
    size = 0
    suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"} if kind == "image" else {".mp4", ".mov", ".webm", ".mkv", ".avi"}
    suffix = Path(urlsplit(url).path).suffix.lower()
    suffix = suffix if suffix in suffixes else ".image" if kind == "image" else ".mp4"
    try:
        with os.fdopen(descriptor, "wb") as output, requests.Session() as transport:
            transport.trust_env = False
            with transport.get(url, headers={"Accept": "image/*" if kind == "image" else "video/*"}, stream=True, timeout=(10, 120), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise CRUNError("Result download failed. Retry retrieval of the same task; no generation was submitted.")
                length = response.headers.get("Content-Length")
                if length is not None:
                    try:
                        if not 0 <= int(length) <= maximum:
                            raise ValueError("Oversize")
                    except (ValueError, TypeError):
                        raise CRUNError("Result exceeds the supported download size or has an invalid length.") from None
                for chunk in response.iter_content(65536):
                    _interrupt()
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > maximum:
                        raise CRUNError("Result exceeds the supported download size.")
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
        if not size:
            raise CRUNError("CRUN returned empty result media.")
        destination = directory / f"crun-{digest.hexdigest()}{suffix}"
        os.replace(temporary, destination)
        return destination
    except requests.RequestException:
        raise CRUNError("Result download was interrupted. Keep the task ID and retry retrieval; no generation was submitted.") from None
    finally:
        temporary.unlink(missing_ok=True)


def image_from_file(path: Path):
    import warnings
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image pixel limit exceeded")
                image = ImageOps.exif_transpose(image).convert("RGB")
                array = np.asarray(image, dtype=np.float32) / 255.0
        return torch.from_numpy(array).unsqueeze(0)
    except Exception:
        raise CRUNError("Downloaded media could not be decoded as a supported image.") from None


def video_from_file(path: Path):
    try:
        from comfy_api.input_impl import VideoFromFile
        video = VideoFromFile(str(path))
        width, height = video.get_dimensions()
        if width < 1 or height < 1:
            raise ValueError("Empty video")
        return video
    except ImportError:
        raise CRUNError("Native VIDEO output requires a current ComfyUI runtime.") from None
    except Exception:
        raise CRUNError("Downloaded media could not be decoded as a supported video.") from None


def load_result(task_id: str, *, kind: str, result_index: int = 0,
                timeout_seconds: int = 1200, poll_interval: float = 3):
    if kind not in {"image", "video"}:
        raise ValueError("Choose image or video media.")
    if isinstance(result_index, bool) or not isinstance(result_index, int) or not 0 <= result_index < 100:
        raise ValueError("Result index must be between 0 and 99.")
    try:
        record = wait_for_task(CRUNClient(), task_id, timeout_seconds=timeout_seconds, poll_interval=poll_interval)
        result = record.get("result")
        urls = result.get("media_urls") if isinstance(result, dict) else None
        if not isinstance(urls, list) or result_index >= len(urls) or not isinstance(urls[result_index], str):
            raise CRUNError("Successful task did not contain the selected media result.")
        credits = record.get("credits")
        if credits is None:
            credits = -1.0
        elif isinstance(credits, bool) or not isinstance(credits, (int, float)) or not math.isfinite(credits) or credits < 0:
            raise CRUNError("Task has an invalid final credit receipt.")
        url = urls[result_index]
        path = download_to_output(url, kind=kind)
        media = image_from_file(path) if kind == "image" else video_from_file(path)
        return media, url, float(credits), task_id
    except CRUNError as error:
        if isinstance(task_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", task_id) and task_id not in str(error):
            raise CRUNError(f"Task {task_id}: {error}") from None
        raise
    except (OSError, ImportError):
        raise CRUNError(f"Task {task_id}: result could not be loaded or saved locally. Keep this ID and retry retrieval; no replacement generation was submitted.") from None

