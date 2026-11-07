import json

import structlog

from src.domain.ports.llm import LLMClient
from src.domain.value_objects.rewritten_query import RewrittenQuery
from src.domain.value_objects.token_budget import TokenBudget

logger = structlog.get_logger(__name__)


class QueryRewriter:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def rewrite(self, query: str) -> RewrittenQuery:
        system = """You are a search query optimizer. Rewrite the user's question to be optimal for vector search.
You must also extract any metadata filters explicitly mentioned by the user.
Output STRICT JSON only:
{
  "query": "rewritten query string",
  "filters": {"doc_name": "paper.pdf", "section": "Chapter 4"}
}
If no filters are mentioned, return an empty object for "filters"."""

        prompt = f"Question: {query}"
        budget = TokenBudget(max_tokens=150)

        try:
            response = await self.llm.generate(prompt, system, budget)
            clean_json = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            return RewrittenQuery(query=data.get("query", query), filters=data.get("filters", {}))
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}. Using original.")
            return RewrittenQuery(query=query, filters={})
