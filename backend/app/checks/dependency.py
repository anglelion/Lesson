# app/checks/dependency.py
import urllib.request, json

OSV_API = "https://api.osv.dev/v1/query"

def query_osv(package: str, version: str, ecosystem: str = "PyPI") -> list:
    payload = {"package": {"name": package, "ecosystem": ecosystem},
               "version": version}
    req = urllib.request.Request(
        OSV_API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("vulns", [])
    except Exception:
        return []  # 调用失败时上层标记为“未知”

def dependency_check(workdir: str) -> list[dict]:
    findings = []
    # 解析 requirements.txt 或 package-lock.json（此处省略解析代码）
    for pkg, ver in parse_dependencies(workdir):
        vulns = query_osv(pkg, ver)
        for v in vulns:
            findings.append({
                "type": "dependency_vuln",
                "package": pkg,
                "version": ver,
                "vuln_id": v.get("id"),
                "aliases": v.get("aliases", []),
                "severity": extract_severity(v),
                "source": "osv"
            })
    return findings