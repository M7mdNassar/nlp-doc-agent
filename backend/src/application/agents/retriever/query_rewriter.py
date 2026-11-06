import structlog

from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

logger = structlog.get_logger(__name__)


class QueryRewriter:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def rewrite(self, query: str, history: list[str] | None = None) -> str:
        system = "You are a search query optimizer. Rewrite the user's question to be optimal for vector search. Resolve pronouns using the history if provided. Return ONLY the rewritten query, no other text."
        prompt = f"History:\n{history}\n\nQuestion: {query}" if history else f"Question: {query}"

        budget = TokenBudget(max_tokens=100)
        try:
            rewritten = await self.llm.generate(prompt, system, budget)
            return rewritten.strip()
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}. Using original.")
            return query
