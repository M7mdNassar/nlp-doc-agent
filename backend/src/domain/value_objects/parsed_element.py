from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedElement:
    """A raw structural element extracted from a document (text, table, header)."""

    text: str
    page: int
    section: str | None = None
    is_table: bool = False
    table_data: dict[str, Any] | None = None
    chapter: str | None = None
    location: str | None = None
    author: str = ""
    date: str = ""
