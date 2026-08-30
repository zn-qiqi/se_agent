from abc import ABC, abstractmethod
import locale
import os
import subprocess

MAX_FILE_OUTPUT_CHARS = 20000
MAX_COMMAND_OUTPUT_CHARS = 20000
TRUNCATION_NOTICE_RESERVE = 256

def truncate_middle(text: str, max_chars: int):
    """保留输出开头和结尾，确保总长度不超过 max_chars。"""
    if len(text) <= max_chars:
        return text

    marker = "\n\n...[OUTPUT TRUNCATED]...\n\n"
    available = max_chars - len(marker)

    if available <= 0:
        return marker[:max_chars]

    head_length = available // 2
    tail_length = available - head_length

    return (
        text[:head_length] 
        + marker
        + (text[-tail_length:] if tail_length > 0 else "")
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
                raise ValueError("Offset must be a non-negative integer")

            if not isinstance(max_chars, int) or max_chars < 1:
                raise ValueError("max_chars must be a positive integer")

            max_chars = min(max_chars, MAX_FILE_OUTPUT_CHARS)
            full_path = self.resolve_path(path)

            with open(full_path, "r", encoding="utf-8") as file:
                content = file.read()

            if offset > len(content):
                raise ValueError(f"offset {offset} exceeds file length {len(content)}")

            remaining = content[offset:]

            if len(remaining) <= max_chars:
                return remaining

            # 为截断提示预留空间
            chunk_limit = min(
                max_chars,
                MAX_FILE_OUTPUT_CHARS - TRUNCATION_NOTICE_RESERVE,
            )

            chunk = remaining[:chunk_limit]
            next_offset = offset + len(chunk)
            remaining_chars = len(content) - next_offset

            notice = (
                "\n\n"
                f"[FILE TRUNCATED: {remaining_chars} characters remaining)."
                f"Call read_file again with offset={next_offset}]"
            )

            available = MAX_FILE_OUTPUT_CHARS - len(notice)
            return chunk[:available] + notice

        except Exception as e:
            return f"Error:{e}"


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

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return f"Successfully wrote to {path}"

        except Exception as e:
            return f"Error:{e}"


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

            result = []

            for name in os.listdir(full_path):
                item_path = os.path.join(full_path, name)

                if os.path.isdir(item_path):
                    result.append(f"[DIR]{name}")
                else:
                    result.append(f"[FILE]{name}")

            return "\n".join(result)

        except Exception as e:
            return f"Error:{e}"


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

            output = decode_command_output(result.stdout)
            error_output = decode_command_output(result.stderr)

            if error_output:
                if output:
                    output += "\n\n[STDERR]\n"
                output += error_output

            if not output.strip():
                output = f"Command finished with exit code {result.returncode}"

            return truncate_middle(output, MAX_COMMAND_OUTPUT_CHARS)

        except subprocess.TimeoutExpired:
            return "Error: command timed out"

        except Exception as e:
            return f"Error:{e}"


def create_tools(workspace: str, denied_drives=None):
    """创建当前工作区可用的工具。"""
    tools = [
        ReadFileTool(workspace, denied_drives),
        WriteFileTool(workspace, denied_drives),
        ListFilesTool(workspace, denied_drives),
        RunCommandTool(workspace, denied_drives),
    ]
    return {tool.name: tool for tool in tools}
