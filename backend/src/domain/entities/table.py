from dataclasses import dataclass, field

from ..value_objects.confidence import Confidence
from ..value_objects.document_id import DocumentId
from ..value_objects.page_range import PageRange


@dataclass
class Table:
    document_id: DocumentId
    page_range: PageRange
    markdown_content: str
    confidence: Confidence
    section: str | None = None
    chunk_id: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
