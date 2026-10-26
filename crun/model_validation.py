"""Documented cross-field/media conditions beyond imported JSON Schema.

Pure functions: no credentials, filesystem, uploads or provider requests. Source
contracts are CRUN's own Kling Omni, motion-control and Wan 2.7 descriptions;
KIE's limits are deliberately not used as CRUN defaults.
"""
from __future__ import annotations

import math


def _references(value):
    return value if isinstance(value, list) else []


def _present(value):
    return isinstance(value, str) and bool(value.strip())


def validate_model_inputs(entry: dict, inputs: dict) -> list[str]:
    """Return actionable, value-free validation messages for known contracts."""
    if not isinstance(inputs, dict):
        return ["input: expected an object."]
    model = entry.get("model")
    errors = []
    if model == "kling/v3-omni-r2v":
        images = _references(inputs.get("reference_images"))
        videos = _references(inputs.get("reference_videos"))
        if not images and not videos:
            errors.append("reference_images: provide at least one reference image or video.")
        if len(videos) > 1:
            errors.append("reference_videos: this model accepts at most one reference video.")
        if videos and inputs.get("reference_video_type") not in ("base_video", "feature_video"):
            errors.append("reference_video_type: choose base_video or feature_video for the connected video.")
        if not videos and inputs.get("aspect_ratio") == "auto":
            errors.append("aspect_ratio: auto requires a reference video; choose 1:1, 16:9 or 9:16 for images only.")
        if len(images) > (5 if videos else 7):
            errors.append("reference_images: use at most five images with video, or seven images without video.")
    elif model in {"kling/v2-6-motion-control", "kling/v3-motion-control"}:
        if len(_references(inputs.get("img_urls"))) != 1:
            errors.append("img_urls: connect exactly one character image.")
        if len(_references(inputs.get("video_urls"))) != 1:
            errors.append("video_urls: connect exactly one motion reference video.")
        if inputs.get("character_orientation", "image") not in ("image", "video"):
            errors.append("character_orientation: choose image or video orientation.")
    elif model == "wan/2-7-r2v":
        references = _references(inputs.get("reference_medias"))
        if not references:
            errors.append("reference_medias: provide at least one image or video reference.")
        has_video = False
        for index, reference in enumerate(references):
            if not isinstance(reference, dict):
                continue  # The schema reports the item's type independently.
            image, video = reference.get("reference_image"), reference.get("reference_video")
            if not _present(image) and not _present(video):
                errors.append(f"reference_medias[{index}]: each reference needs an image or video; voice alone is insufficient.")
            has_video = has_video or _present(video)
        duration = inputs.get("duration", 5)
        if has_video and isinstance(duration, (float, int)) and not isinstance(duration, bool) and duration > 10:
            errors.append("duration: use ten seconds or less when a reference video is included.")
    return errors


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _file_sizes(metadata):
    sizes = metadata.get("byte_counts")
    if isinstance(sizes, list):
        return [size for size in sizes if _number(size)]
    return [metadata["byte_count"]] if metadata.get("count", 1) == 1 and _number(metadata.get("byte_count")) else []


def validate_native_media(entry: dict, metadata: list[dict], inputs: dict | None = None) -> list[str]:
    """Validate measured local references against explicitly documented limits.

    Missing measurements are not fabricated. Encoding/adapters must establish
    media validity; these checks add model-specific restrictions to known data.
    Byte limits are per file, never the sum of an image batch.
    """
    errors = []
    model = entry.get("model")
    inputs = inputs or {}
    for item in metadata:
        if not isinstance(item, dict):
            continue
        wire, kind = item.get("wire_name"), item.get("kind")
        role = str(item.get("socket") or wire or "reference")
        if not role.replace("_", "").isalnum():
            role = "reference"
        low_size = high_size = min_duration = max_duration = max_bytes = None
        check_ratio = fps_range = None
        if model == "kling/v3-omni-r2v":
            if wire == "reference_images" and kind == "image":
                low_size, max_bytes, check_ratio = 300, 50 * 1024 * 1024, (0.4, 2.5)
            elif wire == "reference_videos" and kind == "video":
                low_size, high_size = 700, 2160
                min_duration, max_duration, max_bytes, fps_range = 3, 10, 200 * 1024 * 1024, (24, 60)
        elif model == "kling/v2-6-motion-control":
            if wire == "img_urls" and kind == "image":
                low_size, high_size, max_bytes, check_ratio = 340, 3850, 10 * 1024 * 1024, (0.4, 2.5)
            elif wire == "video_urls" and kind == "video":
                min_duration = 3
                max_duration = 10 if inputs.get("character_orientation", "image") == "image" else 30
                max_bytes = 100 * 1024 * 1024
        elif model == "wan/2-7-r2v":
            # Native nested-reference adapters can supply the actual leaf role.
            if wire == "reference_image" and kind == "image":
                low_size, high_size, max_bytes, check_ratio = 240, 8000, 20 * 1024 * 1024, (0.125, 8)
            elif wire == "reference_video" and kind == "video":
                low_size, high_size, min_duration, max_duration = 240, 4096, 1, 30
                max_bytes, check_ratio = 100 * 1024 * 1024, (0.125, 8)
        for dimension in ("width", "height"):
            value = item.get(dimension)
            if _number(value) and low_size is not None and value < low_size:
                errors.append(f"{role}: reference width and height are below this model's documented minimum.")
                break
            if _number(value) and high_size is not None and value > high_size:
                errors.append(f"{role}: reference width or height exceeds this model's documented maximum.")
                break
        width, height = item.get("width"), item.get("height")
        if check_ratio and _number(width) and _number(height) and height > 0 and not check_ratio[0] <= width / height <= check_ratio[1]:
            errors.append(f"{role}: reference aspect ratio is outside this model's documented limits.")
        duration = item.get("duration")
        if _number(duration) and min_duration is not None and not min_duration <= duration <= max_duration:
            errors.append(f"{role}: reference duration is outside this model's documented limits for the selected mode.")
        fps = item.get("frame_rate")
        if fps_range and _number(fps) and not fps_range[0] <= fps <= fps_range[1]:
            errors.append(f"{role}: reference frame rate is outside this model's documented limits.")
        if max_bytes is not None and any(size > max_bytes for size in _file_sizes(item)):
            errors.append(f"{role}: reference file exceeds this model's documented size limit.")
    return list(dict.fromkeys(errors))
