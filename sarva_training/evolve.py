"""Self-evolution orchestration — paper §4.4 (distillation) + §8 (RLEF cycle).

Ties the pieces into one automated "prepare the next training cycle" step:

  1. Multi-source distillation (§4.4): assemble conductor training rows from
       - RLEF ledger high-reward interactions (learn from what routed well), and
       - the harvest reservoir (teacher outputs), when present.
  2. RLEF cycle gate (§8.2): only signal ``ready_for_retrain`` once enough
     high-signal records have accumulated.

What this does NOT do (needs a GPU, external): the actual PPO/QLoRA fine-tune.
This step produces the retrain-ready JSONL + a manifest that `train_sarva.py`
consumes — the orchestration is code; the training run is infrastructure.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sarva_training.rlef import LEDGER_PATH

_OUT_DIR = Path(__file__).resolve().parent / "data" / "evolution"
REWARD_KEEP = float(os.environ.get("SARVA_DISTILL_REWARD_MIN", "0.7"))
CYCLE_SIZE = int(os.environ.get("RLEF_CYCLE_SIZE", "1000"))

_ROUTING_SYSTEM = (
    "You are Sarva, an intelligent conductor AI. Analyze the user query and decide "
    "the best routing plan. Respond with valid JSON only."
)


def _load_ledger(path: Path | None = None) -> list[dict]:
    p = path or LEDGER_PATH
    rows: list[dict] = []
    if not p.exists():
        return rows
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return rows


def _record_to_training_row(rec: dict) -> dict | None:
    """Turn a high-reward RoutingRecord into a conductor SFT row (messages fmt)."""
    query = rec.get("query")
    models = rec.get("routing_action") or []
    if not query or not models:
        return None
    plan = {
        "primary_model": models[0],
        "secondary_models": models[1:],
        "parallel": rec.get("synthesis_strategy") == "MERGE",
        "complexity": "high" if len(models) > 1 else "medium",
        "task_type": rec.get("task_type", "general"),
        "reason": f"learned from reward {rec.get('reward')}",
    }
    return {
        "messages": [
            {"role": "system", "content": _ROUTING_SYSTEM},
            {"role": "user", "content": f"Query: {query}\nReturn routing JSON:"},
            {"role": "assistant", "content": json.dumps(plan)},
        ],
        "_source": "rlef_distill",
        "_reward": rec.get("reward"),
    }


def _harvest_rows(reservoir: Path) -> list[dict]:
    """Optional: teacher outputs from the harvest reservoir → distillation rows."""
    rows: list[dict] = []
    if not reservoir.exists():
        return rows
    for ln in reservoir.read_text(encoding="utf-8").splitlines()[:5000]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        q, ans, model = r.get("query"), r.get("response") or r.get("content"), r.get("model")
        if q and ans:
            rows.append({
                "messages": [
                    {"role": "system", "content": _ROUTING_SYSTEM},
                    {"role": "user", "content": f"Query: {q}\nReturn routing JSON:"},
                    {"role": "assistant", "content": json.dumps({
                        "primary_model": model or "qwen", "secondary_models": [],
                        "parallel": False, "complexity": "medium",
                        "task_type": "general", "reason": "teacher distillation",
                    })},
                ],
                "_source": "harvest_distill",
            })
    return rows


def prepare_evolution_cycle(
    *,
    ledger: Path | None = None,
    reservoir: Path | None = None,
    out_dir: Path | None = None,
) -> dict:
    """Assemble the next training cycle from RLEF + harvest. Returns a manifest."""
    records = _load_ledger(ledger)
    high = [r for r in records if r.get("reward", 0) >= REWARD_KEEP]
    rlef_rows = [row for row in (_record_to_training_row(r) for r in high) if row]

    harvest_rows: list[dict] = []
    if reservoir is not None:
        harvest_rows = _harvest_rows(reservoir)

    all_rows = rlef_rows + harvest_rows
    out_dir = out_dir or _OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = out_dir / f"evolution_cycle_{stamp}.jsonl"
    with batch.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ledger_total": len(records),
        "high_reward": len(high),
        "rlef_rows": len(rlef_rows),
        "harvest_rows": len(harvest_rows),
        "total_rows": len(all_rows),
        "batch_path": str(batch),
        "ready_for_retrain": len(records) >= CYCLE_SIZE and len(all_rows) > 0,
        "next": "feed batch_path to deploy/runpod/train_sarva.py via DATA_PATH + RESUME_ADAPTER",
    }
    (out_dir / f"evolution_manifest_{stamp}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(prepare_evolution_cycle(), indent=2))
