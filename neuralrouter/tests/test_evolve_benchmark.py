"""§4/§8 evolution + §14 benchmark tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_prepare_evolution_cycle(tmp_path):
    from sarva_training.evolve import prepare_evolution_cycle

    ledger = tmp_path / "rlef.jsonl"
    rows = [
        {"query": "fix async bug", "routing_action": ["nemotron"], "reward": 0.9, "task_type": "code"},
        {"query": "write tests", "routing_action": ["qwen", "kimi"], "reward": 0.8,
         "synthesis_strategy": "MERGE", "task_type": "code"},
        {"query": "low signal", "routing_action": ["qwen"], "reward": 0.2, "task_type": "general"},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    m = prepare_evolution_cycle(ledger=ledger, out_dir=tmp_path / "out")
    assert m["ledger_total"] == 3
    assert m["high_reward"] == 2         # reward >= 0.7
    assert m["rlef_rows"] == 2
    # produced batch is valid conductor rows
    batch = Path(m["batch_path"])
    lines = [json.loads(l) for l in batch.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert lines[0]["messages"][0]["role"] == "system"
    plan = json.loads(lines[0]["messages"][-1]["content"])
    assert "primary_model" in plan


def test_run_benchmark_offline():
    from sarva_training.benchmark import run_benchmark

    r = run_benchmark()
    assert r["n"] == 8
    assert 0.0 <= r["self_handle_calibration"] <= 1.0
    assert 0.0 <= r["routing_accuracy"] <= 1.0
    # cost efficiency should be strongly positive (free-first routing vs premium baseline)
    assert r["cost_efficiency_reduction"] > 0.9


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
