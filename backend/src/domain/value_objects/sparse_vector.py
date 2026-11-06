from dataclasses import dataclass

from ..exceptions.domain_error import DomainError


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]

    def __post_init__(self) -> None:
        if len(self.indices) != len(self.values):
            raise DomainError("SparseVector indices and values must have equal lengths")
