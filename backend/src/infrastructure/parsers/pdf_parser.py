import asyncio
import re
from functools import partial
from pathlib import Path
from typing import Any

import pdfplumber
from pdfplumber.page import Page

from src.domain.value_objects.parsed_element import ParsedElement

from .structure import chapter_number, table_element_data, table_markdown


def outside_tables(obj: dict[str, Any], boxes: list[tuple[float, float, float, float]]) -> bool:
    return not any(
        box[0] <= obj.get("x0", -1)
        and obj.get("x1", -1) <= box[2]
        and box[1] <= obj.get("top", -1)
        and obj.get("bottom", -1) <= box[3]
        for box in boxes
    )


def page_elements(
    page: Page, page_num: int, section: str | None, chapter: str | None, author: str, date: str
) -> tuple[list[ParsedElement], str | None, str | None]:
    tables = page.find_tables()
    body = page.filter(partial(outside_tables, boxes=[table.bbox for table in tables]))
    events: list[tuple[float, str, dict[str, Any] | None]] = [
        (float(line["top"]), str(line["text"]), None) for line in body.extract_text_lines()
    ]
    for table in tables:
        rows = [[str(cell or "") for cell in row] for row in table.extract()]
        table_data = table_element_data(rows, list(table.bbox))
        if table_data["headers"]:
            events.append((table.bbox[1], table_markdown(table_data), table_data))
    elements = []
    lines: list[str] = []
    for _, text, data in sorted(events, key=lambda item: item[0]):
        heading = bool(re.match(r"(?:chapter|section)\s+\w", text, re.I))
        if (heading or data is not None) and lines:
            elements.append(
                ParsedElement(
                    "\n".join(lines),
                    page_num,
                    section=section,
                    chapter=chapter,
                    author=author,
                    date=date,
                )
            )
            lines = []
        if heading:
            section, chapter = text.strip(), chapter_number(text) or chapter
        if data is not None:
            elements.append(
                ParsedElement(
                    text,
                    page_num,
                    section=section,
                    chapter=chapter,
                    author=author,
                    date=date,
                    is_table=True,
                    table_data=data,
                )
            )
        else:
            lines.append(text)
    if lines:
        elements.append(
            ParsedElement(
                "\n".join(lines),
                page_num,
                section=section,
                chapter=chapter,
                author=author,
                date=date,
            )
        )
    return elements, section, chapter


class PDFParser:
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in ["pdf", "application/pdf"]

    def _extract(self, file_path: Path) -> list[ParsedElement]:
        elements = []
        section, chapter = None, None
        with pdfplumber.open(file_path) as pdf:
            metadata = pdf.metadata or {}
            author = str(metadata.get("Author", "") or "")
            match = re.search(r"(\d{4})(\d{2})(\d{2})", str(metadata.get("CreationDate", "") or ""))
            date = "-".join(match.groups()) if match else ""
            for page_num, page in enumerate(pdf.pages, start=1):
                extracted, section, chapter = page_elements(
                    page, page_num, section, chapter, author, date
                )
                elements.extend(extracted)
        return elements

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._extract, file_path)
