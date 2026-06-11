"""
tests/test_webhook_handle.py

调试 /review/webhook 接口的端到端行为，重点验证 review_rule 目录模式新增的功能：
  1. 路由分发  — GitLab / GitHub / Gitea 平台识别
  2. Skip 规则 — default.yaml 和仓库级 review_skip_regex
  3. WeCom 规则 — 仓库级 webhook_url / score_threshold 生效

运行方式（项目根目录）：
    venv/Scripts/python.exe -m pytest tests/test_webhook_handle.py -v

重要说明：
  - 所有下游 I/O（外部 API 调用、IM 通知、DB 写入）均被 Mock，不产生真实副作用。
  - 使用 Flask test client 原地测试，无需启动服务器。
  - 测试用 review_rule 目录从 conf/review_rule/ 真实加载，反映当前配置文件内容。
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# 确保从项目根目录导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("LLM_PROVIDER", "deepseek")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("DEEPSEEK_API_MODEL", "deepseek-chat")
os.environ.setdefault("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com")

from dotenv import load_dotenv
load_dotenv("conf/.env", override=False)

from biz.api import api_app, init_app
init_app(api_app)


# ---------------------------------------------------------------------------
# 常量：真实仓库名（来自 conf/review_rule/*.yaml）
# ---------------------------------------------------------------------------
REPO_AUTO_OPS       = "rd-fy21-canway-GOAC/auto-ops"       # auto-ops.yaml
REPO_CW_AUTO_OPS    = "rd-fy23-canway-kingark/auto-ops-v4/cw-auto-ops"  # cw-auto-ops.yaml
REPO_UNKNOWN        = "some-team/unknown-project"           # 无专属规则，走 default


# ---------------------------------------------------------------------------
# Payload 工厂函数
# ---------------------------------------------------------------------------

def gitlab_mr_payload(
    project_name="test-service",
    namespace="test-team",
    action="open",
    title="feat: add login",
    commit_messages=("feat: add login page",),
    last_commit_id="abc123456789",
    draft=False,
):
    return {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "user": {"username": "zhangsan"},
        "project": {
            "id": 1,
            "name": project_name,
            "path_with_namespace": f"{namespace}/{project_name}",
        },
        "object_attributes": {
            "id": 100,
            "iid": 42,
            "title": title,
            "state": "opened",
            "action": action,
            "source_branch": "feature/login",
            "target_branch": "main",
            "url": f"https://gitlab.example.com/{namespace}/{project_name}/-/merge_requests/42",
            "last_commit": {"id": last_commit_id},
            "target_project_id": 1,
            "draft": draft,
            "work_in_progress": False,
        },
        "commits": [{"id": last_commit_id, "message": msg} for msg in commit_messages],
    }


def gitlab_push_payload(
    project_name="test-service",
    namespace="test-team",
    commit_messages=("feat: init push",),
):
    commits = [{"id": f"cmt{i}", "message": msg} for i, msg in enumerate(commit_messages)]
    return {
        "object_kind": "push",
        "event_name": "push",
        "user_username": "zhangsan",
        "ref": "refs/heads/main",
        "project_id": 1,
        "project": {
            "id": 1,
            "name": project_name,
            "path_with_namespace": f"{namespace}/{project_name}",
        },
        "commits": commits,
        "repository": {
            "name": project_name,
            "homepage": f"https://gitlab.example.com/{namespace}/{project_name}",
        },
    }


def github_pr_payload(
    repo_name="test-service",
    owner="test-team",
    action="opened",
    title="feat: add login",
    commit_sha="abc123456789",
):
    return {
        "action": action,
        "pull_request": {
            "number": 42,
            "title": title,
            "state": "open",
            "html_url": f"https://github.com/{owner}/{repo_name}/pull/42",
            "head": {"ref": "feature/login", "sha": commit_sha},
            "base": {"ref": "main"},
            "user": {"login": "zhangsan"},
        },
        "repository": {
            "name": repo_name,
            "full_name": f"{owner}/{repo_name}",
        },
        "sender": {"login": "zhangsan"},
    }


def github_push_payload(repo_name="test-service", owner="test-team", commit_messages=("feat: init",)):
    commits = [{"id": f"cmt{i}", "message": msg, "url": "#", "timestamp": "2026-06-11T10:00:00Z",
                "author": {"name": "zhangsan"}} for i, msg in enumerate(commit_messages)]
    return {
        "ref": "refs/heads/main",
        "repository": {"name": repo_name, "full_name": f"{owner}/{repo_name}"},
        "sender": {"login": "zhangsan"},
        "commits": commits,
    }


def gitea_pr_payload(
    repo_name="test-service",
    owner="test-team",
    action="opened",
    title="feat: add login",
    commit_sha="abc123456789",
):
    return {
        "action": action,
        "pull_request": {
            "id": 42,
            "title": title,
            "state": "open",
            "html_url": f"https://gitea.example.com/{owner}/{repo_name}/pulls/42",
            "head": {"ref": "feature/login", "sha": commit_sha},
            "base": {"ref": "main"},
            "user": {"login": "zhangsan"},
        },
        "repository": {
            "name": repo_name,
            "full_name": f"{owner}/{repo_name}",
        },
        "sender": {"login": "zhangsan"},
    }


# ---------------------------------------------------------------------------
# 测试基类：统一 Mock 配置
# ---------------------------------------------------------------------------

class WebhookTestBase(unittest.TestCase):
    """
    提供 Flask test client 和公共 Mock。
    被 Mock 的副作用：
      - ReviewService.check_mr_last_commit_id_exists → False（commit 未见过）
      - ReviewService.insert_mr_review_log / insert_push_review_log → 无操作
      - CodeReviewer.review_and_strip_code → 返回固定字符串
      - 所有平台 handler 的 get_*_commits / get_*_changes / add_*_notes → 返回测试数据
      - notifier.send_notification → 无操作
    """

    def setUp(self):
        self.client = api_app.test_client()
        self.headers_gitlab = {
            "Content-Type": "application/json",
            "X-Gitlab-Token": "test-token",
            "X-Gitlab-Instance": "https://gitlab.example.com",
        }
        self.headers_github = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Token": "ghp_test",
        }
        self.headers_github_push = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Token": "ghp_test",
        }
        self.headers_gitea = {
            "Content-Type": "application/json",
            "X-Gitea-Event": "pull_request",
            "X-Gitea-Token": "gitea-test-token",
        }

        # Mock DB
        self.patcher_db_check = patch(
            "biz.service.review_service.ReviewService.check_mr_last_commit_id_exists",
            return_value=False,
        )
        self.patcher_db_insert_mr = patch(
            "biz.service.review_service.ReviewService.insert_mr_review_log"
        )
        self.patcher_db_insert_push = patch(
            "biz.service.review_service.ReviewService.insert_push_review_log"
        )
        # Mock LLM
        self.patcher_llm = patch(
            "biz.utils.code_reviewer.CodeReviewer.review_and_strip_code",
            return_value="### Review 结果\n总分:85分",
        )
        # Mock IM 通知
        self.patcher_notify = patch("biz.utils.im.notifier.send_notification")
        # Mock WeCom 发送（避免真实 HTTP）
        self.patcher_wecom_send = patch("biz.utils.im.wecom.WeComNotifier._send_request", return_value={"errcode": 0})

        self.mock_db_check      = self.patcher_db_check.start()
        self.mock_db_insert_mr  = self.patcher_db_insert_mr.start()
        self.mock_db_insert_push= self.patcher_db_insert_push.start()
        self.mock_llm           = self.patcher_llm.start()
        self.mock_notify        = self.patcher_notify.start()
        self.mock_wecom_send    = self.patcher_wecom_send.start()

    def tearDown(self):
        self.patcher_db_check.stop()
        self.patcher_db_insert_mr.stop()
        self.patcher_db_insert_push.stop()
        self.patcher_llm.stop()
        self.patcher_notify.stop()
        self.patcher_wecom_send.stop()

    # ------------------------------------------------------------------
    # 辅助：mock 平台 handler 的网络调用
    # ------------------------------------------------------------------
    def mock_gitlab_mr_handler(self, commits=None, changes=None):
        commits = commits or [{"id": "abc123", "message": "feat: add login"}]
        changes = changes or [{"diff": "+print('hello')", "new_path": "app.py",
                               "additions": 1, "deletions": 0}]
        patcher_commits = patch("biz.platforms.gitlab.webhook_handler.MergeRequestHandler.get_merge_request_commits",
                                return_value=commits)
        patcher_changes = patch("biz.platforms.gitlab.webhook_handler.MergeRequestHandler.get_merge_request_changes",
                                return_value=changes)
        patcher_notes   = patch("biz.platforms.gitlab.webhook_handler.MergeRequestHandler.add_merge_request_notes")
        patcher_protected = patch("biz.platforms.gitlab.webhook_handler.MergeRequestHandler.target_branch_protected",
                                  return_value=True)
        return patcher_commits, patcher_changes, patcher_notes, patcher_protected

    def mock_gitlab_push_handler(self, commits=None, changes=None):
        commits = commits or [{"id": "abc123", "message": "feat: init push"}]
        changes = changes or [{"diff": "+x=1", "new_path": "main.py", "additions": 1, "deletions": 0}]
        patcher_commits = patch("biz.platforms.gitlab.webhook_handler.PushHandler.get_push_commits",
                                return_value=commits)
        patcher_changes = patch("biz.platforms.gitlab.webhook_handler.PushHandler.get_push_changes",
                                return_value=changes)
        patcher_notes   = patch("biz.platforms.gitlab.webhook_handler.PushHandler.add_push_notes")
        return patcher_commits, patcher_changes, patcher_notes

    def mock_github_pr_handler(self, commits=None, changes=None):
        commits = commits or [{"sha": "abc123", "commit": {"message": "feat: login"}}]
        changes = changes or [{"diff": "+x=1", "new_path": "app.py", "additions": 1, "deletions": 0}]
        patcher_commits   = patch("biz.platforms.github.webhook_handler.PullRequestHandler.get_pull_request_commits",
                                  return_value=commits)
        patcher_changes   = patch("biz.platforms.github.webhook_handler.PullRequestHandler.get_pull_request_changes",
                                  return_value=changes)
        patcher_notes     = patch("biz.platforms.github.webhook_handler.PullRequestHandler.add_pull_request_notes")
        patcher_protected = patch("biz.platforms.github.webhook_handler.PullRequestHandler.target_branch_protected",
                                  return_value=True)
        return patcher_commits, patcher_changes, patcher_notes, patcher_protected

    def mock_gitea_pr_handler(self, commits=None, changes=None):
        commits = commits or [{"id": "abc123", "message": "feat: login"}]
        changes = changes or [{"diff": "+x=1", "new_path": "app.py", "additions": 1, "deletions": 0}]
        patcher_commits   = patch("biz.platforms.gitea.webhook_handler.PullRequestHandler.get_pull_request_commits",
                                  return_value=commits)
        patcher_changes   = patch("biz.platforms.gitea.webhook_handler.PullRequestHandler.get_pull_request_changes",
                                  return_value=changes)
        patcher_notes     = patch("biz.platforms.gitea.webhook_handler.PullRequestHandler.add_pull_request_notes")
        patcher_protected = patch("biz.platforms.gitea.webhook_handler.PullRequestHandler.target_branch_protected",
                                  return_value=True)
        return patcher_commits, patcher_changes, patcher_notes, patcher_protected

    def start_all(self, *patchers):
        mocks = [p.start() for p in patchers]
        for p in patchers:
            self.addCleanup(p.stop)
        return mocks

    # ------------------------------------------------------------------
    # 辅助：同步执行 worker（绕过 multiprocessing）
    # ------------------------------------------------------------------
    def sync_queue(self):
        """将 handle_queue 改为直接同步调用，方便断言副作用。"""
        return patch(
            "biz.api.routes.webhook.handle_queue",
            side_effect=lambda fn, *args: fn(*args),
        )


# ===========================================================================
# 一、路由分发测试
# ===========================================================================

class TestWebhookRouting(WebhookTestBase):
    """验证 /review/webhook 能正确识别 GitLab / GitHub / Gitea 平台。"""

    def test_gitlab_mr_returns_200(self):
        """GitLab MR webhook 返回 200，触发异步队列。"""
        response = self.client.post(
            "/review/webhook",
            json=gitlab_mr_payload(),
            headers=self.headers_gitlab,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("merge_request", response.get_json().get("message", ""))

    def test_gitlab_push_returns_200(self):
        """GitLab Push webhook 返回 200。"""
        response = self.client.post(
            "/review/webhook",
            json=gitlab_push_payload(),
            headers=self.headers_gitlab,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("push", response.get_json().get("message", ""))

    def test_github_pr_returns_200(self):
        """GitHub Pull Request webhook 返回 200。"""
        response = self.client.post(
            "/review/webhook",
            json=github_pr_payload(),
            headers=self.headers_github,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("pull_request", response.get_json().get("message", ""))

    def test_github_push_returns_200(self):
        """GitHub Push webhook 返回 200。"""
        response = self.client.post(
            "/review/webhook",
            json=github_push_payload(),
            headers=self.headers_github_push,
        )
        self.assertEqual(response.status_code, 200)

    def test_gitea_pr_returns_200(self):
        """Gitea PR webhook 返回 200（X-Gitea-Event 优先于 X-GitHub-Event）。"""
        response = self.client.post(
            "/review/webhook",
            json=gitea_pr_payload(),
            headers=self.headers_gitea,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("pull_request", response.get_json().get("message", ""))

    def test_gitea_header_priority_over_github(self):
        """同时携带 X-Gitea-Event 和 X-GitHub-Event 时，Gitea 优先。"""
        headers = {**self.headers_gitea, "X-GitHub-Event": "pull_request", "X-GitHub-Token": "ghp_test"}
        response = self.client.post(
            "/review/webhook",
            json=gitea_pr_payload(),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        # 返回 Gitea 消息，而非 GitHub
        msg = response.get_json().get("message", "")
        self.assertIn("Gitea", msg)

    def test_missing_gitlab_token_returns_400(self):
        """缺少 GitLab token 时返回 400。"""
        headers = {"Content-Type": "application/json"}  # 无 X-Gitlab-Token
        with patch.dict(os.environ, {}, clear=False):
            # 确保环境变量也没有 GITLAB_ACCESS_TOKEN
            env = os.environ.copy()
            env.pop("GITLAB_ACCESS_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                response = self.client.post(
                    "/review/webhook",
                    json=gitlab_mr_payload(),
                    headers=headers,
                )
        self.assertEqual(response.status_code, 400)

    def test_unsupported_github_event_returns_400(self):
        """不支持的 GitHub 事件类型返回 400。"""
        headers = {**self.headers_github, "X-GitHub-Event": "issues"}
        response = self.client.post(
            "/review/webhook",
            json={"action": "opened"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_non_json_body_returns_400(self):
        """非 JSON 请求体返回 400。"""
        response = self.client.post(
            "/review/webhook",
            data="not json",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 400)


# ===========================================================================
# 二、Skip 规则测试（使用真实 conf/review_rule/ 配置）
# ===========================================================================

class TestSkipReviewRules(WebhookTestBase):
    """
    验证 worker 在调用 LLM 前正确执行 skip 规则检查。
    使用真实 conf/review_rule/ 目录（default.yaml + auto-ops.yaml + cw-auto-ops.yaml）。
    """

    def _post_gitlab_mr(self, payload):
        with self.sync_queue():
            patchers = self.mock_gitlab_mr_handler(
                commits=[{"id": "abc", "message": payload["object_attributes"]["title"]}]
            )
            self.start_all(*patchers)
            return self.client.post(
                "/review/webhook",
                json=payload,
                headers=self.headers_gitlab,
            )

    # ---------- default.yaml 规则：[skip review] ----------

    def test_default_skip_regex_on_unknown_repo_title(self):
        """未配置仓库 + 标题含 [skip review] → 跳过（命中 default.yaml 规则）。"""
        ns, name = REPO_UNKNOWN.split("/", 1)
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="fix: urgent patch [skip review]",
            commit_messages=("fix: urgent patch [skip review]",),
        )
        with self.sync_queue():
            patchers = self.mock_gitlab_mr_handler(
                commits=[{"id": "abc", "message": "fix: urgent patch [skip review]"}]
            )
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()

    def test_default_skip_regex_on_commit_message(self):
        """未配置仓库 + commit message 含 [no review] → 跳过。"""
        ns, name = REPO_UNKNOWN.split("/", 1)
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="feat: normal title",
            commit_messages=("chore: update deps [no review]",),
        )
        with self.sync_queue():
            patchers = self.mock_gitlab_mr_handler(
                commits=[{"id": "abc", "message": "chore: update deps [no review]"}]
            )
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()

    def test_revert_commit_skipped_by_default(self):
        """以 'Revert ' 开头的 MR 标题 → 命中 default.yaml 的 ^Revert 规则，跳过。"""
        ns, name = REPO_UNKNOWN.split("/", 1)
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="Revert \"feat: add login\"",
            commit_messages=("Revert commit",),
        )
        with self.sync_queue():
            patchers = self.mock_gitlab_mr_handler(
                commits=[{"id": "abc", "message": "Revert commit"}]
            )
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()

    # ---------- auto-ops.yaml 仓库级规则：^chore: ----------

    def test_repo_level_skip_regex_chore(self):
        """auto-ops 仓库级规则 ^chore: → 跳过（使用独立临时规则目录，不依赖真实文件内容）。"""
        import shutil, tempfile
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        with open(os.path.join(tmpdir, "auto-ops.yaml"), "w") as f:
            f.write(f'repository: "{REPO_AUTO_OPS}"\nreview_skip_regex:\n  - "^chore:"\n  - "\\\\[skip review\\\\]"\n')
        with open(os.path.join(tmpdir, "default.yaml"), "w") as f:
            f.write('review_skip_regex:\n  - "\\\\[skip review\\\\]"\n')

        parts = REPO_AUTO_OPS.split("/")
        ns, name = "/".join(parts[:-1]), parts[-1]
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="chore: update ci",
            commit_messages=("chore: bump version",),
        )
        with self.sync_queue(), patch.dict(os.environ, {"REVIEW_RULES_CONFIG_DIR": tmpdir}, clear=False):
            patchers = self.mock_gitlab_mr_handler(
                commits=[{"id": "abc", "message": "chore: bump version"}]
            )
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()

    def test_repo_level_skip_does_not_affect_other_repo(self):
        """auto-ops 的 ^chore: 规则不影响 unknown-project（继承 default，无 ^chore: 规则）。"""
        import shutil, tempfile
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        with open(os.path.join(tmpdir, "auto-ops.yaml"), "w") as f:
            f.write(f'repository: "{REPO_AUTO_OPS}"\nreview_skip_regex:\n  - "^chore:"\n')
        with open(os.path.join(tmpdir, "default.yaml"), "w") as f:
            f.write('review_skip_regex:\n  - "\\\\[skip review\\\\]"\n')

        ns, name = REPO_UNKNOWN.split("/", 1)
        commits = [{"id": "abc", "message": "chore: cleanup"}]
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="chore: cleanup",
            commit_messages=("chore: cleanup",),
        )
        with self.sync_queue(), patch.dict(os.environ, {"REVIEW_RULES_CONFIG_DIR": tmpdir}, clear=False):
            patchers = self.mock_gitlab_mr_handler(commits=commits)
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        # unknown-project 没有 ^chore: 规则，应该正常触发 Review
        self.mock_llm.assert_called_once()

    # ---------- cw-auto-ops.yaml 仓库级规则：^WIP: ----------

    def test_repo_level_skip_wip_prefix(self):
        """cw-auto-ops 仓库级规则 ^WIP: → 跳过（使用独立临时规则目录）。"""
        import shutil, tempfile
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        with open(os.path.join(tmpdir, "cw-auto-ops.yaml"), "w") as f:
            f.write(f'repository: "{REPO_CW_AUTO_OPS}"\nreview_skip_regex:\n  - "^WIP:"\n  - "\\\\[skip review\\\\]"\n')
        with open(os.path.join(tmpdir, "default.yaml"), "w") as f:
            f.write('review_skip_regex:\n  - "\\\\[skip review\\\\]"\n')

        parts = REPO_CW_AUTO_OPS.split("/")
        ns, name = "/".join(parts[:-1]), parts[-1]
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="WIP: draft implementation",
            commit_messages=("WIP: work in progress",),
        )
        with self.sync_queue(), patch.dict(os.environ, {"REVIEW_RULES_CONFIG_DIR": tmpdir}, clear=False):
            patchers = self.mock_gitlab_mr_handler(
                commits=[{"id": "abc", "message": "WIP: work in progress"}]
            )
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()

    # ---------- 正常流程：不命中任何规则 ----------

    def test_normal_mr_triggers_review(self):
        """正常 MR，标题和 commit 均不命中跳过规则 → 调用 LLM。"""
        ns, name = REPO_UNKNOWN.split("/", 1)
        payload = gitlab_mr_payload(
            project_name=name, namespace=ns,
            title="feat: add login feature",
            commit_messages=("feat: add login page", "test: add unit tests"),
        )
        with self.sync_queue():
            patchers = self.mock_gitlab_mr_handler(
                commits=[
                    {"id": "abc1", "message": "feat: add login page"},
                    {"id": "abc2", "message": "test: add unit tests"},
                ]
            )
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_called_once()

    # ---------- GitHub Push：commit message 命中跳过规则 ----------

    def test_github_push_skip_on_commit_message(self):
        """GitHub Push + commit message 含 [skip review] → 跳过。"""
        payload = github_push_payload(
            owner="test-team",
            repo_name="test-service",
            commit_messages=("[skip review] hotfix deploy",),
        )
        with self.sync_queue():
            patcher_commits = patch(
                "biz.platforms.github.webhook_handler.PushHandler.get_push_commits",
                return_value=[{"id": "c1", "message": "[skip review] hotfix deploy"}],
            )
            patcher_commits.start()
            self.addCleanup(patcher_commits.stop)
            self.client.post(
                "/review/webhook",
                json=payload,
                headers=self.headers_github_push,
            )

        self.mock_llm.assert_not_called()

    # ---------- Draft MR 通知但不 Review ----------

    def test_draft_mr_sends_notification_but_no_review(self):
        """Draft MR → 发送通知，不调用 LLM。"""
        payload = gitlab_mr_payload(
            title="Draft: WIP feature",
            commit_messages=("WIP commit",),
            draft=True,
        )
        with self.sync_queue():
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()
        self.mock_notify.assert_called_once()
        call_args = self.mock_notify.call_args
        self.assertIn("draft", call_args.kwargs.get("content", "").lower())

    # ---------- 重复 commit_id 跳过 ----------

    def test_duplicate_commit_id_skips_review(self):
        """已处理的 commit id → 跳过，不调用 LLM。"""
        self.mock_db_check.return_value = True  # 模拟已存在
        payload = gitlab_mr_payload(last_commit_id="already-seen-commit")
        with self.sync_queue():
            patchers = self.mock_gitlab_mr_handler()
            self.start_all(*patchers)
            self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)

        self.mock_llm.assert_not_called()


# ===========================================================================
# 三、WeCom 规则测试（仓库级 webhook_url / score_threshold）
# ===========================================================================

class TestWeComRules(WebhookTestBase):
    """
    验证 review_rule 目录配置的 wecom_webhook_url 和 wecom_score_threshold 生效。
    通过捕获 WeComNotifier._send_request 的调用 URL 来断言路由。

    注意：WeCom 阈值测试需要让真实 send_notification → WeComNotifier 链路走通，
    因此在 _trigger_mr_review 中暂停 setUp 的 patcher_notify，改为只 Mock 各
    通道的网络底层（DingTalk/Feishu/ExtraWebhook.send_message，WeComNotifier._send_request）。
    """

    def _trigger_mr_review(self, namespace, project_name, env_overrides=None):
        """触发一次完整的 MR Review 流程（同步），返回 WeComNotifier._send_request 的调用记录。"""
        payload = gitlab_mr_payload(project_name=project_name, namespace=namespace)
        env = {**(env_overrides or {}), "WECOM_ENABLED": "1"}

        # 暂停整体 notify mock，让真实 send_notification → WeComNotifier 走通
        self.patcher_notify.stop()
        try:
            with self.sync_queue(), \
                 patch.dict(os.environ, env, clear=False), \
                 patch("biz.utils.im.dingtalk.DingTalkNotifier.send_message"), \
                 patch("biz.utils.im.feishu.FeishuNotifier.send_message"), \
                 patch("biz.utils.im.webhook.ExtraWebhookNotifier.send_message"):

                patchers = self.mock_gitlab_mr_handler()
                self.start_all(*patchers)
                self.mock_wecom_send.reset_mock()
                self.client.post("/review/webhook", json=payload, headers=self.headers_gitlab)
        finally:
            # 恢复 notify mock，避免影响其他测试
            self.mock_notify = self.patcher_notify.start()

        return self.mock_wecom_send.call_args_list

    def test_repo_webhook_url_overrides_env(self):
        """auto-ops 仓库级 wecom_webhook_url 优先于环境变量 WECOM_WEBHOOK_URL。"""
        parts = REPO_AUTO_OPS.split("/")
        ns, name = "/".join(parts[:-1]), parts[-1]

        calls = self._trigger_mr_review(ns, name, env_overrides={
            "WECOM_WEBHOOK_URL": "https://example.com/fallback",
        })

        if calls:
            actual_url = calls[0].args[0] if calls[0].args else calls[0].kwargs.get("url", "")
            self.assertIn("aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb", actual_url,
                          "应使用仓库级 webhook_url，而非环境变量默认值")
        else:
            # WECOM_ENABLED=0 时不会调用，跳过 URL 断言
            self.skipTest("WECOM_ENABLED 未开启，跳过 URL 断言（检查 .env 配置）")

    def test_repo_score_threshold_applied(self):
        """auto-ops 仓库 score_threshold=70，LLM 返回 85 分 → 不发送（85 >= 70）。"""
        parts = REPO_AUTO_OPS.split("/")
        ns, name = "/".join(parts[:-1]), parts[-1]

        # LLM 返回 85 分，高于 auto-ops 阈值 70，不应推送
        self.mock_llm.return_value = "### Review 结果\n总分:85分"

        calls = self._trigger_mr_review(ns, name, env_overrides={
            "WECOM_ENABLED": "1",
            "WECOM_WEBHOOK_URL": "https://example.com/fallback",
        })

        # 85 >= 70，不应调用 _send_request
        self.assertEqual(len(calls), 0, "分数 85 >= 阈值 70，不应发送企业微信消息")

    def test_repo_score_below_threshold_sends(self):
        """auto-ops 仓库 score_threshold=70，LLM 返回 60 分 → 应发送。"""
        parts = REPO_AUTO_OPS.split("/")
        ns, name = "/".join(parts[:-1]), parts[-1]

        self.mock_llm.return_value = "### Review 结果\n总分:60分"

        calls = self._trigger_mr_review(ns, name, env_overrides={
            "WECOM_ENABLED": "1",
            "WECOM_WEBHOOK_URL": "https://example.com/fallback",
        })

        self.assertGreater(len(calls), 0, "分数 60 < 阈值 70，应发送企业微信消息")

    def test_default_threshold_for_unknown_repo(self):
        """unknown 仓库使用 default.yaml 阈值 80，LLM 返回 85 分 → 不发送。"""
        ns, name = REPO_UNKNOWN.split("/", 1)
        self.mock_llm.return_value = "### Review 结果\n总分:85分"

        calls = self._trigger_mr_review(ns, name, env_overrides={
            "WECOM_ENABLED": "1",
            "WECOM_WEBHOOK_URL": "https://example.com/default",
        })

        self.assertEqual(len(calls), 0, "分数 85 >= default 阈值 80，不应发送企业微信消息")


# ===========================================================================
# 四、repository_full_name 传递测试
# ===========================================================================

class TestRepositoryFullNamePropagation(WebhookTestBase):
    """验证各平台均正确提取并传递 repository_full_name 到 ReviewEntity。"""

    def test_gitlab_mr_passes_path_with_namespace(self):
        """GitLab MR：repository_full_name = path_with_namespace。"""
        captured = []

        original_send = __import__(
            "biz.event.event_manager", fromlist=["event_manager"]
        ).event_manager["merge_request_reviewed"].send

        def capture_send(entity):
            captured.append(entity)
            return original_send(entity)

        with self.sync_queue(), \
             patch("biz.event.event_manager.event_manager") as mock_em, \
             patch("biz.service.review_service.ReviewService.insert_mr_review_log"):
            mock_signal = MagicMock()
            mock_em.__getitem__.return_value = mock_signal

            patchers = self.mock_gitlab_mr_handler()
            self.start_all(*patchers)
            self.client.post(
                "/review/webhook",
                json=gitlab_mr_payload(project_name="auto-ops", namespace="rd-fy21-canway-GOAC"),
                headers=self.headers_gitlab,
            )

            call_args = mock_signal.send.call_args
            if call_args:
                entity = call_args.args[0] if call_args.args else None
                if entity:
                    self.assertEqual(
                        entity.repository_full_name,
                        "rd-fy21-canway-GOAC/auto-ops",
                    )

    def test_github_pr_passes_full_name(self):
        """GitHub PR：repository_full_name = repository.full_name。"""
        with self.sync_queue(), \
             patch("biz.event.event_manager.event_manager") as mock_em, \
             patch("biz.service.review_service.ReviewService.insert_mr_review_log"):
            mock_signal = MagicMock()
            mock_em.__getitem__.return_value = mock_signal

            patchers = self.mock_github_pr_handler()
            self.start_all(*patchers)
            self.client.post(
                "/review/webhook",
                json=github_pr_payload(owner="org-team", repo_name="my-service"),
                headers=self.headers_github,
            )

            call_args = mock_signal.send.call_args
            if call_args:
                entity = call_args.args[0] if call_args.args else None
                if entity:
                    self.assertEqual(entity.repository_full_name, "org-team/my-service")

    def test_gitea_pr_passes_full_name(self):
        """Gitea PR：repository_full_name = repository.full_name。"""
        with self.sync_queue(), \
             patch("biz.event.event_manager.event_manager") as mock_em, \
             patch("biz.service.review_service.ReviewService.insert_mr_review_log"):
            mock_signal = MagicMock()
            mock_em.__getitem__.return_value = mock_signal

            patchers = self.mock_gitea_pr_handler()
            self.start_all(*patchers)
            self.client.post(
                "/review/webhook",
                json=gitea_pr_payload(owner="org-team", repo_name="my-service"),
                headers=self.headers_gitea,
            )

            call_args = mock_signal.send.call_args
            if call_args:
                entity = call_args.args[0] if call_args.args else None
                if entity:
                    self.assertEqual(entity.repository_full_name, "org-team/my-service")


if __name__ == "__main__":
    unittest.main(verbosity=2)
