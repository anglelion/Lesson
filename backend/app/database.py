"""Database engine, session factory, and declarative model base."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables for local development outside the migration workflow."""

    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
