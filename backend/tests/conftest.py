from unittest.mock import AsyncMock

import pytest

from src.domain.entities.chunk import Chunk
from src.domain.entities.document import Document, DocumentStatus
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_doc_repo():
    return AsyncMock()


@pytest.fixture
def sample_document():
    return Document(
        id=DocumentId("doc_123456789"),
        name="test.pdf",
        file_type="pdf",
        checksum="abc123checksum",
        status=DocumentStatus.QUEUED,
    )


@pytest.fixture
def sample_chunks():
    doc_id = DocumentId("doc_123456789")
    return [
        Chunk(id=ChunkId("chunk_1"), document_id=doc_id, text="Model X is 95% accurate.", page=1),
        Chunk(id=ChunkId("chunk_2"), document_id=doc_id, text="Model Y is 80% accurate.", page=2),
    ]
