# Data model

## SQLite

| Table | Content |
|---|---|
| documents | UUID-based document ID, filename, type, unique checksum, lifecycle status, page count, error, access_tags, creation time. |
| chunks | UUID-based chunk ID, document ID, text, page, section, parent_id, metadata_json. |
| jobs | UUID job ID, document ID, queued/processing/completed/failed status, error, updated_at. |
| conversations | Conversation ID, local user ID, JSON messages with roles/content/UTC timestamps. |

Chunk metadata_json stores document_name, file_type, author, date, chapter, location, and table_data. Table data contains headers, rows, and an optional PDF bounding box. It is preserved when storing/restoring evidence.

Document deletion uses ORM cascades to remove related chunk and job records. Citation/source objects are returned with answers; they do not have a separate citations table.

Migration 20261107_task_requirements adds metadata_json and conversations without deleting existing documents. Existing chunk rows receive empty metadata; reindex uploads to populate the new fields and Qdrant payloads.

## Qdrant

Collection: documents. Named vectors: dense (384-dimensional cosine) and sparse (BM25).

Payload contains chunk_id, doc_id, page, section, text, parent_id, access_tags, and all chunk metadata fields. Normalized name_key, author_key, and section_key support case-insensitive/numeric metadata filters. Payload indexes cover document/page/access tags and the new filter fields.

Old points remain readable with default metadata. Reindexing is needed for filename/chapter/author/date filtering and structured table tools over old uploads.

## Agent contracts

- EvidencePackage: selected Chunk objects, structured Table objects, and diagnostics.
- AnalysisPlan: up to six typed tool requests.
- AnalysisResult: strict sufficiency/conflict verdict, missing information, source-linked findings, executed tool results.
- AnswerDraft: one to twelve answer blocks, each carrying one or more chunk references and exact source quotes.
- ChatResult: formatted answer, state, retrieval-loop count, evidence count, structured sources, tool results, conversation ID.

Structured model output is validated before use. Incomplete/empty Groq completions are rejected before JSON parsing.
