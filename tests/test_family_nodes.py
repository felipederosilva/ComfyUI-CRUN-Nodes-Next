import json
import unittest
from unittest.mock import patch

import family_nodes as family
import generated_nodes as generated


class FamilyNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = family.family_catalog()
        cls.classes, cls.names = family.family_node_mappings()

    def get(self, name, task):
        return next(node for node in self.classes.values() if node.CRUN_FAMILY["family"] == name and node.CRUN_FAMILY["task"] == task)

    def defaults(self, node):
        values = {}
        for specs in node.INPUT_TYPES().values():
            for name, spec in specs.items():
                if isinstance(spec[0], str) and spec[0] in {"IMAGE", "MASK", "VIDEO", "AUDIO"}:
                    continue
                options = spec[1] if len(spec) > 1 else {}
                values[name] = options.get("default", spec[0][0] if isinstance(spec[0], list) else "")
        return values

    def test_families_cover_actual_media_operations_without_network(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
            catalog = family.family_catalog()
        eligible = [entry for entry in generated._load_model_entries() if family.family_identity(entry)]
        self.assertEqual(sum(len(record["entries"]) for record in catalog), len(eligible))
        self.assertGreater(len(catalog), 20)
        self.assertEqual(len(self.classes), len(self.names))
        self.assertEqual(len({entry["id"] for record in catalog for entry in record["entries"]}), len(eligible))

    def test_seedance_is_split_by_task_with_version_dropdown(self):
        for task, count in (("Text to Video", 8), ("Image to Video", 8), ("Reference to Video", 5)):
            node = self.get("Seedance", task)
            definition = node.INPUT_TYPES()
            choices, options = definition["required"]["model"]
            self.assertEqual(len(choices), count)
            self.assertEqual(set(choices), set(options["crun_profiles"]))
            self.assertEqual(list(definition["required"])[:2], ["model", "prompt"])
            self.assertEqual(definition["required"]["crun_mode"][1]["default"], "prepare")

    def test_video_editing_and_motion_control_are_not_grouped_as_image_generation(self):
        editing = self.get("Runway", "Video Editing")
        generating = self.get("Runway", "Text / Image to Video")
        self.assertEqual({entry["model"] for entry in editing.CRUN_FAMILY["entries"]}, {"runway/gen-4-aleph"})
        self.assertEqual({entry["model"] for entry in generating.CRUN_FAMILY["entries"]}, {"runway/gen-4-turbo"})
        self.assertEqual(self.get("DreamActor", "Motion Control").CRUN_FAMILY["entries"][0]["model"], "bytedance/dreamactor")

    def test_native_sockets_are_part_of_families(self):
        image = self.get("Seedance", "Image to Video").INPUT_TYPES()
        text = self.get("Seedance", "Text to Video").INPUT_TYPES()
        self.assertEqual(image["optional"]["first_frame"][0], "IMAGE")
        self.assertEqual(image["optional"]["last_frame"][0], "IMAGE")
        self.assertNotIn("optional", text)
        self.assertEqual(self.get("Nano Banana", "Generate & Edit Image").INPUT_TYPES()["optional"]["image"][0], "IMAGE")

    def test_profiles_keep_selected_model_constraints(self):
        node = self.get("Seedance", "Image to Video")
        profiles = node.CRUN_PROFILES
        newest = next(profile for profile in profiles.values() if profile["model_id"] == "bytedance/seedance2-5-i2v")
        version_two = next(profile for profile in profiles.values() if profile["model_id"] == "bytedance/seedance2-0-i2v")
        self.assertEqual(newest["fields"]["aspect_ratio"]["options"]["values"], ["auto"])
        self.assertNotIn("4k", newest["fields"]["resolution"]["options"]["values"])
        self.assertIn("4k", version_two["fields"]["resolution"]["options"]["values"])
        self.assertEqual(newest["fields"]["duration"]["options"]["max"], 30)
        self.assertEqual(version_two["fields"]["duration"]["options"]["max"], 15)

    def test_dropdown_executes_exact_model_not_a_union_payload(self):
        node = self.get("Seedance", "Text to Video")
        model = next(label for label, profile in node.CRUN_PROFILES.items() if profile["model_id"] == "bytedance/seedance1-5-pro-t2v")
        with patch.object(generated, "run_entry", return_value={"mode": "prepare", "payload": {}, "task_id": ""}) as run:
            node().execute(model=model, prompt="Fictional", duration="8", camera_fixed=True)
        self.assertEqual(run.call_args.args[0]["model"], "bytedance/seedance1-5-pro-t2v")
        self.assertEqual(run.call_args.args[1]["duration"], 8)
        self.assertTrue(run.call_args.args[1]["camera_fixed"])
        self.assertEqual(run.call_args.args[2], "prepare")

    def test_incompatible_native_reference_is_not_silently_dropped(self):
        node = self.get("Seedance", "Image to Video")
        model = next(label for label, profile in node.CRUN_PROFILES.items() if profile["model_id"] == "bytedance/seedance1-0-pro-fast-i2v")
        with patch.object(generated, "run_entry", side_effect=AssertionError("No execution")):
            with self.assertRaisesRegex(ValueError, "disconnect this reference"):
                node().execute(model=model, last_frame=object())

    def test_unsupported_modified_widget_rejected_but_inactive_default_allowed(self):
        node = self.get("Seedance", "Text to Video")
        model = next(label for label, profile in node.CRUN_PROFILES.items() if profile["model_id"] == "bytedance/seedance2-5-t2v")
        with patch.object(generated, "run_entry", return_value={"mode": "prepare", "task_id": ""}) as run:
            node().execute(model=model, camera_fixed=False)
            self.assertNotIn("camera_fixed", run.call_args.args[1])
            with self.assertRaisesRegex(ValueError, "not supported"):
                node().execute(model=model, camera_fixed=True)

    def test_unknown_model_and_input_rejected_before_network(self):
        node = self.get("Seedance", "Text to Video")
        with patch.object(generated, "run_entry", side_effect=AssertionError("No execution")):
            with self.assertRaises(ValueError):
                node().execute(model="pretend/model")
            with self.assertRaises(ValueError):
                node().execute(pretend_parameter="secret")

    def test_nullable_optional_enum_keeps_provider_default(self):
        node = self.get("Wan", "Text to Video")
        model = next(label for label, profile in node.CRUN_PROFILES.items() if profile["model_id"] == "wan/3-0-t2v")
        with patch.object(generated, "run_entry", return_value={"mode": "prepare", "task_id": ""}) as run:
            node().execute(model=model, region=family.PROVIDER_DEFAULT)
        self.assertNotIn("region", run.call_args.args[1])

    def test_all_family_default_preparation_is_offline(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
            for node in self.classes.values():
                with self.subTest(family=node.CRUN_FAMILY["id"]):
                    result = node().execute(**self.defaults(node))
                    payload = json.loads(result["result"][0])
                    self.assertEqual(payload["mode"], "prepare")
                    self.assertEqual(payload["task_id"], "")


if __name__ == "__main__":
    unittest.main()
