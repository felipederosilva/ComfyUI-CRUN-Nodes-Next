import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generated_nodes as generated
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
        node = generated.make_node(entry)
        workflow = builder.workflow_for(entry, node, "CRUN • Sample")
        self.assertEqual(workflow["version"], 0.4)
        self.assertEqual(workflow["links"], [])
        graph_node = workflow["nodes"][0]
        self.assertEqual(graph_node["type"], generated.node_id_for(entry))
        self.assertEqual(graph_node["widgets_values"][:3], ["prepare", False, 0])
        self.assertEqual(workflow["nodes"][1]["type"], "Note")
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
        node_ids = {generated.node_id_for(entry) for entry in entries}
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
