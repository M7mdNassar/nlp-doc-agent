from typing import Any

from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.tool import Tool


class TableExtractor(Tool):
    def __init__(self, evidence: EvidencePackage) -> None:
        self.evidence = evidence

    @property
    def name(self) -> str:
        return "table_extractor"

    @property
    def description(self) -> str:
        return "Extracts all tabular data from the retrieved document chunks."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        tables = []
        for chunk in self.evidence.chunks:
            if chunk.text.strip().startswith("|") and "---" in chunk.text:
                tables.append(f"From Page {chunk.page}:\n{chunk.text}")
        if not tables:
            return "No tables found in the retrieved evidence."
        return "\n\n".join(tables)
