from dataclasses import dataclass


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]

    def __post_init__(self) -> None:
        if len(self.indices) != len(self.values):
            raise ValueError("SparseVector indices and values must have equal lengths")
