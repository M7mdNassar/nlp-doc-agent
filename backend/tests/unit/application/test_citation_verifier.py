from src.application.citations.verifier import CitationVerifier
from src.domain.entities.evidence import EvidencePackage


def test_citation_verifier_strips_hallucinations(sample_chunks):
    verifier = CitationVerifier()
    evidence = EvidencePackage(chunks=sample_chunks)

    # "chunk_3" does not exist in evidence, but "chunk_1" does
    raw_answer = (
        "Model X is great [doc_123456789, p. 1]. But Model Z is better [doc_123456789, p. 5]."
    )

    verified = verifier.verify_and_fix(raw_answer, evidence)

    # Valid citation kept
    assert "[doc_123456789, p. 1]" in verified
    # Invalid citation stripped
    assert "[doc_123456789, p. 5]" not in verified
