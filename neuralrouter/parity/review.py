"""Bugbot-style code review — security scan + Sarva review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neuralrouter.model_clients import call_model, provider_configured
from neuralrouter.security.scan import scan_project
from saas.storage.projects import list_files, read_file


async def review_project(
    user_id: str,
    project_id: str,
    root: Path,
    *,
    focus: str = "bugs and security",
) -> dict[str, Any]:
    scan = scan_project(root)
    snippets: list[str] = []
    for path in list_files(user_id, project_id)[:15]:
        if path.endswith((".png", ".jpg", ".zip")):
            continue
        try:
            text = read_file(user_id, project_id, path)
            snippets.append(f"### {path}\n{text[:2000]}")
        except Exception:
            continue

    review_text = ""
    if provider_configured() and snippets:
        prompt = (
            f"You are Aksh Bugbot (Sarva). Review this project for: {focus}.\n"
            "Format: numbered findings with severity (critical/high/medium/low), file, issue, fix.\n\n"
            + "\n\n".join(snippets[:10])
        )
        result = await call_model(prompt, "qwen", system_prompt="You are a professional code reviewer.")
        review_text = result.get("content") or ""

    return {
        "ok": True,
        "security_scan": scan,
        "ai_review": review_text,
        "summary": scan.get("summary", "") + (" · AI review included" if review_text else ""),
    }
