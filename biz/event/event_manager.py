from blinker import Signal

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity
from biz.service.review_service import ReviewService
from biz.utils.im import notifier

# 定义全局事件管理器（事件信号）
event_manager = {
    "merge_request_reviewed": Signal(),
    "push_reviewed": Signal(),
}


def _score_color(score) -> str:
    """根据分数返回企微 font color 标签值：高分绿色，低分橙红。"""
    if score is None:
        return "comment"
    return "info" if score >= 80 else "warning" if score < 60 else "comment"


def _build_mr_message(entity: MergeRequestReviewEntity) -> str:
    """
    构造符合企业微信 markdown 规范的 MR/PR Review 消息。
    支持语法：# 标题、**加粗**、[text](url)、> 引用、<font color="">
    """
    score_str = f'<font color="{_score_color(entity.score)}">**{entity.score} 分**</font>' \
        if entity.score else '<font color="comment">未评分</font>'

    lines = [
        f"# 🔀 Merge Request Review — {entity.project_name}",
        "",
        f"**提交者：** {entity.author}",
        f"**源分支：** `{entity.source_branch}` → **目标分支：** `{entity.target_branch}`",
        f"**AI 评分：** {score_str}",
        f"**提交信息：** {entity.commit_messages}",
        f"[查看合并详情]({entity.url})",
        "",
        "---",
        "",
        "**AI Review 结果：**",
        "",
    ]

    # Review 内容：保留首段核心意见，过长时截断（企微 markdown 上限 4096 字节）
    review_text = (entity.review_result or "").strip()
    # 去掉外层 ```markdown ``` 包裹（如果有）
    if review_text.startswith("```"):
        review_text = "\n".join(review_text.splitlines()[1:])
        if review_text.endswith("```"):
            review_text = review_text[:-3].strip()

    lines.append(review_text)

    content = "\n".join(lines)

    # 企微 markdown 上限 4096 字节
    encoded = content.encode("utf-8")
    if len(encoded) > 4000:
        content = encoded[:4000].decode("utf-8", errors="ignore") + "\n…（内容过长，已截断）"

    return content


def _build_push_message(entity: PushReviewEntity) -> str:
    """
    构造符合企业微信 markdown 规范的 Push Review 消息。
    """
    score_str = f'<font color="{_score_color(entity.score)}">**{entity.score} 分**</font>' \
        if entity.score else '<font color="comment">未评分</font>'

    commit_lines = []
    for commit in entity.commits[:5]:  # 最多展示 5 条
        msg = commit.get("message", "").strip().splitlines()[0]  # 只取首行
        author = commit.get("author", "")
        url = commit.get("url", "")
        commit_lines.append(f"> [{msg}]({url}) — {author}" if url else f"> {msg} — {author}")
    if len(entity.commits) > 5:
        commit_lines.append(f"> …… 共 {len(entity.commits)} 条提交")

    lines = [
        f"# 🚀 Push Review — {entity.project_name}",
        "",
        f"**提交者：** {entity.author}　**分支：** `{entity.branch}`",
        f"**AI 评分：** {score_str}　**变更：** +{entity.additions} / -{entity.deletions}",
        "",
        "**提交记录：**",
        *commit_lines,
    ]

    if entity.review_result:
        review_text = (entity.review_result or "").strip()
        if review_text.startswith("```"):
            review_text = "\n".join(review_text.splitlines()[1:])
            if review_text.endswith("```"):
                review_text = review_text[:-3].strip()
        lines += ["", "**AI Review 结果：**", "", review_text]

    content = "\n".join(lines)
    encoded = content.encode("utf-8")
    if len(encoded) > 4000:
        content = encoded[:4000].decode("utf-8", errors="ignore") + "\n…（内容过长，已截断）"

    return content


# 定义事件处理函数
def on_merge_request_reviewed(mr_review_entity: MergeRequestReviewEntity):
    im_msg = _build_mr_message(mr_review_entity)
    notifier.send_notification(
        content=im_msg,
        msg_type='markdown',
        title='Merge Request Review',
        project_name=mr_review_entity.project_name,
        url_slug=mr_review_entity.url_slug,
        webhook_data=mr_review_entity.webhook_data,
        score=mr_review_entity.score,
        repository_full_name=mr_review_entity.repository_full_name,
    )
    ReviewService().insert_mr_review_log(mr_review_entity)


def on_push_reviewed(entity: PushReviewEntity):
    im_msg = _build_push_message(entity)
    notifier.send_notification(
        content=im_msg,
        msg_type='markdown',
        title=f"{entity.project_name} Push Event",
        project_name=entity.project_name,
        url_slug=entity.url_slug,
        webhook_data=entity.webhook_data,
        score=entity.score,
        repository_full_name=entity.repository_full_name,
    )
    ReviewService().insert_push_review_log(entity)


# 连接事件处理函数到事件信号
event_manager["merge_request_reviewed"].connect(on_merge_request_reviewed)
event_manager["push_reviewed"].connect(on_push_reviewed)
