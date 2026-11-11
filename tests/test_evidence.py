from backend.app.clock import utc_now
from backend.app.decisions import arbitrate
from backend.app.evidence import EvidenceLevel, Severity, ToolRun, ToolStatus, normalize_finding


def test_normalization_and_blocking_decision():
    finding = normalize_finding(
        {
            "rule_id": "x",
            "type": "tool_poisoning",
            "message": "bad",
            "severity": "CRITICAL",
            "evidence_level": "confirmed",
        },
        "test",
    )
    now = utc_now()
    decision = arbitrate(
        [finding],
        [
            ToolRun(
                tool="test",
                status=ToolStatus.SUCCESS,
                started_at=now,
                finished_at=now,
                duration_ms=0,
                finding_count=1,
            )
        ],
    )
    assert finding.severity is Severity.CRITICAL
    assert finding.evidence_level is EvidenceLevel.CONFIRMED
    assert decision.decision == "reject"


def test_failed_scanner_never_passes():
    now = utc_now()
    decision = arbitrate(
        [],
        [
            ToolRun(
                tool="test",
                status=ToolStatus.FAILED,
                started_at=now,
                finished_at=now,
                duration_ms=0,
                finding_count=0,
                error="failed",
            )
        ],
    )
    assert decision.decision == "manual_review"
