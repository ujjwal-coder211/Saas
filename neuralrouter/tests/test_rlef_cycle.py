"""RLEF end-to-end cycle orchestration tests (paper §8.2)."""

from __future__ import annotations

import json

import pytest

from sarva_training import rlef_cycle
from sarva_training.rlef import RoutingRecord, log_routing_record


def _seed_ledger(path, n=12):
    # varied rewards so the advantage filter keeps a meaningful subset
    for i in range(n):
        rec = RoutingRecord(
            query=f"task {i}",
            task_type="code",
            routing_action=["nemotron"] if i % 2 else ["qwen"],
            reward=0.9 if i % 2 else 0.2,
            reward_components={"R_exec": 1.0 if i % 2 else 0.0},
        )
        log_routing_record(rec, ledger=path)


def test_cycle_waits_when_not_enough_data(tmp_path):
    ledger = tmp_path / "led.jsonl"
    _seed_ledger(ledger, 5)
    r = rlef_cycle.run_cycle(ledger=ledger, record_history=False, force=False)
    assert r["status"] == "waiting_for_data"
    assert r["need"] >= 1000


def test_dry_run_cycle_measures_and_records(tmp_path):
    ledger = tmp_path / "led.jsonl"
    hist = tmp_path / "hist.jsonl"
    _seed_ledger(ledger, 12)
    r = rlef_cycle.run_cycle(
        ledger=ledger,
        force=True,  # bypass the 1000-record gate for the test
        history_path=hist,
        evolution_out_dir=tmp_path / "evo",
    )
    assert r["status"] == "dry_run_complete"
    assert r["mode"] == "dry_run"
    assert 0.0 <= r["baseline_routing_accuracy"] <= 1.0
    assert r["candidate_routing_accuracy"] >= r["baseline_routing_accuracy"]
    assert hist.exists()
    rows = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()]
    assert len(rows) == 1 and rows[0]["mode"] == "dry_run"


def test_dry_run_never_touches_real_registry(tmp_path):
    from sarva_training import brain_registry

    before = brain_registry.load_registry()["active_version_id"]
    rlef_cycle.run_cycle(
        ledger=tmp_path / "led.jsonl",  # empty → waiting, but ensure no mutation
        force=True,
        history_path=tmp_path / "h.jsonl",
        evolution_out_dir=tmp_path / "evo",
    )
    after = brain_registry.load_registry()["active_version_id"]
    assert before == after  # dry-run must not promote anything


def test_multi_cycle_history_makes_rq3_measurable(tmp_path):
    from neuralrouter.evaluation import rq

    ledger = tmp_path / "led.jsonl"
    hist = tmp_path / "hist.jsonl"
    _seed_ledger(ledger, 12)
    for _ in range(3):
        rlef_cycle.run_cycle(
            ledger=ledger, force=True, history_path=hist, evolution_out_dir=tmp_path / "evo"
        )
    res = rq.rq3_rlef_improvement(hist)[0]
    assert res.n == 3
    assert res.value is not None  # now measurable
    assert res.evidence == "simulation"  # dry-run cycles are honestly labelled


def test_live_apply_requires_candidate(tmp_path):
    r = rlef_cycle.run_cycle(
        apply=True, ledger=tmp_path / "led.jsonl", force=True,
        history_path=tmp_path / "h.jsonl", evolution_out_dir=tmp_path / "evo",
    )
    assert r["status"] == "error"
    assert "candidate" in r["note"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
