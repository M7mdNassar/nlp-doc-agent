from collections.abc import Callable

from src.domain.entities.chunk import Chunk
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.parsed_element import ParsedElement


class Chunker:
    def __init__(
        self,
        chunk_size: int = 384,
        overlap: int = 48,
        count_tokens: Callable[[str], int] | None = None,
    ):
        if not 0 <= overlap < chunk_size:
            raise ValueError("Overlap must be smaller than chunk size")
        self.chunk_size = chunk_size
        self.overlap = overlap
        # Production injects the embedding tokenizer; offline fallback is conservative.
        self.count_tokens = count_tokens or (lambda text: len(text.encode("utf-8")))

    def chunk(self, doc_id: DocumentId, elements: list[ParsedElement]) -> list[Chunk]:
        chunks = []
        for element in elements:
            texts = [element.text] if element.is_table else self._split(element.text)
            for text in texts:
                chunks.append(
                    Chunk(
                        id=ChunkId.generate(),
                        document_id=doc_id,
                        text=text,
                        page=element.page,
                        section=element.section,
                        chapter=element.chapter,
                        location=element.location,
                        author=element.author,
                        date=element.date,
                        table_data=element.table_data,
                    )
                )
        return chunks

    def _split(self, text: str) -> list[str]:
        result = []
        start = 0
        while start < len(text):
            low, high = start + 1, len(text)
            end = start
            while low <= high:
                mid = (low + high) // 2
                if self.count_tokens(text[start:mid]) <= self.chunk_size:
                    end, low = mid, mid + 1
                else:
                    high = mid - 1
            if end == start:
                raise ValueError("Chunk budget cannot fit one character")
            if end < len(text):
                end = self._end_boundary(text, start, end)
            segment = text[start:end].strip()
            if segment:
                result.append(segment)
            if end == len(text):
                break
            next_start = end
            while (
                next_start > start + 1
                and self.count_tokens(text[next_start - 1 : end]) <= self.overlap
            ):
                next_start -= 1
            # Begin overlap at a word boundary, while retaining the token limit.
            while next_start < end and not text[next_start - 1].isspace():
                next_start += 1
            start = next_start
        return result

    @staticmethod
    def _end_boundary(text: str, start: int, end: int) -> int:
        for separator in ("\n\n", ". ", "\n", " "):
            boundary = text.rfind(separator, start + (end - start) // 2, end)
            if boundary > start:
                return boundary + len(separator)
        return end
