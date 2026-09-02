import json
import unittest
from types import SimpleNamespace

from agent import Agent


def make_tool_call(call_id, name="unknown", arguments="{}"):
    tool_call = SimpleNamespace(
        id=str(call_id),
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )
    tool_call.model_dump = lambda exclude_none=True: {
        "id": tool_call.id,
        "type": tool_call.type,
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }
    return tool_call


class SequenceLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, messages, tools):
        response = self.responses[self.calls]
        self.calls += 1
        return response


class SuccessTool:
    def execute(self):
        return {"ok": True, "tool": "success"}


class AgentTests(unittest.TestCase):
    def test_run_emits_realtime_progress_events(self):
        tool_call = make_tool_call("call-1", "success")
        llm = SequenceLLM(
            [
                SimpleNamespace(content=None, tool_calls=[tool_call]),
                SimpleNamespace(content="done", tool_calls=[]),
            ]
        )
        agent = Agent(llm)
        agent.tools["success"] = SuccessTool()
        events = []

        result = agent.run("test", event_callback=events.append)

        self.assertEqual(result, "done")
        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "task_started")
        self.assertIn("model_started", event_types)
        self.assertIn("model_finished", event_types)
        self.assertIn("tool_started", event_types)
        self.assertIn("tool_finished", event_types)
        tool_result = next(
            event for event in events if event["type"] == "tool_finished"
        )
        self.assertTrue(tool_result["ok"])

    def test_sdk_tool_call_is_saved_as_plain_dictionary(self):
        tool_call = make_tool_call("call-1")
        llm = SequenceLLM(
            [
                SimpleNamespace(content=None, tool_calls=[tool_call]),
                SimpleNamespace(content="done", tool_calls=[]),
            ]
        )
        agent = Agent(llm)

        self.assertEqual(agent.run("test"), "done")

        assistant_message = next(
            message
            for message in agent.messages
            if message["role"] == "assistant" and message.get("tool_calls")
        )
        self.assertIsInstance(assistant_message["tool_calls"][0], dict)
        self.assertEqual(assistant_message["tool_calls"][0]["id"], "call-1")

    def test_reasoning_content_is_preserved_for_tool_follow_up(self):
        tool_call = make_tool_call("call-1")
        response = SimpleNamespace(
            content=None,
            reasoning_content="internal reasoning",
            tool_calls=[tool_call],
        )
        agent = Agent(SequenceLLM([]))

        message = agent._assistant_message_to_dict(response)

        self.assertEqual(message["reasoning_content"], "internal reasoning")

    def test_context_snapshot_can_be_restored(self):
        agent = Agent(SequenceLLM([]))
        snapshot = agent.snapshot_context()

        agent.messages.append({"role": "user", "content": "temporary"})
        agent.context_manager.summary["user_requests"].append("temporary")
        agent.restore_context(snapshot)

        self.assertEqual(agent.messages, [agent.system_message])
        self.assertEqual(agent.context_manager.summary["user_requests"], [])

    def test_stops_after_five_consecutive_tool_errors(self):
        tool_calls = [make_tool_call(index) for index in range(6)]
        agent = Agent(
            SequenceLLM([SimpleNamespace(content=None, tool_calls=tool_calls)]),
            max_consecutive_errors=5,
        )

        result = agent.run("trigger errors")

        self.assertIn("5 consecutive", result)
        tool_messages = [
            message for message in agent.messages if message["role"] == "tool"
        ]
        self.assertEqual(len(tool_messages), 6)
        self.assertFalse(json.loads(tool_messages[-1]["content"])["executed"])

    def test_executes_no_more_than_forty_tool_calls(self):
        tool_calls = [make_tool_call(index, "success") for index in range(41)]
        agent = Agent(
            SequenceLLM([SimpleNamespace(content=None, tool_calls=tool_calls)]),
            max_tool_calls=40,
        )
        agent.tools["success"] = SuccessTool()

        result = agent.run("trigger limit")

        self.assertIn("40", result)
        payloads = [
            json.loads(message["content"])
            for message in agent.messages
            if message["role"] == "tool"
        ]
        self.assertEqual(len(payloads), 41)
        self.assertEqual(
            sum(payload.get("executed") is False for payload in payloads),
            1,
        )


if __name__ == "__main__":
    unittest.main()
