"""Run Semgrep Community Edition with registry and project-local rules."""

import json
from pathlib import Path
import subprocess

from ..config import settings


class StaticAuditError(RuntimeError):
    """Raised when Semgrep cannot provide trustworthy scan output."""


def static_audit(workdir: str) -> list[dict]:
    rules_dir = Path(__file__).resolve().parents[2] / "rules"
    command = [
        "semgrep",
        "scan",
        "--config",
        "auto",
        "--config",
        str(rules_dir),
        "--json",
        "--quiet",
        "--metrics=off",
        "--timeout",
        str(settings.semgrep_rule_timeout_seconds),
        "--timeout-threshold",
        "3",
        "--max-target-bytes",
        str(settings.semgrep_max_target_bytes),
        workdir,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.semgrep_timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise StaticAuditError("Semgrep executable is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise StaticAuditError("Semgrep scan exceeded its global time limit") from exc

    if not result.stdout.strip():
        detail = result.stderr.strip() or "Semgrep produced no JSON output"
        raise StaticAuditError(detail[:2000])

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StaticAuditError("Semgrep output was not valid JSON") from exc

    if result.returncode != 0:
        errors = data.get("errors") or []
        detail = "; ".join(str(error.get("message") or error) for error in errors)
        detail = detail or result.stderr.strip() or f"Semgrep exited with {result.returncode}"
        raise StaticAuditError(detail[:2000])

    findings: list[dict] = []
    root = Path(workdir).resolve()
    for item in data.get("results", []):
        extra = item.get("extra") or {}
        start = item.get("start") or {}
        end = item.get("end") or {}
        raw_path = Path(str(item.get("path") or ""))
        try:
            candidate = raw_path if raw_path.is_absolute() else root / raw_path
            file_path = candidate.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            file_path = raw_path.as_posix().removeprefix("/src/")

        findings.append(
            {
                "rule_id": item.get("check_id") or "semgrep:unknown",
                "type": "static_vulnerability",
                "file": file_path,
                "line": start.get("line"),
                "end_line": end.get("line"),
                "severity": extra.get("severity", "UNKNOWN"),
                "evidence_level": "likely",
                "message": extra.get("message") or "Semgrep rule matched",
                "evidence": str(extra.get("lines") or "")[:1000],
                "remediation": (extra.get("metadata") or {}).get("fix"),
                "source": "semgrep",
                "metadata": {
                    "engine_kind": extra.get("engine_kind"),
                    "metadata": extra.get("metadata") or {},
                },
            }
        )

    return findings
