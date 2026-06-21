"""Load cloud project rules, files, and codebase search context for Omni."""

from __future__ import annotations

from pathlib import Path

from neuralrouter.index.codebase_index import CodebaseIndex
from saas.storage.projects import list_files, project_root_path, read_file


def load_project_rules(user_id: str, project_id: str) -> str:
    try:
        return read_file(user_id, project_id, ".akshrules").strip()
    except Exception:
        return "Be concise. Prefer working code. Use env vars for secrets.\n"


def build_codebase_context(user_id: str, project_id: str, query: str, *, limit: int = 8) -> str:
    root = project_root_path(user_id, project_id)
    if not root.exists():
        return ""
    index = CodebaseIndex()
    count = index.index_directory(root)
    if count == 0:
        return ""
    hits = index.search(query, limit=limit)
    if not hits:
        return ""
    lines = ["Relevant project files (codebase index):"]
    for h in hits:
        lines.append(
            f"- {h['path']} (lines {h['lines'][0]}-{h['lines'][1]}, score {h['score']}):\n"
            f"  {h['preview'][:300]}"
        )
    return "\n".join(lines)


def load_project_file_summary(user_id: str, project_id: str, *, max_files: int = 30) -> str:
    files = list_files(user_id, project_id)[:max_files]
    if not files:
        return ""
    return "Project files:\n" + "\n".join(f"- {f}" for f in files)


def enrich_message_with_project(
    message: str,
    user_id: str | None,
    project_id: str | None,
    *,
    rules: str | None = None,
    include_index: bool = True,
) -> tuple[str, str]:
    """Returns (enriched_message, effective_rules)."""
    if not user_id or not project_id:
        return message, rules or ""

    effective_rules = rules.strip() if rules else load_project_rules(user_id, project_id)
    parts: list[str] = []

    summary = load_project_file_summary(user_id, project_id)
    if summary:
        parts.append(summary)

    if include_index:
        ctx = build_codebase_context(user_id, project_id, message)
        if ctx:
            parts.append(ctx)

    if effective_rules:
        parts.append(f"Project rules (.akshrules):\n{effective_rules}")

    parts.append(f"User message:\n{message}")
    return "\n\n".join(parts), effective_rules


def resolve_agent_root(user_id: str | None, project_id: str | None) -> Path | None:
    if not user_id or not project_id:
        return None
    root = project_root_path(user_id, project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root
