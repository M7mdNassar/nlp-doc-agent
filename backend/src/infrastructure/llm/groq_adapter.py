import math
import time
from collections.abc import AsyncGenerator

import structlog
from groq import APIError, APIStatusError, AsyncGroq

from src.core.config import settings
from src.core.observability import llm_call_scope, llm_operation, provider_request
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMCooldownError,
    LLMProviderError,
    LLMRateLimitError,
)
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

from .retry import async_retry
from .usage import record_error, record_response

logger = structlog.get_logger(__name__)


class GroqAdapter(LLMClient):
    def __init__(self, model: str | None = None) -> None:
        # One retry layer only. In particular, never retry 429 inside the SDK.
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY, max_retries=0)
        self.model = model or settings.LLM_MODEL
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

    @llm_operation
    @async_retry(max_retries=3)
    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        return await self._generate_once(prompt, system, budget)

    @async_retry(max_retries=3, max_rate_limit_wait=0)
    async def generate_for_router(self, prompt: str, system: str, budget: TokenBudget) -> str:
        """Keep bounded transient retries, but let the router handle 429 immediately."""
        return await self._generate_once(prompt, system, budget)

    async def _generate_once(self, prompt: str, system: str, budget: TokenBudget) -> str:
        self._check_rate_limit()
        with provider_request("groq", self.model, budget.remaining) as request:
            try:
                response = await self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model,
                    temperature=0.1,
                    max_tokens=budget.remaining,
                )
            except APIError as exc:
                record_error(request, exc)
                raise self._provider_error(exc) from exc
            # Account for every completion, including drafts rejected by validation.
            record_response(request, response)
            request.finish_reason = response.choices[0].finish_reason
            content = response.choices[0].message.content or ""
            if request.finish_reason != "stop" or not content.strip():
                raise ValueError("LLM completion was incomplete or empty")
            return content

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        with llm_call_scope():
            async for token in self.stream_for_router(prompt, system, budget):
                yield token

    async def stream_for_router(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        self._check_rate_limit()
        with provider_request("groq", self.model, budget.remaining) as request:
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
                try:
                    async for chunk in stream:
                        record_response(request, chunk)
                        if chunk.choices:
                            request.finish_reason = (
                                getattr(chunk.choices[0], "finish_reason", None)
                                or request.finish_reason
                            )
                            delta = chunk.choices[0].delta.content
                            if delta:
                                yield delta
                finally:
                    close = getattr(stream, "close", None) or getattr(stream, "aclose", None)
                    if close is not None:
                        await close()
            except APIError as exc:
                record_error(request, exc)
                # Streaming is never replayed after partial output.
                raise self._provider_error(exc) from exc
