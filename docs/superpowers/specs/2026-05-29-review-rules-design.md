# Review Rules Configuration Design

## Context

The current service reviews code from GitLab, GitHub, and Gitea webhook events, then sends review notifications through DingTalk, WeCom, Feishu, and an extra webhook. WeCom already supports a global low-score threshold and has partial environment-variable routing by project name or platform URL slug, but this does not scale well when many repositories need different WeCom robots or different alert thresholds.

Some repositories or changes should not trigger AI review at all. The skip decision should be configurable and based on regular expressions against MR/PR titles and commit messages.

## Goals

- Configure different WeCom robots for different repositories.
- Configure a different WeCom score threshold for each repository.
- Configure regular expressions that skip AI review for matching MR/PR titles and commit messages.
- Keep existing `.env` behavior working as a fallback.
- Apply the behavior consistently across GitLab, GitHub, and Gitea.

## Non-Goals

- Replacing all existing `.env` notification settings.
- Adding a UI for rule management.
- Changing how review scores are parsed from LLM output.
- Changing DingTalk, Feishu, or extra webhook behavior beyond preserving existing routing.

## Configuration

Add `conf/review_rules.yml`.

```yaml
defaults:
  wecom_score_threshold: 80
  review_skip_regex:
    - "\\[skip review\\]"
    - "^WIP:"

repositories:
  my-group/my-repo:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
    wecom_score_threshold: 70
    review_skip_regex:
      - "\\[no ai\\]"

  another-repo:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=yyy"
    wecom_score_threshold: 90
```

Repository keys use the most specific repository identity available:

- GitHub and Gitea: `repository.full_name`, falling back to `repository.name`.
- GitLab: `project.path_with_namespace`, falling back to `project.name`.

Matching is case-insensitive. If an exact repository key is not found, the loader also tries the repository name fallback.

## Rule Precedence

WeCom webhook URL resolution:

1. `repositories.<repo>.wecom_webhook_url`
2. Existing environment-variable routing, such as `WECOM_WEBHOOK_URL_<PROJECT_OR_URL_SLUG>`
3. Existing global `WECOM_WEBHOOK_URL`

WeCom score threshold resolution:

1. `repositories.<repo>.wecom_score_threshold`
2. `defaults.wecom_score_threshold`
3. Existing global `WECOM_SCORE_THRESHOLD`
4. No threshold filtering

Review skip regex resolution:

1. `repositories.<repo>.review_skip_regex`, if present
2. `defaults.review_skip_regex`
3. No skip patterns

Repository-level skip regex replaces defaults instead of merging. This lets a repository opt into a narrower or broader skip policy without inheriting global patterns accidentally.

## Review Skip Behavior

Before fetching large diffs or calling the LLM, each webhook handler builds a skip input:

- MR/PR events: title plus all commit messages.
- Push events: all commit messages.

If any configured regex matches the input, the handler logs the skip reason and returns before AI review. The service does not add platform notes and does not send review-result notifications for skipped reviews.

Invalid regex patterns are ignored with an error log so one bad pattern does not break webhook processing.

## Components

Add `biz/utils/review_rules.py`, with responsibilities:

- Load `conf/review_rules.yml` lazily.
- Normalize repository identity for matching.
- Resolve repository-specific WeCom webhook URLs.
- Resolve repository-specific WeCom score thresholds.
- Evaluate skip regex patterns against title and commit messages.

Update `biz/queue/worker.py`:

- Extract repository identity per platform.
- Run skip checks for MR/PR and push events before review.
- Pass repository identity into notifications so WeCom can resolve repository-specific rules.

Update `biz/utils/im/wecom.py`:

- Ask the rule module for repository-level webhook URL and threshold first.
- Preserve existing project/url slug/global environment fallbacks.

Update docs:

- Add `REVIEW_RULES_CONFIG_PATH` to `.env.dist`, defaulting to `conf/review_rules.yml`.
- Document the YAML format and examples in README and FAQ.

## Error Handling

- Missing `conf/review_rules.yml`: log at info level and use existing `.env` behavior.
- Malformed YAML: log an error and use existing `.env` behavior.
- Invalid threshold values: log an error and continue to fallback threshold.
- Invalid regex: log an error and ignore that pattern.
- Missing repository identity: use project name where available; otherwise only defaults apply.

## Testing

Add focused tests for:

- Repository matching by full name and name fallback.
- WeCom webhook precedence.
- Repository threshold overriding default and environment fallback.
- Regex skip for MR/PR title plus commit messages.
- Regex skip for push commit messages.
- Invalid regex and missing config fallback behavior.

## Acceptance Criteria

- A repository can send low-score WeCom alerts to its own robot.
- Two repositories can use different WeCom score thresholds in the same deployment.
- A configured regex such as `\\[skip review\\]` skips AI review when present in an MR/PR title or commit message.
- Existing installations using only `.env` continue to behave as before.
