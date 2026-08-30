from abc import ABC, abstractmethod
import locale
import os 
import subprocess


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

    return data.decode("utf-8", errors = "replace")

# 抽象工具类
class Tool(ABC):
    name: str
    description: str
    parameters: dict

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)

    def resolve_path(self, path: str):
        """ 将路径限制在workspace内 """
        full_path = os.path.abspath(
            os.path.join(self.workspace, path)
        )

        try:
            if os.path.commonpath(
                [self.workspace, full_path]
            ) != self.workspace:
                raise ValueError("Path is outside workspace")
        except ValueError:
            raise ValueError("Invalid path")

        return full_path


    @abstractmethod
    def execute(self, **kwargs):
        pass

    def get_schema(self):
        return{
            "type": "function",
            "function":{
                "name": self.name,
                "description": self.description,
                "parameters" : self.parameters
            }
            
        }

# 读取文件
class ReadFileTool(Tool):
    name = "read_file"
    description = "读取workspace中指定文件的内容"

    parameters = {
        "type" : "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于workspace的文件路径"
            }
        },
        "required": ["path"]
    }

    def execute(self, path: str):
        try:
            full_path = self.resolve_path(path)

            with open(full_path, "r", encoding = "utf-8") as f:
                return f.read()

        except Exception as e:
            return f"Error:{e}"


# 写入文件
class WriteFileTool(Tool):
    name = "write_file"
    description = "在workspace中指定文件写入内容"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于workspace的文件路径"
            },
            "content": {
                "type": "string",
                "description": "需要写入文件的内容"
            }
        },
        "required": ["path", "content"]
    }

    def execute(self, path: str, content: str):
        try:
            full_path = self.resolve_path(path)

            # 父目录不存在则创建
            parent = os.path.dirname(full_path)

            if parent:
                os.makedirs(parent, exist_ok = True)

            with open(full_path, "w", encoding = "utf-8") as f:
                f.write(content)

            return f"Successfully wrote to {path}"

        except Exception as e:
            return f"Error:{e}"

# 查看目录
class ListFilesTool(Tool):
    name = "list_files"
    description = "列出workspace中指定目录的文件和文件夹"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于workspace的目录路径，默认为当前目录"
            }
        },
        "required": []
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
            "command": {
                "type": "string",
                "description": "需要执行的终端命令"
            }
        },
        "required": ["command"]
    }

    def execute(self, command: str):
        try:
            result = subprocess.run(
                command,
                shell = True,
                cwd = self.workspace,
                capture_output = True,
                timeout = 30
            )

            output = decode_command_output(result.stdout)
            error_output = decode_command_output(result.stderr)

            if error_output:
                output += "\n" + error_output

            if not output.strip():
                output = f"Command finished with exit code {result.returncode}"

            return output
        
        except subprocess.TimeoutExpired:
            return "Error: command timed out"

        except Exception as e:
            return f"Error:{e}"


def create_tools(workspace: str):
    """创建当前工作区可用的工具。"""
    tools = [
        ReadFileTool(workspace),
        WriteFileTool(workspace),
        ListFilesTool(workspace),
        RunCommandTool(workspace),
    ]
    return {tool.name: tool for tool in tools}
