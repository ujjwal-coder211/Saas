"""Git helpers for cloud / enterprise project directories."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run_git(root: Path, *args: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "git not installed on server"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git command timed out"}
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"ok": proc.returncode == 0, "output": out.strip(), "exit_code": proc.returncode}


def ensure_git_repo(root: Path) -> None:
    if not (root / ".git").exists():
        _run_git(root, "init")
        _run_git(root, "config", "user.email", "aksh@aitotech.in")
        _run_git(root, "config", "user.name", "Aksh Studio")


def git_status(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"ok": False, "error": "No project root"}
    ensure_git_repo(root)
    return _run_git(root, "status", "--short", "--branch")


def git_diff(root: Path | None, path: str = ".") -> dict[str, Any]:
    if root is None:
        return {"ok": False, "error": "No project root"}
    ensure_git_repo(root)
    return _run_git(root, "diff", "--", path)


def git_commit(root: Path | None, message: str) -> dict[str, Any]:
    if root is None:
        return {"ok": False, "error": "No project root"}
    ensure_git_repo(root)
    _run_git(root, "add", "-A")
    return _run_git(root, "commit", "-m", message[:500])
