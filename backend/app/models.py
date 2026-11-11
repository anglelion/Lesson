"""Persistent data models for review tasks."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ReviewTask(Base):
    """A repository review request and its current result."""

    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    repo_url: Mapped[str] = mapped_column(String, index=True)
    ref: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

