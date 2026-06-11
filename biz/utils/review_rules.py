import os
import re
from dataclasses import dataclass
from typing import Optional

import yaml

from biz.utils.log import logger


DEFAULT_REVIEW_RULES_CONFIG_PATH = "conf/review_rules.yml"
DEFAULT_REVIEW_RULES_CONFIG_DIR = "conf/review_rule"


@dataclass
class SkipReviewResult:
    should_skip: bool
    pattern: Optional[str] = None
    matched_text: Optional[str] = None


class ReviewRules:
    """
    加载仓库级 Review 规则，支持两种模式：

    目录模式（优先）：
        REVIEW_RULES_CONFIG_DIR 指向目录（默认 conf/review_rule/）。
        - default.yaml / default.yml：全局默认值。
        - 其余 .yaml / .yml 文件：每个文件内必须包含 `repository:` 字段，
          声明该文件归属的仓库（如 "backend-team/core-api"）。
        文件名不参与匹配，只作为人类可读标识。

    单文件模式（兼容旧版）：
        REVIEW_RULES_CONFIG_PATH 指向单个 YAML 文件（含 defaults: + repositories: 两段）。
        仅当目录模式未生效时（目录不存在或为空）才回退到此模式。

    构造参数 config_dir / config_path 可直接传入，优先级高于环境变量，主要供测试使用。
    """

    def __init__(
        self,
        config_dir: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        # 目录模式参数
        self.config_dir = config_dir or os.getenv(
            "REVIEW_RULES_CONFIG_DIR", DEFAULT_REVIEW_RULES_CONFIG_DIR
        )
        # 单文件模式参数（向后兼容）
        self.config_path = config_path or os.getenv(
            "REVIEW_RULES_CONFIG_PATH", DEFAULT_REVIEW_RULES_CONFIG_PATH
        )

        self._default_rule: Optional[dict] = None
        self._repo_rules: Optional[dict] = None   # normalized_key -> rule dict

    # ------------------------------------------------------------------
    # 内部：加载
    # ------------------------------------------------------------------

    def _use_dir_mode(self) -> bool:
        """判断是否使用目录模式。"""
        return bool(self.config_dir and os.path.isdir(self.config_dir))

    def _load_yaml_file(self, path: str) -> Optional[dict]:
        """安全加载单个 YAML 文件，失败返回 None。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                logger.error(f"Review rules file {path} must be a mapping, ignored.")
                return None
            return data
        except Exception as exc:
            logger.error(f"Failed to load review rules file {path}: {exc}")
            return None

    def _ensure_loaded(self):
        if self._repo_rules is not None:
            return

        if self._use_dir_mode():
            self._load_dir_mode()
        else:
            self._load_single_file_mode()

    def _load_dir_mode(self):
        """扫描目录，分别加载 default.yaml 和各仓库规则文件。"""
        self._default_rule = {}
        self._repo_rules = {}

        try:
            entries = os.listdir(self.config_dir)
        except OSError as exc:
            logger.error(f"Cannot list review_rule dir {self.config_dir}: {exc}")
            return

        for filename in entries:
            if not (filename.endswith(".yaml") or filename.endswith(".yml")):
                continue
            filepath = os.path.join(self.config_dir, filename)
            data = self._load_yaml_file(filepath)
            if data is None:
                continue

            stem = os.path.splitext(filename)[0].lower()
            if stem == "default":
                self._default_rule = data
                logger.info(f"Review rules: loaded default from {filepath}")
                continue

            repo_key = data.get("repository")
            if not repo_key:
                logger.warning(
                    f"Review rules file {filepath} has no 'repository:' field, skipped."
                )
                continue

            # 支持逗号分隔多个仓库，每个 key 都指向同一份规则
            repo_keys = [k.strip() for k in str(repo_key).split(",") if k.strip()]
            for key in repo_keys:
                normalized = self.normalize_repository_key(key)
                if normalized in self._repo_rules:
                    logger.warning(
                        f"Review rules: duplicate repository key '{key}' in {filepath}, overwriting."
                    )
                self._repo_rules[normalized] = data
            logger.info(f"Review rules: loaded repository {repo_keys} from {filepath}")

    def _load_single_file_mode(self):
        """加载旧版单文件格式（defaults: + repositories: 两段）。"""
        self._default_rule = {}
        self._repo_rules = {}

        if not self.config_path or not os.path.exists(self.config_path):
            logger.info(f"Review rules config not found: {self.config_path}")
            return

        data = self._load_yaml_file(self.config_path)
        if not data:
            return

        defaults = data.get("defaults") or {}
        if isinstance(defaults, dict):
            self._default_rule = defaults
        else:
            logger.error("review_rules.yml defaults must be a mapping.")

        repositories = data.get("repositories") or {}
        if not isinstance(repositories, dict):
            logger.error("review_rules.yml repositories must be a mapping.")
            return

        for key, value in repositories.items():
            if not isinstance(value, dict):
                continue
            normalized = self.normalize_repository_key(key)
            self._repo_rules[normalized] = value

        logger.info(f"Review rules: loaded single-file config from {self.config_path}")

    # ------------------------------------------------------------------
    # 静态工具
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_repository_key(value: Optional[str]) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def repository_name_from_full_name(repository_full_name: Optional[str]) -> str:
        normalized = (repository_full_name or "").strip()
        if "/" not in normalized:
            return normalized
        return normalized.rsplit("/", 1)[-1]

    # ------------------------------------------------------------------
    # 公开查询接口
    # ------------------------------------------------------------------

    def get_default_rule(self) -> dict:
        self._ensure_loaded()
        return self._default_rule or {}

    def get_repository_rule(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> dict:
        self._ensure_loaded()
        repo_rules = self._repo_rules or {}
        logger.info(f"[ReviewRules] get_repository_rule: full_name={repository_full_name!r}, project_name={project_name!r}, loaded_keys={list(repo_rules.keys())}")

        candidates = [
            repository_full_name,
            project_name,
            self.repository_name_from_full_name(repository_full_name),
        ]
        for candidate in candidates:
            key = self.normalize_repository_key(candidate)
            if key and key in repo_rules:
                logger.info(f"[ReviewRules] matched key={key!r}")
                return repo_rules[key]
        logger.info(f"[ReviewRules] no match found for candidates={[self.normalize_repository_key(c) for c in candidates]}")
        return {}

    @staticmethod
    def _parse_non_negative_int(value, source: str) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            threshold = int(value)
        except (TypeError, ValueError):
            logger.error(f"{source} must be a non-negative integer.")
            return None
        if threshold < 0:
            logger.error(f"{source} must be a non-negative integer.")
            return None
        return threshold

    def get_wecom_webhook_url(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[str]:
        rule = self.get_repository_rule(repository_full_name, project_name)
        url = rule.get("wecom_webhook_url")
        if url:
            return str(url).strip()
        # 尝试 default
        url = self.get_default_rule().get("wecom_webhook_url")
        if url:
            return str(url).strip()
        return None

    def get_wecom_score_threshold(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[int]:
        # 1. 仓库级
        rule = self.get_repository_rule(repository_full_name, project_name)
        v = self._parse_non_negative_int(
            rule.get("wecom_score_threshold"),
            "repository.wecom_score_threshold",
        )
        if v is not None:
            return v
        # 2. 全局默认
        v = self._parse_non_negative_int(
            self.get_default_rule().get("wecom_score_threshold"),
            "default.wecom_score_threshold",
        )
        if v is not None:
            return v
        # 3. 环境变量
        return self._parse_non_negative_int(
            os.getenv("WECOM_SCORE_THRESHOLD"), "WECOM_SCORE_THRESHOLD"
        )

    @staticmethod
    def _commit_messages(commits: Optional[list]) -> list:
        messages = []
        for commit in commits or []:
            if not isinstance(commit, dict):
                continue
            message = commit.get("message")
            if message:
                messages.append(str(message))
        return messages

    def get_code_review_prompt(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[dict]:
        """
        获取仓库级 code_review_prompt（system_prompt + user_prompt）。
        优先级：仓库规则 > default.yaml > None（调用方回退到 conf/prompt_templates.yml）
        返回含 system_prompt / user_prompt 两个 key 的 dict，或 None。
        """
        rule = self.get_repository_rule(repository_full_name, project_name)
        prompt = rule.get("code_review_prompt")
        if prompt and isinstance(prompt, dict):
            return prompt

        prompt = self.get_default_rule().get("code_review_prompt")
        if prompt and isinstance(prompt, dict):
            return prompt

        return None

    def get_review_skip_regex(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> list:
        rule = self.get_repository_rule(repository_full_name, project_name)
        if "review_skip_regex" in rule:
            patterns = rule.get("review_skip_regex") or []
        else:
            patterns = self.get_default_rule().get("review_skip_regex") or []
        if isinstance(patterns, str):
            return [patterns]
        if not isinstance(patterns, list):
            logger.error("review_skip_regex must be a string or list of strings.")
            return []
        return [str(p) for p in patterns if p]

    def should_skip_review(
        self,
        repository_full_name: Optional[str] = None,
        project_name: Optional[str] = None,
        title: Optional[str] = None,
        commits: Optional[list] = None,
    ) -> SkipReviewResult:
        text_parts = []
        if title:
            text_parts.append(str(title))
        text_parts.extend(self._commit_messages(commits))
        target_text = "\n".join(text_parts)

        if not target_text:
            return SkipReviewResult(False)

        for pattern in self.get_review_skip_regex(repository_full_name, project_name):
            try:
                if re.search(pattern, target_text, flags=re.IGNORECASE | re.MULTILINE):
                    return SkipReviewResult(True, pattern=pattern, matched_text=target_text)
            except re.error as exc:
                logger.error(f"Invalid review skip regex '{pattern}': {exc}")
        return SkipReviewResult(False)

    # ------------------------------------------------------------------
    # 向后兼容：旧版 load_config()
    # ------------------------------------------------------------------

    def load_config(self) -> dict:
        """
        向后兼容接口。目录模式下返回合并后的伪单文件结构；
        单文件模式下返回原始 dict。
        """
        self._ensure_loaded()
        if self._use_dir_mode():
            repos = {}
            for key, rule in (self._repo_rules or {}).items():
                # 以原始 repository 字段为 key 还原，若无则用 normalized key
                display_key = rule.get("repository", key)
                repos[display_key] = rule
            result = {}
            if self._default_rule:
                result["defaults"] = self._default_rule
            if repos:
                result["repositories"] = repos
            return result
        else:
            # 单文件模式：直接重新读一次原始 dict 供 config_checker 使用
            if self.config_path and os.path.exists(self.config_path):
                data = self._load_yaml_file(self.config_path)
                return data or {}
            return {}
