import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
NAME = "crun_next_test_package"
if NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(NAME, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[NAME] = package
    spec.loader.exec_module(package)
nodes = sys.modules[NAME + ".nodes"]


class NodeTests(unittest.TestCase):
    def test_every_node_has_separate_namespace_and_no_key_widget(self):
        self.assertGreaterEqual(len(nodes.NODE_CLASS_MAPPINGS), 7)
        for name, klass in nodes.NODE_CLASS_MAPPINGS.items():
            self.assertTrue(name.startswith("CRUN_Next_"))
            self.assertTrue(callable(getattr(klass(), klass.FUNCTION)))
            self.assertNotIn("api_key", json.dumps(klass.INPUT_TYPES()))

    def test_balance_node_uses_client_only_on_execution(self):
        with patch.object(nodes, "CRUNClient") as client:
            client.return_value.get_balance.return_value = 15.25
            result = nodes.CRUNCredits().check()
        self.assertEqual(result["result"][0], 15.25)

    def test_task_credit_state_is_not_confused(self):
        for status, expected in (("pending", "reserved"), ("running", "reserved"), ("success", "actual"), ("failed", "actual"), ("unexpected", "unknown")):
            with patch.object(nodes, "CRUNClient") as client:
                client.return_value.get_task.return_value = {"status": status, "credits": 3}
                output = nodes.CRUNInspectTask().check("task_1")["result"]
            self.assertEqual(output[2], expected)

    def test_missing_task_cost_is_unavailable_not_zero(self):
        with patch.object(nodes, "CRUNClient") as client:
            client.return_value.get_task.return_value = {"status": "success"}
            output = nodes.CRUNInspectTask().check("task_1")["result"]
        self.assertEqual(output[1:3], (-1.0, "unavailable"))

    def test_boolean_cost_is_not_a_valid_receipt(self):
        for amount in (True, False):
            with patch.object(nodes, "CRUNClient") as client:
                client.return_value.get_task.return_value = {"status": "success", "credits": amount}
                with self.assertRaises(ValueError):
                    nodes.CRUNInspectTask().check("task_1")

    def test_draft_effect_plan_cannot_execute(self):
        plan, raw = nodes.CRUNPrepareEffectPlan().prepare("kling", "test-template", '["https://example.com/input.png"]', "{}")
        self.assertFalse(plan["execution_enabled"])
        self.assertFalse(plan["ready_to_submit"])

    def test_tools_catalog_is_metadata_for_prepare_default_nodes(self):
        output = nodes.CRUNToolsCatalog().check()["result"][0]
        self.assertTrue(all(entry["status"] == "node_available" and entry["default_mode"] == "prepare" for entry in json.loads(output)))


if __name__ == "__main__":
    unittest.main()
