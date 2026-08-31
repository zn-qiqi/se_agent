import json
import unittest

from context_manager import SUMMARY_PREFIX, ContextManager, estimate_tokens


def tool_message(tool_name, **payload):
    return {
        "role": "tool",
        "tool_call_id": f"{tool_name}-call",
        "content": json.dumps(
            {"ok": True, "tool": tool_name, **payload},
            ensure_ascii=False,
        ),
    }


class ContextManagerTests(unittest.TestCase):
    def test_compaction_preserves_recent_messages_and_summarizes_old_tools(self):
        manager = ContextManager(
            max_context_tokens=100000,
            max_recent_groups=1,
            min_recent_groups=1,
            reserved_tokens=1000,
        )
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old request"},
            tool_message("read_file", path="old.py"),
            tool_message("write_file", path="new.py"),
            {"role": "user", "content": "current request"},
        ]

        compacted = manager.compact(messages)

        self.assertEqual(compacted[-1]["content"], "current request")
        self.assertIn("old.py", manager.summary["files_read"])
        self.assertIn("new.py", manager.summary["files_modified"])
        summary_messages = [
            message
            for message in compacted
            if isinstance(message.get("content"), str)
            and message["content"].startswith(SUMMARY_PREFIX)
        ]
        self.assertEqual(len(summary_messages), 1)

    def test_tool_call_and_results_are_not_split(self):
        manager = ContextManager(
            max_context_tokens=100000,
            max_recent_groups=1,
            min_recent_groups=1,
            reserved_tokens=1000,
        )
        tool_call = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call-1", "type": "function"}],
        }
        tool_result = tool_message("read_file", path="sample.py")

        groups = manager._group_messages(
            [
                {"role": "user", "content": "request"},
                tool_call,
                tool_result,
            ]
        )

        self.assertEqual(groups[1], [tool_call, tool_result])

    def test_assistant_notes_have_a_bounded_length(self):
        manager = ContextManager(
            max_context_tokens=100000,
            max_recent_groups=1,
            min_recent_groups=1,
            reserved_tokens=1000,
        )
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "assistant", "content": f"note-{index}"}
            for index in range(10)
        )

        manager.compact(messages)

        self.assertLessEqual(len(manager.summary["assistant_notes"]), 6)
        self.assertEqual(manager.summary["assistant_notes"][-1], "note-8")

    def test_snapshot_and_restore_do_not_share_mutable_state(self):
        manager = ContextManager()
        manager.summary["user_requests"].append("original")
        snapshot = manager.snapshot()

        manager.summary["user_requests"].append("changed")
        manager.restore(snapshot)

        self.assertEqual(manager.summary["user_requests"], ["original"])

    def test_token_limit_can_compress_below_preferred_minimum(self):
        manager = ContextManager(
            max_context_tokens=100,
            max_recent_groups=10,
            min_recent_groups=4,
            reserved_tokens=20,
        )
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "user", "content": "x" * 300}
            for _ in range(5)
        )

        compacted = manager.compact(messages)
        conversation_messages = [
            message
            for message in compacted
            if message["role"] != "system"
        ]

        self.assertEqual(len(conversation_messages), 1)
        self.assertEqual(manager.compressed_groups, 4)

    def test_token_estimator_counts_non_ascii_text_conservatively(self):
        self.assertGreater(
            estimate_tokens("中文中文"),
            estimate_tokens("abcd"),
        )

    def test_invalid_token_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "greater than reserved_tokens"):
            ContextManager(
                max_context_tokens=100,
                reserved_tokens=100,
            )


if __name__ == "__main__":
    unittest.main()
