import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generated_nodes as generated
import creative_nodes as creative
from test_generated_nodes import sample_entry

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("crun_build_templates", ROOT / "scripts" / "build_templates.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
sync_spec = importlib.util.spec_from_file_location("crun_sync_effects", ROOT / "scripts" / "sync_effects.py")
effects_sync = importlib.util.module_from_spec(sync_spec)
sync_spec.loader.exec_module(effects_sync)


class TemplateTests(unittest.TestCase):
    def test_workflow_is_safe_and_matches_generated_node_definition(self):
        entry = sample_entry()
        node = creative.creative_mappings([entry])[0][creative.media_node_id(entry)]
        workflow = builder.workflow_for(entry, node, "CRUN • Sample")
        self.assertEqual(workflow["version"], 0.4)
        self.assertTrue(all(link[5] == 'IMAGE' for link in workflow['links']))
        self.assertTrue(any(node['type'] == 'LoadImage' for node in workflow['nodes']))
        graph_node = workflow["nodes"][0]
        self.assertEqual(graph_node["type"], creative.media_node_id(entry))
        self.assertEqual(graph_node["outputs"][0]["type"], "IMAGE")
        self.assertTrue(any(node["type"] == "PreviewImage" for node in workflow["nodes"]))
        self.assertFalse(any("Get_Image_Result" in node["type"] for node in workflow["nodes"]))
        self.assertEqual(graph_node["widgets_values"][:3], ["prepare", False, 0])
        self.assertTrue(any(node["type"] == "Note" for node in workflow["nodes"]))
        self.assertFalse(workflow["extra"]["crun_next"]["generation_tested"])

    def test_names_are_short_stable_and_unique_even_with_same_title(self):
        first = sample_entry(id="a", title="Same title " * 40)
        second = sample_entry(id="b", title=first["title"])
        self.assertLess(len(builder._filename(first)), 90)
        self.assertEqual(builder._filename(first), builder._filename(first))
        self.assertNotEqual(builder._filename(first), builder._filename(second))

    def test_build_maps_every_entry_to_flat_existing_file(self):
        entries = [sample_entry(id="a"), sample_entry(id="b", kind="tool", group="AI Tools")]
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temp:
            out = Path(temp)
            with patch("requests.sessions.Session.request", side_effect=AssertionError("No network permitted")):
                manifest = builder.build_templates(out, entries)
            self.assertEqual(manifest["total_templates"], 2)
            for record in manifest["entries"]:
                self.assertNotIn("/", record["path"])
                workflow = json.loads((out / record["path"]).read_text(encoding="utf-8"))
                self.assertEqual(workflow["nodes"][0]["type"], record["node_type"])
                self.assertEqual(workflow["nodes"][0]["widgets_values"][:3], ["prepare", False, 0])

    def test_checked_in_manifest_covers_all_option_nodes_and_effect_records(self):
        path = ROOT / "data" / "workflow_manifest.json"
        if not path.exists():
            self.skipTest("Templates have not been generated yet.")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        entries = builder.bundled_entries()
        self.assertEqual(manifest["total_templates"], len(entries))
        self.assertEqual({r["entry_id"] for r in manifest["entries"]}, {e["id"] for e in entries})
        node_ids = {creative.media_node_id(entry) if creative.output_kind(entry) else generated.node_id_for(entry) for entry in entries}
        for record in manifest["entries"]:
            workflow_path = ROOT / "example_workflows" / record["path"]
            self.assertTrue(workflow_path.is_file())
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            self.assertIn(workflow["nodes"][0]["type"], node_ids)
            self.assertEqual(workflow["nodes"][0]["widgets_values"][:3], ["prepare", False, 0])
        effects = json.loads(generated.EFFECTS_PATH.read_text(encoding="utf-8"))
        record_count = sum(provider.get("total_records", len(provider.get("cards", []))) for provider in effects["providers"].values())
        self.assertEqual(manifest["effect_catalog_records"], record_count)
        self.assertEqual(len(manifest["catalog_record_coverage"]), record_count)
        paths = {record["path"] for record in manifest["entries"]}
        self.assertTrue(all(record["path"] in paths for record in manifest["catalog_record_coverage"]))
        self.assertFalse((ROOT / "example_workflows" / "manifest.json").exists())

    def test_every_creative_recipe_has_a_direct_native_media_sink(self):
        manifest = json.loads((ROOT / "data/workflow_manifest.json").read_text(encoding="utf-8"))
        for record in manifest["entries"]:
            workflow = json.loads((ROOT / "example_workflows" / record["path"]).read_text(encoding="utf-8"))
            nodes = {node["id"]: node for node in workflow["nodes"]}
            if record["output_kind"]:
                sink = next(node for node in nodes.values() if node["type"] == record["preview_node"])
                media_link = next(link for link in workflow["links"] if link[3] == sink["id"])
                self.assertEqual(media_link[1:3], [1, 0])
                self.assertEqual(media_link[-1], record["output_kind"].upper())
                self.assertEqual(nodes[1]["outputs"][0]["type"], media_link[-1])
            else:
                self.assertEqual(record["workflow_type"], "advanced_api_preparation")
                note = next(node for node in nodes.values() if node["type"] == "Note")
                self.assertIn("ADVANCED API PREPARATION ONLY", note["widgets_values"][0])
            for link_id, source, source_slot, target, target_slot, media in workflow["links"]:
                self.assertIn(link_id, nodes[source]["outputs"][source_slot]["links"])
                self.assertEqual(nodes[target]["inputs"][target_slot]["link"], link_id)
                self.assertEqual(nodes[source]["outputs"][source_slot]["type"], media)
                self.assertEqual(nodes[target]["inputs"][target_slot]["type"], media)

    def test_motion_reference_recipe_uses_load_video_and_native_video_link(self):
        entry = next(entry for entry in builder.bundled_entries() if entry.get("model") == "kling/v3-motion-control")
        node = creative.creative_mappings([entry])[0][creative.media_node_id(entry)]
        workflow = builder.workflow_for(entry, node, "CRUN Motion")
        loaders = [node for node in workflow["nodes"] if node["type"] == "LoadVideo"]
        self.assertEqual(len(loaders), 1)
        self.assertEqual(loaders[0]["widgets_values"], [""])
        video_link = next(link for link in workflow["links"] if link[1] == loaders[0]["id"])
        self.assertEqual(video_link[-1], "VIDEO")
        target = workflow["nodes"][0]["inputs"][video_link[4]]
        self.assertEqual(target["name"], "motion_video")

    def test_fixed_effect_recipe_keeps_every_required_image_in_order(self):
        entry = generated._effect_entry("bytedance", {"id": "two_image_fixture", "name": "Two images", "required_images": 2, "credits": [{"resolution": "720p", "credits": 3}], "raw": {}})
        node = creative.creative_mappings([entry])[0][creative.media_node_id(entry)]
        workflow = builder.workflow_for(entry, node, "Two images")
        links = [link for link in workflow["links"] if link[3] == 1]
        ports = workflow["nodes"][0]["inputs"]
        self.assertEqual([ports[link[4]]["name"] for link in links], ["image_1", "image_2"])
        self.assertEqual(sum(node["type"] == "LoadImage" for node in workflow["nodes"]), 2)

    def test_inpaint_recipe_has_a_native_black_white_mask_path(self):
        entry = next(entry for entry in builder.bundled_entries() if entry.get("model") == "image-inpaint")
        node = creative.creative_mappings([entry])[0][creative.media_node_id(entry)]
        workflow = builder.workflow_for(entry, node, "Inpaint")
        conversion = next(node for node in workflow["nodes"] if node["type"] == "ImageToMask")
        self.assertEqual(conversion["widgets_values"], ["red"])
        mask_link = next(link for link in workflow["links"] if link[1] == conversion["id"])
        self.assertEqual(mask_link[-1], "MASK")
        target = workflow["nodes"][0]["inputs"][mask_link[4]]
        self.assertEqual(target["name"], "mask")

    def test_effects_pagination_reads_all_records_not_just_first_page(self):
        class Client:
            def __init__(self):
                self.pages = []

            def _request(self, method, path, *, params):
                self.pages.append(params["page"])
                return {"total": 3, "templates": [{"key": "a"}, {"key": "b"}] if params["page"] == 1 else [{"key": "c"}]}

        client = Client()
        result = effects_sync._fetch_catalog(client, "kling")
        self.assertEqual(client.pages, [1, 2])
        self.assertEqual(len(result["templates"]), 3)

    def test_effects_pagination_repeated_page_is_not_claimed_complete(self):
        class Client:
            def _request(self, method, path, *, params):
                return {"total": 3, "templates": [{"key": "same"}]}

        with self.assertRaises(ValueError):
            effects_sync._fetch_catalog(Client(), "kling")

    def test_signed_asset_links_are_not_bundled(self):
        result = effects_sync._public_metadata({"cover": "https://cdn.example.com/a.png?token=private", "video": "https://cdn.example.com/a.mp4"})
        self.assertIsNone(result["cover"])
        self.assertEqual(result["video"], "https://cdn.example.com/a.mp4")


if __name__ == "__main__":
    unittest.main()
