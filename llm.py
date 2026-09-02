import time

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)


class LLMRequestError(RuntimeError):
    """模型API请求失败"""


class LLM:
    def __init__(
        self,
        api_key,
        model,
        base_url=None,
        max_retries=3,
        request_timeout=60,
    ):
        self.model = model
        self.max_retries = max_retries
        self.request_timeout = request_timeout

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def _api_status_detail(self, error):
        """提取兼容接口返回的业务错误码与消息。"""
        body = getattr(error, "body", None)
        if not isinstance(body, dict):
            return ""

        detail = body.get("error", body)
        if not isinstance(detail, dict):
            return ""

        code = detail.get("code")
        message = detail.get("message")
        parts = [str(value) for value in (code, message) if value]
        return " - ".join(parts)

    def _wait_before_retry(
        self,
        attempt,
        error,
        message,
    ):
        if attempt >= self.max_retries:
            raise LLMRequestError(f"{message} after {attempt + 1} attempts") from error

        wait_seconds = 2**attempt

        print(f"[LLM] {message}. " f"Retrying in {wait_seconds} second(s)...")

        time.sleep(wait_seconds)

    def chat(self, messages, tools=None):
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    timeout=self.request_timeout,
                )

                if not response.choices:
                    raise LLMRequestError("Model API returned no choices")

                message = response.choices[0].message

                if message is None:
                    raise LLMRequestError("Model API returned an empty message")

                return message

            # API Key错误，不进行重试
            except AuthenticationError as error:
                raise LLMRequestError(
                    "API authentication failed; please check the API key"
                ) from error

            except PermissionDeniedError as error:
                raise LLMRequestError("API permission denied") from error

            # 请求过于频繁，可以重试
            except RateLimitError as error:
                self._wait_before_retry(
                    attempt,
                    error,
                    "API rate limit reached",
                )

            # 网络错误和超时可以重试
            except (
                APIConnectionError,
                APITimeoutError,
            ) as error:
                self._wait_before_retry(
                    attempt,
                    error,
                    "API connection failed",
                )

            # 服务器5xx错误可以重试
            except APIStatusError as error:
                status_code = error.status_code

                if status_code >= 500:
                    self._wait_before_retry(
                        attempt,
                        error,
                        f"API server error ({status_code})",
                    )
                else:
                    detail = self._api_status_detail(error)
                    detail_suffix = f": {detail}" if detail else ""
                    raise LLMRequestError(
                        "API request failed with status "
                        f"{status_code}{detail_suffix}"
                    ) from error

            except OpenAIError as error:
                raise LLMRequestError(f"API request failed: {error}") from error

        raise LLMRequestError("API request failed unexpectedly")
