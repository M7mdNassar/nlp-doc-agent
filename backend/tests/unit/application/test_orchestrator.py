from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agents.analyst.analyst_agent import AnalysisResult
from src.application.agents.orchestrator.orchestrator import Orchestrator, State
from src.domain.entities.evidence import EvidencePackage


@pytest.mark.asyncio
async def test_orchestrator_happy_path(sample_chunks, mock_llm):
    # Setup Mocks
    mock_rewriter = AsyncMock()
    mock_rewriter.rewrite.return_value = "rewritten query"

    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = EvidencePackage(chunks=sample_chunks)

    mock_analyst = AsyncMock()
    mock_analyst.analyze.return_value = AnalysisResult(has_enough_evidence=True, missing_info="")

    mock_answer = AsyncMock()
    mock_answer.generate.return_value = "The answer is 95% [doc_123456789, p. 1]."

    mock_verifier = MagicMock()
    mock_verifier.verify_and_fix.side_effect = lambda x, y: x  # Pass-through

    orchestrator = Orchestrator(
        mock_rewriter, mock_retriever, mock_analyst, mock_answer, mock_verifier
    )

    result = await orchestrator.process("What is the accuracy?")

    assert result["state"] == State.ANSWER_READY.value
    assert result["loops"] == 0
    assert "[doc_123456789, p. 1]" in result["answer"]
    mock_retriever.retrieve.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_feedback_loop(sample_chunks, mock_llm):
    # Setup Mocks
    mock_rewriter = AsyncMock()
    mock_rewriter.rewrite.return_value = "rewritten query"

    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = EvidencePackage(chunks=sample_chunks)

    # First time it says NO, second time it says YES
    mock_analyst = AsyncMock()
    mock_analyst.analyze.side_effect = [
        AnalysisResult(has_enough_evidence=False, missing_info="Need financials"),
        AnalysisResult(has_enough_evidence=True, missing_info=""),
    ]

    mock_answer = AsyncMock()
    mock_answer.generate.return_value = "Final answer."
    mock_verifier = MagicMock()
    mock_verifier.verify_and_fix.return_value = "Final answer."

    orchestrator = Orchestrator(
        mock_rewriter, mock_retriever, mock_analyst, mock_answer, mock_verifier
    )

    result = await orchestrator.process("What is the accuracy?")

    assert result["loops"] == 1  # It looped once
    assert mock_analyst.analyze.call_count == 2
    assert mock_retriever.retrieve.call_count == 2
