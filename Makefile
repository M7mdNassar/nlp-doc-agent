.PHONY: help up down dev logs test lint format codegen seed reset

help:
	@echo "Available commands:"
	@echo "  make up       - Start all services"
	@echo "  make down     - Stop all services"
	@echo "  make dev      - Start with hot-reload"
	@echo "  make logs     - Tail logs"
	@echo "  make test     - Run all tests"
	@echo "  make lint     - Run linters"
	@echo "  make format   - Auto-format code"
	@echo "  make codegen  - Generate TS client from OpenAPI"
	@echo "  make seed FILES=path - Upload files (paths relative to backend/)"
	@echo "  make reset    - Wipe volumes and restart fresh"

up:
	docker compose -f docker-compose.yml up -d --build qdrant redis migrate backend worker

down:
	docker compose down

dev:
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build qdrant redis migrate backend worker

logs:
	docker compose logs -f

test:
	cd backend && uv run --no-sync pytest

lint:
	cd backend && uv run --no-sync ruff check .
	cd backend && uv run --no-sync mypy src

format:
	cd backend && uv run --no-sync ruff format .

codegen:
	@echo "Generating OpenAPI client (will be implemented in later phases)"
	# docker compose exec frontend npx openapi-typescript-codegen ...

seed:
	cd backend && uv run --no-sync python ../infrastructure/scripts/seed_sample_documents.py $(FILES)

reset:
	docker compose down -v
	docker compose up -d --build
