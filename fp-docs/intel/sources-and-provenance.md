# Sources and Provenance

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `CLAUDE.md` @ 4fe853d757db2ec1617f39f5d8788ee5712828e1
- `README.md` @ ef27472c800db4b9e2c252f2b5a3f15cfc71ab5f
- `requirements.txt` @ efe97f3537ad0610a0923733f8293e827e92c07c
- `Dockerfile` @ 482e1e9b481b0de09fc9c8bfe5db9fab2d2e448c
- `docker-compose.yml` @ dd977e7026827b5962458614dde26ca06595012d
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## Scope

本文件来自一次有界、只读的轻量 discovery。它记录来源与覆盖边界，不证明运行时行为。

| Source | Used For | Confidence |
| --- | --- | --- |
| `CLAUDE.md` | 项目命令、入口、架构概览、已知测试约束 | high |
| `README.md` | 项目目的、本地与 Docker 使用方式 | medium；部分说明可能落后于当前代码 |
| `requirements.txt` | Python 依赖信号 | high |
| `Dockerfile`, `docker-compose.yml`, `conf/supervisord.conf` | 容器、进程、挂载与端口 | high |
| `api.py`, `ui.py`, `biz/cmd/review.py` | 三个运行入口 | high |
| `biz/api/routes/*`, `biz/queue/worker.py` | Webhook、日报与评审编排 | high |
| `biz/llm/*`, `biz/utils/code_reviewer.py` | LLM 抽象、提示词与审查契约 | high |
| `biz/service/review_service.py` | SQLite 表与迁移逻辑 | high |
| `biz/utils/review_rules.py`, `biz/utils/test_review_rules.py` | 仓库规则与代表性测试 | high |

## Discovery Boundaries

- 未读取 `conf/.env`、密钥值、生产数据或 `data/data.db` 内容。
- 未运行测试、构建、lint、服务启动或依赖安装。
- 未穷举所有平台 handler、配置文件或测试文件。
- CodeGraph 仅用于写入前候选定位；所有记录均应在使用时回到当前源码复核。
