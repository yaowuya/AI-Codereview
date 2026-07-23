import os
import unittest
from unittest.mock import patch

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError

from biz.llm.client.openai import OpenAIClient
from biz.llm.exceptions import LLMServiceUnavailableError


class OpenAIClientTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_API_BASE_URL": "https://llm.example.com",
            "OPENAI_API_MODEL": "test-model",
            "OPENAI_TIMEOUT_SECONDS": "45",
            "OPENAI_MAX_RETRIES": "1",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    @patch("biz.llm.client.openai.OpenAI")
    def test_configures_timeout_and_retries(self, openai_cls):
        OpenAIClient()

        openai_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://llm.example.com",
            timeout=45.0,
            max_retries=1,
        )

    @patch("biz.llm.client.openai.OpenAI")
    def test_transient_provider_errors_are_normalized(self, openai_cls):
        request = httpx.Request("POST", "https://llm.example.com/v1/chat/completions")
        response_408 = httpx.Response(408, request=request)
        response_429 = httpx.Response(429, request=request)
        response_504 = httpx.Response(504, request=request)
        transient_errors = [
            APIConnectionError(request=request),
            APITimeoutError(request=request),
            APIStatusError("request timeout", response=response_408, body=None),
            RateLimitError("rate limited", response=response_429, body=None),
            InternalServerError("gateway timeout", response=response_504, body=None),
        ]

        client = OpenAIClient()
        create = openai_cls.return_value.chat.completions.create

        for error in transient_errors:
            with self.subTest(error=type(error).__name__):
                create.side_effect = error
                with self.assertRaises(LLMServiceUnavailableError) as raised:
                    client.completions(messages=[{"role": "user", "content": "hello"}])
                self.assertEqual(raised.exception.status_code, getattr(error, "status_code", None))
                self.assertEqual(raised.exception.provider, "openai")
                self.assertNotIn("gateway timeout", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
