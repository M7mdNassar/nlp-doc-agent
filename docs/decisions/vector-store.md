# Vector Store Selection

## Status

Accepted.

## Context

The system must store dense embeddings and sparse BM25 vectors for every chunk, filter retrieval by metadata (document, page, section, access tags) at query time, and stay consistent under concurrent ingestion and querying. Retrieval quality under metadata filters is critical: a filter that silently drops recall undermines the evidence-first guarantee of the whole system.

Candidate vector stores included embedded options (Chroma), self-hosted servers (Qdrant, Weaviate), and managed services (Pinecone, Supabase pgvector).

## Decision

We use **Qdrant**, self-hosted via Docker Compose with a persistent named volume.

Qdrant provides:

- **Filterable HNSW.** Metadata filters are applied during graph traversal, preserving recall under filtering.
- **Native hybrid search.** Dense and sparse vectors live in the same collection. Reciprocal Rank Fusion is performed by Qdrant in a single query. There is no separate keyword service to keep in sync.
- **Atomic upserts.** Dense and sparse representations of a chunk are written together.
- **Payload indexes.** Fast metadata filtering on `doc_id`, `page`, `section`, `access_tags`, and `embedding_version`.
- **Production concurrency.** A single Rust binary with a persistent volume, not a SQLite-backed embedded store.

## Consequences

Easier:

- One system stores vectors, metadata, and the semantic cache collection.
- No custom fusion code, no dual-write consistency between a vector DB and a keyword index.
- Metadata filters preserve recall, which is essential for chapter-scoped or document-scoped questions.

Harder:

- Requires running a stateful service locally. This is acceptable for the current single-machine deployment.
- Backups must use Qdrant snapshots rather than a plain file copy.

Risks accepted:

- Adding a new dependency to the local stack. Mitigated by Compose healthchecks and pinned images.

## Alternatives considered

- **Chroma (embedded).** Rejected for production use. Its local persistent mode is SQLite-backed, which causes write contention under concurrent writers and does not scale beyond a single process. It also has no horizontal scaling path and no native hybrid search.
- **Supabase pgvector (managed).** Viable for a cloud demo, but ties the local deployment to an external service, adds network latency, and complicates offline development. Revisit if the deployment model changes.
- **Weaviate.** Comparable capabilities. Rejected because the operational surface (modules, schemas, cluster config) is larger than needed for this project’s scale.