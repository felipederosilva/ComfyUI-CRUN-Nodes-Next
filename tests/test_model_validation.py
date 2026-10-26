import unittest
from unittest.mock import patch

from crun.model_validation import validate_model_inputs, validate_native_media


OMNI = {"model": "kling/v3-omni-r2v"}
MOTION = {"model": "kling/v2-6-motion-control"}
WAN = {"model": "wan/2-7-r2v"}
IMAGE = "https://example.com/reference.png"
VIDEO = "https://example.com/motion.mp4"


class ModelValidationTests(unittest.TestCase):
    def test_omni_missing_references_and_image_only_auto_are_rejected(self):
        self.assertTrue(validate_model_inputs(OMNI, {"prompt": "Fictional"}))
        errors = validate_model_inputs(OMNI, {"reference_images": [IMAGE], "aspect_ratio": "auto"})
        self.assertTrue(any("auto requires" in error for error in errors))
        self.assertEqual(validate_model_inputs(OMNI, {"reference_images": [IMAGE], "aspect_ratio": "16:9"}), [])

    def test_omni_video_requires_explicit_role_and_single_video(self):
        errors = validate_model_inputs(OMNI, {"reference_videos": [VIDEO], "aspect_ratio": "auto"})
        self.assertTrue(any("reference_video_type" in error for error in errors))
        for role in ("base_video", "feature_video"):
            self.assertEqual(validate_model_inputs(OMNI, {"reference_videos": [VIDEO], "reference_video_type": role, "aspect_ratio": "auto"}), [])
        self.assertTrue(validate_model_inputs(OMNI, {"reference_videos": [VIDEO, VIDEO], "reference_video_type": "base_video"}))
        self.assertTrue(validate_model_inputs(OMNI, {"reference_videos": [VIDEO], "reference_video_type": []}))

    def test_omni_image_counts_follow_the_video_scenario(self):
        self.assertEqual(validate_model_inputs(OMNI, {"reference_images": [IMAGE] * 7}), [])
        self.assertTrue(validate_model_inputs(OMNI, {"reference_images": [IMAGE] * 8}))
        mixed = {"reference_images": [IMAGE] * 5, "reference_videos": [VIDEO], "reference_video_type": "feature_video"}
        self.assertEqual(validate_model_inputs(OMNI, mixed), [])
        self.assertTrue(validate_model_inputs(OMNI, {**mixed, "reference_images": [IMAGE] * 6}))

    def test_base_video_does_not_invent_a_duration_rule_for_ignored_parameter(self):
        self.assertEqual(validate_model_inputs(OMNI, {"reference_videos": [VIDEO], "reference_video_type": "base_video", "duration": 8}), [])

    def test_motion_needs_one_character_and_motion_reference(self):
        for model in ("kling/v2-6-motion-control", "kling/v3-motion-control"):
            entry = {"model": model}
            self.assertTrue(validate_model_inputs(entry, {}))
            valid = {"img_urls": [IMAGE], "video_urls": [VIDEO], "character_orientation": "video"}
            self.assertEqual(validate_model_inputs(entry, valid), [])
            self.assertTrue(validate_model_inputs(entry, {**valid, "video_urls": [VIDEO, VIDEO]}))
            self.assertTrue(validate_model_inputs(entry, {**valid, "character_orientation": []}))

    def test_wan_empty_and_voice_only_references_are_not_usable(self):
        for value in ([], [{}], [{"reference_voice": "https://example.com/voice.wav"}]):
            self.assertTrue(validate_model_inputs(WAN, {"reference_medias": value}))
        valid = [{"reference_image": IMAGE, "reference_voice": "https://example.com/voice.wav"}]
        self.assertEqual(validate_model_inputs(WAN, {"reference_medias": valid, "duration": 15}), [])

    def test_wan_reference_video_restricts_generation_duration(self):
        inputs = {"reference_medias": [{"reference_video": VIDEO}], "duration": 10}
        self.assertEqual(validate_model_inputs(WAN, inputs), [])
        self.assertTrue(validate_model_inputs(WAN, {**inputs, "duration": 11}))

    def test_seedance_schema_alternatives_remain_schema_validated(self):
        # Its existing oneOf already handles reference requirements. Do not
        # replace that rule with an image-only assumption in this layer.
        for model in ("bytedance/seedance2-5-r2v", "bytedance/seedance2-5-i2v"):
            self.assertEqual(validate_model_inputs({"model": model}, {}), [])

    def test_known_placeholders_are_valid_reference_presence_before_upload(self):
        placeholder = "https://crun-next.invalid/local/fixture.mp4"
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
            self.assertEqual(validate_model_inputs(OMNI, {"reference_videos": [placeholder], "reference_video_type": "base_video"}), [])

    def test_omni_native_video_boundaries_and_each_measurement(self):
        valid = {"kind": "video", "wire_name": "reference_videos", "socket": "reference_video", "duration": 3, "width": 700, "height": 700, "frame_rate": 24, "byte_count": 200 * 1024 * 1024}
        self.assertEqual(validate_native_media(OMNI, [valid]), [])
        for field, value in (("duration", 2.9), ("duration", 10.1), ("width", 699), ("height", 2161), ("frame_rate", 23.9), ("frame_rate", 60.1), ("byte_count", 200 * 1024 * 1024 + 1)):
            with self.subTest(field=field, value=value):
                self.assertTrue(validate_native_media(OMNI, [{**valid, field: value}]))

    def test_image_batch_file_limit_is_per_item_and_alpha_not_invented(self):
        valid = {"kind": "image", "wire_name": "reference_images", "socket": "reference_images", "count": 2, "width": 1000, "height": 1000, "byte_count": 80 * 1024 * 1024, "byte_counts": [40 * 1024 * 1024] * 2}
        self.assertEqual(validate_native_media(OMNI, [valid]), [])
        self.assertTrue(validate_native_media(OMNI, [{**valid, "byte_counts": [51 * 1024 * 1024, 1]}]))
        self.assertTrue(validate_native_media(OMNI, [{**valid, "width": 299}]))
        self.assertTrue(validate_native_media(OMNI, [{**valid, "width": 4000}]))

    def test_motion_orientation_applies_only_its_documented_duration_limit(self):
        video = {"kind": "video", "wire_name": "video_urls", "socket": "motion_video", "duration": 11, "byte_count": 1}
        self.assertTrue(validate_native_media(MOTION, [video], {"character_orientation": "image"}))
        self.assertEqual(validate_native_media(MOTION, [video], {"character_orientation": "video"}), [])
        self.assertTrue(validate_native_media(MOTION, [{**video, "duration": 31}], {"character_orientation": "video"}))
        self.assertTrue(validate_native_media(MOTION, [{**video, "duration": 2}], {"character_orientation": "video"}))

    def test_motion_image_dimensions_and_ratio(self):
        image = {"kind": "image", "wire_name": "img_urls", "socket": "image", "width": 340, "height": 340, "byte_count": 10 * 1024 * 1024}
        self.assertEqual(validate_native_media(MOTION, [image]), [])
        self.assertTrue(validate_native_media(MOTION, [{**image, "width": 339}]))
        self.assertTrue(validate_native_media(MOTION, [{**image, "height": 3851}]))
        self.assertTrue(validate_native_media(MOTION, [{**image, "width": 1200}]))

    def test_unknown_measurements_and_other_models_do_not_invent_restrictions(self):
        self.assertEqual(validate_native_media(OMNI, [{"kind": "video", "wire_name": "reference_videos"}]), [])
        video = {"kind": "video", "wire_name": "video_urls", "duration": 1, "width": 128, "height": 128}
        self.assertEqual(validate_native_media({"model": "kling/v3-motion-control"}, [video]), [])
        self.assertEqual(validate_model_inputs({"model": "unrelated"}, {}), [])

    def test_messages_do_not_echo_reference_urls_or_prompts(self):
        errors = validate_model_inputs(OMNI, {"prompt": "PRIVATE PROMPT", "reference_images": [IMAGE], "aspect_ratio": "auto"})
        self.assertNotIn(IMAGE, str(errors))
        self.assertNotIn("PRIVATE", str(errors))


if __name__ == "__main__":
    unittest.main()
