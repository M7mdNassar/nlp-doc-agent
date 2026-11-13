import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.answer.answer_agent import AnswerAgent
from src.application.agents.answer.constraints import validate_length, word_requirement
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.agents.source_texts import SourceExcerpts, SourceTexts
from src.application.tools.analyst_tools import AnalystTools
from src.core.errors import AnalysisOutputError, AppError
from src.core.retrieval_diagnostics import retrieval_events
from src.domain.entities.analysis import AnalysisResult, Finding, FindingQuote, ToolRequest
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference, GroundingVerdict
from src.domain.entities.evidence import EvidencePackage
from src.infrastructure.parsers.pdf_parser import PDFParser
from tests.unit.application.test_orchestrator import make_orchestrator


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "how does attention work in transformers, answer in 50 words",
            "how does attention work in transformers",
        ),
        ("Explain section 3.2 of attention.pdf", "Explain section 3.2 of attention.pdf"),
        ("How were changes in 50 words measured?", "How were changes in 50 words measured?"),
    ],
)
async def test_standalone_search_preserves_subject_without_model_call(question, expected):
    llm = SimpleNamespace(generate=AsyncMock())
    assert await QueryRewriter(llm).rewrite(question) == expected
    llm.generate.assert_not_awaited()


async def test_failed_followup_rewrite_keeps_the_original_string_contract():
    llm = SimpleNamespace(generate=AsyncMock(side_effect=ValueError("Invalid rewrite")))
    result = await QueryRewriter(llm).rewrite(
        "What tools did it use?", ["user: Explain the ETL pipeline."]
    )
    assert result == "What tools did it use?"
    assert isinstance(result, str)


async def test_paper_preserves_mechanism_spacing_sections_and_decoder_scope():
    path = Path(__file__).resolve().parents[2] / "attention.pdf"
    elements = await PDFParser().parse(path)
    mechanism = next(e for e in elements if e.page == 4 and (e.section or "").startswith("3.2.1"))
    assert "We compute the dot products" in mechanism.text
    assert "softmax function to obtain the weights" in mechanism.text
    assert "√" in mechanism.text
    assert "queries and keys" in mechanism.text
    applications = next(
        e for e in elements if e.page == 5 and (e.section or "").startswith("3.2.3")
    )
    assert "self-attention layers in the decoder" in applications.text
    assert "masking out" in applications.text
    assert any(e.is_table and e.page == 9 for e in elements)


async def test_partial_rules_preserve_complete_configuration_table_and_column_spacing():
    elements = await PDFParser().parse(Path(__file__).resolve().parents[2] / "attention.pdf")
    table = next(e for e in elements if e.is_table and e.page == 9)
    assert table.table_data["format"] == "layout"
    assert table.table_data["headers"] == []  # No invented cell structure for numerical tools.
    assert table.table_data["bbox"][0] == pytest.approx(108, abs=1)
    assert table.table_data["bbox"][2] == pytest.approx(508.7, abs=1)
    lines = table.text.splitlines()
    base = next(line for line in lines if line.strip().startswith("base "))
    big = next(line for line in lines if "big" in line)
    assert base.split() == [
        "base",
        "6",
        "512",
        "2048",
        "8",
        "64",
        "64",
        "0.1",
        "0.1",
        "100K",
        "4.92",
        "25.8",
        "65",
    ]
    assert big.split() == ["big", "6", "1024", "4096", "16", "0.3", "300K", "4.33", "26.4", "213"]
    assert abs(base.index("4.92") - big.index("4.33")) <= 1
    head_variant = next(line for line in lines if "5.29" in line)
    assert abs(head_variant.index("1") - (base.index(" 8 ") + 1)) <= 1
    assert "positional embedding instead of sinusoids" in table.text
    assert table.text.startswith("Table 3: Variations on the Transformer architecture")
    assert "Unlisted values are identical" in table.text
    assert "Table 3:" not in "\n".join(e.text for e in elements if e.page == 9 and not e.is_table)
    assert "25.8" not in "\n".join(e.text for e in elements if e.page == 9 and not e.is_table)


def test_table_tool_resolves_only_supplied_table_references(sample_chunks):
    table = replace(sample_chunks[0], table_data={"headers": ["Value"], "rows": [["95"]]})
    evidence = EvidencePackage(chunks=[table, sample_chunks[1]])
    excerpts = SourceExcerpts(evidence, SourceTexts())
    tools = AnalystTools(evidence, excerpts.references)
    result = tools.execute(ToolRequest(name="table_extractor", arguments={"quote_id": "quote_1"}))
    assert result.chunk_ids == [str(table.id)]
    assert result.output == table.table_data
    for args in (
        {"quote_id": "quote_999"},
        {"quote_id": "quote_2"},
        {"quote_id": "text_1"},
        {"quote_id": "quote_1", "chunk_id": str(table.id)},
    ):
        with pytest.raises(ValueError):
            tools.execute(ToolRequest(name="table_extractor", arguments=args))


def test_layout_tool_text_reuses_source_parts_without_changing_actual_tool_output(sample_chunks):
    from src.domain.entities.analysis import ToolResult

    text = "A row with spacing   and values\n" * 100
    chunk = replace(sample_chunks[0], text=text)
    texts = SourceTexts()
    SourceExcerpts(EvidencePackage(chunks=[chunk]), texts)
    before = dict(texts.texts)
    result = ToolResult("table_extractor", {"format": "layout", "text": text}, [str(chunk.id)])
    encoded = texts.tool_results([result])[0]["output"]
    assert texts.texts == before
    assert "".join(texts.texts[key] for key in encoded["text_ids"]) == text
    assert result.output["text"] == text


async def test_tool_free_analysis_uses_one_call_and_validates_support(sample_chunks):
    response = {
        "tools": [],
        "verdict": {
            "has_enough_evidence": True,
            "missing_info": "",
            "findings": [
                {
                    "text": "The reported accuracy is 95%.",
                    "chunk_ids": ["chunk_1"],
                    "quotes": [{"chunk_id": "chunk_1", "quote": sample_chunks[0].text}],
                }
            ],
        },
    }
    llm = SimpleNamespace(generate=AsyncMock(return_value=json.dumps(response)))
    result = await AnalystAgent(llm).analyze("Accuracy?", EvidencePackage(chunks=sample_chunks))
    assert result.has_enough_evidence
    assert result.findings[0].quotes[0].quote == sample_chunks[0].text
    llm.generate.assert_awaited_once()


async def test_analyst_selects_exact_excerpts_without_copying_source(sample_chunks):
    response = {
        "tools": [],
        "verdict": {
            "has_enough_evidence": True,
            "missing_info": "",
            "findings": [{"text": "The reported accuracy is 95%.", "quote_ids": ["quote_1"]}],
        },
    }
    llm = SimpleNamespace(generate=AsyncMock(return_value=json.dumps(response)))
    result = await AnalystAgent(llm).analyze("Accuracy?", EvidencePackage(chunks=sample_chunks))
    assert result.findings[0].chunk_ids == [str(sample_chunks[0].id)]
    assert result.findings[0].quotes[0].quote == sample_chunks[0].text
    llm.generate.assert_awaited_once()


@pytest.mark.parametrize("quote_ids", [["quote_999"], []])
async def test_analyst_rejects_unknown_or_absent_source_references(sample_chunks, quote_ids):
    response = {
        "tools": [],
        "verdict": {
            "has_enough_evidence": True,
            "missing_info": "",
            "findings": [{"text": "An unsupported claim", "quote_ids": quote_ids}],
        },
    }
    llm = SimpleNamespace(generate=AsyncMock(return_value=json.dumps(response)))
    with pytest.raises(AnalysisOutputError):
        await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=sample_chunks))


async def test_first_draft_uses_shared_source_quotes_without_analyst_claims(sample_chunks):
    chunk = sample_chunks[0]
    llm = SimpleNamespace(
        generate=AsyncMock(
            return_value=json.dumps(
                {"blocks": [{"text": chunk.text, "citations": [{"quote_id": "quote_1"}]}]}
            )
        )
    )
    analysis = AnalysisResult(
        True,
        "",
        findings=[
            Finding(
                text="An unsupported analyst interpretation",
                chunk_ids=[str(chunk.id)],
                quotes=[FindingQuote(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ],
    )
    await AnswerAgent(llm).generate("Accuracy?", EvidencePackage(chunks=[chunk]), analysis)
    prompt = llm.generate.await_args.args[0]
    payload = json.loads(prompt)
    assert "unsupported analyst interpretation" not in prompt
    assert list(payload["texts"].values()) == [chunk.text]
    assert payload["analysis"]["findings"][0]["quotes"][0]["text_id"] == "text_1"


@pytest.mark.parametrize("quotes", [[], [{"chunk_id": "chunk_1", "quote": "Invented evidence"}]])
async def test_known_chunk_id_does_not_authorize_unsupported_findings(sample_chunks, quotes):
    response = {
        "tools": [],
        "verdict": {
            "has_enough_evidence": True,
            "missing_info": "",
            "findings": [{"text": "Invented evidence", "chunk_ids": ["chunk_1"], "quotes": quotes}],
        },
    }
    llm = SimpleNamespace(generate=AsyncMock(return_value=json.dumps(response)))
    with pytest.raises(AnalysisOutputError):
        await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=sample_chunks))
    assert llm.generate.await_count == 2


def test_selection_diagnostic_records_excluded_candidates_without_enabling_global_capture(
    sample_chunks,
):
    events = []
    token = retrieval_events.set(events)
    try:
        selected = ContextSelector(len, per_document=1).select(sample_chunks)
    finally:
        retrieval_events.reset(token)
    assert selected == sample_chunks[:1]
    assert events[0]["candidates"][1]["decision"] == "document_limit"
    ContextSelector(len).select(sample_chunks)
    assert len(events) == 1


async def test_original_word_count_reaches_generation(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    orchestrator.rewriter.rewrite.return_value = "Model X accuracy"
    await orchestrator.process("Explain its accuracy in 50 words")
    assert (
        orchestrator.answer_agent.generate.await_args.args[0] == "Explain its accuracy in 50 words"
    )


async def test_missing_support_retrieves_new_evidence_before_next_draft(sample_chunks):
    orchestrator = make_orchestrator(
        sample_chunks,
        [AnalysisResult(True, ""), AnalysisResult(True, "")],
        [EvidencePackage(chunks=sample_chunks[:1]), EvidencePackage(chunks=sample_chunks[1:])],
    )
    orchestrator.answer_agent.review.side_effect = [
        GroundingVerdict(
            supported=[False],
            qualifications_preserved=[True],
            no_added_details=[False],
            missing_info="Model Y accuracy",
            feedback=["Need the Model Y result."],
        ),
        GroundingVerdict(
            supported=[True], qualifications_preserved=[True], no_added_details=[True]
        ),
    ]
    result = await orchestrator.process("Compare accuracy", {"doc_ids": ["doc_123456789"]})
    assert result["state"] == "answer_ready" and result["loops"] == 1
    assert orchestrator.retriever.retrieve.await_args.args == (
        "Model Y accuracy",
        {"doc_ids": ["doc_123456789"]},
    )
    assert len(orchestrator.answer_agent.generate.await_args.args[1].chunks) == 2
    assert orchestrator.answer_agent.review.await_count == 2


async def test_exhausted_length_correction_is_an_output_error(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    llm = SimpleNamespace(
        generate=AsyncMock(
            return_value=json.dumps(
                {"blocks": [{"text": "Too short.", "citations": [{"quote_id": "quote_1"}]}]}
            )
        )
    )
    orchestrator.answer_agent = AnswerAgent(llm)
    with pytest.raises(AppError) as error:
        await orchestrator.process("Explain in 50 words")
    assert error.value.code == "ANSWER_OUTPUT_INVALID"
    assert llm.generate.await_count == 2


async def test_missing_support_stops_when_retrieval_adds_nothing(sample_chunks):
    orchestrator = make_orchestrator(sample_chunks, [AnalysisResult(True, "")])
    orchestrator.answer_agent.review.return_value = GroundingVerdict(
        supported=[False],
        qualifications_preserved=[True],
        no_added_details=[False],
        missing_info="Unknown mechanism",
    )
    result = await orchestrator.process("Explain the mechanism")
    assert result["state"] == "insufficient_evidence"
    assert orchestrator.answer_agent.generate.await_count == 1
    assert orchestrator.retriever.retrieve.await_count == 2


@pytest.mark.parametrize(
    "question,expected",
    [
        ("answer in 50 words", (50, True)),
        ("use at most 50 words", (50, False)),
        ("use under 50 words", (49, False)),
        ("what are the 50 words?", None),
    ],
)
def test_explicit_word_requirements(question, expected):
    assert word_requirement(question) == expected


def test_word_count_excludes_citations_and_accepts_hyphenated_words():
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Multi-head attention uses weights.",
                citations=[EvidenceReference(chunk_id="chunk_1", quote="A longer source quote")],
            )
        ]
    )
    validate_length("answer in 4 words", draft)
    with pytest.raises(ValueError, match="has 4 words"):
        validate_length("answer in 5 words", draft)
