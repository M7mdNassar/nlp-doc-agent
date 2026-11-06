import asyncio
from pathlib import Path

import pdfplumber

from src.domain.ports.parser import DocumentParser
from src.domain.value_objects.parsed_element import ParsedElement


class PDFParser(DocumentParser):
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in ["pdf", "application/pdf"]

    def _extract(self, file_path: Path) -> list[ParsedElement]:
        elements = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    elements.append(ParsedElement(text=text, page=page_num))

                # Extract tables
                tables = page.extract_tables()
                for table in tables:
                    # Convert to Markdown format for the LLM
                    if not table or not table[0]:
                        continue
                    md_table = "| " + " | ".join(str(c) for c in table[0]) + " |\n"
                    md_table += "|" + "|".join(["---"] * len(table[0])) + "|\n"
                    for row in table[1:]:
                        md_table += "| " + " | ".join(str(c) for c in row) + " |\n"

                    elements.append(ParsedElement(text=md_table, page=page_num, is_table=True))
        return elements

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        # Run CPU-bound pdfplumber in a thread pool
        return await asyncio.to_thread(self._extract, file_path)
