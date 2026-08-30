import json
import os

from tools import create_tools, tool_error


class Agent:
    def __init__(self, llm, max_steps=20, workspace=".", denied_drives=None):
        self.llm = llm
        self.max_steps = max_steps
        self.tools = create_tools(os.path.abspath(workspace), denied_drives)

        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are a coding agent. "
                    "You can read and write files, inspect directories, "
                    "and execute commands using the provided tools. "
                    "Use tools when necessary to complete the user's task."
                ),
            }
        ]

        self.tool_schemas = [tool.get_schema() for tool in self.tools.values()]

    def run(self, task: str):
        self.messages.append({"role": "user", "content": task})

        for _ in range(self.max_steps):
            response = self.llm.chat(self.messages, self.tool_schemas)

            # 把模型回复加入历史
            self.messages.append(response)

            # 如果没有工具调用，说明模型已经给出最终回答
            if not response.tool_calls:
                return response.content

            # 执行所有工具调用
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call)

                # 工具执行结果必须重新传给模型
                self.messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                )

        return f"Agent stopped after {self.max_steps} steps."

    def _execute_tool(self, tool_call):
        tool_name = tool_call.function.name

        try:
            arguments = json.loads(
                tool_call.function.arguments
            )
        except json.JSONDecodeError as error:
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