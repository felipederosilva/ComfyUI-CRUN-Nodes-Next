"""Pure configuration checks shared by Comfy queue validation and execution.

No settings, credentials, media encoding or provider client is touched here.
Unknown linked controls are deferred only during queue validation; execution
must call the same checks with the actual values and defer_unknown=False.
"""
from __future__ import annotations

import math


_MISSING = object()
_MODES = ("prepare", "estimate", "generate")


def configuration_errors(mode, allow_paid_generation, max_credits, *,
                         allow_upload=False, has_native_media=False,
                         defer_unknown=False) -> list[str]:
    """Describe missing user approvals without choosing a budget or spending."""
    errors = []
    mode_unknown = mode is None and defer_unknown
    if not mode_unknown and mode not in _MODES:
        errors.append("crun_mode must be prepare, estimate or generate.")

    paid_unknown = allow_paid_generation is None and defer_unknown
    if not paid_unknown and not isinstance(allow_paid_generation, bool):
        errors.append("crun_allow_paid_generation must be true or false.")
    upload_unknown = allow_upload is None and defer_unknown
    if not upload_unknown and not isinstance(allow_upload, bool):
        errors.append("crun_allow_upload must be true or false.")

    budget_unknown = max_credits is None and defer_unknown
    budget_valid = isinstance(max_credits, (int, float)) and not isinstance(max_credits, bool)
    if budget_valid:
        try:
            budget_valid = math.isfinite(max_credits) and max_credits >= 0
        except (OverflowError, ValueError):
            budget_valid = False
    if not budget_unknown and not budget_valid:
        errors.append("crun_max_credits must be a finite, nonnegative number. Generating requires a positive user-approved limit.")

    if mode == "generate":
        if allow_paid_generation is False:
            errors.append("Paid generation is not armed. Enable crun_allow_paid_generation only after reviewing the estimate.")
        if budget_valid and max_credits == 0:
            errors.append("Set crun_max_credits to a positive user-approved estimated-credit limit before generating; zero blocks generation. Use crun_mode=estimate first to review the quote.")

    if mode in ("estimate", "generate") and has_native_media and allow_upload is False:
        errors.append("Enable crun_allow_upload to allow the connected images or masks to be sent to CRUN. Estimating native references also requires this upload permission; prepare stays offline.")
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
