import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from biz.utils.im.wecom import WeComNotifier


class WeComNotifierTest(unittest.TestCase):
    def write_rules_dir(self, default_content: str = None, repo_files: dict = None) -> str:
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        if default_content is not None:
            with open(os.path.join(tmpdir, "default.yaml"), "w", encoding="utf-8") as f:
                f.write(default_content)
        for filename, content in (repo_files or {}).items():
            with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
                f.write(content)
        return tmpdir

    def test_repository_webhook_takes_precedence(self):
        d = self.write_rules_dir(repo_files={
            "api.yaml": "repository: group/service-api\nwecom_webhook_url: https://example.com/repo\n",
        })
        notifier = WeComNotifier()
        with patch.dict(os.environ, {
            "REVIEW_RULES_CONFIG_DIR": d,
            "WECOM_WEBHOOK_URL": "https://example.com/default",
        }, clear=False):
            self.assertEqual(
                notifier._get_webhook_url(project_name="service-api", repository_full_name="group/service-api"),
                "https://example.com/repo",
            )

    def test_repository_threshold_controls_send_decision(self):
        d = self.write_rules_dir(repo_files={
            "api.yaml": "repository: group/service-api\nwecom_score_threshold: 70\n",
        })
        notifier = WeComNotifier()
        with patch.dict(os.environ, {
            "REVIEW_RULES_CONFIG_DIR": d,
            "WECOM_SCORE_THRESHOLD": "90",
        }, clear=False):
            self.assertTrue(notifier._should_send_by_score(
                score=69, project_name="service-api", repository_full_name="group/service-api"))
            self.assertFalse(notifier._should_send_by_score(
                score=70, project_name="service-api", repository_full_name="group/service-api"))

    def test_missing_score_does_not_compare_with_threshold(self):
        d = self.write_rules_dir(repo_files={
            "api.yaml": "repository: group/service-api\nwecom_score_threshold: 70\n",
        })
        notifier = WeComNotifier()
        with patch.dict(os.environ, {"REVIEW_RULES_CONFIG_DIR": d}, clear=False):
            self.assertTrue(notifier._should_send_by_score(
                score=None, project_name="service-api", repository_full_name="group/service-api"))


if __name__ == "__main__":
    unittest.main()
