"""Routing baselines for RQ1 (paper §14.3).

Each baseline maps a task → a chosen primary model id, so routing accuracy
(share matching the oracle label) is comparable across:

    oracle          upper bound (always the labeled best model) → 1.0
    learned         Sarva's hybrid policy (decide_routing)
    heuristic       keyword expert activation only (no confidence reasoning)
    always_premium  quality upper bound / cost lower bound
    random          lower bound (seeded, deterministic)

`learned` is the system under test; the rest are the reference frame the paper
requires so "learned outperforms heuristic" (RQ1) is a measured claim.
"""

from __future__ import annotations

import hashlib

from neuralrouter.router import REGISTRY, activate_experts
from neuralrouter.sarva_brain.routing_policy import decide_routing

# Registry model treated as the "premium" arbiter locally (paper's premium tier).
PREMIUM_MODEL = "kimi"

_ALL_MODELS = sorted(REGISTRY.keys())


def route_oracle(task: dict) -> str:
    return task["oracle_model"]


def route_learned(task: dict) -> str:
    return decide_routing(task["query"]).primary_model


def route_heuristic(task: dict) -> str:
    return activate_experts(task["query"])[0].model_id


def route_always_premium(task: dict) -> str:
    return PREMIUM_MODEL


def route_random(task: dict) -> str:
    """Deterministic pseudo-random: hash the task id → stable model choice."""
    h = int(hashlib.sha256(task["id"].encode()).hexdigest(), 16)
    return _ALL_MODELS[h % len(_ALL_MODELS)]


BASELINES = {
    "oracle": route_oracle,
    "learned": route_learned,
    "heuristic": route_heuristic,
    "always_premium": route_always_premium,
    "random": route_random,
}


def accuracy(router, tasks: list[dict]) -> float:
    """Share of tasks where the router's primary == the oracle label."""
    if not tasks:
        return 0.0
    hits = sum(1 for t in tasks if router(t) == t["oracle_model"])
    return round(hits / len(tasks), 4)


def all_accuracies(tasks: list[dict]) -> dict[str, float]:
    return {name: accuracy(fn, tasks) for name, fn in BASELINES.items()}
