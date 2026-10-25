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

    def test_arm_and_budget_required_before_any_provider_call(self):
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            for arm, maximum in ((False, 10), (True, 0), (True, -1), (True, float("nan")), (True, True)):
                with self.assertRaises(ValueError):
                    execution.run_entry(entry(), {"prompt": "Test"}, "generate", arm, maximum)

    def test_invalid_inputs_stop_before_network(self):
        with patch.object(execution, "CRUNClient", side_effect=AssertionError("No network")):
            for values in ({}, {"prompt": "Test", "duration": 20}, {"prompt": "Test", "duration": False}):
                with self.assertRaises(ValueError):
                    execution.run_entry(entry(), values, "estimate")

    def test_budget_and_balance_block_submission(self):
        for maximum, balance in ((3, 20), (10, 1)):
            with patch.object(execution, "CRUNClient") as client:
                client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
                client.return_value.get_balance.return_value = balance
                with self.assertRaises(ValueError):
                    execution.run_entry(entry(), {"prompt": "Test"}, "generate", True, maximum)
                client.return_value.create_task.assert_not_called()

    def test_submits_exactly_once_and_returns_recoverable_id(self):
        with patch.object(execution, "CRUNClient") as client, patch.object(execution, "_record") as journal:
            client.return_value.estimate_credits.return_value = {"credits": 4, "estimated": True}
            client.return_value.get_balance.return_value = 20
            client.return_value.create_task.return_value = "test_task_id"
            result = execution.run_entry(entry(), {"prompt": "Test"}, "generate", True, 10)
            client.return_value.create_task.assert_called_once_with("test/model", {"prompt": "Test"})
        self.assertEqual(result["task_id"], "test_task_id")
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
        with tempfile.TemporaryDirectory() as directory:
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
