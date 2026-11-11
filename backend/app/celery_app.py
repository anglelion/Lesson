"""Celery application shared by the API and workers."""

from celery import Celery

from .config import settings

celery = Celery(
    "mcp_audit",
    broker=settings.redis_broker_url,
    backend=settings.redis_result_url,
    include=["backend.app.tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.task_time_limit_seconds,
)
