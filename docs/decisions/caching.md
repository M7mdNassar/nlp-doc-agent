# Dual-Layer Caching Strategy

## Status

Implemented with conservative semantic matching. See [current behavior and tests](../answer-cache.md).

## Context

The system depends on an external LLM provider with strict rate limits and on retrieval that takes non-trivial time. Repeated identical or near-identical questions are common in document Q&A. Caching has to serve two purposes:

- **Latency.** Return answers in milliseconds when possible.
- **Cost and rate-limit protection.** Avoid duplicate LLM calls under load.

An exact-match cache alone has a low hit rate because users paraphrase. A semantic cache alone risks returning an answer to a *different* question when similarity is not strict enough.

## Decision

The current implementation uses:

1. **Exact answers (Redis).** A hashed question key is scoped by effective filters, history, corpus fingerprint and pipeline/model version. Only previously verified answers are stored, with a 24-hour default TTL.
2. **Guarded semantic lookup (Qdrant).** A separate collection stores query embeddings and pointers to Redis entries. A hit requires cosine similarity at least 0.94 AND the same ordered subject and constraints after removing a supported introductory phrase. This is narrow paraphrase reuse, not general semantic equivalence. The threshold has targeted regression coverage, not a completed golden-set calibration.
3. **In-flight lease (Redis).** Identical requests share one generation. Leases renew while work runs and release on failure/cancellation. Waiting is bounded; expiry of the wait budget returns an in-progress error rather than starting duplicate generation.

Invalidation uses a fingerprint of all documents, indexed content and ingestion jobs. Adding, editing, deleting or reindexing any document makes old entries unreachable, including answers affected by newly introduced evidence. Old entries expire by TTL. Every hit also checks the current source metadata and exact quotes. Changes to effective conversation history or output requirements cannot reuse an incompatible answer.

A separate embedding-result cache is not implemented. Loaded model instances are reused, and providers may independently report cached prompt tokens; neither is an answer-cache hit.

## Consequences

Easier:

- Repeated questions are answered instantly.
- Eligible, tightly guarded paraphrases benefit from the semantic layer; other paraphrases intentionally miss.
- Rate-limit pressure on the LLM provider is reduced.
- Duplicate concurrent work is eliminated.

Harder:

- Two caches to maintain and keep consistent.
- The semantic cache requires tuning. The threshold is a real, documented knob, not a magic number.
- Corpus fingerprint checks enforce lifecycle invalidation without a database migration. For large corpora, use a transactional revision counter instead of scanning content.

Risks accepted:

- A wrongly-hit semantic entry is worse than a miss. Similarity alone never authorizes reuse; preservation of subject, order, case, quantities and instructions is required. Broad semantic reuse remains deliberately unsupported.

## Alternatives considered

- **Exact cache only.** Rejected. Hit rate is low for natural-language queries.
- **Semantic cache only.** Rejected. Incorrect hits on similar-but-different questions destroy trust.
- **Framework-provided caches.** Rejected. They do not integrate with citation-based invalidation or with Qdrant natively.
