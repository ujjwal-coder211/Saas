"""Adaptive permission promotion — paper §6.2.

"When a user consistently approves a specific action type in a specific context,
that pair is promoted toward auto-approval." So security and usability improve
together instead of trading off.

We track (tool, context) approval history in a small JSONL store. A pair is
*promoted* once it has been approved at least ``PROMOTE_AFTER`` times with no
denials recorded since. A promoted pair lets the gate auto-approve an action that
would otherwise need confirmation — but high-risk / blocked outcomes are never
promoted (those always keep their friction, per §6.2). This is the HCI trade-off
the paper registers as open question RQ-D; the mechanism is here, the optimal
curve is an empirical question.
"""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_STORE = Path(
    os.environ.get(
        "SARVA_TRUST_STORE",
        str(Path(__file__).resolve().parents[2] / "sarva_training" / "data" / "trust" / "approvals.jsonl"),
    )
)
PROMOTE_AFTER = int(os.environ.get("SARVA_PROMOTE_AFTER", "5"))
_lock = threading.Lock()

# Tiers that must never be auto-promoted, however often approved.
_NEVER_PROMOTE = {"blocked", "high"}


def _key(tool: str, context: str) -> str:
    return f"{tool}|{context or 'default'}"


def record_approval(tool: str, *, context: str = "default", approved: bool, risk: str = "medium") -> bool:
    """Log an approval decision for a (tool, context). Never raises."""
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with _lock, _STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "key": _key(tool, context), "approved": bool(approved), "risk": risk,
            }) + "\n")
        return True
    except Exception:
        return False


def _history() -> dict[str, list[dict]]:
    hist: dict[str, list[dict]] = defaultdict(list)
    if not _STORE.exists():
        return hist
    try:
        for ln in _STORE.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            row = json.loads(ln)
            hist[row["key"]].append(row)
    except Exception:
        pass
    return hist


def is_promoted(tool: str, *, context: str = "default") -> bool:
    """True if this (tool, context) has earned auto-approval."""
    rows = _history().get(_key(tool, context), [])
    if not rows:
        return False
    # No denials, and at least PROMOTE_AFTER approvals. Also never promote
    # a pair whose observed risk was high/blocked.
    if any(not r.get("approved") for r in rows):
        return False
    if any(r.get("risk") in _NEVER_PROMOTE for r in rows):
        return False
    return len(rows) >= PROMOTE_AFTER


def promoted_pairs() -> list[str]:
    out = []
    for k in _history():
        tool, _, ctx = k.partition("|")
        if is_promoted(tool, context=ctx or "default"):
            out.append(k)
    return out
