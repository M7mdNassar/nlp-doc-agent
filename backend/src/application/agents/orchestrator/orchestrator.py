import json
from dataclasses import asdict
from enum import Enum
from typing import Any

import structlog

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.answer.constraints import AnswerLengthError
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.agents.retriever.metadata_filter import MetadataFilterResolver
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.citations.verifier import INSUFFICIENT_ANSWER, CitationVerifier
from src.core.errors import AppError
from src.core.observability import stage
from src.domain.entities.analysis import AnalysisResult
from src.domain.entities.answer import ChatResult
from src.domain.entities.document import Document
from src.domain.entities.evidence import EvidencePackage
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
        self.selector = selector or ContextSelector(max_tokens=24000, max_chunks=16, per_document=12)
        self.max_rounds = max_rounds

    async def process(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        history: list[str] | None = None,
        documents: list[Document] | None = None,
    ) -> ChatResult:
        evidence = EvidencePackage()
        with stage("query_rewrite", history_messages=len(history or [])):
            resolved_question = await self.rewriter.rewrite(question, history)
        answer_question = question
        if history:
            answer_question += f"\nConversation-resolved subject: {resolved_question}"
        if documents is not None:
            filters = (
                MetadataFilterResolver()
                .resolve(
                    question + "\n" + resolved_question,
                    documents,
                    MetadataFilters.model_validate(filters or {}),
                )
                .model_dump(exclude_none=True)
            )
        current_query = resolved_question
        analysis = AnalysisResult(False, "No evidence retrieved")
        round_index = 0
        for attempt in range(self.max_rounds):
            round_index = attempt
            evidence = await self._retrieve(current_query, filters, evidence, attempt + 1)
            with stage("analysis", retrieval_round=attempt + 1) as metrics:
                analysis = await self.analyst.analyze(answer_question, evidence)
                metrics["has_enough_evidence"] = analysis.has_enough_evidence
                metrics["conflict_detected"] = analysis.conflict_detected
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
        return await self._answer(answer_question, filters, result, evidence, analysis, round_index)

    async def _answer(
        self,
        question: str,
        filters: dict[str, Any] | None,
        result: ChatResult,
        evidence: EvidencePackage,
        analysis: AnalysisResult,
        round_index: int,
    ) -> ChatResult:
        try:
            review_feedback = None
            for answer_attempt in range(self.MAX_ANSWER_ATTEMPTS):
                with stage("answer_generation", answer_attempt=answer_attempt + 1):
                    draft = await self.answer_agent.generate(
                        question, evidence, analysis, review_feedback=review_feedback
                    )
                with stage("citation_validation"):
                    self.verifier.validate(draft, evidence)
                with stage("answer_verification", answer_attempt=answer_attempt + 1) as metrics:
                    review = await self.answer_agent.review(draft, evidence, analysis)
                    metrics["accepted"] = review.accepts(len(draft.blocks))
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
                if review.missing_info:
                    if (
                        round_index + 1 >= self.max_rounds
                        or answer_attempt + 1 >= self.MAX_ANSWER_ATTEMPTS
                    ):
                        break
                    previous_ids = {c.id for c in evidence.chunks}
                    round_index += 1
                    evidence = await self._retrieve(
                        review.missing_info, filters, evidence, round_index + 1
                    )
                    result["loops"] = round_index
                    result["evidence_count"] = len(evidence.chunks)
                    if {c.id for c in evidence.chunks} <= previous_ids:
                        break
                    with stage("analysis", retrieval_round=round_index + 1):
                        analysis = await self.analyst.analyze(question, evidence)
                    result["tool_results"] = [asdict(r) for r in analysis.tool_results]
                    if not analysis.has_enough_evidence:
                        break
        except AnswerLengthError as exc:
            raise AppError("ANSWER_OUTPUT_INVALID", str(exc), 503) from exc
        except ValueError as exc:
            logger.warning("answer_rejected", error_type=type(exc).__name__)
        return result

    async def _retrieve(
        self,
        query: str,
        filters: dict[str, Any] | None,
        previous: EvidencePackage,
        round_number: int,
    ) -> EvidencePackage:
        with stage("retrieval", retrieval_round=round_number) as metrics:
            retrieved = await self.retriever.retrieve(query, filters)
            metrics["retrieved_chunks"] = len(retrieved.chunks)
        # Prioritize the current search for missing facts, retaining earlier evidence
        # within the same context budget instead of starving new candidates.
        combined = {str(c.id): c for c in retrieved.chunks}
        for chunk in previous.chunks:
            combined.setdefault(str(chunk.id), chunk)
        with stage("context_selection", candidate_chunks=len(combined)) as metrics:
            evidence = EvidencePackage.from_chunks(self.selector.select(list(combined.values())))
            metrics["selected_chunks"] = len(evidence.chunks)
            metrics["selected_characters"] = sum(len(c.text) for c in evidence.chunks)
        return evidence
