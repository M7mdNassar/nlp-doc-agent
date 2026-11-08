from pydantic import BaseModel, ConfigDict, Field


class MetadataFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    doc_id: str | None = None
    doc_ids: list[str] | None = Field(default=None, max_length=30)
    document_name: str | None = None
    page: int | None = Field(default=None, ge=1)
    chapter: str | None = None
    section: str | None = None
    author: str | None = None
    date: str | None = None
    file_type: str | None = None
