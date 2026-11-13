import asyncio
from collections.abc import AsyncGenerator

import structlog

from src.core.config import settings
from src.core.observability import current_trace, llm_call_scope, llm_operation, retry_wait
from src.domain.exceptions.llm_provider_error import LLMCooldownError, LLMRateLimitError
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

from .groq_adapter import GroqAdapter
from .openrouter_adapter import OpenRouterAdapter

logger = structlog.get_logger(__name__)


class LLMRouter(LLMClient):
    """Try fallbacks immediately, then allow one bounded cooldown retry per call."""

    def __init__(self) -> None:
        models = list(
            dict.fromkeys(
                model.strip()
                for model in [settings.LLM_MODEL, *settings.LLM_FALLBACK_MODELS]
                if model.strip()
            )
        )
        if not models:
            raise ValueError("At least one LLM model must be configured")
        self.providers: list[GroqAdapter | OpenRouterAdapter] = [
            GroqAdapter(model=model) for model in models
        ]
        if settings.OPENROUTER_API_KEY.strip():
            self.providers.extend(
                OpenRouterAdapter(model=model)
                for model in dict.fromkeys(m.strip() for m in settings.OPENROUTER_FALLBACK_MODELS)
                if model
            )
        if "openai/gpt-oss-safeguard-20b" in models:
            logger.warning(
                "llm_specialized_fallback_configured",
                model="openai/gpt-oss-safeguard-20b",
                intended_task="safety_classification",
            )

    @staticmethod
    def _log_limit(provider: GroqAdapter | OpenRouterAdapter, error: LLMRateLimitError) -> None:
        logger.warning(
            "llm_model_rate_limited",
            model=provider.model,
            local_cooldown=isinstance(error, LLMCooldownError),
            retry_after_seconds=error.retry_after_seconds,
            action="try_next_model",
        )

    @staticmethod
    def _exhausted(errors: list[LLMRateLimitError]) -> LLMRateLimitError:
        # Any one model recovering is enough to serve the next call. Do not
        # return the primary's long cooldown if a fallback resets sooner.
        known_waits = [e.retry_after_seconds for e in errors if e.retry_after_seconds is not None]
        delay = min(known_waits) if known_waits else None
        logger.warning("llm_models_exhausted", model_count=len(errors), retry_after_seconds=delay)
        providers = list(dict.fromkeys(error.provider for error in errors))
        return LLMRateLimitError(" / ".join(providers), delay)

    @llm_operation
    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        for attempt in range(2):
            errors: list[LLMRateLimitError] = []
            for index, provider in enumerate(self.providers):
                try:
                    response = await provider.generate_for_router(prompt, system, budget)
                    logger.info("llm_model_selected", model=provider.model, fallback=index > 0)
                    return response
                except LLMRateLimitError as exc:
                    self._log_limit(provider, exc)
                    errors.append(exc)
            exhausted = self._exhausted(errors)
            trace = current_trace()
            spent = sum(float(wait["planned_seconds"]) for wait in trace.waits) if trace else 0
            remaining = settings.LLM_FALLBACK_MAX_WAIT_SECONDS - spent
            # Unknown resets and long daily limits must not become blind retry loops.
            # Cached cooldowns may belong to a smaller, earlier prompt. Prefer
            # fresh HTTP hints, which were computed for this call's token demand.
            fresh_waits = [
                error.retry_after_seconds
                for error in errors
                if not isinstance(error, LLMCooldownError) and error.retry_after_seconds is not None
            ]
            delay = min(fresh_waits) if fresh_waits else exhausted.retry_after_seconds
            if attempt or delay is None or max(1, delay) > remaining:
                raise exhausted
            with retry_wait(max(1, delay), "all_models_rate_limited"):
                await asyncio.sleep(max(1, delay))
        raise AssertionError("Unreachable fallback retry state")

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        with llm_call_scope():
            errors: list[LLMRateLimitError] = []
            for provider in self.providers:
                emitted = False
                try:
                    async for token in provider.stream_for_router(prompt, system, budget):
                        emitted = True
                        yield token
                    return
                except LLMRateLimitError as exc:
                    # Replaying a partially emitted answer would mix model outputs.
                    if emitted:
                        raise
                    self._log_limit(provider, exc)
                    errors.append(exc)
            raise self._exhausted(errors)
