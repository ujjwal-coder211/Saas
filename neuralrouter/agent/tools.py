"""Sarva Agent — sandboxed file tools for autonomous coding tasks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neuralrouter.deploy.kit import generate_deploy_kit
from neuralrouter.parity.browser import (
    browser_click,
    browser_execute,
    browser_extract,
    browser_navigate,
    browser_open,
    browser_screenshot,
    browser_type,
    browser_wait,
)
from neuralrouter.parity.git import git_commit, git_diff, git_status
from neuralrouter.parity.system_tools import (
    manage_clipboard,
    notify,
    open_app,
    screenshot_region,
)
from neuralrouter.parity.terminal import run_terminal
from neuralrouter.security.scan import scan_project

# Harness write-class tools gated by work-mode read-only scope.
_WRITE_TOOLS = {
    "write_file",
    "generate_deploy_kit",
    "browser_click",
    "browser_type",
    "browser_execute",
    "open_app",
    "manage_clipboard",
    "notify",
}

ALLOWED_TOOLS = (
    "read_file",
    "write_file",
    "grep",
    "list_files",
    "generate_deploy_kit",
    "security_scan",
    "run_terminal",
    "git_status",
    "git_diff",
    "git_commit",
    # Browser tools (Harness §4.2.2 — CDP via Playwright)
    "browser_open",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_extract",
    "browser_screenshot",
    "browser_wait",
    "browser_execute",
    # System tools (Harness §4.2.3)
    "open_app",
    "manage_clipboard",
    "notify",
    "screenshot_region",
)


def _resolve_path(project_root: Path | None, rel_path: str) -> Path:
    if not rel_path or rel_path.startswith(".."):
        raise ValueError("Invalid path — must be relative and not escape project root")
    root = (project_root or Path.cwd()).resolve()
    target = (root / rel_path).resolve()
    if project_root is not None and not str(target).startswith(str(root)):
        raise ValueError("Path escapes project root")
    return target


def read_file(project_root: Path | None, path: str, *, max_bytes: int = 100_000) -> dict[str, Any]:
    target = _resolve_path(project_root, path)
    if not target.exists():
        return {"ok": False, "error": f"File not found: {path}"}
    if not target.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    data = target.read_bytes()[:max_bytes]
    return {"ok": True, "path": path, "content": data.decode("utf-8", errors="replace")}


def write_file(project_root: Path | None, path: str, content: str) -> dict[str, Any]:
    target = _resolve_path(project_root, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "bytes_written": len(content.encode("utf-8"))}


def list_files_tool(project_root: Path | None, path: str = ".") -> dict[str, Any]:
    root = _resolve_path(project_root, path)
    if not root.exists():
        return {"ok": False, "error": f"Path not found: {path}"}
    files: list[str] = []
    base = (project_root or Path.cwd()).resolve()
    if root.is_file():
        files.append(str(root.relative_to(base)))
    else:
        for fp in sorted(root.rglob("*")):
            if fp.is_file() and not any(p.startswith(".git") for p in fp.relative_to(base).parts):
                files.append(str(fp.relative_to(base)).replace("\\", "/"))
    return {"ok": True, "files": files[:200], "count": len(files)}


def grep(
    project_root: Path | None,
    pattern: str,
    *,
    path: str = ".",
    max_matches: int = 50,
) -> dict[str, Any]:
    root = _resolve_path(project_root, path)
    if not root.exists():
        return {"ok": False, "error": f"Path not found: {path}"}
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"ok": False, "error": f"Invalid regex: {exc}"}

    matches: list[dict[str, Any]] = []
    files = [root] if root.is_file() else list(root.rglob("*"))
    base = (project_root or Path.cwd()).resolve()

    for fp in files:
        if not fp.is_file():
            continue
        if fp.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".pyc"}:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fp.relative_to(base)).replace("\\", "/")
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"file": rel, "line": i, "text": line[:300]})
                if len(matches) >= max_matches:
                    return {"ok": True, "pattern": pattern, "matches": matches, "truncated": True}
    return {"ok": True, "pattern": pattern, "matches": matches, "truncated": False}


def generate_deploy_kit_tool(project_root: Path | None, project_name: str = "app") -> dict[str, Any]:
    if project_root is None:
        return {"ok": False, "error": "Select a cloud project for deploy kit generation"}
    return generate_deploy_kit(project_root, project_name=project_name)


def security_scan_tool(project_root: Path | None) -> dict[str, Any]:
    if project_root is None:
        return {"ok": False, "error": "Select a cloud project for security scan"}
    return scan_project(project_root)


def run_tool(
    name: str,
    args: dict[str, Any],
    *,
    project_root: Path | None = None,
    allow_write: bool = True,
) -> dict[str, Any]:
    if name not in ALLOWED_TOOLS:
        return {"ok": False, "error": f"Unknown tool: {name}"}

    if name in _WRITE_TOOLS and not allow_write:
        return {"ok": False, "error": f"Tool {name} blocked by work mode (read-only scope)"}

    if name == "read_file":
        return read_file(project_root, args.get("path", ""))
    if name == "write_file":
        return write_file(project_root, args.get("path", ""), args.get("content", ""))
    if name == "grep":
        return grep(project_root, args.get("pattern", ""), path=args.get("path", "."))
    if name == "list_files":
        return list_files_tool(project_root, args.get("path", "."))
    if name == "generate_deploy_kit":
        return generate_deploy_kit_tool(project_root, args.get("project_name", "app"))
    if name == "security_scan":
        return security_scan_tool(project_root)
    if name == "run_terminal":
        return run_terminal(project_root, args.get("command", ""))
    if name == "git_status":
        return git_status(project_root)
    if name == "git_diff":
        return git_diff(project_root, args.get("path", "."))
    if name == "git_commit":
        return git_commit(project_root, args.get("message", "Sarva agent commit"))

    # Browser tools (Harness §4.2.2)
    if name == "browser_open":
        return browser_open(args.get("url", ""))
    if name == "browser_navigate":
        return browser_navigate(args.get("url", ""))
    if name == "browser_click":
        return browser_click(args.get("selector", ""))
    if name == "browser_type":
        return browser_type(args.get("selector", ""), args.get("text", ""))
    if name == "browser_extract":
        return browser_extract(args.get("selector", ""))
    if name == "browser_screenshot":
        return browser_screenshot(bool(args.get("full_page", True)))
    if name == "browser_wait":
        return browser_wait(args.get("condition", "networkidle"))
    if name == "browser_execute":
        return browser_execute(args.get("js", ""))

    # System tools (Harness §4.2.3)
    if name == "open_app":
        return open_app(args.get("name", ""))
    if name == "manage_clipboard":
        return manage_clipboard(args.get("action", ""), args.get("content", ""))
    if name == "notify":
        return notify(args.get("title", "Saira"), args.get("message", ""))
    if name == "screenshot_region":
        return screenshot_region(
            int(args.get("x", 0)),
            int(args.get("y", 0)),
            int(args.get("w", 0)),
            int(args.get("h", 0)),
        )
    return {"ok": False, "error": "Unhandled tool"}
