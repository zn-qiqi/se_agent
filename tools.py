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
            "name": self.name,
            "description": self.description
        }

# 读取文件
class ReadFileTool(Tool):
    name = "read_file"
    description = "读取指定文件的内容"

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

    def execute(self, path: str = "."):
        try:
            files = os.listdir(path)
            return "\n".join(files)
        except Exception as e:
            return f"Error:{e}"

# 执行
class RunCommandTool(Tool):
    name = "run_command"
    description = "在本地执行命令行命令"

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

            return output
        except subprocess.TimeoutExpired:
            return "Error: command timed out"

        except Exception as e:
            return f"Error:{e}"

    