# Data Model

This document describes the core entities, value objects, ports, and conventions used across the NLP Doc Chat backend.

## Table of Contents

- [Layers](#layers)
- [Entities](#entities)
- [Value Objects](#value-objects)
- [Ports](#ports)
- [Qdrant Payload Convention](#qdrant-payload-convention)
- [SQLite Schema](#sqlite-schema)
- [Conventions](#conventions)

## Layers

The backend uses four main building blocks:

| Building block | Responsibility |
|---|---|
| **Entities** | Have identity and behavior, and enforce domain invariants. |
| **Value objects** | Are immutable, validated, and compared by value. |
| **Ports** | Define protocols through which the application communicates with external systems. |
| **Adapters** | Implement ports and live in `infrastructure/`. |

## Entities

Entities live in `domain/entities/`.

| Entity | Responsibility |
|---|---|
| `Document` | Represents an uploaded document. Tracks its lifecycle (`queued → parsing → embedding → indexed → failed`) and owns its metadata and access tags. |
| `Chunk` | Represents a retrievable unit of a document. Carries `doc_id`, `page`, `section`, `parent_id`, and text. |
| `Table` | Represents a structured table extracted from a document. Carries provenance information (page and row range) and a confidence score. |
| `EvidencePackage` | Defines the contract between the Retriever and the Analyst. Contains selected chunks, tables, and diagnostics. |
| `Citation` | Represents a resolved reference from an answer to a specific chunk. |
| `Conversation` | Represents a sequence of turns bound to a user and, optionally, to a set of documents. |
| `Job` | Tracks an ingestion job, including its current step, error, and retry count. |

## Value Objects

Value objects live in `domain/value_objects/`.

| Value object | Purpose |
|---|---|
| `DocumentId`, `ChunkId`, `JobId` | Represent prefixed, validated identifiers. |
| `PageRange` | Represents a page or page range and validates that `start ≤ end`. |
| `TokenBudget` | Represents a bounded token count for a call. |
| `Confidence` | Represents a normalized confidence value in the range `[0, 1]`. |

Value objects are immutable. Their constructors validate input and raise domain exceptions when values are invalid.

## Ports

Ports live in `domain/ports/` and are defined as Python `Protocol` classes. They describe **what** the application needs, not **how** the capability is implemented.

| Port | Responsibility |
|---|---|
| `LLMClient` | Completes or streams a prompt and provides token accounting. |
| `Embedder` | Converts text into a dense vector. |
| `Reranker` | Scores query-and-chunk pairs. |
| `VectorStore` | Supports upsert, search (dense, sparse, and hybrid), and delete operations. |
| `ExactCache`, `SemanticCache`, `EmbeddingCache` | Provide cache read and write operations with a time-to-live (TTL). |
| `Lock` | Acquires and releases named locks. |
| `DocumentRepository`, `ChunkRepository`, `JobRepository`, `ConversationRepository`, `CitationRepository` | Persist and retrieve domain entities. |
| `DocumentParser` | Parses a file into structured elements. |
| `OCR` | Extracts text from images. |
| `Tool` | Defines a named callable with a schema and a bounded execution contract. |
| `JobQueue` | Enqueues and tracks background tasks. |

Adapters live in `infrastructure/` and are connected to ports in `api/dependencies/providers.py`. Application code depends on the ports rather than directly on infrastructure implementations.

## Qdrant Payload Convention

Every chunk vector in Qdrant carries a payload with the following structure:

```json
{
  "doc_id": "doc_01HX...",
  "doc_name": "paper.pdf",
  "page": 12,
  "section": "4.2",
  "chunk_id": "chunk_01HX...",
  "parent_id": "chunk_01HX...",
  "content": "Model X achieves 92.4% accuracy...",
  "doc_type": "pdf",
  "author": "A. Researcher",
  "date": "2024-06-01",
  "ocr_confidence": 0.98,
  "access_tags": ["team:research"],
  "embedding_model": "bge-small-en-v1.5",
  "embedding_version": "1.0.0"
}
```

Payload indexes are created for these fields:

- `doc_id`
- `doc_name`
- `page`
- `section`
- `doc_type`
- `access_tags`
- `embedding_version`

The metadata filter and cache invalidation processes depend on these indexed fields.

## SQLite Schema

The following is a high-level overview of the SQLite tables:

| Table | Stored information |
|---|---|
| `documents` | Document registry: ID, name, type, checksum, status, page count, and access tags. |
| `chunks` | Chunk registry: ID, document ID, page, section, parent ID, text, and embedding version. |
| `jobs` | Ingestion jobs: ID, document ID, status, current step, error, and timestamps. |
| `citations` | Resolved citations: ID, answer ID, and chunk ID. |
| `conversations` | Conversation history: ID, user ID, and turns. |

Foreign keys are enabled. Deletes cascade where appropriate, including the document-to-chunks-to-citations relationship.

## Conventions

- **Identifiers:** All IDs use a prefix and are ULID-based: `doc_`, `chunk_`, `job_`, and `conv_`.
- **Timestamps:** Timestamps use UTC and ISO 8601 format. They are stored as ISO strings in SQLite.
- **Enums:** Enum values are stored as strings rather than integers for readability and forward compatibility.
- **Embedding metadata:** Every chunk must include `embedding_model` and `embedding_version`. These fields support re-embedding when the embedding model changes.
