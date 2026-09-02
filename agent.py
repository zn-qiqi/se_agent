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
        system_prompt=None,
        allowed_tool_names=None,
    ):
        self.llm = llm
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_consecutive_errors = max_consecutive_errors

        all_tools = create_tools(
            os.path.abspath(workspace),
            denied_drives,
        )

        if allowed_tool_names is None:
            self.tools = all_tools
        else:
            allowed_tool_names = set(allowed_tool_names)
            unknown_tools = allowed_tool_names - set(all_tools)

            if unknown_tools:
                raise ValueError(
                    f"Unknown allowed tools: {sorted(unknown_tools)}"
                )

            self.tools = {
                name: tool
                for name, tool in all_tools.items()
                if name in allowed_tool_names
            }

        default_system_prompt = (
            "You are a coding agent. "
            "You can read and write files, inspect directories, "
            "and execute commands using the provided tools. "
            "Use tools when necessary to complete the user's task. "
            "You are running on Windows. "
            "When running compiled programs, use their .exe filename. "
            "Call run_command with the target program directly and put "
            "each argument in the args array. Do not use cmd, powershell, "
            "pwsh, bash, sh, shell operators, or Unix-style ./program commands. "
            "Do not call shell built-ins such as echo, dir, type, copy, "
            "del, set, or cd; run the actual compiler, test runner, or "
            "executable directly. "
            "Use bare program names such as python, g++, git, and pytest "
            "instead of absolute paths on a denied drive."
        )

        self.system_message = {
            "role": "system",
            "content": system_prompt or default_system_prompt,
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

    def _emit_event(self, callback, event_type, **data):
        """发送运行事件；界面回调失败不能中断 Agent。"""
        if callback is None:
            return

        try:
            callback({"type": event_type, **data})
        except Exception:
            pass

    def _describe_tool_call(self, tool_call):
        """生成适合界面显示的精简参数说明。"""
        try:
            arguments = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            return "参数不是有效 JSON"

        if not isinstance(arguments, dict):
            return "参数格式错误"

        tool_name = tool_call.function.name
        path = arguments.get("path")

        if tool_name == "write_file":
            content = arguments.get("content", "")
            return f"{path} · 写入 {len(str(content))} 个字符"

        if tool_name == "edit_file":
            return f"{path} · 局部替换"

        if tool_name == "read_file":
            offset = arguments.get("offset", 0)
            return f"{path} · 从字符 {offset} 开始"

        if tool_name == "list_files":
            return str(path or ".")

        if tool_name == "run_command":
            command_args = arguments.get("args", [])
            if not isinstance(command_args, list):
                command_args = [command_args]

            command = " ".join(
                [str(arguments.get("program", ""))]
                + [str(arg) for arg in command_args]
            ).strip()
            return self._shorten_event_text(command, 180)

        return str(path or "")

    def _describe_tool_result(self, result):
        """从结构化工具结果提取简短状态，不展示大段文件或命令输出。"""
        if isinstance(result, str):
            try:
                payload = json.loads(result)
            except json.JSONDecodeError:
                return self._shorten_event_text(result, 180)
        else:
            payload = result

        if not isinstance(payload, dict):
            return self._shorten_event_text(str(payload), 180)

        if payload.get("ok") is False:
            error = payload.get("error", {})
            return self._shorten_event_text(
                str(error.get("message", "工具执行失败")),
                180,
            )

        tool_name = payload.get("tool")

        if tool_name == "read_file":
            return f"读取 {payload.get('returned_chars', 0)} 个字符"

        if tool_name == "write_file":
            return f"写入 {payload.get('characters_written', 0)} 个字符"

        if tool_name == "edit_file":
            return f"完成 {payload.get('replacements', 0)} 处替换"

        if tool_name == "list_files":
            return f"发现 {payload.get('count', 0)} 个条目"

        if tool_name == "run_command":
            return f"退出码 {payload.get('exit_code')}"

        return "执行完成"

    def _shorten_event_text(self, text, limit):
        text = str(text)
        if len(text) <= limit:
            return text

        return text[:limit] + "…"

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

        # GLM 等带思考模式的 OpenAI 兼容接口会在工具调用响应中返回
        # reasoning_content，并要求下一轮请求原样带回该字段。
        response_data = {}
        if hasattr(response, "model_dump"):
            response_data = response.model_dump(exclude_none=True)

        reasoning_content = response_data.get(
            "reasoning_content",
            getattr(response, "reasoning_content", None),
        )
        if reasoning_content is not None:
            message["reasoning_content"] = reasoning_content

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

    def run(self, task: str, event_callback=None):
        self.messages.append({"role": "user", "content": task})

        self._emit_event(event_callback, "task_started")

        total_tool_calls = 0
        consecutive_errors = 0

        for step in range(1, self.max_steps + 1):
            # 每次调用模型前压缩上下文
            self.messages = self.context_manager.compact(self.messages)

            self._emit_event(
                event_callback,
                "model_started",
                step=step,
            )

            response = self.llm.chat(
                self.messages,
                self.tool_schemas,
            )

            # SDK对象转换为普通字典后保存
            self.messages.append(self._assistant_message_to_dict(response))

            tool_calls = response.tool_calls or []

            self._emit_event(
                event_callback,
                "model_finished",
                step=step,
                tool_count=len(tool_calls),
            )

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

                    self._emit_event(
                        event_callback,
                        "stopped",
                        message=message,
                    )

                    return self._stop_agent(message)

                # 执行工具
                total_tool_calls += 1

                self._emit_event(
                    event_callback,
                    "tool_started",
                    tool=tool_call.function.name,
                    detail=self._describe_tool_call(tool_call),
                    call_number=total_tool_calls,
                )

                result = self._execute_tool(tool_call)
                serialized_result = self._serialize_tool_result(result)

                tool_failed = self._is_tool_error(result)

                self._emit_event(
                    event_callback,
                    "tool_finished",
                    tool=tool_call.function.name,
                    ok=not tool_failed,
                    detail=self._describe_tool_result(result),
                    call_number=total_tool_calls,
                )

                # 工具执行结果必须重新传给模型
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": serialized_result,
                    }
                )

                # 统计连续错误次数
                if tool_failed:
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

                    self._emit_event(
                        event_callback,
                        "stopped",
                        message=message,
                    )

                    return self._stop_agent(message)

        message = (
            "Agent stopped after reaching the maximum "
            f"number of model steps ({self.max_steps}). "
            f"Total tool calls executed: {total_tool_calls}."
        )
        self._emit_event(
            event_callback,
            "stopped",
            message=message,
        )
        return self._stop_agent(message)

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
