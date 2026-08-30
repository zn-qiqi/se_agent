import os

from agent import Agent
from llm import LLM

try:
    from config import API_KEY, BASE_URL, MODEL
except ImportError:
    API_KEY = None
    BASE_URL = None
    MODEL = None


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
        raise RuntimeError(
            "Missing environment variable(s): " + ", ".join(missing)
        )

    return api_key, model, base_url


def main():
    api_key, model, base_url = get_settings()
    llm = LLM(
        api_key = api_key,
        model = model,
        base_url = base_url
    )

    agent = Agent(llm, workspace = os.getcwd())

    while True:
        task = input("You: ").strip()

        if task.lower() in ["exit", "quit"]:
            break

        result = agent.run(task)

        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    main()
