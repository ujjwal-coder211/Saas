"""RLEF — Reinforcement Learning from Execution Feedback (paper §7.5 / §8.2).

This closes the self-evolution loop the paper describes but the repo had only
scaffolded:

  1. Every chat/agent turn emits a ``RoutingRecord`` (paper §5.2.3) with a composite
     reward (paper §7.5.1).
  2. ``log_routing_record`` appends it to an append-only JSONL ledger.
  3. ``collect_cycle`` reads the ledger, filters to high-signal interactions via
     advantage estimates (paper §8.2 steps 1-4) and writes a retrain-ready batch.

The reward is computed from signals available at serve time. ``R_exec`` is the paper's
primary term (test pass/fail); at the chat layer we only have a *proxy* (did a usable
answer come back), so callers that actually run code (the agent loop with ``run_tests``)
should pass ``exec_success`` explicitly for a true execution signal.

Logging is strictly best-effort: a failure here must never break a user response.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# --- reward weights (paper §7.5.1: R = α·R_exec + β·R_quality + γ·R_cost + δ·R_latency + ε·R_user)
ALPHA_EXEC = 0.45
BETA_QUALITY = 0.25
GAMMA_COST = 0.15
DELTA_LATENCY = 0.10
EPSILON_USER = 0.05

LATENCY_CEILING_S = float(os.environ.get("RLEF_LATENCY_CEILING_S", "30"))

_DEFAULT_LEDGER = Path(__file__).resolve().parent / "data" / "rlef" / "routing_records.jsonl"
LEDGER_PATH = Path(os.environ.get("RLEF_RECORDS_PATH", str(_DEFAULT_LEDGER)))

# Premium models cost real money; free OpenRouter/NIM models are ~$0 (paper §11 tiering).
# Used only for the R_cost term — a rough per-1k-token estimate is enough to penalise
# unnecessary premium use, which is exactly what the paper's γ term is for.
_PREMIUM_COST_PER_1K = {
    "claude": 0.015,
    "gpt-4o": 0.010,
    "gpt4o": 0.010,
    "deepseek": 0.002,
}
_COST_CEILING = float(os.environ.get("RLEF_COST_CEILING", "0.05"))

_WRITE_LOCK = threading.Lock()


@dataclass
class RoutingRecord:
    """One RLEF training record (paper §5.2.3 RoutingRecord)."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    query: str = ""                       # truncated for storage
    task_type: str = ""                   # work_mode/output_style proxy for paper TaskClass
    routing_action: list[str] = field(default_factory=list)  # models dispatched
    synthesis_strategy: str = "SINGLE"    # SINGLE | MERGE (collaborative)
    execution_result: str = ""            # ok | error | partial
    quality_score: float = 0.0
    cost_actual: float = 0.0
    latency_ms: int = 0
    reward: float = 0.0
    reward_components: dict[str, float] = field(default_factory=dict)
    user_tier: str = "free"
    brain_version_id: str = "sarva-rules-v0"
    user_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _estimate_cost(models: list[str], tokens: int | None) -> float:
    if not tokens:
        return 0.0
    per_1k = 0.0
    for m in models:
        ml = m.lower()
        for key, cost in _PREMIUM_COST_PER_1K.items():
            if key in ml:
                per_1k = max(per_1k, cost)
    return round((tokens / 1000.0) * per_1k, 6)


def compute_reward(
    *,
    answer: str,
    models: list[str],
    quality_alignment: float,
    latency_s: float,
    tokens: int | None = None,
    exec_success: Optional[bool] = None,
    user_thumbs: Optional[int] = None,
    error_sentinels: tuple[str, ...] = ("[Aksh", "[Error", "[Sarva error"),
) -> tuple[float, dict[str, float], float, str]:
    """Composite reward per paper §7.5.1. Returns (reward, components, cost, exec_label)."""
    # R_exec ∈ {0, 0.3, 1}
    if exec_success is True:
        r_exec, exec_label = 1.0, "ok"
    elif exec_success is False:
        r_exec, exec_label = 0.0, "error"
    else:  # proxy from the answer itself
        a = (answer or "").strip()
        if not a or any(a.startswith(s) for s in error_sentinels):
            r_exec, exec_label = 0.0, "error"
        elif len(a) < 20:
            r_exec, exec_label = 0.3, "partial"
        else:
            r_exec, exec_label = 1.0, "ok"

    # R_quality ∈ [0,1] — registry style alignment + a small structure bonus
    r_quality = max(0.0, min(1.0, quality_alignment))
    if "```" in (answer or ""):
        r_quality = min(1.0, r_quality + 0.05)

    # R_cost ∈ [0,1] — 1 − (actual_cost / ceiling). Free models ⇒ ~1.0
    cost = _estimate_cost(models, tokens)
    r_cost = max(0.0, 1.0 - (cost / _COST_CEILING)) if _COST_CEILING > 0 else 1.0

    # R_latency ∈ [0,1]
    r_latency = max(0.0, 1.0 - (latency_s / LATENCY_CEILING_S)) if LATENCY_CEILING_S > 0 else 1.0

    # R_user ∈ {−1, 0, 1}
    r_user = float(user_thumbs) if user_thumbs in (-1, 0, 1) else 0.0

    reward = (
        ALPHA_EXEC * r_exec
        + BETA_QUALITY * r_quality
        + GAMMA_COST * r_cost
        + DELTA_LATENCY * r_latency
        + EPSILON_USER * r_user
    )
    components = {
        "R_exec": round(r_exec, 4),
        "R_quality": round(r_quality, 4),
        "R_cost": round(r_cost, 4),
        "R_latency": round(r_latency, 4),
        "R_user": round(r_user, 4),
    }
    return round(reward, 4), components, cost, exec_label


def log_routing_record(record: RoutingRecord, *, ledger: Path | None = None) -> bool:
    """Append a record to the JSONL ledger. Best-effort; returns success bool."""
    path = ledger or LEDGER_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with _WRITE_LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True
    except Exception:
        return False


def build_and_log(
    *,
    query: str,
    task_type: str,
    models: list[str],
    collaborative: bool,
    answer: str,
    quality_alignment: float,
    latency_s: float,
    tokens: int | None,
    brain_version_id: str,
    user_id: str | None = None,
    user_tier: str = "free",
    exec_success: Optional[bool] = None,
    user_thumbs: Optional[int] = None,
    ledger: Path | None = None,
) -> Optional[RoutingRecord]:
    """Convenience: compute reward, build a RoutingRecord, log it. Never raises."""
    try:
        reward, components, cost, exec_label = compute_reward(
            answer=answer,
            models=models,
            quality_alignment=quality_alignment,
            latency_s=latency_s,
            tokens=tokens,
            exec_success=exec_success,
            user_thumbs=user_thumbs,
        )
        rec = RoutingRecord(
            query=(query or "")[:500],
            task_type=task_type,
            routing_action=models,
            synthesis_strategy="MERGE" if collaborative else "SINGLE",
            execution_result=exec_label,
            quality_score=components["R_quality"],
            cost_actual=cost,
            latency_ms=int(latency_s * 1000),
            reward=reward,
            reward_components=components,
            user_tier=user_tier,
            brain_version_id=brain_version_id,
            user_id=user_id,
        )
        log_routing_record(rec, ledger=ledger)
        return rec
    except Exception:
        return None


def historical_self_success(task_type: str | None = None, *, ledger: Path | None = None) -> float | None:
    """Empirical self-handle / routing success prior for confidence blend (paper §13).

    Returns mean of R_exec proxies in [0,1] for matching task_type prefix, or None
    if the ledger has too few rows. Used by hybrid routing so confidence can shift
    as RLEF data accumulates — without claiming a trained head yet.
    """
    path = ledger or LEDGER_PATH
    if not path.exists():
        return None
    rewards: list[float] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if task_type:
                    tt = str(row.get("task_type") or "")
                    # Match prefix e.g. "ship:prose:general" vs "general"
                    if task_type not in tt and not tt.endswith(f":{task_type}"):
                        continue
                comps = row.get("reward_components") or {}
                r_exec = comps.get("R_exec")
                if r_exec is None:
                    # Fall back: ok execution_result → 1.0
                    r_exec = 1.0 if row.get("execution_result") == "ok" else 0.0
                rewards.append(float(r_exec))
    except OSError:
        return None
    if len(rewards) < 5:
        return None
    return round(sum(rewards) / len(rewards), 4)


def collect_cycle(
    *,
    ledger: Path | None = None,
    min_advantage: float = 0.15,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Build one RLEF training cycle from the ledger (paper §8.2 steps 1-4).

    1. Load all RoutingRecords.
    2. Compute the value baseline V = mean(reward) over the batch.
    3. Advantage A = R − V (paper step 4).
    4. Retain high-signal records where |A| > ``min_advantage`` (paper step 2 intent:
       exclude ambiguous, near-baseline interactions).
    5. Write the filtered batch + a manifest ready for the routing-head fine-tune.
    """
    path = ledger or LEDGER_PATH
    rows: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    if not rows:
        return {"total": 0, "kept": 0, "ready_for_retrain": False, "note": "ledger empty"}

    baseline = sum(r.get("reward", 0.0) for r in rows) / len(rows)
    kept: list[dict] = []
    for r in rows:
        adv = r.get("reward", 0.0) - baseline
        if abs(adv) > min_advantage:
            r = dict(r)
            r["advantage"] = round(adv, 4)
            kept.append(r)

    out_dir = out_dir or (path.parent / "cycles")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_path = out_dir / f"rlef_cycle_{stamp}.jsonl"
    with batch_path.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "total": len(rows),
        "baseline_value": round(baseline, 4),
        "min_advantage": min_advantage,
        "kept": len(kept),
        "positive": sum(1 for r in kept if r.get("advantage", 0) > 0),
        "negative": sum(1 for r in kept if r.get("advantage", 0) < 0),
        "batch_path": str(batch_path),
        # Paper §8.2 step 7-8: only retrain when the cycle has collected ~1,000 records.
        "ready_for_retrain": len(rows) >= int(os.environ.get("RLEF_CYCLE_SIZE", "1000")),
    }
    (out_dir / f"rlef_manifest_{stamp}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(collect_cycle(), indent=2))
