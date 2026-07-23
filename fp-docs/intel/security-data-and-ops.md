# Security, Data, and Operations

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `api.py` @ 8b45014118b17b228f5cdbd172454ace22f29a6f
- `ui.py` @ 14692a3614d15c294ba2f0ee11ad860ceb9d06c3
- `docker-compose.yml` @ dd977e7026827b5962458614dde26ca06595012d
- `biz/api/routes/webhook.py` @ 5e9ca0e46c8cd1b96b32fdf8872cbacd49d80a47
- `biz/platforms/gitlab/webhook_handler.py` @ fa584a22ef87d637259eecdb02ceb3490c580b7e
- `biz/service/review_service.py` @ 887d6fca8bf066b89d77c45b8d9af792329ab2ea
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## Secrets and Configuration

- API 与 Dashboard 从 `conf/.env` 加载运行配置；Docker Compose 也声明该 env file。
- 本信息层不得复制 `.env`、access token、LLM API key 或 webhook URL 值。
- Webhook token 当前来自环境变量或平台特定请求头；精确 header 名需以 route 源码为准。

## Authentication and Transport Signals

- Dashboard 使用 HMAC-SHA256 签名 token/cookie，默认有效期 30 天。
- 当前源码在环境变量缺失时为 Dashboard 用户名、密码和 secret key 提供默认值；部署前必须确认覆盖策略。
- 代表性 GitLab handler 的外部 HTTP 请求使用 `verify=False`；涉及传输安全的改动应专项复核所有平台适配器。
- Webhook route 当前会记录收到的 payload；需结合实际 payload 字段确认日志脱敏与保留策略。

以上是当前源码信号，不是已完成的安全审计结论。

## Data and Side Effects

- 评审结果、提交/项目/作者/分支等元数据写入本地 SQLite。
- 通知并发 fan-out 到 DingTalk、WeCom、Feishu、ExtraWebhook；各通道由配置启用。
- worker 会把 LLM 评审结果写回 GitLab/GitHub/Gitea note。
- Docker Compose 挂载 `data`、`log` 与 `conf/review_rule` 以支持持久化/按仓库配置。

## Operations

- 容器暴露 5001（API）与 5002（Dashboard），由 Supervisor 管理两个进程。
- GitHub Actions 在 tag push 时构建并推送多架构 GHCR 镜像。
- 数据库 schema 兼容迁移在应用启动期执行。

## Critical Unknowns

- 生产 TLS、反向代理、网络 ACL 与 Dashboard 对外暴露范围：Unknown。
- 日志脱敏、保留与访问控制策略：Unknown。
- SQLite 备份、恢复、并发写入与容量策略：Unknown。
- 外部 webhook 重试、超时与失败告警策略：Unknown。
