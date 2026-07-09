"""Failure-mode guards — paper §12.

Runtime safety rails for an autonomous run: loop detection, a hard budget
ceiling, a step limit, and a manual kill switch. A `RunGuard` tracks one
session/agent run and, before each action, returns whether to continue or abort
with a reason — so an agent that loops or burns budget stops itself rather than
running unattended.

Codifies the paper's §12 rows: "loop / cost runaway → loop detection, hard budget
ceiling, automatic kill switch" and "repeated mis-routing → routing confidence
floor / fall back to heuristic prior".
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field


@dataclass
class GuardDecision:
    ok: bool
    reason: str = "ok"
    aborted: bool = False


@dataclass
class RunGuard:
    """One autonomous run's safety envelope."""

    budget_usd: float = float(os.environ.get("SARVA_BUDGET_CEILING_USD", "1.0"))
    max_steps: int = int(os.environ.get("SARVA_MAX_STEPS", "24"))
    loop_threshold: int = int(os.environ.get("SARVA_LOOP_THRESHOLD", "3"))

    spent_usd: float = 0.0
    steps: int = 0
    _recent: list[str] = field(default_factory=list)
    _killed: bool = False

    @staticmethod
    def _sig(tool: str, args: dict | None) -> str:
        payload = f"{tool}:{sorted((args or {}).items(), key=lambda kv: kv[0])}"
        return hashlib.sha1(payload.encode()).hexdigest()[:12]

    def kill(self, reason: str = "manual_kill_switch") -> None:
        self._killed = True
        self._kill_reason = reason  # type: ignore[attr-defined]

    def before_action(self, tool: str, args: dict | None = None, *, est_cost: float = 0.0) -> GuardDecision:
        """Call before every tool action. Returns whether to proceed."""
        if self._killed:
            return GuardDecision(ok=False, reason=getattr(self, "_kill_reason", "killed"), aborted=True)

        if self.steps >= self.max_steps:
            return GuardDecision(ok=False, reason=f"step_limit_reached:{self.max_steps}", aborted=True)

        if self.spent_usd + est_cost > self.budget_usd:
            return GuardDecision(
                ok=False,
                reason=f"budget_ceiling_exceeded:{self.spent_usd + est_cost:.4f}>{self.budget_usd}",
                aborted=True,
            )

        sig = self._sig(tool, args)
        recent_same = self._recent[-(self.loop_threshold - 1):].count(sig) if self.loop_threshold > 1 else 0
        if recent_same >= self.loop_threshold - 1 and self.loop_threshold > 1:
            return GuardDecision(
                ok=False,
                reason=f"loop_detected:{tool} repeated {self.loop_threshold}x",
                aborted=True,
            )
        return GuardDecision(ok=True)

    def after_action(self, tool: str, args: dict | None = None, *, cost: float = 0.0) -> None:
        """Record a completed action's cost + signature."""
        self.steps += 1
        self.spent_usd += max(0.0, cost)
        self._recent.append(self._sig(tool, args))
        if len(self._recent) > 50:
            self._recent = self._recent[-50:]

    def status(self) -> dict:
        return {
            "steps": self.steps,
            "max_steps": self.max_steps,
            "spent_usd": round(self.spent_usd, 4),
            "budget_usd": self.budget_usd,
            "killed": self._killed,
        }


# Routing-confidence floor (§12 "repeated mis-routing"): below this, prefer the
# heuristic prior / delegate rather than trusting a shaky learned decision.
ROUTING_CONFIDENCE_FLOOR = float(os.environ.get("SARVA_ROUTING_FLOOR", "0.35"))


def routing_below_floor(confidence: float) -> bool:
    return confidence < ROUTING_CONFIDENCE_FLOOR
