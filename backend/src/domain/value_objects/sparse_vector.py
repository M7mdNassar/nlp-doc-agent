from dataclasses import dataclass


@dataclass(frozen=True)
class SparseVector:
    """Sparse embedding independent of the vector database client."""

    indices: list[int]
    values: list[float]

    def __post_init__(self) -> None:
        if len(self.indices) != len(self.values):
            raise ValueError("Sparse vector indices and values must have equal lengths")
