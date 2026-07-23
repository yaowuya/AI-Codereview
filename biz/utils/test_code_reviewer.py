import unittest
from unittest.mock import patch

from biz.llm.exceptions import LLMRequestRejectedError, LLMServiceUnavailableError
from biz.utils.code_reviewer import BaseReviewer, CodeReviewer
from biz.utils.token_util import count_tokens


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


class _RecordingClient:
    def __init__(self):
        self.messages = []

    def completions(self, messages):
        self.messages.append(messages)
        return f"batch result {len(self.messages)}"


class _PartiallyUnavailableClient:
    def __init__(self):
        self.calls = 0

    def completions(self, messages):
        self.calls += 1
        if self.calls == 2:
            raise LLMServiceUnavailableError(
                provider="openai",
                status_code=504,
                request_id="req-batch-2",
            )
        return f"batch result {self.calls}"


class CodeReviewerBatchingTest(unittest.TestCase):
    def _reviewer(self):
        reviewer = CodeReviewer.__new__(CodeReviewer)
        reviewer.client = _RecordingClient()
        reviewer.prompts = {
            "system_message": {"role": "system", "content": "review system " * 80},
            "user_message": {
                "role": "user",
                "content": "commits={commits_text}\ndiffs={diffs_text}",
            },
        }
        return reviewer

    def test_large_changes_are_reviewed_in_file_boundary_batches(self):
        changes = [
            {
                "new_path": f"src/module_{index}.py",
                "diff": "+value = '" + (chr(65 + index) * 900) + "'",
            }
            for index in range(6)
        ]
        reviewer = self._reviewer()

        with patch.dict("os.environ", {"REVIEW_BATCH_MAX_TOKENS": "700"}, clear=False):
            result = reviewer.review_changes_in_batches(changes, "commit context")

        self.assertGreater(len(reviewer.client.messages), 1)
        combined_requests = "\n".join(
            message["content"]
            for batch in reviewer.client.messages
            for message in batch
        )
        for change in changes:
            self.assertEqual(combined_requests.count(change["new_path"]), 1)
        for messages in reviewer.client.messages:
            combined_content = "\n".join(message["content"] for message in messages)
            self.assertLessEqual(count_tokens(combined_content), 700)
            self.assertIn("commit context", combined_content)
        self.assertIn("批次 1/", result)
        self.assertIn("batch result 1", result)

    def test_production_scale_changes_cover_all_files_with_bounded_batches(self):
        changes = [
            {
                "new_path": f"apps/service/module_{index:02d}.py",
                "diff": "\n".join(
                    f"+value_{line} = '{chr(65 + index % 26) * 80}'"
                    for line in range(55)
                ),
            }
            for index in range(25)
        ]
        reviewer = self._reviewer()

        with patch.dict("os.environ", {"REVIEW_BATCH_MAX_TOKENS": "4000"}, clear=False), \
                patch("biz.utils.code_reviewer.logger.info") as log_info:
            reviewer.review_changes_in_batches(changes, "production-scale commit")

        combined_requests = "\n".join(
            message["content"]
            for batch in reviewer.client.messages
            for message in batch
        )
        self.assertGreater(len(reviewer.client.messages), 1)
        self.assertTrue(all(change["new_path"] in combined_requests for change in changes))
        self.assertTrue(all(
            count_tokens("\n".join(message["content"] for message in batch)) <= 4000
            for batch in reviewer.client.messages
        ))
        rendered_logs = " ".join(str(call) for call in log_info.call_args_list)
        self.assertIn("batch_count", rendered_logs)
        self.assertIn("content_tokens", rendered_logs)

    def test_transient_failure_in_one_batch_preserves_other_results(self):
        changes = [
            {
                "new_path": f"src/module_{index}.py",
                "diff": "+value = '" + (chr(65 + index) * 900) + "'",
            }
            for index in range(6)
        ]
        reviewer = self._reviewer()
        reviewer.client = _PartiallyUnavailableClient()

        with patch.dict("os.environ", {"REVIEW_BATCH_MAX_TOKENS": "700"}, clear=False):
            result = reviewer.review_changes_in_batches(changes, "commit context")

        self.assertIn("batch result 1", result)
        self.assertIn("batch result 3", result)
        self.assertIn("批次 2/", result)
        self.assertIn("审查失败", result)
        self.assertIn("HTTP 状态: 504", result)
        self.assertIn("请求 ID: req-batch-2", result)
        self.assertIn("部分完成", result)
        self.assertIn("batch result 4", result)
        self.assertEqual(reviewer.client.calls, 4)

    def test_all_transient_batch_failures_propagate_service_unavailable(self):
        changes = [{"new_path": "src/module.py", "diff": "+value = 1"}]
        reviewer = self._reviewer()
        reviewer.client = _PartiallyUnavailableClient()
        reviewer.client.calls = 1

        with patch.dict("os.environ", {"REVIEW_BATCH_MAX_TOKENS": "700"}, clear=False):
            with self.assertRaises(LLMServiceUnavailableError):
                reviewer.review_changes_in_batches(changes, "commit context")

    def test_parse_review_score_uses_lowest_batch_score(self):
        review_text = """
        ### 批次 1/3
        总分: 92分
        ### 批次 2/3
        总分: 61分
        ### 批次 3/3
        总分: 84分
        """

        self.assertEqual(CodeReviewer.parse_review_score(review_text), 61)

    def test_parse_review_score_returns_zero_for_partial_result(self):
        review_text = """
        ## AI Review 分批结果（部分完成）
        ### 批次 1/2
        总分: 92分
        ### 批次 2/2
        本批次审查失败：AI 模型服务暂时不可用。
        """

        self.assertEqual(CodeReviewer.parse_review_score(review_text), 0)

    def test_oversized_single_file_is_split_on_diff_line_boundaries(self):
        diff_lines = [f"+line_{index} = '{'x' * 120}'" for index in range(20)]
        changes = [{"new_path": "src/large.py", "diff": "\n".join(diff_lines)}]
        reviewer = self._reviewer()

        with patch.dict("os.environ", {"REVIEW_BATCH_MAX_TOKENS": "350"}, clear=False):
            reviewer.review_changes_in_batches(changes, "commit context")

        self.assertGreater(len(reviewer.client.messages), 1)
        combined_requests = "\n".join(batch[1]["content"] for batch in reviewer.client.messages)
        for line in diff_lines:
            self.assertEqual(combined_requests.count(line), 1)
        self.assertTrue(all(
            count_tokens("\n".join(message["content"] for message in batch)) <= 350
            for batch in reviewer.client.messages
        ))


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
