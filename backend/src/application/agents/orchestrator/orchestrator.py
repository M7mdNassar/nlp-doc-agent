from enum import Enum

import structlog

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.retriever.retriever_agent import RetrieverAgent
from src.application.citations.verifier import CitationVerifier
from src.domain.entities.evidence import EvidencePackage

logger = structlog.get_logger(__name__)


class State(Enum):
    RECEIVED = "received"
    RETRIEVED = "retrieved"
    ANALYZED = "analyzed"
    ANSWER_READY = "answer_ready"


class Orchestrator:
    def __init__(
        self,
        rewriter: QueryRewriter,
        retriever: RetrieverAgent,
        analyst: AnalystAgent,
        answer_agent: AnswerAgent,
        verifier: CitationVerifier,
    ):
        self.rewriter = rewriter
        self.retriever = retriever
        self.analyst = analyst
        self.answer_agent = answer_agent
        self.verifier = verifier

    async def process(self, question: str) -> dict[str, str | int]:
        state = State.RECEIVED
        evidence = EvidencePackage()
        max_loops = 2
        loop_count = 0
        current_query = question
        filters = {}

        while loop_count < max_loops:
            # 1. Rewrite (Only on first loop)
            if loop_count == 0:
                rewritten = await self.rewriter.rewrite(question)
                current_query = rewritten.query
                filters = rewritten.filters
                logger.info(f"Rewritten query: {current_query} | Filters: {filters}")

            # 2. Retrieve
            evidence = await self.retriever.retrieve(current_query, filters)
            state = State.RETRIEVED

            # 3. Analyze (Tool Loop happens inside)
            analysis = await self.analyst.analyze(question, evidence)
            state = State.ANALYZED

            if analysis.has_enough_evidence:
                logger.info("Analyst approved evidence.")
                break
            else:
                logger.warning(f"Analyst rejected evidence. Missing: {analysis.missing_info}")
                current_query = f"{question} {analysis.missing_info}"
                loop_count += 1

        # 4. Answer
        if evidence.is_empty:
            raw_answer = (
                "I could not find any evidence in the provided documents to answer this question."
            )
        else:
            raw_answer = await self.answer_agent.generate(question, evidence)

        state = State.ANSWER_READY

        # 5. Verify Citations
        final_answer = self.verifier.verify_and_fix(raw_answer, evidence)

        return {
            "answer": final_answer,
            "state": state.value,
            "loops": loop_count,
            "evidence_count": len(evidence.chunks),
        }
