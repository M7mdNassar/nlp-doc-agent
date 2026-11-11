"""Safe diagnostics for untrusted model output, without values or exception messages."""

from typing import Any

from pydantic import ValidationError

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
