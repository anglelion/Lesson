# app/checks/dependency.py
import urllib.request
import json
import os
import re

OSV_API = "https://api.osv.dev/v1/query"


def extract_severity(vuln: dict) -> str:
    try:
        if "database_specific" in vuln and "severity" in vuln["database_specific"]:
            return vuln["database_specific"]["severity"]
        if "severity" in vuln:
            for sev in vuln["severity"]:
                if sev.get("type") == "CVSS_V3":
                    return "HIGH"
    except Exception:
        pass
    return "UNKNOWN"


def query_osv(package: str, version: str, ecosystem: str = "PyPI") -> list:
    payload = {"package": {"name": package, "ecosystem": ecosystem}, "version": version}
    req = urllib.request.Request(
        OSV_API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("vulns", [])
    except Exception as e:
        print(f"[依赖检查] OSV 查询 {package} 失败: {e}")
        return []


def parse_dependencies(workdir: str):
    deps = []
    possible_files = ["requirements.txt", "requirements-dev.txt", "pyproject.toml"]

    for filename in possible_files:
        filepath = os.path.join(workdir, filename)
        if not os.path.exists(filepath):
            continue

        print(f"[依赖检查] 发现依赖文件: {filename}")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配固定版本 (例如 requests==2.28.1)
        matches = re.findall(r'([a-zA-Z0-9_\-]+)\s*(==)\s*([0-9a-zA-Z\.\-]+)', content)
        for match in matches:
            pkg, op, ver = match
            deps.append((pkg, ver))

    return deps


def dependency_check(workdir: str) -> list[dict]:
    findings = []
    deps = parse_dependencies(workdir)

    if not deps:
        print("[依赖检查] 未找到可解析的固定版本依赖 (==)，跳过 OSV 查询。")
        return findings

    print(f"[依赖检查] 准备检查 {len(deps)} 个依赖...")
    for pkg, ver in deps:
        vulns = query_osv(pkg, ver)
        for v in vulns:
            findings.append({
                "rule_id": v.get("id"),
                "type": "dependency_vuln",
                "package": pkg,
                "version": ver,
                "severity": extract_severity(v),
                "message": v.get("summary", "已知依赖漏洞"),
                "evidence_level": "已确认",
                "source": "osv"
            })

    print(f"[依赖检查] 扫描完成，发现 {len(findings)} 个依赖漏洞。")
    return findings