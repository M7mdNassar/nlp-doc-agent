from collections.abc import AsyncGenerator

import structlog

from src.core.config import settings
from src.core.observability import llm_call_scope, llm_operation
from src.domain.exceptions.llm_provider_error import LLMCooldownError, LLMRateLimitError
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

from .groq_adapter import GroqAdapter

logger = structlog.get_logger(__name__)


class LLMRouter(LLMClient):
    """Try models in configured order on rate limits, without waiting between them."""

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
        self.providers = [GroqAdapter(model=model) for model in models]
        if "openai/gpt-oss-safeguard-20b" in models:
            logger.warning(
                "llm_specialized_fallback_configured",
                model="openai/gpt-oss-safeguard-20b",
                intended_task="safety_classification",
            )

    @staticmethod
    def _log_limit(provider: GroqAdapter, error: LLMRateLimitError) -> None:
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
        logger.warning(
            "llm_models_exhausted", model_count=len(errors), retry_after_seconds=delay
        )
        return LLMRateLimitError("Groq", delay)

    @llm_operation
    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        errors: list[LLMRateLimitError] = []
        for index, provider in enumerate(self.providers):
            try:
                response = await provider.generate_for_router(prompt, system, budget)
                logger.info("llm_model_selected", model=provider.model, fallback=index > 0)
                return response
            except LLMRateLimitError as exc:
                self._log_limit(provider, exc)
                errors.append(exc)
        raise self._exhausted(errors)

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
