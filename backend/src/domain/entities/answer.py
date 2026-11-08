from typing import Any, TypedDict

from pydantic import Field

from .analysis import StrictModel


class EvidenceReference(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=3000)


class AnswerBlock(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    citations: list[EvidenceReference] = Field(min_length=1, max_length=12)


class AnswerDraft(StrictModel):
    blocks: list[AnswerBlock] = Field(min_length=1, max_length=12)


class ExcerptReference(StrictModel):
    quote_id: str = Field(min_length=1, max_length=100)


class ExcerptAnswerBlock(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    citations: list[ExcerptReference] = Field(min_length=1, max_length=12)


class ExcerptAnswerDraft(StrictModel):
    blocks: list[ExcerptAnswerBlock] = Field(min_length=1, max_length=12)


class GroundingVerdict(StrictModel):
    supported: list[bool] = Field(min_length=1, max_length=12)
    qualifications_preserved: list[bool] = Field(min_length=1, max_length=12)
    no_added_details: list[bool] = Field(min_length=1, max_length=12)
    feedback: list[str] = Field(default_factory=list, max_length=12)

    def accepts(self, block_count: int) -> bool:
        return all(
            len(checks) == block_count and all(checks)
            for checks in (self.supported, self.qualifications_preserved, self.no_added_details)
        )


class Source(TypedDict):
    chunk_id: str
    document_id: str
    document_name: str
    page: int
    section: str | None
    location: str | None
    quote: str


class ChatResult(TypedDict):
    answer: str
    state: str
    loops: int
    evidence_count: int
    sources: list[Source]
    tool_results: list[dict[str, Any]]
    conversation_id: str
