from pathlib import Path
from typing import Protocol

from ..value_objects.parsed_element import ParsedElement


class DocumentParser(Protocol):
    def supports(self, file_type: str) -> bool: ...
    async def parse(self, file_path: Path) -> list[ParsedElement]:
        """Returns raw extracted structural elements (text, tables, pages)."""
        ...
