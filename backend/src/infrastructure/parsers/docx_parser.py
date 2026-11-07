import asyncio
from pathlib import Path

import docx

from src.domain.ports.parser import DocumentParser
from src.domain.value_objects.parsed_element import ParsedElement


class DOCXParser(DocumentParser):
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in [
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

    def _extract(self, file_path: Path) -> list[ParsedElement]:
        # Cast Path to str to satisfy mypy and python-docx
        doc = docx.Document(str(file_path))
        elements = []

        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        if text:
            elements.append(ParsedElement(text=text, page=1))

        for table in doc.tables:
            md_table = ""
            for row in table.rows:
                md_table += "| " + " | ".join([cell.text.strip() for cell in row.cells]) + " |\n"
            elements.append(ParsedElement(text=md_table, page=1, is_table=True))

        return elements

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._extract, file_path)
