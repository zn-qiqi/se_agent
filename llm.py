from openai import OpenAI

class LLM:
    def __init__(self, api_key, model, base_url = None):
        self.model = model

        self.client = OpenAI(
            api_key = api_key,
            base_url = base_url
        )

    def chat(self, messages, tools = None):
        response = self.client.chat.completions.create(
            model = self.model,
            messages = messages,
            tools = tools,
            tool_choice = "auto"
        )

        return response.choices[0].message
