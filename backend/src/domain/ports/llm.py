from collections.abc import AsyncGenerator
from typing import Protocol

from ..value_objects.token_budget import TokenBudget


class LLMClient(Protocol):
    async def generate(self, prompt: str, system: str, budget: TokenBudget) -> str:
        """Standard completion."""
        ...

    async def stream(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        """Stream tokens for the Answer Agent."""
        ...
