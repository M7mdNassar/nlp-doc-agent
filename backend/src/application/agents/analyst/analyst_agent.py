import json
from dataclasses import dataclass

import structlog

from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

logger = structlog.get_logger(__name__)


@dataclass
class AnalysisResult:
    has_enough_evidence: bool
    missing_info: str
    conflict_detected: bool = False


class AnalystAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def analyze(self, question: str, evidence: EvidencePackage) -> AnalysisResult:
        if evidence.is_empty:
            return AnalysisResult(False, "No documents found.")

        # Format evidence for the prompt
        context = ""
        for i, chunk in enumerate(evidence.chunks):
            context += f"[{i}] {chunk.document_id} (p.{chunk.page}): {chunk.text}\n\n"

        system = """You are an expert research analyst. Evaluate if the provided context contains enough evidence to answer the user's question.
Output STRICT JSON only, with this schema:
{
  "has_enough_evidence": boolean,
  "missing_info": "string (if false, describe what is missing)",
  "conflict_detected": boolean
}"""

        prompt = f"Question: {question}\n\nContext:\n{context}"
        budget = TokenBudget(max_tokens=200)

        try:
            response = await self.llm.generate(prompt, system, budget)
            # Parse JSON (basic cleanup in case LLM adds markdown)
            clean_json = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            return AnalysisResult(
                has_enough_evidence=data.get("has_enough_evidence", False),
                missing_info=data.get("missing_info", ""),
                conflict_detected=data.get("conflict_detected", False),
            )
        except Exception as e:
            logger.error(f"Analyst failed to parse LLM output: {e}")
            # Fail safe: assume we don't have enough evidence
            return AnalysisResult(False, "Analysis failed.")
