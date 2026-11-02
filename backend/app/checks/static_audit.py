# app/checks/static_audit.py
import os
import re


def static_audit(workdir: str) -> list[dict]:
    """
    纯 Python 实现的轻量级静态代码审计器。
    替代损坏的 Semgrep，确保系统流程能跑通并产出真实数据。
    """
    print(f"[静态审计] 开始使用内置引擎扫描目录: {workdir}")

    findings = []

    # 定义我们要扫描的危险模式（正则表达式）
    rules = [
        {
            "rule_id": "SEC-001",
            "severity": "HIGH",
            "message": "发现潜在的危险函数调用 (eval/exec)",
            "pattern": re.compile(r'\b(eval|exec)\s*\('),
        },
        {
            "rule_id": "SEC-002",
            "severity": "MEDIUM",
            "message": "发现系统命令执行调用 (os.system/subprocess)",
            "pattern": re.compile(r'\b(os\.system|subprocess\.Popen|subprocess\.run)\s*\('),
        },
        {
            "rule_id": "SEC-003",
            "severity": "HIGH",
            "message": "发现硬编码的密码或密钥 (password/secret)",
            "pattern": re.compile(r'(password|secret|api_key|token)\s*=\s*[\'"][a-zA-Z0-9_\-]{8,}[\'"]', re.IGNORECASE),
        }
    ]

    # 遍历目录下的所有文件
    for root, dirs, files in os.walk(workdir):
        # 跳过 .git 等隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            if not file.endswith(('.py', '.js', '.ts', '.sh')):
                continue

            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, workdir)

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                for line_num, line in enumerate(lines, 1):
                    # 忽略注释行（简单处理）
                    if line.strip().startswith(('#', '//')):
                        continue

                    for rule in rules:
                        if rule["pattern"].search(line):
                            findings.append({
                                "rule_id": rule["rule_id"],
                                "file": rel_path,
                                "line": line_num,
                                "severity": rule["severity"],
                                "message": rule["message"],
                                "evidence": line.strip()[:100],
                                "source": "builtin_audit",
                                "type": "static_vuln"
                            })
            except Exception as e:
                print(f"[静态审计] 读取文件失败 {rel_path}: {e}")

    print(f"[静态审计] 扫描完成，发现 {len(findings)} 个代码问题。")
    return findings