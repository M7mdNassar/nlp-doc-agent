import math
import time
from collections.abc import AsyncGenerator

import structlog
from groq import APIError, APIStatusError, AsyncGroq

from src.core.config import settings
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMCooldownError,
    LLMProviderError,
    LLMRateLimitError,
)
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

from .retry import async_retry

logger = structlog.get_logger(__name__)


class GroqAdapter(LLMClient):
    def __init__(self) -> None:
        # One retry layer only. In particular, never retry 429 inside the SDK.
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY, max_retries=0)
        # Using standard production models
        self.model = settings.LLM_MODEL
        self._rate_limit_until = 0.0

    def _check_rate_limit(self) -> None:
        remaining = self._rate_limit_until - time.monotonic()
        if remaining > 0:
            raise LLMCooldownError("Groq", math.ceil(remaining))

    def _provider_error(self, error: APIError) -> LLMProviderError:
        if isinstance(error, APIStatusError):
            if error.status_code == 429:
                seconds = None
                try:
                    delay = float(error.response.headers.get("retry-after", ""))
                    if math.isfinite(delay) and delay > 0:
                        seconds = math.ceil(delay)
                except ValueError:
                    pass
                if seconds is not None:
                    self._rate_limit_until = max(self._rate_limit_until, time.monotonic() + seconds)
                return LLMRateLimitError("Groq", seconds)
            if error.status_code in {400, 401, 403, 404, 422}:
                return LLMConfigurationError("Groq")
        return LLMProviderError("Groq")

    @async_retry(max_retries=3)
    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        self._check_rate_limit()
        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,  # Low temp for factual RAG
                max_tokens=budget.remaining,
            )
        except APIError as exc:
            raise self._provider_error(exc) from exc
        content = response.choices[0].message.content or ""
        if response.choices[0].finish_reason != "stop" or not content.strip():
            raise ValueError("LLM completion was incomplete or empty")
        return content

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        self._check_rate_limit()
        try:
            stream = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=budget.remaining,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except APIError as exc:
            # Streaming is never replayed after partial output.
            raise self._provider_error(exc) from exc
