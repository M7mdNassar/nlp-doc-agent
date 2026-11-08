import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.agents.orchestrator.orchestrator import Orchestrator
from src.application.citations.verifier import CitationVerifier
from src.domain.entities.analysis import AnalysisResult
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference, GroundingVerdict
from src.domain.entities.evidence import EvidencePackage


def make_orchestrator(sample_chunks, verdicts, batches=None):
    rewriter = SimpleNamespace(rewrite=AsyncMock(return_value="resolved question"))
    retriever = SimpleNamespace(
        retrieve=AsyncMock(side_effect=batches or [EvidencePackage(chunks=sample_chunks)] * 3)
    )
    analyst = SimpleNamespace(analyze=AsyncMock(side_effect=verdicts))
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Model X is 95% accurate.",
                citations=[
                    EvidenceReference(
                        chunk_id=str(sample_chunks[0].id), quote=sample_chunks[0].text
                    )
                ],
            )
        ]
    )
    answer = SimpleNamespace(
        generate=AsyncMock(return_value=draft),
        review=AsyncMock(
            return_value=GroundingVerdict(
                supported=[True], qualifications_preserved=[True], no_added_details=[True]
            )
        ),
    )
    return Orchestrator(rewriter, retriever, analyst, answer, CitationVerifier())


async def test_orchestrator_happy_path_passes_history_analysis_and_formats_sources(sample_chunks):
    analysis = AnalysisResult(True, "")
    orchestrator = make_orchestrator(sample_chunks, [analysis])
    result = await orchestrator.process("What is its accuracy?", {"page": 1}, ["user: Model X?"])
    assert result["state"] == "answer_ready"
    assert result["sources"][0]["chunk_id"] == str(sample_chunks[0].id)
    assert "[doc_123456789, p. 1]" in result["answer"]
    orchestrator.rewriter.rewrite.assert_awaited_once_with(
        "What is its accuracy?", ["user: Model X?"]
    )
    assert orchestrator.answer_agent.generate.await_args.args[2] is analysis


async def test_feedback_accumulates_previous_evidence_and_preserves_filters(sample_chunks):
    orchestrator = make_orchestrator(
        sample_chunks,
        [AnalysisResult(False, "Need Model Y"), AnalysisResult(True, "")],
        [EvidencePackage(chunks=sample_chunks[:1]), EvidencePackage(chunks=sample_chunks[1:])],
    )
    result = await orchestrator.process("Compare models", {"doc_id": "doc_123456789"})
    assert result["state"] == "answer_ready"
    assert result["loops"] == 1
    assert result["evidence_count"] == 2
    assert "Need Model Y" in orchestrator.retriever.retrieve.await_args.args[0]
    for call in orchestrator.retriever.retrieve.await_args_list:
        assert call.args[1] == {"doc_id": "doc_123456789"}


async def test_exhausted_insufficient_evidence_never_calls_answer(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(False, "Missing costs")] * 3)
    result = await orchestrator.process("Compare costs")
    assert result["state"] == "insufficient_evidence"
    assert result["sources"] == []
    orchestrator.answer_agent.generate.assert_not_awaited()


@pytest.mark.parametrize("failure", ["unknown_chunk", "fake_quote", "unsupported_claim"])
async def test_invalid_or_unsupported_drafts_fail_closed(sample_chunks, failure):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    draft = orchestrator.answer_agent.generate.return_value
    if failure == "unknown_chunk":
        draft.blocks[0].citations[0].chunk_id = "chunk_missing"
    elif failure == "fake_quote":
        draft.blocks[0].citations[0].quote = "This quote was invented."
    else:
        orchestrator.answer_agent.review.return_value = GroundingVerdict(
            supported=[False], qualifications_preserved=[True], no_added_details=[True]
        )
    result = await orchestrator.process("Accuracy?")
    assert result["state"] == "insufficient_evidence"
    assert result["sources"] == []
    if failure != "unsupported_claim":
        orchestrator.answer_agent.review.assert_not_awaited()


async def test_failed_qualification_review_gets_one_correction_with_same_evidence(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    rejected = GroundingVerdict(
        supported=[True],
        qualifications_preserved=[False],
        no_added_details=[True],
        feedback=["Block 1: retain the validation-set qualification."],
    )
    accepted = GroundingVerdict(
        supported=[True], qualifications_preserved=[True], no_added_details=[True]
    )
    orchestrator.answer_agent.review.side_effect = [rejected, accepted]
    result = await orchestrator.process("Summarize the result")
    assert result["state"] == "answer_ready"
    calls = orchestrator.answer_agent.generate.await_args_list
    assert len(calls) == 2
    assert calls[0].args == calls[1].args
    feedback = json.loads(calls[1].kwargs["review_feedback"])
    assert feedback["review"] == rejected.model_dump()
    assert feedback["previous_blocks"][0]["text"] == "Model X is 95% accurate."
    assert feedback["previous_blocks"][0]["cited_chunk_ids"] == [str(sample_chunks[0].id)]


async def test_second_correction_is_reviewed_before_returning_answer(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    orchestrator.answer_agent.review.side_effect = [
        GroundingVerdict(
            supported=[True],
            qualifications_preserved=[False],
            no_added_details=[True],
            feedback=["Block 1: retain the validation-set qualification."],
        ),
        GroundingVerdict(
            supported=[False],
            qualifications_preserved=[True],
            no_added_details=[False],
            feedback=["Block 1: remove the unsupported population description."],
        ),
        GroundingVerdict(
            supported=[True],
            qualifications_preserved=[True],
            no_added_details=[True],
        ),
    ]
    result = await orchestrator.process("Summarize the result")
    assert result["state"] == "answer_ready"
    assert result["loops"] == 0
    assert orchestrator.answer_agent.generate.await_count == 3
    assert orchestrator.answer_agent.review.await_count == 3
    feedback = json.loads(orchestrator.answer_agent.generate.await_args.kwargs["review_feedback"])
    assert "population" in feedback["review"]["feedback"][0]


async def test_persistent_added_details_stop_after_three_drafts(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    orchestrator.answer_agent.review.return_value = GroundingVerdict(
        supported=[True], qualifications_preserved=[True], no_added_details=[False]
    )
    result = await orchestrator.process("Summarize the result")
    assert result["state"] == "insufficient_evidence"
    assert result["sources"] == []
    assert orchestrator.answer_agent.generate.await_count == 3
    assert orchestrator.answer_agent.review.await_count == 3
