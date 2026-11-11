"""Acquire an exact, temporary Git repository snapshot."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urlparse

from ..config import settings


class RepositoryError(RuntimeError):
    """Raised when a requested repository snapshot cannot be acquired."""


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    path: Path
    commit_sha: str


def _validate_git_argument(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or normalized.startswith("-"):
        raise RepositoryError(f"Invalid {label}")
    if any(character in normalized for character in ("\x00", "\r", "\n")):
        raise RepositoryError(f"Invalid {label}")
    return normalized


def _validate_repository_url(value: str) -> str:
    normalized = _validate_git_argument(value, "repository URL")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RepositoryError("Only HTTPS repository URLs are allowed")
    if parsed.username or parsed.password:
        raise RepositoryError("Credentials must not be embedded in repository URLs")
    if parsed.port not in (None, 443):
        raise RepositoryError("Repository URL must use the standard HTTPS port")

    hostname = parsed.hostname.lower().rstrip(".")
    allowed_hosts = {host.lower().rstrip(".") for host in settings.allowed_repo_hosts}
    if hostname not in allowed_hosts:
        raise RepositoryError(f"Repository host '{hostname}' is not allowed")

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise RepositoryError("Repository hostname could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise RepositoryError("Repository hostname resolves to a non-public address")
    return normalized


def _validate_snapshot(workdir: Path) -> None:
    total_bytes = 0
    total_files = 0
    for path in workdir.rglob("*"):
        if path.is_symlink():
            raise RepositoryError("Repository contains symbolic links")
        if not path.is_file():
            continue
        total_files += 1
        try:
            total_bytes += path.stat().st_size
        except OSError as exc:
            raise RepositoryError("Repository file metadata could not be read") from exc
        if total_files > settings.repository_max_files:
            raise RepositoryError("Repository exceeds the file-count limit")
        if total_bytes > settings.repository_max_bytes:
            raise RepositoryError("Repository exceeds the unpacked-size limit")


def _run_git(args: list[str], cwd: Path, timeout_seconds: int) -> str:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_LFS_SKIP_SMUDGE": "1",
        }
    )

    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=never",
                "-c",
                "protocol.ext.allow=never",
                *args,
            ],
            cwd=cwd,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RepositoryError("Git operation timed out") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Git operation failed").strip()
        raise RepositoryError(message[:1000]) from exc

    return result.stdout.strip()


@contextmanager
def acquire_snapshot(
    repo_url: str,
    requested_ref: str,
    timeout_seconds: int,
) -> Iterator[RepositorySnapshot]:
    """Fetch only the requested ref and expose its detached commit checkout."""

    safe_url = _validate_repository_url(repo_url)
    safe_ref = _validate_git_argument(requested_ref, "Git ref")
    workdir = Path(tempfile.mkdtemp(prefix="mcp_audit_"))

    try:
        _run_git(["init", "--quiet"], workdir, timeout_seconds)
        _run_git(["remote", "add", "origin", safe_url], workdir, timeout_seconds)
        _run_git(
            ["fetch", "--quiet", "--depth", "1", "--no-tags", "origin", safe_ref],
            workdir,
            timeout_seconds,
        )
        commit_sha = _run_git(
            ["rev-parse", "--verify", "FETCH_HEAD^{commit}"],
            workdir,
            timeout_seconds,
        )
        _run_git(
            ["-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", commit_sha],
            workdir,
            timeout_seconds,
        )
        shutil.rmtree(workdir / ".git", ignore_errors=True)
        _validate_snapshot(workdir)
        yield RepositorySnapshot(path=workdir, commit_sha=commit_sha)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
