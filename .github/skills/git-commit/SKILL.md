---
name: git-commit
description: "当被要求在 AI-Codereview-Gitlab 项目中提交代码、创建 commit、整理 staged changes、生成 commit message 时使用。会结合当前 Python/Flask/Streamlit、Webhook、多平台通知、LLM 配置仓库结构，检查变更范围、补齐必要验证、生成贴合仓库历史的 Conventional Commit message，并安全完成提交。"
argument-hint: "可选：提交范围、message 偏好、是否拆分多个 commits"
---

# Git Commit 技能

## 适用场景

- 用户要求 `commit`、`git commit`、提交代码、整理暂存区
- 需要根据当前仓库变更自动生成更贴合项目的 commit message
- 需要在提交前检查这个项目常见的联动文件是否遗漏

## 仓库特征

这是一个以 Python 为主的 AI Code Review 项目，核心结构包括：

- `api.py`、`biz/api/`：Flask API 与 Webhook 入口
- `ui.py`：Streamlit Dashboard
- `biz/platforms/`：GitLab、GitHub、Gitea 平台适配
- `biz/queue/worker.py`：异步处理主链路
- `biz/service/`、`biz/entity/`：业务逻辑与数据实体
- `biz/utils/im/`：钉钉、企微、飞书、自定义 Webhook 通知
- `biz/llm/`：多模型接入与工厂
- `conf/.env.dist`：环境变量样例配置

提交时要优先留意这些仓库内的联动关系，而不是套用其他项目的通用规则。

## 执行流程

### Step 1：收集仓库状态

优先收集这些信息：

- `git --no-pager status`
- `git --no-pager diff`
- `git --no-pager diff --cached`
- `git --no-pager log --oneline -10`

目标：

1. 确认这次提交只包含当前任务相关文件
2. 识别是否存在未暂存、已暂存、未跟踪文件混杂的情况
3. 从最近提交历史中提取当前仓库更常见的 message 风格

如果发现与当前任务无关的改动，尤其是出现在将要提交的同一文件中，先停下来提醒用户，不要擅自把无关内容一起提交。

### Step 2：按项目语义分析变更

分析变更时，优先按当前项目模块归类：

- 通知能力：`biz/utils/im/`、`biz/event/`
- 平台适配：`biz/platforms/`、`biz/api/routes/webhook.py`
- Review 主流程：`biz/queue/worker.py`、`biz/utils/code_reviewer.py`
- 配置能力：`conf/.env.dist`、`biz/utils/config_checker.py`
- 数据与统计：`biz/service/review_service.py`、`ui.py`
- LLM 能力：`biz/llm/`
- 文档与部署：`README.md`、`Dockerfile`、`docker-compose.yml`

同时检查这些常见联动是否遗漏：

- 新增环境变量时，是否同时更新了 `conf/.env.dist`
- 配置逻辑变化时，是否需要同步更新 `biz/utils/config_checker.py`
- 通知渠道行为变化时，是否需要补充 `README.md` 说明
- 平台事件解析改动时，是否影响 `biz/platforms/` 中其他平台实现
- 数据结构或查询变更时，是否会影响 `ui.py` Dashboard 展示
- 依赖变化时，是否需要更新 `requirements.txt` 或部署文件

### Step 3：先验证，再提交

这个仓库当前没有可确认存在的统一 pre-commit / black / flake8 / isort / commit-msg hook 配置，因此不要假设这些 hook 一定会帮你兜底。

提交前应根据改动类型做最小但真实的验证：

- Python 代码改动：优先运行相关单测；如果没有现成测试，至少运行目标文件的 `python -m py_compile`
- 配置逻辑改动：检查相关配置读取路径、默认值、错误处理是否合理
- 文档改动：核对文档内容与代码行为一致
- 如果用户这次任务里已经跑过验证，提交前要复述并沿用已有验证结论，不要凭空省略

对当前仓库，常见的验证命令示例包括：

- `python -m unittest <target>`
- `python -m py_compile <changed python files>`

如果仓库基线本身存在环境问题或依赖缺失，要在提交说明中明确，而不是假装“已全部验证通过”。

### Step 4：生成 Commit Message

优先贴合当前仓库最近历史，推荐使用 Conventional Commits 风格：

- `feat`
- `fix`
- `docs`
- `chore`
- `refactor`
- `test`
- `perf`
- `ci`

推荐格式：

- `type(scope): 简短描述`
- scope 仅在明确时使用，例如：`wecom`、`dingtalk`、`config`、`gitlab`、`github`、`gitea`、`ui`、`queue`、`llm`

如果 scope 不明显，可以退化为：

- `type: 简短描述`

当前仓库里可优先参考的 message 风格示例：

- `fix(dingtalk): 修复钉钉机器人日志记录格式问题`
- `docs(config): 更新环境配置文件中的通知渠道配置说明`
- `chore(ci): 更新 Docker 镜像标签并调整工作流触发条件`
- `fix(wecom): 支持企微评分阈值过滤`

生成规则：

1. 标题尽量短，一眼看出“改了什么”
2. 多文件但同一主题时，用一个清晰主题概括，不要堆文件名
3. 纯文档/图片/说明更新优先用 `docs` 或 `chore`
4. 修 bug 优先用 `fix`
5. 新功能优先用 `feat`

正文在这些情况下建议补充：

- 改动跨多个模块
- 涉及环境变量、兼容性或默认行为变化
- 需要记录验证结果或已知限制

推荐提交模板：

```text
type(scope): 简短描述

- 变更点 1
- 变更点 2
- 验证方式或限制（如有）

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

如果改动很小，也可以只写标题和 trailer：

```text
docs(config): 补充企微评分阈值配置说明

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

### Step 5：暂存文件

优先按文件精确暂存：

- 使用 `git add <具体文件>`
- 避免在存在无关改动时使用 `git add .`
- 暂存前确认没有把样例外的敏感配置、临时文件或日志带进去

### Step 6：执行提交

提交前再次确认：

1. 提交说明与变更内容一致
2. 暂存区文件范围正确
3. trailer 使用：
   `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

提交完成后，用 `git --no-pager status` 确认工作区状态。

## 当前项目特别规则

### 配置类改动

如果本次改动涉及环境变量或配置项，优先检查：

- `conf/.env.dist`
- `README.md`
- `biz/utils/config_checker.py`

这三者经常需要一起更新。

### 通知类改动

如果改动涉及钉钉、企微、飞书或自定义 Webhook：

- 优先检查 `biz/utils/im/`
- 看是否需要同步修改 `biz/event/event_manager.py`
- 如果是用户可感知行为变化，补充 README 说明

### Review 主链路改动

如果改动落在 `biz/queue/worker.py`、`biz/utils/code_reviewer.py`、`biz/platforms/`：

- 检查事件入口、评分提取、消息发送、数据库记录是否仍然连通
- 避免只改一个节点导致主流程断裂

## 安全规则

以下内容默认不要提交：

- `conf/.env`
- 任何 `.env.*` 实际环境文件
- 含真实密钥、Token、Webhook 的配置
- `data/` 下运行时数据库文件
- `log/` 下日志文件
- 证书、私钥、凭证文件

如果发现敏感文件出现在变更中，必须提醒用户并排除。

## 不要做的事

- 不要自动 `git push`
- 不要擅自 `git commit --amend`
- 不要使用 `--no-verify` 绕过校验，除非用户明确要求
- 不要假设仓库存在某些 hook 或规范，必须以仓库实际内容为准
