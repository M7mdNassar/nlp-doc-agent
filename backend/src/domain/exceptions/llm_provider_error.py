class LLMProviderError(Exception):
    """The provider could not complete a request; this is not an evidence verdict."""

    def __init__(self, provider: str, message: str | None = None) -> None:
        self.provider = provider
        super().__init__(
            message or f"{provider} is temporarily unavailable. Please try again later."
        )


class LLMRateLimitError(LLMProviderError):
    def __init__(self, provider: str, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            provider, f"{provider} has reached a request or token limit. Please try again later."
        )


class LLMOutputError(LLMProviderError):
    """The provider returned an incomplete/empty completion, not an evidence verdict."""

    def __init__(self, provider: str, *, finish_reason: str | None = None) -> None:
        self.finish_reason = finish_reason
        super().__init__(
            provider,
            "The AI model returned incomplete output. Please retry. "
            "Your documents are still available.",
        )


class LLMTimeoutError(LLMProviderError):
    """A complete provider response did not arrive within its wall-clock limit."""

    def __init__(self, provider: str) -> None:
        super().__init__(provider, f"{provider} did not complete its response in time.")


class LLMCooldownError(LLMRateLimitError):
    """A known rate limit blocked a local call before a provider request was sent."""


class LLMConfigurationError(LLMProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            provider,
            f"{provider} could not accept the request. Check the backend provider credentials, model, and request limits.",
        )
