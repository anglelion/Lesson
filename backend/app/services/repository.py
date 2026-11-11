"""Acquire an exact, temporary Git repository snapshot."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


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
            ["git", *args],
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

    safe_url = _validate_git_argument(repo_url, "repository URL")
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
        yield RepositorySnapshot(path=workdir, commit_sha=commit_sha)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
