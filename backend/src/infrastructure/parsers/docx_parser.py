import asyncio
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from src.domain.value_objects.parsed_element import ParsedElement

from .structure import chapter_number, table_element_data, table_markdown


class DOCXParser:
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in {
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

    def _extract(self, file_path: Path) -> list[ParsedElement]:
        document = Document(str(file_path))
        props = document.core_properties
        author = props.author or ""
        date = props.created.date().isoformat() if props.created else ""
        section, chapter = None, None
        elements = []
        # DOCX has no reliable physical pagination. Cite native block positions.
        for position, block in enumerate(document.iter_inner_content(), 1):
            location = f"block {position}"
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                style = block.style.name if block.style else ""
                if style.startswith("Heading") or chapter_number(text):
                    section = text
                    chapter = chapter_number(text) or chapter
                elements.append(
                    ParsedElement(
                        text,
                        1,
                        section=section,
                        chapter=chapter,
                        location=location,
                        author=author,
                        date=date,
                    )
                )
            elif isinstance(block, Table):
                rows = [[cell.text.strip() for cell in row.cells] for row in block.rows]
                data = table_element_data(rows)
                if data["headers"]:
                    elements.append(
                        ParsedElement(
                            table_markdown(data),
                            1,
                            section=section,
                            is_table=True,
                            table_data=data,
                            chapter=chapter,
                            location=location,
                            author=author,
                            date=date,
                        )
                    )
        return elements

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._extract, file_path)
