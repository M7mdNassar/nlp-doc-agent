import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.agents.answer.answer_agent import AnswerAgent
from src.domain.entities.analysis import AnalysisResult, Finding, ToolResult
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference
from src.domain.entities.evidence import EvidencePackage
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId


def selected_answer(text="Model X is 95% accurate.", quote_id="quote_1"):
    return json.dumps({"blocks": [{"text": text, "citations": [{"quote_id": quote_id}]}]})


def grounding_response(supported=True, qualifications_preserved=True, no_added_details=True):
    return json.dumps(
        {
            "supported": [supported],
            "qualifications_preserved": [qualifications_preserved],
            "no_added_details": [no_added_details],
        }
    )


async def test_answer_serializes_typed_findings_and_calculation_results(sample_chunks):
    chunk = sample_chunks[0]
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Model X is 95% accurate.",
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    llm = SimpleNamespace(generate=AsyncMock(return_value=selected_answer()))
    analysis = AnalysisResult(
        True,
        "",
        findings=[Finding(text="Model X is 95% accurate.", chunk_ids=[str(chunk.id)])],
        tool_results=[ToolResult("calculator", {"result": "95"}, [str(chunk.id)])],
    )
    answer = await AnswerAgent(llm).generate(
        "Accuracy?", EvidencePackage(chunks=sample_chunks), analysis
    )
    assert answer == draft
    payload = json.loads(llm.generate.await_args.args[0])
    assert payload["analysis"]["findings"][0]["chunk_ids"] == [str(chunk.id)]
    assert payload["analysis"]["tool_results"][0]["output"]["result"] == "95"
    llm.generate.assert_awaited_once()
    assert payload["texts"][payload["evidence"][0]["excerpts"][0]["text_id"]] == chunk.text


@pytest.mark.parametrize("failure", ["paraphrased_quote", "unknown_chunk", "invalid_json"])
async def test_invalid_draft_is_corrected_once_using_original_evidence(sample_chunks, failure):
    chunk = sample_chunks[0]
    valid = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Model X is 95% accurate.",
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    invalid = valid.model_copy(deep=True)
    if failure == "paraphrased_quote":
        invalid.blocks[0].citations[0].quote = "Model X has an accuracy of 95%."
    elif failure == "unknown_chunk":
        invalid.blocks[0].citations[0].chunk_id = "chunk_missing"
    first_response = (
        "not JSON"
        if failure == "invalid_json"
        else selected_answer(quote_id="missing")
        if failure == "unknown_chunk"
        else invalid.model_dump_json()
    )
    llm = SimpleNamespace(generate=AsyncMock(side_effect=[first_response, selected_answer()]))
    answer = await AnswerAgent(llm).generate(
        "Accuracy?", EvidencePackage(chunks=sample_chunks), AnalysisResult(True, "")
    )
    assert answer == valid
    assert llm.generate.await_count == 2
    original = json.loads(llm.generate.await_args_list[0].args[0])
    repair = json.loads(llm.generate.await_args_list[1].args[0])
    assert repair["original_request"] == original
    assert repair["correction"]["previous_draft"] == first_response
    assert repair["correction"]["validation_error"]


async def test_persistently_unknown_excerpt_is_rejected_after_one_correction(sample_chunks):
    response = selected_answer(quote_id="invented")
    llm = SimpleNamespace(generate=AsyncMock(return_value=response))
    with pytest.raises(ValueError, match="unknown source excerpt"):
        await AnswerAgent(llm).generate(
            "Accuracy?", EvidencePackage(chunks=sample_chunks), AnalysisResult(True, "")
        )
    assert llm.generate.await_count == 2


async def test_source_quotes_preserve_pdf_punctuation_and_bound_long_excerpts(sample_chunks):
    chunk = sample_chunks[0]
    chunk.text = "Experience\n\u25cf Internship \u2013 built NLP models. " * 100
    llm = SimpleNamespace(generate=AsyncMock(return_value=selected_answer(quote_id="quote_2")))
    draft = await AnswerAgent(llm).generate(
        "Experience?", EvidencePackage(chunks=[chunk]), AnalysisResult(True, "")
    )
    ref = draft.blocks[0].citations[0]
    assert ref.chunk_id == str(chunk.id)
    assert ref.quote == chunk.text[2000:4000].strip()
    assert ref.quote in chunk.text
    assert len(ref.quote) <= 2000


async def test_grounding_review_uses_selected_excerpt_not_uncited_chunk_text(sample_chunks):
    chunk = sample_chunks[0]
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Model X is 95% accurate.",
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    chunk.text += " Extra uncited information."
    llm = SimpleNamespace(generate=AsyncMock(return_value=grounding_response()))
    assert await AnswerAgent(llm).is_grounded(
        draft, EvidencePackage(chunks=[chunk]), AnalysisResult(True, "")
    )
    payload = json.loads(llm.generate.await_args.args[0])
    source = payload["sources"][payload["blocks"][0]["source_ids"][0]]
    assert payload["texts"][source["quote_text_id"]] == "Model X is 95% accurate."
    assert payload["texts"][source["context_text_id"]] == chunk.text


async def test_provider_failure_is_not_retried_as_a_citation_correction(sample_chunks):
    llm = SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError("Provider unavailable")))
    with pytest.raises(RuntimeError, match="Provider unavailable"):
        await AnswerAgent(llm).generate(
            "Accuracy?", EvidencePackage(chunks=sample_chunks), AnalysisResult(True, "")
        )
    llm.generate.assert_awaited_once()


async def test_quality_correction_does_not_reuse_unverified_findings(sample_chunks):
    llm = SimpleNamespace(generate=AsyncMock(return_value=selected_answer()))
    analysis = AnalysisResult(
        True,
        "",
        findings=[
            Finding(text="An unsupported interpretation", chunk_ids=[str(sample_chunks[0].id)])
        ],
        tool_results=[ToolResult("calculator", {"result": "95"}, [str(sample_chunks[0].id)])],
    )
    await AnswerAgent(llm).generate(
        "Accuracy?",
        EvidencePackage(chunks=sample_chunks),
        analysis,
        review_feedback='{"feedback":["Remove the unsupported interpretation"]}',
    )
    payload = json.loads(llm.generate.await_args.args[0])
    assert payload["analysis"]["findings"] == []
    assert payload["analysis"]["tool_results"][0]["output"]["result"] == "95"
    assert payload["review_feedback"]
    assert (
        payload["texts"][payload["evidence"][0]["excerpts"][0]["text_id"]] == sample_chunks[0].text
    )


@pytest.mark.parametrize(
    "response",
    [
        grounding_response(supported=False),
        grounding_response(qualifications_preserved=False),
        grounding_response(no_added_details=False),
        json.dumps(
            {
                "supported": [True, True],
                "qualifications_preserved": [True],
                "no_added_details": [True],
            }
        ),
        json.dumps(
            {
                "supported": [True],
                "qualifications_preserved": [True, True],
                "no_added_details": [True],
            }
        ),
        json.dumps(
            {
                "supported": [True],
                "qualifications_preserved": [True],
                "no_added_details": [True, True],
            }
        ),
    ],
)
async def test_grounding_review_rejects_false_or_wrong_length_verdict(sample_chunks, response):
    chunk = sample_chunks[0]
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Model X is 100% accurate.",
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    llm = SimpleNamespace(generate=AsyncMock(return_value=response))
    assert not await AnswerAgent(llm).is_grounded(
        draft, EvidencePackage(chunks=sample_chunks), AnalysisResult(True, "")
    )


@pytest.mark.parametrize(
    "response",
    [
        '{"supported":[true]}',
        '{"supported":[true],"qualifications_preserved":["true"],"no_added_details":[true]}',
    ],
)
async def test_incomplete_or_non_boolean_quality_reviews_fail_closed(sample_chunks, response):
    chunk = sample_chunks[0]
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text=chunk.text,
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    llm = SimpleNamespace(generate=AsyncMock(return_value=response))
    with pytest.raises(ValueError):
        await AnswerAgent(llm).is_grounded(
            draft, EvidencePackage(chunks=sample_chunks), AnalysisResult(True, "")
        )


async def test_review_deduplicates_text_without_losing_qualifications_or_citation_scope(
    sample_chunks,
):
    chunk = sample_chunks[0]
    chunk.text = "Throughput improved by ~0.25 cars/s versus fixed timing (simulation-based). " * 20
    quote = chunk.text[: chunk.text.index("(simulation-based)")].strip()
    other = sample_chunks[1]
    first_ref = EvidenceReference(chunk_id=str(chunk.id), quote=quote)
    draft = AnswerDraft(
        blocks=[
            *[
                AnswerBlock(
                    text="Throughput improved by ~0.25 cars/s in simulation.", citations=[first_ref]
                )
                for _ in range(6)
            ],
            AnswerBlock(
                text=other.text,
                citations=[EvidenceReference(chunk_id=str(other.id), quote=other.text)],
            ),
        ]
    )
    llm = SimpleNamespace(
        generate=AsyncMock(
            return_value=json.dumps(
                {
                    "supported": [True] * 7,
                    "qualifications_preserved": [True] * 7,
                    "no_added_details": [True] * 7,
                }
            )
        )
    )
    await AnswerAgent(llm).review(
        draft, EvidencePackage(chunks=[chunk, other]), AnalysisResult(True, "")
    )
    serialized, instructions, _ = llm.generate.await_args.args
    payload = json.loads(serialized)
    assert list(payload["texts"].values()).count(chunk.text.strip()) == 1
    assert len(payload["sources"]) == 2
    for block in payload["blocks"][:6]:
        source = payload["sources"][block["source_ids"][0]]
        assert source["chunk_id"] == str(chunk.id)
        assert payload["texts"][source["quote_text_id"]] == quote
        assert "simulation-based" in payload["texts"][source["context_text_id"]]
    assert payload["blocks"][-1]["source_ids"] != payload["blocks"][0]["source_ids"]
    assert "ONLY its own source_ids" in instructions
    old = json.dumps(
        {
            "blocks": [
                {
                    "claim": b.text,
                    "sources": [
                        {"chunk_id": r.chunk_id, "text": r.quote, "source_context": chunk.text}
                        for r in b.citations
                    ],
                }
                for b in draft.blocks[:6]
            ]
        }
    )
    assert len(serialized) < len(old) * 0.5


async def test_generation_shares_identical_text_but_keeps_both_documents(sample_chunks):
    first = sample_chunks[0]
    second = replace(
        first, id=ChunkId.generate(), document_id=DocumentId.generate(), document_name="copy.docx"
    )
    llm = SimpleNamespace(generate=AsyncMock(return_value=selected_answer(quote_id="quote_2")))
    draft = await AnswerAgent(llm).generate(
        "Accuracy?", EvidencePackage(chunks=[first, second]), AnalysisResult(True, "")
    )
    payload = json.loads(llm.generate.await_args.args[0])
    assert len(payload["texts"]) == 1
    assert len(payload["evidence"]) == 2
    assert (
        payload["evidence"][0]["excerpts"][0]["text_id"]
        == payload["evidence"][1]["excerpts"][0]["text_id"]
    )
    assert draft.blocks[0].citations[0].chunk_id == str(second.id)


async def test_similar_but_differently_qualified_sources_are_not_merged(sample_chunks):
    first = sample_chunks[0]
    first.text = "Throughput improved in simulation."
    second = sample_chunks[1]
    second.text = "Throughput improved in deployment."
    llm = SimpleNamespace(generate=AsyncMock(return_value=selected_answer()))
    await AnswerAgent(llm).generate(
        "Results?", EvidencePackage(chunks=[first, second]), AnalysisResult(True, "")
    )
    payload = json.loads(llm.generate.await_args.args[0])
    assert set(payload["texts"].values()) == {first.text, second.text}
