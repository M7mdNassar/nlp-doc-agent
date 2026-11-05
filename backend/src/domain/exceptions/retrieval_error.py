from .domain_error import DomainError


class RetrievalError(DomainError):
    """Raised when the vector store or retrieval pipeline fails."""

    pass
