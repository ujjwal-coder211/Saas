"""Append-only audit trail — paper §6.5.

Every tool call, permission decision, model dispatch, and credential access is
written with timestamp, actor, inputs (redacted), and outcome to an append-only
JSONL log. This is the substrate for enterprise compliance (§16) and
post-incident forensics.

Best-effort and non-blocking: an audit failure must never break a request. Values
are passed through the credential vault's `redact()` so secrets never land in the
log.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT = Path(__file__).resolve().parents[2] / "sarva_training" / "data" / "audit" / "audit.jsonl"
AUDIT_PATH = Path(os.environ.get("SARVA_AUDIT_PATH", str(_DEFAULT)))
_lock = threading.Lock()


def _redact(obj: Any) -> Any:
    try:
        from neuralrouter.security.vault import redact

        if isinstance(obj, str):
            return redact(obj)
        if isinstance(obj, dict):
            return {k: _redact(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_redact(v) for v in obj]
    except Exception:
        pass
    return obj


def record(
    event: str,
    *,
    actor: str = "sarva",
    tool: str | None = None,
    decision: str | None = None,
    risk: str | None = None,
    detail: dict[str, Any] | None = None,
) -> bool:
    """Append one audit event. Never raises."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,          # tool_call | permission | credential | model_dispatch
            "actor": actor,
            "tool": tool,
            "decision": decision,    # approved | denied | ...
            "risk": risk,
            "detail": _redact(detail or {}),
        }
        line = json.dumps(entry, ensure_ascii=False)
        with _lock:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True
    except Exception:
        return False


def tail(n: int = 50) -> list[dict]:
    """Read the last n audit entries (for a compliance dashboard / forensics)."""
    if not AUDIT_PATH.exists():
        return []
    try:
        lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for ln in lines[-n:]:
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out
