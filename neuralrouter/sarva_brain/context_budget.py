"""Context window budgeting (paper §11).

Context is budgeted, not merely limited. Default allocation over a ~200K window:
  - Hermes skills:     ~10K tokens
  - Codebase context:  ~60K tokens
  - Recent turns:      ~30K tokens
  - Active workspace / remainder: rest

When a bucket crosses its soft cap, older / lower-score content is compacted
or dropped so the model does not silently fill and degrade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Rough chars→tokens heuristic (English/Hinglish mix).
CHARS_PER_TOKEN = 4


@dataclass
class ContextBudgets:
    skills_tokens: int = 10_000
    codebase_tokens: int = 60_000
    history_tokens: int = 30_000
    workspace_tokens: int = 40_000
    total_soft_cap: int = 140_000  # leave headroom under 200K


@dataclass
class BudgetedContext:
    skills: str = ""
    codebase: str = ""
    history: str = ""
    workspace: str = ""
    user_message: str = ""
    truncated: list[str] = field(default_factory=list)
    token_estimate: dict[str, int] = field(default_factory=dict)

    def as_prompt_block(self) -> str:
        parts: list[str] = []
        if self.skills:
            parts.append(f"[Hermes skills — budgeted]\n{self.skills}")
        if self.codebase:
            parts.append(f"[Codebase context — budgeted]\n{self.codebase}")
        if self.history:
            parts.append(f"[Recent conversation — budgeted]\n{self.history}")
        if self.workspace:
            parts.append(f"[Workspace — budgeted]\n{self.workspace}")
        parts.append(self.user_message)
        return "\n\n".join(parts)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def _truncate_to_tokens(text: str, max_tokens: int, *, keep: str = "tail") -> tuple[str, bool]:
    if estimate_tokens(text) <= max_tokens:
        return text, False
    max_chars = max_tokens * CHARS_PER_TOKEN
    if keep == "head":
        return text[:max_chars] + "\n…[truncated]", True
    return "…[truncated]\n" + text[-max_chars:], True


def budget_history(
    history: list[dict[str, Any]] | None,
    *,
    max_tokens: int = 30_000,
    max_turns: int = 20,
) -> tuple[str, bool]:
    """Keep newest turns within token budget (paper: recent conversational turns)."""
    if not history:
        return "", False
    recent = history[-max_turns:]
    lines: list[str] = []
    truncated = False
    # Build from newest backwards so we prefer recent context.
    for h in reversed(recent):
        role = str(h.get("role", "user")).upper()
        content = str(h.get("content", ""))
        line = f"{role}: {content}"
        candidate = "\n".join([line] + lines)
        if estimate_tokens(candidate) > max_tokens:
            truncated = True
            break
        lines.insert(0, line)
    return "\n".join(lines), truncated


def budget_context(
    *,
    user_message: str,
    skills: str = "",
    codebase: str = "",
    history: list[dict[str, Any]] | None = None,
    workspace: str = "",
    budgets: ContextBudgets | None = None,
) -> BudgetedContext:
    """Assemble a budgeted context packet for one turn."""
    b = budgets or ContextBudgets()
    truncated: list[str] = []

    skills_t, t1 = _truncate_to_tokens(skills, b.skills_tokens, keep="head")
    if t1:
        truncated.append("skills")

    codebase_t, t2 = _truncate_to_tokens(codebase, b.codebase_tokens, keep="head")
    if t2:
        truncated.append("codebase")

    history_t, t3 = budget_history(history, max_tokens=b.history_tokens)
    if t3:
        truncated.append("history")

    workspace_t, t4 = _truncate_to_tokens(workspace, b.workspace_tokens, keep="tail")
    if t4:
        truncated.append("workspace")

    # Soft total cap — if still over, shrink codebase then history.
    packet = BudgetedContext(
        skills=skills_t,
        codebase=codebase_t,
        history=history_t,
        workspace=workspace_t,
        user_message=user_message,
        truncated=truncated,
    )
    total = sum(
        estimate_tokens(x)
        for x in (skills_t, codebase_t, history_t, workspace_t, user_message)
    )
    if total > b.total_soft_cap:
        overflow = total - b.total_soft_cap
        # Shrink codebase first (paper: replace inactive files with summaries).
        if estimate_tokens(packet.codebase) > overflow:
            new_cap = max(2_000, estimate_tokens(packet.codebase) - overflow)
            packet.codebase, _ = _truncate_to_tokens(packet.codebase, new_cap, keep="head")
            if "codebase" not in packet.truncated:
                packet.truncated.append("codebase")
        else:
            packet.history, _ = _truncate_to_tokens(
                packet.history,
                max(1_000, estimate_tokens(packet.history) // 2),
                keep="tail",
            )
            if "history" not in packet.truncated:
                packet.truncated.append("history")

    packet.token_estimate = {
        "skills": estimate_tokens(packet.skills),
        "codebase": estimate_tokens(packet.codebase),
        "history": estimate_tokens(packet.history),
        "workspace": estimate_tokens(packet.workspace),
        "user": estimate_tokens(packet.user_message),
        "total": sum(
            estimate_tokens(x)
            for x in (
                packet.skills,
                packet.codebase,
                packet.history,
                packet.workspace,
                packet.user_message,
            )
        ),
    }
    return packet
