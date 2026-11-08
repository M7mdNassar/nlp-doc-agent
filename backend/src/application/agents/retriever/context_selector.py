import re
from collections import Counter
from collections.abc import Callable

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
                if any(c.id == chunk.id for c in selected) or overlap >= 0.9:
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
        return selected
