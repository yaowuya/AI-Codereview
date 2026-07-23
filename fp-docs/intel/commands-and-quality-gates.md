# Commands and Quality Gates

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `CLAUDE.md` @ 4fe853d757db2ec1617f39f5d8788ee5712828e1
- `README.md` @ ef27472c800db4b9e2c252f2b5a3f15cfc71ab5f
- `.github/workflows/build_images.yml` @ d05b5197c5ad8b48cb41f5056a9f1baeed190728
- `biz/utils/test_review_rules.py` @ e66ef587b86fde3c47208302dcd1fc714eb4122d
- `tests/test_webhook_handle.py` @ 1750a0a1e56fe4ee5eeb2fac13503345ac3ed833
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## Project-Documented Commands

项目使用 `venv/`，不是 `.venv/`。

```bash
venv/Scripts/python.exe -m pytest biz -q --ignore=biz/platforms/gitea/test_webhook_handler.py
```

```bash
venv/Scripts/python.exe -m pytest biz/utils/test_review_rules.py -q
```

```bash
venv/Scripts/python.exe -m pytest biz/utils/test_review_rules.py -k "test_wecom_threshold_precedence" -q
```

```bash
venv/Scripts/python.exe api.py
```

```bash
venv/Scripts/streamlit.exe run ui.py --server.port 5002
```

```bash
venv/Scripts/python.exe biz/cmd/review.py
```

## Known Constraints

- `biz/platforms/gitea/test_webhook_handler.py` 有已知 import 问题，项目文档要求全量测试时排除。
- `biz/platforms/gitlab/test_webhook_handler.py::TestPushHandler::test_get_parent_commit_id` 记录为已知预存失败。
- GitHub Actions 当前发现的是 tag push 驱动的多架构 Docker 镜像构建与推送，不等同于测试质量门。

## Validation Status

本轮 discovery 未运行上述任何命令。后续完成声明必须重新运行与变更范围匹配的命令并保留输出。

## Unknowns

- 项目级 lint、format、type-check 命令：Unknown。
- CI 中是否有仓库外部测试门：Unknown。
