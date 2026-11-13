import asyncio
import re
from pathlib import Path

from src.domain.value_objects.parsed_element import ParsedElement

from .structure import chapter_number


def parse_text(text: str) -> list[ParsedElement]:
    elements: list[ParsedElement] = []
    section, chapter = None, None
    lines = text.splitlines()
    start = 0

    def append(end: int) -> None:
        content = "\n".join(lines[start:end]).strip()
        if content:
            elements.append(
                ParsedElement(
                    content,
                    1,
                    section=section,
                    chapter=chapter,
                    location=f"lines {start + 1}-{end}",
                )
            )

    for index, line in enumerate(lines):
        if re.match(r"^(?:#{1,6}\s+|chapter\s+\w|section\s+\w)", line, re.I):
            append(index)
            section = re.sub(r"^#+\s*", "", line).strip()
            chapter = chapter_number(section) or chapter
            start = index
    append(len(lines))
    return elements


class TXTParser:
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in ["txt", "text/plain"]

    def _extract(self, file_path: Path) -> list[ParsedElement]:
        return parse_text(file_path.read_text(encoding="utf-8-sig", errors="replace"))

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._extract, file_path)
