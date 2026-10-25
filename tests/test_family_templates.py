import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from family_nodes import family_node_mappings

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_family_templates", ROOT / "scripts" / "build_family_templates.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class FamilyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.families = builder.bundled_families()
        entries = [entry for family in cls.families for entry in family["entries"]]
        cls.classes, cls.names = family_node_mappings(entries)

    def workflow(self, name, task):
        record = next(record for record in self.families if record["family"] == name and record["task"] == task)
        return builder.workflow_for(record, self.classes[record["id"]], self.names[record["id"]])

    def test_seedance_i2v_has_real_image_link_and_text_video_has_none(self):
        image = self.workflow("Seedance", "Image to Video")
        text = self.workflow("Seedance", "Text to Video")
        self.assertEqual(image["links"][0][2], 0)
        self.assertEqual(image["links"][0][-1], "IMAGE")
        native = image["nodes"][0]["inputs"][image["links"][0][4]]
        self.assertEqual(native["name"], "first_frame")
        self.assertEqual(native["type"], "IMAGE")
        self.assertEqual(len(text["links"]), 2)
        self.assertEqual(text["links"][0][1:3], [1, 1])
        self.assertFalse(any(node["type"] == "LoadImage" for node in text["nodes"]))

    def test_image_editing_and_references_have_ordered_native_connections(self):
        editing = self.workflow("Seedream", "Generate & Edit Image")
        references = self.workflow("Seedance", "Reference to Video")
        self.assertEqual(editing["extra"]["crun_next"]["native_inputs_connected"], ["image"])
        self.assertEqual(references["extra"]["crun_next"]["native_inputs_connected"], ["reference_images"])
        note = next(node for node in editing["nodes"] if node["type"] == "Note")["widgets_values"][0]
        self.assertIn("IMAGE EDITING", note)
        self.assertIn("Disconnect", note)

    def test_widget_values_exclude_native_inputs_and_never_serialize_profiles(self):
        workflow = self.workflow("Seedance", "Image to Video")
        node = workflow["nodes"][0]
        klass = self.classes[node["type"]]
        fields = klass.INPUT_TYPES()["required"]
        values = dict(zip(fields, node["widgets_values"]))
        self.assertEqual(len(values), len(fields))
        self.assertEqual(values["crun_mode"], "prepare")
        self.assertFalse(values["crun_allow_paid_generation"])
        self.assertFalse(values["crun_allow_upload"])
        self.assertEqual(values["crun_max_credits"], 0)
        self.assertNotIn("first_frame", values)
        self.assertNotIn("crun_profiles", json.dumps(workflow))

    def test_native_result_pipeline_and_compact_layout(self):
        for name, task, result_type, preview_type, media in (
            ("Seedance", "Image to Video", "CRUN_Next_Get_Video_Result", "SaveVideo", "VIDEO"),
            ("Seedream", "Generate & Edit Image", "CRUN_Next_Get_Image_Result", "PreviewImage", "IMAGE"),
        ):
            with self.subTest(task=task):
                workflow = self.workflow(name, task)
                result = next(node for node in workflow["nodes"] if node["type"] == result_type)
                preview = next(node for node in workflow["nodes"] if node["type"] == preview_type)
                task_link = next(link for link in workflow["links"] if link[3] == result["id"])
                media_link = next(link for link in workflow["links"] if link[3] == preview["id"])
                self.assertEqual(task_link[1:3], [1, 1])
                self.assertEqual(task_link[-1], "STRING")
                self.assertEqual(media_link[1:3], [result["id"], 0])
                self.assertEqual(media_link[-1], media)
                self.assertEqual(result["widgets_values"], [0, 1200, 3.0])
                self.assertEqual(preview["widgets_values"], [] if media == "IMAGE" else ["video/CRUN", "auto", "auto"])
                self.assertGreater(preview["pos"][1], result["pos"][1])
                note = next(node for node in workflow["nodes"] if node["type"] == "Note")
                self.assertTrue(note["flags"]["collapsed"])
                self.assertLess(note["pos"][0], workflow["nodes"][0]["pos"][0])
                self.assertEqual(workflow["extra"]["ds"]["scale"], 0.8)

    def test_links_are_consistent_and_empty_task_preview_is_offline(self):
        from result_nodes import CRUNGetImageResult, CRUNGetVideoResult
        with patch("result_nodes.load_result", side_effect=AssertionError("No provider request")):
            for node in (CRUNGetImageResult(), CRUNGetVideoResult()):
                output = node.load("")
                self.assertEqual(output["result"][1:], ("", -1.0, ""))
        for record in self.families:
            workflow = builder.workflow_for(record, self.classes[record["id"]], self.names[record["id"]])
            nodes = {node["id"]: node for node in workflow["nodes"]}
            for link_id, source, source_slot, target, target_slot, media in workflow["links"]:
                self.assertIn(link_id, nodes[source]["outputs"][source_slot]["links"])
                self.assertEqual(nodes[target]["inputs"][target_slot]["link"], link_id)
                self.assertEqual(nodes[source]["outputs"][source_slot]["type"], media)
                self.assertEqual(nodes[target]["inputs"][target_slot]["type"], media)

    def test_complete_flat_coverage_built_offline_from_bundled_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
                manifest = builder.build_templates(directory)
            self.assertEqual(manifest["family_templates"], len(self.families))
            self.assertEqual(manifest["model_variants"], sum(len(record["entries"]) for record in self.families))
            files = list(Path(directory).glob("Studio-*.json"))
            self.assertEqual(len(files), len(self.families))
            for path in files:
                workflow = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn(workflow["nodes"][0]["type"], self.classes)
                self.assertEqual(workflow["extra"]["crun_next"]["default_mode"], "prepare")

    def test_checked_in_starters_match_manifest_and_do_not_include_user_files(self):
        path = ROOT / "data" / "family_workflow_manifest.json"
        self.assertTrue(path.is_file(), "Generate family templates before packaging")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["family_templates"], len(self.families))
        self.assertEqual({entry["family_id"] for entry in manifest["entries"]}, set(self.classes))
        for entry in manifest["entries"]:
            workflow = json.loads((ROOT / "example_workflows" / entry["path"]).read_text(encoding="utf-8"))
            self.assertEqual(workflow["nodes"][0]["type"], entry["family_id"])
            for node in workflow["nodes"]:
                if node["type"] == "LoadImage":
                    self.assertEqual(node["widgets_values"][0], "")


if __name__ == "__main__":
    unittest.main()
