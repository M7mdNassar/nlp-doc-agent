import re

import structlog

from src.domain.exceptions.llm_provider_error import LLMProviderError
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.rewritten_query import RewrittenQuery
from src.domain.value_objects.token_budget import TokenBudget

logger = structlog.get_logger(__name__)


class QueryRewriter:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def rewrite(self, query: str, history: list[str] | None = None) -> str:
        if not history:
            # Standalone questions already name their subject. Rewriting them can
            # change retrieval rankings and spends a call without resolving context.
            search_query = re.sub(
                r"(?:[,;]\s*|\s+)(?:please\s+)?(?:answer|respond|explain|summarize)"
                r"\s+(?:in|exactly|at most|no more than|under|fewer than|up to)"
                r"\s+\d+\s+words[.!?]?\s*$",
                "",
                query,
                flags=re.I,
            ).strip()
            return search_query or query
        system = (
            "Rewrite the question as a concise document search query. Resolve pronouns using "
            "history. Preserve named documents, entities, dates and page/section restrictions. "
            "Remove answer formatting and word-count instructions. For how/why questions, "
            "search for the mechanism, steps or explanation requested. Do not answer the "
            "question or invent facts. Return ONLY the search query."
        )
        prompt = f"History:\n{history}\n\nQuestion: {query}" if history else f"Question: {query}"

        budget = TokenBudget(max_tokens=1024)
        try:
            rewritten = await self.llm.generate(prompt, system, budget)
            return rewritten.strip()
        except LLMProviderError:
            raise
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}. Using original.")
            return RewrittenQuery(query=query, filters={})
