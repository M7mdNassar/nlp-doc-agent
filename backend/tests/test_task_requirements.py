import json
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from docx import Document as WordDocument
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.retriever.context_selector import ContextSelector
from src.application.agents.retriever.metadata_filter import MetadataFilterResolver
from src.application.ingestion.chunker import Chunker
from src.application.ingestion.cleaner import clean_elements
from src.application.tools.analyst_tools import AnalystTools
from src.application.tools.calculator import calculate
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.domain.entities.analysis import ToolRequest
from src.domain.entities.chunk import Chunk
from src.domain.entities.conversation import Conversation
from src.domain.entities.document import Document
from src.domain.entities.evidence import EvidencePackage
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.metadata_filters import MetadataFilters
from src.domain.value_objects.parsed_element import ParsedElement
from src.infrastructure.parsers.factory import parser_factory


def passage(value, document=None):
    return Chunk(
        ChunkId.generate(),
        document or DocumentId.generate(),
        f"Model accuracy is {value}%.",
        1,
        document_name="paper.pdf",
    )


def number_source(chunk, value):
    return {"chunk_id": str(chunk.id), "quote": chunk.text, "value": str(value)}


async def test_docx_extracts_headings_tables_and_provenance(tmp_path):
    document = WordDocument()
    document.core_properties.author = "Ada"
    document.add_heading("Chapter 4 Results", 1)
    document.add_paragraph("Accuracy results.")
    table = document.add_table(rows=3, cols=2)
    for row, values in zip(
        table.rows, [("Model", "Accuracy"), ("A", "92"), ("B", "95")], strict=True
    ):
        for cell, value in zip(row.cells, values, strict=True):
            cell.text = value
    path = tmp_path / "research.docx"
    document.save(path)
    elements = await parser_factory.get_parser("docx").parse(path)
    extracted = next(e for e in elements if e.is_table)
    assert extracted.table_data["headers"] == ["Model", "Accuracy"]
    assert extracted.table_data["rows"] == [["A", "92"], ["B", "95"]]
    assert extracted.chapter == "4"
    assert extracted.section == "Chapter 4 Results"
    assert extracted.author == "Ada"
    assert extracted.location == "block 3"
    chunk = next(c for c in Chunker().chunk(DocumentId.generate(), elements) if c.table_data)
    assert chunk.table_data == extracted.table_data


def write_pdf(path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"""BT /F1 12 Tf 50 740 Td (Chapter 4 Results) Tj ET
BT /F1 12 Tf 50 710 Td (This study compares model accuracy.) Tj ET
50 600 m 300 600 l S 50 630 m 300 630 l S 50 660 m 300 660 l S
50 600 m 50 660 l S 175 600 m 175 660 l S 300 600 m 300 660 l S
BT /F1 12 Tf 60 640 Td (Model) Tj ET
BT /F1 12 Tf 185 640 Td (Accuracy) Tj ET
BT /F1 12 Tf 60 610 Td (A) Tj ET
BT /F1 12 Tf 185 610 Td (92) Tj ET""")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


async def test_real_pdf_extracts_structured_table_without_duplicate_body(tmp_path):
    path = tmp_path / "table.pdf"
    write_pdf(path)
    elements = await parser_factory.get_parser("pdf").parse(path)
    table = next(e for e in elements if e.is_table)
    assert table.page == 1
    assert table.chapter == "4"
    assert table.table_data["rows"] == [["A", "92"]]
    assert len(table.table_data["bbox"]) == 4
    assert "92" not in "\n".join(e.text for e in elements if not e.is_table)


def test_cleaning_removes_boilerplate_and_repairs_hyphenation():
    elements = [
        ParsedElement(f"Repeated header\nPage {i} has docu-\nments.\nRepeated footer", i)
        for i in range(1, 4)
    ]
    cleaned = clean_elements(elements)
    assert len(cleaned) == 3
    assert all("documents." in e.text and "Repeated" not in e.text for e in cleaned)


def test_chunking_respects_tokenizer_limit_and_handles_long_unbroken_text():
    chunks = Chunker(chunk_size=10, overlap=2, count_tokens=len).chunk(
        DocumentId.generate(), [ParsedElement("a" * 35, 1)]
    )
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 10 for chunk in chunks)
    assert chunks[-1].text.endswith("a")


def test_context_selector_deduplicates_and_keeps_document_coverage_within_budget():
    first = passage(92)
    duplicate = replace(first, id=ChunkId.generate())
    other = passage(95)
    selector = ContextSelector(len, max_tokens=200, max_chunks=3)
    selected = selector.select([first, duplicate, other])
    assert len(selected) == 2
    assert {c.document_id for c in selected} == {first.document_id, other.document_id}
    assert ContextSelector(len, max_tokens=1).select([first]) == []


def test_context_selector_preserves_a_small_but_material_source_difference():
    first = passage(92)
    first.text = "The traffic project improved measured vehicle throughput using the adaptive traffic signal recommendations based on real drone observations during simulation."
    different = replace(
        first, id=ChunkId.generate(), text=first.text.replace("simulation", "deployment")
    )
    assert len(ContextSelector(len, max_tokens=2000).select([first, different])) == 2


def test_natural_metadata_constraints_and_unknown_files_do_not_widen_search():
    doc = Document(DocumentId.generate(), "paper.pdf", "pdf", "sum")
    resolved = MetadataFilterResolver().resolve(
        "According to Chapter 4 of paper.pdf, page 2?", [doc]
    )
    assert resolved.doc_ids == [str(doc.id)]
    assert resolved.chapter == "4" and resolved.page == 2
    unknown = MetadataFilterResolver().resolve("According to missing.pdf?", [doc])
    assert unknown.doc_ids == []
    explicit = MetadataFilters(page=8)
    assert MetadataFilterResolver().resolve("page 2 of paper.pdf", [doc], explicit).page == 8


def test_calculator_uses_evidence_values_and_returns_exact_average():
    chunks = [passage(n) for n in (92, 95, 89)]
    values = {
        letter: number_source(chunk, n)
        for letter, chunk, n in zip("abc", chunks, (92, 95, 89), strict=True)
    }
    result = AnalystTools(EvidencePackage(chunks=chunks)).execute(
        ToolRequest(name="calculator", arguments={"expression": "(a+b+c)/3", "values": values})
    )
    assert result.output["result"] == "92"
    assert set(result.chunk_ids) == {str(c.id) for c in chunks}


@pytest.mark.parametrize(
    "expression", ["__import__('os').system('x')", "a.__class__", "a**100", "a/0", "999"]
)
def test_calculator_rejects_code_and_unsafe_expressions(expression):
    with pytest.raises((ValueError, SyntaxError)):
        calculate(expression, {"a": Decimal(92)})


def test_tool_rejects_invented_value():
    chunk = passage(92)
    with pytest.raises(ValueError, match="value"):
        AnalystTools(EvidencePackage(chunks=[chunk])).execute(
            ToolRequest(
                name="calculator",
                arguments={"expression": "a+1", "values": {"a": number_source(chunk, 999)}},
            )
        )


def test_tool_rejects_a_number_cut_out_of_a_larger_number():
    chunk = passage(192)
    with pytest.raises(ValueError, match="quote"):
        AnalystTools(EvidencePackage(chunks=[chunk])).execute(
            ToolRequest(
                name="calculator",
                arguments={
                    "expression": "a+1",
                    "values": {"a": {"chunk_id": str(chunk.id), "quote": "92", "value": "92"}},
                },
            )
        )


def table_chunk():
    return Chunk(
        ChunkId.generate(),
        DocumentId.generate(),
        "| Model | Accuracy |\n| --- | --- |\n| A | 92 |\n| B | 95 |",
        2,
        document_name="table.pdf",
        table_data={"headers": ["Model", "Accuracy"], "rows": [["A", "92"], ["B", "95"]]},
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("mean", "93.5"), ("difference", "3"), ("sum", "187"), ("median", "93.5")],
)
def test_structured_table_analysis(operation, expected):
    chunk = table_chunk()
    tools = AnalystTools(EvidencePackage.from_chunks([chunk]))
    table = tools.execute(
        ToolRequest(name="table_extractor", arguments={"chunk_id": str(chunk.id)})
    )
    assert table.output["headers"] == ["Model", "Accuracy"]
    result = tools.execute(
        ToolRequest(
            name="data_analysis",
            arguments={
                "operation": operation,
                "table_chunk_id": str(chunk.id),
                "column": "Accuracy",
            },
        )
    )
    assert result.output["result"] == expected


def test_document_comparison_organizes_cited_facts_across_documents():
    chunks = [passage(92), passage(95)]
    result = AnalystTools(EvidencePackage(chunks=chunks)).execute(
        ToolRequest(
            name="document_comparison",
            arguments={
                "items": [
                    {"chunk_id": str(c.id), "quote": c.text, "aspect": "accuracy"} for c in chunks
                ]
            },
        )
    )
    assert len(result.output["rows"]) == 2
    assert len({row["document_id"] for row in result.output["rows"]}) == 2


async def test_analyst_executes_tools_and_passes_results_to_verdict():
    chunk = table_chunk()
    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                json.dumps(
                    {
                        "tools": [
                            {
                                "name": "data_analysis",
                                "arguments": {
                                    "operation": "mean",
                                    "table_chunk_id": str(chunk.id),
                                    "column": "Accuracy",
                                },
                            }
                        ]
                    }
                ),
                json.dumps(
                    {
                        "has_enough_evidence": True,
                        "missing_info": "",
                        "findings": [
                            {"text": "Average accuracy is 93.5%.", "chunk_ids": [str(chunk.id)]}
                        ],
                    }
                ),
            ]
        )
    )
    result = await AnalystAgent(llm).analyze(
        "Average accuracy?", EvidencePackage.from_chunks([chunk])
    )
    assert result.has_enough_evidence
    assert result.tool_results[0].output["result"] == "93.5"
    assert "93.5" in llm.generate.await_args.args[0]


async def test_analyst_shared_text_preserves_multiple_source_identities():
    first = passage(92)
    second = replace(first, id=ChunkId.generate(), document_id=DocumentId.generate())
    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                '{"tools":[]}',
                json.dumps(
                    {
                        "has_enough_evidence": True,
                        "missing_info": "",
                        "findings": [
                            {
                                "text": "Both report 92%.",
                                "chunk_ids": [str(first.id), str(second.id)],
                            }
                        ],
                    }
                ),
            ]
        )
    )
    result = await AnalystAgent(llm).analyze("Compare", EvidencePackage(chunks=[first, second]))
    assert result.has_enough_evidence
    payload = json.loads(llm.generate.await_args_list[0].args[0])
    assert len(payload["texts"]) == 1
    assert {item["document_id"] for item in payload["evidence"]} == {
        str(first.document_id),
        str(second.document_id),
    }
    for item in payload["evidence"]:
        assert payload["texts"][item["text_id"]] == first.text


@pytest.mark.parametrize("bad", ['"false"', '"true"', "1", "null"])
async def test_analyst_rejects_non_boolean_verdicts(bad):
    from src.core.errors import AnalysisOutputError

    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                '{"tools":[]}',
                '{"has_enough_evidence":' + bad + ',"missing_info":"missing"}',
                '{"has_enough_evidence":' + bad + ',"missing_info":"missing"}',
            ]
        )
    )
    with pytest.raises(AnalysisOutputError):
        await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=[passage(92)]))
    assert llm.generate.await_count == 3


async def test_chat_uses_saved_history_filters_and_persists_new_turn():
    conversation = Conversation.create("local")
    conversation.add_message("user", "What is RAG?")
    conversation.add_message("assistant", "Retrieval augmented generation.")
    repository = SimpleNamespace(get=AsyncMock(return_value=conversation), save=AsyncMock())
    document = Document(DocumentId.generate(), "paper.pdf", "pdf", "sum")
    documents = SimpleNamespace(list_all=AsyncMock(return_value=[document]))
    orchestrator = SimpleNamespace(
        process=AsyncMock(
            return_value={
                "answer": "A grounded answer",
                "state": "answer_ready",
                "loops": 0,
                "evidence_count": 1,
                "sources": [],
                "tool_results": [],
                "conversation_id": "",
            }
        )
    )
    result = await AskQuestionUseCase(orchestrator, repository, documents).execute(
        "What are its disadvantages in paper.pdf?", conversation.id, MetadataFilters(page=4)
    )
    args = orchestrator.process.await_args.args
    assert args[1]["page"] == 4 and args[1]["doc_ids"] == [str(document.id)]
    assert "What is RAG?" in args[2][0]
    assert result["conversation_id"] == conversation.id
    assert len(conversation.messages) == 4
    repository.save.assert_awaited_once()
