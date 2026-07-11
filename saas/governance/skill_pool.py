"""Team skill pooling over Hermes (paper §16.1: "one engineer's solved problem
benefits all").

A member promotes a curated personal skill into the team pool; from then on it is
injected for every team member. File-backed JSONL, one pool per team. Only skills
above the curator floor (paper §12) are poolable, so weak patterns don't spread.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
CURATOR_FLOOR = 0.5  # paper §12: prune/never-pool skills below 0.5 success


def _pool_path(store_dir: str | Path, team_id: str) -> Path:
    return Path(store_dir) / f"skillpool_{team_id}.jsonl"


def pool_skill(
    store_dir: str | Path,
    team_id: str,
    *,
    skill_key: str,
    author: str,
    success_rate: float,
    trigger: str,
    procedure: str = "",
) -> dict:
    """Promote a personal skill into the team pool. Returns {pooled, reason}."""
    if success_rate < CURATOR_FLOOR:
        return {"pooled": False, "reason": f"below_curator_floor_{CURATOR_FLOOR}"}
    path = _pool_path(store_dir, team_id)
    with _LOCK:
        existing = {s["skill_key"]: s for s in _read(path)}
        existing[skill_key] = {
            "skill_key": skill_key,
            "author": author,
            "success_rate": round(float(success_rate), 4),
            "trigger": trigger,
            "procedure": procedure,
            "pooled_at": datetime.now(timezone.utc).isoformat(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for s in existing.values():
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return {"pooled": True, "skill_key": skill_key, "team_id": team_id}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def team_skills(store_dir: str | Path, team_id: str) -> list[dict]:
    """All pooled skills for a team, best success-rate first (curated only)."""
    skills = [s for s in _read(_pool_path(store_dir, team_id)) if s.get("success_rate", 0) >= CURATOR_FLOOR]
    return sorted(skills, key=lambda s: s.get("success_rate", 0), reverse=True)
