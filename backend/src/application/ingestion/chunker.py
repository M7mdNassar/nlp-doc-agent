from src.domain.entities.chunk import Chunk
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.domain.value_objects.parsed_element import ParsedElement


class Chunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc_id: DocumentId, elements: list[ParsedElement]) -> list[Chunk]:
        chunks = []
        for el in elements:
            # Tables are never split
            if el.is_table:
                chunks.append(
                    Chunk(
                        id=ChunkId.generate(),
                        document_id=doc_id,
                        text=el.text,
                        page=el.page,
                        section=el.section,
                    )
                )
                continue

            # Basic character-based splitting (In production, use tiktoken or LangChain)
            words = el.text.split()
            current_chunk_words = []

            for word in words:
                current_chunk_words.append(word)
                if len(current_chunk_words) >= (self.chunk_size // 4):  # rough word/token ratio
                    chunks.append(
                        Chunk(
                            id=ChunkId.generate(),
                            document_id=doc_id,
                            text=" ".join(current_chunk_words),
                            page=el.page,
                            section=el.section,
                        )
                    )
                    # Keep overlap
                    current_chunk_words = current_chunk_words[-int(self.overlap // 4) :]

            if current_chunk_words:
                chunks.append(
                    Chunk(
                        id=ChunkId.generate(),
                        document_id=doc_id,
                        text=" ".join(current_chunk_words),
                        page=el.page,
                        section=el.section,
                    )
                )
        return chunks
