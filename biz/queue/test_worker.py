import unittest
from unittest.mock import patch

from biz.llm.exceptions import LLMRequestRejectedError
from biz.queue.worker import _review_changes


class _RejectingReviewer:
    def __init__(self, repository_full_name=None, project_name=None):
        self.repository_full_name = repository_full_name
        self.project_name = project_name

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        raise LLMRequestRejectedError("AI Review 请求被模型服务拒绝，可能是本次代码变更或提交信息触发了模型服务的风险策略。")


class WorkerReviewTest(unittest.TestCase):
    def test_review_changes_returns_message_when_llm_rejects_request(self):
        with patch("biz.queue.worker.CodeReviewer", _RejectingReviewer):
            result = _review_changes(
                changes=[{"new_path": "app.py", "diff": "+print('x')"}],
                commits=[{"message": "normal commit"}],
                repository_full_name="group/repo",
                project_name="repo",
            )

        self.assertIn("模型服务拒绝", result)


if __name__ == "__main__":
    unittest.main()
