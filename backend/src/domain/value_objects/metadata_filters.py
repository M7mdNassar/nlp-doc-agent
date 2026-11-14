import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


def section_key(value: str) -> str:
    match = re.match(r"(?:section\s+)?(\d+(?:\.\d+)*)\b", value, re.I)
    return match.group(1) if match else value.casefold()


class MetadataFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    doc_id: str | None = None
    doc_ids: list[str] | None = Field(default=None, max_length=30)
    document_name: str | None = None
    page: int | None = Field(default=None, ge=1)
    pages: list[Annotated[int, Field(ge=1)]] | None = Field(default=None, max_length=50)
    chapter: str | None = None
    section: str | None = None
    sections: list[str] | None = Field(default=None, max_length=50)
    author: str | None = None
    date: str | None = None
    file_type: str | None = None
