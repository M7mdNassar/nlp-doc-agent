import re

from src.domain.entities.document import Document
from src.domain.value_objects.metadata_filters import MetadataFilters


class MetadataFilterResolver:
    """Resolve explicit natural-language constraints without widening explicit API filters."""

    def resolve(
        self, question: str, documents: list[Document], explicit: MetadataFilters | None = None
    ) -> MetadataFilters:
        values = (explicit or MetadataFilters()).model_dump(exclude_none=True)
        mentioned = [
            str(doc.id)
            for doc in documents
            if re.search(r"(?<![\w.-])" + re.escape(doc.name) + r"(?![\w.-])", question, re.I)
        ]
        # Unknown named files must return no results, not silently search other files.
        file_mentions = re.findall(r"[\w.-]+\.(?:pdf|docx|txt|md)\b", question, re.I)
        unknown = [
            name
            for name in file_mentions
            if not any(doc.name.casefold().endswith(name.casefold()) for doc in documents)
        ]
        if mentioned or file_mentions:
            inferred = [] if unknown else mentioned
            if "doc_ids" in values:
                inferred = [doc for doc in inferred if doc in values["doc_ids"]]
            values["doc_ids"] = inferred
        patterns = {
            "page": r"\b(?:page|p\.)\s*(\d+)\b",
            "chapter": r"\bchapter\s+([\w.-]+)",
            "section": r"\bsection\s+(\d+(?:\.\d+)*)",
            "date": r"\b(?:dated?|published(?: on)?)\s+(\d{4}-\d{2}-\d{2})\b",
            "author": r'\b(?:author|written by|authored by)\s+["\']([^"\']+)["\']',
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, question, re.I)
            if match and key not in values:
                values[key] = int(match.group(1)) if key == "page" else match.group(1)
        if "file_type" not in values:
            match = re.search(r"\b(pdf|docx|txt|markdown)\s+(?:files|documents)\b", question, re.I)
            if match:
                values["file_type"] = {"markdown": "md"}.get(
                    match.group(1).lower(), match.group(1).lower()
                )
        return MetadataFilters.model_validate(values)
