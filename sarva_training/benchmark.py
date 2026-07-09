"""Routing benchmark — paper §14 (offline runnable slice).

A fixed benchmark task set plus a runner that scores the *routing decision* the
conductor makes, with no model calls — so RQ1-style routing behaviour is testable
today. Each task carries an ``oracle`` (the model a human would pick) and
``expect_self`` (whether Sarva should self-handle). The runner uses the live
hybrid policy (`decide_routing`) and feeds the outcome into `evaluate()`.

The quality/cost columns needed for the full §14 metrics still require running the
models (future work); this slice measures routing fit and self-handle calibration
deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

from neuralrouter.sarva_brain.routing_policy import decide_routing
from sarva_training.evaluate import evaluate

# (query, oracle_model, expect_self_handle)
BENCHMARK: list[dict] = [
    {"query": "what is a python list", "oracle": "qwen", "expect_self": True},
    {"query": "fix a typo in the readme", "oracle": "qwen", "expect_self": True},
    {"query": "design a secure distributed auth system with JWT", "oracle": "kimi", "expect_self": False},
    {"query": "debug this async race condition in the worker", "oracle": "nemotron", "expect_self": False},
    {"query": "prove quicksort is O(n log n) average case", "oracle": "nemotron", "expect_self": False},
    {"query": "rename a variable in utils.py", "oracle": "qwen", "expect_self": True},
    {"query": "refactor the entire payments module to async", "oracle": "nemotron", "expect_self": False},
    {"query": "audit this code for security vulnerabilities", "oracle": "kimi", "expect_self": False},
]


def run_benchmark(tasks: list[dict] | None = None) -> dict:
    """Route each task with the hybrid policy; score self-handle calibration + fit."""
    tasks = tasks or BENCHMARK
    records: list[dict] = []
    self_correct = 0
    for t in tasks:
        trace = decide_routing(t["query"])
        self_ok = trace.self_executable == t["expect_self"]
        self_correct += int(self_ok)
        records.append({
            "task_id": t["query"][:40],
            "chosen_model": trace.primary_model,
            "oracle_model": t["oracle"],
            "quality": 0.85 if self_ok else 0.6,   # placeholder until models run
            "cost_usd": 0.001,
            "baseline_quality": 0.9,
            "baseline_cost_usd": 0.02,
            "self_handle_correct": self_ok,
        })
    scored = evaluate(records)
    return {
        "n": len(tasks),
        "self_handle_calibration": round(self_correct / len(tasks), 4),
        "routing_accuracy": scored["metrics"]["routing_accuracy"],
        "cost_efficiency_reduction": scored["metrics"]["cost_efficiency_reduction"],
        "detail": records,
        "note": "Routing/self-handle scored offline; full quality metrics need model runs (§14 future work).",
    }


if __name__ == "__main__":
    print(json.dumps({k: v for k, v in run_benchmark().items() if k != "detail"}, indent=2))
