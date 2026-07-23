# Tech Stack

Generated: 2026-07-23T11:03:46+08:00
Refreshed: never
Generated from Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty
Depends on:
- `requirements.txt` @ efe97f3537ad0610a0923733f8293e827e92c07c
- `Dockerfile` @ 482e1e9b481b0de09fc9c8bfe5db9fab2d2e448c
- `conf/supervisord.conf` @ c3d54fb001adadb48008f8816a97595daf260f9e
- `biz/llm/factory.py` @ 0ac117856be0eb963c2cfaa26bfd83f1fd0c26eb
- `biz/service/review_service.py` @ 887d6fca8bf066b89d77c45b8d9af792329ab2ea
Generated body hash: unavailable
Freshness: soft-stale
Refresh decision: keep
Use as: navigation-hint-only

## Runtime

- Python 应用；容器基础镜像为 `python:3.10-slim`。
- Flask 提供 webhook/API 服务。
- Streamlit 提供审查历史 Dashboard。
- APScheduler 提供日报调度。
- Supervisor 在 Docker 中同时运行 API 与 Dashboard。

## Data and Integration

- SQLite 文件由 `biz/service/review_service.py` 管理。
- pandas 用于结果查询与 Dashboard/日报数据处理。
- Blinker 用于评审完成事件。
- requests 用于外部代码托管平台与 webhook 调用。

## LLM Layer

- `biz/llm/factory.py` 当前支持 Anthropic、ZhipuAI、OpenAI、DeepSeek、Qwen、Ollama client。
- `BaseClient.completions()` 是统一文本完成契约。
- Prompt 模板使用 PyYAML 与 Jinja2 加载/渲染。

## Unknowns

- 生产环境实际 Python patch 版本：Unknown。
- 当前锁定的传递依赖版本：Unknown；根目录未发现 Python lockfile。
- 静态类型检查与正式 lint 工具链：Unknown。
