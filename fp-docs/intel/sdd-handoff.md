# SDD Handoff

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `CLAUDE.md` @ 4fe853d757db2ec1617f39f5d8788ee5712828e1
- `fp-docs/manifest.md` @ unavailable
- `fp-docs/settings/agent.md` @ unavailable
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: regenerate
Use as: navigation-hint-only

## Mandatory Context Files

- `fp-docs/manifest.md`
- 与当前任务领域相关的最小 settings/intel 文件；禁止批量读取全部信息层。

## Global Constraints Sources

- 项目级 `CLAUDE.md`
- `fp-docs/settings/agent.md`
- 当前用户指令与已批准的 active change artifacts

## Allowed Edit Scope Rules

- 以 active change 的任务文件为准。
- 修改前重新打开目标源码；generated intel 仅用于导航。
- 不读取或复制 `conf/.env`、凭据、生产数据。

## Validation Evidence Requirements

- 使用 `CLAUDE.md` 中与变更范围匹配的 `venv/Scripts/...` 命令。
- 完成声明必须包含本轮实际命令输出；不能引用 discovery 代替验证。
- 已知预存失败必须与新回归区分。

## Commit Policy

- Exact branch/commit policy: Unknown。

## Review Severity Policy

- Exact project-specific severity policy: Unknown。

## Visual Evidence Requirements

- Streamlit UI 变更的浏览器/截图验收规则：Unknown。
- Canway/CW frontend/prototype settings 是可编辑草稿；只有当前项目源码或明确设计输入确认后才能应用其具体组件/token。

## Backend Evidence Requirements

- API/worker/service 变更至少运行相关单测；跨平台或共享流程变更应考虑项目文档中的全量 `biz` 测试命令。
- Webhook contract 变更应覆盖有效事件、无效 JSON、缺 token 与不支持事件等负向路径。

## Security/Data Constraints

- 不把 token、API key、webhook URL 或环境变量值写入 FeaturePilot artifacts。
- 认证、日志 payload、TLS 校验、外部 webhook 与 SQLite schema 变更需要专项负向验证。

## Common Project Pitfalls

- 虚拟环境目录是 `venv/`，不是 `.venv/`。
- `biz/platforms/gitea/test_webhook_handler.py` 有项目记录的已知 import 问题。
- GitLab `PushHandler.get_parent_commit_id` 有项目记录的未实现测试失败。
- Webhook worker 使用 OS process，不是持久化消息队列。

## Stale Intel Handling

- 修改前重新打开源码文件。
- 完成声明前重新运行命令。
- 依赖路径缺失或 fingerprint 变化时，把相关 intel 视为 stale。
- Working tree dirty 时仅把 intel 当作 soft-stale navigation hint。
