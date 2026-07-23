# Architecture and Boundaries

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `api.py` @ 8b45014118b17b228f5cdbd172454ace22f29a6f
- `biz/api/routes/webhook.py` @ 5e9ca0e46c8cd1b96b32fdf8872cbacd49d80a47
- `biz/utils/queue.py` @ d47a39025d55a19f393b4de55cc60f4a388e3c89
- `biz/queue/worker.py` @ 22aad16c59084f1da451679b1151bdb431a68663
- `biz/utils/code_reviewer.py` @ de9d1a1805306608fcea49379c2f56363cf150ad
- `biz/event/event_manager.py` @ 5107102161667cfe92080be5e2554b4e8be05690
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## Webhook-to-Review Flow

1. `api.py` 加载配置，创建 Flask app 并启动调度器。
2. `POST /review/webhook` 依据 Gitea/GitHub event header 或 GitLab payload 选择平台处理路径。
3. `biz.utils.queue.handle_queue()` 启动独立 `multiprocessing.Process`。
4. `biz/queue/worker.py` 获取 commits，应用 `ReviewRules.should_skip_review()`，获取并过滤 changes。
5. `CodeReviewer.review_and_strip_code()` 选择 prompt、限制 token 并调用 LLM client。
6. worker 把 review note 写回代码托管平台。
7. `event_manager` 发送 reviewed signal，触发 IM 通知与 SQLite 持久化。

## Key Boundaries

- **Platform boundary**：`biz/platforms/{gitlab,github,gitea}/` 封装外部 API。
- **LLM boundary**：`Factory` 根据 `LLM_PROVIDER` 构造 `BaseClient` 实现。
- **Policy boundary**：`ReviewRules` 负责仓库匹配、跳过规则、prompt 与 WeCom 策略。
- **Side-effect boundary**：平台 note、IM webhook 与 SQLite 写入都在 LLM 结果生成之后发生。
- **Process boundary**：webhook 请求与评审 worker 通过 OS process 分离，不是内存任务队列。

## Other Flows

- `ui.py` 直接读取 ReviewService 数据以展示 Dashboard，并实现独立的 cookie/HMAC 登录。
- `biz/cmd/review.py` 是交互式 CLI，不经过 webhook route。
- `biz/api/routes/daily_report.py` 与 scheduler 形成日报生成/通知路径。

## Change Guidance

修改 route、worker、ReviewRules、CodeReviewer、event signal 或数据表时，应同时检查平台适配器、通知、持久化以及相关测试；精确影响范围以当前源码与测试为准。
