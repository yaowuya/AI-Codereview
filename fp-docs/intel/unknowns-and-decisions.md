# Unknowns and Decisions

## Unknowns

| Area | Unknown | Impact | Resolve By | Blocking For |
| --- | --- | --- | --- | --- |
| Validation | 项目级 lint、format、type-check 命令 | 无法定义完整静态质量门 | 项目文档或 CI 配置确认 | 相关完成声明 |
| Security | 生产 TLS、反向代理、网络 ACL 与 Dashboard 暴露范围 | 无法判断现有 transport/access 风险 | 部署配置与运维负责人确认 | 安全/部署变更 |
| Security | 日志脱敏、保留和访问控制策略 | Webhook payload 可能包含敏感元数据 | 日志规范与生产样例字段确认（不得复制值） | 日志/合规变更 |
| Data | SQLite 备份、恢复、并发写入与容量策略 | 无法规划持久化可靠性变更 | 运维与数据保留要求确认 | 数据层演进 |
| Operations | 外部 API/webhook 的统一超时、重试和失败告警策略 | 无法定义可靠性验收 | 当前平台 client 与运维策略确认 | 集成可靠性变更 |
| Workflow | Exact branch, commit, release, and review severity policy | SDD 提交/审查策略不完整 | 项目维护者确认 | 发布或归档 |
| UI | Streamlit Dashboard 的浏览器、响应式和视觉回归要求 | UI 变更验收证据不完整 | 当前产品/设计要求确认 | UI 变更 |

## Decisions

| Date | Decision | Source | Applies To |
| --- | --- | --- | --- |
| 2026-07-23 | 启用项目级 CodeGraph；图结果仅作 navigation hint | `/fp-init` 用户确认 | 代码定位与影响范围候选 |
| 2026-07-23 | 采用全部 Canway/CW settings 作为可编辑草稿 | `/fp-init` 用户确认 | `fp-docs/settings/*` |
| 2026-07-23 | 生成轻量只读 discovery intel | `/fp-init` 用户确认 | `fp-docs/intel/*` |
