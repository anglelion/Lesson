"""API request and response schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SubmitRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=2048)
    ref: str = Field(default="HEAD", min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    deploy_type: Literal["stdio", "http"] = "stdio"


class TaskAccepted(BaseModel):
    task_id: str
    status: Literal["pending"]
    stage: Literal["queued"]


class TaskResponse(BaseModel):
    task_id: str
    repo_url: str
    requested_ref: str
    resolved_commit: str | None
    deploy_type: str
    status: str
    stage: str
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
