import json
import os

from tools import create_tools


class Agent:
    def __init__(self, llm, max_steps = 20, workspace = "."):
        self.llm = llm
        self.max_steps = max_steps
        self.tools = create_tools(os.path.abspath(workspace))

        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are a coding agent. "
                    "You can read and write files, inspect directories, "
                    "and execute commands using the provided tools. "
                    "Use tools when necessary to complete the user's task."
                )
            }
        ]

        self.tool_schemas = [
            tool.get_schema()
            for tool in self.tools.values()
        ]

    def run(self, task: str):
        self.messages.append({
            "role": "user",
            "content": task
        })

        for _ in range(self.max_steps):
            response = self.llm.chat(
                self.messages,
                self.tool_schemas
            )

            # 把模型回复加入历史
            self.messages.append(response)

            # 如果没有工具调用，说明模型已经给出最终回答
            if not response.tool_calls:
                return response.content

            # 执行所有工具调用
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call)

                # 工具执行结果必须重新传给模型
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

        return f"Agent stopped after {self.max_steps} steps."

    def _execute_tool(self, tool_call):
        tool_name = tool_call.function.name

        try:
            arguments = json.loads(
                tool_call.function.arguments
            )
        except json.JSONDecodeError as e:
            return f"Error: invalid tool arguments: {e}"

        tool = self.tools.get(tool_name)

        if tool is None:
            return f"Error: unknown tool '{tool_name}'"

        try:
            return str(
                tool.execute(**arguments)
            )
        except Exception as e:
            return f"Error executing {tool_name}: {e}"
        
