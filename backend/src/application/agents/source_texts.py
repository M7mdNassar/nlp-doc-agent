from dataclasses import asdict
from typing import Any

from src.domain.entities.analysis import ToolResult
from src.domain.entities.answer import EvidenceReference
from src.domain.entities.evidence import EvidencePackage


class SourceTexts:
    """Share identical strings without merging document identities or rewriting evidence."""

    def __init__(self) -> None:
        self.texts: dict[str, str] = {}
        self._ids: dict[str, str] = {}

    def add(self, text: str) -> str:
        if text not in self._ids:
            text_id = f"text_{len(self.texts) + 1}"
            self._ids[text] = text_id
            self.texts[text_id] = text
        return self._ids[text]

    def tool_results(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        """Share layout text already present in evidence instead of sending it twice."""
        encoded = []
        for result in results:
            item = asdict(result)
            output = item["output"]
            if output.get("format") == "layout" and isinstance(output.get("text"), str):
                text = output.pop("text")
                output["text_ids"] = [
                    self.add(text[offset : offset + 2000]) for offset in range(0, len(text), 2000)
                ]
            encoded.append(item)
        return encoded


class SourceExcerpts:
    """Assign short references to exact source spans before requesting model output."""

    def __init__(self, evidence: EvidencePackage, texts: SourceTexts):
        self.references: dict[str, EvidenceReference] = {}
        self.by_chunk: dict[str, list[dict[str, str]]] = {}
        for chunk in evidence.chunks:
            excerpts = []
            for offset in range(0, len(chunk.text), 2000):
                quote = chunk.text[offset : offset + 2000]
                if not quote.strip():
                    continue
                quote_id = f"quote_{len(self.references) + 1}"
                self.references[quote_id] = EvidenceReference(chunk_id=str(chunk.id), quote=quote)
                excerpts.append({"quote_id": quote_id, "text_id": texts.add(quote)})
            self.by_chunk[str(chunk.id)] = excerpts
