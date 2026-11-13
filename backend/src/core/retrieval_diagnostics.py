"""Request-local candidate details for the opt-in diagnostic capture."""

from contextvars import ContextVar
from typing import Any

from src.domain.entities.chunk import Chunk

retrieval_events: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "retrieval_events", default=None
)


def record_candidates(
    stage: str,
    chunks: list[Chunk],
    scores: list[float] | None = None,
    decisions: list[str] | None = None,
) -> None:
    events = retrieval_events.get()
    if events is None:
        return
    events.append(
        {
            "stage": stage,
            "candidates": [
                {
                    "rank": index + 1,
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "page": chunk.page,
                    "section": chunk.section,
                    "text": chunk.text,
                    "score": scores[index] if scores is not None else None,
                    "decision": decisions[index] if decisions is not None else None,
                }
                for index, chunk in enumerate(chunks)
            ],
        }
    )
