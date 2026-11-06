import asyncio
from pathlib import Path

from src.domain.ports.parser import DocumentParser
from src.domain.value_objects.parsed_element import ParsedElement


class TXTParser(DocumentParser):
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in ["txt", "text/plain"]

    def _extract(self, file_path: Path) -> list[ParsedElement]:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        # Treat whole file as page 1
        return [ParsedElement(text=text, page=1)]

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._extract, file_path)
