# Task-7 backend implementation

Frontend work is excluded. This document maps the PDF requirements to the updated backend and explains the behavior changes.

| Requirement | Before | After |
|---|---|---|
| Preparation: PDF/Word/text (p. 3) | PDF/TXT/Markdown parsers; DOCX failed. | DOCX paragraphs/headings/tables supported alongside existing formats. |
| Cleaning (pp. 2-3) | Primarily whitespace splitting. | Repeated page-edge boilerplate removal, Unicode/whitespace cleanup, broken-hyphen repair. |
| Chunk/embed/store (p. 3) | Rough word splitting; metadata limited. | Embedding-tokenizer chunk limits, overlap, native source locations, structured table storage, dense/sparse indexing. |
| Query rewriting (pp. 6-7) | Optional history parameter never supplied. | Conversation turns persist in SQLite; recent history reaches the rewriter. |
| Semantic and keyword retrieval (pp. 7-8) | Dense/BM25 hybrid search existed. | Preserved; BM25 uses its query-specific embedding method. |
| Metadata filters (pp. 8-9) | Internal doc/page filters not reachable from chat. | Strict API filters, supported natural-language constraints, searchable filename/chapter/section/author/date/type metadata. Unknown files do not widen the search. |
| Reranking (pp. 9-10) | Cross-encoder top-eight truncation. | Rerank up to 20, then select evidence with diversity, redundancy reduction, per-document caps, and a context budget. |
| Context selector (p. 10) | Top-k only. | Explicit context-selection component. |
| Calculator (p. 11) | No calculator tool. | Bounded deterministic Decimal arithmetic over source-validated numeric inputs. |
| Table extractor (p. 12) | PDF tables converted to plain Markdown. | PDF/DOCX tables retain rows/headers/provenance and are available to the Analyst as structured data. |
| Document comparison (pp. 12-13) | No comparison tool. | Source-linked comparison matrices spanning multiple documents. |
| Data analysis (pp. 13-14) | No numerical analysis tool. | Means, sums, medians, min/max, differences, ratios, percent change, standard deviation, ranking, counts, distributions. |
| Feedback loop (p. 14) | New retrieval overwrote earlier evidence; generation continued after rejection. | Evidence is merged under a budget; missing facts drive retries; exhaustion returns insufficient_evidence without generating an answer. |
| Answer synthesis/citations (pp. 2, 4-5) | Answer saw raw chunks but no analytical findings; invalid citation markers were removed while claims remained. | Typed findings/tool outputs reach Answer; every block carries exact source references; reference/quote validation plus independent grounding review precede formatting. |

## Other backend corrections

- Strict boolean/schema validation prevents string "false" from being treated as approval.
- Incomplete or empty provider completions are rejected before parsing.
- Jobs transition from queued through processing to completed/failed, including initialization failures.
- Reindexing preserves document IDs and reuses stored uploads; duplicate uploads return existing IDs.
- Production Docker stages install the ML extra; lockfile use is frozen.
- A migration service gates backend/worker startup, and online Alembic migrations respect DATABASE_URL.
- SQLite stores conversation history and chunk metadata/table data. Existing document rows survive the migration.
- Documentation now describes the implemented API instead of unimplemented authentication, streaming, caching, and OCR features.

## Verification and deployment

Installation and upgrade commands are documented in [deployment.md](deployment.md). The automated suite covers generated PDF/DOCX parsing, cleaning/chunking, tools and invalid inputs, citation rejection, conversation persistence, metadata retrieval through in-memory Qdrant, ingestion/reindexing, worker status, API contracts, and upgrading an existing SQLite database without losing documents.

The optional live smoke script uses real embeddings, reranking, and Groq over synthetic documents. It checks the mean of 92, 95, and 89 (92), three source references, and a follow-up identifying Model B at 95%.

Latest verification, 2026-11-08:

- The latest automated run passed 101 tests. Ruff lint passed, and mypy passed across 113 source files. The answer-quality source files remain unchanged since that run.
- Formatting passes for the files changed in the answer-quality update. A repository-wide formatting check still flags the pre-existing initial migration and worker entry point; these are not runtime failures.
- The updated backend image has been built and the backend container recreated. Its deployed answer-generation, orchestration, and verdict-schema files match the tested source.
- The running `/health` reports SQLite, Qdrant, and Redis as healthy; `/docs` returns HTTP 200.
- Both previously pending questions now pass through the deployed `POST /chat` API with real retrieval and Groq: a project summary retains the approximate throughput gain, fixed-timing baseline, and simulation qualification; the direct simulation question does not invent the origin of the input data or exclude real observations without evidence. Both responses include source references.
- All eight synthetic answer-quality checks passed against Groq in the updated backend container. The checks reject omitted simulation qualifications, invented data origins, unsupported absolute exclusions, and invented production claims; they accept appropriately scoped claims and a generated summary. This completes the repeat check previously interrupted by provider quota limits.
- Earlier isolated live pipeline verification covered BGE embeddings/reranking, the mean of 92, three sources, and a successful conversational follow-up. Production and development Compose configurations also passed validation.

The PDF's backend workflow is implemented and verified for the task's local, single-user scope. Frontend work remains excluded. GitHub-hosted CI has not been run. Model-based grounding can still make mistakes, and provider quota limits can prevent chat requests even when service health is good; see [reliability.md](reliability.md) for the other limits.

No additional Docker commands, database migration, reindexing, or replacement provider key are needed for this already-updated local installation. For another installation upgrading from the original schema or images, follow [deployment.md](deployment.md), including rebuilding containers, applying migrations, and reindexing older uploads to populate metadata and tables. A volume reset is not required.
