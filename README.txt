se_agent - 本地编程智能体

Git 仓库地址
https://github.com/zn-qiqi/se_agent.git

项目简介
这是一个从零实现的简化版 Coding Agent。模型负责决定下一步操作，本地 Python 程序负责文件读写、命令执行、结果回传和循环控制。项目没有使用 Agent 框架或服务端托管的文件、代码执行工具。

如何运行
使用 Python 3.10 及以上版本，在 PowerShell 中执行：

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

API 配置可以写在不会提交到 Git 的 config.py 中：

API_KEY = "你的 API Key"
MODEL = "模型名称"
BASE_URL = "OpenAI 兼容接口地址"
DENIED_DRIVES = ["C:"]

请勿把真实 API Key 写入 README 或提交仓库。config.py 已被 Git 忽略。

命令行版本：
python main.py

桌面界面版本：
python ui.py

输入 exit 或 quit 退出，输入 /new 开始新对话。运行自动化测试：
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

特色功能
1. 支持分段读取、原子写入、唯一匹配局部修改、目录查看和受限命令执行。
2. 工具结果采用统一 JSON 结构，模型可以根据编译或测试错误继续修正代码。
3. 使用滑动窗口、结构化摘要和 token 估算控制长对话上下文。
4. 最多执行 20 轮模型请求、40 次实际工具调用；连续 5 次工具错误时自动停止。
5. API 请求支持超时、分类重试和清晰错误提示，异常时可以恢复对话快照。
6. UI 会实时显示模型轮次、文件操作、命令、退出码和错误摘要。

其它说明
当前安全机制属于应用层限制，不是完整系统沙箱。默认禁止访问 C 盘。请只在可信环境运行，并在重要任务前备份文件。
