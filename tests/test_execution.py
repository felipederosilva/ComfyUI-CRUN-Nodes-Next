import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from crun import execution


def entry():
    return {"id": "fixture", "model": "test/model", "method": "POST", "endpoint": "/api/v1/client/job/CreateTask", "generation_supported": True,
            "request_schema": {"type": "object", "required": ["model", "input"], "properties": {"model": {"type": "string", "const": "test/model"},
            "input": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}, "duration": {"type": "integer", "minimum": 1, "maximum": 10}}}}}}


class ExecutionTests(unittest.TestCase):
    def test_prepare_never_touches_network(self):
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            result = execution.run_entry(entry(), {}, "prepare")
        self.assertEqual(result["status"], "draft")
        self.assertTrue(result["errors"])

    def test_estimate_does_not_submit(self):
        with patch.object(execution, "CRUNClient") as client:
            client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
            result = execution.run_entry(entry(), {"prompt": "Test"}, "estimate")
            client.return_value.create_task.assert_not_called()
        self.assertEqual(result["credit_state"], "estimate")
        self.assertEqual(result["credit_limit"], 0)
        self.assertIsInstance(result["quoted_at"], int)
        self.assertIsNone(result["balance_before"])
        client.return_value.get_balance.assert_not_called()

    def test_invalid_optional_limits_stop_before_any_provider_call(self):
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            for maximum in (-1, float("nan"), float("inf"), True, "10"):
                with self.assertRaises(ValueError):
                    execution.run_entry(entry(), {"prompt": "Test"}, "generate", False, maximum)

    def test_prepare_does_not_upload_or_submit_when_legacy_switches_are_true(self):
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            result = execution.run_entry(entry(), {"prompt": "Test"}, "prepare", True, 0, allow_upload=True)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["task_id"], "")

    def test_generate_action_authorizes_one_submission_without_optional_cap(self):
        with patch.object(execution, "CRUNClient") as client, patch.object(execution, "_record") as journal, patch("builtins.print") as console:
            client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
            client.return_value.get_balance.return_value = 20
            client.return_value.create_task.return_value = "uncapped_fixture_task"
            result = execution.run_entry(entry(), {"prompt": "Test"}, "generate", False, 0, allow_upload=False)
            client.return_value.create_task.assert_called_once_with("test/model", {"prompt": "Test"})
        self.assertEqual(result["task_id"], "uncapped_fixture_task")
        self.assertEqual(result["credit_limit"], 0)
        self.assertEqual(journal.call_count, 2)
        self.assertTrue(any("optional cap disabled" in call.args[0] for call in console.call_args_list))

    def test_estimate_action_uploads_needed_references_without_legacy_checkbox(self):
        native = [{"wire_name": "img_urls", "pngs": [b"fixture png"]}]
        with patch.object(execution, "_native_inputs", return_value=({"prompt": "Test", "img_urls": ["https://crun-next.invalid/local/fixture.png"]}, native, [{"upload_required": True}])):
            with patch.object(execution, "CRUNClient") as client, patch("crun.media.upload_pngs", return_value=["https://cdn.example.com/uploaded.png"]) as upload:
                client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
                result = execution.run_entry(entry(), {"prompt": "Test"}, "estimate", False, 0, native_media=[{}], allow_upload=False)
                upload.assert_called_once_with(client.return_value, [b"fixture png"], allow_upload=True)
                client.return_value.estimate_credits.assert_called_once_with("test/model", {"prompt": "Test", "img_urls": ["https://cdn.example.com/uploaded.png"]})
                client.return_value.create_task.assert_not_called()
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["task_id"], "")

    def test_invalid_inputs_stop_before_network(self):
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            for values in ({}, {"prompt": "Test", "duration": 20}, {"prompt": "Test", "duration": False}):
                with self.assertRaises(ValueError):
                    execution.run_entry(entry(), values, "estimate")

    def test_budget_and_balance_block_submission(self):
        for maximum, balance, status in ((3, 20, "budget_blocked"), (10, 1, "insufficient_balance")):
            with self.subTest(status=status), patch.object(execution, "CRUNClient") as client, patch.object(execution, "_record") as journal:
                client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
                client.return_value.get_balance.return_value = balance
                result = execution.run_entry(entry(), {"prompt": "Test"}, "generate", True, maximum)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["task_id"], "")
                self.assertEqual(result["credits"], 4)
                self.assertEqual(result["credit_limit"], maximum)
                self.assertEqual(result["credit_state"], "estimate")
                self.assertIsInstance(result["quoted_at"], int)
                self.assertIn("No generation was submitted", result["errors"][0])
                if status == "budget_blocked":
                    self.assertIn("limit is 3", result["errors"][0])
                    self.assertIsNone(result["balance_before"])
                    client.return_value.get_balance.assert_not_called()
                else:
                    self.assertEqual(result["balance_before"], 1)
                    self.assertIn("balance is 1", result["errors"][0])
                json.dumps(result, allow_nan=False)
                client.return_value.create_task.assert_not_called()
                journal.assert_not_called()

    def test_reported_hundred_credit_limit_returns_exact_quote_without_spending(self):
        with patch.object(execution, "CRUNClient") as client, patch.object(execution, "_record") as journal, patch("builtins.print") as console:
            client.return_value.estimate_credits.return_value = {"credits": 146.25, "estimated": False}
            result = execution.run_entry(entry(), {"prompt": "Test"}, "generate", True, 100)
            client.return_value.create_task.assert_not_called()
            client.return_value.get_balance.assert_not_called()
            journal.assert_not_called()
        encoded = json.loads(json.dumps(result, allow_nan=False))
        self.assertEqual(encoded["status"], "budget_blocked")
        self.assertEqual(encoded["credits"], 146.25)
        self.assertEqual(encoded["credit_limit"], 100)
        self.assertFalse(encoded["provisional"])
        self.assertIn("146.25", encoded["errors"][0])
        self.assertIn("100", encoded["errors"][0])
        self.assertTrue(any("146.25 CRUN credits" in call.args[0] for call in console.call_args_list))

    def test_submits_exactly_once_and_returns_recoverable_id(self):
        with patch.object(execution, "CRUNClient") as client, patch.object(execution, "_record") as journal:
            client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
            client.return_value.get_balance.return_value = 20
            client.return_value.create_task.return_value = "test_task_id"
            result = execution.run_entry(entry(), {"prompt": "Test"}, "generate", True, 10)
            client.return_value.create_task.assert_called_once_with("test/model", {"prompt": "Test"})
        self.assertEqual(result["task_id"], "test_task_id")
        self.assertEqual(result["balance_before"], 20)
        self.assertEqual(result["credit_limit"], 10)
        self.assertEqual(journal.call_count, 2)
        self.assertTrue(all("payload" not in call.args[0] for call in journal.call_args_list))

    def test_unknown_outcome_never_retries(self):
        with patch.object(execution, "CRUNClient") as client, patch.object(execution, "_record"):
            client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
            client.return_value.get_balance.return_value = 20
            client.return_value.create_task.side_effect = execution.CRUNError("Outcome unknown")
            with self.assertRaises(execution.CRUNError):
                execution.run_entry(entry(), {"prompt": "Test"}, "generate", True, 10)
            self.assertEqual(client.return_value.create_task.call_count, 1)

    def test_unsupported_protocol_is_not_guessed(self):
        record = {**entry(), "endpoint": "/api/v1/chat/completions", "generation_supported": False}
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            with self.assertRaises(ValueError):
                execution.run_entry(record, {"prompt": "Test"}, "generate", True, 10)

    def test_callback_example_is_not_carried_forward(self):
        record = {**entry(), "payload_template": {"callback_url": "https://example.com/callback"}}
        payload, _ = execution.build_payload(record, {"prompt": "Test"})
        self.assertNotIn("callback_url", payload)

    def test_documented_pattern_blocks_invalid_hex_color(self):
        schema = {"type": "string", "pattern": "^[a-fA-F0-9]{6}$"}
        self.assertTrue(execution.validate("ZZZZZZ", schema))
        self.assertEqual(execution.validate("aB1234", schema), [])
        self.assertEqual(execution.validate(None, {**schema, "nullable": True}), [])

    def test_malformed_journal_is_preserved_and_blocks_submission(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            credential = Path(directory) / "credentials.json"
            journal = credential.with_name("tasks.json")
            original = json.dumps({"recovery": "keep"})
            journal.write_text(original, encoding="utf-8")
            with patch.object(execution, "settings_path", return_value=credential):
                with self.assertRaises(execution.CRUNError):
                    execution._record({"status": "submitting"})
            self.assertEqual(journal.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
