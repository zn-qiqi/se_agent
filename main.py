import os

from agent import Agent
from llm import LLM, LLMRequestError

try:
    import config as local_config
except ImportError:
    local_config = None

API_KEY = getattr(local_config, "API_KEY", None)
BASE_URL = getattr(local_config, "BASE_URL", None)
DENIED_DRIVES = getattr(local_config, "DENIED_DRIVES", ["C:"])
MODEL = getattr(local_config, "MODEL", None)


def get_settings():
    api_key = os.getenv("OPENAI_API_KEY") or API_KEY
    model = os.getenv("OPENAI_MODEL") or MODEL
    base_url = os.getenv("OPENAI_BASE_URL") or BASE_URL or None

    missing = [
        name
        for name, value in {
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing environment variable(s): " + ", ".join(missing))

    return api_key, model, base_url


def main():
    try:
        api_key, model, base_url = get_settings()
        llm = LLM(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_retries=3,
            request_timeout=60,
        )

    except RuntimeError as error:
        print(f"Configuration error: {error}")
        return 1

    except Exception as error:
        print(f"Failed to initialize LLM: {error}")
        return 1

    agent = Agent(llm, workspace=os.getcwd(), denied_drives=DENIED_DRIVES)

    while True:
        try:
            task = input("You: ").strip()

        except KeyboardInterrupt:
            print("\nAgent exited by user.")
            return 0

        except EOFError:
            print("\nAgent exited.")
            return 0

        if task.lower() in ["exit", "quit"]:
            return 0

        if not task:
            continue

        if task.lower() == "/new":
            agent.reset_context()

            print("\nAgent: Conversation context cleared.\n")

            continue

        context_snapshot = agent.snapshot_context()

        try:
            result = agent.run(task)

            print(f"\nAgent: {result}\n")

        except LLMRequestError as error:
            message = f"Task stopped because of an API error: {error}"

            # API错误发生在模型调用边界，
            # 添加一条本地Assistant消息保持历史完整
            agent.messages.append(
                {
                    "role": "assistant",
                    "content": message,
                }
            )

            print(f"\nAgent: {message}\n")

        except KeyboardInterrupt:
            agent.restore_context(context_snapshot)

            print("\nAgent: Current task cancelled by user.\n")

        except Exception as error:
            agent.restore_context(context_snapshot)

            print(
                "\nAgent: Task failed with an unexpected "
                f"error: {type(error).__name__}: {error}\n"
            )


if __name__ == "__main__":
    raise SystemExit(main())
