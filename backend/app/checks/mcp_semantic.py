"""Static MCP-specific checks for misleading tools and unsafe schemas."""

import ast
import json
from pathlib import Path
import re
from typing import Any

from ..config import settings


_SKIP_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "vendor", "dist", "build"}
_INJECTION_PATTERNS = (
    re.compile(r"ignore (?:all |any )?(?:previous|prior) instructions", re.IGNORECASE),
    re.compile(r"(?:reveal|print|return|expose).{0,30}(?:system prompt|secret|credential|token)", re.IGNORECASE),
    re.compile(r"do not (?:tell|inform|show).{0,20}(?:user|human)", re.IGNORECASE),
    re.compile(r"must (?:always )?(?:call|invoke|use) this tool", re.IGNORECASE),
)
_DESTRUCTIVE_WORDS = {"delete", "remove", "destroy", "overwrite", "write", "modify", "send"}
_NETWORK_WORDS = {"network", "http", "api", "request", "fetch", "download", "upload", "send"}
_FILE_WORDS = {"file", "directory", "folder", "path", "read", "write", "save"}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _tool_decorator(node: ast.AST) -> ast.AST | None:
    target = node.func if isinstance(node, ast.Call) else node
    final_name = _call_name(target).rsplit(".", 1)[-1]
    return node if final_name in {"tool", "register_tool"} else None


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _decorator_value(decorator: ast.AST | None, name: str) -> Any:
    if not isinstance(decorator, ast.Call):
        return None
    for keyword in decorator.keywords:
        if keyword.arg == name:
            return _literal(keyword.value)
    return None


class _BehaviorVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.destructive = False
        self.network = False
        self.file_access = False
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        self.calls.add(name)
        if name in {
            "os.remove",
            "os.unlink",
            "os.rmdir",
            "shutil.rmtree",
            "pathlib.Path.unlink",
            "pathlib.Path.rmdir",
        }:
            self.destructive = True
            self.file_access = True
        if name in {"os.system", "subprocess.run", "subprocess.call", "subprocess.Popen"}:
            self.destructive = True
        if name == "open":
            self.file_access = True
            mode = _literal(node.args[1]) if len(node.args) > 1 else None
            for keyword in node.keywords:
                if keyword.arg == "mode":
                    mode = _literal(keyword.value)
            if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+")):
                self.destructive = True
        if name.endswith((".write_text", ".write_bytes", ".unlink", ".rmdir", ".rename", ".replace")):
            self.file_access = True
            self.destructive = True
        if name.endswith((".read_text", ".read_bytes", ".open")):
            self.file_access = True
        if name.startswith(("requests.", "httpx.", "urllib.", "aiohttp.", "socket.")):
            self.network = True
        self.generic_visit(node)


def _annotation_map(decorator: ast.AST | None) -> dict[str, Any]:
    if not isinstance(decorator, ast.Call):
        return {}
    for keyword in decorator.keywords:
        if keyword.arg != "annotations":
            continue
        direct = _literal(keyword.value)
        if isinstance(direct, dict):
            return direct
        if isinstance(keyword.value, ast.Call):
            return {
                item.arg: _literal(item.value)
                for item in keyword.value.keywords
                if item.arg is not None
            }
    return {}


def _finding(
    *,
    rule_id: str,
    finding_type: str,
    message: str,
    severity: str,
    file: str,
    line: int,
    evidence: str,
    remediation: str,
    level: str = "likely",
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "type": finding_type,
        "title": message,
        "message": message,
        "severity": severity,
        "evidence_level": level,
        "source": "mcp_semantic",
        "file": file,
        "line": line,
        "evidence": evidence[:1000],
        "remediation": remediation,
    }


def _python_tools(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return []

    relative = path.relative_to(root).as_posix()
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorator = next(
            (matched for item in node.decorator_list if (matched := _tool_decorator(item))),
            None,
        )
        if decorator is None:
            continue

        tool_name = str(_decorator_value(decorator, "name") or node.name)
        description = str(_decorator_value(decorator, "description") or ast.get_docstring(node) or "")
        lowered_description = description.lower()
        annotations = _annotation_map(decorator)
        visitor = _BehaviorVisitor()
        visitor.visit(node)

        if not description.strip():
            findings.append(
                _finding(
                    rule_id="mcp.tool.missing-description",
                    finding_type="mcp_schema",
                    message=f"MCP tool '{tool_name}' has no user-visible description",
                    severity="MEDIUM",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Tool decorator on function {node.name}",
                    remediation="Describe the operation, side effects, data access, and confirmation needs.",
                )
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(description):
                findings.append(
                    _finding(
                        rule_id="mcp.tool.description-prompt-injection",
                        finding_type="tool_poisoning",
                        message=f"MCP tool '{tool_name}' description contains prompt-injection language",
                        severity="CRITICAL",
                        file=relative,
                        line=node.lineno,
                        evidence=description,
                        remediation="Remove instructions aimed at controlling the model or hiding behavior.",
                    )
                )
                break

        if visitor.destructive and annotations.get("readOnlyHint") is True:
            findings.append(
                _finding(
                    rule_id="mcp.tool.false-read-only-annotation",
                    finding_type="tool_poisoning",
                    message=f"MCP tool '{tool_name}' is marked read-only but performs side effects",
                    severity="CRITICAL",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Observed calls: {', '.join(sorted(visitor.calls))}",
                    remediation="Remove readOnlyHint or redesign the tool to avoid side effects.",
                )
            )
        if visitor.destructive and annotations.get("destructiveHint") is False:
            findings.append(
                _finding(
                    rule_id="mcp.tool.false-nondestructive-annotation",
                    finding_type="tool_poisoning",
                    message=f"MCP tool '{tool_name}' hides destructive behavior in its annotations",
                    severity="HIGH",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Observed calls: {', '.join(sorted(visitor.calls))}",
                    remediation="Set destructiveHint=true and clearly disclose the side effects.",
                )
            )

        if visitor.destructive and not (_DESTRUCTIVE_WORDS & set(lowered_description.split())):
            findings.append(
                _finding(
                    rule_id="mcp.tool.undisclosed-side-effect",
                    finding_type="description_mismatch",
                    message=f"MCP tool '{tool_name}' performs side effects not disclosed in its description",
                    severity="HIGH",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Observed calls: {', '.join(sorted(visitor.calls))}",
                    remediation="Explicitly describe writes, deletion, command execution, or external actions.",
                )
            )
        if visitor.network and not (_NETWORK_WORDS & set(lowered_description.split())):
            findings.append(
                _finding(
                    rule_id="mcp.tool.undisclosed-network-access",
                    finding_type="description_mismatch",
                    message=f"MCP tool '{tool_name}' performs network access not disclosed in its description",
                    severity="MEDIUM",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Observed calls: {', '.join(sorted(visitor.calls))}",
                    remediation="Disclose remote services, transmitted data, and authorization requirements.",
                )
            )
        if visitor.file_access and not (_FILE_WORDS & set(lowered_description.split())):
            findings.append(
                _finding(
                    rule_id="mcp.tool.undisclosed-file-access",
                    finding_type="description_mismatch",
                    message=f"MCP tool '{tool_name}' accesses files without disclosure",
                    severity="MEDIUM",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Observed calls: {', '.join(sorted(visitor.calls))}",
                    remediation="Describe the file scope and whether data is read, created, or modified.",
                )
            )

        unsafe_parameters = [
            argument.arg
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if argument.arg not in {"self", "cls", "ctx", "context"} and argument.annotation is None
        ]
        if unsafe_parameters or node.args.kwarg is not None:
            names = unsafe_parameters + ([f"**{node.args.kwarg.arg}"] if node.args.kwarg else [])
            findings.append(
                _finding(
                    rule_id="mcp.tool.unconstrained-input",
                    finding_type="mcp_schema",
                    message=f"MCP tool '{tool_name}' exposes unconstrained input parameters",
                    severity="MEDIUM",
                    file=relative,
                    line=node.lineno,
                    evidence=f"Unconstrained parameters: {', '.join(names)}",
                    remediation="Add precise types and bounded validation for every tool input.",
                )
            )
    return findings


def _manifest_tools(value: Any, file: str, findings: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if "name" in value and "inputSchema" in value:
            name = str(value.get("name"))
            description = str(value.get("description") or "")
            schema = value.get("inputSchema")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                findings.append(
                    _finding(
                        rule_id="mcp.tool.invalid-input-schema",
                        finding_type="mcp_schema",
                        message=f"MCP tool '{name}' does not use an object inputSchema",
                        severity="HIGH",
                        file=file,
                        line=1,
                        evidence="inputSchema must be a valid JSON Schema object",
                        remediation="Use an object JSON Schema and explicitly declare accepted properties.",
                        level="confirmed",
                    )
                )
            elif schema.get("additionalProperties") is not False:
                findings.append(
                    _finding(
                        rule_id="mcp.tool.open-input-schema",
                        finding_type="mcp_schema",
                        message=f"MCP tool '{name}' accepts undeclared input properties",
                        severity="MEDIUM",
                        file=file,
                        line=1,
                        evidence="inputSchema does not set additionalProperties=false",
                        remediation="Reject undeclared properties unless the open object is intentional.",
                    )
                )
            output_schema = value.get("outputSchema")
            if output_schema is not None and (
                not isinstance(output_schema, dict) or output_schema.get("type") != "object"
            ):
                findings.append(
                    _finding(
                        rule_id="mcp.tool.invalid-output-schema",
                        finding_type="mcp_schema",
                        message=f"MCP tool '{name}' does not use an object outputSchema",
                        severity="MEDIUM",
                        file=file,
                        line=1,
                        evidence="outputSchema must be a valid JSON Schema object when present",
                        remediation="Declare structured tool output with an object JSON Schema.",
                        level="confirmed",
                    )
                )
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(description):
                    findings.append(
                        _finding(
                            rule_id="mcp.tool.description-prompt-injection",
                            finding_type="tool_poisoning",
                            message=f"MCP tool '{name}' description contains prompt-injection language",
                            severity="CRITICAL",
                            file=file,
                            line=1,
                            evidence=description,
                            remediation="Remove instructions aimed at controlling the model or user.",
                        )
                    )
                    break
        for child in value.values():
            _manifest_tools(child, file, findings)
    elif isinstance(value, list):
        for child in value:
            _manifest_tools(child, file, findings)


def _json_tools(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    findings: list[dict[str, Any]] = []
    _manifest_tools(data, path.relative_to(root).as_posix(), findings)
    return findings


def _javascript_tools(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > settings.semgrep_max_target_bytes:
            return []
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    if not re.search(r"(?:registerTool|\.tool)\s*\(", source):
        return []

    findings: list[dict[str, Any]] = []
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(source)
        if match:
            findings.append(
                _finding(
                    rule_id="mcp.tool.description-prompt-injection",
                    finding_type="tool_poisoning",
                    message="MCP tool registration contains prompt-injection language",
                    severity="CRITICAL",
                    file=path.relative_to(root).as_posix(),
                    line=source.count("\n", 0, match.start()) + 1,
                    evidence=match.group(0),
                    remediation="Remove instructions aimed at controlling the model or hiding behavior.",
                )
            )
            break
    return findings


def mcp_semantic_check(workdir: str) -> list[dict]:
    root = Path(workdir).resolve()
    findings: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        try:
            if path.stat().st_size > settings.semgrep_max_target_bytes:
                continue
        except OSError:
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            findings.extend(_python_tools(path, root))
        elif suffix == ".json":
            findings.extend(_json_tools(path, root))
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            findings.extend(_javascript_tools(path, root))
    return findings
