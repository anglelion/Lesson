from backend.app.checks.mcp_semantic import mcp_semantic_check


def test_vulnerable_fixture_detects_tool_poisoning():
    findings = mcp_semantic_check("examples/vulnerable-mcp")
    assert any(item["type"] == "tool_poisoning" for item in findings)


def test_safe_fixture_has_no_tool_poisoning():
    findings = mcp_semantic_check("examples/safe-mcp")
    assert not any(item["type"] == "tool_poisoning" for item in findings)
