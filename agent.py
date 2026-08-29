import json
from tools import ToolS

class Agent:
    def __init__(self, llm, max_steps = 20):
        self.llm = llm
        self.max_steps = max_steps

        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are a coding agent."
                    "You can read and write files, inspect directories,"
                    "and execute commands using the provided tools."
                    "Use tools when necessary to complete the user's task."
                )
            }
        ]

        self.tool_schemas = [
            tool.get_schema()
            for tool in TOOLS.values()
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
                self.messages.append(
                    "role": "tools",
                    "tool_call_id": tool_call.id,
                    "content": result
                )

        return f"Agent stopped after {self.max_steps} steps."
        
        