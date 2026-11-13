# Backend architecture

## Ingestion

POST /documents validates the format and nonempty/size limits, stores the raw file, creates document/job records, and submits a Celery task to Redis. Identical file checksums return the existing document/job.

The worker records processing, parses PDF/DOCX/TXT/Markdown, cleans repeated page-edge boilerplate and broken hyphenation, chunks text using the embedding tokenizer, generates dense and BM25 sparse vectors, writes SQLite chunk records and Qdrant points, then records completed. Failure is persisted in both job and document state and propagated to Celery.

Tables retain headers, rows, PDF bounding boxes, and provenance. Text chunks carry document name, file type, available author/date metadata, chapter/section, and source location. Table content remains together. DOCX uses block locations; TXT/Markdown use line ranges; PDF uses physical pages.

POST /documents/{id}/reindex reuses the stored upload and document ID. Embeddings are computed before replacing old indexed content. SQLite and Qdrant updates are not a distributed transaction; a failed replacement is reported and can be retried.

## Question workflow

1. Load the conversation and its recent bounded history.
2. Resolve explicit API filters and supported natural-language constraints.
3. Rewrite the question using history, then resolve constraints introduced by that contextual rewrite.
4. Search Qdrant using dense and sparse vectors and RRF fusion.
5. Cross-encoder rerank up to 20 candidates; select up to eight chunks with redundancy reduction, document diversity, per-document caps, and an embedding-tokenizer budget.
6. Merge new evidence with prior retrieval rounds under a larger cumulative context budget.
7. Ask the Analyst for a typed tool plan, execute source-validated deterministic tools, and obtain a strict sufficiency verdict with cited findings.
8. If evidence is missing, retrieve again using the missing-information request. At most three retrieval rounds run.
9. Generate a structured answer only after sufficiency. Pass findings, conflicts, and tool results to the Answer Agent.
10. Validate every chunk reference and exact supporting quote, run a separate grounding review, and format document/location citations plus a Sources list.
11. Persist the turn and return the conversation ID, answer state, sources, and executed tool results.

## Analyst tools

- Calculator: a bounded arithmetic AST interpreter over Decimal values. No eval, generated code, shell commands, or arbitrary function calls.
- Table extractor: retrieves structured table headers/rows from selected evidence.
- Document comparison: creates a source-linked comparison matrix across at least two documents.
- Data analysis: sum, mean, median, min/max, population standard deviation, difference, ratio, percentage change, descending rank, count, and frequency distribution.
- Retrieve more evidence: the Analyst's missing-information verdict drives the orchestrator's bounded feedback loop.

Numeric tool inputs must occur in exact source quotes. Table calculations use stored cells. Unknown evidence, fabricated values, malformed plans, invalid booleans, missing findings, and failed tools prevent approval.

## Persistence and deployment

FastAPI and Celery share uploaded files and SQLite volumes. Qdrant stores dense/sparse vectors and searchable payloads; Redis is the Celery broker/result backend. Groq is the external LLM provider. Embedding and reranking models run locally in the backend/worker.

A one-shot Compose migration service runs Alembic before API/worker startup. Production images explicitly install the ml extra. Ports are bound to localhost.

Cache/lock adapters and other domain interfaces from the original design remain in the repository, but response caching, semantic caching, distributed query locks, OCR, and provider failover are not wired into this workflow.
