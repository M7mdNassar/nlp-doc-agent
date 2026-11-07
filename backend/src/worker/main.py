from src.infrastructure.queue.celery_app import celery_app

# Entrypoint for the worker Docker container
celery = celery_app
