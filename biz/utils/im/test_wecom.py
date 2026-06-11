import os
import tempfile
import unittest
from unittest.mock import patch

from biz.utils.im.wecom import WeComNotifier


class WeComNotifierTest(unittest.TestCase):
    def write_rules(self, content: str) -> str:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".yml")
        tmp.write(content)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.remove(tmp.name))
        return tmp.name

    def test_repository_webhook_takes_precedence(self):
        path = self.write_rules("""
repositories:
  group/service-api:
    wecom_webhook_url: https://example.com/repo
""")
        notifier = WeComNotifier()

        with patch.dict(os.environ, {
            "REVIEW_RULES_CONFIG_PATH": path,
            "WECOM_WEBHOOK_URL": "https://example.com/default",
        }, clear=False):
            self.assertEqual(
                notifier._get_webhook_url(project_name="service-api", repository_full_name="group/service-api"),
                "https://example.com/repo",
            )

    def test_repository_threshold_controls_send_decision(self):
        path = self.write_rules("""
repositories:
  group/service-api:
    wecom_score_threshold: 70
""")
        notifier = WeComNotifier()

        with patch.dict(os.environ, {"REVIEW_RULES_CONFIG_PATH": path, "WECOM_SCORE_THRESHOLD": "90"}, clear=False):
            self.assertTrue(notifier._should_send_by_score(score=69, project_name="service-api", repository_full_name="group/service-api"))
            self.assertFalse(notifier._should_send_by_score(score=70, project_name="service-api", repository_full_name="group/service-api"))


if __name__ == "__main__":
    unittest.main()
