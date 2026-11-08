"""Bounded deterministic tools. No eval, generated Python, filesystem, or network access."""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field

from src.domain.entities.analysis import StrictModel, ToolRequest, ToolResult
from src.domain.entities.chunk import Chunk
from src.domain.entities.evidence import EvidencePackage

from .calculator import calculate
from .statistics import summarize

NUMBER = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
MAX_NUMBER = Decimal("1e18")


class NumberSource(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=2000)
    value: str
    label: str = ""


class CalculatorArguments(StrictModel):
    expression: str = Field(min_length=1, max_length=500)
    values: dict[str, NumberSource] = Field(min_length=1, max_length=100)


class TableArguments(StrictModel):
    chunk_id: str


class ComparisonItem(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=2000)
    aspect: str = Field(min_length=1, max_length=100)


class ComparisonArguments(StrictModel):
    items: list[ComparisonItem] = Field(min_length=2, max_length=50)


class DataArguments(StrictModel):
    operation: Literal[
        "sum",
        "mean",
        "median",
        "min",
        "max",
        "difference",
        "percent_change",
        "ratio",
        "stdev",
        "rank",
        "count",
        "distribution",
    ]
    values: list[NumberSource] = Field(default_factory=list, max_length=1000)
    table_chunk_id: str | None = None
    column: str | None = None
    label_column: str | None = None


def normalized(text: str) -> str:
    return " ".join(text.split())


def checked_number(value: str) -> Decimal:
    try:
        number = Decimal(value.replace(",", "").strip().rstrip("%"))
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if not number.is_finite() or abs(number) > MAX_NUMBER:
        raise ValueError("Number outside the supported range")
    return number


class AnalystTools:
    def __init__(self, evidence: EvidencePackage):
        self.chunks = {str(chunk.id): chunk for chunk in evidence.chunks}

    def _chunk(self, chunk_id: str) -> Chunk:
        if chunk_id not in self.chunks:
            raise ValueError(f"Unknown evidence chunk: {chunk_id}")
        return self.chunks[chunk_id]

    def _quote(self, chunk_id: str, quote: str) -> Chunk:
        chunk = self._chunk(chunk_id)
        # Do not accept e.g. "92" as a quote from the number "192".
        exact = normalized(quote)
        left = r"(?<![\w.])" if exact[0].isalnum() else ""
        right = r"(?![\w.])" if exact[-1].isalnum() else ""
        if not re.search(left + re.escape(exact) + right, normalized(chunk.text)):
            raise ValueError("Tool input quote does not occur in the cited evidence")
        return chunk

    def _number(self, source: NumberSource) -> Decimal:
        self._quote(source.chunk_id, source.quote)
        number = checked_number(source.value)
        found = [checked_number(m.group()) for m in NUMBER.finditer(source.quote)]
        if number not in found:
            raise ValueError("Tool input value does not occur in its evidence quote")
        return number

    def execute(self, request: ToolRequest) -> ToolResult:
        if request.name == "calculator":
            return self._calculate(CalculatorArguments.model_validate(request.arguments))
        if request.name == "table_extractor":
            args = TableArguments.model_validate(request.arguments)
            chunk = self._chunk(args.chunk_id)
            if not chunk.table_data:
                raise ValueError("The selected chunk is not a structured table")
            return ToolResult("table_extractor", chunk.table_data, [args.chunk_id])
        if request.name == "document_comparison":
            return self._compare(ComparisonArguments.model_validate(request.arguments))
        return self._analyze(DataArguments.model_validate(request.arguments))

    def _calculate(self, args: CalculatorArguments) -> ToolResult:
        values = {key: self._number(source) for key, source in args.values.items()}
        result = calculate(args.expression, values)
        return ToolResult(
            "calculator",
            {
                "expression": args.expression,
                "inputs": {k: str(v) for k, v in values.items()},
                "result": str(result),
            },
            list(dict.fromkeys(v.chunk_id for v in args.values.values())),
        )

    def _compare(self, args: ComparisonArguments) -> ToolResult:
        rows: list[dict[str, str]] = []
        documents = set()
        for item in args.items:
            chunk = self._quote(item.chunk_id, item.quote)
            documents.add(str(chunk.document_id))
            rows.append(
                {
                    "document_id": str(chunk.document_id),
                    "document_name": chunk.document_name,
                    "aspect": item.aspect,
                    "evidence": item.quote,
                    "chunk_id": item.chunk_id,
                }
            )
        if len(documents) < 2:
            raise ValueError("Document comparison requires evidence from at least two documents")
        return ToolResult(
            "document_comparison",
            {"rows": rows},
            list(dict.fromkeys(item.chunk_id for item in args.items)),
        )

    def _analyze(self, args: DataArguments) -> ToolResult:
        sources = list(args.values)
        if args.table_chunk_id is not None:
            if sources:
                raise ValueError("Choose either quoted values or a table column")
            chunk = self._chunk(args.table_chunk_id)
            if not chunk.table_data or not args.column:
                raise ValueError("A structured table and column are required")
            headers = chunk.table_data["headers"]
            if args.column not in headers:
                raise ValueError("Unknown table column")
            if args.label_column is not None and args.label_column not in headers:
                raise ValueError("Unknown table label column")
            index = headers.index(args.column)
            label_index = headers.index(args.label_column) if args.label_column in headers else None
            for row in chunk.table_data["rows"]:
                cell = str(row[index]).strip()
                # Missing/non-numeric cells cannot silently change the statistical population.
                if not re.fullmatch(
                    r"[$\u20ac\u00a3]?\s*[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?", cell
                ):
                    raise ValueError(f"Non-numeric cell in selected column: {cell!r}")
                raw = cell.lstrip("$\u20ac\u00a3").strip().rstrip("%")
                sources.append(
                    NumberSource(
                        chunk_id=args.table_chunk_id,
                        quote=cell,
                        value=raw,
                        label=str(row[label_index]) if label_index is not None else "",
                    )
                )
        if not sources or len(sources) > 1000:
            raise ValueError("Data analysis requires between 1 and 1000 evidence values")
        values = [self._number(source) for source in sources]
        value = summarize(
            args.operation,
            values,
            [{"label": source.label, "chunk_id": source.chunk_id} for source in sources],
        )
        output = {
            "operation": args.operation,
            "count": len(values),
            "result": str(value) if isinstance(value, Decimal) else value,
        }
        return ToolResult(
            "data_analysis", output, list(dict.fromkeys(source.chunk_id for source in sources))
        )
