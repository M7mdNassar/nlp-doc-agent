from src.domain.ports.parser import DocumentParser

from .markdown_parser import MarkdownParser
from .pdf_parser import PDFParser
from .txt_parser import TXTParser


class ParserFactory:
    def __init__(self):
        self.parsers: list[DocumentParser] = [
            PDFParser(),
            TXTParser(),
            MarkdownParser(),
            # DOCXParser(),
        ]

    def get_parser(self, file_type: str) -> DocumentParser:
        for parser in self.parsers:
            if parser.supports(file_type):
                return parser
        raise ValueError(f"No parser found for type: {file_type}")


parser_factory = ParserFactory()
