import inspect
import math
import unittest
from unittest.mock import patch

from crun.preflight import configuration_errors, validate_node_inputs


class PreflightTests(unittest.TestCase):
    def test_reported_workflow_identifies_budget_and_upload_together(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
            result = validate_node_inputs(
                object, crun_mode="generate", crun_allow_paid_generation=True,
                crun_max_credits=0, crun_allow_upload=False, first_frame=None,
            )
        self.assertIsInstance(result, str)
        self.assertIn("crun_max_credits", result)
        self.assertIn("positive user-approved", result)
        self.assertIn("crun_mode=estimate", result)
        self.assertIn("crun_allow_upload", result)
        self.assertIn("No provider request", result)

    def test_url_only_requests_do_not_require_native_upload_permission(self):
        self.assertEqual(configuration_errors("generate", True, 12, allow_upload=False), [])
        self.assertIs(validate_node_inputs(object, "generate", True, 12, False), True)
        self.assertEqual(configuration_errors("estimate", False, 0), [])

    def test_prepare_accepts_zero_budget_and_connected_images_without_upload(self):
        self.assertEqual(configuration_errors("prepare", False, 0, has_native_media=True), [])
        self.assertIs(validate_node_inputs(object, first_frame=None, mask=None), True)

    def test_estimate_requires_upload_permission_only_for_native_references(self):
        errors = configuration_errors("estimate", False, 0, has_native_media=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("crun_allow_upload", errors[0])
        self.assertEqual(configuration_errors("estimate", False, 0, allow_upload=True, has_native_media=True), [])

    def test_all_native_socket_names_are_detected_before_execution(self):
        names = ("image", "first_frame", "last_frame", "reference_images", "mask",
                 "background_image", "face_image", *(f"image_{n}" for n in range(1, 9)))
        for name in names:
            with self.subTest(socket=name):
                result = validate_node_inputs(object, crun_mode="estimate", **{name: None})
                self.assertIn("crun_allow_upload", result)

    def test_invalid_modes_booleans_and_budgets_are_rejected(self):
        for mode in (None, "run", [], True):
            with self.subTest(mode=mode):
                self.assertTrue(configuration_errors(mode, False, 0))
        for budget in (None, True, False, -1, "10", math.nan, math.inf, -math.inf, 10**1000):
            with self.subTest(budget_type=type(budget).__name__):
                errors = configuration_errors("generate", True, budget)
                self.assertTrue(any("crun_max_credits" in error for error in errors))
        self.assertTrue(configuration_errors("prepare", "yes", 0))
        self.assertTrue(configuration_errors("estimate", False, 0, allow_upload=1))

    def test_unknown_linked_controls_defer_only_at_queue_time(self):
        self.assertIs(validate_node_inputs(object, "generate", None, None, None, first_frame=None), True)
        self.assertIs(validate_node_inputs(object, None, False, 0, False, first_frame=None), True)
        self.assertTrue(configuration_errors("generate", None, None, allow_upload=None, has_native_media=True))

    def test_paid_permission_remains_required_and_not_automatically_enabled(self):
        errors = configuration_errors("generate", False, 12, allow_upload=True, has_native_media=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("not armed", errors[0])
        self.assertIn("crun_allow_paid_generation", errors[0])

    def test_explicit_signature_preserves_unrelated_comfy_validation(self):
        parameters = inspect.signature(validate_node_inputs).parameters
        self.assertNotIn("input_types", parameters)
        self.assertFalse(any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()))


if __name__ == "__main__":
    unittest.main()
