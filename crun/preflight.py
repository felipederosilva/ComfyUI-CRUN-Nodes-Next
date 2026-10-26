"""Pure configuration checks shared by Comfy queue validation and execution.

No settings, credentials, media encoding or provider client is touched here.
The selected action expresses intent: Prepare is offline; Estimate/Generate
upload references as required, and Generate submits a paid task. Legacy
permission arguments remain accepted for existing workflows. A zero credit
limit disables the optional cap; positive limits are preserved and enforced.
"""
from __future__ import annotations

import math


_MISSING = object()
_MODES = ("prepare", "estimate", "generate")


def configuration_errors(mode, allow_paid_generation, max_credits, *,
                         allow_upload=False, has_native_media=False,
                         defer_unknown=False) -> list[str]:
    """Validate the action and optional cap without requesting or spending."""
    errors = []
    mode_unknown = mode is None and defer_unknown
    if not mode_unknown and mode not in _MODES:
        errors.append("crun_mode must be prepare, estimate or generate.")

    budget_unknown = max_credits is None and defer_unknown
    budget_valid = isinstance(max_credits, (int, float)) and not isinstance(max_credits, bool)
    if budget_valid:
        try:
            budget_valid = math.isfinite(max_credits) and max_credits >= 0
        except (OverflowError, ValueError):
            budget_valid = False
    if not budget_unknown and not budget_valid:
        errors.append("crun_max_credits must be a finite, nonnegative number. Set 0 for no optional cap, or a positive limit you choose.")
    return errors


def validate_node_inputs(cls, crun_mode="prepare", crun_allow_paid_generation=False,
                         crun_max_credits=0.0, crun_allow_upload=False,
                         image=_MISSING, first_frame=_MISSING, last_frame=_MISSING,
                         reference_images=_MISSING, mask=_MISSING,
                         background_image=_MISSING, face_image=_MISSING,
                         image_1=_MISSING, image_2=_MISSING, image_3=_MISSING,
                         image_4=_MISSING, image_5=_MISSING, image_6=_MISSING,
                         image_7=_MISSING, image_8=_MISSING):
    """Comfy VALIDATE_INPUTS hook with an intentionally explicit signature.

    A linked image is None before upstream execution; an absent socket retains
    its sentinel. Do not add **kwargs or input_types: either would bypass parts
    of Comfy's default widget/link validation beyond these named controls.
    """
    native = (image, first_frame, last_frame, reference_images, mask,
              background_image, face_image, image_1, image_2, image_3,
              image_4, image_5, image_6, image_7, image_8)
    errors = configuration_errors(
        crun_mode, crun_allow_paid_generation, crun_max_credits,
        allow_upload=crun_allow_upload,
        has_native_media=any(value is not _MISSING for value in native),
        defer_unknown=True,
    )
    if not errors:
        return True
    return "CRUN configuration is not ready: " + " ".join(errors) + " No provider request has been made."
