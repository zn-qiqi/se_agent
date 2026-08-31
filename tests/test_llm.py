import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openai import APIConnectionError

from llm import LLM, LLMRequestError


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


def make_llm(responses, max_retries=0):
    completions = FakeCompletions(responses)
    llm = LLM.__new__(LLM)
    llm.model = "test-model"
    llm.max_retries = max_retries
    llm.request_timeout = 12
    llm.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )
    return llm, completions


class LLMTests(unittest.TestCase):
    def test_chat_forwards_model_tools_and_timeout(self):
        message = SimpleNamespace(content="done", tool_calls=[])
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        llm, completions = make_llm([response])
        tools = [{"type": "function"}]

        result = llm.chat([{"role": "user", "content": "test"}], tools)

        self.assertIs(result, message)
        request = completions.calls[0]
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["tools"], tools)
        self.assertEqual(request["tool_choice"], "auto")
        self.assertEqual(request["timeout"], 12)

    def test_connection_error_is_retried_without_real_network_access(self):
        connection_error = APIConnectionError(request=SimpleNamespace())
        message = SimpleNamespace(content="recovered", tool_calls=[])
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        llm, completions = make_llm(
            [connection_error, response],
            max_retries=1,
        )

        with patch("llm.time.sleep") as sleep:
            result = llm.chat([], [])

        self.assertIs(result, message)
        self.assertEqual(len(completions.calls), 2)
        sleep.assert_called_once_with(1)

    def test_empty_choices_raise_a_clear_error(self):
        llm, _ = make_llm([SimpleNamespace(choices=[])])

        with self.assertRaisesRegex(LLMRequestError, "no choices"):
            llm.chat([], [])


if __name__ == "__main__":
    unittest.main()
