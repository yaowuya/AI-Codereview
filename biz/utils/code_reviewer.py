import abc
import os
import re
from typing import Dict, Any, List, Optional

import yaml
from jinja2 import Template

from biz.llm.exceptions import LLMRequestRejectedError, LLMServiceUnavailableError
from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.review_rules import ReviewRules
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


LLM_REJECTION_MESSAGE = (
    "AI Review 请求被模型服务拒绝，可能是本次代码变更或提交信息触发了模型服务的风险策略。"
    "请检查变更内容，或通过 review_skip_regex 跳过该提交。"
)


class BaseReviewer(abc.ABC):
    """代码审查基类"""

    def __init__(self, prompt_key: str,
                 repository_full_name: Optional[str] = None,
                 project_name: Optional[str] = None):
        self.client = Factory().getClient()
        style = os.getenv("REVIEW_STYLE", "professional")
        self.prompts = self._load_prompts(
            prompt_key, style,
            repository_full_name=repository_full_name,
            project_name=project_name,
        )

    def _load_prompts(self, prompt_key: str, style: str = "professional",
                      repository_full_name: Optional[str] = None,
                      project_name: Optional[str] = None) -> Dict[str, Any]:
        """
        加载提示词配置，优先级：
          1. ReviewRules 仓库规则 / default.yaml 中的 code_review_prompt
          2. conf/prompt_templates.yml（兜底）
        """
        def render(template_str: str) -> str:
            return Template(template_str).render(style=style)

        # --- 优先从 ReviewRules 目录模式加载 ---
        if prompt_key == "code_review_prompt":
            rules_prompt = ReviewRules().get_code_review_prompt(
                repository_full_name=repository_full_name,
                project_name=project_name,
            )
            if rules_prompt:
                try:
                    return {
                        "system_message": {
                            "role": "system",
                            "content": render(rules_prompt["system_prompt"]),
                        },
                        "user_message": {
                            "role": "user",
                            "content": render(rules_prompt["user_prompt"]),
                        },
                    }
                except KeyError as e:
                    logger.warning(
                        f"[ReviewRules] code_review_prompt missing key {e} for "
                        f"repo={repository_full_name!r}, falling back to prompt_templates.yml"
                    )

        # --- 兜底：conf/prompt_templates.yml ---
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get(prompt_key, {})

            return {
                "system_message": {"role": "system", "content": render(prompts["system_prompt"])},
                "user_message": {"role": "user", "content": render(prompts["user_prompt"])},
            }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载提示词配置失败: {e}")
            raise Exception(f"提示词配置加载失败: {e}")

    def call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM 进行代码审核"""
        content_chars = sum(len(message.get("content", "")) for message in messages)
        logger.info(
            "Sending AI review request: message_count=%s content_chars=%s",
            len(messages),
            content_chars,
        )
        try:
            review_result = self.client.completions(messages=messages)
        except Exception as exc:
            error_text = str(exc)
            if "considered high risk" in error_text or "request was rejected" in error_text:
                logger.warning(f"AI Review 请求被模型服务拒绝: {error_text}")
                raise LLMRequestRejectedError(LLM_REJECTION_MESSAGE) from exc
            raise
        logger.info("Received AI review response: response_chars=%s", len(review_result or ""))
        return review_result

    @abc.abstractmethod
    def review_code(self, *args, **kwargs) -> str:
        """抽象方法，子类必须实现"""
        pass


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    def __init__(self,
                 repository_full_name: Optional[str] = None,
                 project_name: Optional[str] = None):
        super().__init__(
            "code_review_prompt",
            repository_full_name=repository_full_name,
            project_name=project_name,
        )

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        :param changes_text:
        :param commits_text:
        :return:
        """
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %", str(changes_text))
            return "代码为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_text
        tokens_count = count_tokens(changes_text)
        if tokens_count > review_max_tokens:
            changes_text = truncate_text_by_tokens(changes_text, review_max_tokens)

        return self._strip_markdown(self.review_code(changes_text, commits_text))

    def review_changes_in_batches(self, changes: List[Dict[str, Any]], commits_text: str = "") -> str:
        if not changes:
            logger.info("代码为空, changes = %s", changes)
            return "代码为空"

        max_tokens = int(os.getenv("REVIEW_BATCH_MAX_TOKENS", "6000"))
        batches = self._build_review_batches(changes, commits_text, max_tokens)
        logger.info(
            "Preparing batched AI review: change_count=%s batch_count=%s input_tokens=%s batch_max_tokens=%s",
            len(changes),
            len(batches),
            count_tokens(str(changes)),
            max_tokens,
        )

        results = []
        for index, batch in enumerate(batches, start=1):
            diffs_text = str(batch)
            paths = list(dict.fromkeys(
                item.get("new_path") or item.get("filename") or item.get("old_path")
                for item in batch
            ))
            message_tokens = self._messages_token_count(diffs_text, commits_text)
            logger.info(
                "Reviewing AI batch: batch=%s/%s file_count=%s paths=%s content_tokens=%s content_chars=%s",
                index,
                len(batches),
                len(paths),
                paths,
                message_tokens,
                sum(len(message.get("content", "")) for message in self._build_messages(diffs_text, commits_text)),
            )
            try:
                result = self._strip_markdown(self.review_code(diffs_text, commits_text))
                results.append((index, paths, result, None))
            except LLMServiceUnavailableError as exc:
                logger.warning(
                    "AI review batch unavailable: batch=%s/%s status_code=%s request_id=%s paths=%s",
                    index,
                    len(batches),
                    exc.status_code,
                    exc.request_id,
                    paths,
                )
                results.append((index, paths, None, exc))

        successful_results = [result for result in results if result[2] is not None]
        if not successful_results:
            raise results[0][3]
        if len(results) == 1:
            return successful_results[0][2]

        failed_count = len(results) - len(successful_results)
        status = "（部分完成）" if failed_count else ""
        sections = [f"## AI Review 分批结果{status}"]
        for index, paths, result, error in results:
            if error is None:
                body = result
            else:
                details = ["本批次审查失败：AI 模型服务暂时不可用。"]
                if error.status_code is not None:
                    details.append(f"HTTP 状态: {error.status_code}")
                if error.request_id:
                    details.append(f"请求 ID: {error.request_id}")
                body = "\n".join(details)
            sections.append(
                f"### 批次 {index}/{len(results)}\n"
                f"涉及文件: {', '.join(str(path) for path in paths if path)}\n\n"
                f"{body}"
            )
        return "\n\n".join(sections)

    def _build_review_batches(self, changes: List[Dict[str, Any]], commits_text: str,
                              max_tokens: int) -> List[List[Dict[str, Any]]]:
        if max_tokens <= 0:
            raise ValueError("REVIEW_BATCH_MAX_TOKENS 必须大于 0")
        if not self._batch_fits([], commits_text, max_tokens):
            raise ValueError("REVIEW_BATCH_MAX_TOKENS 小于提示词和提交信息所需 token 数")

        units = []
        for change in changes:
            if self._batch_fits([change], commits_text, max_tokens):
                units.append(change)
            else:
                units.extend(self._split_change_by_diff_lines(change, commits_text, max_tokens))

        batches = []
        current_batch = []
        for unit in units:
            candidate = current_batch + [unit]
            if current_batch and not self._batch_fits(candidate, commits_text, max_tokens):
                batches.append(current_batch)
                current_batch = [unit]
            else:
                current_batch = candidate
        if current_batch:
            batches.append(current_batch)
        return batches

    def _split_change_by_diff_lines(self, change: Dict[str, Any], commits_text: str,
                                    max_tokens: int) -> List[Dict[str, Any]]:
        diff = change.get("diff") or change.get("patch") or ""
        diff_key = "diff" if "diff" in change or "patch" not in change else "patch"
        base_change = dict(change)
        base_change[diff_key] = ""
        if not self._batch_fits([base_change], commits_text, max_tokens):
            path = change.get("new_path") or change.get("filename") or change.get("old_path")
            raise ValueError(f"文件元数据超过单批 token 预算: {path}")

        chunks = []
        current = ""
        for line in diff.splitlines(keepends=True) or [diff]:
            candidate = current + line
            candidate_change = dict(base_change)
            candidate_change[diff_key] = candidate
            if self._batch_fits([candidate_change], commits_text, max_tokens):
                current = candidate
                continue

            if current:
                chunk = dict(base_change)
                chunk[diff_key] = current
                chunks.append(chunk)
                current = ""

            line_change = dict(base_change)
            line_change[diff_key] = line
            if self._batch_fits([line_change], commits_text, max_tokens):
                current = line
                continue

            logger.warning(
                "Diff line exceeds AI batch token budget and will be split: path=%s line_chars=%s",
                change.get("new_path") or change.get("filename") or change.get("old_path"),
                len(line),
            )
            line_parts = self._split_text_to_fit(base_change, diff_key, line, commits_text, max_tokens)
            chunks.extend(line_parts[:-1])
            current = line_parts[-1][diff_key]

        if current or not chunks:
            chunk = dict(base_change)
            chunk[diff_key] = current
            chunks.append(chunk)
        return chunks

    def _split_text_to_fit(self, base_change: Dict[str, Any], diff_key: str, text: str,
                           commits_text: str, max_tokens: int) -> List[Dict[str, Any]]:
        chunks = []
        remaining = text
        while remaining:
            low, high, best = 1, len(remaining), 0
            while low <= high:
                middle = (low + high) // 2
                candidate = dict(base_change)
                candidate[diff_key] = remaining[:middle]
                if self._batch_fits([candidate], commits_text, max_tokens):
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best == 0:
                raise ValueError("REVIEW_BATCH_MAX_TOKENS 无法容纳单个 diff 字符")
            chunk = dict(base_change)
            chunk[diff_key] = remaining[:best]
            chunks.append(chunk)
            remaining = remaining[best:]
        return chunks

    def _batch_fits(self, changes: List[Dict[str, Any]], commits_text: str, max_tokens: int) -> bool:
        return self._messages_token_count(str(changes), commits_text) <= max_tokens

    def _messages_token_count(self, diffs_text: str, commits_text: str) -> int:
        combined_content = "\n".join(
            message.get("content", "")
            for message in self._build_messages(diffs_text, commits_text)
        )
        return count_tokens(combined_content)

    def _build_messages(self, diffs_text: str, commits_text: str) -> List[Dict[str, Any]]:
        return [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self._render_user_content(diffs_text, commits_text),
            },
        ]

    def _render_user_content(self, diffs_text: str, commits_text: str) -> str:
        return self.prompts["user_message"]["content"].format(
            diffs_text=diffs_text,
            commits_text=commits_text,
        )

    @staticmethod
    def _strip_markdown(review_result: str) -> str:
        review_result = review_result.strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, diffs_text: str, commits_text: str = "") -> str:
        """Review 代码并返回结果"""
        messages = self._build_messages(diffs_text, commits_text)
        return self.call_llm(messages)

    @staticmethod
    def parse_review_score(review_text: str) -> int:
        """解析 AI 返回的 Review 结果，返回评分"""
        if not review_text:
            return 0
        if "AI Review 分批结果（部分完成）" in review_text:
            return 0
        scores = [int(score) for score in re.findall(r"总分[:：]\s*(\d+)分?", review_text)]
        return min(scores) if scores else 0
