import asyncio
import re
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any

import pdfplumber
from pdfplumber.page import Page
from pdfplumber.table import Table
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.domain.value_objects.parsed_element import ParsedElement

from .structure import chapter_number, table_element_data, table_markdown


def extract_table(page: Page, table: Table) -> tuple[str, dict[str, Any]]:
    """Keep partially ruled tables intact instead of claiming a false cell grid."""
    rows = [[str(cell or "") for cell in row] for row in table.extract(x_tolerance_ratio=0.15)]
    bbox = table.bbox
    # Vertical rules can enclose only the middle of a scientific table. Require
    # matching top AND bottom rules before extending the crop to their full width.
    edges = [edge for edge in page.edges if edge.get("orientation") == "h"]
    top = [edge for edge in edges if abs(float(edge["top"]) - bbox[1]) < 2]
    bottom = [edge for edge in edges if abs(float(edge["top"]) - bbox[3]) < 2]
    bounds = [
        (max(float(a["x0"]), float(b["x0"])), min(float(a["x1"]), float(b["x1"])))
        for a in top
        for b in bottom
        if abs(float(a["x0"]) - float(b["x0"])) < 2
        and abs(float(a["x1"]) - float(b["x1"])) < 2
        and float(a["x0"]) <= bbox[0] + 2
        and float(a["x1"]) >= bbox[2] - 2
    ]
    if bounds:
        left, right = max(bounds, key=lambda pair: pair[1] - pair[0])
        if left < bbox[0] - 3 or right > bbox[2] + 3:
            expanded = (max(page.bbox[0], left), bbox[1], min(page.bbox[2], right), bbox[3])
            layout = (
                page.crop(expanded).extract_text(
                    layout=True, x_tolerance_ratio=0.15, x_density=5, y_density=10
                )
                or ""
            )
            layout = "\n".join(line.rstrip() for line in layout.splitlines()).strip("\n")
            if layout.strip():
                return layout, {
                    "format": "layout",
                    "text": layout,
                    "headers": [],
                    "rows": [],
                    "bbox": list(expanded),
                }
    data = table_element_data(rows, list(bbox))
    return table_markdown(data) if data["headers"] else "", data


def outside_tables(obj: dict[str, Any], boxes: list[tuple[float, float, float, float]]) -> bool:
    return not any(
        box[0] <= obj.get("x0", -1)
        and obj.get("x1", -1) <= box[2]
        and box[1] <= obj.get("top", -1)
        and obj.get("bottom", -1) <= box[3]
        for box in boxes
    )


def attach_caption(lines: list[str], text: str, data: dict[str, Any]) -> tuple[list[str], str]:
    """Keep nearby captions with table data during indexing."""
    start = next((i for i in range(len(lines) - 1, max(-1, len(lines) - 7), -1)
                  if re.match(r"Table\s+\d+[.:\s]", lines[i], re.I)), None)
    if start is not None:
        caption = "\n".join(lines[start:])
        if len(caption) < 1000:
            text = caption + "\n\n" + text
            lines = lines[:start]
            if data.get("format") == "layout":
                data["text"] = text
    return lines, text


def page_elements(
    page: Page,
    page_num: int,
    section: str | None,
    chapter: str | None,
    author: str,
    date: str,
    flow_text: str | None = None,
) -> tuple[list[ParsedElement], str | None, str | None]:
    tables = page.find_tables()
    extracted_tables = [extract_table(page, table) for table in tables]
    body = page.filter(
        partial(outside_tables, boxes=[data["bbox"] for _, data in extracted_tables])
    )
    # The PDF text stream preserves inline scientific notation better than grouping
    # glyphs by their vertical position. Table pages retain geometric extraction so
    # table text is excluded from prose and keeps its original bounding box.
    events: list[tuple[float, str, dict[str, Any] | None]]
    if flow_text and not tables:
        events = [(float(index), line, None) for index, line in enumerate(flow_text.splitlines())]
    else:
        events = [
            (float(line["top"]), str(line["text"]), None)
            for line in body.extract_text_lines(x_tolerance_ratio=0.15)
        ]
    for text, table_data in extracted_tables:
        if text:
            events.append((table_data["bbox"][1], text, table_data))
    elements = []
    lines: list[str] = []
    for _, text, data in sorted(events, key=lambda item: item[0]):
        if data is not None:
            lines, text = attach_caption(lines, text, data)
        heading = bool(
            re.match(r"(?:chapter|section)\s+\w", text, re.I)
            or re.fullmatch(r"\d+(?:\.\d+)*\s+[A-Z][^.!?\n]{1,120}", text.strip())
        )
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
        try:
            reader: PdfReader | None = PdfReader(file_path)
        except PdfReadError:
            reader = None
        with pdfplumber.open(file_path) as pdf:
            metadata = pdf.metadata or {}
            author = str(metadata.get("Author", "") or "")
            match = re.search(r"(\d{4})(\d{2})(\d{2})", str(metadata.get("CreationDate", "") or ""))
            date = "-".join(match.groups()) if match else ""
            for page_num, page in enumerate(pdf.pages, start=1):
                flow_text = None
                if reader is not None:
                    with suppress(PdfReadError):
                        flow_text = reader.pages[page_num - 1].extract_text()
                extracted, section, chapter = page_elements(
                    page, page_num, section, chapter, author, date, flow_text
                )
                elements.extend(extracted)
        return elements

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._extract, file_path)
