# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The project uses `venv/` (not `.venv/`) as the virtual environment.

```bash
# Run all tests (exclude the broken Gitea test file)
venv/Scripts/python.exe -m pytest biz -q --ignore=biz/platforms/gitea/test_webhook_handler.py

# Run a single test file
venv/Scripts/python.exe -m pytest biz/utils/test_review_rules.py -q

# Run a single test by name
venv/Scripts/python.exe -m pytest biz/utils/test_review_rules.py -k "test_wecom_threshold_precedence" -q

# Start the Flask webhook server (port 5001)
venv/Scripts/python.exe api.py

# Start the Streamlit dashboard (port 5002)
venv/Scripts/streamlit.exe run ui.py --server.port 5002

# Run the CLI review tool (interactive)
venv/Scripts/python.exe biz/cmd/review.py

# Install dependencies
venv/Scripts/pip.exe install -r requirements.txt
```

**Known pre-existing test failures (unrelated to this codebase's logic):**
- `biz/platforms/gitea/test_webhook_handler.py` — broken import (`biz.gitea` should be `biz.platforms.gitea`); exclude with `--ignore`
- `biz/platforms/gitlab/test_webhook_handler.py::TestPushHandler::test_get_parent_commit_id` — `get_parent_commit_id` method not implemented on `PushHandler`

## Architecture

### Entry Points

There are three entry points:
- **`api.py`** — Flask webhook server (port 5001). Receives webhooks from GitLab/GitHub/Gitea.
- **`ui.py`** — Streamlit dashboard (port 5002). Displays review history from SQLite.
- **`biz/cmd/review.py`** — CLI tool for one-off reviews (directory structure, branch naming, complexity, MySQL schema).

In Docker, `supervisord` runs both `api.py` and `ui.py` together.

### Webhook-to-Review Flow

```
POST /review/webhook
  └── biz/api/routes/webhook.py       # platform detection (GitHub by X-GitHub-Event header,
                                      # Gitea by X-Gitea-Event, otherwise GitLab)
       └── handle_queue()             # spawns a new OS Process (multiprocessing)
            └── biz/queue/worker.py   # per-platform handle_* functions
                 1. get commits
                 2. ReviewRules.should_skip_review()  ← early exit if regex matches
                 3. get diff changes, filter by SUPPORTED_EXTENSIONS
                 4. CodeReviewer.review_and_strip_code()  ← calls LLM
                 5. post review note back to platform
                 6. event_manager["*_reviewed"].send(entity)
                      └── biz/event/event_manager.py
                           ├── send IM notifications (notifier.send_notification)
                           └── log to SQLite (ReviewService)
```

Each platform handler (`biz/platforms/{gitlab,github,gitea}/webhook_handler.py`) implements `get_push_commits()`, `get_merge_request_commits()`, `get_*_changes()`, and `add_*_notes()` against the respective platform API.

### LLM Abstraction

`biz/llm/factory.py` selects a client by the `LLM_PROVIDER` env var. All clients extend `biz/llm/client/base.py:BaseClient` and implement `completions(messages)`. The prompt template (system + user) is loaded from `conf/prompt_templates.yml` using Jinja2 (style injected via `REVIEW_STYLE`). Score parsing extracts `总分:XX分` from the LLM response.

### IM Notification Fan-out

`biz/utils/im/notifier.py:send_notification()` fans out to four channels simultaneously: DingTalk, WeCom, Feishu, ExtraWebhook. Each notifier reads its own `*_ENABLED` env var.

**WeCom-specific routing**: `WeComNotifier` consults `ReviewRules` first for a per-repository webhook URL and score threshold before falling back to env vars. The `url_slug` mechanism (non-alphanumeric chars replaced with `_`) allows per-server webhook overrides via env vars like `WECOM_WEBHOOK_URL_GITLAB_COMPANY_COM`.

### Repository-Level Rules (`ReviewRules`)

`biz/utils/review_rules.py` supports two loading modes (directory mode takes priority):

**Directory mode** (`REVIEW_RULES_CONFIG_DIR`, default `conf/review_rule/`):
- `default.yaml` — global defaults (no `repository:` field)
- Other `.yaml`/`.yml` files — one per repo; must contain `repository: "namespace/project"` to declare ownership; filename is free-form

**Single-file mode** (legacy, `REVIEW_RULES_CONFIG_PATH`): original `conf/review_rules.yml` with `defaults:` + `repositories:` sections; used only when the directory doesn't exist.

Public API:
- **`get_wecom_webhook_url()`** — per-repo WeCom robot URL
- **`get_wecom_score_threshold()`** — precedence: repo rule → default.yaml → `WECOM_SCORE_THRESHOLD` env var
- **`should_skip_review()`** — matches MR/PR title + commit messages against `review_skip_regex`; returns `SkipReviewResult`

Repository keys are matched case-insensitively via `repository:` field against `full_name`, then `project_name`, then bare project name.

### Data Layer

SQLite at `data/data.db`, managed by `biz/service/review_service.py`. Tables: `mr_review_log` and `push_review_log`. Schema migrations (adding columns to old tables) run at startup via `init_db()`.

### Configuration

Copy `conf/.env.dist` to `conf/.env` before running. `conf/.env` is gitignored. `conf/prompt_templates.yml` holds all LLM prompts. Per-repo review rules live in `conf/review_rule/` (directory mode); the legacy `conf/review_rules.yml` (single-file mode) is kept for backward compatibility.
