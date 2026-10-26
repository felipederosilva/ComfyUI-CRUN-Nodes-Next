import json
import os
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from crun import creative, jobs
from crun.client import CRUNError
import creative_nodes
import generated_nodes
import family_nodes


class CreativeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.env = patch.dict(os.environ, {"CRUN_NEXT_CONFIG_DIR": self.directory.name, "CRUN_API_KEY": "synthetic-crun-creative-key-not-live"})
        self.env.start()
        self.requests = patch("requests.sessions.Session.request", side_effect=AssertionError("No network allowed"))
        self.requests.start()
        self.count = 0
        self.media, self.mask = object(), object()
        self.details = patch("crun.results.load_result_details", return_value={"media": self.media, "mask": self.mask,
            "url": "https://cdn.example.com/fixture", "actual_credits": 3.5, "task_id": "fixture_task", "local_path": "/synthetic/local/media"})
        self.loader = self.details.start()
        self.balance = patch.object(creative, "CRUNClient")
        self.client = self.balance.start()
        self.client.return_value.get_balance.return_value = 96.5

    def tearDown(self):
        self.balance.stop()
        self.details.stop()
        self.requests.stop()
        self.env.stop()
        self.directory.cleanup()

    def delegate(self, **inputs):
        mode = inputs.get("crun_mode", "prepare")
        receipt = {"mode": mode, "status": "draft", "model": "test/model", "payload": {"model": "test/model", "input": {"prompt": inputs.get("prompt", "fictional")}},
                   "errors": [], "warnings": [], "task_id": "", "credits": -1, "credit_limit": inputs.get("crun_max_credits", 0)}
        if mode == "estimate":
            receipt.update(status="estimated", credits=4)
        if mode == "generate":
            jobs.submission_starting()
            self.count += 1
            task_id = f"fixture_task_{self.count}"
            jobs.submission_received(task_id)
            receipt.update(status="submitted", task_id=task_id, credits=4)
        return {"result": (json.dumps(receipt), receipt["task_id"], receipt["credits"])}

    def run_video(self, **controls):
        return creative.run_creative(self.delegate, {"crun_mode": "generate", "crun_max_credits": 100, "prompt": "fictional"}, "video", **controls)

    def test_native_completion_has_distinct_quote_actual_and_remaining(self):
        response = self.run_video()
        self.assertIs(response["result"][0], self.media)
        self.assertEqual(response["result"][1:6], ("https://cdn.example.com/fixture", "fixture_task_1", 4.0, 3.5, 96.5))
        self.assertEqual(response["receipt"]["status"], "completed")
        self.assertEqual(self.count, 1)

    def test_image_has_native_mask_and_audio_has_native_audio(self):
        image = creative.run_creative(self.delegate, {"crun_mode": "generate", "prompt": "image"}, "image")
        self.assertEqual(image["result"][:2], (self.media, self.mask))
        audio = creative.run_creative(self.delegate, {"crun_mode": "generate", "prompt": "audio"}, "audio")
        self.assertIs(audio["result"][0], self.media)

    def test_prepare_and_estimate_never_submit_or_load_results(self):
        for mode in ("prepare", "estimate"):
            result = creative.run_creative(self.delegate, {"crun_mode": mode}, "video")
            self.assertEqual(result["receipt"]["mode"], mode)
            self.assertEqual(result["receipt"]["task_id"], "")
        self.assertEqual(self.count, 0)
        self.loader.assert_not_called()
        self.client.assert_not_called()
        self.assertFalse(jobs._path().exists())

    def test_same_take_reuses_persisted_task_and_positive_cap_is_retained(self):
        self.run_video()
        response = self.run_video()
        self.assertEqual(self.count, 1)
        self.assertEqual(response["receipt"]["task_id"], "fixture_task_1")
        self.assertEqual(response["receipt"]["status"], "resumed")
        self.assertEqual(response["receipt"]["credit_limit"], 100)
        records = json.loads(jobs._path().read_text())["jobs"]
        self.assertEqual(len(records), 1)
        self.assertEqual(next(iter(records.values()))["status"], "completed")

    def test_new_take_intentionally_submits_once_more(self):
        self.run_video(take=0)
        self.run_video(take=1)
        self.run_video(take=1)
        self.assertEqual(self.count, 2)

    def test_two_concurrent_requests_for_same_take_submit_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_video(), range(2)))
        self.assertEqual(self.count, 1)
        self.assertEqual({r["receipt"]["task_id"] for r in results}, {"fixture_task_1"})

    def test_separate_process_cannot_acquire_an_active_submission(self):
        code = "from crun import jobs; from crun.client import CRUNError\ntry:\n with jobs.submission_lock(): print('ACQUIRED')\nexcept CRUNError:\n print('BLOCKED')"
        with jobs.submission_lock():
            child = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(child.stdout.strip(), "BLOCKED")

    def test_retrieval_failure_keeps_id_and_next_run_resumes(self):
        self.loader.side_effect = CRUNError("Task fixture_task_1 timed out; retry retrieval.")
        first = self.run_video()
        self.assertEqual(first["receipt"]["status"], "failed")
        self.assertEqual(first["receipt"]["task_id"], "fixture_task_1")
        self.loader.side_effect = None
        second = self.run_video()
        self.assertIs(second["result"][0], self.media)
        self.assertEqual(self.count, 1)

    def test_unknown_submission_does_not_retry(self):
        def unknown(**inputs):
            if inputs.get("crun_mode") == "generate":
                jobs.submission_starting()
                self.count += 1
                raise CRUNError("Ambiguous transport failure")
            return self.delegate(**inputs)
        inputs = {"crun_mode": "generate"}
        creative.run_creative(unknown, inputs, "video")
        second = creative.run_creative(unknown, inputs, "video")
        self.assertEqual(self.count, 1)
        self.assertEqual(second["receipt"]["status"], "failed")
        self.assertIn("unknown", " ".join(second["receipt"]["errors"]))
        self.loader.assert_not_called()

    def test_manual_resume_does_not_read_original_media_or_submit(self):
        def forbidden(**kwargs):
            raise AssertionError("Recovery must not access original references")
        result = creative.run_creative(forbidden, {"crun_mode": "generate"}, "video", resume_task_id="existing_task")
        self.assertIs(result["result"][0], self.media)
        self.assertEqual(self.count, 0)
        self.loader.assert_called_once_with("existing_task", kind="video", result_index=0, timeout_seconds=1200, poll_interval=3)

    def test_local_draft_errors_block_generation_and_are_visible(self):
        def invalid(**kwargs):
            return {"result": (json.dumps({"mode": "prepare", "errors": ["input.image: required."], "task_id": ""}), "", -1)}
        result = creative.run_creative(invalid, {"crun_mode": "generate"}, "image")
        self.assertEqual(result["receipt"]["validation_errors"], ["input.image: required."])
        self.assertEqual(self.count, 0)
        self.loader.assert_not_called()

    def test_completed_media_survives_balance_refresh_failure(self):
        self.client.return_value.get_balance.side_effect = CRUNError("Unavailable")
        result = self.run_video()
        self.assertIs(result["result"][0], self.media)
        self.assertEqual(result["result"][5], -1)

    def test_journal_contains_no_key_prompt_or_reference_url(self):
        self.run_video()
        text = jobs._path().read_text()
        for forbidden in ("synthetic-crun-creative-key-not-live", "fictional", "https://"):
            self.assertNotIn(forbidden, text)

    def test_different_credentials_do_not_reuse_other_account_job(self):
        self.run_video()
        with patch.dict(os.environ, {"CRUN_API_KEY": "another-synthetic-account-key"}):
            self.run_video()
        self.assertEqual(self.count, 2)

    def test_corrupt_history_stops_before_submission(self):
        jobs._path().write_text("broken")
        with self.assertRaises(CRUNError):
            self.run_video()
        self.assertEqual(self.count, 0)

    def test_paid_record_without_task_id_fails_closed(self):
        key = jobs.request_key({"model": "test/model", "input": {"prompt": "fictional"}}, 0)
        jobs.save(key, {"status": "submitted", "task_id": ""})
        with self.assertRaises(CRUNError):
            self.run_video()
        self.assertEqual(self.count, 0)

    def test_completed_task_mapping_is_never_evicted_for_newer_jobs(self):
        original = jobs.request_key({"first": "original"}, 0)
        jobs.save(original, {"status": "completed", "task_id": "first_paid_task"})
        records = jobs._read()
        for index in range(2001):
            key = jobs.request_key({"fixture": index}, 0)
            records[key] = {"status": "completed", "task_id": f"fixture_{index}"}
        jobs._path().write_text(json.dumps({"version": 1, "jobs": records}))
        jobs.save(jobs.request_key({"next": "new"}, 0), {"status": "preflight"})
        self.assertEqual(jobs.find(original)["task_id"], "first_paid_task")

    def test_invalid_recovery_controls_stop_before_client(self):
        for controls in ({"take": True}, {"take": -1}, {"resume_task_id": "bad/id"}, {"timeout_seconds": -1}, {"poll_interval": 0}, {"result_index": 100}):
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                self.run_video(**controls)
        self.assertEqual(self.count, 0)


class CreativeDefinitionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = generated_nodes.all_entries()
        cls.classes, cls.names = creative_nodes.creative_mappings(cls.entries)

    def test_all_new_creative_nodes_expose_native_media_without_output_target(self):
        for node in self.classes.values():
            self.assertIn(node.RETURN_TYPES[0], {"IMAGE", "VIDEO", "AUDIO"})
            self.assertFalse(node.OUTPUT_NODE)
            self.assertIn("actual_credits", node.RETURN_NAMES)
            self.assertIn("credits_left", node.RETURN_NAMES)

    def test_new_ids_do_not_change_existing_graph_contracts(self):
        legacy, _ = generated_nodes.generated_mappings(self.entries)
        families, _ = family_nodes.family_node_mappings(self.entries)
        self.assertFalse(set(self.classes) & (set(legacy) | set(families)))
        for node in list(legacy.values()) + list(families.values()):
            self.assertEqual(node.RETURN_NAMES, ("result_json", "task_id", "credits"))

    def test_saved_v032_family_widget_positions_and_caps_remain_stable(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/legacy-family-widget-order.json").read_text())
        families, _ = family_nodes.family_node_mappings(self.entries)
        for identifier, expected in fixture.items():
            definitions = families[identifier].INPUT_TYPES()
            actual = [name for section in ("required", "optional") for name, spec in definitions.get(section, {}).items()
                      if not (isinstance(spec[0], str) and spec[0] in {"IMAGE", "MASK", "VIDEO", "AUDIO"})]
            self.assertEqual(actual, expected, identifier)

    def test_unknown_effect_output_is_not_guessed_as_video(self):
        self.assertIsNone(creative_nodes.output_kind({"kind": "effect", "model": "vidu/template", "generation_supported": True}))
        self.assertEqual(creative_nodes.output_kind({"kind": "effect", "model": "vidu/template", "generation_supported": True, "effect_metadata": {"raw": {"output_type": "image"}}}), "image")

    def test_motion_control_and_seedance_native_references_reach_creative_families(self):
        motion = self.classes["CRUN_Next_Studio_Kling_Motion_Control"].INPUT_TYPES()
        self.assertTrue(any(s[0] == "VIDEO" for s in motion["optional"].values()))
        seedance = self.classes["CRUN_Next_Studio_Seedance_Reference_to_Video"].INPUT_TYPES()
        self.assertTrue(any(s[0] == "AUDIO" for s in seedance["optional"].values()))
        self.assertEqual(seedance["optional"]["take"][1]["default"], 0)

    def test_motion_quality_names_translate_to_documented_wire_values(self):
        node = self.classes["CRUN_Next_Studio_Kling_Motion_Control"]
        self.assertEqual(node.INPUT_TYPES()["required"]["mode"][0], ["Standard (720p)", "Professional (1080p)"])
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Prepare is offline")):
            response = node().execute(crun_mode="prepare", mode="Professional (1080p)")
        receipt = json.loads(response["ui"]["text"][0])
        self.assertEqual(receipt["payload"]["input"]["mode"], "pro")

    def test_explicit_resume_does_not_request_native_reference_evaluation(self):
        node = self.classes["CRUN_Next_Studio_Kling_Motion_Control"]()
        native = {name: None for name, spec in node.INPUT_TYPES()["optional"].items()
                  if isinstance(spec[0], str) and spec[0] in {"IMAGE", "VIDEO", "AUDIO", "MASK"}}
        self.assertTrue(native)
        self.assertEqual(node.check_lazy_status(crun_mode="generate", resume_task_id="existing_task", **native), [])
        self.assertEqual(set(node.check_lazy_status(crun_mode="generate", **native)), set(native))


if __name__ == "__main__":
    unittest.main()
