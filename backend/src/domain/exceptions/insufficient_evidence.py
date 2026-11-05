from .domain_error import DomainError


class InsufficientEvidenceError(DomainError):
    """Raised when the Analyst determines there is not enough evidence to answer."""

    def __init__(self, missing_aspects: list[str]):
        self.missing_aspects = missing_aspects
        super().__init__(f"Insufficient evidence. Missing: {', '.join(missing_aspects)}")
