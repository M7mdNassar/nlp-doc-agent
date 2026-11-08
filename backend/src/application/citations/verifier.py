import re

from src.domain.entities.answer import AnswerDraft, Source
from src.domain.entities.evidence import EvidencePackage

INSUFFICIENT_ANSWER = (
    "I don't have enough verified evidence in the selected documents to answer this question."
)


def normalized(text: str) -> str:
    return " ".join(text.split())


def markdown_label(text: str) -> str:
    return re.sub(r"[\[\]\r\n]", " ", text).strip()


class CitationVerifier:
    def validate(self, draft: AnswerDraft, evidence: EvidencePackage) -> None:
        chunks = {str(chunk.id): chunk for chunk in evidence.chunks}
        for block in draft.blocks:
            for ref in block.citations:
                if ref.chunk_id not in chunks:
                    raise ValueError("Answer cites an unknown evidence chunk")
                if normalized(ref.quote) not in normalized(chunks[ref.chunk_id].text):
                    raise ValueError("Answer citation quote is not present in its source")

    def format(self, draft: AnswerDraft, evidence: EvidencePackage) -> tuple[str, list[Source]]:
        self.validate(draft, evidence)
        chunks = {str(chunk.id): chunk for chunk in evidence.chunks}
        sources: list[Source] = []
        paragraphs = []
        seen = set()
        for block in draft.blocks:
            labels = []
            for ref in block.citations:
                chunk = chunks[ref.chunk_id]
                name = markdown_label(chunk.document_name or str(chunk.document_id))
                location = chunk.location or f"p. {chunk.page}"
                if chunk.location and chunk.section:
                    location = f"{chunk.section}, {location}"
                label = f"[{name}, {markdown_label(location)}]"
                if label not in labels:
                    labels.append(label)
                if ref.chunk_id not in seen:
                    sources.append(
                        Source(
                            chunk_id=ref.chunk_id,
                            document_id=str(chunk.document_id),
                            document_name=chunk.document_name or str(chunk.document_id),
                            page=chunk.page,
                            section=chunk.section,
                            location=chunk.location,
                            quote=ref.quote,
                        )
                    )
                    seen.add(ref.chunk_id)
            paragraphs.append(block.text.strip() + "\n\n" + " ".join(labels))
        source_lines = []
        for source in sources:
            location = source["location"] or f"p. {source['page']}"
            source_lines.append(
                f"- {markdown_label(source['document_name'])}, "
                f"{markdown_label(location)} ({source['chunk_id']})"
            )
        return "\n\n".join(paragraphs) + "\n\nSources:\n" + "\n".join(source_lines), sources

    def verify_and_fix(self, answer: str, evidence: EvidencePackage) -> str:
        """Legacy plain-text compatibility: invalid or uncited content fails closed."""
        pattern = re.compile(r"\[(doc_[a-fA-F0-9]+),\s*p\.\s*(\d+)\]")
        valid = {(str(c.document_id), c.page) for c in evidence.chunks}
        paragraphs = [part for part in answer.split("\n\n") if part.strip()]
        for part in paragraphs:
            refs = pattern.findall(part)
            if not refs or any((doc_id, int(page)) not in valid for doc_id, page in refs):
                return INSUFFICIENT_ANSWER
        return answer if paragraphs else INSUFFICIENT_ANSWER
