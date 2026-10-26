import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from creative_nodes import creative_mappings, studio_node_id

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_family_templates", ROOT / "scripts/build_family_templates.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
NATIVE = {"IMAGE", "MASK", "VIDEO", "AUDIO"}


class FamilyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.families = builder.bundled_families()
        entries = [entry for family in cls.families for entry in family["entries"]]
        cls.classes, cls.names = creative_mappings(entries)

    def workflow(self, name, task):
        record = next(record for record in self.families if record["family"] == name and record["task"] == task)
        identifier = studio_node_id(record)
        return builder.workflow_for(record, self.classes[identifier], self.names[identifier])

    def test_seedance_i2v_has_real_image_link_and_text_video_has_none(self):
        image = self.workflow("Seedance", "Image to Video")
        text = self.workflow("Seedance", "Text to Video")
        image_link = next(link for link in image["links"] if link[3] == 1)
        native = image["nodes"][0]["inputs"][image_link[4]]
        self.assertEqual(native["name"], "first_frame")
        self.assertEqual(native["type"], "IMAGE")
        self.assertEqual(len(text["links"]), 1)
        self.assertEqual(text["links"][0][1:3], [1, 0])
        self.assertEqual(text["links"][0][-1], "VIDEO")
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
        definition = self.classes[node["type"]].INPUT_TYPES()
        fields = {name: spec for section in ("required", "optional") for name, spec in definition.get(section, {}).items()
                  if not (isinstance(spec[0], str) and spec[0] in NATIVE)}
        values = dict(zip(fields, node["widgets_values"]))
        self.assertEqual(len(values), len(fields))
        self.assertEqual(values["crun_mode"], "prepare")
        self.assertFalse(values["crun_allow_paid_generation"])
        self.assertFalse(values["crun_allow_upload"])
        self.assertEqual(values["crun_max_credits"], 0)
        self.assertEqual(values["take"], 0)
        self.assertEqual(values["resume_task_id"], "")
        self.assertNotIn("first_frame", values)
        self.assertNotIn("crun_profiles", json.dumps(workflow))

    def test_generation_connects_directly_to_native_preview_or_save(self):
        for name, task, preview_type, media in (
            ("Seedance", "Image to Video", "SaveVideo", "VIDEO"),
            ("Seedream", "Generate & Edit Image", "PreviewImage", "IMAGE"),
        ):
            with self.subTest(task=task):
                workflow = self.workflow(name, task)
                preview = next(node for node in workflow["nodes"] if node["type"] == preview_type)
                media_link = next(link for link in workflow["links"] if link[3] == preview["id"])
                self.assertEqual(media_link[1:3], [1, 0])
                self.assertEqual(media_link[-1], media)
                self.assertFalse(any("_Get_" in node["type"] for node in workflow["nodes"]))
                self.assertEqual(preview["widgets_values"], [] if media == "IMAGE" else ["video/CRUN", "auto", "auto"])
                self.assertIsNone(workflow["extra"]["crun_next"]["result_node"])
                if media == "IMAGE":
                    self.assertEqual(workflow["nodes"][0]["outputs"][1]["type"], "MASK")
                note = next(node for node in workflow["nodes"] if node["type"] == "Note")
                self.assertTrue(note["flags"]["collapsed"])

    def test_all_native_links_are_consistent_with_source_and_target_types(self):
        for record in self.families:
            identifier = studio_node_id(record)
            workflow = builder.workflow_for(record, self.classes[identifier], self.names[identifier])
            nodes = {node["id"]: node for node in workflow["nodes"]}
            for link_id, source, source_slot, target, target_slot, media in workflow["links"]:
                self.assertIn(link_id, nodes[source]["outputs"][source_slot]["links"])
                self.assertEqual(nodes[target]["inputs"][target_slot]["link"], link_id)
                self.assertEqual(nodes[source]["outputs"][source_slot]["type"], media)
                self.assertEqual(nodes[target]["inputs"][target_slot]["type"], media)

    def test_motion_starter_includes_required_native_motion_video(self):
        workflow = self.workflow("Kling", "Motion Control")
        video = next(node for node in workflow["nodes"] if node["type"] == "LoadVideo")
        self.assertEqual(video["widgets_values"], [""])
        link = next(link for link in workflow["links"] if link[1] == video["id"])
        target = workflow["nodes"][0]["inputs"][link[4]]
        self.assertEqual(target["name"], "motion_video")
        self.assertEqual(target["type"], "VIDEO")
        self.assertEqual(sum(node["type"] == "LoadVideo" for node in workflow["nodes"]), 1)

    def test_complete_flat_coverage_built_offline_from_bundled_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
                manifest = builder.build_templates(directory)
            self.assertEqual(manifest["family_templates"], len(self.families))
            self.assertEqual(manifest["model_variants"], sum(len(record["entries"]) for record in self.families))
            for path in Path(directory).glob("Studio-*.json"):
                workflow = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn(workflow["nodes"][0]["type"], self.classes)
                self.assertTrue(workflow["nodes"][0]["type"].startswith("CRUN_Next_Studio_"))
                self.assertEqual(workflow["extra"]["crun_next"]["default_mode"], "prepare")

    def test_checked_in_starters_match_manifest_and_do_not_include_user_files(self):
        manifest = json.loads((ROOT / "data/family_workflow_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["family_templates"], len(self.families))
        self.assertEqual({entry["family_id"] for entry in manifest["entries"]}, {record["id"] for record in self.families})
        for entry in manifest["entries"]:
            workflow = json.loads((ROOT / "example_workflows" / entry["path"]).read_text(encoding="utf-8"))
            self.assertEqual(workflow["nodes"][0]["type"], entry["node_type"])
            for node in workflow["nodes"]:
                if node["type"] in {"LoadImage", "LoadVideo", "LoadAudio"}:
                    self.assertEqual(node["widgets_values"][0], "")


if __name__ == "__main__":
    unittest.main()
