# Workspace Map

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `CLAUDE.md` @ 4fe853d757db2ec1617f39f5d8788ee5712828e1
- `api.py` @ 8b45014118b17b228f5cdbd172454ace22f29a6f
- `ui.py` @ 14692a3614d15c294ba2f0ee11ad860ceb9d06c3
- `biz/cmd/review.py` @ 342b005b3e3a33b6fc4a05a8b5334e99ec9113a9
- `biz/api/routes/__init__.py` @ 935502ef77ff3c04ea1cae7bdebef9215c420736
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## Entry Points

| Path | Role |
| --- | --- |
| `api.py` | Flask webhook/API 服务入口，默认端口 5001 |
| `ui.py` | Streamlit 审查历史 Dashboard，端口 5002 |
| `biz/cmd/review.py` | 交互式一次性审查 CLI |

## Main Boundaries

| Path | Responsibility |
| --- | --- |
| `biz/api/` | Flask app、Blueprint、调度器 |
| `biz/platforms/` | GitLab、GitHub、Gitea API 适配器 |
| `biz/queue/` | 平台事件到代码评审的 worker 编排 |
| `biz/llm/` | LLM client 抽象与 provider factory |
| `biz/utils/code_reviewer.py` | Prompt 选择、token 截断、LLM 调用、评分解析 |
| `biz/utils/review_rules.py` | 仓库级规则加载与匹配 |
| `biz/event/` | 评审完成信号与副作用连接 |
| `biz/utils/im/` | 即时消息通知适配器 |
| `biz/service/` | SQLite 数据持久化与查询 |
| `conf/` | 非秘密模板、规则、supervisor 配置；实际 `.env` 不应进入 intel |
| `tests/`, `biz/**/test_*.py` | 集成与单元测试 |
| `data/`, `log/` | 运行期持久化数据和日志 |

## Route Map

`biz/api/routes/__init__.py` 注册 `home`、`daily_report`、`webhook` 三个 Blueprint。精确路由、状态码与 payload 需读取当前 route 文件。
