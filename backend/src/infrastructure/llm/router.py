from collections.abc import AsyncGenerator

import structlog

from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

from .groq_adapter import GroqAdapter

logger = structlog.get_logger(__name__)


class LLMRouter(LLMClient):
    """
    Routes LLM requests.
    In v1, we primarily use Groq. If Groq fails, we can add Cerebras here.
    """

    def __init__(self) -> None:
        self.providers: list[LLMClient] = [
            GroqAdapter(),
            # CerebrasAdapter(), # Will be added later
        ]

    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        last_error = None
        for provider in self.providers:
            try:
                return await provider.generate(prompt, system, budget)
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} failed: {e}")
                last_error = e
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        last_error = None
        for provider in self.providers:
            try:
                async for token in provider.stream(prompt, system, budget):
                    yield token
                return  # Success
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} stream failed: {e}")
                last_error = e
        raise RuntimeError(f"All LLM providers failed to stream. Last error: {last_error}")
