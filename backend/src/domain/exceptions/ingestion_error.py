from .domain_error import DomainError


class IngestionError(DomainError):
    """Raised when a document fails to parse, chunk, or embed."""

    pass
