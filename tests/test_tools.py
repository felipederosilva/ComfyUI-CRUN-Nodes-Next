import json
import unittest
from unittest.mock import patch

from crun import tools as tools_module
from crun.catalog import BUNDLED_PATH
from crun.tools import list_tools


class ToolsTests(unittest.TestCase):
    def setUp(self):
        # Tests are based on the shipped snapshot, not another Comfy profile's
        # refreshed runtime cache or provider account.
        snapshot = json.loads(BUNDLED_PATH.read_text(encoding="utf-8"))
        self.catalog_patch = patch.object(tools_module, "list_catalog", return_value=snapshot)
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)

    def test_cards_match_documented_tool_nodes_and_official_links(self):
        tools = list_tools()
        self.assertEqual(len(tools), 18)
        self.assertEqual(len(tools), len({tool["id"] for tool in tools}))
        for tool in tools:
            self.assertEqual(tool["status"], "node_available")
            self.assertTrue(tool["documentation_url"].startswith("https://docs.crun.ai/"))
            self.assertTrue(tool["description"])
            self.assertEqual(tool["node_menu"], f"CRUN Next/AI Tools/{tool['provider']}")
            self.assertTrue(tool["node_display_name"].startswith("CRUN • "))
            self.assertEqual(tool["default_mode"], "prepare")
            self.assertFalse(tool["workspace_execution_enabled"])
            self.assertIsInstance(tool["input_schema"], dict)

    def test_callers_cannot_mutate_the_shared_index(self):
        tools = list_tools()
        tools[0]["status"] = "implemented"
        tools[0]["input_schema"].clear()
        self.assertEqual(list_tools()[0]["status"], "node_available")
        self.assertTrue(list_tools()[0]["input_schema"])

    def test_index_follows_catalog_instead_of_static_planned_cards(self):
        snapshot = {"entries": [
            {"id": "one", "model": "new-tool", "title": "New Tool", "kind": "tool", "inputs": {"description": "New operation", "properties": {"image": {"type": "string"}}}},
            {"id": "two", "model": "not-tool", "title": "Image Model", "kind": "image"},
        ]}
        with patch.object(tools_module, "list_catalog", return_value=snapshot) as load:
            tools = list_tools()
        load.assert_called_once_with()
        self.assertEqual([tool["model"] for tool in tools], ["new-tool"])
        self.assertEqual(tools[0]["description"], "New operation")

    def test_rights_sensitive_tools_remain_explicit(self):
        sensitive = [tool for tool in list_tools() if tool["rights_sensitive"]]
        self.assertTrue(sensitive)
        for tool in sensitive:
            self.assertIn("authorized", tool["usage_note"])

    def test_empty_catalog_is_empty_not_synthetic(self):
        self.assertEqual(list_tools({"entries": []}), [])


if __name__ == "__main__":
    unittest.main()
