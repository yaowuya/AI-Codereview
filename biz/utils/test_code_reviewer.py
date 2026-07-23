import unittest
from unittest.mock import patch

from biz.llm.exceptions import LLMRequestRejectedError
from biz.utils.code_reviewer import BaseReviewer


class _RejectingClient:
    def completions(self, messages):
        raise Exception("The request was rejected because it was considered high risk")


class _Reviewer(BaseReviewer):
    def __init__(self):
        self.client = _RejectingClient()

    def review_code(self, *args, **kwargs) -> str:
        return self.call_llm([])


class _SuccessfulClient:
    def completions(self, messages):
        return "ok"


class _SuccessfulReviewer(BaseReviewer):
    def __init__(self):
        self.client = _SuccessfulClient()

    def review_code(self, *args, **kwargs) -> str:
        return self.call_llm([{"role": "user", "content": "private source"}])


class CodeReviewerErrorTest(unittest.TestCase):
    def test_high_risk_rejection_raises_specific_error(self):
        reviewer = _Reviewer()

        with self.assertRaises(LLMRequestRejectedError) as context:
            reviewer.review_code()

        self.assertIn("模型服务拒绝", str(context.exception))

    def test_llm_logging_uses_metadata_instead_of_message_content(self):
        reviewer = _SuccessfulReviewer()

        with patch("biz.utils.code_reviewer.logger.info") as log_info:
            reviewer.review_code()

        rendered_logs = " ".join(str(call) for call in log_info.call_args_list)
        self.assertIn("message_count", rendered_logs)
        self.assertIn("content_chars", rendered_logs)
        self.assertNotIn("private source", rendered_logs)


if __name__ == "__main__":
    unittest.main()
