import uuid
from dataclasses import dataclass

from ..exceptions.domain_error import DomainError


@dataclass(frozen=True)
class DocumentId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.startswith("doc_"):
            raise DomainError("DocumentId must start with 'doc_'")
        if len(self.value) < 10:
            raise DomainError("DocumentId is too short")

    @classmethod
    def generate(cls) -> "DocumentId":
        return cls(f"doc_{uuid.uuid4().hex}")

    def __str__(self) -> str:
        return self.value
