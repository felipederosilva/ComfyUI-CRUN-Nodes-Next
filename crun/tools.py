"""Curated CRUN AI Tools research index, not executable generation nodes."""

from __future__ import annotations

from copy import deepcopy


_TOOLS = (
    ("image-upscale", "Image Upscale", "Image / Enhance", "Enlarge and enhance an image with model-specific scale and cleanup controls."),
    ("image-upscale-pro", "Image Upscale Pro", "Image / Enhance", "Advanced image restoration and enlargement; parameters await integration validation."),
    ("image-expand", "Image Expand", "Image / Reframe", "Outpaint a canvas or extend selected sides to prepare alternate compositions."),
    ("image-background-remove", "Background Remove", "Image / Cutout", "Create a subject cutout from an image for compositing workflows."),
    ("image-inpaint", "Image Inpaint", "Image / Repair", "Repair a selected mask or rectangle rather than regenerating the whole image."),
    ("image-colorization", "Image Colorization", "Image / Restore", "Add color to monochrome images with a dedicated restoration operation."),
    ("image-background-regeneration", "Background Regeneration", "Image / Composite", "Replace a scene background using a description, color, or reference image."),
    ("image-headshot", "Headshot", "Image / Portrait", "Prepare a professional-looking portrait using an authorized subject reference."),
    ("video-enhance", "Video Enhance", "Video / Enhance", "Enhance a clip with model-specific quality, resolution, and frame-rate controls."),
)


def list_tools() -> list[dict[str, str]]:
    """Return fresh planned-feature cards; none of these cards executes a tool.

    Entries were discovered in CRUN's published docs index on 2026-10-25. This
    curated index is not a live entitlement/catalog query and may become stale.
    Watermark-removal services are deliberately not prioritized; future adapters
    must require users to hold rights to the media and intended modification.
    """
    return deepcopy([
        {
            "id": identifier,
            "name": name,
            "category": category,
            "description": description,
            "documentation_url": f"https://docs.crun.ai/ai-tools/{identifier}",
            "status": "planned",
        }
        for identifier, name, category, description in _TOOLS
    ])
