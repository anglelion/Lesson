# app/celery_app.py
from celery import Celery

# 配置 Redis 的 Broker 和 Backend
celery = Celery(
    "mcp_audit",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1"
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
)