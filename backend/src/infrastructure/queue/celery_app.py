from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "nlp_doc_chat_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["src.infrastructure.queue.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)
