"""Parse locked Python and Node.js dependencies and query OSV in batches."""

import json
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from packaging.requirements import InvalidRequirement, Requirement

from ..config import settings

OSV_BATCH_API = "https://api.osv.dev/v1/querybatch"
OSV_VULN_API = "https://api.osv.dev/v1/vulns"
_SKIP_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "vendor", "dist", "build"}


class DependencyCheckError(RuntimeError):
    """Raised when dependency coverage or the OSV query is incomplete."""


@dataclass(frozen=True, slots=True)
class Dependency:
    name: str
    version: str
    ecosystem: str
    source_file: str


def _exact_version(requirement: Requirement) -> str | None:
    for specifier in requirement.specifier:
        if specifier.operator in {"==", "==="} and "*" not in specifier.version:
            return specifier.version
    return None


def _parse_requirement_strings(
    values: Iterable[str],
    source_file: str,
) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for value in values:
        candidate = value.strip()
        if not candidate or candidate.startswith(("#", "-", "git+", "http://", "https://")):
            continue
        try:
            requirement = Requirement(candidate)
        except InvalidRequirement:
            continue
        version = _exact_version(requirement)
        if version:
            dependencies.append(Dependency(requirement.name, version, "PyPI", source_file))
    return dependencies


def _parse_requirements_file(path: Path, root: Path) -> list[Dependency]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    cleaned = [line.split(" #", 1)[0].strip() for line in lines]
    return _parse_requirement_strings(cleaned, path.relative_to(root).as_posix())


def _parse_pyproject(path: Path, root: Path) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return []

    project = data.get("project") or {}
    values = list(project.get("dependencies") or [])
    for optional_values in (project.get("optional-dependencies") or {}).values():
        values.extend(optional_values or [])
    return _parse_requirement_strings(values, path.relative_to(root).as_posix())


def _parse_python_lock(path: Path, root: Path) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return []

    dependencies: list[Dependency] = []
    for package in data.get("package") or []:
        name = package.get("name")
        version = package.get("version")
        if name and version:
            dependencies.append(
                Dependency(str(name), str(version), "PyPI", path.relative_to(root).as_posix())
            )
    return dependencies


def _parse_pipfile_lock(path: Path, root: Path) -> list[Dependency]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []

    dependencies: list[Dependency] = []
    for section in ("default", "develop"):
        for name, metadata in (data.get(section) or {}).items():
            version = str((metadata or {}).get("version") or "")
            if version.startswith("==") and "*" not in version:
                dependencies.append(
                    Dependency(name, version[2:], "PyPI", path.relative_to(root).as_posix())
                )
    return dependencies


def _walk_npm_v1(
    packages: dict[str, Any],
    source_file: str,
) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for name, metadata in packages.items():
        version = (metadata or {}).get("version")
        if version:
            dependencies.append(Dependency(name, str(version), "npm", source_file))
        dependencies.extend(_walk_npm_v1((metadata or {}).get("dependencies") or {}, source_file))
    return dependencies


def _parse_package_lock(path: Path, root: Path) -> list[Dependency]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []

    source_file = path.relative_to(root).as_posix()
    packages = data.get("packages")
    if isinstance(packages, dict):
        dependencies: list[Dependency] = []
        for package_path, metadata in packages.items():
            if not package_path:
                continue
            name = (metadata or {}).get("name")
            if not name and "node_modules/" in package_path:
                name = package_path.rsplit("node_modules/", 1)[-1]
            version = (metadata or {}).get("version")
            if name and version:
                dependencies.append(Dependency(str(name), str(version), "npm", source_file))
        return dependencies
    return _walk_npm_v1(data.get("dependencies") or {}, source_file)


def _candidate_paths(root: Path, pattern: str) -> Iterable[Path]:
    return (
        path
        for path in root.rglob(pattern)
        if not any(part in _SKIP_DIRECTORIES for part in path.relative_to(root).parts)
    )


def parse_dependencies(workdir: str) -> list[Dependency]:
    root = Path(workdir).resolve()
    dependencies: list[Dependency] = []

    for path in _candidate_paths(root, "requirements*.txt"):
        dependencies.extend(_parse_requirements_file(path, root))
    for path in _candidate_paths(root, "requirements*.in"):
        dependencies.extend(_parse_requirements_file(path, root))
    for path in _candidate_paths(root, "pyproject.toml"):
        dependencies.extend(_parse_pyproject(path, root))
    for filename in ("poetry.lock", "uv.lock"):
        for path in _candidate_paths(root, filename):
            dependencies.extend(_parse_python_lock(path, root))
    for path in _candidate_paths(root, "Pipfile.lock"):
        dependencies.extend(_parse_pipfile_lock(path, root))
    for filename in ("package-lock.json", "npm-shrinkwrap.json"):
        for path in _candidate_paths(root, filename):
            dependencies.extend(_parse_package_lock(path, root))

    unique = {
        (dependency.ecosystem, dependency.name.lower(), dependency.version): dependency
        for dependency in dependencies
    }
    result = sorted(
        unique.values(), key=lambda item: (item.ecosystem, item.name.lower(), item.version)
    )
    if len(result) > settings.dependency_limit:
        raise DependencyCheckError(
            f"Dependency count {len(result)} exceeds limit {settings.dependency_limit}"
        )
    return result


def _severity(vulnerability: dict[str, Any]) -> str:
    candidates = [
        (vulnerability.get("database_specific") or {}).get("severity"),
        (vulnerability.get("ecosystem_specific") or {}).get("severity"),
    ]
    for candidate in candidates:
        normalized = str(candidate or "").upper()
        if normalized in {"LOW", "MEDIUM", "MODERATE", "HIGH", "CRITICAL"}:
            return "MEDIUM" if normalized == "MODERATE" else normalized

    for affected in vulnerability.get("affected") or []:
        normalized = str(
            ((affected or {}).get("ecosystem_specific") or {}).get("severity") or ""
        ).upper()
        if normalized in {"LOW", "MEDIUM", "MODERATE", "HIGH", "CRITICAL"}:
            return "MEDIUM" if normalized == "MODERATE" else normalized

    for item in vulnerability.get("severity") or []:
        score = str((item or {}).get("score") or "")
        try:
            numeric = float(score)
        except ValueError:
            continue
        if numeric >= 9:
            return "CRITICAL"
        if numeric >= 7:
            return "HIGH"
        if numeric >= 4:
            return "MEDIUM"
        if numeric > 0:
            return "LOW"
    return "UNKNOWN"


def _fixed_versions(vulnerability: dict[str, Any]) -> list[str]:
    fixed: set[str] = set()
    for affected in vulnerability.get("affected") or []:
        for value_range in (affected or {}).get("ranges") or []:
            for event in (value_range or {}).get("events") or []:
                if (event or {}).get("fixed"):
                    fixed.add(str(event["fixed"]))
    return sorted(fixed)


def _finding(dependency: Dependency, vulnerability: dict[str, Any]) -> dict[str, Any]:
    vulnerability_id = str(vulnerability.get("id") or "OSV-UNKNOWN")
    fixed_versions = _fixed_versions(vulnerability)
    summary = str(vulnerability.get("summary") or vulnerability.get("details") or vulnerability_id)
    remediation = "Upgrade to a non-affected release."
    if fixed_versions:
        remediation = f"Upgrade to one of the fixed versions: {', '.join(fixed_versions)}."
    return {
        "rule_id": vulnerability_id,
        "type": "dependency_vulnerability",
        "title": f"{vulnerability_id} affects {dependency.name} {dependency.version}",
        "message": summary[:2000],
        "severity": _severity(vulnerability),
        "evidence_level": "confirmed",
        "source": "osv",
        "file": dependency.source_file,
        "package": dependency.name,
        "version": dependency.version,
        "evidence": f"OSV reports {dependency.name} {dependency.version} as affected",
        "remediation": remediation,
        "ecosystem": dependency.ecosystem,
        "aliases": vulnerability.get("aliases") or [],
        "fixed_versions": fixed_versions,
        "modified": vulnerability.get("modified"),
    }


def dependency_check(workdir: str) -> list[dict]:
    dependencies = parse_dependencies(workdir)
    if not dependencies:
        return []

    queries = [
        {
            "package": {"name": dependency.name, "ecosystem": dependency.ecosystem},
            "version": dependency.version,
        }
        for dependency in dependencies
    ]
    findings: list[dict] = []
    details_cache: dict[str, dict[str, Any]] = {}

    try:
        with httpx.Client(timeout=settings.osv_timeout_seconds) as client:
            for offset in range(0, len(queries), 1000):
                chunk = queries[offset : offset + 1000]
                response = client.post(OSV_BATCH_API, json={"queries": chunk})
                response.raise_for_status()
                results = response.json().get("results") or []
                if len(results) != len(chunk):
                    raise DependencyCheckError("OSV returned an incomplete batch response")

                for index, result in enumerate(results):
                    dependency = dependencies[offset + index]
                    for reference in (result or {}).get("vulns") or []:
                        vulnerability_id = str((reference or {}).get("id") or "")
                        if not vulnerability_id:
                            continue
                        if vulnerability_id not in details_cache:
                            detail_response = client.get(f"{OSV_VULN_API}/{vulnerability_id}")
                            detail_response.raise_for_status()
                            details_cache[vulnerability_id] = detail_response.json()
                        findings.append(_finding(dependency, details_cache[vulnerability_id]))
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise DependencyCheckError(f"OSV query failed: {exc}") from exc

    return findings
