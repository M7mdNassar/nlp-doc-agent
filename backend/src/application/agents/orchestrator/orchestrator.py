import json
from dataclasses import asdict
from enum import Enum
from typing import Any

import structlog

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.agents.retriever.metadata_filter import MetadataFilterResolver
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.citations.verifier import INSUFFICIENT_ANSWER, CitationVerifier
from src.domain.entities.analysis import AnalysisResult
from src.domain.entities.answer import ChatResult
from src.domain.entities.document import Document
from src.domain.entities.evidence import EvidencePackage
from src.domain.exceptions.llm_provider_error import LLMProviderError
from src.domain.value_objects.metadata_filters import MetadataFilters

logger = structlog.get_logger(__name__)


class State(Enum):
    RECEIVED = "received"
    RETRIEVED = "retrieved"
    ANALYZED = "analyzed"
    ANSWER_READY = "answer_ready"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Orchestrator:
    MAX_ANSWER_ATTEMPTS = 3

    def __init__(
        self,
        rewriter: QueryRewriter,
        retriever: RetrieverAgent,
        analyst: AnalystAgent,
        answer_agent: AnswerAgent,
        verifier: CitationVerifier,
        selector: ContextSelector | None = None,
        max_rounds: int = 3,
    ):
        if max_rounds < 1:
            raise ValueError("At least one retrieval round is required")
        self.rewriter, self.retriever, self.analyst = rewriter, retriever, analyst
        self.answer_agent, self.verifier = answer_agent, verifier
        self.selector = selector or ContextSelector(max_tokens=24000, max_chunks=16, per_document=8)
        self.max_rounds = max_rounds

    async def process(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        history: list[str] | None = None,
        documents: list[Document] | None = None,
    ) -> ChatResult:
        evidence = EvidencePackage()
        resolved_question = await self.rewriter.rewrite(question, history)
        if documents is not None:
            filters = (
                MetadataFilterResolver()
                .resolve(
                    resolved_question, documents, MetadataFilters.model_validate(filters or {})
                )
                .model_dump(exclude_none=True)
            )
        current_query = resolved_question
        analysis = AnalysisResult(False, "No evidence retrieved")
        round_index = 0
        for attempt in range(self.max_rounds):
            round_index = attempt
            retrieved = await self.retriever.retrieve(current_query, filters)
            combined = {str(c.id): c for c in evidence.chunks}
            combined.update({str(c.id): c for c in retrieved.chunks})
            evidence = EvidencePackage.from_chunks(self.selector.select(list(combined.values())))
            analysis = await self.analyst.analyze(resolved_question, evidence)
            if analysis.has_enough_evidence:
                break
            current_query = (
                f"{resolved_question}\nAdditional evidence needed: {analysis.missing_info}"
            )

        result = ChatResult(
            answer=INSUFFICIENT_ANSWER,
            state=State.INSUFFICIENT_EVIDENCE.value,
            loops=round_index,
            evidence_count=len(evidence.chunks),
            sources=[],
            tool_results=[asdict(r) for r in analysis.tool_results],
            conversation_id="",
        )
        # Exhausted budgets and malformed/insufficient verdicts never authorize generation.
        if not analysis.has_enough_evidence or evidence.is_empty:
            return result
        try:
            review_feedback = None
            for answer_attempt in range(self.MAX_ANSWER_ATTEMPTS):
                if review_feedback is None:
                    draft = await self.answer_agent.generate(resolved_question, evidence, analysis)
                else:
                    draft = await self.answer_agent.generate(
                        resolved_question, evidence, analysis, review_feedback=review_feedback
                    )
                self.verifier.validate(draft, evidence)
                review = await self.answer_agent.review(draft, evidence, analysis)
                if review.accepts(len(draft.blocks)):
                    result["answer"], result["sources"] = self.verifier.format(draft, evidence)
                    result["state"] = State.ANSWER_READY.value
                    break
                logger.warning(
                    "answer_quality_rejected",
                    attempt=answer_attempt + 1,
                    supported=review.supported,
                    qualifications_preserved=review.qualifications_preserved,
                    no_added_details=review.no_added_details,
                )
                review_feedback = json.dumps(
                    {
                        "review": review.model_dump(),
                        "previous_blocks": [
                            {
                                "text": block.text,
                                "cited_chunk_ids": [ref.chunk_id for ref in block.citations],
                            }
                            for block in draft.blocks
                        ],
                    }
                )
        except LLMProviderError:
            raise
        except Exception as exc:
            logger.warning("answer_rejected", error=str(exc))
        return result
