from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generated_nodes as generated


def sample_entry(**overrides):
    entry = {
        "id": "sample", "model": "google/sample", "title": "Sample Image", "provider": "Google",
        "kind": "image", "group": "Image", "generation_supported": True,
        "endpoint": "/api/v1/client/job/CreateTask", "method": "POST",
        "inputs": {"type": "object", "required": ["prompt"], "properties": {
            "prompt": {"type": "string"}, "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9"], "default": "16:9"},
            "images": {"type": "array", "items": {"type": "string"}}, "seed": {"type": "integer", "default": 7, "minimum": 0},
            "quality": {"type": "integer", "enum": [1, 4, 8]},
        }},
    }
    entry.update(overrides)
    return entry


class GeneratedNodeTests(unittest.TestCase):
    def test_model_widgets_follow_schema_and_safe_defaults(self):
        node = generated.make_node(sample_entry())
        widgets = node.INPUT_TYPES()
        self.assertIn("prompt", widgets["required"])
        self.assertEqual(widgets["required"]["crun_mode"][1]["default"], "prepare")
        self.assertFalse(widgets["required"]["crun_allow_paid_generation"][1]["default"])
        self.assertEqual(widgets["required"]["crun_max_credits"][1]["default"], 0)
        self.assertEqual(widgets["optional"]["aspect_ratio"][0], ["1:1", "16:9"])
        self.assertEqual(widgets["optional"]["images"][1]["default"], "[]")
        self.assertEqual(widgets["optional"]["quality"][0], ["1", "4", "8"])

    def test_no_network_for_menu_definitions(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network permitted")):
            classes, names = generated.generated_mappings([sample_entry()])
            for node in classes.values():
                node.INPUT_TYPES()
        self.assertEqual(len(classes), len(names))

    def test_execute_parses_model_fields_and_forwards_explicit_gates(self):
        node = generated.make_node(sample_entry())()
        response = {"mode": "prepare", "task_id": "", "credits": None, "payload": {}}
        with patch.object(generated, "run_entry", return_value=response) as run:
            result = node.execute(prompt="x", images='["https://cdn.example.com/i.png"]', quality="4")
        args, kwargs = run.call_args
        self.assertEqual(args[1]["quality"], 4)
        self.assertEqual(args[1]["images"], ["https://cdn.example.com/i.png"])
        self.assertEqual(args[2], "prepare")
        self.assertFalse(kwargs["allow_paid_generation"])
        self.assertEqual(kwargs["max_credits"], 0)
        self.assertEqual(result["result"][2], -1)

    def test_nested_request_schema_and_fixed_template_are_supported(self):
        schema = {"type": "object", "properties": {"model": {"type": "string"}, "input": {"type": "object", "required": ["template_id", "img_urls"], "properties": {"template_id": {"type": "string", "const": "fixed"}, "img_urls": {"type": "array"}}}}}
        node = generated.make_node(sample_entry(inputs=schema))
        self.assertNotIn("template_id", node.INPUT_TYPES()["required"])
        with patch.object(generated, "run_entry", return_value={"mode": "prepare"}) as run:
            node().execute(img_urls="[]")
        self.assertEqual(run.call_args.args[1]["template_id"], "fixed")
        with self.assertRaises(ValueError):
            node().execute(template_id="changed", img_urls="[]")

    def test_entry_mutation_cannot_change_already_created_class(self):
        entry = sample_entry()
        node = generated.make_node(entry)
        entry["inputs"]["properties"]["aspect_ratio"]["enum"].append("unsupported")
        self.assertNotIn("unsupported", node.INPUT_TYPES()["optional"]["aspect_ratio"][0])

    def test_control_name_collision_is_explicitly_mapped(self):
        entry = sample_entry()
        entry["inputs"]["properties"]["crun_mode"] = {"type": "string"}
        node = generated.make_node(entry)
        self.assertIn("input_crun_mode", node.INPUT_TYPES()["optional"])
        with patch.object(generated, "run_entry", return_value={}) as run:
            node().execute(input_crun_mode="model-value")
        self.assertEqual(run.call_args.args[1]["crun_mode"], "model-value")

    def test_bad_json_mode_and_budget_fail_before_execution(self):
        node = generated.make_node(sample_entry())()
        for kwargs in ({"images": "not-json"}, {"crun_mode": "auto"}, {"crun_max_credits": float("nan")}, {"crun_allow_paid_generation": "yes"}):
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                node.execute(**kwargs)

    def test_effects_use_exact_count_and_live_resolution_choices(self):
        card = {"id": "123", "name": "Effect", "required_images": 2, "credits": [{"resolution": "480p", "credits": 2}, {"resolution": "720p", "credits": 4}], "raw": {}}
        entry = generated._effect_entry("bytedance", card)
        self.assertEqual(entry["inputs"]["properties"]["img_urls"]["minItems"], 2)
        self.assertEqual(entry["inputs"]["properties"]["resolution"]["enum"], ["480p", "720p"])
        self.assertNotIn("template_id", generated.make_node(entry).INPUT_TYPES()["required"])

    def test_unknown_effect_count_is_not_invented(self):
        card = {"id": "pet", "required_images": None, "raw": {"aspect_ratio": ["auto"]}}
        entry = generated._effect_entry("vidu", card)
        self.assertNotIn("maxItems", entry["inputs"]["properties"]["images"])
        self.assertTrue(entry["warnings"])
        self.assertEqual(entry["inputs"]["properties"]["aspect_ratio"]["enum"], ["auto"])

    def test_bundled_coverage_has_a_distinct_node_for_every_entry(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network permitted")):
            entries = generated.all_entries()
            classes, names = generated.generated_mappings(entries)
            self.assertEqual(len(classes), len(entries))
            for cls in classes.values():
                definition = cls.INPUT_TYPES()
                self.assertEqual(definition["required"]["crun_mode"][0], generated.MODES)
        self.assertGreater(len(entries), 100)
        self.assertEqual(len(names), len(classes))


if __name__ == "__main__":
    unittest.main()
