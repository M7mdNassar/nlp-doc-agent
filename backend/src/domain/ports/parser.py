from pathlib import Path
from typing import Any, Protocol


class DocumentParser(Protocol):
    def supports(self, file_type: str) -> bool: ...
    async def parse(self, file_path: Path) -> list[dict[str, Any]]:
        """Returns raw extracted structural elements (text, tables, pages)."""
        ...
