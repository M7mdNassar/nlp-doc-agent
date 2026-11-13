from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class ToolRequest(StrictModel):
    name: Literal["calculator", "table_extractor", "document_comparison", "data_analysis"]
    arguments: dict[str, Any]


class AnalysisPlan(StrictModel):
    tools: list[ToolRequest] = Field(default_factory=list, max_length=6)


class FindingQuote(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=3000)


class Finding(StrictModel):
    text: str = Field(min_length=1, max_length=3000)
    chunk_ids: list[str] = Field(default_factory=list, max_length=12)
    quotes: list[FindingQuote] = Field(default_factory=list, max_length=12)
    quote_ids: list[str] = Field(default_factory=list, max_length=12)


class AnalysisVerdict(StrictModel):
    has_enough_evidence: bool
    missing_info: str
    conflict_detected: bool = False
    findings: list[Finding] = Field(default_factory=list, max_length=12)


class AnalysisDecision(AnalysisPlan):
    verdict: AnalysisVerdict | None = None


@dataclass
class ToolResult:
    name: str
    output: dict[str, Any]
    chunk_ids: list[str]


@dataclass
class AnalysisResult:
    has_enough_evidence: bool
    missing_info: str
    conflict_detected: bool = False
    findings: list[Finding] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
