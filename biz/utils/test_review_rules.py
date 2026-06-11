import os
import tempfile
import unittest
from unittest.mock import patch

from biz.utils.review_rules import ReviewRules


class ReviewRulesTest(unittest.TestCase):
    def write_rules(self, content: str) -> str:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".yml")
        tmp.write(content)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.remove(tmp.name))
        return tmp.name

    def test_matches_full_name_and_repository_name_fallback(self):
        path = self.write_rules("""
repositories:
  group/service-api:
    wecom_webhook_url: https://example.com/full
  service-web:
    wecom_webhook_url: https://example.com/name
""")
        rules = ReviewRules(config_path=path)

        full_match = rules.get_repository_rule("GROUP/SERVICE-API", "service-api")
        name_match = rules.get_repository_rule("missing/full", "SERVICE-WEB")

        self.assertEqual(full_match.get("wecom_webhook_url"), "https://example.com/full")
        self.assertEqual(name_match.get("wecom_webhook_url"), "https://example.com/name")

    def test_wecom_threshold_precedence(self):
        path = self.write_rules("""
defaults:
  wecom_score_threshold: 80
repositories:
  group/service-api:
    wecom_score_threshold: 70
""")
        rules = ReviewRules(config_path=path)

        with patch.dict(os.environ, {"WECOM_SCORE_THRESHOLD": "90"}, clear=False):
            self.assertEqual(rules.get_wecom_score_threshold("group/service-api", "service-api"), 70)
            self.assertEqual(rules.get_wecom_score_threshold("group/other", "other"), 80)

    def test_wecom_threshold_falls_back_to_environment(self):
        path = self.write_rules("""
repositories: {}
""")
        rules = ReviewRules(config_path=path)

        with patch.dict(os.environ, {"WECOM_SCORE_THRESHOLD": "88"}, clear=False):
            self.assertEqual(rules.get_wecom_score_threshold("group/other", "other"), 88)

    def test_wecom_webhook_from_repository_rule(self):
        path = self.write_rules("""
repositories:
  group/service-api:
    wecom_webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=repo
""")
        rules = ReviewRules(config_path=path)

        self.assertEqual(
            rules.get_wecom_webhook_url("group/service-api", "service-api"),
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=repo",
        )

    def test_should_skip_review_matches_title_and_commit_messages(self):
        path = self.write_rules("""
defaults:
  review_skip_regex:
    - "\\\\[skip review\\\\]"
repositories:
  group/service-api:
    review_skip_regex:
      - "^WIP:"
""")
        rules = ReviewRules(config_path=path)

        repo_match = rules.should_skip_review(
            repository_full_name="group/service-api",
            project_name="service-api",
            title="WIP: draft change",
            commits=[{"message": "normal commit"}],
        )
        default_match = rules.should_skip_review(
            repository_full_name="group/other",
            project_name="other",
            title="Ready",
            commits=[{"message": "docs update [skip review]"}],
        )

        self.assertTrue(repo_match.should_skip)
        self.assertEqual(repo_match.pattern, "^WIP:")
        self.assertTrue(default_match.should_skip)
        self.assertEqual(default_match.pattern, "\\[skip review\\]")

    def test_invalid_regex_is_ignored(self):
        path = self.write_rules("""
defaults:
  review_skip_regex:
    - "["
    - "\\\\[skip review\\\\]"
""")
        rules = ReviewRules(config_path=path)

        result = rules.should_skip_review(
            repository_full_name="group/other",
            project_name="other",
            title="Ready",
            commits=[{"message": "docs update [skip review]"}],
        )

        self.assertTrue(result.should_skip)
        self.assertEqual(result.pattern, "\\[skip review\\]")


if __name__ == "__main__":
    unittest.main()
