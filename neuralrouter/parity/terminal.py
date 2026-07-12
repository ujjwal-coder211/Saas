"""Sandboxed terminal commands for Sarva Agent (project-scoped)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

MAX_OUTPUT = 20_000
TIMEOUT_S = 45

BLOCKED_PATTERNS = [
    r"rm\s+-rf",
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/",
    r"curl\s+.*\|\s*sh",
    r"wget\s+.*\|\s*sh",
    r"powershell\s+-",
    r";\s*rm\s+",
]

ALLOWED_FIRST = {
    "npm",
    "npx",
    "node",
    "python",
    "pip",
    "pip3",
    "pytest",
    "docker",
    "docker-compose",
    "git",
    "ls",
    "dir",
    "cat",
    "type",
    "echo",
    "mkdir",
    "cp",
    "copy",
    "mv",
    "move",
    "uvicorn",
    "flake8",
    "ruff",
    "black",
    "pnpm",
    "yarn",
    "cargo",
    "go",
    "make",
}


def run_terminal(project_root: Path | None, command: str) -> dict[str, Any]:
    if project_root is None:
        return {"ok": False, "error": "Select a cloud project for terminal commands"}
    cmd = command.strip()
    if not cmd:
        return {"ok": False, "error": "Empty command"}
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, cmd, re.I):
            return {"ok": False, "error": "Command blocked for safety"}

    first = cmd.split()[0].lower().replace("\\", "/").split("/")[-1]
    if first not in ALLOWED_FIRST:
        return {
            "ok": False,
            "error": f"Command '{first}' not allowed. Allowed: {', '.join(sorted(ALLOWED_FIRST))}",
        }

    if first == "git" and re.search(r"git\s+(push|remote|config\s+-global)", cmd, re.I):
        return {"ok": False, "error": "git push/remote/global config blocked in cloud sandbox"}

    root = project_root.resolve()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out after {TIMEOUT_S}s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    out = (proc.stdout or "") + (proc.stderr or "")
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + "\n...(truncated)"
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output": out or "(no output)",
        "command": cmd,
    }
