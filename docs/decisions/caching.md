# Dual-Layer Caching Strategy

## Status

Accepted.

## Context

The system depends on an external LLM provider with strict rate limits and on retrieval that takes non-trivial time. Repeated identical or near-identical questions are common in document Q&A. Caching has to serve two purposes:

- **Latency.** Return answers in milliseconds when possible.
- **Cost and rate-limit protection.** Avoid duplicate LLM calls under load.

An exact-match cache alone has a low hit rate because users paraphrase. A semantic cache alone risks returning an answer to a *different* question when similarity is not strict enough.

## Decision

Two cache layers are used together:

1. **Exact cache (Redis).** Key is `sha256(normalized_query + sorted(filters) + params_hash)`. Value is the serialized answer package. Sub-50 ms lookups.
2. **Semantic cache (Qdrant).** A dedicated collection stores the embedding of the normalized query and the answer package. On lookup, the query is embedded and searched against this collection. A hit requires cosine similarity above a **strict threshold**, tuned on the golden evaluation set.
3. **Embedding cache (Redis).** `sha256(text)` → vector. Embeddings are deterministic, so this is always safe.
4. **In-flight lock (Redis).** When two identical queries arrive concurrently, one computes and the other waits on a lock and reads the result.

Invalidation is **citation-based**. Every cached answer records the document IDs it cites. When any of those documents is updated or deleted, all affected entries are evicted from both layers.

## Consequences

Easier:

- Repeated questions are answered instantly.
- Paraphrased questions benefit from the semantic layer.
- Rate-limit pressure on the LLM provider is reduced.
- Duplicate concurrent work is eliminated.

Harder:

- Two caches to maintain and keep consistent.
- The semantic cache requires tuning. The threshold is a real, documented knob, not a magic number.
- Cache invalidation must be wired into the document lifecycle — this is a hard requirement, not a nice-to-have.

Risks accepted:

- A wrongly-hit semantic cache entry is worse than a miss. The threshold is chosen to prefer misses. This is monitored via the evaluation harness.

## Alternatives considered

- **Exact cache only.** Rejected. Hit rate is low for natural-language queries.
- **Semantic cache only.** Rejected. Incorrect hits on similar-but-different questions destroy trust.
- **Framework-provided caches.** Rejected. They do not integrate with citation-based invalidation or with Qdrant natively.