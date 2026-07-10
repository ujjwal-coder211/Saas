"""Top-level runner: execute RQ1–RQ6 + §14.2 auxiliaries, assemble a Report."""

from __future__ import annotations

from pathlib import Path

from neuralrouter.evaluation import rq
from neuralrouter.evaluation.report import Report
from neuralrouter.evaluation.tasksets import load_tasks


def run_all(
    *,
    tasks_path: str | Path | None = None,
    rlef_history_path: str | Path | None = None,
    records_path: str | Path | None = None,
) -> Report:
    tasks = load_tasks(tasks_path)
    report = Report(task_set_size=len(tasks))

    for r in rq.rq1_routing_accuracy(tasks):
        report.add(r)
    for r in rq.rq2_synthesis_gain():
        report.add(r)
    for r in rq.rq3_rlef_improvement(rlef_history_path):
        report.add(r)
    for r in rq.rq4_skill_hit_rate(tasks):
        report.add(r)
    for r in rq.rq5_voice_convergence():
        report.add(r)
    for r in rq.rq6_safe_action_rate():
        report.add(r)

    report.add(rq.aux_hallucination_proxy(tasks))
    report.add(rq.aux_recovery_rate(records_path))
    return report


if __name__ == "__main__":
    print(run_all().to_markdown())
