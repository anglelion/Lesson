"""HTTP API for submitting and inspecting repository reviews."""

from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, HTTPException, status
from redis import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import SessionLocal, engine
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
                    status="pending",
                )
            )
    except SQLAlchemyError as exc:
        logger.exception("Failed to persist review task")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to create review task",
        ) from exc

    run_review.delay(task_id, req.repo_url, req.ref, req.deploy_type)
    return TaskAccepted(task_id=task_id, status="pending")


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
        status=task.status,
        result=task.result,
        created_at=task.created_at,
    )

