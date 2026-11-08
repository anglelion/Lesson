# app/checks/static_audit.py
import subprocess
import json
import os

def static_audit(workdir: str) -> list[dict]:
    print(f"[静态审计] 使用 Docker 运行 Semgrep，目标目录: {workdir}")

    # 将 Windows 路径转换为 Docker 可识别的格式（如果路径含空格需加引号）
    # workdir 形如 C:\Users\...\Temp\mcp_xxx，Docker 挂载时直接使用 Windows 路径即可
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{workdir}:/src",
        "semgrep/semgrep",
        "semgrep", "scan",
        "--config=auto",
        "--json",
        "--quiet",
        "/src"
    ]

    print(f"[静态审计] 执行命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if not result.stdout.strip():
            print(f"[静态审计] 无标准输出，错误详情:\n{result.stderr[:500]}")
            return [{"type": "tool_error", "tool": "semgrep", "message": "Docker 运行无 JSON 输出"}]

        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return [{"type": "tool_error", "tool": "semgrep", "message": "扫描超时（300秒）"}]
    except json.JSONDecodeError as e:
        print(f"[静态审计] JSON 解析失败: {e}")
        print(f"原始输出前 300 字: {result.stdout[:300]}")
        return [{"type": "tool_error", "tool": "semgrep", "message": "输出不是合法 JSON"}]
    except Exception as e:
        return [{"type": "tool_error", "tool": "semgrep", "message": str(e)}]

    findings = []
    for r in data.get("results", []):
        # Docker 容器内路径以 /src 开头，需要替换掉以便和本地路径对应
        file_path = r.get("path", "").replace("/src/", "")
        findings.append({
            "rule_id": r.get("check_id"),
            "file": file_path,
            "line": r.get("start", {}).get("line"),
            "severity": r.get("extra", {}).get("severity", "INFO"),
            "message": r.get("extra", {}).get("message", "无描述"),
            "evidence": r.get("extra", {}).get("lines", "")[:200],
            "source": "semgrep",
            "type": "static_vuln"
        })

    print(f"[静态审计] Semgrep(Docker) 扫描完成，发现 {len(findings)} 个问题。")
    return findings