"""Render stored review results as portable Markdown reports."""

from typing import Any

from ..models import ReviewTask


def render_markdown(task: ReviewTask) -> str:
    result: dict[str, Any] = task.result or {}
    decision = result.get("decision") or {}
    summary = result.get("summary") or {}
    findings = result.get("findings") or []
    lines = [
        "# MCP Audit security report",
        "",
        f"- Task: `{task.id}`",
        f"- Repository: `{task.repo_url}`",
        f"- Requested ref: `{task.ref}`",
        f"- Resolved commit: `{task.resolved_commit or 'unresolved'}`",
        f"- Status: `{task.status}`",
        f"- Decision: `{decision.get('decision', 'unavailable')}`",
        f"- Reason: {decision.get('reason', task.error or 'No result')}",
        f"- Total findings: {summary.get('total_findings', len(findings))}",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No findings were recorded.")
    for index, finding in enumerate(findings, 1):
        location = finding.get("file") or "repository"
        if finding.get("line"):
            location = f"{location}:{finding['line']}"
        lines.extend(
            [
                f"### {index}. {finding.get('title') or finding.get('rule_id')}",
                "",
                f"- Rule: `{finding.get('rule_id', 'unknown')}`",
                f"- Severity: `{finding.get('severity', 'unknown')}`",
                f"- Evidence level: `{finding.get('evidence_level', 'unverified')}`",
                f"- Location: `{location}`",
                "",
                str(finding.get("message") or "No description"),
                "",
                "Remediation: "
                f"{finding.get('remediation') or 'Review and remediate as appropriate.'}",
                "",
            ]
        )
    return "\n".join(lines)
