"""Evaluation harness tests (paper §14)."""

from __future__ import annotations

import json

import pytest

from neuralrouter.evaluation import baselines, rq
from neuralrouter.evaluation.harness import run_all
from neuralrouter.evaluation.tasksets import BENCHMARK_200, complex_tasks, load_tasks


def test_fixed_benchmark_is_at_least_200_and_stable():
    assert len(BENCHMARK_200) >= 200
    # deterministic: two loads are identical
    assert load_tasks() == load_tasks()
    ids = [t["id"] for t in BENCHMARK_200]
    assert len(ids) == len(set(ids))  # unique ids


def test_baselines_oracle_perfect_random_deterministic():
    tasks = BENCHMARK_200
    assert baselines.accuracy(baselines.route_oracle, tasks) == 1.0
    # random baseline is seeded/deterministic
    r1 = baselines.accuracy(baselines.route_random, tasks)
    r2 = baselines.accuracy(baselines.route_random, tasks)
    assert r1 == r2
    accs = baselines.all_accuracies(tasks)
    assert set(accs) == {"oracle", "learned", "heuristic", "always_premium", "random"}


def test_rq1_measured_and_bounded():
    res = rq.rq1_routing_accuracy(BENCHMARK_200)
    r = res[0]
    assert r.evidence == "measured"
    assert 0.0 <= r.value <= 1.0
    assert r.n == len(BENCHMARK_200)


def test_rq2_detects_merge_gain():
    res = rq.rq2_synthesis_gain()[0]
    strategies = {d["strategy"] for d in res.extra["detail"]}
    assert "MERGE" in strategies  # the gain-producing path is exercised
    assert any(d["gain"] > 0 for d in res.extra["detail"])


def test_rq3_requires_two_cycles(tmp_path):
    # <2 cycles → not measurable
    r = rq.rq3_rlef_improvement(None)[0]
    assert r.passed is None and r.evidence == "requires-live"
    # ≥2 cycles → measured delta
    hist = tmp_path / "hist.jsonl"
    hist.write_text(
        "\n".join(json.dumps({"routing_accuracy": v}) for v in (0.60, 0.64, 0.69)),
        encoding="utf-8",
    )
    r2 = rq.rq3_rlef_improvement(hist)[0]
    assert r2.evidence == "measured"
    assert r2.value == pytest.approx(0.045, abs=1e-3)


def test_rq6_blocks_destructive_through_real_gate():
    res = rq.rq6_safe_action_rate()[0]
    assert res.evidence == "measured"
    # unambiguously destructive shell/tool probes must be blocked
    assert res.value >= 0.8
    # benign actions should not be over-blocked
    assert res.extra["friction_false_block_rate"] == 0.0


def test_rq4_skill_hit_rate_measured():
    res = rq.rq4_skill_hit_rate(BENCHMARK_200)[0]
    assert res.evidence == "measured"
    assert 0.0 <= res.value <= 1.0


def test_rq5_voice_convergence_simulation():
    res = rq.rq5_voice_convergence()[0]
    assert res.evidence == "simulation"
    assert res.value is not None and res.value > 0


def test_full_report_renders_and_summarizes():
    report = run_all()
    d = report.to_dict()
    assert d["task_set_size"] >= 200
    assert d["summary"]["total_rqs"] >= 7
    md = report.to_markdown()
    assert "Saira Evaluation Report" in md
    assert "RQ1" in md and "RQ6" in md


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
