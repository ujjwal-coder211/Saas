"""Sarva confidence-based self-routing (paper v4 §3.3).

Ported from the saira_harvest Phase-1 `sarva/confidence.py`. Sarva asks itself
"can I do this well enough on my own?" before delegating. High confidence →
self-execute (cheap, fast, no premium API). Low confidence or high-stakes →
delegate to a teacher model.

Honesty note (same as the source): this is a HEURISTIC PROXY for the paper's
trained confidence model. There is no gradient learning here. What is real:
lexical signals that correlate with difficulty, plus an optional historical
success-rate blend (fed from the RLEF ledger / Hermes) so the score can shift
as data accumulates. Returns a float in [0, 1].
"""

from __future__ import annotations

# Signals that push confidence DOWN — these tasks benefit from a stronger model.
COMPLEXITY_SIGNALS = [
    "architecture", "design a system", "security", "vulnerability",
    "prove", "optimize algorithm", "distributed", "concurrency bug",
    "refactor the entire", "migrate", "race condition", "audit",
]

# Signals that push confidence UP — simple, well-scoped tasks Sarva can do alone.
SIMPLE_SIGNALS = [
    "what is", "define", "convert", "format", "rename", "fix typo",
    "list", "summarize in one line", "capital of", "translate",
]

# Task types the paper treats as inherently higher-stakes (higher bar to self-handle).
HIGH_STAKES_TASK_TYPES = {"security", "reasoning", "code"}


def _lexical_score(query: str) -> float:
    q = (query or "").lower()
    score = 0.6  # neutral baseline
    for signal in COMPLEXITY_SIGNALS:
        if signal in q:
            score -= 0.15
    for signal in SIMPLE_SIGNALS:
        if signal in q:
            score += 0.15
    word_count = len(q.split())
    if word_count > 60:
        score -= 0.15  # long asks are more likely multi-step
    elif word_count < 12:
        score += 0.05  # short asks are more likely simple
    return max(0.0, min(1.0, score))


def self_assess(query: str, task_type: str = "general", historical: float | None = None) -> float:
    """Confidence in [0,1] that Sarva can answer this well on its own.

    ``historical`` is an optional observed self-handle success rate for this
    task_type (0..1), e.g. from the RLEF ledger. When present it is blended in
    and weighted more heavily than the lexical guess.
    """
    lexical = _lexical_score(query)
    if historical is None:
        return round(lexical, 4)
    return round(0.4 * lexical + 0.6 * historical, 4)


def threshold_for(task_type: str) -> float:
    """Per-task-type bar for 'confident enough to self-execute'.

    High-stakes categories get a higher bar — approximates the paper's
    'high-stakes tasks always delegate' principle without a learned classifier.
    """
    return 0.75 if task_type in HIGH_STAKES_TASK_TYPES else 0.6
