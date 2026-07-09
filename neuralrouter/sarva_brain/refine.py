"""Sarva refinement layer (paper v4 §3.4).

Ported from the saira_harvest Phase-1 `sarva/refine.py`. When Sarva delegates, it
treats the teacher's answer as a DRAFT — it verifies the output before returning
it, rather than forwarding blindly.

Honesty note (same as source): true refinement needs Sarva's own model judgment
(rewriting, style adaptation). This first version does deterministic CHECKS only
— it never silently rewrites content it can't verify. It flags issues so a human,
or a future model-based refiner, can act on them. An honest "unverified" flag is
better than a heuristic "fix" that is wrong.
"""

from __future__ import annotations

import ast
import re

PLACEHOLDER_MARKERS = ["TODO", "FIXME", "<insert", "[your code here]"]


def _extract_code_blocks(text: str) -> list[str]:
    """Return fenced code block bodies; if none, treat whole text as candidate."""
    blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", text, re.S)
    return blocks if blocks else []


def _looks_like_python(text: str) -> bool:
    return bool(re.search(r"\bdef \w+\(|\bimport \w+|\bclass \w+\s*[:(]", text))


def _verify_python_syntax(code: str) -> tuple[bool, str | None]:
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def refine(draft: str, task_type: str = "general", query: str = "") -> dict:
    """Verify a delegated draft. Returns {content, verified, issues}.

    ``verified`` is True only when every check that applied passed — it is a
    lower bound on quality, not a guarantee.
    """
    issues: list[str] = []
    content = (draft or "").strip()

    if not content:
        issues.append("empty_response")

    # Prefer fenced code blocks; fall back to scanning the whole answer.
    code_candidates = _extract_code_blocks(content)
    if not code_candidates and (task_type == "code" or _looks_like_python(content)):
        code_candidates = [content]

    for code in code_candidates:
        if _looks_like_python(code):
            ok, err = _verify_python_syntax(code)
            if not ok:
                issues.append(f"syntax_error: {err}")

    for marker in PLACEHOLDER_MARKERS:
        if marker in content:
            issues.append(f"placeholder_left: '{marker}'")

    if 0 < len(content) < 3:
        issues.append("suspiciously_short_response")

    return {"content": content, "verified": len(issues) == 0, "issues": issues}
