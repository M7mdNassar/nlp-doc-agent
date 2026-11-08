import pytest

from src.application.citations.verifier import INSUFFICIENT_ANSWER, CitationVerifier
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference
from src.domain.entities.evidence import EvidencePackage


def test_invalid_legacy_citation_rejects_claim_instead_of_stripping_marker(sample_chunks):
    evidence = EvidencePackage(chunks=sample_chunks)
    raw = "Model Z is better [doc_123456789, p. 99]."
    assert CitationVerifier().verify_and_fix(raw, evidence) == INSUFFICIENT_ANSWER
    assert CitationVerifier().verify_and_fix("Uncited claim.", evidence) == INSUFFICIENT_ANSWER


def test_citations_use_original_document_and_native_location(sample_chunks):
    chunk = sample_chunks[0]
    chunk.document_name, chunk.file_type = "Research.docx", "docx"
    chunk.location, chunk.section = "block 4", "Chapter 2"
    draft = AnswerDraft(
        blocks=[
            AnswerBlock(
                text="Model X is 95% accurate.",
                citations=[EvidenceReference(chunk_id=str(chunk.id), quote=chunk.text)],
            )
        ]
    )
    answer, sources = CitationVerifier().format(draft, EvidencePackage(chunks=[chunk]))
    assert "[Research.docx, Chapter 2, block 4]" in answer
    assert "p. 1" not in answer
    assert sources[0]["quote"] == chunk.text


def test_every_answer_block_requires_a_source():
    with pytest.raises(ValueError):
        AnswerDraft.model_validate({"blocks": [{"text": "Uncited", "citations": []}]})
