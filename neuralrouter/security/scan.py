"""Basic security scan for Aksh cloud projects — secrets, risky patterns, env leaks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----")),
    ("jwt_like", re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+\.")),
    ("generic_api_key", re.compile(r"(?i)(api[_-]?key|secret|password)\s*=\s*['\"][^'\"]{8,}['\"]")),
    ("openrouter", re.compile(r"sk-or-v1-[a-zA-Z0-9]{20,}")),
]

SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".pyc", ".woff", ".ico"}


def scan_project(root: Path, *, max_files: int = 200) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists():
        return {"ok": False, "error": "Project root not found"}

    findings: list[dict[str, Any]] = []
    scanned = 0

    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() in SKIP_SUFFIX:
            continue
        if any(p.startswith(".git") for p in fp.relative_to(root).parts):
            continue
        scanned += 1
        if scanned > max_files:
            findings.append(
                {
                    "severity": "info",
                    "file": ".",
                    "message": f"Scan truncated after {max_files} files",
                }
            )
            break
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = fp.relative_to(root).as_posix()

        if rel == ".env":
            findings.append(
                {
                    "severity": "high",
                    "file": rel,
                    "message": ".env file in project — use .env.example only; real secrets belong on server",
                }
            )

        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    {
                        "severity": "critical",
                        "file": rel,
                        "message": f"Possible secret ({name}) — move to environment variables",
                    }
                )

        if "eval(" in text and fp.suffix == ".py":
            findings.append(
                {
                    "severity": "medium",
                    "file": rel,
                    "message": "Use of eval() — security risk",
                }
            )

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "info": 3, "low": 4}
    findings.sort(key=lambda f: severity_rank.get(f["severity"], 9))

    return {
        "ok": True,
        "files_scanned": min(scanned, max_files),
        "findings": findings,
        "summary": _summary(findings),
    }


def _summary(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No issues found in basic scan."
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
    return "Findings — " + ", ".join(parts)
