import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from biz.utils.review_rules import ReviewRules


class ReviewRulesTest(unittest.TestCase):
    # ------------------------------------------------------------------
    # 辅助：单文件模式（向后兼容）
    # ------------------------------------------------------------------
    def write_rules(self, content: str) -> str:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".yml")
        tmp.write(content)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.remove(tmp.name))
        return tmp.name

    # ------------------------------------------------------------------
    # 辅助：目录模式
    # default_content: default.yaml 的内容字符串（None 表示不创建）
    # repo_files: {filename: yaml_content_str}
    # ------------------------------------------------------------------
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

    # ==================================================================
    # 目录模式测试
    # ==================================================================

    def test_dir_mode_matches_full_name(self):
        d = self.write_rules_dir(repo_files={
            "full.yaml": "repository: group/service-api\nwecom_webhook_url: https://example.com/full\n",
            "name.yaml": "repository: service-web\nwecom_webhook_url: https://example.com/name\n",
        })
        rules = ReviewRules(config_dir=d)
        full_match = rules.get_repository_rule("GROUP/SERVICE-API", "service-api")
        name_match = rules.get_repository_rule("missing/full", "SERVICE-WEB")
        self.assertEqual(full_match.get("wecom_webhook_url"), "https://example.com/full")
        self.assertEqual(name_match.get("wecom_webhook_url"), "https://example.com/name")

    def test_dir_mode_threshold_precedence(self):
        d = self.write_rules_dir(
            default_content="wecom_score_threshold: 80\n",
            repo_files={
                "api.yaml": "repository: group/service-api\nwecom_score_threshold: 70\n",
            },
        )
        rules = ReviewRules(config_dir=d)
        with patch.dict(os.environ, {"WECOM_SCORE_THRESHOLD": "90"}, clear=False):
            self.assertEqual(rules.get_wecom_score_threshold("group/service-api", "service-api"), 70)
            self.assertEqual(rules.get_wecom_score_threshold("group/other", "other"), 80)

    def test_dir_mode_threshold_falls_back_to_environment(self):
        d = self.write_rules_dir()          # 空目录，无 default
        rules = ReviewRules(config_dir=d)
        with patch.dict(os.environ, {"WECOM_SCORE_THRESHOLD": "88"}, clear=False):
            self.assertEqual(rules.get_wecom_score_threshold("group/other", "other"), 88)

    def test_dir_mode_webhook_from_repo_file(self):
        d = self.write_rules_dir(repo_files={
            "api.yaml": "repository: group/service-api\nwecom_webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=repo\n",
        })
        rules = ReviewRules(config_dir=d)
        self.assertEqual(
            rules.get_wecom_webhook_url("group/service-api", "service-api"),
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=repo",
        )

    def test_dir_mode_skip_review_title_and_commits(self):
        d = self.write_rules_dir(
            default_content='review_skip_regex:\n  - "\\\\[skip review\\\\]"\n',
            repo_files={
                "api.yaml": 'repository: group/service-api\nreview_skip_regex:\n  - "^WIP:"\n',
            },
        )
        rules = ReviewRules(config_dir=d)
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

    def test_dir_mode_invalid_regex_is_ignored(self):
        d = self.write_rules_dir(
            default_content='review_skip_regex:\n  - "["\n  - "\\\\[skip review\\\\]"\n',
        )
        rules = ReviewRules(config_dir=d)
        result = rules.should_skip_review(
            repository_full_name="group/other",
            project_name="other",
            title="Ready",
            commits=[{"message": "docs update [skip review]"}],
        )
        self.assertTrue(result.should_skip)
        self.assertEqual(result.pattern, "\\[skip review\\]")

    def test_dir_mode_file_without_repository_field_is_skipped(self):
        """没有 repository: 字段的文件应被忽略，不引发异常。"""
        d = self.write_rules_dir(repo_files={
            "orphan.yaml": "wecom_score_threshold: 50\n",   # 无 repository:
            "api.yaml": "repository: group/service-api\nwecom_score_threshold: 60\n",
        })
        rules = ReviewRules(config_dir=d)
        self.assertEqual(rules.get_wecom_score_threshold("group/service-api", "service-api"), 60)
        self.assertIsNone(rules.get_wecom_score_threshold("group/other", "other"))

    # ==================================================================
    # 单文件模式测试（向后兼容，config_path 显式传入，不受 config_dir 影响）
    # ==================================================================

    def test_single_file_matches_full_name_and_repository_name_fallback(self):
        path = self.write_rules("""
repositories:
  group/service-api:
    wecom_webhook_url: https://example.com/full
  service-web:
    wecom_webhook_url: https://example.com/name
""")
        rules = ReviewRules(config_dir="/nonexistent_dir_abc", config_path=path)

        full_match = rules.get_repository_rule("GROUP/SERVICE-API", "service-api")
        name_match = rules.get_repository_rule("missing/full", "SERVICE-WEB")

        self.assertEqual(full_match.get("wecom_webhook_url"), "https://example.com/full")
        self.assertEqual(name_match.get("wecom_webhook_url"), "https://example.com/name")

    def test_single_file_wecom_threshold_precedence(self):
        path = self.write_rules("""
defaults:
  wecom_score_threshold: 80
repositories:
  group/service-api:
    wecom_score_threshold: 70
""")
        rules = ReviewRules(config_dir="/nonexistent_dir_abc", config_path=path)

        with patch.dict(os.environ, {"WECOM_SCORE_THRESHOLD": "90"}, clear=False):
            self.assertEqual(rules.get_wecom_score_threshold("group/service-api", "service-api"), 70)
            self.assertEqual(rules.get_wecom_score_threshold("group/other", "other"), 80)

    def test_single_file_wecom_threshold_falls_back_to_environment(self):
        path = self.write_rules("repositories: {}\n")
        rules = ReviewRules(config_dir="/nonexistent_dir_abc", config_path=path)
        with patch.dict(os.environ, {"WECOM_SCORE_THRESHOLD": "88"}, clear=False):
            self.assertEqual(rules.get_wecom_score_threshold("group/other", "other"), 88)

    def test_single_file_wecom_webhook_from_repository_rule(self):
        path = self.write_rules("""
repositories:
  group/service-api:
    wecom_webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=repo
""")
        rules = ReviewRules(config_dir="/nonexistent_dir_abc", config_path=path)
        self.assertEqual(
            rules.get_wecom_webhook_url("group/service-api", "service-api"),
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=repo",
        )

    def test_single_file_skip_review_matches_title_and_commit_messages(self):
        path = self.write_rules("""
defaults:
  review_skip_regex:
    - "\\\\[skip review\\\\]"
repositories:
  group/service-api:
    review_skip_regex:
      - "^WIP:"
""")
        rules = ReviewRules(config_dir="/nonexistent_dir_abc", config_path=path)

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

    def test_single_file_invalid_regex_is_ignored(self):
        path = self.write_rules("""
defaults:
  review_skip_regex:
    - "["
    - "\\\\[skip review\\\\]"
""")
        rules = ReviewRules(config_dir="/nonexistent_dir_abc", config_path=path)
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
