class LLMRequestRejectedError(Exception):
    """Raised when the model provider rejects a request before generation."""
