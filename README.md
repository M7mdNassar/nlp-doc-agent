# NLP Doc Agent

A production-grade, evidence-first document question-answering system. Upload PDF, Word, plain-text, or Markdown documents and ask questions in natural language. Answers are generated through a deterministic multi-agent pipeline and are grounded in document evidence with precise page and document citations.

## What It Does

- **Supports multiple document formats:** Ingests PDF, DOCX, TXT, and Markdown files.
- **Processes documents for retrieval:** Parses, cleans, chunks, and embeds document content into a vector store, retaining rich metadata such as page, section, author, and document type.
- **Uses a multi-agent pipeline:** Coordinates three agents — **Retriever**, **Analyst**, and **Answer** — through a deterministic **Orchestrator**.
- **Combines retrieval methods:** Uses semantic search, keyword search, metadata filtering, and reranking to identify relevant evidence.
- **Analyzes retrieved content:** Supports calculations, table extraction, document comparison, and data analysis based on retrieved evidence.
- **Provides traceable answers:** Returns precise inline citations that open the corresponding source chunk in the user interface.

## Technology Stack

### Backend

- FastAPI and Python 3.12
- Qdrant for vector storage
- Redis for caching and queuing
- SQLite for metadata storage
- Groq for LLM inference
- Self-hosted `bge-small` for embeddings
- Self-hosted `bge-reranker-base` for reranking

### Frontend

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui
- Vercel AI SDK

### Deployment

- Docker Compose
- Five local services

## Quick Start

### Prerequisites

Make sure Docker with Docker Compose is installed and running. The project also uses `make` for its convenience commands.

### Run the Application

```bash
git clone <repo-url>
cd nlp-doc-chat
cp .env.example .env
make up
```

Before starting the application, review `.env` and configure any required environment variables. Refer to `.env.example` for the available settings. Do not commit your `.env` file or any secrets.

Once the services are running, open:

- **Frontend:** [http://localhost:3000](http://localhost:3000)
- **Backend API documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

## Documentation

- [Architecture](docs/architecture.md) — system structure and component responsibilities.
- [Reliability Invariants](docs/reliability.md) — rules and guarantees the system is designed to maintain.
- [API Reference](docs/api-reference.md) — API endpoints and usage details.
- [Data Model](docs/data-model.md) — data structures and relationships.
- [Deployment](docs/deployment.md) — deployment and configuration guidance.
- [Decision Records](docs/decisions/README.md) — architectural and technical decisions.
- [Contributing Guide](CONTRIBUTING.md) — development setup, Git workflow, contribution rules, and code review standards.

## Contributing

Contributions are welcome. Before making changes, read the [Contributing Guide](CONTRIBUTING.md) for development setup, branching conventions, commit messages, pull request requirements, testing, and code review standards.

## License

See the [LICENSE](LICENSE) file in the root of the repository for the project's license terms.
