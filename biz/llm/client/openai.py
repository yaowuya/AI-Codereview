import os
from typing import Dict, List, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from biz.llm.client.base import BaseClient
from biz.llm.exceptions import LLMServiceUnavailableError
from biz.llm.types import NotGiven, NOT_GIVEN


class OpenAIClient(BaseClient):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com")
        if not self.api_key:
            raise ValueError("API key is required. Please provide it or set it in the environment variables.")

        timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120"))
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.default_model = os.getenv("OPENAI_API_MODEL", "gpt-4o-mini")

    def completions(self,
                    messages: List[Dict[str, str]],
                    model: Optional[str] | NotGiven = NOT_GIVEN,
                    ) -> str:
        model = model or self.default_model
        try:
            completion = self.client.chat.completions.create(
                model=model,
                messages=messages,
            )
        except (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError) as exc:
            raise LLMServiceUnavailableError(
                provider="openai",
                status_code=getattr(exc, "status_code", None),
                request_id=getattr(exc, "request_id", None),
            ) from exc
        except APIStatusError as exc:
            if exc.status_code != 408:
                raise
            raise LLMServiceUnavailableError(
                provider="openai",
                status_code=exc.status_code,
                request_id=getattr(exc, "request_id", None),
            ) from exc
        return completion.choices[0].message.content
