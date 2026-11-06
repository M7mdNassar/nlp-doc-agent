import pytest

from src.domain.entities.document import DocumentStatus
from src.domain.exceptions.domain_error import DomainError
from src.domain.exceptions.ingestion_error import IngestionError
from src.domain.value_objects.token_budget import TokenBudget


def test_document_lifecycle_happy_path(sample_document):
    sample_document.mark_parsing()
    assert sample_document.status == DocumentStatus.PARSING

    sample_document.mark_embedding(page_count=5)
    assert sample_document.status == DocumentStatus.EMBEDDING
    assert sample_document.page_count == 5

    sample_document.mark_indexed()
    assert sample_document.status == DocumentStatus.INDEXED


def test_document_invalid_transition_raises_error(sample_document):
    # Cannot jump straight from QUEUED to INDEXED
    with pytest.raises(IngestionError):
        sample_document.mark_indexed()


def test_token_budget_enforcement():
    budget = TokenBudget(max_tokens=100)
    budget.consume(80)
    assert budget.remaining == 20

    with pytest.raises(DomainError):
        budget.consume(-10)
