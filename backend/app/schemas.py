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


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: dict[str, Any] | None
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str

