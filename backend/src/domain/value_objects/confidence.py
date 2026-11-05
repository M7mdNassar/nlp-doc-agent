from dataclasses import dataclass

from ..exceptions.domain_error import DomainError


@dataclass(frozen=True)
class Confidence:
    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise DomainError("Confidence must be between 0.0 and 1.0")
