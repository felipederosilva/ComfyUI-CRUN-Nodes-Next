import inspect
import math
import unittest
from unittest.mock import patch

from crun.preflight import configuration_errors, validate_node_inputs


class PreflightTests(unittest.TestCase):
    def test_generate_zero_is_allowed_without_legacy_permission_checkboxes(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
            result = validate_node_inputs(
                object, crun_mode="generate", crun_allow_paid_generation=False,
                crun_max_credits=0, crun_allow_upload=False, first_frame=None,
            )
        self.assertIs(result, True)
        self.assertEqual(configuration_errors("generate", False, 0, has_native_media=True), [])

    def test_url_only_requests_do_not_require_native_upload_permission(self):
        self.assertEqual(configuration_errors("generate", True, 12, allow_upload=False), [])
        self.assertIs(validate_node_inputs(object, "generate", True, 12, False), True)
        self.assertEqual(configuration_errors("estimate", False, 0), [])

    def test_prepare_accepts_zero_budget_and_connected_images_without_upload(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Prepare stays offline")):
            self.assertEqual(configuration_errors("prepare", False, 0, has_native_media=True), [])
            self.assertIs(validate_node_inputs(object, first_frame=None, mask=None), True)

    def test_estimate_accepts_native_references_without_upload_checkbox(self):
        self.assertEqual(configuration_errors("estimate", False, 0, has_native_media=True), [])
        self.assertEqual(configuration_errors("estimate", False, 0, allow_upload=True, has_native_media=True), [])
        self.assertIs(validate_node_inputs(object, crun_mode="estimate", image=None), True)

    def test_all_native_sockets_accept_simple_action_flow(self):
        names = ("image", "first_frame", "last_frame", "reference_images", "mask",
                 "background_image", "face_image", *(f"image_{n}" for n in range(1, 9)))
        for name in names:
            with self.subTest(socket=name):
                result = validate_node_inputs(object, crun_mode="estimate", **{name: None})
                self.assertIs(result, True)

    def test_invalid_modes_and_optional_caps_are_rejected(self):
        for mode in (None, "run", [], True):
            with self.subTest(mode=mode):
                self.assertTrue(configuration_errors(mode, False, 0))
        for budget in (None, True, False, -1, "10", math.nan, math.inf, -math.inf, 10**1000):
            with self.subTest(budget_type=type(budget).__name__):
                errors = configuration_errors("generate", True, budget)
                self.assertTrue(any("crun_max_credits" in error for error in errors))
        for legacy_value in (False, True, None, "old value", 1):
            self.assertEqual(configuration_errors("generate", legacy_value, 0, allow_upload=legacy_value), [])

    def test_unknown_linked_controls_defer_only_at_queue_time(self):
        self.assertIs(validate_node_inputs(object, "generate", None, None, None, first_frame=None), True)
        self.assertIs(validate_node_inputs(object, None, False, 0, False, first_frame=None), True)
        errors = configuration_errors(None, None, None, allow_upload=None, has_native_media=True)
        self.assertEqual(len(errors), 2)
        self.assertIn("crun_mode", errors[0])
        self.assertIn("crun_max_credits", errors[1])

    def test_existing_positive_credit_cap_is_preserved(self):
        controls = {"crun_mode": "generate", "crun_allow_paid_generation": False,
                    "crun_max_credits": 100, "crun_allow_upload": False}
        original = controls.copy()
        self.assertIs(validate_node_inputs(object, **controls), True)
        self.assertEqual(configuration_errors("generate", False, controls["crun_max_credits"]), [])
        self.assertEqual(controls, original)
        self.assertEqual(controls["crun_max_credits"], 100)

    def test_explicit_signature_preserves_unrelated_comfy_validation(self):
        parameters = inspect.signature(validate_node_inputs).parameters
        self.assertNotIn("input_types", parameters)
        self.assertFalse(any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()))


if __name__ == "__main__":
    unittest.main()
