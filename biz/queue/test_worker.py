import unittest
from unittest.mock import patch

from biz.llm.exceptions import LLMRequestRejectedError, LLMServiceUnavailableError
from biz.queue.worker import _notify_llm_service_unavailable, _review_changes, _summarize_changes


class _RejectingReviewer:
    def __init__(self, repository_full_name=None, project_name=None):
        self.repository_full_name = repository_full_name
        self.project_name = project_name

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        raise LLMRequestRejectedError("AI Review 请求被模型服务拒绝，可能是本次代码变更或提交信息触发了模型服务的风险策略。")


class _UnavailableReviewer:
    def __init__(self, repository_full_name=None, project_name=None):
        self.repository_full_name = repository_full_name
        self.project_name = project_name

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        raise LLMServiceUnavailableError(provider="openai", status_code=504, request_id="req-123")


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

    def test_review_changes_propagates_transient_service_failure(self):
        with patch("biz.queue.worker.CodeReviewer", _UnavailableReviewer):
            with self.assertRaises(LLMServiceUnavailableError) as raised:
                _review_changes(
                    changes=[{"new_path": "app.py", "diff": "+print('x')"}],
                    commits=[{"message": "normal commit"}],
                    repository_full_name="group/repo",
                    project_name="repo",
                )

        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(raised.exception.request_id, "req-123")

    def test_change_summary_excludes_diff_content(self):
        summary = _summarize_changes([
            {
                "new_path": "app.py",
                "diff": "+secret source line",
                "additions": 2,
                "deletions": 1,
            }
        ])

        self.assertEqual(summary["file_count"], 1)
        self.assertEqual(summary["paths"], ["app.py"])
        self.assertEqual(summary["additions"], 2)
        self.assertEqual(summary["deletions"], 1)
        self.assertEqual(summary["diff_chars"], len("+secret source line"))
        self.assertNotIn("secret source line", str(summary))

    def test_notify_transient_failure_omits_raw_provider_body(self):
        error = LLMServiceUnavailableError(provider="openai", status_code=504, request_id="req-123")

        with patch("biz.queue.worker.notifier.send_notification") as send_notification:
            _notify_llm_service_unavailable(error, project_name="repo", repository_full_name="group/repo")

        content = send_notification.call_args.kwargs["content"]
        self.assertIn("模型服务暂时不可用", content)
        self.assertIn("HTTP 状态: 504", content)
        self.assertIn("请求 ID: req-123", content)
        self.assertNotIn("Traceback", content)
        send_notification.assert_called_once_with(
            content=content,
            project_name="repo",
            repository_full_name="group/repo",
        )


if __name__ == "__main__":
    unittest.main()
