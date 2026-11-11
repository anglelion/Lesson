"""Celery orchestration for repository security reviews."""

from datetime import datetime
import logging
from typing import Any

from .celery_app import celery
from .checks.dependency import dependency_check
from .checks.static_audit import static_audit
from .checks.transport import transport_check
from .config import settings
from .database import SessionLocal
from .domain import ReviewStage, TaskStatus
from .models import ReviewTask
from .services.repository import acquire_snapshot


logger = logging.getLogger(__name__)


def _update_task(task_id: str, **changes: Any) -> None:
    with SessionLocal.begin() as db:
        task = db.get(ReviewTask, task_id)
        if task is None:
            raise LookupError(f"Review task {task_id} does not exist")
        for field, value in changes.items():
            setattr(task, field, value)


def _run_checks(workdir: str, deploy_type: str) -> list[dict]:
    findings: list[dict] = []

    try:
        findings.extend(static_audit(workdir))
    except Exception as exc:
        logger.exception("Static audit failed")
        findings.append(
            {
                "type": "tool_error",
                "tool": "semgrep",
                "message": str(exc),
            }
        )

    try:
        findings.extend(dependency_check(workdir))
    except Exception as exc:
        logger.exception("Dependency audit failed")
        findings.append(
            {
                "type": "tool_error",
                "tool": "osv",
                "message": str(exc),
            }
        )

    try:
        findings.extend(transport_check(workdir, deploy_type))
    except Exception as exc:
        logger.exception("Transport audit failed")
        findings.append(
            {
                "type": "tool_error",
                "tool": "transport",
                "message": str(exc),
            }
        )

    return findings


@celery.task(bind=True, max_retries=2, name="mcp_audit.run_review")
def run_review(
    self,
    task_id: str,
    repo_url: str,
    requested_ref: str,
    deploy_type: str,
) -> dict:
    """Acquire the exact requested revision, scan it, and persist the outcome."""

    try:
        _update_task(
            task_id,
            status=TaskStatus.RUNNING,
            stage=ReviewStage.FETCHING,
            error=None,
            started_at=datetime.utcnow(),
            finished_at=None,
        )

        with acquire_snapshot(
            repo_url=repo_url,
            requested_ref=requested_ref,
            timeout_seconds=settings.clone_timeout_seconds,
        ) as snapshot:
            _update_task(
                task_id,
                resolved_commit=snapshot.commit_sha,
                stage=ReviewStage.SCANNING,
            )
            findings = _run_checks(str(snapshot.path), deploy_type)

        _update_task(task_id, stage=ReviewStage.ARBITRATING)
        decision = {"decision": "pass", "reason": "No findings"}
        if findings:
            decision = {
                "decision": "manual_review",
                "reason": f"Review produced {len(findings)} finding(s)",
            }

        result = {
            "requested_ref": requested_ref,
            "resolved_commit": snapshot.commit_sha,
            "findings": findings,
            "decision": decision,
        }
        _update_task(
            task_id,
            status=TaskStatus.SUCCESS,
            stage=ReviewStage.COMPLETED,
            result=result,
            error=None,
            finished_at=datetime.utcnow(),
        )
        return result

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"[:4000]
        logger.exception("Review task %s failed", task_id)

        if self.request.retries < self.max_retries:
            _update_task(
                task_id,
                status=TaskStatus.PENDING,
                stage=ReviewStage.RETRYING,
                error=error_message,
            )
            raise self.retry(
                exc=exc,
                countdown=settings.task_retry_delay_seconds,
            )

        _update_task(
            task_id,
            status=TaskStatus.FAILED,
            stage=ReviewStage.FAILED,
            error=error_message,
            finished_at=datetime.utcnow(),
        )
        raise
