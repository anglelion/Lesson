"""Shared domain values for review state transitions."""

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ReviewStage(StrEnum):
    QUEUED = "queued"
    FETCHING = "fetching"
    SCANNING = "scanning"
    ARBITRATING = "arbitrating"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
