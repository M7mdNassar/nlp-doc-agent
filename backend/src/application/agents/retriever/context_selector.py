import re
from collections import Counter
from collections.abc import Callable

from src.core.retrieval_diagnostics import record_candidates
from src.domain.entities.chunk import Chunk


class ContextSelector:
    def __init__(
        self,
        count_tokens: Callable[[str], int] | None = None,
        max_tokens: int = 4000,
        max_chunks: int = 8,
        per_document: int = 4,
    ):
        self.count_tokens = count_tokens or (lambda text: len(text.encode("utf-8")))
        self.max_tokens, self.max_chunks, self.per_document = max_tokens, max_chunks, per_document

    def select(self, ranked: list[Chunk]) -> list[Chunk]:
        selected: list[Chunk] = []
        counts: Counter[str] = Counter()
        used = 0
        remaining = list(enumerate(ranked))
        while remaining and len(selected) < self.max_chunks:
            best: tuple[int, Chunk] | None = None
            best_score = float("-inf")
            for rank, chunk in remaining:
                doc_id = str(chunk.document_id)
                cost = (
                    self.count_tokens(chunk.text + chunk.document_name + (chunk.section or "")) + 32
                )
                if used + cost > self.max_tokens or counts[doc_id] >= self.per_document:
                    continue
                words = set(re.findall(r"\w+", chunk.text.casefold()))
                overlap = 0.0
                for previous in selected:
                    if previous.document_id != chunk.document_id:
                        continue
                    other = set(re.findall(r"\w+", previous.text.casefold()))
                    overlap = max(overlap, len(words & other) / max(1, len(words | other)))
                # Similar wording can still differ in a number, negation, or caveat.
                # Only discard exact duplicates within one document; cross-document
                # text is shared in prompts while keeping both source identities.
                if any(
                    c.id == chunk.id
                    or (
                        c.document_id == chunk.document_id
                        and c.text == chunk.text
                        and c.table_data == chunk.table_data
                    )
                    for c in selected
                ):
                    continue
                score = 1 / (rank + 1) + 0.35 * (counts[doc_id] == 0) - 0.4 * overlap
                if score > best_score:
                    best, best_score = (rank, chunk), score
            if best is None:
                break
            remaining.remove(best)
            chunk = best[1]
            selected.append(chunk)
            counts[str(chunk.document_id)] += 1
            used += self.count_tokens(chunk.text + chunk.document_name + (chunk.section or "")) + 32
        self._record_selection(ranked, selected, counts)
        return selected

    def _record_selection(
        self, ranked: list[Chunk], selected: list[Chunk], counts: Counter[str]
    ) -> None:
        decisions = []
        selected_ids = {chunk.id for chunk in selected}
        for chunk in ranked:
            if chunk.id in selected_ids:
                reason = "selected"
            elif any(
                previous.document_id == chunk.document_id
                and previous.text == chunk.text
                and previous.table_data == chunk.table_data
                for previous in selected
            ):
                reason = "duplicate"
            elif counts[str(chunk.document_id)] >= self.per_document:
                reason = "document_limit"
            elif len(selected) >= self.max_chunks:
                reason = "chunk_limit"
            else:
                reason = "token_budget"
            decisions.append(reason)
        record_candidates("context_selection", ranked, decisions=decisions)
