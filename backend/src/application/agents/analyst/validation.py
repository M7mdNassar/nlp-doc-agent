"""Safe diagnostics for untrusted model output, without values or exception messages."""

from typing import Any

from pydantic import ValidationError

from src.application.agents.source_texts import SourceExcerpts, SourceTexts
from src.application.citations.verifier import normalized
from src.domain.entities.analysis import AnalysisVerdict, FindingQuote
from src.domain.entities.evidence import EvidencePackage

# Only application-defined field names may appear in log paths. Extra keys and
# dynamic calculator-variable names can contain private/model-generated text.
SAFE_FIELDS = frozenset(
    [
        "tools",
        "name",
        "arguments",
        "has_enough_evidence",
        "missing_info",
        "conflict_detected",
        "findings",
        "text",
        "chunk_ids",
        "quotes",
        "quote_ids",
        "verdict",
        "expression",
        "values",
        "chunk_id",
        "quote",
        "value",
        "label",
        "items",
        "aspect",
        "operation",
        "table_chunk_id",
        "column",
        "label_column",
    ]
)


class AnalysisGroundingError(ValueError):
    def __init__(self, check: str, field: str):
        super().__init__(check)
        self.check = check
        self.field = field


def _resolve_references(verdict: AnalysisVerdict, evidence: EvidencePackage) -> None:
    references = SourceExcerpts(evidence, SourceTexts()).references
    for finding in verdict.findings:
        if finding.quote_ids:
            if any(quote_id not in references for quote_id in finding.quote_ids):
                raise AnalysisGroundingError("unknown_quote_reference", "findings.quote_ids")
            resolved = [references[quote_id] for quote_id in finding.quote_ids]
            resolved_ids = list(dict.fromkeys(ref.chunk_id for ref in resolved))
            if finding.chunk_ids and set(finding.chunk_ids) != set(resolved_ids):
                raise AnalysisGroundingError("mismatched_quote_references", "findings.chunk_ids")
            finding.chunk_ids = resolved_ids
            finding.quotes = [
                FindingQuote(chunk_id=ref.chunk_id, quote=ref.quote) for ref in resolved
            ]
        if not finding.chunk_ids:
            raise AnalysisGroundingError("missing_supporting_quotes", "findings.quotes")


def validate_grounding(verdict: AnalysisVerdict, evidence: EvidencePackage) -> AnalysisVerdict:
    chunks = {str(chunk.id): chunk for chunk in evidence.chunks}
    _resolve_references(verdict, evidence)
    if any(not set(f.chunk_ids) <= chunks.keys() for f in verdict.findings):
        raise AnalysisGroundingError("unknown_chunk_reference", "findings.chunk_ids")
    if verdict.has_enough_evidence and not verdict.findings:
        raise AnalysisGroundingError("missing_grounded_findings", "findings")
    for finding in verdict.findings:
        # Older extractive responses can use their verbatim finding as the quote.
        if not finding.quotes:
            finding.quotes = [
                FindingQuote(chunk_id=chunk_id, quote=finding.text)
                for chunk_id in finding.chunk_ids
                if normalized(finding.text) in normalized(chunks[chunk_id].text)
            ]
        if {quote.chunk_id for quote in finding.quotes} != set(finding.chunk_ids):
            raise AnalysisGroundingError("missing_supporting_quotes", "findings.quotes")
        if any(
            normalized(quote.quote) not in normalized(chunks[quote.chunk_id].text)
            for quote in finding.quotes
        ):
            raise AnalysisGroundingError("quote_not_in_source", "findings.quotes")
    return verdict


def validation_details(exc: ValueError) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        issues = []
        for error in errors[:8]:
            path = [
                str(part) if isinstance(part, int) or part in SAFE_FIELDS else "<redacted>"
                for part in error["loc"][:8]
            ]
            issues.append({"field": ".".join(path) or "$", "type": error["type"]})
        return {
            "category": "json" if any(e["type"] == "json_invalid" for e in errors) else "schema",
            "issues": issues,
            "error_count": len(errors),
        }
    if isinstance(exc, AnalysisGroundingError):
        return {"category": "grounding", "check": exc.check, "field": exc.field}
    # Deterministic tools raise ValueError for invalid/ungrounded arguments. Their
    # exception strings may include source text, IDs, expressions or field values.
    return {"category": "tool_validation", "check": "invalid_tool_arguments_or_evidence"}
