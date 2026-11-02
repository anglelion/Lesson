# app/checks/static.py
import subprocess, json, os

def static_audit(workdir: str) -> list[dict]:
    out_file = os.path.join(workdir, "semgrep.json")
    subprocess.run(
        ["semgrep", "--config=auto", "--json", "--output", out_file, workdir],
        capture_output=True, timeout=300
    )
    if not os.path.exists(out_file):
        return [{"type": "tool_error", "tool": "semgrep",
                 "message": "semgrep 未产生输出，覆盖缺口"}]

    with open(out_file) as f:
        data = json.load(f)

    findings = []
    for r in data.get("results", []):
        findings.append({
            "rule_id": r.get("check_id"),
            "file": r.get("path"),
            "line": r.get("start", {}).get("line"),
            "severity": r.get("extra", {}).get("severity"),
            "message": r.get("extra", {}).get("message"),
            "evidence": r.get("extra", {}).get("lines", "")[:200],  # 脱敏前先截断
            "source": "semgrep"
        })
    return findings