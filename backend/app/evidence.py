"""Normalized evidence and result contracts shared by every scanner."""

from collections import Counter
from datetime import datetime
from enum import StrEnum
import hashlib
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    UNKNOWN = "unknown"
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceLevel(StrEnum):
    UNVERIFIED = "unverified"
    SUSPECTED = "suspected"
    LIKELY = "likely"
    CONFIRMED = "confirmed"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DecisionKind(StrEnum):
    PASS = "pass"
    MANUAL_REVIEW = "manual_review"
    REJECT = "reject"


class Finding(BaseModel):
    id: str
    rule_id: str
    type: str
    title: str
    message: str
    severity: Severity = Severity.UNKNOWN
    evidence_level: EvidenceLevel = EvidenceLevel.UNVERIFIED
    source: str
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    evidence: str | None = None
    remediation: str | None = None
    package: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolRun(BaseModel):
    tool: str
    status: ToolStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    error: str | None = None


class Decision(BaseModel):
    decision: DecisionKind
    reason: str
    reasons: list[str] = Field(default_factory=list)
    blocking_finding_ids: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    schema_version: str = "1.0"
    requested_ref: str
    resolved_commit: str
    findings: list[Finding]
    tool_runs: list[ToolRun]
    summary: dict[str, Any]
    decision: Decision


_SEVERITY_ALIASES = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "warn": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
}

_EVIDENCE_ALIASES = {
    "已确认": EvidenceLevel.CONFIRMED,
    "confirmed": EvidenceLevel.CONFIRMED,
    "likely": EvidenceLevel.LIKELY,
    "suspected": EvidenceLevel.SUSPECTED,
    "unverified": EvidenceLevel.UNVERIFIED,
}


def _normalize_severity(value: Any) -> Severity:
    normalized = str(value or "unknown").strip().lower()
    if normalized in _SEVERITY_ALIASES:
        return _SEVERITY_ALIASES[normalized]
    try:
        return Severity(normalized)
    except ValueError:
        return Severity.UNKNOWN


def _normalize_evidence_level(value: Any) -> EvidenceLevel:
    normalized = str(value or "unverified").strip().lower()
    return _EVIDENCE_ALIASES.get(normalized, EvidenceLevel.UNVERIFIED)


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None
    return converted if converted >= 1 else None


def _finding_id(raw: dict[str, Any], source: str, rule_id: str, message: str) -> str:
    supplied = raw.get("id")
    if supplied:
        return str(supplied)
    identity = "|".join(
        (
            source,
            rule_id,
            str(raw.get("file") or ""),
            str(raw.get("line") or ""),
            message,
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def normalize_finding(raw: dict[str, Any], default_source: str) -> Finding:
    """Convert a scanner-specific dictionary into the stable Finding contract."""

    source = str(raw.get("source") or raw.get("tool") or default_source)
    finding_type = str(raw.get("type") or "scanner_finding")
    rule_id = str(raw.get("rule_id") or f"{source}:{finding_type}")
    message = str(raw.get("message") or raw.get("summary") or "No description provided")
    title = str(raw.get("title") or message[:120])
    known_fields = {
        "id",
        "rule_id",
        "type",
        "title",
        "message",
        "summary",
        "severity",
        "evidence_level",
        "source",
        "tool",
        "file",
        "line",
        "end_line",
        "evidence",
        "remediation",
        "package",
        "version",
    }

    line = raw.get("line")
    end_line = raw.get("end_line")
    return Finding(
        id=_finding_id(raw, source, rule_id, message),
        rule_id=rule_id,
        type=finding_type,
        title=title,
        message=message,
        severity=_normalize_severity(raw.get("severity")),
        evidence_level=_normalize_evidence_level(raw.get("evidence_level")),
        source=source,
        file=str(raw["file"]) if raw.get("file") else None,
        line=_optional_positive_int(line),
        end_line=_optional_positive_int(end_line),
        evidence=str(raw["evidence"]) if raw.get("evidence") is not None else None,
        remediation=str(raw["remediation"]) if raw.get("remediation") else None,
        package=str(raw["package"]) if raw.get("package") else None,
        version=str(raw["version"]) if raw.get("version") else None,
        metadata={key: value for key, value in raw.items() if key not in known_fields},
    )


def summarize_findings(findings: list[Finding], tool_runs: list[ToolRun]) -> dict[str, Any]:
    severity_counts = Counter(finding.severity.value for finding in findings)
    type_counts = Counter(finding.type for finding in findings)
    return {
        "total_findings": len(findings),
        "by_severity": dict(sorted(severity_counts.items())),
        "by_type": dict(sorted(type_counts.items())),
        "tools": {
            run.tool: {
                "status": run.status.value,
                "finding_count": run.finding_count,
                "duration_ms": run.duration_ms,
            }
            for run in tool_runs
        },
    }

