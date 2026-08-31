import copy
import json
import os

from context_manager import ContextManager
from tools import create_tools, tool_error


class Agent:
    def __init__(
        self,
        llm,
        max_steps=20,
        workspace=".",
        denied_drives=None,
        max_tool_calls=40,
        max_consecutive_errors=5,
        max_context_tokens=16000,
        max_recent_groups=12,
        reserved_tokens=4000,
    ):
        self.llm = llm
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_consecutive_errors = max_consecutive_errors

        self.tools = create_tools(
            os.path.abspath(workspace),
            denied_drives,
        )

        self.system_message = {
            "role": "system",
            "content": (
                "You are a coding agent. "
                "You can read and write files, inspect directories, "
                "and execute commands using the provided tools. "
                "Use tools when necessary to complete the user's task."
            ),
        }

        self.messages = [copy.deepcopy(self.system_message)]

        self.context_manager = ContextManager(
            max_context_tokens=max_context_tokens,
            max_recent_groups=max_recent_groups,
            reserved_tokens=reserved_tokens,
        )

        self.tool_schemas = [tool.get_schema() for tool in self.tools.values()]

    def _is_tool_error(self, result):
        """判断结构化工具结果是否表示失败。"""
        if isinstance(result, dict):
            payload = result
        else:
            try:
                payload = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                # 兼容尚未结构化的旧工具结果
                return str(result).startswith("Error:")
        return payload.get("ok") is False

    def _serialize_tool_result(self, result):
        """确保 Tool Result 是 API 接受的字符串。"""
        if isinstance(result, str):
            return result

        return json.dumps(result, ensure_ascii=False)

    def _append_skipped_tool_results(
        self,
        tool_calls,
        start_index,
        error_type,
        message,
    ):
        """
        给尚未执行的 Tool Call 补充结果。
        Assistant 一次可能返回多个 Tool Call。即使中途终止，
        也要为剩余调用添加 Tool Result，保证消息历史完整。
        """
        for tool_call in tool_calls[start_index:]:
            skipped_result = tool_error(
                tool_call.function.name,
                error_type,
                message,
                executed=False,
            )
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(skipped_result, ensure_ascii=False),
                }
            )

    # 类消息转换方法
    def _assistant_message_to_dict(
        self,
        response,
    ):
        message = {
            "role": "assistant",
            "content": response.content,
        }

        if response.tool_calls:
            tool_calls = []

            for tool_call in response.tool_calls:
                if hasattr(tool_call, "model_dump"):
                    tool_call_data = tool_call.model_dump(exclude_none=True)

                else:
                    tool_call_data = {
                        "id": tool_call.id,
                        "type": getattr(
                            tool_call,
                            "type",
                            "function",
                        ),
                        "function": {
                            "name": (tool_call.function.name),
                            "arguments": (tool_call.function.arguments),
                        },
                    }

                tool_calls.append(tool_call_data)

            message["tool_calls"] = tool_calls

        return message

    # 上下文控制方法
    def reset_context(self):
        self.context_manager.reset()

        self.messages = [copy.deepcopy(self.system_message)]

    def snapshot_context(self):
        return {
            "messages": copy.deepcopy(self.messages),
            "context_manager": (self.context_manager.snapshot()),
        }

    def restore_context(self, snapshot):
        self.messages = copy.deepcopy(snapshot["messages"])
        self.context_manager.restore(snapshot["context_manager"])

    def _stop_agent(self, message):
        """
        记录控制器产生的停止消息，保证下一次用户输入时，
        历史不是以未完成的 Tool Result 结尾。
        """
        self.messages.append(
            {
                "role": "assistant",
                "content": message,
            }
        )

        return message

    def run(self, task: str):
        self.messages.append({"role": "user", "content": task})

        total_tool_calls = 0
        consecutive_errors = 0

        for step in range(1, self.max_steps + 1):
            # 每次调用模型前压缩上下文
            self.messages = self.context_manager.compact(self.messages)

            response = self.llm.chat(
                self.messages,
                self.tool_schemas,
            )

            # SDK对象转换为普通字典后保存
            self.messages.append(self._assistant_message_to_dict(response))

            tool_calls = response.tool_calls or []

            # 如果没有工具调用，说明模型已经给出最终回答
            if not tool_calls:
                if response.content:
                    return response.content

                return self._stop_agent(
                    "Agent stopped because the model returned "
                    "neither content nor tool calls."
                )

            # 执行所有工具调用
            for index, tool_call in enumerate(tool_calls):
                # 终止条件一：总工具调用次数
                if total_tool_calls >= self.max_tool_calls:
                    message = (
                        "Agent stopped because the maximum number "
                        f"of tool calls ({self.max_tool_calls}) "
                        "was reached."
                    )

                    self._append_skipped_tool_results(
                        tool_calls,
                        index,
                        "tool_call_limit",
                        message,
                    )

                    return self._stop_agent(message)

                # 执行工具
                total_tool_calls += 1
                result = self._execute_tool(tool_call)
                serialized_result = self._serialize_tool_result(result)

                # 工具执行结果必须重新传给模型
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": serialized_result,
                    }
                )

                # 统计连续错误次数
                if self._is_tool_error(result):
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0

                # 终止条件三：连续错误次数
                if consecutive_errors >= self.max_consecutive_errors:
                    message = (
                        "Agent stopped after "
                        f"{consecutive_errors} consecutive "
                        "tool errors."
                    )

                    # 当前调用已经有结果，只补充后面的调用
                    self._append_skipped_tool_results(
                        tool_calls,
                        index + 1,
                        "consecutive_error_limit",
                        message,
                    )

                    return self._stop_agent(message)

        return self._stop_agent(
            "Agent stopped after reaching the maximum "
            f"number of model steps ({self.max_steps}). "
            f"Total tool calls executed: {total_tool_calls}."
        )

    def _execute_tool(self, tool_call):
        tool_name = tool_call.function.name

        try:
            arguments = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError) as error:
            result = tool_error(
                tool_name,
                "invalid_json",
                f"Invalid tool arguments: {error}",
            )
            return json.dumps(result, ensure_ascii=False)

        if not isinstance(arguments, dict):
            result = tool_error(
                tool_name,
                "invalid_arguments",
                "Tool arguments must be a JSON object.",
            )
            return json.dumps(result, ensure_ascii=False)

        tool = self.tools.get(tool_name)

        if tool is None:
            result = tool_error(
                tool_name,
                "unknown_tool",
                f"Unknown tool: {tool_name}",
            )
            return json.dumps(result, ensure_ascii=False)

        try:
            result = tool.execute(**arguments)

            if not isinstance(result, dict):
                result = {
                    "ok": True,
                    "tool": tool_name,
                    "result": str(result),
                }

        except TypeError as error:
            result = tool_error(
                tool_name,
                "invalid_arguments",
                str(error),
            )

        except Exception as error:
            result = tool_error(
                tool_name,
                type(error).__name__,
                str(error),
            )

        try:
            return json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            fallback = tool_error(
                tool_name,
                "serialization_error",
                str(error),
            )
            return json.dumps(fallback, ensure_ascii=False)
