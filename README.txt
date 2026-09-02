se_agent - 本地双 Agent 编程智能体

Git 仓库地址
https://github.com/zn-qiqi/se_agent.git

项目简介
这是一个从零实现且不使用 Agent 框架的本地 Coding Agent。Python 程序负责上下文、工具执行和循环控制；编码完成后，Reviewer 会独立检查文件、测试结果并反馈。

如何运行
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

在项目根目录创建已被 Git 忽略的 config.py：

API_KEY = "编程模型的 API Key"
MODEL = "编程模型名称"
BASE_URL = "OpenAI 兼容接口地址"
REVIEWER_API_KEY = "审查模型的 API Key"
REVIEWER_MODEL = "审查模型名称"
REVIEWER_BASE_URL = "审查模型接口地址"
DENIED_DRIVES = ["C:"]

启动 UI：
.\.venv\Scripts\python.exe ui.py

启动 CLI：
.\.venv\Scripts\python.exe main.py

运行测试：
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

特色功能
1. 支持分段读文件、原子写入、唯一匹配编辑、目录查看和 shell=False 命令执行。
2. 工具结果统一为 JSON；限制输出长度，并用滑动窗口、结构化摘要和 token 估算控制上下文。
3. Coding Agent 上限为 20 轮、40 次工具调用和连续 5 次错误。
4. Reviewer 独立重置上下文，只直接拥有读取、目录和命令工具；上限为 8 轮、12 次调用和连续 3 次错误。
5. 支持 API 分类重试、超时和异常恢复；UI 实时展示两个 Agent 的执行过程。

其它说明
本项目不是系统沙箱，命令仍可能修改文件。为了保证安全性，初步默认拒绝 C 盘，请在可信环境运行并备份重要文件。现有 26 项测试。
