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
