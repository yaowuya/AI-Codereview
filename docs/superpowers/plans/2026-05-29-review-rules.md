# Review Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build repository-level review rules so each repository can route low-score WeCom alerts to its own robot, use its own score threshold, and skip AI Review by regex against MR/PR titles and commit messages.

**Architecture:** Add a focused rule loader in `biz/utils/review_rules.py` that reads `conf/review_rules.yml`, normalizes repository identity, resolves repository-level WeCom settings, and evaluates skip regexes. `biz/queue/worker.py` extracts repository identity and checks skip rules before expensive diff/LLM work. `biz/utils/im/wecom.py` uses the rule loader before existing environment-variable fallbacks.

**Tech Stack:** Python 3.10+, Flask webhook workers, PyYAML, pytest/unittest, existing notifier and platform handler modules.

---

## File Structure

- Create `biz/utils/review_rules.py`: loads YAML rules, matches repository keys, resolves WeCom webhook URLs and thresholds, evaluates skip regexes.
- Create `conf/review_rules.yml`: sample/default empty rules file that is safe to ship.
- Modify `requirements.txt`: add `PyYAML==6.0.2`.
- Modify `biz/utils/im/notifier.py`: accept and forward `repository_full_name` to WeCom and extra webhook metadata.
- Modify `biz/utils/im/wecom.py`: resolve webhook URL and threshold through `ReviewRules`.
- Modify `biz/event/event_manager.py`: pass entity repository identity into notifications.
- Modify `biz/entity/review_entity.py`: store optional `repository_full_name` on review entities.
- Modify `biz/queue/worker.py`: extract repository identity/title, run skip checks, pass repository identity into entities.
- Modify `biz/utils/config_checker.py`: validate optional `REVIEW_RULES_CONFIG_PATH` without breaking startup.
- Modify `conf/.env.dist`: document `REVIEW_RULES_CONFIG_PATH`.
- Modify `README.md` and `doc/faq.md`: document YAML examples and precedence.
- Add tests under `biz/utils/test_review_rules.py` and `biz/utils/im/test_wecom.py`.

## Task 1: Add Rule Loader Tests

**Files:**
- Create: `biz/utils/test_review_rules.py`
- Create later: `biz/utils/review_rules.py`

- [ ] **Step 1: Write failing tests for repository matching, thresholds, webhook routing, and skip regex**

Create `biz/utils/test_review_rules.py` with:

```python
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
        self.assertEqual(default_match.pattern, "\\\\[skip review\\\\]")

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
        self.assertEqual(result.pattern, "\\\\[skip review\\\\]")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail because the module does not exist**

Run: `.venv\Scripts\python.exe -m pytest biz/utils/test_review_rules.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'biz.utils.review_rules'`.

## Task 2: Implement `ReviewRules`

**Files:**
- Create: `biz/utils/review_rules.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add PyYAML dependency**

Add this line to `requirements.txt`:

```text
PyYAML==6.0.2
```

- [ ] **Step 2: Implement the rule loader**

Create `biz/utils/review_rules.py` with:

```python
import os
import re
from dataclasses import dataclass
from typing import Optional

import yaml

from biz.utils.log import logger


DEFAULT_REVIEW_RULES_CONFIG_PATH = "conf/review_rules.yml"


@dataclass
class SkipReviewResult:
    should_skip: bool
    pattern: Optional[str] = None
    matched_text: Optional[str] = None


class ReviewRules:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv("REVIEW_RULES_CONFIG_PATH", DEFAULT_REVIEW_RULES_CONFIG_PATH)
        self._config = None

    @staticmethod
    def normalize_repository_key(value: Optional[str]) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def repository_name_from_full_name(repository_full_name: Optional[str]) -> str:
        normalized = (repository_full_name or "").strip()
        if "/" not in normalized:
            return normalized
        return normalized.rsplit("/", 1)[-1]

    def load_config(self) -> dict:
        if self._config is not None:
            return self._config

        if not self.config_path or not os.path.exists(self.config_path):
            logger.info(f"Review rules config not found: {self.config_path}")
            self._config = {}
            return self._config

        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except Exception as exc:
            logger.error(f"Failed to load review rules config {self.config_path}: {exc}")
            self._config = {}
            return self._config

        if not isinstance(data, dict):
            logger.error(f"Review rules config {self.config_path} must be a mapping.")
            self._config = {}
            return self._config

        self._config = data
        return self._config

    def get_repository_rule(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> dict:
        config = self.load_config()
        repositories = config.get("repositories") or {}
        if not isinstance(repositories, dict):
            logger.error("review_rules.yml repositories must be a mapping.")
            return {}

        normalized_repositories = {
            self.normalize_repository_key(key): value
            for key, value in repositories.items()
            if isinstance(value, dict)
        }
        candidates = [
            repository_full_name,
            project_name,
            self.repository_name_from_full_name(repository_full_name),
        ]

        for candidate in candidates:
            key = self.normalize_repository_key(candidate)
            if key and key in normalized_repositories:
                return normalized_repositories[key]
        return {}

    def get_default_rule(self) -> dict:
        defaults = self.load_config().get("defaults") or {}
        if not isinstance(defaults, dict):
            logger.error("review_rules.yml defaults must be a mapping.")
            return {}
        return defaults

    @staticmethod
    def _parse_non_negative_int(value, source: str) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            threshold = int(value)
        except (TypeError, ValueError):
            logger.error(f"{source} must be a non-negative integer.")
            return None
        if threshold < 0:
            logger.error(f"{source} must be a non-negative integer.")
            return None
        return threshold

    def get_wecom_webhook_url(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> Optional[str]:
        repository_rule = self.get_repository_rule(repository_full_name, project_name)
        webhook_url = repository_rule.get("wecom_webhook_url")
        if webhook_url:
            return str(webhook_url).strip()
        return None

    def get_wecom_score_threshold(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> Optional[int]:
        repository_rule = self.get_repository_rule(repository_full_name, project_name)
        repository_threshold = self._parse_non_negative_int(
            repository_rule.get("wecom_score_threshold"),
            "repositories.<repo>.wecom_score_threshold",
        )
        if repository_threshold is not None:
            return repository_threshold

        default_rule = self.get_default_rule()
        default_threshold = self._parse_non_negative_int(
            default_rule.get("wecom_score_threshold"),
            "defaults.wecom_score_threshold",
        )
        if default_threshold is not None:
            return default_threshold

        return self._parse_non_negative_int(os.getenv("WECOM_SCORE_THRESHOLD"), "WECOM_SCORE_THRESHOLD")

    @staticmethod
    def _commit_messages(commits: Optional[list]) -> list:
        messages = []
        for commit in commits or []:
            if not isinstance(commit, dict):
                continue
            message = commit.get("message")
            if message:
                messages.append(str(message))
        return messages

    def get_review_skip_regex(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> list:
        repository_rule = self.get_repository_rule(repository_full_name, project_name)
        if "review_skip_regex" in repository_rule:
            patterns = repository_rule.get("review_skip_regex") or []
        else:
            patterns = self.get_default_rule().get("review_skip_regex") or []
        if isinstance(patterns, str):
            return [patterns]
        if not isinstance(patterns, list):
            logger.error("review_skip_regex must be a string or list of strings.")
            return []
        return [str(pattern) for pattern in patterns if pattern]

    def should_skip_review(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
        title: Optional[str] = None,
        commits: Optional[list] = None,
    ) -> SkipReviewResult:
        text_parts = []
        if title:
            text_parts.append(str(title))
        text_parts.extend(self._commit_messages(commits))
        target_text = "\n".join(text_parts)

        if not target_text:
            return SkipReviewResult(False)

        for pattern in self.get_review_skip_regex(repository_full_name, project_name):
            try:
                if re.search(pattern, target_text, flags=re.IGNORECASE | re.MULTILINE):
                    return SkipReviewResult(True, pattern=pattern, matched_text=target_text)
            except re.error as exc:
                logger.error(f"Invalid review skip regex '{pattern}': {exc}")
        return SkipReviewResult(False)
```

- [ ] **Step 3: Run rule tests**

Run: `.venv\Scripts\python.exe -m pytest biz/utils/test_review_rules.py -q`

Expected: PASS.

- [ ] **Step 4: Commit rule loader**

Run:

```bash
git add requirements.txt biz/utils/review_rules.py biz/utils/test_review_rules.py
git commit -m "feat: add repository review rules loader"
```

## Task 3: Wire WeCom Routing and Thresholds

**Files:**
- Modify: `biz/utils/im/wecom.py`
- Modify: `biz/utils/im/notifier.py`
- Create: `biz/utils/im/test_wecom.py`

- [ ] **Step 1: Write failing WeCom tests**

Create `biz/utils/im/test_wecom.py` with:

```python
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
```

- [ ] **Step 2: Run WeCom tests to verify signature failure**

Run: `.venv\Scripts\python.exe -m pytest biz/utils/im/test_wecom.py -q`

Expected: FAIL because `_get_webhook_url` and `_should_send_by_score` do not accept `repository_full_name`.

- [ ] **Step 3: Update `notifier.send_notification` signature**

Modify `biz/utils/im/notifier.py`:

```python
def send_notification(content, msg_type='text', title="通知", is_at_all=False, project_name=None, url_slug=None,
                      webhook_data: dict={}, score=None, repository_full_name=None):
```

Forward the new argument to WeCom:

```python
    wecom_notifier.send_message(content=content, msg_type=msg_type, title=title, is_at_all=is_at_all,
                                project_name=project_name, url_slug=url_slug, score=score,
                                repository_full_name=repository_full_name)
```

Include it in `system_data`:

```python
        "repository_full_name": repository_full_name
```

- [ ] **Step 4: Update WeCom notifier**

Modify `biz/utils/im/wecom.py`:

```python
from biz.utils.review_rules import ReviewRules
```

Change `_get_score_threshold` to accept repository context:

```python
    @staticmethod
    def _get_score_threshold(project_name=None, repository_full_name=None):
        threshold = ReviewRules().get_wecom_score_threshold(repository_full_name=repository_full_name,
                                                            project_name=project_name)
        return threshold
```

Change `_should_send_by_score`:

```python
    def _should_send_by_score(self, score=None, project_name=None, repository_full_name=None):
        threshold = self._get_score_threshold(project_name=project_name, repository_full_name=repository_full_name)
        logger.info(f"评分阈值：{threshold}，当前评分：{score}，对比结果：{score < threshold if threshold is not None and score is not None else '未启用'}")
        if threshold is None or score is None:
            return True

        if score < threshold:
            return True

        logger.info(f"Review 分数 {score} 未低于企微阈值 {threshold}，跳过企业微信推送。")
        return False
```

Change `_get_webhook_url` signature and add repository rule first:

```python
    def _get_webhook_url(self, project_name=None, url_slug=None, repository_full_name=None):
        rules_webhook_url = ReviewRules().get_wecom_webhook_url(repository_full_name=repository_full_name,
                                                                project_name=project_name)
        if rules_webhook_url:
            return rules_webhook_url
```

Change `send_message` signature:

```python
    def send_message(self, content, msg_type='text', title=None, is_at_all=False, project_name=None,
                     url_slug=None, score=None, repository_full_name=None):
```

Call updated helpers:

```python
            if not self._should_send_by_score(score, project_name=project_name, repository_full_name=repository_full_name):
                return

            post_url = self._get_webhook_url(project_name=project_name, url_slug=url_slug,
                                             repository_full_name=repository_full_name)
```

- [ ] **Step 5: Run notifier tests**

Run: `.venv\Scripts\python.exe -m pytest biz/utils/test_review_rules.py biz/utils/im/test_wecom.py -q`

Expected: PASS.

- [ ] **Step 6: Commit WeCom integration**

Run:

```bash
git add biz/utils/im/notifier.py biz/utils/im/wecom.py biz/utils/im/test_wecom.py
git commit -m "feat: route wecom notifications by repository rules"
```

## Task 4: Add Repository Identity to Entities and Events

**Files:**
- Modify: `biz/entity/review_entity.py`
- Modify: `biz/event/event_manager.py`

- [ ] **Step 1: Update entity constructors**

Modify `MergeRequestReviewEntity.__init__`:

```python
                 additions: int, deletions: int, last_commit_id: str, repository_full_name: str = None):
```

Add:

```python
        self.repository_full_name = repository_full_name
```

Modify `PushReviewEntity.__init__`:

```python
                 review_result: str, url_slug: str, webhook_data: dict, additions: int, deletions: int,
                 repository_full_name: str = None):
```

Add:

```python
        self.repository_full_name = repository_full_name
```

- [ ] **Step 2: Pass repository identity into event notifications**

In `biz/event/event_manager.py`, update both `send_notification` calls:

```python
                               webhook_data=mr_review_entity.webhook_data, score=mr_review_entity.score,
                               repository_full_name=mr_review_entity.repository_full_name)
```

and:

```python
                               webhook_data=entity.webhook_data, score=entity.score,
                               repository_full_name=entity.repository_full_name)
```

- [ ] **Step 3: Run existing tests**

Run: `.venv\Scripts\python.exe -m pytest biz -q`

Expected: PASS or only unrelated existing failures. If failures are from constructor call sites, update those call sites to pass the new optional argument or rely on the default.

- [ ] **Step 4: Commit entity/event wiring**

Run:

```bash
git add biz/entity/review_entity.py biz/event/event_manager.py
git commit -m "feat: carry repository identity through review events"
```

## Task 5: Skip Review in Workers

**Files:**
- Modify: `biz/queue/worker.py`

- [ ] **Step 1: Import `ReviewRules`**

Add near the other utility imports:

```python
from biz.utils.review_rules import ReviewRules
```

- [ ] **Step 2: Add helper functions near the top of `worker.py`**

```python
def _commit_messages(commits: list) -> str:
    return ';'.join((commit.get('message') or '').strip() for commit in commits or [])


def _should_skip_review(repository_full_name=None, project_name=None, title=None, commits=None) -> bool:
    result = ReviewRules().should_skip_review(
        repository_full_name=repository_full_name,
        project_name=project_name,
        title=title,
        commits=commits,
    )
    if result.should_skip:
        logger.info(
            f"Review skipped by regex pattern '{result.pattern}' for repository '{repository_full_name or project_name}'."
        )
        return True
    return False
```

- [ ] **Step 3: Wire GitLab push**

After `commits = handler.get_push_commits()` and before diff fetching:

```python
        project = webhook_data.get('project', {})
        project_name = project.get('name')
        repository_full_name = project.get('path_with_namespace') or project_name
        if _should_skip_review(repository_full_name=repository_full_name, project_name=project_name, commits=commits):
            return
```

Pass `repository_full_name=repository_full_name` into `PushReviewEntity`.

- [ ] **Step 4: Wire GitLab merge request**

After duplicate commit check and before `get_merge_request_changes()`:

```python
        project = webhook_data.get('project', {})
        project_name = project.get('name')
        repository_full_name = project.get('path_with_namespace') or project_name
        title = object_attributes.get('title')
        commits = handler.get_merge_request_commits()
        if not commits:
            logger.error('Failed to get commits')
            return
        if _should_skip_review(repository_full_name=repository_full_name, project_name=project_name,
                               title=title, commits=commits):
            return
```

Remove the later duplicate `commits = handler.get_merge_request_commits()` block, and keep using the earlier `commits`.

Pass `repository_full_name=repository_full_name` into `MergeRequestReviewEntity`.

- [ ] **Step 5: Wire GitHub push and PR**

For GitHub push, use:

```python
        repository = webhook_data.get('repository', {})
        project_name = repository.get('name')
        repository_full_name = repository.get('full_name') or project_name
        if _should_skip_review(repository_full_name=repository_full_name, project_name=project_name, commits=commits):
            return
```

For GitHub PR, after duplicate commit check and before changes:

```python
        repository = webhook_data.get('repository', {})
        project_name = repository.get('name')
        repository_full_name = repository.get('full_name') or project_name
        title = webhook_data.get('pull_request', {}).get('title')
        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error('Failed to get commits')
            return
        if _should_skip_review(repository_full_name=repository_full_name, project_name=project_name,
                               title=title, commits=commits):
            return
```

Remove the later duplicate PR commits fetch.

Pass `repository_full_name=repository_full_name` into both entity constructors.

- [ ] **Step 6: Wire Gitea push and PR**

For Gitea push, use:

```python
        repository = webhook_data.get('repository', {})
        project_name = repository.get('name')
        repository_full_name = repository.get('full_name') or project_name
        if _should_skip_review(repository_full_name=repository_full_name, project_name=project_name, commits=commits):
            return
```

For Gitea PR, after duplicate commit check and before changes:

```python
        repository = webhook_data.get('repository', {})
        project_name = repository.get('name')
        repository_full_name = repository.get('full_name') or project_name
        title = pull_request.get('title')
        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error('Failed to get commits for Gitea pull request')
            return
        if _should_skip_review(repository_full_name=repository_full_name, project_name=project_name,
                               title=title, commits=commits):
            return
```

Remove the later duplicate Gitea PR commits fetch.

Pass `repository_full_name=repository_full_name` into both entity constructors.

- [ ] **Step 7: Run worker-related tests**

Run: `.venv\Scripts\python.exe -m pytest biz/platforms biz/utils -q`

Expected: PASS.

- [ ] **Step 8: Commit worker integration**

Run:

```bash
git add biz/queue/worker.py
git commit -m "feat: skip reviews by repository rules"
```

## Task 6: Add Config Sample and Documentation

**Files:**
- Create: `conf/review_rules.yml`
- Modify: `conf/.env.dist`
- Modify: `README.md`
- Modify: `doc/faq.md`
- Modify: `biz/utils/config_checker.py`

- [ ] **Step 1: Add default rules file**

Create `conf/review_rules.yml`:

```yaml
# 仓库级 Review 规则配置。
# 默认不启用任何仓库级规则；需要时取消注释并按实际仓库修改。
defaults:
  # wecom_score_threshold: 80
  review_skip_regex: []

repositories:
  # my-group/my-repo:
  #   wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
  #   wecom_score_threshold: 70
  #   review_skip_regex:
  #     - "\\[skip review\\]"
  #     - "^WIP:"
```

- [ ] **Step 2: Add `.env.dist` setting**

Add near review settings:

```text
# 仓库级 Review 规则配置文件路径
REVIEW_RULES_CONFIG_PATH=conf/review_rules.yml
```

- [ ] **Step 3: Update config checker**

In `biz/utils/config_checker.py`, import `ReviewRules`:

```python
from biz.utils.review_rules import ReviewRules
```

Add:

```python
def check_review_rules_config():
    """检查仓库级 Review 规则配置。"""
    rules = ReviewRules()
    config = rules.load_config()
    if config:
        logger.info(f"Review 规则配置已加载：{rules.config_path}")
    else:
        logger.info("Review 规则配置为空或未配置，将使用现有环境变量行为。")
```

Call it in `check_config()` after `check_wecom_score_threshold()`:

```python
    check_review_rules_config()
```

- [ ] **Step 4: Update README**

In README 企业微信阈值 section, add:

```markdown
如果有多个仓库需要发往不同的企业微信机器人，或每个仓库需要不同的低分阈值，可以配置 `conf/review_rules.yml`：

```yaml
defaults:
  wecom_score_threshold: 80
  review_skip_regex:
    - "\\[skip review\\]"

repositories:
  my-group/my-repo:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
    wecom_score_threshold: 70
    review_skip_regex:
      - "^WIP:"
```

仓库规则优先级高于 `.env`。`review_skip_regex` 会匹配 MR/PR 标题和 commit message；Push 事件只匹配 commit message。命中后不会调用 AI Review，也不会写平台 note 或发送 Review 结果通知。
```

- [ ] **Step 5: Update FAQ**

In `doc/faq.md`, update “如何让不同项目的消息发送到不同的群？” to mention `conf/review_rules.yml` for WeCom:

```markdown
企业微信推荐使用 `conf/review_rules.yml` 做仓库级配置：

```yaml
repositories:
  project-a:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=project-a"
    wecom_score_threshold: 70
  group/project-b:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=project-b"
    wecom_score_threshold: 90
```

仓库 key 优先使用 GitHub/Gitea 的 `owner/repo` 或 GitLab 的 `namespace/project`。取不到完整名称时，也可以直接使用项目名。
```

Add a new FAQ item:

```markdown
### 如何跳过某些 MR/PR 或提交的 AI Review？

在 `conf/review_rules.yml` 配置 `review_skip_regex`：

```yaml
defaults:
  review_skip_regex:
    - "\\[skip review\\]"

repositories:
  my-group/my-repo:
    review_skip_regex:
      - "^WIP:"
      - "\\[no ai\\]"
```

MR/PR 事件会匹配标题和 commit message；Push 事件只匹配 commit message。仓库级 `review_skip_regex` 会替换默认规则。
```

- [ ] **Step 6: Run docs/config tests**

Run: `.venv\Scripts\python.exe -m pytest biz/utils/test_review_rules.py biz/utils/im/test_wecom.py -q`

Expected: PASS.

- [ ] **Step 7: Commit docs and config**

Run:

```bash
git add conf/review_rules.yml conf/.env.dist README.md doc/faq.md biz/utils/config_checker.py
git commit -m "docs: document repository review rules"
```

## Task 7: Final Verification

**Files:**
- All changed files

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv\Scripts\python.exe -m pytest biz/utils/test_review_rules.py biz/utils/im/test_wecom.py biz/platforms -q
```

Expected: PASS.

- [ ] **Step 2: Run broader test suite**

Run:

```bash
.venv\Scripts\python.exe -m pytest biz -q
```

Expected: PASS. If unrelated legacy tests fail, capture the failure names and confirm they are unrelated to review rules.

- [ ] **Step 3: Check working tree**

Run:

```bash
git status --short
```

Expected: no unstaged implementation changes except any user-owned files not touched by this plan.

- [ ] **Step 4: Final summary**

Summarize:

- Rule config file path and YAML keys.
- How repository-level WeCom webhook and threshold precedence works.
- How skip regex matching works.
- Test commands and results.

## Self-Review

- Spec coverage: The plan covers repository-specific WeCom robots, repository-specific thresholds, regex skip rules, `.env` fallback, GitLab/GitHub/Gitea worker integration, config validation, docs, and tests.
- Completion scan: No task uses incomplete wording as implementation instructions. The plan steps are concrete.
- Type consistency: `repository_full_name`, `project_name`, `wecom_webhook_url`, `wecom_score_threshold`, and `review_skip_regex` are used consistently across the rule loader, notifier, entities, and worker plan.
