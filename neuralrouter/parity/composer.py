"""Composer — multi-file coordinated edits (Cursor Composer style)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuralrouter.model_clients import call_model, provider_configured
from saas.storage.projects import list_files, read_file, write_file

_FILE_BLOCK = re.compile(
    r"```file:([^\n]+)\n(.*?)```",
    re.DOTALL,
)


@dataclass
class ComposerResult:
    answer: str
    files_changed: list[str] = field(default_factory=list)
    plan: str = ""


async def run_composer(
    task: str,
    user_id: str,
    project_id: str,
    *,
    rules: str = "",
    max_files: int = 12,
) -> ComposerResult:
    if not provider_configured():
        raise ValueError("OPENROUTER_API_KEY required for Composer")

    paths = list_files(user_id, project_id)[:max_files]
    file_summaries: list[str] = []
    for p in paths[:8]:
        try:
            text = read_file(user_id, project_id, p)
            file_summaries.append(f"### {p}\n{text[:1500]}")
        except Exception:
            continue

    plan_prompt = (
        "You are Sarva Composer for Aksh. Plan a multi-file change.\n"
        f"Task: {task}\n"
        f"Rules: {rules or '(none)'}\n"
        f"Project files: {', '.join(paths) or '(empty)'}\n\n"
        "Then output each file change as:\n"
        "```file:path/to/file.py\n(full new file content)\n```\n"
        "Only include files you change. Be complete and working."
    )
    if file_summaries:
        plan_prompt += "\n\nExisting code:\n" + "\n\n".join(file_summaries)

    raw = await call_model(plan_prompt, "qwen", system_prompt="You are Aksh Composer powered by Sarva.")
    content = raw.get("content") or ""
    changed: list[str] = []

    for m in _FILE_BLOCK.finditer(content):
        rel = m.group(1).strip().lstrip("/")
        body = m.group(2)
        if not rel or ".." in rel:
            continue
        write_file(user_id, project_id, rel, body)
        changed.append(rel)

    summary = content if not changed else f"Updated {len(changed)} file(s): " + ", ".join(changed)
    return ComposerResult(answer=summary, files_changed=changed, plan=content[:3000])
