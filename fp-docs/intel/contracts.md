# Contracts

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `biz/api/routes/webhook.py` @ 5e9ca0e46c8cd1b96b32fdf8872cbacd49d80a47
- `biz/api/routes/daily_report.py` @ f9bfca68bce1b8df78683f923321ed13a1fed0ac
- `biz/llm/client/base.py` @ 69ea8691013f3ad44c394046f6993737ce0847d4
- `biz/utils/code_reviewer.py` @ de9d1a1805306608fcea49379c2f56363cf150ad
- `biz/utils/review_rules.py` @ 8745906c5389a2c69009dba9127d74cfd1a74cf4
- `biz/service/review_service.py` @ 887d6fca8bf066b89d77c45b8d9af792329ab2ea
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## HTTP Contracts

- `GET /` 返回服务状态 HTML。
- `POST /review/webhook` 要求 JSON；无效格式或不支持事件返回 400。
- GitHub/Gitea 支持 `pull_request` 与 `push`；GitLab 支持 `merge_request` 与 `push`。
- `GET /review/daily_report` 无数据时返回 200 与 `No data to process.`，异常时返回 500。

精确响应 JSON、header 和 payload 字段必须以当前 route 文件为准。

## LLM Contract

- `BaseClient.completions(messages, model=...) -> str` 是 provider 统一接口。
- 默认 provider 由 `LLM_PROVIDER` 决定，代码默认值为 `anthropic`。
- Prompt 优先级：仓库/default `ReviewRules` 中的 `code_review_prompt`，然后 `conf/prompt_templates.yml`。
- 评分解析匹配 `总分:XX分` 或中文冒号变体；无法匹配时返回 0。

## Review Rules Contract

- `REVIEW_RULES_CONFIG_DIR` 目录模式优先于 legacy `REVIEW_RULES_CONFIG_PATH` 单文件模式。
- `default.yaml`/`default.yml` 提供全局默认；其他规则文件必须声明 `repository:`。
- 仓库候选按 `repository_full_name`、`project_name`、bare repository name 归一化后匹配。
- WeCom score threshold 优先级：repo → default → `WECOM_SCORE_THRESHOLD`。
- `review_skip_regex` 匹配 MR/PR title 与 commit messages；无效 regex 不应中断全部评审。

## Data Contract

- SQLite 路径：`data/data.db`。
- 表：`mr_review_log`、`push_review_log`。
- `init_db()` 兼容旧表，为缺失列/索引执行启动期迁移。

## Unknowns

- 外部平台 API 的完整重试、超时、分页与错误 envelope：Unknown。
- 生产 LLM provider 的结构化错误语义：Unknown。
