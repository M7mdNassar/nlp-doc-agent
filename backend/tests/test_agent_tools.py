import json
import math
import random
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.source_texts import SourceExcerpts, SourceTexts
from src.application.tools.analyst_tools import AnalystTools
from src.core.errors import AnalysisOutputError
from src.core.observability import question_scope
from src.core.progress import progress_scope
from src.domain.entities.analysis import ToolRequest
from src.domain.entities.chunk import Chunk
from src.domain.entities.evidence import EvidencePackage
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId


def chunk(text, doc="doc_synthetic_a", table=None):
    return Chunk(
        ChunkId.generate(), DocumentId(doc), text, 1, document_name=doc + ".pdf", table_data=table
    )


def number(c, value, quote=None, label=""):
    return {
        "chunk_id": str(c.id),
        "quote": c.text if quote is None else quote,
        "value": str(value),
        "label": label,
    }


def run_calc(text, expression, value, quote=None):
    c = chunk(text)
    return AnalystTools(EvidencePackage.from_chunks([c])).execute(
        ToolRequest(
            name="calculator",
            arguments={"expression": expression, "values": {"a": number(c, value, quote)}},
        )
    )


@pytest.mark.parametrize(
    "expression,value,expected",
    [
        ("a", "18.6", "18.6"),
        ("a*2", "18.6", "37.2"),
        ("a/2", "18.6", "9.3"),
        ("a+0.2", "0.1", "0.3"),
        ("-a", "18.6", "-18.6"),
        ("+a", "18.6", "18.6"),
        ("(a+2)*3", "4", "18"),
        ("a**8", "2", "256"),
        ("a**-2", "2", "0.25"),
        ("a**0", "2", "1"),
        ("a*-2", "-2.5", "5"),
        ("a/100", "92%", "0.92"),
        ("a+1", "1,234", "1235"),
        ("a*2", "1e-3", "0.002"),
        ("a*2", "-1e-3", "-0.002"),
        ("a*2", "1e3", "2000"),
    ],
)
def test_calculator_valid_arithmetic(expression, value, expected):
    result = run_calc("Observed value: " + value + ".", expression, value)
    assert Decimal(result.output["result"]) == Decimal(expected)
    assert len(result.chunk_ids) == 1


@pytest.mark.parametrize(
    "expression",
    [
        "a+",
        "a/0",
        "a**9",
        "a**-9",
        "a**0.5",
        "a//2",
        "a%2",
        "a<<2",
        "a&2",
        "a.__class__",
        "a[0]",
        "abs(a)",
        '__import__("os")',
        "(lambda: a)()",
        "[a for x in [1]]",
        '{"x":a}',
        "[a]",
        "(a,)",
        "True+a",
        '"1"+a',
        "b+1",
        "999",
        "(a:=1)",
        "a if a else 0",
        "not a",
        "+" * 101 + "a",
    ],
)
def test_calculator_rejects_unsafe_or_undefined_expression(expression):
    with pytest.raises(ValueError):
        run_calc("Value is 2.", expression, "2")


@pytest.mark.parametrize(
    "text,quote,value",
    [
        ("Value is 192.", "92", "92"),
        ("Value is 18.60.", "18.6", "18.6"),
        ("Value is 18.6.", "6", "6"),
        ("Value is 1e3.", "1", "1"),
        ("Value is 18.6.", "999", "999"),
        ("Value is 18.6.", "18.6", "999"),
        ("Value is -18.6.", "18.6", "18.6"),
        ("Value is -12%.", "12%", "12"),
        ("Value is 1e-3.", "3", "3"),
        ("Value is 1,234.", "1", "1"),
        ("Value is 1,234.", "234", "234"),
        ("Value is \u221218.6.", "18.6", "18.6"),
    ],
)
def test_numeric_fragment_cannot_change_the_source_number(text, quote, value):
    with pytest.raises(ValueError):
        run_calc(text, "a", value, quote)


@pytest.mark.parametrize(
    "value",
    [
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        "1e19",
        "1e1000000",
        "1000000000000000000.0000000000000001",
    ],
)
def test_out_of_range_input_is_a_handled_validation_error(value):
    with pytest.raises(ValueError):
        run_calc("Value is " + value + ".", "a", value)


def test_nonzero_identity_multiplication_must_not_silently_underflow_to_zero():
    value = "1e-10000000"
    try:
        result = run_calc("Value is " + value + ".", "a*1", value)
    except ValueError:
        return  # Rejecting an unsupported number range is safe.
    assert Decimal(result.output["result"]) != 0


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"a": {}},
        {"a": {"chunk_id": "missing", "quote": "2", "value": "2"}},
        {"a": {"chunk_id": "missing", "quote": " ", "value": "2"}},
        {"a": {"chunk_id": "missing", "quote": "2", "value": 2}},
    ],
)
def test_invalid_calculator_schema_and_unknown_sources_are_rejected(invalid):
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage()).execute(
            ToolRequest(name="calculator", arguments={"expression": "a", "values": invalid})
        )


def table(data=None):
    data = (
        data
        if data is not None
        else {
            "headers": ["Class", "Recall"],
            "rows": [["Alpha", "0.8"], ["Beta", "0.6"], ["Gamma", "0.7"]],
        }
    )
    return chunk(
        "| Class | Recall |\n| --- | --- |\n| Alpha | 0.8 |\n| Beta | 0.6 |\n| Gamma | 0.7 |",
        table=data,
    )


@pytest.mark.parametrize("mode", ["chunk_id", "quote_id", "layout"])
def test_table_extractor_preserves_grid_or_layout_and_provenance(mode):
    c = table()
    if mode == "layout":
        c.text = "Model     Value\nA         0.8\nB         \n"
        c.table_data = {
            "format": "layout",
            "text": c.text,
            "headers": [],
            "rows": [],
            "bbox": [1, 2, 3, 4],
        }
    evidence = EvidencePackage.from_chunks([c])
    excerpts = SourceExcerpts(evidence, SourceTexts())
    args = {"quote_id": "quote_1"} if mode == "quote_id" else {"chunk_id": str(c.id)}
    result = AnalystTools(evidence, excerpts.references).execute(
        ToolRequest(name="table_extractor", arguments=args)
    )
    assert result.output == c.table_data
    assert result.chunk_ids == [str(c.id)]


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"quote_id": "missing"},
        {"chunk_id": "missing"},
        {"quote_id": "quote_1", "chunk_id": "x"},
        {"chunk_id": "x", "url": "https://invalid.example"},
    ],
)
def test_table_reference_validation(args):
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage()).execute(ToolRequest(name="table_extractor", arguments=args))


def test_prose_cannot_be_claimed_as_a_table():
    c = chunk("Accuracy is 0.8. This is prose, not a structured table.")
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage.from_chunks([c])).execute(
            ToolRequest(name="table_extractor", arguments={"chunk_id": str(c.id)})
        )


OPERATIONS = [
    "sum",
    "mean",
    "median",
    "min",
    "max",
    "stdev",
    "rank",
    "count",
    "distribution",
    "difference",
    "ratio",
    "percent_change",
]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("seed", range(40))
def test_data_analysis_against_independent_numeric_oracle(operation, seed):
    rng = random.Random(seed)
    count = 2 if operation in {"difference", "ratio", "percent_change"} else rng.randrange(1, 20)
    values = [Decimal(rng.randrange(-9999, 10000)) / 10 for _ in range(count)]
    if values[0] == 0:
        values[0] = Decimal("1.1")
    chunks = [chunk("Observed value: " + str(v) + ".") for v in values]
    inputs = [
        number(c, v, label="item " + str(i))
        for i, (c, v) in enumerate(zip(chunks, values, strict=True))
    ]
    result = AnalystTools(EvidencePackage.from_chunks(chunks)).execute(
        ToolRequest(name="data_analysis", arguments={"operation": operation, "values": inputs})
    )
    actual = result.output["result"]
    fractions = list(map(Fraction, values))
    ordered = sorted(fractions)
    expected = {
        "sum": sum(fractions),
        "mean": sum(fractions) / count,
        "min": min(fractions),
        "max": max(fractions),
        "median": ordered[count // 2]
        if count % 2
        else (ordered[count // 2 - 1] + ordered[count // 2]) / 2,
    }
    if operation in expected:
        v = expected[operation]
        assert Decimal(actual) == Decimal(v.numerator) / Decimal(v.denominator)
    elif operation == "difference":
        assert Decimal(actual) == values[1] - values[0]
    elif operation == "ratio":
        assert Decimal(actual) == values[1] / values[0]
    elif operation == "percent_change":
        assert Decimal(actual) == (values[1] - values[0]) / abs(values[0]) * 100
    elif operation == "stdev":
        mean = sum(fractions) / count
        variance = sum((v - mean) ** 2 for v in fractions) / count
        assert math.isclose(float(actual), math.sqrt(float(variance)), abs_tol=1e-10)
    elif operation == "count":
        assert actual == count
    elif operation == "distribution":
        assert {Decimal(k): v for k, v in actual.items()} == dict(Counter(values))
    else:
        expected_indices = sorted(range(count), key=lambda i: values[i], reverse=True)
        assert [(row["label"], Decimal(row["value"]), row["chunk_id"]) for row in actual] == [
            ("item " + str(i), values[i], str(chunks[i].id)) for i in expected_indices
        ]
    assert result.output["count"] == count
    assert result.chunk_ids == [str(c.id) for c in chunks]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_each_statistical_operation_accepts_a_valid_numeric_table_column(operation):
    c = table()
    if operation in {"difference", "ratio", "percent_change"}:
        c.table_data["rows"] = c.table_data["rows"][:2]
    result = AnalystTools(EvidencePackage.from_chunks([c])).execute(
        ToolRequest(
            name="data_analysis",
            arguments={
                "operation": operation,
                "table_chunk_id": str(c.id),
                "column": "Recall",
                "label_column": "Class",
            },
        )
    )
    assert result.output["count"] == len(c.table_data["rows"])
    assert result.chunk_ids == [str(c.id)]


@pytest.mark.parametrize(
    "cell", ["", "N/A", "not reported", "\u2014", "18.6 ms", "1-2", "NaN", "Infinity"]
)
def test_statistics_does_not_drop_or_guess_non_numeric_cells(cell):
    c = table({"headers": ["Class", "Recall"], "rows": [["Alpha", "0.8"], ["Beta", cell]]})
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage.from_chunks([c])).execute(
            ToolRequest(
                name="data_analysis",
                arguments={"operation": "mean", "table_chunk_id": str(c.id), "column": "Recall"},
            )
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"rows": [["Alpha", "0.8"]]},
        {"headers": ["Class", "Recall"]},
        {"headers": ["Class", "Recall"], "rows": [["Alpha"]]},
        {"format": "layout", "text": "Alpha  0.8"},
    ],
)
def test_malformed_table_shape_is_a_handled_validation_error(metadata):
    c = table(metadata)
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage.from_chunks([c])).execute(
            ToolRequest(
                name="data_analysis",
                arguments={"operation": "mean", "table_chunk_id": str(c.id), "column": "Recall"},
            )
        )


@pytest.mark.parametrize("column,label", [("Score", None), ("Recall", "Class")])
def test_ambiguous_selected_column_names_are_rejected(column, label):
    data = {"headers": ["Class", "Score", "Score"], "rows": [["Alpha", "0.8", "0.6"]]}
    if label:
        data = {"headers": ["Class", "Class", "Recall"], "rows": [["Alpha", "Beta", "0.8"]]}
    c = table(data)
    c.text = "| " + " | ".join(data["headers"]) + " |\n| " + " | ".join(data["rows"][0]) + " |"
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage.from_chunks([c])).execute(
            ToolRequest(
                name="data_analysis",
                arguments={
                    "operation": "rank",
                    "table_chunk_id": str(c.id),
                    "column": column,
                    "label_column": label,
                },
            )
        )


@pytest.mark.parametrize(
    "operation,values",
    [
        ("ratio", [0, 2]),
        ("percent_change", [0, 2]),
        ("difference", [1]),
        ("ratio", [1, 2, 3]),
        ("sum", []),
        ("median", []),
        ("stdev", []),
    ],
)
def test_invalid_statistical_populations_are_rejected(operation, values):
    chunks = [chunk("Value is " + str(v) + ".") for v in values]
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage.from_chunks(chunks)).execute(
            ToolRequest(
                name="data_analysis",
                arguments={
                    "operation": operation,
                    "values": [number(c, v) for c, v in zip(chunks, values, strict=True)],
                },
            )
        )


@pytest.mark.parametrize(
    "problem", ["same_document", "invented_quote", "unknown_chunk", "too_few_items"]
)
def test_document_comparison_rejects_invalid_sources(problem):
    a, b = chunk("Model A accuracy is 0.9."), chunk("Model B accuracy is 0.8.", "doc_synthetic_b")
    if problem == "same_document":
        b.document_id = a.document_id
    items = [{"chunk_id": str(c.id), "quote": c.text, "aspect": "accuracy"} for c in [a, b]]
    if problem == "invented_quote":
        items[1]["quote"] = "Invented evidence"
    if problem == "unknown_chunk":
        items[1]["chunk_id"] = "missing"
    if problem == "too_few_items":
        items = items[:1]
    with pytest.raises(ValueError):
        AnalystTools(EvidencePackage.from_chunks([a, b])).execute(
            ToolRequest(name="document_comparison", arguments={"items": items})
        )


def test_comparison_preserves_conflicting_values_and_both_document_identities():
    a, b = chunk("Model accuracy is 0.9."), chunk("Model accuracy is 0.8.", "doc_synthetic_b")
    result = AnalystTools(EvidencePackage.from_chunks([a, b])).execute(
        ToolRequest(
            name="document_comparison",
            arguments={
                "items": [
                    {"chunk_id": str(c.id), "quote": c.text, "aspect": "accuracy"} for c in [a, b]
                ]
            },
        )
    )
    assert [r["evidence"] for r in result.output["rows"]] == [a.text, b.text]
    assert len({r["document_id"] for r in result.output["rows"]}) == 2


@pytest.mark.parametrize(
    "tool_name", ["calculator", "table_extractor", "document_comparison", "data_analysis"]
)
async def test_analyst_executes_tool_and_passes_real_result_to_verdict(tool_name):
    a, b, t = (
        chunk("Median latency is 18.6 ms."),
        chunk("Median latency is 2.8 ms.", "doc_synthetic_b"),
        table(),
    )
    evidence = EvidencePackage.from_chunks([a, b, t])
    arguments = {
        "calculator": {
            "expression": "a-b",
            "values": {"a": number(a, "18.6"), "b": number(b, "2.8")},
        },
        "table_extractor": {"quote_id": "quote_3"},
        "document_comparison": {
            "items": [{"chunk_id": str(c.id), "quote": c.text, "aspect": "latency"} for c in [a, b]]
        },
        "data_analysis": {"operation": "mean", "table_chunk_id": str(t.id), "column": "Recall"},
    }[tool_name]
    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                json.dumps(
                    {"tools": [{"name": tool_name, "arguments": arguments}], "verdict": None}
                ),
                json.dumps(
                    {
                        "has_enough_evidence": True,
                        "missing_info": "",
                        "findings": [
                            {
                                "text": "Source-backed result.",
                                "quote_ids": ["quote_1", "quote_2", "quote_3"],
                            }
                        ],
                    }
                ),
            ]
        )
    )
    with question_scope() as trace, progress_scope() as progress:
        result = await AnalystAgent(llm).analyze(
            "Use " + tool_name + " on the supplied evidence.", evidence
        )
    assert result.has_enough_evidence and len(result.tool_results) == 1
    assert result.tool_results[0].name == tool_name
    passed = json.loads(llm.generate.await_args.args[0].split("Executed tool results:\n")[1])
    assert passed[0]["name"] == tool_name
    assert passed[0]["output"] == result.tool_results[0].output
    assert progress.tools()[0]["name"] == tool_name
    assert progress.tools()[0]["completed"] == 1 and progress.tools()[0]["failed"] == 0
    assert any(s["stage"] == "analyst_tool" for s in trace.stages)


async def test_bad_table_plan_uses_one_correction_and_records_failed_then_successful_call():
    t = table()

    def plan(args):
        return json.dumps({"tools": [{"name": "table_extractor", "arguments": args}]})

    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                plan({"quote_id": "missing"}),
                plan({"quote_id": "quote_1"}),
                json.dumps(
                    {
                        "has_enough_evidence": True,
                        "missing_info": "",
                        "findings": [{"text": "Table result.", "quote_ids": ["quote_1"]}],
                    }
                ),
            ]
        )
    )
    with progress_scope() as progress:
        result = await AnalystAgent(llm).analyze(
            "Extract the table.", EvidencePackage.from_chunks([t])
        )
    assert result.has_enough_evidence and llm.generate.await_count == 3
    tool = progress.tools()[0]
    assert tool["calls"] == 2 and tool["failed"] == 1 and tool["completed"] == 1


async def test_invalid_tools_exhaust_correction_instead_of_authorizing_generation():
    t = table()
    invalid = json.dumps(
        {"tools": [{"name": "table_extractor", "arguments": {"quote_id": "missing"}}]}
    )
    llm = SimpleNamespace(generate=AsyncMock(return_value=invalid))
    with pytest.raises(AnalysisOutputError):
        await AnalystAgent(llm).analyze("Extract the table.", EvidencePackage.from_chunks([t]))
    assert llm.generate.await_count == 2


@pytest.mark.parametrize(
    "text,quote,value,expected",
    [
        ("Change is \u221218.6 ms.", "\u221218.6 ms", "-18.6", "-37.2"),
        ("Value is \u22121.2e\u22123.", "\u22121.2e\u22123", "-0.0012", "-0.0024"),
        ("Values are -18.6 and 18.6.", "18.6", "18.6", "37.2"),
        ("Counts are 1,234 and 234.", "234", "234", "468"),
        ("Median is\t18.6  ms.", "18.6 ms", "18.6", "37.2"),
    ],
)
def test_complete_numeric_quotes_remain_valid(text, quote, value, expected):
    assert Decimal(run_calc(text, "a*2", value, quote).output["result"]) == Decimal(expected)


@pytest.mark.parametrize(
    "cell,value", [("\u22120.8", "-0.8"), ("1e-3", "0.001"), ("$ 1,234", "1234")]
)
def test_numeric_table_formats_keep_source_values(cell, value):
    c = table({"headers": ["Class", "Recall"], "rows": [["Alpha", cell]]})
    c.text = "| Class | Recall |\n| Alpha | " + cell + " |"
    result = AnalystTools(EvidencePackage.from_chunks([c])).execute(
        ToolRequest(
            name="data_analysis",
            arguments={"operation": "mean", "table_chunk_id": str(c.id), "column": "Recall"},
        )
    )
    assert Decimal(result.output["result"]) == Decimal(value)


def test_duplicate_unselected_headers_do_not_block_a_unique_column():
    c = table(
        {"headers": ["Class", "Score", "Score", "Recall"], "rows": [["Alpha", "1", "2", "0.8"]]}
    )
    c.text = "| Class | Score | Score | Recall |\n| Alpha | 1 | 2 | 0.8 |"
    result = AnalystTools(EvidencePackage.from_chunks([c])).execute(
        ToolRequest(
            name="data_analysis",
            arguments={
                "operation": "mean",
                "table_chunk_id": str(c.id),
                "column": "Recall",
                "label_column": "Class",
            },
        )
    )
    assert Decimal(result.output["result"]) == Decimal("0.8")


@pytest.mark.parametrize("data", ["corrupt", ["corrupt"], {"headers": [1], "rows": []}])
def test_invalid_table_container_types_raise_validation_errors(data):
    with pytest.raises(ValueError):
        EvidencePackage.from_chunks([table(data)])
