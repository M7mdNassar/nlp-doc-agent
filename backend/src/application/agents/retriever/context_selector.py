from src.domain.entities.chunk import Chunk


class ContextSelector:
    def __init__(self, max_chunks: int = 5, lambda_param: float = 0.7):
        self.max_chunks = max_chunks
        self.lambda_param = lambda_param

    def select(self, chunks: list[Chunk]) -> list[Chunk]:
        """Basic MMR (Max Marginal Relevance) for diversity."""
        if not chunks:
            return []

        selected = [chunks[0]]
        candidates = chunks[1:]

        while len(selected) < self.max_chunks and candidates:
            best_score = -float("inf")
            best_candidate = None

            for candidate in candidates:
                # Relevance is assumed to be the order from the reranker (highest first)
                # Diversity is the penalty for overlapping words with already selected chunks
                candidate_words = set(candidate.text.lower().split())
                max_overlap = 0.0

                for sel in selected:
                    sel_words = set(sel.text.lower().split())
                    if not candidate_words or not sel_words:
                        continue
                    intersection = candidate_words.intersection(sel_words)
                    overlap = len(intersection) / max(len(candidate_words), len(sel_words))
                    max_overlap = max(max_overlap, overlap)

                # MMR Formula
                score = self.lambda_param * (1.0) - (1 - self.lambda_param) * max_overlap

                if score > best_score:
                    best_score = score
                    best_candidate = candidate

            if best_candidate:
                selected.append(best_candidate)
                candidates.remove(best_candidate)

        return selected
