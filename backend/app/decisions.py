"""Deterministic policy for turning evidence into a review decision."""

from .evidence import (
    Decision,
    DecisionKind,
    EvidenceLevel,
    Finding,
    Severity,
    ToolRun,
    ToolStatus,
)


def arbitrate(findings: list[Finding], tool_runs: list[ToolRun]) -> Decision:
    failed_tools = [run.tool for run in tool_runs if run.status is ToolStatus.FAILED]
    if failed_tools:
        tools = ", ".join(sorted(failed_tools))
        return Decision(
            decision=DecisionKind.MANUAL_REVIEW,
            reason="Required security coverage is incomplete",
            reasons=[f"Scanner failure: {tools}"],
        )

    blocking = [
        finding
        for finding in findings
        if (
            finding.evidence_level is EvidenceLevel.CONFIRMED
            and finding.severity is Severity.CRITICAL
        )
        or (
            finding.type == "tool_poisoning"
            and finding.evidence_level in {EvidenceLevel.CONFIRMED, EvidenceLevel.LIKELY}
        )
    ]
    if blocking:
        return Decision(
            decision=DecisionKind.REJECT,
            reason="Confirmed blocking security risk",
            reasons=sorted({finding.message for finding in blocking}),
            blocking_finding_ids=[finding.id for finding in blocking],
        )

    review_findings = [
        finding
        for finding in findings
        if finding.type == "tool_error"
        or finding.severity in {Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL}
    ]
    if review_findings:
        return Decision(
            decision=DecisionKind.MANUAL_REVIEW,
            reason="Security findings require human review",
            reasons=sorted({finding.message for finding in review_findings}),
            blocking_finding_ids=[finding.id for finding in review_findings],
        )

    if findings:
        return Decision(
            decision=DecisionKind.PASS,
            reason="Only informational or low-risk findings were detected",
            reasons=sorted({finding.message for finding in findings}),
        )

    return Decision(
        decision=DecisionKind.PASS,
        reason="All required checks completed without findings",
    )
