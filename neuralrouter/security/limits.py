"""Cost-runaway defenses — paper §6.1 (loop detection, budget ceiling, kill switch).

Two lightweight, dependency-free guards an agent loop consults before each action:

    LoopGuard   trips when the same (tool, args) action repeats more than
                ``max_repeat`` times in a row — the classic stuck-agent loop.
    BudgetGuard trips when cumulative spend crosses a hard ceiling.

Both expose ``tripped`` (the kill switch) so the event loop can halt and alert
the user rather than burn budget unattended.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


def _action_key(tool: str, args: dict | None) -> str:
    blob = json.dumps({"t": tool, "a": args or {}}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class LoopGuard:
    max_repeat: int = 5
    _last: str = ""
    _streak: int = 0
    tripped: bool = False

    def check(self, tool: str, args: dict | None = None) -> bool:
        """Record an action; return True if allowed, False if the loop tripped."""
        key = _action_key(tool, args)
        if key == self._last:
            self._streak += 1
        else:
            self._last = key
            self._streak = 1
        if self._streak > self.max_repeat:
            self.tripped = True
            return False
        return True

    def reset(self) -> None:
        self._last, self._streak, self.tripped = "", 0, False


@dataclass
class BudgetGuard:
    ceiling_usd: float = 5.0
    spent_usd: float = 0.0
    tripped: bool = False

    def charge(self, cost_usd: float) -> bool:
        """Add spend; return True if still under ceiling, False if it tripped."""
        self.spent_usd = round(self.spent_usd + max(0.0, cost_usd), 6)
        if self.spent_usd > self.ceiling_usd:
            self.tripped = True
            return False
        return True

    def remaining(self) -> float:
        return round(max(0.0, self.ceiling_usd - self.spent_usd), 6)
