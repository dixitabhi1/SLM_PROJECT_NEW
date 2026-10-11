import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.tools.tolerant_harness import (
    parse_fenced_tool_call,
    run_local_python,
    run_local_sql,
    run_local_search
)

class TestTolerantHarness(unittest.TestCase):
    def test_python_parsing(self):
        text = "Let me compute this.\n```python\nprint(10 * 5)\n```\nWait for output."
        has_tool, name, args, malformed = parse_fenced_tool_call(text)
        self.assertTrue(has_tool)
        self.assertEqual(name, "execute_python")
        self.assertEqual(args["code"], "print(10 * 5)")
        self.assertFalse(malformed)

    def test_sql_parsing_fence_line(self):
        text = "```sql world_1\nSELECT count(*) FROM city;\n```"
        has_tool, name, args, malformed = parse_fenced_tool_call(text)
        self.assertTrue(has_tool)
        self.assertEqual(name, "execute_sql")
        self.assertEqual(args["db_name"], "world_1")
        self.assertIn("SELECT count(*)", args["query"])
        self.assertFalse(malformed)

    def test_sql_parsing_comment_line(self):
        text = "```sql\n-- database: world_1\nSELECT count(*) FROM city;\n```"
        has_tool, name, args, malformed = parse_fenced_tool_call(text)
        self.assertTrue(has_tool)
        self.assertEqual(name, "execute_sql")
        self.assertEqual(args["db_name"], "world_1")
        self.assertIn("SELECT count(*)", args["query"])

    def test_sql_parsing_prompt_fallback(self):
        text = "```sql\nSELECT count(*) FROM city;\n```"
        prompt = "Query the world_1 database for cities."
        has_tool, name, args, malformed = parse_fenced_tool_call(text, prompt_context=prompt)
        self.assertTrue(has_tool)
        self.assertEqual(name, "execute_sql")
        self.assertEqual(args["db_name"], "world_1")

    def test_direct_answer_no_tool(self):
        text = "The answer is straightforward.\n\nFinal Answer: 42"
        has_tool, name, args, malformed = parse_fenced_tool_call(text)
        self.assertFalse(has_tool)
        self.assertFalse(malformed)

    def test_python_execution(self):
        success, out = run_local_python("print(42 + 8)")
        self.assertTrue(success)
        self.assertEqual(out, "50")

    def test_sql_execution(self):
        success, out = run_local_sql("world_1", "SELECT count(*) FROM city WHERE CountryCode = 'USA';")
        self.assertTrue(success)
        self.assertIn("274", out)

if __name__ == "__main__":
    unittest.main()

