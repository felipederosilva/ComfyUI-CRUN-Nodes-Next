import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crun import catalog


def spec(model="vendor/exact-id"):
    return {"openapi": "3.0.0", "info": {"title": "Test"}, "security": [{"ApiKey": []}], "components": {"securitySchemes": {"ApiKey": {"type": "apiKey", "name": "x-api-key", "in": "header"}}, "schemas": {"Input encoded": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string", "maxLength": 300}, "img_urls": {"type": "array", "maxItems": 2, "items": {"type": "string"}}}}}}, "paths": {"/api/v1/client/job/CreateTask": {"post": {"requestBody": {"content": {"application/json": {"schema": {"type": "object", "required": ["model", "input"], "properties": {"model": {"enum": [model]}, "input": {"$ref": "#/components/schemas/Input%20encoded"}}}}}}}}}}


class CatalogTests(unittest.TestCase):
    def test_index_english_only_and_fixed_host(self):
        index = "- [model](/models/google/a.json)\n- [zh](/zh/models/google/a.json)\n- [again](/models/google/a.json)"
        self.assertEqual(catalog.parse_index(index), ["https://docs.crun.ai/models/google/a.json"])
        with self.assertRaises(catalog.CatalogError):
            catalog.parse_index("- [bad](https://attacker.example/models/a.json)")

    def test_exact_wire_id_not_url_slug_and_ref_constraints(self):
        entries = catalog.normalize_openapi(spec("kling/v3"), "https://docs.crun.ai/models/kling/v3-0.json", {"title": "Kling", "section": "Video Models"})
        self.assertEqual(entries[0]["model"], "kling/v3")
        self.assertEqual(entries[0]["kind"], "video")
        self.assertEqual(entries[0]["auth"], ["x-api-key"])
        self.assertEqual(entries[0]["inputs"]["required"], ["prompt"])
        self.assertEqual(entries[0]["inputs"]["properties"]["img_urls"]["maxItems"], 2)
        self.assertFalse(entries[0]["execution_enabled"])

    def test_unresolved_ids_never_invented(self):
        document = spec()
        document["paths"]["/api/v1/client/job/CreateTask"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["model"] = {"type": "string"}
        self.assertEqual(catalog.normalize_openapi(document, "https://docs.crun.ai/models/google/fake-slug.json"), [])

    def test_sora_fallback_is_video_without_index_metadata(self):
        for page, model in (("sora-2", "openai/sora2"), ("sora-2-pro", "openai/sora2-pro"), ("sora-2-pro-storyboard", "openai/sora2-pro-storyboard")):
            with self.subTest(model=model):
                entry = catalog.normalize_openapi(spec(model), f"https://docs.crun.ai/models/sora2/{page}.json")[0]
                self.assertEqual((entry["kind"], entry["group"]), ("video", "Video"))
                self.assertEqual(entry["model"], model)

    def test_status_and_assets_excluded(self):
        for path in ("/models/common/get-task-info.json", "/models/seedance/asset-upload.json", "/templates/kling-template-list.json"):
            self.assertEqual(catalog.normalize_openapi(spec(), "https://docs.crun.ai" + path), [])

    def test_missing_ref_keeps_definition_but_disables_generation(self):
        document = spec()
        document["components"]["schemas"] = {}
        entries = catalog.normalize_openapi(document, "https://docs.crun.ai/models/google/a.json")
        self.assertTrue(entries[0]["inputs"]["unresolved"])
        self.assertFalse(entries[0]["generation_supported"])

    def test_const_and_payload_defaults_do_not_copy_sample_urls(self):
        document = spec()
        root = document["paths"]["/api/v1/client/job/CreateTask"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        root["properties"]["model"] = {"const": "exact/const"}
        field = document["components"]["schemas"]["Input encoded"]["properties"]
        field["prompt"]["example"] = "Sample, not a default"
        field["resolution"] = {"type": "string", "default": "720p"}
        record = catalog.normalize_openapi(document, "https://docs.crun.ai/models/google/a.json")[0]
        self.assertEqual(record["payload_template"], {"model": "exact/const", "input": {"resolution": "720p"}})
        self.assertEqual(record["request_schema"]["properties"]["model"]["const"], "exact/const")

    def test_llm_table_is_documented_not_live(self):
        entries = catalog.parse_llm_table("| Model ID | Provider | Input | Output |\n| :-: | :-: | :-: | :-: |\n| actual-id | Provider | $1 | $2 |")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["model"], "actual-id")
        self.assertEqual(entries[0]["source"], "public_llm_documentation")

    def test_live_list_shape_is_not_media_envelope(self):
        self.assertEqual(catalog.parse_live_llm_models({"object": "list", "data": [{"id": "actual", "owned_by": "Provider"}]})[0]["model"], "actual")
        for payload in ({"code": 200, "data": {}}, {"object": "list", "data": [{}]}):
            with self.assertRaises(catalog.CatalogError):
                catalog.parse_live_llm_models(payload)

    def test_live_merge_keeps_ids_availability_and_prices_separate(self):
        entries = catalog.parse_llm_table("| documented-id | Provider | $1 | $2 |")
        snapshot = {"schema_version": 1, "refreshed_at": "2026-01-01", "entries": entries, "summary": {}, "errors": []}
        result = catalog.merge_live_models(snapshot, [{"model": "new-live-id", "provider": "NewProvider"}])
        self.assertEqual(len(result["entries"]), 2)
        records = {entry["model"]: entry for entry in result["entries"]}
        self.assertEqual(records["new-live-id"]["source"], "authenticated_llm_catalog")
        self.assertNotIn("pricing_note", records["new-live-id"])
        self.assertFalse(records["documented-id"]["account_catalog_listed"])
        self.assertEqual(snapshot["entries"][0]["availability"], "documented_not_account_verified")

    def test_nonstandard_operation_has_no_fabricated_model(self):
        document = {"paths": {"/api/v1/client/job/suno-persona-generate": {"post": {"operationId": "suno-persona-generate", "requestBody": {"content": {"application/json": {"schema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}}}}}}}}}
        entry = catalog.normalize_openapi(document, "https://docs.crun.ai/suno-api/suno-persona-generate.json")[0]
        self.assertIsNone(entry["model"])
        self.assertEqual(entry["operation_id"], "suno-persona-generate")
        self.assertFalse(entry["generation_supported"])
        self.assertNotIn("model", entry["payload_template"])

    def test_cycle_ref_is_bounded(self):
        document = {"components": {"schemas": {"Cycle": {"$ref": "#/components/schemas/Cycle"}}}}
        self.assertTrue(catalog.resolve_schema({"$ref": "#/components/schemas/Cycle"}, document)["unresolved"])

    def test_bom_parsing_and_atomic_refresh(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            destination = Path(directory) / "snapshot.json"
            docs = {
                catalog.INDEX_URL: b"- [test](/models/google/a.json)",
                catalog.MODEL_INDEX_URL: b"### Image Models\n- [A](https://docs.crun.ai/models/google/a.md): A",
                catalog.LLM_LIST_URL: b"| test-llm | Provider | $1 | $2 |",
                "https://docs.crun.ai/models/google/a.json": b"\xef\xbb\xbf" + json.dumps(spec()).encode(),
            }
            with patch.object(catalog, "_fetch", side_effect=lambda url: docs[url]):
                snapshot = catalog.refresh_catalog(destination=destination)
            self.assertEqual(len(snapshot["entries"]), 2)
            self.assertEqual(snapshot["summary"]["unresolved_count"], 0)
            self.assertEqual(json.loads(destination.read_text())["schema_version"], 1)

    def test_read_only_load_never_fetches_network(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.object(catalog, "BUNDLED_PATH", Path(directory) / "bundled.json"), patch.object(catalog, "cache_path", return_value=Path(directory) / "cache.json"), patch.object(catalog, "_fetch", side_effect=AssertionError("No network")):
                self.assertEqual(catalog.list_catalog()["entries"], [])


if __name__ == "__main__":
    unittest.main()
