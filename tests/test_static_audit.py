import json
from types import SimpleNamespace

from backend.app.checks import static_audit as scanner


def test_semgrep_output_is_normalized(monkeypatch, tmp_path):
    source = tmp_path / "server.py"
    source.write_text("eval(user_input)\n", encoding="utf-8")
    semgrep_output = {
        "results": [
            {
                "check_id": "mcp-audit.python.dynamic-code-execution",
                "path": str(source),
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {
                    "severity": "ERROR",
                    "message": "Dynamic execution",
                    "lines": "eval(user_input)",
                    "metadata": {},
                },
            }
        ],
        "errors": [],
    }
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(semgrep_output), stderr="")

    monkeypatch.setattr(scanner, "_semgrep_executable", lambda: "semgrep")
    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    findings = scanner.static_audit(str(tmp_path))

    assert findings[0]["rule_id"] == "mcp-audit.python.dynamic-code-execution"
    assert findings[0]["file"] == "server.py"
    assert findings[0]["evidence_level"] == "likely"
    assert "p/security-audit" in captured["command"]
    assert "auto" not in captured["command"]
    assert "--metrics=off" in captured["command"]
