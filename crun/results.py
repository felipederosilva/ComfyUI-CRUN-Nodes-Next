"""Recover existing CRUN tasks into durable native Comfy media, never submit."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

import requests

from .client import CRUNClient, CRUNError
from .effects import _https_url
from .settings import SettingsError, get_api_key, settings_path

MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_AUDIO_BYTES = 256 * 1024 * 1024
MAX_AUDIO_DECODED_BYTES = 256 * 1024 * 1024
MAX_AUDIO_SECONDS = 3600
MAX_IMAGE_PIXELS = 64 * 1024 * 1024
_CACHE_LOCK = threading.RLock()
_KINDS = {"image", "video", "audio"}


def _validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", task_id):
        raise ValueError("Enter or connect a valid existing CRUN task ID.")


def _validate_wait_options(timeout_seconds, poll_interval) -> None:
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 7200:
        raise ValueError("Task wait timeout must be between 0 and 7200 seconds.")
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or not math.isfinite(poll_interval) or not 1 <= poll_interval <= 30:
        raise ValueError("Polling interval must be between 1 and 30 seconds.")


def _interrupt() -> None:
    # The running Comfy host already loaded this module. Do not initialize its
    # GPU/runtime merely because an offline helper is inspected or tested.
    model_management = sys.modules.get("comfy.model_management")
    check = getattr(model_management, "throw_exception_if_processing_interrupted", None)
    if callable(check):
        check()


def wait_for_task(client, task_id: str, *, timeout_seconds: int = 1200,
                  poll_interval: float = 3) -> dict:
    _validate_task_id(task_id)
    _validate_wait_options(timeout_seconds, poll_interval)
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
    if kind not in _KINDS:
        raise ValueError("Choose image, video or audio media.")
    url = _public_download_url(url)
    maximum = {"image": MAX_IMAGE_BYTES, "video": MAX_VIDEO_BYTES, "audio": MAX_AUDIO_BYTES}[kind]
    directory = _output_directory()
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".crun-result-", suffix=".part")
    temporary = Path(name)
    digest = hashlib.sha256()
    size = 0
    suffixes = {"image": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"},
                "video": {".mp4", ".mov", ".webm", ".mkv", ".avi"},
                "audio": {".wav", ".mp3", ".flac", ".ogg", ".opus", ".aac", ".m4a", ".aiff", ".aif"}}[kind]
    suffix = Path(urlsplit(url).path).suffix.lower()
    suffix = suffix if suffix in suffixes else {"image": ".image", "video": ".mp4", "audio": ".audio"}[kind]
    try:
        with os.fdopen(descriptor, "wb") as output, requests.Session() as transport:
            transport.trust_env = False
            with transport.get(url, headers={"Accept": f"{kind}/*"}, stream=True, timeout=(10, 120), allow_redirects=False) as response:
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
    """Compatibility IMAGE adapter; richer creative nodes also expose its mask."""
    return image_with_mask_from_file(path)[0]


def image_with_mask_from_file(path: Path):
    """Decode an image and Comfy MASK (one minus alpha), keeping transparency."""
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
                image = ImageOps.exif_transpose(image)
                rgba = image.convert("RGBA")
                alpha = np.asarray(rgba.getchannel("A"), dtype=np.float32) / 255.0
                array = np.asarray(rgba.convert("RGB"), dtype=np.float32) / 255.0
        return torch.from_numpy(array).unsqueeze(0), torch.from_numpy(1.0 - alpha).unsqueeze(0)
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


def audio_from_file(path: Path):
    """Decode bounded audio to Comfy's waveform[B,C,T]/sample_rate contract."""
    try:
        import av
        import numpy as np
        import torch

        chunks, decoded_bytes, samples = [], 0, 0
        sample_rate, channels, resampler = None, None, None

        def retain(frames):
            nonlocal decoded_bytes, samples
            for frame in frames:
                array = frame.to_ndarray()
                if array.ndim != 2 or array.shape[0] != channels or not np.isfinite(array).all():
                    raise ValueError("Unsupported audio shape")
                decoded_bytes += array.size * 4
                samples += array.shape[1]
                if decoded_bytes > MAX_AUDIO_DECODED_BYTES or samples > sample_rate * MAX_AUDIO_SECONDS:
                    raise ValueError("Decoded audio exceeds limit")
                chunks.append(torch.from_numpy(array.copy()).float())

        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise ValueError("No audio stream")
            stream = container.streams.audio[0]
            for frame in container.decode(stream):
                _interrupt()
                if resampler is None:
                    sample_rate = int(frame.sample_rate)
                    channels = len(frame.layout.channels)
                    if not 1 <= sample_rate <= 384000 or not 1 <= channels <= 8:
                        raise ValueError("Unsupported audio configuration")
                    resampler = av.AudioResampler(format="fltp", layout=frame.layout.name, rate=sample_rate)
                retain(resampler.resample(frame))
            if resampler is not None:
                retain(resampler.resample(None))
        if not chunks or samples < 1:
            raise ValueError("No audio samples")
        return {"waveform": torch.cat(chunks, dim=1).unsqueeze(0), "sample_rate": sample_rate}
    except ImportError:
        raise CRUNError("Native AUDIO output requires PyAV and PyTorch from the ComfyUI runtime.") from None
    except Exception as error:
        interrupted = getattr(sys.modules.get("comfy.model_management"), "InterruptProcessingException", None)
        if isinstance(interrupted, type) and isinstance(error, interrupted):
            raise
        raise CRUNError("Downloaded media could not be decoded as supported audio within the size/duration limits.") from None


def _index_path() -> Path | None:
    """No credentials or signed URLs are written into the completed-asset index."""
    try:
        key = get_api_key()
        if not key:
            return None
        scope = hashlib.sha256(("crun-completed-results-v1\0" + key).encode("utf-8")).hexdigest()
        return settings_path().parent / "completed-results" / (scope + ".json")
    except (SettingsError, OSError):
        return None


def _index_key(task_id: str, kind: str, result_index: int) -> str:
    return hashlib.sha256(json.dumps([task_id, kind, result_index], separators=(",", ":")).encode()).hexdigest()


def _read_index(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1 or not isinstance(value.get("entries"), dict):
            return {}
        return value["entries"]
    except (OSError, ValueError, AttributeError):
        return {}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            _interrupt()
            digest.update(chunk)
    return digest.hexdigest()


def _safe_asset(entry: dict, kind: str) -> Path | None:
    name, digest = entry.get("file_name"), entry.get("sha256")
    if not isinstance(name, str) or not re.fullmatch(r"crun-[a-f0-9]{64}\.[a-z0-9]{1,8}", name):
        return None
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        return None
    if name[5:69] != digest:
        return None
    directory = _output_directory().resolve()
    path = directory / name
    try:
        maximum = {"image": MAX_IMAGE_BYTES, "video": MAX_VIDEO_BYTES, "audio": MAX_AUDIO_BYTES}[kind]
        if path.is_symlink() or path.resolve().parent != directory or not path.is_file() or not 0 < path.stat().st_size <= maximum:
            return None
        if path.stat().st_size != entry.get("bytes") or _file_hash(path) != digest:
            return None
        return path
    except OSError:
        return None


def _cached_asset(task_id: str, kind: str, result_index: int):
    index = _index_path()
    if index is None:
        return None
    with _CACHE_LOCK:
        entry = _read_index(index).get(_index_key(task_id, kind, result_index))
    if not isinstance(entry, dict) or entry.get("task_id") != task_id or entry.get("kind") != kind or entry.get("result_index") != result_index:
        return None
    credits = entry.get("actual_credits")
    if isinstance(credits, bool) or not isinstance(credits, (int, float)) or not math.isfinite(credits) or credits < 0 and credits != -1:
        return None
    path = _safe_asset(entry, kind)
    return (path, float(credits)) if path is not None else None


def _remember_asset(task_id: str, kind: str, result_index: int, path: Path, credits: float) -> None:
    index = _index_path()
    if index is None:
        return
    try:
        path = Path(path)
        if not path.is_file() or path.is_symlink() or path.resolve().parent != _output_directory().resolve():
            return
        digest = _file_hash(path)
        entry = {"task_id": task_id, "kind": kind, "result_index": result_index,
                 "file_name": path.name, "sha256": digest, "bytes": path.stat().st_size,
                 "actual_credits": credits, "saved_at": int(time.time())}
        if _safe_asset(entry, kind) is None:
            return
        with _CACHE_LOCK:
            entries = _read_index(index)
            entries[_index_key(task_id, kind, result_index)] = entry
            entries = dict(sorted(entries.items(), key=lambda pair: pair[1].get("saved_at", 0) if isinstance(pair[1], dict) else 0)[-2000:])
            index.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(dir=index.parent, prefix=".completed-", suffix=".tmp")
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    os.chmod(temporary, 0o600)
                    json.dump({"schema_version": 1, "entries": entries}, stream, allow_nan=False)
                os.replace(temporary, index)
            finally:
                temporary.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        # A provider task already succeeded; cache failure must not invite another job.
        print(f"[CRUN Next] Task {task_id}: media loaded, but its local reuse index could not be saved. Keep the task ID.")


def _decoded(path: Path, kind: str, include_mask: bool):
    if kind == "image":
        if include_mask:
            return image_with_mask_from_file(path)
        return image_from_file(path), None
    return (video_from_file(path) if kind == "video" else audio_from_file(path)), None


def _load_result_details(task_id: str, *, kind: str, result_index: int,
                         timeout_seconds: int, poll_interval: float, include_mask: bool):
    if kind not in _KINDS:
        raise ValueError("Choose image, video or audio media.")
    _validate_task_id(task_id)
    _validate_wait_options(timeout_seconds, poll_interval)
    if isinstance(result_index, bool) or not isinstance(result_index, int) or not 0 <= result_index < 100:
        raise ValueError("Result index must be between 0 and 99.")
    try:
        cached = _cached_asset(task_id, kind, result_index)
        if cached is not None:
            path, credits = cached
            media, mask = _decoded(path, kind, include_mask)
            print(f"[CRUN Next] Task {task_id}: reusing verified local {kind}; no provider request.")
            return {"media": media, "mask": mask, "url": "", "actual_credits": credits,
                    "task_id": task_id, "local_path": str(path)}
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
        media, mask = _decoded(path, kind, include_mask)
        _remember_asset(task_id, kind, result_index, path, float(credits))
        return {"media": media, "mask": mask, "url": url, "actual_credits": float(credits),
                "task_id": task_id, "local_path": str(path)}
    except CRUNError as error:
        if isinstance(task_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", task_id) and task_id not in str(error):
            raise CRUNError(f"Task {task_id}: {error}") from None
        raise
    except (OSError, ImportError):
        raise CRUNError(f"Task {task_id}: result could not be loaded or saved locally. Keep this ID and retry retrieval; no replacement generation was submitted.") from None


def load_result_details(task_id: str, *, kind: str, result_index: int = 0,
                        timeout_seconds: int = 1200, poll_interval: float = 3) -> dict:
    """Retrieve or reuse native media; IMAGE additionally includes its alpha mask.

    A locally reused result has an empty URL because expiring/signed provider
    URLs are deliberately not persisted. local_path and native media remain usable.
    """
    return _load_result_details(task_id, kind=kind, result_index=result_index,
                                timeout_seconds=timeout_seconds, poll_interval=poll_interval,
                                include_mask=True)


def load_result(task_id: str, *, kind: str, result_index: int = 0,
                timeout_seconds: int = 1200, poll_interval: float = 3):
    """Legacy tuple positions remain unchanged for existing saved workflows."""
    details = _load_result_details(task_id, kind=kind, result_index=result_index,
                                   timeout_seconds=timeout_seconds, poll_interval=poll_interval,
                                   include_mask=False)
    return details["media"], details["url"], details["actual_credits"], details["task_id"]

