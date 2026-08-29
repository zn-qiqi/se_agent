from abc import ABC, abstractmethod
import os 
import subprocess

# 抽象工具类
class Tool(ABC):
    name: str
    description: str

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
    description = "读取指定文件的内容"

    parameters = {
        "type" : "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "需要读取的文件路径"
            }
        },
        "required": ["path"]
    }

    def execute(self, path: str):
        try:
            with open(path, "r", encoding = "utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error:{e}"


# 写入文件
class WriteFileTool(Tool):
    name = "write_file"
    description = "在指定文件中写入内容"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "需要写入的文件路径"
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
            # 父目录不存在则创建
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok = True)

            with open(path, "w", encoding = "utf-8") as f:
                f.write(content)

            return f"Successfully write to {path}"
        except Exception as e:
            return f"Error:{e}"

# 查看目录
class ListFilesTool(Tool):
    name = "list_files"
    description = "列出指定目录中的文件和文件夹"

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "需要查看的目录路径，默认为当前目录"
            }
        },
        "required": []
    }

    def execute(self, path: str = "."):
        try:
            result = []

            for name in os.listdir(path):
                full_path = os.path.join(path, name)

                if os.path.isdir(full_path):
                    result.append(f"[DIR]{name}")
                else:
                    result.append(f"[FILE]{name}")

            return "\n".join(result)
           
        except Exception as e:
            return f"Error:{e}"

# 执行
class RunCommandTool(Tool):
    name = "run_command"
    description = "在本地执行命令行命令，并返回命令输出"

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "需要执行的终端命令，例如 python main.py 或 pytest"
            }
        },
        "required": ["command"]
    }

    def execute(self, command: str):
        try:
            result = subprocess.run(
                command,
                shell = True,
                capture_output = True,
                text = True,
                timeout = 30
            )
            output = result.stdout

            if result.stderr:
                output += "\n" + result.stderr

            if not output.strip():
                output = f"Command finished with exit code {result.returncode}"

            return output
        
        except subprocess.TimeoutExpired:
            return "Error: command timed out"

        except Exception as e:
            return f"Error:{e}"

    