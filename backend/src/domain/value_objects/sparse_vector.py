from dataclasses import dataclass


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]
