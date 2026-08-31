import os
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

from agent import Agent
from llm import LLM, LLMRequestError
from main import DENIED_DRIVES, get_settings


COLORS = {
    "background": "#FBFCFB",
    "surface": "#FFFFFF",
    "composer": "#F2F7F3",
    "primary": "#5C9B6B",
    "primary_dark": "#386847",
    "primary_light": "#E5F2E8",
    "user_message": "#EAF5EC",
    "border": "#C7D9CB",
    "text": "#202923",
    "muted": "#728078",
    "error": "#A44747",
}


class CodingAgentUI:
    def __init__(self, root, agent=None, startup_error=None):
        self.root = root
        self.agent = agent
        self.busy = False
        self.results = queue.Queue()

        self.root.title("Coding Agent")
        self.root.geometry("900x680")
        self.root.minsize(720, 520)
        self.root.configure(bg=COLORS["background"])
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_widgets()
        self._append_message(
            "system",
            "Coding Agent 已就绪。输入一个编程任务开始工作。",
        )

        if startup_error:
            self._append_message("error", startup_error)
            self._set_status("配置不可用", error=True)
            self._set_input_enabled(False)

        self.root.after(100, self._poll_results)

    def _build_widgets(self):
        header = tk.Frame(
            self.root,
            bg=COLORS["surface"],
            padx=22,
            pady=12,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        tk.Label(
            header,
            text="se_agent",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")

        status_area = tk.Frame(header, bg=COLORS["surface"])
        status_area.grid(row=0, column=1, sticky="e", padx=18)

        self.status_dot = tk.Label(
            status_area,
            text="●",
            bg=COLORS["surface"],
            fg=COLORS["primary"],
            font=("Segoe UI", 8),
        )
        self.status_dot.pack(side="left")

        self.status_label = tk.Label(
            status_area,
            text="就绪",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 8),
        )
        self.status_label.pack(side="left", padx=(5, 0))

        self.new_button = tk.Button(
            header,
            text="新对话",
            command=self._reset_conversation,
            bg=COLORS["primary_light"],
            fg=COLORS["primary_dark"],
            activebackground="#D8EADB",
            activeforeground=COLORS["primary_dark"],
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        self.new_button.grid(row=0, column=2, sticky="e")

        separator = tk.Frame(self.root, bg="#E6EBE7", height=1)
        separator.grid(row=0, column=0, sticky="sew")

        chat_container = tk.Frame(
            self.root,
            bg=COLORS["background"],
            padx=44,
            pady=0,
        )
        chat_container.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(18, 8),
        )
        chat_container.grid_rowconfigure(0, weight=1)
        chat_container.grid_columnconfigure(0, weight=1)

        self.chat = scrolledtext.ScrolledText(
            chat_container,
            wrap="word",
            state="disabled",
            bg=COLORS["background"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            bd=0,
            padx=16,
            pady=10,
            font=("Microsoft YaHei UI", 10),
            spacing1=3,
            spacing3=7,
        )
        self.chat.grid(row=0, column=0, sticky="nsew")

        self.chat.tag_configure(
            "user_label",
            foreground=COLORS["primary_dark"],
            font=("Microsoft YaHei UI", 9, "bold"),
            spacing1=8,
        )
        self.chat.tag_configure(
            "agent_label",
            foreground=COLORS["muted"],
            font=("Microsoft YaHei UI", 9, "bold"),
            spacing1=8,
        )
        self.chat.tag_configure(
            "user_message",
            background=COLORS["user_message"],
            lmargin1=90,
            lmargin2=90,
            rmargin=24,
            spacing1=4,
            spacing3=10,
        )
        self.chat.tag_configure(
            "agent_message",
            background=COLORS["background"],
            lmargin1=24,
            lmargin2=24,
            rmargin=90,
            spacing1=4,
            spacing3=10,
        )
        self.chat.tag_configure(
            "system_message",
            foreground=COLORS["muted"],
            justify="center",
            font=("Microsoft YaHei UI", 9),
            spacing1=6,
            spacing3=10,
        )
        self.chat.tag_configure(
            "error_message",
            foreground=COLORS["error"],
            background="#FFF3F3",
            lmargin1=18,
            lmargin2=18,
            rmargin=30,
        )
        self.chat.tag_configure(
            "process_label",
            foreground=COLORS["primary_dark"],
            font=("Microsoft YaHei UI", 9, "bold"),
            lmargin1=24,
            spacing1=4,
            spacing3=4,
        )
        self.chat.tag_configure(
            "process_message",
            foreground=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
            lmargin1=38,
            lmargin2=38,
            rmargin=70,
            spacing1=2,
            spacing3=3,
        )
        self.chat.tag_configure(
            "process_success",
            foreground=COLORS["primary_dark"],
            font=("Microsoft YaHei UI", 9),
            lmargin1=38,
            lmargin2=38,
            rmargin=70,
            spacing1=2,
            spacing3=3,
        )
        self.chat.tag_configure(
            "process_error",
            foreground=COLORS["error"],
            font=("Microsoft YaHei UI", 9),
            lmargin1=38,
            lmargin2=38,
            rmargin=70,
            spacing1=2,
            spacing3=3,
        )

        composer_area = tk.Frame(
            self.root,
            bg=COLORS["surface"],
            padx=58,
            pady=0,
        )
        composer_area.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 18),
        )
        composer_area.grid_columnconfigure(0, weight=1)

        composer = tk.Frame(
            composer_area,
            bg=COLORS["composer"],
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["primary"],
            highlightthickness=1,
            padx=16,
            pady=11,
        )
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)

        self.task_input = tk.Text(
            composer,
            height=4,
            wrap="word",
            bg=COLORS["composer"],
            fg=COLORS["text"],
            insertbackground=COLORS["primary_dark"],
            selectbackground=COLORS["primary_light"],
            selectforeground=COLORS["text"],
            relief="flat",
            bd=0,
            font=("Microsoft YaHei UI", 10),
            padx=2,
            pady=2,
        )
        self.task_input.grid(row=0, column=0, sticky="ew")
        self.task_input.bind("<Return>", self._handle_return)
        self.task_input.bind("<FocusIn>", self._remove_placeholder)
        self.task_input.bind("<FocusOut>", self._restore_placeholder)

        toolbar = tk.Frame(composer, bg=COLORS["composer"])
        toolbar.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        tk.Label(
            toolbar,
            text="Enter 发送  ·  Shift+Enter 换行",
            bg=COLORS["composer"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 8),
        ).grid(row=0, column=0, sticky="w")

        self.send_button = tk.Button(
            toolbar,
            text="↑",
            command=self._send_task,
            bg=COLORS["primary"],
            fg="#FFFFFF",
            activebackground=COLORS["primary_dark"],
            activeforeground="#FFFFFF",
            disabledforeground="#EAF2EC",
            relief="flat",
            bd=0,
            width=3,
            height=1,
            cursor="hand2",
            font=("Segoe UI", 13, "bold"),
        )
        self.send_button.grid(row=0, column=1, sticky="e")

        self.placeholder_active = False
        self._show_placeholder()
        self.task_input.focus_set()

    def _show_placeholder(self):
        if self.task_input.get("1.0", "end-1c"):
            return

        self.placeholder_active = True
        self.task_input.configure(fg=COLORS["muted"])
        self.task_input.insert("1.0", "描述你想完成的编程任务…")

    def _remove_placeholder(self, _event=None):
        if not self.placeholder_active:
            return

        self.task_input.delete("1.0", "end")
        self.task_input.configure(fg=COLORS["text"])
        self.placeholder_active = False

    def _restore_placeholder(self, _event=None):
        if not self.task_input.get("1.0", "end-1c").strip():
            self._show_placeholder()

    def _handle_return(self, event):
        if event.state & 0x0001:
            return None

        self._send_task()
        return "break"

    def _append_message(self, role, content):
        labels = {
            "user": ("你", "user_label", "user_message"),
            "agent": ("Agent", "agent_label", "agent_message"),
            "error": ("错误", "agent_label", "error_message"),
        }

        self.chat.configure(state="normal")

        if role == "system":
            self.chat.insert("end", f"{content}\n", "system_message")
        else:
            label, label_tag, message_tag = labels[role]
            self.chat.insert("end", f"{label}\n", label_tag)
            self.chat.insert("end", f"{content}\n\n", message_tag)

        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _append_progress(self, event):
        event_type = event.get("type")
        text = None
        tag = "process_message"

        if event_type == "task_started":
            text = "执行过程"
            tag = "process_label"

        elif event_type == "model_started":
            step = event.get("step")
            text = f"○ 第 {step} 步：正在请求模型…"
            self._set_status(f"第 {step} 步：模型思考中…")

        elif event_type == "model_finished":
            tool_count = event.get("tool_count", 0)
            if tool_count:
                text = f"  模型计划调用 {tool_count} 个工具"
            else:
                text = "  模型已生成最终回答"

        elif event_type == "tool_started":
            tool_name = event.get("tool", "tool")
            detail = event.get("detail")
            suffix = f" · {detail}" if detail else ""
            text = f"↳ {tool_name}{suffix}"
            self._set_status(f"正在执行 {tool_name}…")

        elif event_type == "tool_finished":
            tool_name = event.get("tool", "tool")
            detail = event.get("detail")
            suffix = f" · {detail}" if detail else ""

            if event.get("ok"):
                text = f"✓ {tool_name}{suffix}"
                tag = "process_success"
            else:
                text = f"✕ {tool_name}{suffix}"
                tag = "process_error"

        elif event_type == "stopped":
            text = f"■ {event.get('message', 'Agent 已停止')}"
            tag = "process_error"

        if text is None:
            return

        self.chat.configure(state="normal")
        self.chat.insert("end", f"{text}\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _set_status(self, text, error=False):
        self.status_label.configure(text=text)
        self.status_dot.configure(
            fg=COLORS["error"] if error else COLORS["primary"]
        )

    def _set_input_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.task_input.configure(state=state)
        self.send_button.configure(state=state)
        self.new_button.configure(state=state)

        if enabled:
            if not self.task_input.get("1.0", "end-1c").strip():
                self._show_placeholder()
            self.task_input.focus_set()

    def _send_task(self):
        if self.busy or self.agent is None:
            return

        if self.placeholder_active:
            return

        task = self.task_input.get("1.0", "end-1c").strip()
        if not task:
            return

        self.task_input.delete("1.0", "end")
        self._append_message("user", task)
        self.busy = True
        self._set_input_enabled(False)
        self._set_status("Agent 正在工作…")

        worker = threading.Thread(
            target=self._run_agent,
            args=(task,),
            daemon=True,
            name="coding-agent-worker",
        )
        worker.start()

    def _run_agent(self, task):
        snapshot = self.agent.snapshot_context()

        try:
            result = self.agent.run(
                task,
                event_callback=lambda event: self.results.put(
                    ("progress", event)
                ),
            )
            self.results.put(("agent", result))

        except LLMRequestError as error:
            message = f"任务因 API 错误停止：{error}"
            self.agent.messages.append(
                {
                    "role": "assistant",
                    "content": message,
                }
            )
            self.results.put(("error", message))

        except Exception as error:
            self.agent.restore_context(snapshot)
            message = (
                "任务因未预期错误停止："
                f"{type(error).__name__}: {error}"
            )
            self.results.put(("error", message))

    def _poll_results(self):
        try:
            while True:
                role, content = self.results.get_nowait()

                if role == "progress":
                    self._append_progress(content)
                    continue

                self._append_message(role, content)
                self.busy = False
                self._set_input_enabled(True)
                self._set_status("就绪", error=role == "error")

        except queue.Empty:
            pass

        self.root.after(100, self._poll_results)

    def _reset_conversation(self):
        if self.busy or self.agent is None:
            return

        self.agent.reset_context()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._append_message("system", "已开始新对话。")
        self._set_status("就绪")


def create_agent():
    api_key, model, base_url = get_settings()
    llm = LLM(
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_retries=3,
        request_timeout=60,
    )
    return Agent(
        llm,
        workspace=os.getcwd(),
        denied_drives=DENIED_DRIVES,
    )


def main():
    root = tk.Tk()

    try:
        agent = create_agent()
        startup_error = None
    except Exception as error:
        agent = None
        startup_error = f"Agent 初始化失败：{error}"

    CodingAgentUI(
        root,
        agent=agent,
        startup_error=startup_error,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
