import queue
import unittest

from ui import CodingAgentUI


class FakeCodingAgent:
    def snapshot_context(self):
        return {"messages": [], "context_manager": {}}

    def run(self, task, event_callback=None):
        if event_callback:
            event_callback({"type": "task_started"})
        return f"完成：{task}"


class FakeReviewerAgent:
    def __init__(self):
        self.received = None

    def review(self, original_task, coding_result):
        self.received = (original_task, coding_result)
        return "审查结论：通过"


class UILogicTests(unittest.TestCase):
    def test_worker_runs_coder_then_reviewer(self):
        ui = CodingAgentUI.__new__(CodingAgentUI)
        ui.agent = FakeCodingAgent()
        ui.reviewer = FakeReviewerAgent()
        ui.results = queue.Queue()

        ui._run_agent("创建示例")

        results = []
        while not ui.results.empty():
            results.append(ui.results.get_nowait())

        self.assertEqual(
            [role for role, _ in results],
            ["progress", "coding_result", "reviewer"],
        )
        self.assertEqual(
            ui.reviewer.received,
            ("创建示例", "完成：创建示例"),
        )


if __name__ == "__main__":
    unittest.main()
