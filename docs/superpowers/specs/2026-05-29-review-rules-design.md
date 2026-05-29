# Review 规则配置设计

## 背景

当前服务会处理 GitLab、GitHub 和 Gitea 的 webhook 事件，对代码进行 AI Review，然后通过钉钉、企业微信、飞书和额外自定义 webhook 推送审查结果。企业微信目前已经支持全局低分阈值，也有按项目名或平台 URL slug 路由 webhook 的雏形，但当多个仓库需要发送到不同企业微信机器人、并使用不同告警阈值时，这种环境变量配置方式不够清晰，也不方便长期维护。

另外，并不是所有代码变更都需要触发 AI Review。是否跳过 Review 应该可配置，并通过正则表达式匹配 MR/PR 标题和 commit message。

## 目标

- 支持为不同仓库配置不同的企业微信机器人。
- 支持为不同仓库配置不同的企业微信分数阈值。
- 支持用正则表达式匹配 MR/PR 标题和 commit message，从而跳过 AI Review。
- 保持现有 `.env` 配置行为作为兼容回退。
- 在 GitLab、GitHub 和 Gitea 上保持一致行为。

## 非目标

- 不替换所有现有 `.env` 通知配置。
- 不增加规则管理 UI。
- 不改变 LLM Review 分数解析方式。
- 不改变钉钉、飞书或额外自定义 webhook 的现有行为，只保留已有路由能力。

## 配置文件

新增 `conf/review_rules.yml`。

```yaml
defaults:
  wecom_score_threshold: 80
  review_skip_regex:
    - "\\[skip review\\]"
    - "^WIP:"

repositories:
  my-group/my-repo:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
    wecom_score_threshold: 70
    review_skip_regex:
      - "\\[no ai\\]"

  another-repo:
    wecom_webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=yyy"
    wecom_score_threshold: 90
```

仓库 key 使用当前平台能拿到的最具体仓库标识：

- GitHub 和 Gitea：优先使用 `repository.full_name`，取不到时回退到 `repository.name`。
- GitLab：优先使用 `project.path_with_namespace`，取不到时回退到 `project.name`。

匹配时忽略大小写。如果完整仓库 key 没有命中，规则加载器还会尝试用仓库名回退匹配。

## 规则优先级

企业微信 webhook URL 解析顺序：

1. `repositories.<repo>.wecom_webhook_url`
2. 现有环境变量路由，例如 `WECOM_WEBHOOK_URL_<PROJECT_OR_URL_SLUG>`
3. 现有全局 `WECOM_WEBHOOK_URL`

企业微信分数阈值解析顺序：

1. `repositories.<repo>.wecom_score_threshold`
2. `defaults.wecom_score_threshold`
3. 现有全局 `WECOM_SCORE_THRESHOLD`
4. 不按分数过滤

跳过 Review 的正则解析顺序：

1. 如果存在，使用 `repositories.<repo>.review_skip_regex`
2. 使用 `defaults.review_skip_regex`
3. 不配置跳过规则

仓库级 `review_skip_regex` 会替换默认规则，而不是与默认规则合并。这样单个仓库可以配置更宽或更窄的跳过策略，不会意外继承全局规则。

## 跳过 Review 行为

在获取大 diff 或调用 LLM 之前，每个 webhook handler 构造待匹配文本：

- MR/PR 事件：标题加所有 commit message。
- Push 事件：所有 commit message。

如果任意配置的正则命中待匹配文本，handler 记录跳过原因并直接返回。被跳过的 Review 不调用 AI、不写平台 note、不发送 Review 结果通知。

无效正则会记录错误日志并被忽略，避免一个错误 pattern 阻断整个 webhook 处理流程。

## 组件设计

新增 `biz/utils/review_rules.py`，职责如下：

- 懒加载 `conf/review_rules.yml`。
- 归一化仓库标识用于规则匹配。
- 解析仓库级企业微信 webhook URL。
- 解析仓库级企业微信分数阈值。
- 基于标题和 commit message 判断是否跳过 Review。

更新 `biz/queue/worker.py`：

- 为各平台事件提取仓库标识。
- 在 MR/PR 和 Push Review 前执行跳过判断。
- 将仓库标识传入通知链路，让企业微信能够解析仓库级规则。

更新 `biz/utils/im/wecom.py`：

- 优先向规则模块查询仓库级 webhook URL 和分数阈值。
- 保留现有按项目名、URL slug 和全局环境变量的回退逻辑。

更新文档：

- 在 `.env.dist` 增加 `REVIEW_RULES_CONFIG_PATH`，默认值为 `conf/review_rules.yml`。
- 在 README 和 FAQ 中说明 YAML 格式和配置示例。

## 错误处理

- `conf/review_rules.yml` 不存在：记录 info 日志，并使用现有 `.env` 行为。
- YAML 格式错误：记录 error 日志，并使用现有 `.env` 行为。
- 阈值配置非法：记录 error 日志，并继续使用下一级阈值。
- 正则配置非法：记录 error 日志，并忽略该 pattern。
- 仓库标识缺失：尽量使用项目名；仍取不到时只应用 defaults。

## 测试

新增聚焦测试，覆盖：

- 通过完整仓库名和仓库名回退匹配规则。
- 企业微信 webhook 的优先级。
- 仓库级阈值覆盖默认阈值和环境变量阈值。
- MR/PR 标题和 commit message 命中正则后跳过 Review。
- Push commit message 命中正则后跳过 Review。
- 无效正则和缺失配置文件时的回退行为。

## 验收标准

- 单个仓库可以把低分企业微信告警发送到自己的机器人。
- 同一个部署中，两个仓库可以使用不同的企业微信分数阈值。
- 配置 `\\[skip review\\]` 这类正则后，MR/PR 标题或 commit message 命中时会跳过 AI Review。
- 只使用 `.env` 的现有部署保持原行为。
