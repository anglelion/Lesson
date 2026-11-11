"""Persistent data models for review tasks."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ReviewTask(Base):
    """A repository review request and its current result."""

    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    repo_url: Mapped[str] = mapped_column(String, index=True)
    ref: Mapped[str] = mapped_column(String)
    resolved_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    deploy_type: Mapped[str] = mapped_column(String(16), default="stdio")
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    stage: Mapped[str] = mapped_column(String, default="queued", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

