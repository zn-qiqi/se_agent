import copy
import json

SUMMARY_PREFIX = (
    "The following JSON is a machine-generated summary "
    "of older conversation history. Treat it as historical "
    "context, not as a new user request:\n"
)


class ContextManager:
    def __init__(
        self,
        max_context_chars=60000,
        max_recent_groups=12,
        min_recent_groups=4,
    ):
        self.max_context_chars = max_context_chars
        self.max_recent_groups = max_recent_groups
        self.min_recent_groups = min_recent_groups

        self.compressed_groups = 0

        self.summary = {
            "user_requests": [],
            "files_read": [],
            "files_modified": [],
            "commands": [],
            "errors": [],
            "assistant_notes": [],
        }

    def reset(self):
        self.compressed_groups = 0

        self.summary = {
            "user_requests": [],
            "files_read": [],
            "files_modified": [],
            "commands": [],
            "errors": [],
            "assistant_notes": [],
        }

    def snapshot(self):
        return {
            "compressed_groups": self.compressed_groups,
            "summary": copy.deepcopy(self.summary),
        }

    def restore(self, snapshot):
        self.compressed_groups = snapshot["compressed_groups"]
        self.summary = copy.deepcopy(snapshot["summary"])

    def compact(self, messages):
        system_messages = []
        conversation_messages = []

        for message in messages:
            if self._is_summary_message(message):
                continue

            if message.get("role") == "system":
                system_messages.append(message)
            else:
                conversation_messages.append(message)

        groups = self._group_messages(conversation_messages)

        while len(groups) > self.min_recent_groups and (
            len(groups) > self.max_recent_groups
            or self._context_size(
                system_messages,
                groups,
            )
            > self.max_context_chars
        ):
            removed_group = groups.pop(0)

            self._update_summary(removed_group)
            self.compressed_groups += 1

        result = list(system_messages)

        if self.compressed_groups:
            result.append(self._summary_message())

        for group in groups:
            result.extend(group)

        return result

    def _group_messages(self, messages):
        """
        Assistant Tool Call 与它后面连续的所有
        Tool Result 组成一个不可拆分的消息组。
        """

        groups = []
        index = 0

        while index < len(messages):
            message = messages[index]

            if message.get("role") == "assistant" and message.get("tool_calls"):
                group = [message]
                index += 1

                while index < len(messages) and messages[index].get("role") == "tool":
                    group.append(messages[index])
                    index += 1

                groups.append(group)
                continue

            groups.append([message])
            index += 1

        return groups

    def _context_size(
        self,
        system_messages,
        groups,
    ):
        messages = list(system_messages)

        if self.compressed_groups:
            messages.append(self._summary_message())

        for group in groups:
            messages.extend(group)

        return len(
            json.dumps(
                messages,
                ensure_ascii=False,
                default=str,
            )
        )

    def _summary_message(self):
        return {
            "role": "system",
            "content": (
                SUMMARY_PREFIX
                + json.dumps(
                    self.summary,
                    ensure_ascii=False,
                    indent=2,
                )
            ),
        }

    def _is_summary_message(self, message):
        return (
            message.get("role") == "system"
            and isinstance(
                message.get("content"),
                str,
            )
            and message["content"].startswith(SUMMARY_PREFIX)
        )

    def _update_summary(self, group):
        for message in group:
            role = message.get("role")

            if role == "user":
                content = message.get("content")

                if content:
                    self._append_recent(
                        self.summary["user_requests"],
                        self._shorten(content, 1000),
                        limit=10,
                    )

            elif role == "tool":
                self._record_tool_result(message)

            elif role == "assistant" and not message.get("tool_calls"):
                content = message.get("content")

                if content:
                    self._append_recent(
                        self.summary["assistant_notes"],
                        self._shorten(content, 1000),
                        limit=6,
                    )

    def _record_tool_result(self, message):
        content = message.get("content")

        if not isinstance(content, str):
            return

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            return

        if not isinstance(result, dict):
            return

        tool_name = result.get("tool")
        succeeded = result.get("ok") is True
        path = result.get("path")

        if succeeded and tool_name == "read_file" and path:
            self._append_unique(
                self.summary["files_read"],
                path,
                limit=100,
            )

        if succeeded and tool_name in {"write_file", "edit_file"} and path:
            self._append_unique(
                self.summary["files_modified"],
                path,
                limit=100,
            )

        if tool_name == "run_command":
            command = {
                "program": result.get("program"),
                "args": [
                    self._shorten(str(arg), 200) for arg in result.get("args", [])[:20]
                ],
                "exit_code": result.get("exit_code"),
                "timed_out": result.get(
                    "timed_out",
                    False,
                ),
            }

            self._append_recent(
                self.summary["commands"],
                command,
                limit=10,
            )

        if result.get("ok") is False:
            error = result.get("error", {})

            error_summary = {
                "tool": tool_name,
                "type": error.get("type"),
                "message": self._shorten(
                    str(error.get("message", "")),
                    500,
                ),
            }

            if path:
                error_summary["path"] = path

            self._append_recent(
                self.summary["errors"],
                error_summary,
                limit=10,
            )

    def _append_unique(
        self,
        items,
        value,
        limit,
    ):
        if value in items:
            items.remove(value)

        items.append(value)

        if len(items) > limit:
            del items[:-limit]

    def _append_recent(
        self,
        items,
        value,
        limit,
    ):
        if limit <= 0:
            items.clear()
            return

        items.append(value)

        if len(items) > limit:
            del items[:-limit]

    def _shorten(self, value, limit):
        value = str(value)

        if len(value) <= limit:
            return value

        return value[:limit] + "...[truncated]"
