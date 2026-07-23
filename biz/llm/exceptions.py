class LLMRequestRejectedError(Exception):
    """Raised when the model provider rejects a request before generation."""


class LLMServiceUnavailableError(Exception):
    """Raised when a transient provider failure prevents generation."""

    def __init__(self, provider: str, status_code: int = None, request_id: str = None):
        super().__init__("AI 模型服务暂时不可用，请稍后重试。")
        self.provider = provider
        self.status_code = status_code
        self.request_id = request_id
