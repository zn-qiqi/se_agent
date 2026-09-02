from agent import Agent

REVIEWER_SYSTEM_PROMPT = """
You are a code review agent running on Windows.

Your job is to independently review work completed by another coding agent.

You may:
- inspect directories;
- read relevant source files;
- run safe compilation, tests, and read-only Git commands.

When calling run_command, invoke the target program directly and pass each
argument separately. Never use cmd, powershell, pwsh, bash, sh, shell
operators, or Unix-style ./program commands. Prefer bare program names from
PATH instead of absolute paths on a denied drive.
Do not call shell built-ins such as echo, dir, type, copy, del, set, or cd.
Do not probe run_command with echo; run the actual compiler, test runner, or
executable directly.

When calling read_file, read only files relevant to the task and set max_chars
to at most 6000. Read additional chunks with offset only when necessary.

You must not modify, create, or delete files.

Do not trust the coding agent's final answer by itself.
Verify important claims using the available tools.

Focus on:
1. whether the original requirement was satisfied;
2. correctness and possible bugs;
3. error handling and boundary cases;
4. security and maintainability;
5. whether tests actually passed;
6. concrete improvements.

Return the review in Chinese using this format:

审查结论：通过 / 基本通过 / 需要修改 / 无法验证

已验证内容：
- ...

发现的问题：
- ...

改进建议：
- ...

Do not invent problems.
""".strip()


class ReviewerAgent(Agent):
    def __init__(
        self,
        llm,
        workspace=".",
        denied_drives=None,
    ):
        super().__init__(
            llm=llm,
            workspace=workspace,
            denied_drives=denied_drives,
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            allowed_tool_names={
                "read_file",
                "list_files",
                "run_command",
            },
            max_steps=12,
            max_tool_calls=20,
            max_consecutive_errors=3,
            max_context_tokens=12000,
            max_recent_groups=8,
            reserved_tokens=3000,
        )

    def review(
        self,
        original_task,
        coding_result,
        event_callback=None,
    ):
        # 每个任务单独审查，避免受到上次任务影响
        self.reset_context()

        review_task = (
            "请审查另一个 Coding Agent 完成的编程任务。\n\n"
            "原始用户任务：\n"
            "--- ORIGINAL TASK ---\n"
            f"{original_task}\n"
            "--- END ORIGINAL TASK ---\n\n"
            "Coding Agent 声称的完成结果：\n"
            "--- CODING RESULT ---\n"
            f"{coding_result}\n"
            "--- END CODING RESULT ---\n\n"
            "请独立读取相关文件，并在必要时运行测试。\n"
            "不要只相信 Coding Agent 的文字说明。\n"
            "只提供审查反馈，不要修改文件。"
        )

        return self.run(
            review_task,
            event_callback=event_callback,
        )
