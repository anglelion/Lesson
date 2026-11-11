"""Static checks for MCP HTTP and stdio transport exposure."""

from pathlib import Path
import re
from typing import Any

from ..config import settings


_TEXT_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".env"}
_SKIP_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "vendor", "dist", "build"}
_PUBLIC_BIND = re.compile(r"(?:host\s*[=:]\s*['\"]0\.0\.0\.0['\"]|--host\s+0\.0\.0\.0)", re.IGNORECASE)
_CORS_WILDCARD = re.compile(r"(?:allow_origins|origin)\s*[=:]\s*\[?\s*['\"]\*['\"]", re.IGNORECASE)
_CLEARTEXT_REMOTE = re.compile(r"http://(?!localhost\b|127\.0\.0\.1\b|\[::1\])[^\s'\"/]+", re.IGNORECASE)
_NETWORK_SERVER = re.compile(r"(?:uvicorn\.run|app\.listen|server\.listen|createServer\s*\(|transport\s*=\s*['\"](?:sse|http|streamable_http))", re.IGNORECASE)
_AUTH_SIGNAL = re.compile(r"(?:authorization|bearer|oauth|api[_-]?key|jwt|authmiddleware)", re.IGNORECASE)
_TRUSTED_HOST = re.compile(r"(?:TrustedHostMiddleware|allowedHosts|allowed_hosts|validateHost)")


def _finding(rule_id: str, message: str, severity: str, file: str, line: int, evidence: str, remediation: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "type": "transport_security",
        "title": message,
        "message": message,
        "severity": severity,
        "evidence_level": "likely",
        "source": "transport",
        "file": file,
        "line": line,
        "evidence": evidence[:500],
        "remediation": remediation,
    }


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def transport_check(workdir: str, deploy_type: str) -> list[dict]:
    root = Path(workdir).resolve()
    files: list[tuple[Path, str]] = []
    corpus_parts: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or path.suffix.lower() not in _TEXT_SUFFIXES
            or any(part in _SKIP_DIRECTORIES for part in relative.parts)
        ):
            continue
        try:
            if path.stat().st_size > settings.semgrep_max_target_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files.append((path, text))
        corpus_parts.append(text)

    corpus = "\n".join(corpus_parts)
    has_auth = bool(_AUTH_SIGNAL.search(corpus))
    has_trusted_host = bool(_TRUSTED_HOST.search(corpus))
    findings: list[dict[str, Any]] = []

    for path, text in files:
        relative = path.relative_to(root).as_posix()
        for match in _CLEARTEXT_REMOTE.finditer(text):
            findings.append(
                _finding(
                    "transport.cleartext-http",
                    "Remote service communication uses cleartext HTTP",
                    "HIGH",
                    relative,
                    _line(text, match.start()),
                    match.group(0),
                    "Use HTTPS with certificate verification for remote MCP and API traffic.",
                )
            )
        for match in _CORS_WILDCARD.finditer(text):
            findings.append(
                _finding(
                    "transport.wildcard-cors",
                    "HTTP transport allows requests from every web origin",
                    "HIGH",
                    relative,
                    _line(text, match.start()),
                    match.group(0),
                    "Allow only explicit trusted origins and avoid credentialed wildcard CORS.",
                )
            )

        public_match = _PUBLIC_BIND.search(text)
        if public_match and deploy_type == "http":
            if not has_auth:
                findings.append(
                    _finding(
                        "transport.public-without-auth",
                        "HTTP MCP server binds publicly without visible authentication",
                        "HIGH",
                        relative,
                        _line(text, public_match.start()),
                        public_match.group(0),
                        "Require authenticated requests before exposing the MCP endpoint.",
                    )
                )
            if not has_trusted_host:
                findings.append(
                    _finding(
                        "transport.missing-host-validation",
                        "Public HTTP MCP server has no visible Host validation",
                        "MEDIUM",
                        relative,
                        _line(text, public_match.start()),
                        public_match.group(0),
                        "Validate Host headers against an explicit allowlist to reduce DNS rebinding risk.",
                    )
                )

        server_match = _NETWORK_SERVER.search(text)
        if server_match and deploy_type == "stdio":
            findings.append(
                _finding(
                    "transport.stdio-network-mismatch",
                    "Repository declared as stdio also starts a network server",
                    "MEDIUM",
                    relative,
                    _line(text, server_match.start()),
                    server_match.group(0),
                    "Remove the listener or submit the repository as an HTTP deployment for full review.",
                )
            )

    return findings
