# Extending security rules

General Semgrep rules live in `backend/rules`. Add YAML rules with a stable `mcp-audit.*` ID,
message, language, severity, and the narrowest reliable pattern. MCP behavior checks belong in
`backend/app/checks/mcp_semantic.py`; transport configuration checks belong in `transport.py`.

Every finding should provide a stable rule ID, type, message, severity, evidence level, source,
location when known, redacted evidence, and actionable remediation. A new scanner must raise when
coverage is incomplete rather than returning an empty result.

