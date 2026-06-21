"""Inline edit (Cursor Cmd+K style) and tab completion via Omni."""

from __future__ import annotations

from neuralrouter.model_clients import call_model, provider_configured


async def inline_edit(
    *,
    file_path: str,
    full_content: str,
    selection: str,
    instruction: str,
    language: str = "plaintext",
) -> dict:
    if not provider_configured():
        raise ValueError("OPENROUTER_API_KEY required for inline edit")
    prompt = (
        f"File: {file_path} ({language})\n"
        f"User selected this code:\n```\n{selection}\n```\n"
        f"Instruction: {instruction}\n\n"
        "Return ONLY the replacement text for the selection — no markdown fences, no explanation."
    )
    system = (
        "You are Omni inline edit. Output only the new code that replaces the selection. "
        "Keep indentation consistent."
    )
    result = await call_model(prompt, "qwen", system_prompt=system)
    replacement = (result.get("content") or "").strip()
    if replacement.startswith("```"):
        lines = replacement.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        replacement = "\n".join(lines)
    return {
        "replacement": replacement,
        "model": "omni",
    }


async def tab_complete(
    *,
    file_path: str,
    content: str,
    prefix: str,
    line: int,
    column: int,
) -> dict:
    if not provider_configured():
        return {"completion": "", "reason": "no_api_key"}
    if len(prefix) > 200:
        return {"completion": "", "reason": "prefix_too_long"}
    lines = content.splitlines()
    context_start = max(0, line - 15)
    context = "\n".join(lines[context_start : line + 1])
    prompt = (
        f"File: {file_path}\n"
        f"Cursor at line {line}, column {column}.\n"
        f"Text before cursor on current line: ...{prefix[-80:]}\n\n"
        f"Context:\n```\n{context}\n```\n\n"
        "Suggest the next characters to insert at the cursor (Aksh Tab). "
        "Return ONLY the completion suffix (what comes after the prefix), max 120 chars. "
        "If nothing useful, return empty string."
    )
    result = await call_model(prompt, "qwen", system_prompt="You are Omni Tab completion.")
    completion = (result.get("content") or "").strip().replace("\n", " ")[:120]
    return {"completion": completion, "model": "omni"}
