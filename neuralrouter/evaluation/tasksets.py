"""Fixed labeled benchmark task set (paper §14 "fixed 200-task benchmark").

Each task is generated deterministically (no RNG, stable order) so the set is
reproducible across runs and machines — the paper's "fixed" requirement. A task
carries human-assigned labels used as ground truth for the RQ evaluators:

    id                : stable identifier
    query             : the user request
    task_type         : general | code | reasoning | security | architecture
    complexity        : low | medium | high
    oracle_model      : the model a human would pick (RQ1 ground truth)
    expect_self       : should Sarva self-handle? (self-handle calibration)
    hallucination_risk: needs grounding/search rather than free recall
    skill_trigger     : a Hermes skill key this task should match (RQ4), or None

Oracle labels reflect the registry's model specialties, assigned independently
of the routing policy — so RQ1 measures how well the policy matches human labels
rather than trivially scoring itself.
"""

from __future__ import annotations

import json
from pathlib import Path

# model specialties → oracle label per task type (from models_registry/*.json)
_ORACLE = {
    "general": "qwen",
    "code": "nemotron",
    "reasoning": "glm",
    "security": "kimi",
    "architecture": "nemotron",
}

# (template, task_type, complexity, expect_self, hallucination_risk, skill_trigger)
_TEMPLATES = [
    # simple/general — Sarva should self-handle
    ("what is {s}", "general", "low", True, False, "explain-concept"),
    ("define {s} in one line", "general", "low", True, False, "explain-concept"),
    ("convert {s} to json", "general", "low", True, False, "format-convert"),
    ("rename the variable {s} in utils.py", "general", "low", True, False, "safe-rename"),
    ("fix the typo in the {s} section of the readme", "general", "low", True, False, None),
    ("list the fields of the {s} model", "general", "low", True, False, None),
    ("summarize the {s} module in one line", "general", "low", True, False, None),
    ("translate the {s} label to spanish", "general", "low", True, False, None),
    # code — delegate
    ("write a function to validate {s}", "code", "medium", False, False, "codegen"),
    ("fix the bug in the {s} handler", "code", "medium", False, False, "bugfix"),
    ("debug this async race condition in the {s} worker", "code", "high", False, False, "deep-debug"),
    ("trace the root cause of the {s} segfault", "code", "high", False, False, "deep-debug"),
    ("write pytest unit tests for the {s} module", "code", "medium", False, False, "test-gen"),
    ("optimize the {s} algorithm for performance", "code", "high", False, False, "perf"),
    # reasoning — delegate to reasoning-capable
    ("explain why {s} improves throughput", "reasoning", "medium", False, False, None),
    ("prove that the {s} routine terminates", "reasoning", "high", False, False, None),
    ("compare {s} and its alternative on trade-offs", "reasoning", "high", False, False, None),
    # security — always delegate, high bar
    ("audit the {s} endpoint for vulnerabilities", "security", "high", False, False, "sec-audit"),
    ("design a secure {s} flow with JWT", "security", "high", False, False, "sec-design"),
    ("check the {s} form for injection risks", "security", "medium", False, False, "sec-audit"),
    # architecture — delegate, multi
    ("design a system for {s} at scale", "architecture", "high", False, False, "arch-design"),
    ("refactor the entire {s} module to async", "architecture", "high", False, False, "refactor"),
    # grounding / hallucination-risk — must not free-recall
    ("what is the latest version of {s} as of today", "general", "medium", False, True, None),
    ("what is the current price of {s} stock today", "general", "medium", False, True, None),
]

_SUBJECTS = [
    "auth", "payments", "the cache layer", "the search index", "the user profile",
    "the checkout", "the webhook", "the rate limiter", "the queue", "the scheduler",
]


def _build() -> list[dict]:
    tasks: list[dict] = []
    idx = 0
    for tmpl, ttype, cx, self_ok, halluc, skill in _TEMPLATES:
        for subj in _SUBJECTS:
            idx += 1
            tasks.append(
                {
                    "id": f"t{idx:03d}",
                    "query": tmpl.format(s=subj),
                    "task_type": ttype,
                    "complexity": cx,
                    "oracle_model": _ORACLE[ttype],
                    "expect_self": self_ok,
                    "hallucination_risk": halluc,
                    "skill_trigger": skill,
                }
            )
    return tasks


# 23 templates × 10 subjects = 230 tasks (≥ the paper's fixed 200-task benchmark)
BENCHMARK_200: list[dict] = _build()


def load_tasks(path: str | Path | None = None) -> list[dict]:
    """Load the fixed benchmark, or a user-supplied JSONL of the same schema."""
    if path is None:
        return list(BENCHMARK_200)
    p = Path(path)
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def complex_tasks(tasks: list[dict] | None = None) -> list[dict]:
    tasks = tasks or BENCHMARK_200
    return [t for t in tasks if t["complexity"] == "high"]


if __name__ == "__main__":
    print(f"{len(BENCHMARK_200)} tasks")
    print(json.dumps(BENCHMARK_200[:3], indent=2))
