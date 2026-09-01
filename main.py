import os

from agent import Agent
from llm import LLM, LLMRequestError
from reviewer import ReviewerAgent

try:
    import config as local_config
except ImportError:
    local_config = None

API_KEY = getattr(local_config, "API_KEY", None)
BASE_URL = getattr(local_config, "BASE_URL", None)
DENIED_DRIVES = getattr(local_config, "DENIED_DRIVES", ["C:"])
MODEL = getattr(local_config, "MODEL", None)

REVIEWER_API_KEY = getattr(
    local_config, 
    "REVIEWER_API_KEY", 
    None,
)
REVIEWER_MODEL = getattr(
    local_config, 
    "REVIEWER_MODEL", 
    None,
)
REVIEWER_BASE_URL = getattr(
    local_config, 
    "REVIEWER_BASE_URL", 
    None,
)


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

def get_reviewer_settings():
    api_key = os.getenv("REVIEWER_API_KEY") or REVIEWER_API_KEY
    model = os.getenv("REVIEWER_MODEL") or REVIEWER_MODEL
    base_url = os.getenv("REVIEWER_BASE_URL") or REVIEWER_BASE_URL or None

    missing = [
        name
        for name, value in {
            "REVIEWER_API_KEY": api_key,
            "REVIEWER_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing reviewer settings(s): " + ", ".join(missing))

    return api_key, model, base_url


def main():
    try:
        coding_api_key, coding_model, coding_base_url = get_settings()
        reviewer_api_key, reviewer_model, reviewer_base_url = get_reviewer_settings()

        coding_llm = LLM(
            api_key=coding_api_key,
            model=coding_model,
            base_url=coding_base_url,
            max_retries=3,
            request_timeout=60,
        )

        reviewer_llm = LLM(
            api_key=reviewer_api_key,
            model=reviewer_model,
            base_url=reviewer_base_url,
            max_retries=3,
            request_timeout=60,
        )


    except RuntimeError as error:
        print(f"Configuration error: {error}")
        return 1

    except Exception as error:
        print(f"Failed to initialize LLM: {error}")
        return 1

    agent = Agent(coding_llm, workspace=os.getcwd(), denied_drives=DENIED_DRIVES)
    reviewer = ReviewerAgent(reviewer_llm, workspace=os.getcwd(), denied_drives=DENIED_DRIVES)

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
            reviewer.reset_context()

            print("\nAgent: Conversation context cleared.\n")

            continue

        context_snapshot = agent.snapshot_context()

        try:
            result = agent.run(task)

            print(f"\nCoding Agent: \n{result}\n")
            print("Reviewer Agent 正在检查...\n")

            try:
                review_result = reviewer.review(
                    original_task=task,
                    coding_result=result,
                )

                print(f"\nReviewer Agent: \n{review_result}\n")

            except LLMRequestError as error:
                print(
                    "Reviewer Agent: 审查因API错误停止:"
                    f" {error}\n"
                )

            except Exception as error:
                print(
                    "Reviewer Agent 审查失败"
                    f" {type(error).__name__}: {error}\n"
                )

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
