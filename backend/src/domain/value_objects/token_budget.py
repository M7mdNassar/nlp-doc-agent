from dataclasses import dataclass

from ..exceptions.domain_error import DomainError


@dataclass
class TokenBudget:
    max_tokens: int
    used_tokens: int = 0

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise DomainError("Max tokens must be > 0")
        if self.used_tokens < 0:
            raise DomainError("Used tokens cannot be negative")

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)

    def consume(self, amount: int) -> None:
        if amount < 0:
            raise DomainError("Cannot consume negative tokens")
        self.used_tokens += amount
