from .txt_parser import TXTParser


class MarkdownParser(TXTParser):
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in ["md", "markdown", "text/markdown"]
