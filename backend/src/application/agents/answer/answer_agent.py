from collections.abc import AsyncGenerator

from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget


class AnswerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _build_prompt(self, question: str, evidence: EvidencePackage) -> str:
        context = ""
        for chunk in evidence.chunks:
            # We use the format [doc_name, p. X] to match our Citation Verifier
            context += f"Source [p. {chunk.page}]: {chunk.text}\n\n"
        return f"Context:\n{context}\n\nQuestion: {question}"

    async def generate(self, question: str, evidence: EvidencePackage) -> str:
        system = """You are a helpful assistant. Answer the question using ONLY the provided context.
You MUST cite your sources using the format [doc_id, p. page_number] exactly as shown in the context.
If the context does not contain the answer, say "I don't have enough information."
Do not use outside knowledge."""

        prompt = self._build_prompt(question, evidence)
        budget = TokenBudget(max_tokens=1000)
        return await self.llm.generate(prompt, system, budget)

    async def stream(self, question: str, evidence: EvidencePackage) -> AsyncGenerator[str, None]:
        system = """You are a helpful assistant. Answer the question using ONLY the provided context.
You MUST cite your sources using the format [doc_id, p. page_number] exactly as shown in the context."""

        prompt = self._build_prompt(question, evidence)
        budget = TokenBudget(max_tokens=1000)

        async for token in self.llm.stream(prompt, system, budget):
            yield token
