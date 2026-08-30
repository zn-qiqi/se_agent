from abc import ABC, abstractmethod
import locale
import os
import subprocess

MAX_FILE_OUTPUT_CHARS = 20000
MAX_COMMAND_OUTPUT_CHARS = 20000
TRUNCATION_NOTICE_RESERVE = 256

def truncate_middle(text: str, max_chars: int):
    """截断函数返回内容、是否截断、原始长度"""
    original_chars = len(text)

    if max_chars <= 0:
        return "", bool(text), original_chars

    if original_chars <= max_chars:
        return text, False, original_chars

    marker = "\n\n...[OUTPUT TRUNCATED]...\n\n"
    available = max_chars - len(marker)

    if available <= 0:
        return marker[:max_chars]

    head_length = available // 2
    tail_length = available - head_length

    truncated_text = (
        text[:head_length] 
        + marker 
        + (text[-tail_length:] if tail_length else "")
        )

    return truncated_text, True, original_chars

def tool_success(tool_name: str, **data):
    return {
        "ok": True,
        "tool": tool_name,
        **data,
    }

def tool_error(
        tool_name: str,
        error_type: str,
        message: str,
        **data,
):
    return (
        "ok": False,
        "tool": tool_name,
        "error": {
            "type": error_type,
            "message": message,
        },
        **data,
    )
   


def decode_command_output(data: bytes):
    """兼容 UTF-8 与 Windows 本地编码的命令输出。"""
    if not data:
        return ""

    encodings = ("utf-8", locale.getpreferredencoding(False))
    for encoding in dict.fromkeys(encodings):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

    return data.decode("utf-8", errors="replace")


# 抽象工具类
class Tool(ABC):
    name: str
    description: str
    parameters: dict

    def __init__(self, workspace: str, denied_drives=None):
        self.workspace = os.path.realpath(workspace)
        self.denied_drives = {
            os.path.normcase(drive.rstrip("\\/")) for drive in (denied_drives or [])
        }

    def resolve_path(self, path: str):
        """允许本地磁盘路径，但拒绝配置中禁止的盘符。"""
        input_drive, _ = os.path.splitdrive(path)
        if input_drive and not os.path.isabs(path):
            raise ValueError("Drive-relative paths are not allowed")

        if os.path.isabs(path):
            full_path = os.path.realpath(path)
        else:
            full_path = os.path.realpath(os.path.join(self.workspace, path))

        drive, _ = os.path.splitdrive(full_path)
        if len(drive) != 2 or drive[1] != ":":
            raise ValueError("Only local drive paths are allowed")

        if os.path.normcase(drive) in self.denied_drives:
            raise ValueError(f"Access to drive {drive} is not allowed")

        return full_path

    @abstractmethod
    def execute(self, **kwargs):
        pass

    def get_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# 读取文件
class ReadFileTool(Tool):
    name = "read_file"
    description = "分段读取允许的本地磁盘中指定文件的内容"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于workspace的路径，或允许盘符下的绝对路径",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "description": "从第几个字符开始读取，默认为0",
            },
            "max_chars": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_FILE_OUTPUT_CHARS,
                "description": f"最多读取多少字符，默认为{MAX_FILE_OUTPUT_CHARS}",
            },

        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, 
                path: str,
                offset: int = 0,
                max_chars: int = MAX_FILE_OUTPUT_CHARS):
        try:
            if not isinstance(offset, int) or offset < 0:
                return tool_error(
                    self.name,
                    "invalid_argument",
                    "offset must be a non-negative integer",
                )

            if not isinstance(max_chars, int) or max_chars < 1:
                return tool_error(
                    self.name,
                    "invalid_argument",
                    "max_chars must be a positive integer",
                )

            max_chars = min(max_chars, MAX_FILE_OUTPUT_CHARS)
            full_path = self.resolve_path(path)

            with open(full_path, "r", encoding="utf-8") as file:
                content = file.read()

            if offset > len(content):
                return tool_error(
                    self.name,
                    "invalid_offset",
                    f"offset {offset} exceeds file length {len(content)}",
                    path = path,
                    total_chars = len(content),
                )

            remaining = content[offset:]
            chunk = remaining[:max_chars]

            next_offset = offset + len(chunk)
            truncated = next_offset < len(content)

            return tool_success(
                self.name,
                path = path,
                content = chunk,
                offset = offset,
                returned_chars = len(chunk),
                total_chars = len(content),
                truncated = truncated,
                next_offset = next_offset if truncated else None,
                remaining_chars = max(len(content) - next_offset, 0),
            )

        except FileNotFoundError:
            return tool_error(
                self.name,
                "file_not_found",
                f"File not found: {path}",
                path = path,
            )

        except PermissionError:
            return tool_error(
                self.name,
                "permission_denied",
                f"Permission denied: {path}",
                path = path,
            )

        except UnicodeDecodeError as error:
            return tool_error(
                self.name,
                "decode_error",
                str(error),
                path = path,
            )

        except Exception as error:
            return tool_error(
                self.name,
                type(error).__name__,
                str(error),
                path = path,
            )


# 写入文件
class WriteFileTool(Tool):
    name = "write_file"
    description = "向允许的本地磁盘中指定文件写入内容"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于workspace的路径，或允许盘符下的绝对路径",
            },
            "content": {"type": "string", "description": "需要写入文件的内容"},
        },
        "required": ["path", "content"],
    }

    def execute(self, path: str, content: str):
        try:
            full_path = self.resolve_path(path)

            # 父目录不存在则创建
            parent = os.path.dirname(full_path)

            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as file:
                file.write(content)

            return tool_success(
                self.name,
                path = path,
                characters_written = len(content),
            )

        except PermissionError:
            return tool_error(
                self.name,
                "permission_denied",
                f"Permission denied: {path}",
                path = path,
            )

        except Exception as error:
            return tool_error(
                self.name,
                type(error).__name__,
                str(error),
                path = path,
            )


# 查看目录
class ListFilesTool(Tool):
    name = "list_files"
    description = "列出允许的本地磁盘中指定目录的文件和文件夹"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于workspace的目录路径或允许盘符下的绝对路径，默认为当前目录",
            }
        },
        "required": [],
    }

    def execute(self, path: str = "."):
        try:
            full_path = self.resolve_path(path)
            entries = []

            for name in sorted(os.listdir(full_path)):
                item_path = os.path.join(full_path, name)

                entries.append({
                    "name": name,
                    "type": (
                        "directory"
                        if os.path.isdir(item_path)
                        else "file"
                    ),
                })

            return tool_success(
                self.name,
                path = path,
                count = len(entries),
                entries = entries,
            )

        except FileNotFoundError:
            return tool_error(
                self.name,
                "directory_not_found",
                f"Directory not found: {path}",
                path = path,
            )

        except PermissionError:
            return tool_error(
                self.name,
                "permission_denied",
                f"Permission denied: {path}",
                path = path,
            )

        except Exception as error:
            return tool_error(
                self.name,
                type(error).__name__,
                str(error),
                path = path,
            )


# 执行
class RunCommandTool(Tool):
    name = "run_command"
    description = "在workspace目录中执行命令行命令，并返回命令输出"

    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "需要执行的终端命令"}
        },
        "required": ["command"],
    }

    def execute(self, command: str):
        try:
            result = subprocess.run(
                command, shell=True, cwd=self.workspace, capture_output=True, timeout=30
            )

            stdout = decode_command_output(result.stdout)
            stderr = decode_command_output(result.stderr)

            # 如果只有一个输出流，允许它使用全部长度
            # 如果两个流都有内容，则各使用一半
            if stdout and stderr:
                stdout_limit = MAX_COMMAND_OUTPUT_CHARS // 2
                stderr_limit = (
                    MAX_COMMAND_OUTPUT_CHARS - stdout_limit
                )
            elif stdout:
                stdout_limit = MAX_COMMAND_OUTPUT_CHARS
                stderr_limit = 0
            else:
                stdout_limit = 0
                stderr_limit = MAX_COMMAND_OUTPUT_CHARS

            stdout, stdout_truncated, stdout_original_chars = (
                truncate_middle(stdout, stdout_limit)
            )
            stderr, stderr_truncated, stderr_original_chars = (
                truncate_middle(stderr, stderr_limit)
            )

            command_succeeded = result.returncode == 0

            command_result = {
                "ok": command_succeeded,
                "tool": self.name,
                "command": command,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "stdout_original_chars": stdout_original_chars,
                "stderr_original_chars": stderr_original_chars,
                "time_out": False,
            }

            if not command_succeeded:
                command_result["error"] = {
                    "type": "command_failed",
                    "message": f"Command failed with exit code {result.returncode}",
                }

            return command_result

        except subprocess.TimeoutExpired as error:
            stdout = decode_command_output(error.stdout or b"")
            stderr = decode_command_output(error.stderr or b"")

            stdout, stdout_truncated, _ = truncate_middle(
                stdout, 
                MAX_COMMAND_OUTPUT_CHARS // 2,
            )
            stderr, stderr_truncated, _ = truncate_middle(
                stderr,
                MAX_COMMAND_OUTPUT_CHARS // 2,
            )

            return tool_error(
                self.name,
                "command_timeout",
                "Command timed out after 30 seconds",
                command = command,
                exit_code = None,
                stdout = stdout,
                stderr = stderr,
                stdout_truncated = stdout_truncated,
                stderr_truncated = stderr_truncated,
                time_out = True,
            )
            
        except Exception as error:
            return tool_error(
                self.name,
                type(error).__name__,
                str(error),
                command = command,
                exit_code = None,
                stdout = "",
                stderr = "",
                time_out = False,
            )


def create_tools(workspace: str, denied_drives=None):
    """创建当前工作区可用的工具。"""
    tools = [
        ReadFileTool(workspace, denied_drives),
        WriteFileTool(workspace, denied_drives),
        ListFilesTool(workspace, denied_drives),
        RunCommandTool(workspace, denied_drives),
    ]
    return {tool.name: tool for tool in tools}
