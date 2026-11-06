import re

import structlog

from src.domain.entities.evidence import EvidencePackage

logger = structlog.get_logger(__name__)


class CitationVerifier:
    def __init__(self) -> None:
        # Matches [doc_1234, p. 12] or [doc_1234, p.12]
        self.pattern = re.compile(r"\[(doc_[a-fA-F0-9]+),\s*p\.\s*(\d+)\]")

    def verify_and_fix(self, answer: str, evidence: EvidencePackage) -> str:
        """Ensures all citations in the answer map to a real chunk. Strips invalid ones."""
        valid_citations = {(str(chunk.document_id), chunk.page) for chunk in evidence.chunks}

        def replace_match(match: re.Match[str]) -> str:
            doc_id = match.group(1)
            page = int(match.group(2))
            if (doc_id, page) in valid_citations:
                return match.group(0)  # Valid, keep it
            else:
                logger.warning(f"Hallucinated citation stripped: {match.group(0)}")
                return ""  # Strip invalid citation

        verified_answer = self.pattern.sub(replace_match, answer)
        return verified_answer
