import unittest

from crun.effects import build_effect_plan, normalize_catalog


class CatalogTests(unittest.TestCase):
    def test_kling_keeps_unknown_count_unknown_and_plain_text(self):
        raw = {"key": "pet", "name": "<img onerror=alert(1)>", "credit": 20.5,
               "cover_url": "https://cdn.example.com/pet.png", "video_url": "javascript:alert(1)",
               "info": [{"title": "Input Instruction", "values": ["Single animal"]}]}
        cards = normalize_catalog("kling", {"code": 200, "data": {"templates": [raw]}})
        self.assertEqual(cards[0]["name"], "<img onerror=alert(1)>")
        self.assertIsNone(cards[0]["required_images"])
        self.assertEqual(cards[0]["credits"], 20.5)
        self.assertIsNone(cards[0]["preview_url"])
        cards[0]["raw"]["info"].clear()
        self.assertTrue(raw["info"])

    def test_bytedance_uses_template_not_media_identifier(self):
        cards = normalize_catalog("bytedance", {"templates": [{
            "MediaId": "preview-id", "TemplateId": "123", "Title": "原名", "Title_en": "Battle",
            "InputNum": 2, "ConsumeItems": [{"Resolution": "480p", "Credit": 12}, {"Resolution": "720p", "Credit": 20}],
            "Cover": "https://cdn.example.com/cover.png", "PreviewVideo": "https://cdn.example.com/clip.mp4",
        }]})
        self.assertEqual(cards[0]["id"], "123")
        self.assertEqual(cards[0]["required_images"], 2)
        self.assertEqual(cards[0]["credits"], [{"resolution": "480p", "credits": 12.0}, {"resolution": "720p", "credits": 20.0}])

    def test_vidu_defensive_mapping_does_not_infer_count(self):
        card = normalize_catalog("vidu", [{"template": "sample", "name": "Sample", "credits": "5", "image_num": "1-3"}])[0]
        self.assertEqual(card["id"], "sample")
        self.assertIsNone(card["required_images"])

    def test_empty_and_duplicate_entries(self):
        self.assertEqual(normalize_catalog("kling", {"templates": []}), [])
        cards = normalize_catalog("kling", {"templates": [{}, None, {"key": "a"}, {"key": "a", "name": "dup"}]})
        self.assertEqual(len(cards), 1)

    def test_non_success_and_wrong_shapes_rejected(self):
        for value in ({"code": 403, "data": {}}, {"templates": "wrong"}, {"total": 280}, {"items": []}, "wrong"):
            with self.assertRaises(ValueError):
                normalize_catalog("kling", value)
        with self.assertRaises(ValueError):
            normalize_catalog("other", [])

    def test_bad_values_never_become_a_fake_price_or_slot_count(self):
        for value in (True, -1, "NaN", "Infinity", {}, "1-3"):
            card = normalize_catalog("kling", [{"key": "x", "credit": value, "image_count": value}])[0]
            self.assertIsNone(card["credits"])
            self.assertIsNone(card["required_images"])

    def test_private_or_credentials_asset_urls_not_exposed_as_preview(self):
        for url in ("https://localhost/a", "https://127.0.0.1/a", "https://[::1]/a", "https://u:p@example.com/a", "https://host.local/a"):
            card = normalize_catalog("kling", [{"key": "a", "video_url": url}])[0]
            self.assertIsNone(card["preview_url"])


class PlanTests(unittest.TestCase):
    def test_kling_draft_has_documented_request_but_cannot_execute(self):
        plan = build_effect_plan("kling", "pet", ["https://cdn.example.com/input.png"], {"required_images": 1})
        self.assertEqual(plan["payload"], {"model": "kling/template", "input": {"template_id": "pet", "img_urls": ["https://cdn.example.com/input.png"]}})
        self.assertFalse(plan["execution_enabled"])
        self.assertFalse(plan["ready_to_submit"])
        self.assertEqual(plan["status"], "draft")

    def test_bytedance_resolution_and_vidu_request_names(self):
        plan = build_effect_plan("bytedance", "123", ["https://cdn.example.com/i.png"], {"resolution": "720p"})
        self.assertEqual(plan["payload"]["input"]["resolution"], "720p")
        plan = build_effect_plan("vidu", "pet", ["https://cdn.example.com/i.png"], {"bgm": False})
        self.assertEqual(plan["payload"]["input"], {"template": "pet", "images": ["https://cdn.example.com/i.png"], "bgm": False})

    def test_empty_plan_is_explicitly_incomplete(self):
        plan = build_effect_plan("kling", "selected_template", [])
        self.assertFalse(plan["ready_to_submit"])
        self.assertTrue(any("Add image" in warning for warning in plan["warnings"]))
        self.assertIsNone(plan["required_images"])

    def test_count_mismatch_and_unknown_options_fail(self):
        with self.assertRaises(ValueError):
            build_effect_plan("kling", "x", [], {"required_images": 2})
        with self.assertRaises(ValueError):
            build_effect_plan("kling", "x", [], {"model": "some-paid-model"})
        with self.assertRaises(ValueError):
            build_effect_plan("vidu", "x", [], {"bgm": "false"})

    def test_bad_input_urls_rejected(self):
        for url in ("file:///input.png", "data:image/png;base64,x", "http://example.com/x", "https://localhost/x", "https://192.168.1.1/x", "https://u:p@example.com/x"):
            with self.assertRaises(ValueError):
                build_effect_plan("kling", "x", [url])


if __name__ == "__main__":
    unittest.main()
