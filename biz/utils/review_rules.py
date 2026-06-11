import os
import re
from dataclasses import dataclass
from typing import Optional

import yaml

from biz.utils.log import logger


DEFAULT_REVIEW_RULES_CONFIG_PATH = "conf/review_rules.yml"


@dataclass
class SkipReviewResult:
    should_skip: bool
    pattern: Optional[str] = None
    matched_text: Optional[str] = None


class ReviewRules:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv("REVIEW_RULES_CONFIG_PATH", DEFAULT_REVIEW_RULES_CONFIG_PATH)
        self._config = None

    @staticmethod
    def normalize_repository_key(value: Optional[str]) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def repository_name_from_full_name(repository_full_name: Optional[str]) -> str:
        normalized = (repository_full_name or "").strip()
        if "/" not in normalized:
            return normalized
        return normalized.rsplit("/", 1)[-1]

    def load_config(self) -> dict:
        if self._config is not None:
            return self._config

        if not self.config_path or not os.path.exists(self.config_path):
            logger.info(f"Review rules config not found: {self.config_path}")
            self._config = {}
            return self._config

        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except Exception as exc:
            logger.error(f"Failed to load review rules config {self.config_path}: {exc}")
            self._config = {}
            return self._config

        if not isinstance(data, dict):
            logger.error(f"Review rules config {self.config_path} must be a mapping.")
            self._config = {}
            return self._config

        self._config = data
        return self._config

    def get_repository_rule(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> dict:
        config = self.load_config()
        repositories = config.get("repositories") or {}
        if not isinstance(repositories, dict):
            logger.error("review_rules.yml repositories must be a mapping.")
            return {}

        normalized_repositories = {
            self.normalize_repository_key(key): value
            for key, value in repositories.items()
            if isinstance(value, dict)
        }
        candidates = [
            repository_full_name,
            project_name,
            self.repository_name_from_full_name(repository_full_name),
        ]

        for candidate in candidates:
            key = self.normalize_repository_key(candidate)
            if key and key in normalized_repositories:
                return normalized_repositories[key]
        return {}

    def get_default_rule(self) -> dict:
        defaults = self.load_config().get("defaults") or {}
        if not isinstance(defaults, dict):
            logger.error("review_rules.yml defaults must be a mapping.")
            return {}
        return defaults

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

    def get_wecom_webhook_url(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> Optional[str]:
        repository_rule = self.get_repository_rule(repository_full_name, project_name)
        webhook_url = repository_rule.get("wecom_webhook_url")
        if webhook_url:
            return str(webhook_url).strip()
        return None

    def get_wecom_score_threshold(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> Optional[int]:
        repository_rule = self.get_repository_rule(repository_full_name, project_name)
        repository_threshold = self._parse_non_negative_int(
            repository_rule.get("wecom_score_threshold"),
            "repositories.<repo>.wecom_score_threshold",
        )
        if repository_threshold is not None:
            return repository_threshold

        default_rule = self.get_default_rule()
        default_threshold = self._parse_non_negative_int(
            default_rule.get("wecom_score_threshold"),
            "defaults.wecom_score_threshold",
        )
        if default_threshold is not None:
            return default_threshold

        return self._parse_non_negative_int(os.getenv("WECOM_SCORE_THRESHOLD"), "WECOM_SCORE_THRESHOLD")

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

    def get_review_skip_regex(self, repository_full_name: Optional[str] = None, project_name: Optional[str] = None) -> list:
        repository_rule = self.get_repository_rule(repository_full_name, project_name)
        if "review_skip_regex" in repository_rule:
            patterns = repository_rule.get("review_skip_regex") or []
        else:
            patterns = self.get_default_rule().get("review_skip_regex") or []
        if isinstance(patterns, str):
            return [patterns]
        if not isinstance(patterns, list):
            logger.error("review_skip_regex must be a string or list of strings.")
            return []
        return [str(pattern) for pattern in patterns if pattern]

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
