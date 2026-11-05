from dataclasses import dataclass

from ..exceptions.domain_error import DomainError


@dataclass(frozen=True)
class PageRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1:
            raise DomainError("Page numbers must be >= 1")
        if self.end < self.start:
            raise DomainError("End page cannot be less than start page")

    def __str__(self) -> str:
        if self.start == self.end:
            return f"p. {self.start}"
        return f"pp. {self.start}-{self.end}"
