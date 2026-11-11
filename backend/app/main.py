"""HTTP API for submitting and inspecting repository reviews."""

from contextlib import asynccontextmanager
from datetime import datetime
import logging
import uuid

from fastapi import FastAPI, HTTPException, status
from redis import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import SessionLocal, engine
from .domain import ReviewStage, TaskStatus
from .models import ReviewTask
from .schemas import HealthResponse, SubmitRequest, TaskAccepted, TaskResponse
from .tasks import run_review


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Release pooled database connections during application shutdown."""

    yield
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
def liveness() -> HealthResponse:
    return HealthResponse(
        status="alive",
        service=settings.app_name,
        environment=settings.environment,
    )


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
def readiness() -> HealthResponse:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        redis_client = Redis.from_url(settings.redis_broker_url)
        redis_client.ping()
        redis_client.close()
    except Exception as exc:
        logger.exception("Readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required infrastructure is unavailable",
        ) from exc

    return HealthResponse(
        status="ready",
        service=settings.app_name,
        environment=settings.environment,
    )


@app.post(
    "/api/submit",
    response_model=TaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["reviews"],
)
def submit(req: SubmitRequest) -> TaskAccepted:
    task_id = str(uuid.uuid4())

    try:
        with SessionLocal.begin() as db:
            db.add(
                ReviewTask(
                    id=task_id,
                    repo_url=req.repo_url,
                    ref=req.ref,
                    description=req.description,
                    deploy_type=req.deploy_type,
                    status=TaskStatus.PENDING,
                    stage=ReviewStage.QUEUED,
                )
            )
    except SQLAlchemyError as exc:
        logger.exception("Failed to persist review task")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to create review task",
        ) from exc

    try:
        run_review.apply_async(
            args=[task_id, req.repo_url, req.ref, req.deploy_type],
            task_id=task_id,
        )
    except Exception as exc:
        logger.exception("Failed to dispatch review task")
        with SessionLocal.begin() as db:
            task = db.get(ReviewTask, task_id)
            if task is not None:
                task.status = TaskStatus.FAILED
                task.stage = ReviewStage.FAILED
                task.error = "Unable to dispatch background task"
                task.finished_at = datetime.utcnow()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to dispatch review task",
        ) from exc

    return TaskAccepted(
        task_id=task_id,
        status=TaskStatus.PENDING,
        stage=ReviewStage.QUEUED,
    )


@app.get(
    "/api/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["reviews"],
)
def get_task(task_id: str) -> TaskResponse:
    with SessionLocal() as db:
        task = db.get(ReviewTask, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return TaskResponse(
        task_id=task.id,
        repo_url=task.repo_url,
        requested_ref=task.ref,
        resolved_commit=task.resolved_commit,
        deploy_type=task.deploy_type,
        status=task.status,
        stage=task.stage,
        result=task.result,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )

