"""Structural extraction without inventing physical pages for flowing documents."""

import re
from typing import Any


def chapter_number(text: str) -> str | None:
    match = re.match(r"\s*(?:chapter|chap\.)\s+([\w.-]+)", text, re.IGNORECASE)
    return match.group(1).casefold() if match else None


def table_element_data(rows: list[list[str]], bbox: list[float] | None = None) -> dict[str, Any]:
    width = max((len(row) for row in rows), default=0)
    padded = [row + [""] * (width - len(row)) for row in rows]
    return {"headers": padded[0] if padded else [], "rows": padded[1:], "bbox": bbox}


def table_markdown(data: dict[str, Any]) -> str:
    def row_text(row: list[str]) -> str:
        return "| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |"

    headers = data["headers"]
    return "\n".join(
        [row_text(headers), row_text(["---"] * len(headers))]
        + [row_text(row) for row in data["rows"]]
    )
