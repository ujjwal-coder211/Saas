"""Multi-model synthesis scoring + strategy — paper §7.2.

When several models answer the same subtask, score each output and pick a fusion
strategy:

  Q(o) = 0.40·syntax + 0.30·logic + 0.20·style + 0.10·confidence

  DEFER_TO_BEST : max(Q) − min(Q) > 0.40   → return highest-scoring output
  VOTE          : all Q within 0.15         → structural majority, tie-break by Q
  MERGE         : complementary strengths   → combine best algorithm + best code
  ESCALATE      : fundamental contradiction → send to premium arbiter

Honesty note: syntax is checked for real (Python parse); logic/style/confidence
are heuristic proxies, not model judgments. The STRATEGY SELECTION is the real,
testable part; the per-axis scores are legible stand-ins for a trained scorer.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

W_SYNTAX, W_LOGIC, W_STYLE, W_CONF = 0.40, 0.30, 0.20, 0.10


def _has_code(text: str) -> bool:
    return "```" in text or bool(re.search(r"\bdef \w+\(|\bclass \w+|\bimport \w+", text))


def _extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", text, re.S)
    return "\n".join(blocks) if blocks else text


def _syntax_score(text: str) -> float:
    if not _has_code(text):
        return 0.8  # prose: no syntax to fail
    code = _extract_code(text)
    if not re.search(r"\bdef \w+\(|\bclass \w+|\bimport \w+", code):
        return 0.8
    try:
        ast.parse(code)
        return 1.0
    except SyntaxError:
        return 0.0


def _logic_score(text: str) -> float:
    s = 0.5
    if any(k in text.lower() for k in ("because", "therefore", "so that", "step", "first", "then")):
        s += 0.25
    if len(text) > 120:
        s += 0.15
    if any(k in text.lower() for k in ("todo", "fixme", "not sure", "i think maybe")):
        s -= 0.25
    return max(0.0, min(1.0, s))


def _style_score(text: str) -> float:
    s = 0.5
    if "```" in text:
        s += 0.2
    if re.search(r"^[-*]\s|\n[-*]\s|\n#{1,3}\s", text):
        s += 0.15
    if len(text) > 4000:
        s -= 0.2  # overly verbose
    return max(0.0, min(1.0, s))


@dataclass
class OutputScore:
    model: str
    Q: float
    syntax: float
    logic: float
    style: float
    confidence: float

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "Q": round(self.Q, 3),
            "syntax": round(self.syntax, 3),
            "logic": round(self.logic, 3),
            "style": round(self.style, 3),
            "confidence": round(self.confidence, 3),
        }


def score_output(model: str, text: str, confidence: float = 0.6) -> OutputScore:
    syn = _syntax_score(text)
    log = _logic_score(text)
    sty = _style_score(text)
    conf = max(0.0, min(1.0, confidence))
    Q = W_SYNTAX * syn + W_LOGIC * log + W_STYLE * sty + W_CONF * conf
    return OutputScore(model=model, Q=Q, syntax=syn, logic=log, style=sty, confidence=conf)


@dataclass
class SynthesisDecision:
    strategy: str  # DEFER_TO_BEST | VOTE | MERGE | ESCALATE
    winner: str
    scores: list[dict] = field(default_factory=list)
    reason: str = ""


def choose_strategy(outputs: list[tuple[str, str, float]]) -> SynthesisDecision:
    """outputs = [(model, text, confidence), ...]. Returns the fusion decision."""
    if not outputs:
        return SynthesisDecision(strategy="DEFER_TO_BEST", winner="", reason="no outputs")
    scored = [score_output(m, t, c) for m, t, c in outputs]
    scored.sort(key=lambda s: s.Q, reverse=True)
    qs = [s.Q for s in scored]
    spread = qs[0] - qs[-1]
    best = scored[0]
    payload = [s.to_dict() for s in scored]

    if len(scored) == 1:
        return SynthesisDecision("DEFER_TO_BEST", best.model, payload, "single output")

    # Contradiction: one output has valid code/logic, another clearly fails syntax.
    syn_vals = [s.syntax for s in scored]
    if max(syn_vals) >= 0.9 and min(syn_vals) <= 0.1:
        return SynthesisDecision("ESCALATE", best.model, payload, "syntax contradiction between outputs")

    if spread > 0.40:
        return SynthesisDecision("DEFER_TO_BEST", best.model, payload, f"clear leader (spread {spread:.2f})")

    if spread <= 0.15:
        return SynthesisDecision("VOTE", best.model, payload, f"outputs close (spread {spread:.2f})")

    # Complementary strengths: different axes lead in different outputs.
    top_syntax = max(scored, key=lambda s: s.syntax).model
    top_logic = max(scored, key=lambda s: s.logic).model
    if top_syntax != top_logic:
        return SynthesisDecision("MERGE", best.model, payload, f"complementary: code={top_syntax}, logic={top_logic}")
    return SynthesisDecision("DEFER_TO_BEST", best.model, payload, "moderate spread, no complementarity")
