"""Celery orchestration for repository security reviews."""

from datetime import datetime
import logging
from time import perf_counter
from typing import Any, Callable

from .celery_app import celery
from .checks.dependency import dependency_check
from .checks.static_audit import static_audit
from .checks.transport import transport_check
from .config import settings
from .database import SessionLocal
from .decisions import arbitrate
from .domain import ReviewStage, TaskStatus
from .evidence import (
    Finding,
    ReviewResult,
    ToolRun,
    ToolStatus,
    normalize_finding,
    summarize_findings,
)
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


def _execute_check(
    tool: str,
    check: Callable[[], list[dict]],
) -> tuple[list[Finding], ToolRun]:
    started_at = datetime.utcnow()
    started_counter = perf_counter()
    try:
        raw_findings = check()
        findings = [normalize_finding(raw, tool) for raw in raw_findings]
        tool_errors = [finding for finding in findings if finding.type == "tool_error"]
        status = ToolStatus.FAILED if tool_errors else ToolStatus.SUCCESS
        error = "; ".join(finding.message for finding in tool_errors) or None
    except Exception as exc:
        logger.exception("%s check failed", tool)
        error = str(exc)[:2000]
        findings = [
            normalize_finding(
                {
                    "type": "tool_error",
                    "tool": tool,
                    "message": error,
                },
                tool,
            )
        ]
        status = ToolStatus.FAILED

    finished_at = datetime.utcnow()
    run = ToolRun(
        tool=tool,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=max(0, int((perf_counter() - started_counter) * 1000)),
        finding_count=len(findings),
        error=error,
    )
    return findings, run


def _run_checks(workdir: str, deploy_type: str) -> tuple[list[Finding], list[ToolRun]]:
    checks: list[tuple[str, Callable[[], list[dict]]]] = [
        ("semgrep", lambda: static_audit(workdir)),
        ("osv", lambda: dependency_check(workdir)),
        ("transport", lambda: transport_check(workdir, deploy_type)),
    ]
    findings: list[Finding] = []
    tool_runs: list[ToolRun] = []
    for tool, check in checks:
        check_findings, run = _execute_check(tool, check)
        findings.extend(check_findings)
        tool_runs.append(run)
    return findings, tool_runs


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
            findings, tool_runs = _run_checks(str(snapshot.path), deploy_type)

        _update_task(task_id, stage=ReviewStage.ARBITRATING)
        decision = arbitrate(findings, tool_runs)
        result_model = ReviewResult(
            requested_ref=requested_ref,
            resolved_commit=snapshot.commit_sha,
            findings=findings,
            tool_runs=tool_runs,
            summary=summarize_findings(findings, tool_runs),
            decision=decision,
        )
        result = result_model.model_dump(mode="json")
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
