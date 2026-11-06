from collections.abc import AsyncGenerator

import structlog
from groq import AsyncGroq

from src.core.config import settings
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

from .retry import async_retry

logger = structlog.get_logger(__name__)


class GroqAdapter(LLMClient):
    def __init__(self) -> None:
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        # Using standard production models
        self.model = "llama-3.3-70b-versatile"

    @async_retry(max_retries=3)
    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        response = await self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            model=self.model,
            temperature=0.1,  # Low temp for factual RAG
            max_tokens=budget.remaining,
        )
        content = response.choices[0].message.content or ""
        return content

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
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
