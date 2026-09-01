import unittest
from types import SimpleNamespace

from reviewer import ReviewerAgent


class FinalResponseLLM:
    def chat(self, messages, tools):
        return SimpleNamespace(
            content="审查结论：通过",
            tool_calls=[],
        )


class ReviewerAgentTests(unittest.TestCase):
    def test_reviewer_has_no_direct_file_modification_tools(self):
        reviewer = ReviewerAgent(FinalResponseLLM())

        self.assertEqual(
            set(reviewer.tools),
            {"read_file", "list_files", "run_command"},
        )
        self.assertIsInstance(
            reviewer.system_message["content"],
            str,
        )

    def test_review_builds_an_independent_review_task(self):
        reviewer = ReviewerAgent(FinalResponseLLM())

        result = reviewer.review(
            original_task="修复排序代码",
            coding_result="已经修复并通过测试",
        )

        self.assertEqual(result, "审查结论：通过")
        user_message = next(
            message
            for message in reviewer.messages
            if message["role"] == "user"
        )
        self.assertIn("修复排序代码", user_message["content"])
        self.assertIn("已经修复并通过测试", user_message["content"])


if __name__ == "__main__":
    unittest.main()
