import re
from typing import Any

from src.core.errors import ValidationError
from src.domain.entities.document import Document
from src.domain.value_objects.metadata_filters import MetadataFilters, section_key


def numbered_constraints(question: str, field: str) -> list[str]:
    label = r"(?:pages?|p\.)" if field == "page" else r"sections?"
    number = r"\d+" if field == "page" else r"\d+(?:\.\d+)*"
    matches = re.finditer(
        r"\b"
        + label
        + r"\s*("
        + number
        + r"\b(?:\s*(?:,|and|or|to|through|[-\u2013])\s*"
        + r"(?:"
        + label
        + r"\s*)?"
        + number
        + r"\b)*)",
        question,
        re.I,
    )
    found: list[str] = []
    for match in matches:
        expression = re.sub(label, "", match[1], flags=re.I)
        for item in re.split(r"\s*(?:,|\band\b|\bor\b)\s*", expression, flags=re.I):
            bounds = re.split(r"\s*(?:\bto\b|\bthrough\b|[-\u2013])\s*", item)
            if len(bounds) == 1:
                found.append(bounds[0].strip())
            else:
                left, right = (b.strip().split(".") for b in bounds)
                start, stop = int(left[-1]), int(right[-1])
                if left[:-1] != right[:-1] or stop < start or stop - start >= 50:
                    raise ValidationError(
                        "Use an ascending page/section range of at most 50 items."
                    )
                prefix = ".".join(left[:-1])
                found.extend(
                    (prefix + "." if prefix else "") + str(i) for i in range(start, stop + 1)
                )
    result = list(dict.fromkeys(found))
    if len(result) > 50 or (field == "page" and any(int(v) < 1 for v in result)):
        raise ValidationError("Use up to 50 positive page/section constraints.")
    return result


def apply_numbered_constraints(question: str, values: dict[str, Any]) -> None:
    for field, plural in (("page", "pages"), ("section", "sections")):
        inferred = numbered_constraints(question, field)
        if not inferred:
            continue
        selected = [int(v) if field == "page" else v for v in inferred]
        if field in values:
            hard = values[field] if field == "page" else section_key(values[field])
            selected = [v for v in selected if v == hard]
        if plural in values:
            allowed = (
                values[plural] if field == "page" else [section_key(v) for v in values[plural]]
            )
            selected = [v for v in selected if v in allowed]
        if len(selected) == 1 and field not in values and plural not in values:
            values[field] = selected[0]
        else:
            values[plural] = selected


class MetadataFilterResolver:
    """Resolve explicit natural-language constraints without widening explicit API filters."""

    def resolve(
        self, question: str, documents: list[Document], explicit: MetadataFilters | None = None
    ) -> MetadataFilters:
        values = (explicit or MetadataFilters()).model_dump(exclude_none=True)
        mentioned = [
            str(doc.id)
            for doc in documents
            # A terminal period/ellipsis is sentence punctuation. A dot followed
            # by filename characters still belongs to a different filename.
            if re.search(
                r"(?<![\w.-])" + re.escape(doc.name) + r"(?![\w-]|\.+[\w-])", question, re.I
            )
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
            "chapter": r"\bchapter\s+([\w.-]+)",
            "date": r"\b(?:dated?|published(?: on)?)\s+(\d{4}-\d{2}-\d{2})\b",
            "author": r'\b(?:author|written by|authored by)\s+["\']([^"\']+)["\']',
        }
        apply_numbered_constraints(question, values)
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
