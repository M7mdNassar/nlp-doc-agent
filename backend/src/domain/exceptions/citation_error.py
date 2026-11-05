from .domain_error import DomainError


class CitationError(DomainError):
    """Raised when a generated citation cannot be resolved to a real chunk."""

    def __init__(self, invalid_placeholder: str):
        self.invalid_placeholder = invalid_placeholder
        super().__init__(f"Invalid citation placeholder: {invalid_placeholder}")
