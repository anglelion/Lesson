"""Offline credential-pattern scanner that never returns secret values."""

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import settings


@dataclass(frozen=True, slots=True)
class SecretRule:
    rule_id: str
    title: str
    pattern: re.Pattern[str]
    severity: str = "HIGH"


_RULES = (
    SecretRule(
        "secret.private-key",
        "Private key material is committed to the repository",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "CRITICAL",
    ),
    SecretRule(
        "secret.aws-access-key",
        "AWS access key identifier is committed to the repository",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    SecretRule(
        "secret.github-token",
        "GitHub access token is committed to the repository",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ),
    SecretRule(
        "secret.slack-token",
        "Slack token is committed to the repository",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ),
    SecretRule(
        "secret.openai-key",
        "OpenAI-compatible API key is committed to the repository",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    SecretRule(
        "secret.generic-assignment",
        "Credential-like value is hardcoded",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)"
            r"\s*[:=]\s*['\"](?P<value>[^'\"\s]{16,})['\"]"
        ),
        "MEDIUM",
    ),
)

_SKIP_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "vendor",
}
_PLACEHOLDER_MARKERS = ("example", "sample", "dummy", "changeme", "replace", "your_", "xxxx")


def _is_placeholder(match: re.Match[str]) -> bool:
    value = match.groupdict().get("value") or match.group(0)
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def secret_check(workdir: str) -> list[dict]:
    root = Path(workdir).resolve()
    findings: list[dict] = []

    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRECTORIES for part in path.parts):
            continue
        try:
            if path.stat().st_size > settings.secret_scan_max_file_bytes:
                continue
            content = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in content[:4096]:
            continue
        text = content.decode("utf-8", errors="ignore")

        for rule in _RULES:
            for match in rule.pattern.finditer(text):
                if _is_placeholder(match):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "rule_id": rule.rule_id,
                        "type": "secret_exposure",
                        "title": rule.title,
                        "message": rule.title,
                        "severity": rule.severity,
                        "evidence_level": "likely",
                        "source": "secret_scan",
                        "file": path.relative_to(root).as_posix(),
                        "line": line,
                        "evidence": "Credential-like value matched; value redacted",
                        "remediation": (
                            "Revoke the credential, remove it from repository history, and load it "
                            "from an approved secret store or environment variable."
                        ),
                    }
                )

    return findings
