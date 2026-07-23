import os
import time
import unittest
from pathlib import Path

from dotenv import load_dotenv

from biz.llm.factory import Factory
from biz.llm.exceptions import LLMServiceUnavailableError
from biz.utils.code_reviewer import CodeReviewer
from biz.utils.token_util import count_tokens


RUN_LIVE_REPLAY = os.getenv("RUN_LIVE_LLM_REPLAY") == "1"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_SENT_MESSAGE_CHARS = 37_915
LOG_SENT_FILE_MARKERS = 13
LOG_SENT_DIFF_MARKERS = 28
LOG_RAW_CHANGE_CHARS = 2_335_789
LOG_RAW_FILE_MARKERS = 389
LOG_RAW_DIFF_MARKERS = 1_474
SYNTHETIC_COMMIT = "test: sanitized production-scale replay"


def _build_synthetic_changes(target_chars: int, file_markers: int, diff_markers: int) -> str:
    parts = ["["]
    markers_per_file, marker_remainder = divmod(diff_markers, file_markers)
    for file_index in range(file_markers):
        path = f"synthetic/module_{file_index:03d}.py"
        parts.append(
            "{'old_path': '" + path + "', 'new_path': '" + path + "', 'diff': '"
        )
        marker_count = markers_per_file + (1 if file_index < marker_remainder else 0)
        for marker_index in range(marker_count):
            parts.append(
                f"@@ synthetic-{file_index}-{marker_index}\n"
                f"-old_value_{marker_index} = {marker_index}\n"
                f"+new_value_{marker_index} = {marker_index + 1}\n"
            )
        parts.append("', 'additions': 1, 'deletions': 1},")
    parts.append("]")

    payload = "".join(parts)
    if len(payload) > target_chars:
        raise AssertionError(
            f"Synthetic structure exceeds target: structure={len(payload)} target={target_chars}"
        )
    padding_needed = target_chars - len(payload)
    padding_line = "# synthetic padding line for production scale replay 0123456789\n"
    padding = (padding_line * ((padding_needed // len(padding_line)) + 1))[:padding_needed]
    return payload + padding


def _message_metrics(messages) -> dict:
    contents = [message.get("content", "") for message in messages]
    combined = "\n".join(contents)
    return {
        "message_count": len(messages),
        "chars": sum(len(content) for content in contents),
        "tokens": count_tokens(combined),
    }


class _RecordingClient:
    def __init__(self, delegate):
        self.delegate = delegate
        self.last_messages = None

    def completions(self, messages, **kwargs):
        self.last_messages = messages
        return self.delegate.completions(messages=messages, **kwargs)


@unittest.skipUnless(
    RUN_LIVE_REPLAY,
    "Set RUN_LIVE_LLM_REPLAY=1 to execute live model replay cases.",
)
class OpenAILiveReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_dotenv(PROJECT_ROOT / "conf" / ".env", override=False)
        if os.getenv("LLM_PROVIDER") != "openai":
            raise unittest.SkipTest("Live replay requires LLM_PROVIDER=openai.")

    def _new_reviewer(self) -> tuple[CodeReviewer, _RecordingClient]:
        reviewer = CodeReviewer(
            repository_full_name="diagnostics/sanitized-replay",
            project_name="sanitized-replay",
        )
        recorder = _RecordingClient(reviewer.client)
        reviewer.client = recorder
        return reviewer, recorder

    def _payload_for_sent_message_scale(self, reviewer: CodeReviewer) -> str:
        system_chars = len(reviewer.prompts["system_message"].get("content", ""))
        user_template = reviewer.prompts["user_message"]["content"]
        user_overhead = len(user_template.format(diffs_text="", commits_text=SYNTHETIC_COMMIT))
        target_payload_chars = LOG_SENT_MESSAGE_CHARS - system_chars - user_overhead
        self.assertGreater(target_payload_chars, 0)
        payload = _build_synthetic_changes(
            target_chars=target_payload_chars,
            file_markers=LOG_SENT_FILE_MARKERS,
            diff_markers=LOG_SENT_DIFF_MARKERS,
        )
        self.assertLessEqual(count_tokens(payload), int(os.getenv("REVIEW_MAX_TOKENS", "10000")))
        return payload

    def _run_review_case(self, case_name: str, payload: str):
        reviewer, recorder = self._new_reviewer()
        original_metrics = {
            "chars": len(payload),
            "tokens": count_tokens(payload),
            "file_markers": payload.count("new_path"),
            "diff_markers": payload.count("@@"),
        }
        started = time.monotonic()
        try:
            result = reviewer.review_and_strip_code(payload, SYNTHETIC_COMMIT)
        except LLMServiceUnavailableError as exc:
            print(
                f"case={case_name} status=transient_failure "
                f"elapsed_seconds={time.monotonic() - started:.3f} "
                f"original_chars={original_metrics['chars']} "
                f"original_tokens={original_metrics['tokens']} "
                f"file_markers={original_metrics['file_markers']} "
                f"diff_markers={original_metrics['diff_markers']} "
                f"provider={exc.provider} status_code={exc.status_code} "
                f"request_id={exc.request_id or 'unavailable'}"
            )
            raise

        elapsed = time.monotonic() - started
        sent_metrics = _message_metrics(recorder.last_messages)
        score = CodeReviewer.parse_review_score(result)
        print(
            f"case={case_name} status=success elapsed_seconds={elapsed:.3f} "
            f"original_chars={original_metrics['chars']} "
            f"original_tokens={original_metrics['tokens']} "
            f"file_markers={original_metrics['file_markers']} "
            f"diff_markers={original_metrics['diff_markers']} "
            f"sent_messages={sent_metrics['message_count']} "
            f"sent_chars={sent_metrics['chars']} sent_tokens={sent_metrics['tokens']} "
            f"truncated={original_metrics['tokens'] > int(os.getenv('REVIEW_MAX_TOKENS', '10000'))} "
            f"response_chars={len(result or '')} score_parseable={score > 0}"
        )
        self.assertTrue(result)
        self.assertGreater(score, 0)
        return original_metrics, sent_metrics

    def test_01_minimal_connectivity_baseline(self):
        client = Factory().getClient()
        started = time.monotonic()
        result = client.completions(messages=[{"role": "user", "content": '请仅返回 "ok"。'}])
        elapsed = time.monotonic() - started
        print(
            f"case=minimal_baseline status=success elapsed_seconds={elapsed:.3f} "
            f"response_chars={len(result or '')} exact_ok={(result or '').strip() == 'ok'}"
        )
        self.assertEqual((result or "").strip(), "ok")

    def test_02_production_sent_scale(self):
        reviewer, _ = self._new_reviewer()
        payload = self._payload_for_sent_message_scale(reviewer)
        _, sent_metrics = self._run_review_case("production_sent_scale", payload)
        self.assertLessEqual(abs(sent_metrics["chars"] - LOG_SENT_MESSAGE_CHARS), 32)

    def test_03_production_raw_scale_is_truncated_before_send(self):
        payload = _build_synthetic_changes(
            target_chars=LOG_RAW_CHANGE_CHARS,
            file_markers=LOG_RAW_FILE_MARKERS,
            diff_markers=LOG_RAW_DIFF_MARKERS,
        )
        original_metrics, sent_metrics = self._run_review_case("production_raw_scale", payload)
        self.assertEqual(original_metrics["chars"], LOG_RAW_CHANGE_CHARS)
        self.assertEqual(original_metrics["file_markers"], LOG_RAW_FILE_MARKERS)
        self.assertEqual(original_metrics["diff_markers"], LOG_RAW_DIFF_MARKERS)
        self.assertGreater(original_metrics["tokens"], int(os.getenv("REVIEW_MAX_TOKENS", "10000")))
        self.assertLess(sent_metrics["chars"], original_metrics["chars"])

    def test_04_production_sent_scale_repeat(self):
        reviewer, _ = self._new_reviewer()
        payload = self._payload_for_sent_message_scale(reviewer)
        _, sent_metrics = self._run_review_case("production_sent_scale_repeat", payload)
        self.assertLessEqual(abs(sent_metrics["chars"] - LOG_SENT_MESSAGE_CHARS), 32)


if __name__ == "__main__":
    unittest.main()
