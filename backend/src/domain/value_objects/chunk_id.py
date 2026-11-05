import uuid
from dataclasses import dataclass

from ..exceptions.domain_error import DomainError


@dataclass(frozen=True)
class ChunkId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.startswith("chunk_"):
            raise DomainError("ChunkId must start with 'chunk_'")

    @classmethod
    def generate(cls) -> "ChunkId":
        return cls(f"chunk_{uuid.uuid4().hex}")

    def __str__(self) -> str:
        return self.value
