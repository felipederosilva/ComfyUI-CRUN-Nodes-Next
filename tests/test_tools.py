import unittest

from crun.tools import list_tools


class ToolsTests(unittest.TestCase):
    def test_cards_are_unique_explicitly_planned_and_officially_linked(self):
        tools = list_tools()
        self.assertGreaterEqual(len(tools), 8)
        self.assertEqual(len(tools), len({tool["id"] for tool in tools}))
        for tool in tools:
            self.assertEqual(tool["status"], "planned")
            self.assertTrue(tool["documentation_url"].startswith("https://docs.crun.ai/ai-tools/"))
            self.assertTrue(tool["description"])

    def test_callers_cannot_mutate_the_shared_index(self):
        tools = list_tools()
        tools[0]["status"] = "implemented"
        self.assertEqual(list_tools()[0]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
