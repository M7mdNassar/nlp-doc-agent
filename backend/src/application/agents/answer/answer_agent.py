from collections.abc import AsyncGenerator

from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget


class AnswerAgent:
    SYSTEM_PROMPT = """You are a helpful assistant.
Answer the question using ONLY the provided context.

You MUST cite your sources using the EXACT format:
[doc_..., p. page_number]

Example: [doc_1234abcd, p. 5]

Do not use outside knowledge.
If the context does not contain the answer, say:
"I don't have enough information."
"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _build_prompt(self, question: str, evidence: EvidencePackage) -> str:
        context = ""

        for chunk in evidence.chunks:
            # Include the actual document ID and page for accurate citations.
            context += (
                f"Document ID: {chunk.document_id} | Page: {chunk.page}\nText: {chunk.text}\n\n"
            )

        return f"Context:\n{context}\nQuestion: {question}"

    async def generate(self, question: str, evidence: EvidencePackage) -> str:
        prompt = self._build_prompt(question, evidence)
        budget = TokenBudget(max_tokens=1000)

        return await self.llm.generate(
            prompt,
            self.SYSTEM_PROMPT,
            budget,
        )

    async def stream(
        self,
        question: str,
        evidence: EvidencePackage,
    ) -> AsyncGenerator[str, None]:
        prompt = self._build_prompt(question, evidence)
        budget = TokenBudget(max_tokens=1000)

        async for token in self.llm.stream(
            prompt,
            self.SYSTEM_PROMPT,
            budget,
        ):
            yield token
