import os

from dotenv import load_dotenv

from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.review_rules import ReviewRules

# 指定环境变量文件路径
ENV_FILE_PATH = "conf/.env"
load_dotenv(ENV_FILE_PATH)


REQUIRED_ENV_VARS = [
    "LLM_PROVIDER",
]

# 允许的 LLM 供应商
LLM_PROVIDERS = { "anthropic", "zhipuai", "openai", "deepseek", "ollama", "qwen" }

# 每种供应商必须配置的键
LLM_REQUIRED_KEYS = {
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE_URL", "ANTHROPIC_API_MODEL"],
    "zhipuai": ["ZHIPUAI_API_KEY", "ZHIPUAI_API_MODEL"],
    "openai": ["OPENAI_API_KEY", "OPENAI_API_MODEL"],
    "deepseek": ["DEEPSEEK_API_KEY", "DEEPSEEK_API_MODEL"],
    "ollama": ["OLLAMA_API_BASE_URL", "OLLAMA_API_MODEL"],
    "qwen": ["QWEN_API_KEY", "QWEN_API_MODEL"],
}


def check_env_vars():
    """检查环境变量"""
    missing_vars = [var for var in REQUIRED_ENV_VARS if var not in os.environ]
    if missing_vars:
        logger.warning(f"缺少环境变量: {', '.join(missing_vars)}")
    else:
        logger.info("所有必要的环境变量均已设置。")


def check_llm_provider():
    """检查 LLM 供应商的配置"""
    llm_provider = os.getenv("LLM_PROVIDER")

    if not llm_provider:
        logger.error("LLM_PROVIDER 未设置！")
        return

    if llm_provider not in LLM_PROVIDERS:
        logger.error(f"LLM_PROVIDER 值错误，应为 {LLM_PROVIDERS} 之一。")
        return

    required_keys = LLM_REQUIRED_KEYS.get(llm_provider, [])
    missing_keys = [key for key in required_keys if not os.getenv(key)]

    if missing_keys:
        logger.error(f"当前 LLM 供应商为 {llm_provider}，但缺少必要的环境变量: {', '.join(missing_keys)}")
    else:
        logger.info(f"LLM 供应商 {llm_provider} 的配置项已设置。")


def check_wecom_score_threshold():
    """检查企业微信 Review 分数阈值配置。"""
    threshold_text = os.getenv("WECOM_SCORE_THRESHOLD", "").strip()
    if not threshold_text:
        logger.info("WECOM_SCORE_THRESHOLD 未设置，企业微信推送将保持当前默认行为。")
        return

    try:
        threshold = int(threshold_text)
    except ValueError:
        logger.error("WECOM_SCORE_THRESHOLD 配置错误，必须是非负整数。")
        return

    if threshold < 0:
        logger.error("WECOM_SCORE_THRESHOLD 配置错误，必须是非负整数。")
        return

    logger.info(f"WECOM_SCORE_THRESHOLD 已启用：仅当 Review 分数低于 {threshold} 时推送企业微信消息。")


def check_review_rules_config():
    """检查仓库级 Review 规则配置。"""
    rules = ReviewRules()
    if rules._use_dir_mode():
        rules._ensure_loaded()
        repo_count = len(rules._repo_rules or {})
        logger.info(
            f"Review 规则配置已加载（目录模式）：{rules.config_dir}，"
            f"共 {repo_count} 个仓库规则，default.yaml {'已' if rules._default_rule else '未'}配置。"
        )
    else:
        config = rules.load_config()
        if config:
            logger.info(f"Review 规则配置已加载（单文件模式）：{rules.config_path}")
        else:
            logger.info("Review 规则配置为空或未配置，将使用现有环境变量行为。")


def check_llm_connectivity():
    client = Factory().getClient()
    logger.info(f"正在检查 LLM 供应商的连接...")
    if client.ping():
        logger.info("LLM 可以连接成功。")
    else:
        logger.error("LLM连接可能有问题，请检查配置项。")

def check_config():
    """主检查入口"""
    logger.info("开始检查配置项...")
    check_env_vars()
    check_llm_provider()
    check_wecom_score_threshold()
    check_review_rules_config()
    check_llm_connectivity()
    logger.info("配置项检查完成。")
