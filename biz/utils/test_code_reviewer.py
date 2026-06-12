import unittest

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


class CodeReviewerErrorTest(unittest.TestCase):
    def test_high_risk_rejection_raises_specific_error(self):
        reviewer = _Reviewer()

        with self.assertRaises(LLMRequestRejectedError) as context:
            reviewer.review_code()

        self.assertIn("模型服务拒绝", str(context.exception))


if __name__ == "__main__":
    unittest.main()
