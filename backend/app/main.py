"""HTTP API for submitting and inspecting repository reviews."""

from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import SessionLocal, engine
from .domain import ReviewStage, TaskStatus
from .models import ReviewTask
from .schemas import HealthResponse, SubmitRequest, TaskAccepted, TaskListResponse, TaskResponse
from .services.reports import render_markdown
from .tasks import run_review


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Release pooled database connections during application shutdown."""

    yield
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.8.0",
    debug=settings.debug,
    lifespan=lifespan,
)
frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")


def _task_response(task: ReviewTask) -> TaskResponse:
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

    return _task_response(task)


@app.get("/api/tasks", response_model=TaskListResponse, tags=["reviews"])
def list_tasks(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(ReviewTask)) or 0
        tasks = db.scalars(
            select(ReviewTask)
            .order_by(ReviewTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    return TaskListResponse(
        items=[_task_response(task) for task in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post("/api/tasks/{task_id}/retry", response_model=TaskAccepted, tags=["reviews"])
def retry_task(task_id: str) -> TaskAccepted:
    with SessionLocal.begin() as db:
        task = db.get(ReviewTask, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.status != TaskStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only failed tasks can be retried",
            )
        task.status = TaskStatus.PENDING
        task.stage = ReviewStage.QUEUED
        task.error = None
        task.result = None
        task.finished_at = None
        repo_url, requested_ref, deploy_type = task.repo_url, task.ref, task.deploy_type

    run_review.apply_async(
        args=[task_id, repo_url, requested_ref, deploy_type],
        task_id=f"{task_id}:retry:{uuid.uuid4()}",
    )
    return TaskAccepted(task_id=task_id, status=TaskStatus.PENDING, stage=ReviewStage.QUEUED)


@app.get("/api/tasks/{task_id}/report", tags=["reviews"])
def download_report(task_id: str, format: str = Query(default="markdown", pattern="^(markdown|json)$")) -> Response:
    with SessionLocal() as db:
        task = db.get(ReviewTask, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if format == "json":
            content = json.dumps(_task_response(task).model_dump(mode="json"), ensure_ascii=False, indent=2)
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="mcp-audit-{task_id}.json"'},
            )
        return PlainTextResponse(
            render_markdown(task),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="mcp-audit-{task_id}.md"'},
        )


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    index = frontend_dir / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frontend not installed")
    return FileResponse(index)

