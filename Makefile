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
	@echo "  make seed     - Seed sample documents"
	@echo "  make reset    - Wipe volumes and restart fresh"

up:
	docker compose up -d --build

down:
	docker compose down

dev:
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build

logs:
	docker compose logs -f

test:
	@echo "Running tests (will be implemented in later phases)"
	# docker compose exec backend pytest
	# docker compose exec frontend npm run test

lint:
	@echo "Running linters (will be implemented in later phases)"
	# docker compose exec backend ruff check .
	# docker compose exec frontend npm run lint

format:
	@echo "Running formatters (will be implemented in later phases)"
	# docker compose exec backend ruff format .
	# docker compose exec frontend npm run format

codegen:
	@echo "Generating OpenAPI client (will be implemented in later phases)"
	# docker compose exec frontend npx openapi-typescript-codegen ...

seed:
	docker compose exec backend python /app/infrastructure/scripts/seed_sample_documents.py

reset:
	docker compose down -v
	docker compose up -d --build