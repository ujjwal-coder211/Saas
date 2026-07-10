"""Per-team budget ceilings with live usage (paper §16.1 live dashboards).

File-backed so it works without the SaaS Postgres DB. Each charge is appended to
a per-team ledger and rolled up per calendar month; ``status`` powers the live
dashboard and ``would_exceed`` is the pre-flight check the request path calls
before dispatching a paid model.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()


def _year_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class TeamBudget:
    def __init__(self, team_id: str, ceiling_usd: float, store_dir: str | Path):
        self.team_id = team_id
        self.ceiling_usd = float(ceiling_usd)
        self.ledger = Path(store_dir) / f"budget_{team_id}.jsonl"

    def _spent(self, year_month: str | None = None) -> tuple[float, int]:
        ym = year_month or _year_month()
        total, n = 0.0, 0
        if not self.ledger.exists():
            return 0.0, 0
        for ln in self.ledger.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if row.get("ym") == ym:
                total += float(row.get("cost_usd", 0.0))
                n += 1
        return round(total, 6), n

    def would_exceed(self, cost_usd: float) -> bool:
        spent, _ = self._spent()
        return (spent + max(0.0, cost_usd)) > self.ceiling_usd

    def charge(self, cost_usd: float, *, actor: str = "team", model: str = "") -> dict:
        """Record a charge. Returns {allowed, spent, remaining, tripped}."""
        cost_usd = max(0.0, float(cost_usd))
        with _LOCK:
            spent, _ = self._spent()
            if (spent + cost_usd) > self.ceiling_usd:
                return {
                    "allowed": False,
                    "spent": spent,
                    "remaining": round(max(0.0, self.ceiling_usd - spent), 6),
                    "tripped": True,
                    "reason": "budget_ceiling_reached",
                }
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "ym": _year_month(),
                    "cost_usd": cost_usd,
                    "actor": actor,
                    "model": model,
                }) + "\n")
            spent += cost_usd
        return {
            "allowed": True,
            "spent": round(spent, 6),
            "remaining": round(max(0.0, self.ceiling_usd - spent), 6),
            "tripped": False,
        }

    def status(self) -> dict:
        spent, n = self._spent()
        pct = round(spent / self.ceiling_usd, 4) if self.ceiling_usd > 0 else 0.0
        return {
            "team_id": self.team_id,
            "month": _year_month(),
            "ceiling_usd": self.ceiling_usd,
            "spent_usd": spent,
            "remaining_usd": round(max(0.0, self.ceiling_usd - spent), 6),
            "utilization": pct,
            "charges": n,
            "alert": pct >= 0.8,  # dashboard warning band
        }
