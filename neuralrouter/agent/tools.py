"""Aksh Agent — sandboxed file tools for autonomous coding tasks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ALLOWED_TOOLS = ("read_file", "write_file", "grep")


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

    for fp in files:
        if not fp.is_file():
            continue
        if fp.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".pyc"}:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fp.relative_to((project_root or Path.cwd()).resolve()))
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"file": rel, "line": i, "text": line[:300]})
                if len(matches) >= max_matches:
                    return {"ok": True, "pattern": pattern, "matches": matches, "truncated": True}
    return {"ok": True, "pattern": pattern, "matches": matches, "truncated": False}


def run_tool(
    name: str,
    args: dict[str, Any],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    if name not in ALLOWED_TOOLS:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    if name == "read_file":
        return read_file(project_root, args.get("path", ""))
    if name == "write_file":
        return write_file(project_root, args.get("path", ""), args.get("content", ""))
    if name == "grep":
        return grep(project_root, args.get("pattern", ""), path=args.get("path", "."))
    return {"ok": False, "error": "Unhandled tool"}
