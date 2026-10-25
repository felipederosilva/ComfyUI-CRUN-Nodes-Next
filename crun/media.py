"""Local native Comfy image preparation and explicitly allowed CRUN uploads.

No imports, shape inspection or PNG encoding contact a provider. Upload receipts
are cached only in memory for 30 minutes, scoped to both content and credential.
The returned provider URLs are temporary; this is not durable asset storage.
"""
from __future__ import annotations

import hashlib
import io
import threading
import time
from typing import Any

from .effects import _https_url

MAX_IMAGES = 16
MAX_PIXELS = 64 * 1024 * 1024
MAX_DIMENSION = 16384
MAX_IMAGE_BYTES = 20 * 1024 * 1024
_CACHE_SECONDS = 30 * 60
_UPLOAD_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_CACHE_LOCK = threading.RLock()


def _array(value: Any, *, mask: bool = False, max_images: int = MAX_IMAGES,
           max_pixels: int = MAX_PIXELS, max_dimension: int = MAX_DIMENSION):
    import numpy as np

    if not isinstance(max_images, int) or isinstance(max_images, bool) or not 1 <= max_images <= 64:
        raise ValueError("Image batch limit must be between 1 and 64.")
    shape = tuple(getattr(value, "shape", ()))
    valid_dims = (2, 3) if mask else (3, 4)
    if len(shape) not in valid_dims or any(not isinstance(n, int) or n < 1 for n in shape):
        raise ValueError("Expected a Comfy MASK shaped [B,H,W] or [H,W]." if mask else "Expected a Comfy IMAGE shaped [B,H,W,C] or [H,W,C].")
    if mask:
        batch, height, width = (1, *shape) if len(shape) == 2 else shape
        channels = 1
    else:
        batch, height, width, channels = (1, *shape) if len(shape) == 3 else shape
    if batch > max_images or height > max_dimension or width > max_dimension or height * width > max_pixels:
        raise ValueError("Native media exceeds the configured image-count or pixel limit.")
    if channels not in (1, 3, 4):
        raise ValueError("Native IMAGE must have 1, 3 or 4 channels.")
    if isinstance(value, np.ndarray):
        array = value
    else:
        try:
            import torch
        except ImportError:
            raise ValueError("Native tensor inputs require ComfyUI's PyTorch runtime.") from None
        if not isinstance(value, torch.Tensor) or not value.is_floating_point():
            raise ValueError("Expected a floating point Comfy IMAGE or MASK tensor.")
        array = value.detach().to(device="cpu", dtype=torch.float32).numpy()
    if not np.issubdtype(array.dtype, np.floating):
        raise ValueError("Native media values must be floating point values from 0 to 1.")
    if not np.isfinite(array).all() or np.any(array < 0) or np.any(array > 1):
        raise ValueError("Native media contains non-finite values or values outside 0 to 1. Normalize it before uploading.")
    if mask:
        if array.ndim == 2:
            array = array[None, ...]
        return array[..., None]
    return array[None, ...] if array.ndim == 3 else array


def image_batch_to_pngs(image: Any, *, max_images: int = MAX_IMAGES,
                        max_pixels: int = MAX_PIXELS, max_dimension: int = MAX_DIMENSION,
                        max_bytes: int = MAX_IMAGE_BYTES) -> list[bytes]:
    """Encode every NHWC image before any upload, retaining batch order."""
    import numpy as np
    from PIL import Image

    array = _array(image, max_images=max_images, max_pixels=max_pixels, max_dimension=max_dimension)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("Image byte limit must be positive.")
    result = []
    for frame in array:
        pixels = (frame * 255.0 + .5).astype(np.uint8)
        if pixels.shape[-1] == 1:
            pixels = pixels[..., 0]
        buffer = io.BytesIO()
        Image.fromarray(pixels).save(buffer, format="PNG")
        data = buffer.getvalue()
        if len(data) > max_bytes:
            raise ValueError("An encoded native image exceeds the configured upload size limit.")
        result.append(data)
    return result


def describe_image_batch(image: Any, **limits) -> dict:
    """Offline metadata plus reserved-domain placeholders, never tensor JSON."""
    pngs = image_batch_to_pngs(image, **limits)
    array = _array(image, **{key: value for key, value in limits.items() if key != "max_bytes"})
    hashes = [hashlib.sha256(data).hexdigest() for data in pngs]
    return {"kind": "comfy_image", "count": len(pngs), "height": int(array.shape[1]),
            "width": int(array.shape[2]), "channels": int(array.shape[3]), "sha256": hashes,
            "upload_required": True,
            "placeholders": [f"https://crun-next.invalid/local/{digest}.png" for digest in hashes]}


def mask_batch_to_images(mask: Any, **limits):
    """Keep white-as-affected MASK semantics; never invert or resize silently."""
    return _array(mask, mask=True, **limits)


def describe_mask_batch(mask: Any, **limits) -> dict:
    image_limits = {key: value for key, value in limits.items() if key != "max_bytes"}
    result = describe_image_batch(mask_batch_to_images(mask, **image_limits), **limits)
    result.update(kind="comfy_mask", mask_semantics="white is affected; no inversion")
    return result


def upload_pngs(client: Any, pngs: list[bytes], *, allow_upload: bool = False) -> list[str]:
    """Upload an already validated PNG batch only with explicit permission.

    All byte limits are checked before the first network request. No upload is
    automatically retried. Successful earlier uploads may be reused if a later
    item fails; generation itself is never initiated by this helper.
    """
    if allow_upload is not True:
        raise ValueError("Native media upload is not allowed. Enable uploads explicitly after reviewing the images.")
    if not isinstance(pngs, list) or not pngs or len(pngs) > 64 or any(not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > MAX_IMAGE_BYTES for data in pngs):
        raise ValueError("Expected a bounded batch of encoded PNG images.")
    credential = getattr(client, "_api_key", None)
    scope = hashlib.sha256(credential.encode()).hexdigest() if isinstance(credential, str) else f"client:{id(client)}"
    urls = []
    with _CACHE_LOCK:
        now = time.monotonic()
        for key, receipt in list(_UPLOAD_CACHE.items()):
            if receipt[0] <= now:
                _UPLOAD_CACHE.pop(key, None)
        for data in pngs:
            cache_key = (scope, hashlib.sha256(data).hexdigest())
            cached = _UPLOAD_CACHE.get(cache_key)
            if cached and cached[0] > time.monotonic():
                urls.append(cached[1])
                continue
            url = client.upload_bytes(data, mime_type="image/png", extension=".png")
            if not _https_url(url):
                raise ValueError("CRUN did not return a public HTTPS upload URL.")
            _UPLOAD_CACHE[cache_key] = (time.monotonic() + _CACHE_SECONDS, url)
            urls.append(url)
    return urls


def upload_images(client: Any, image: Any, *, allow_upload: bool = False, **limits) -> list[str]:
    if allow_upload is not True:
        raise ValueError("Native media upload is not allowed. Enable uploads explicitly first.")
    return upload_pngs(client, image_batch_to_pngs(image, **limits), allow_upload=True)
