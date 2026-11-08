.PHONY: help up down dev logs reset build

help:
	@echo "Available commands:"
	@echo "  make up       - Start ALL services (production mode)"
	@echo "  make dev      - Start ALL services with hot-reload (dev mode)"
	@echo "  make down     - Stop all services"
	@echo "  make logs     - Tail logs"
	@echo "  make reset    - Stop, wipe volumes, and restart fresh"

up:
	docker compose up -d --build

dev:
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build

down:
	docker compose down

logs:
	docker compose logs -f

reset:
	docker compose down -v
	docker compose up -d --build