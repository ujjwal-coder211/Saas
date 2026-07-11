"""Report model + renderer for the §14 evaluation harness.

Every research-question result is scored against a pre-registered §14.2 target
and tagged with an *evidence class* so a reader can tell a measured number from
a proxy or a simulation:

    measured       computed from real system behaviour on the fixed task set
                   (routing decisions, the live permission gate, synthesis
                   scoring) — deterministic and reproducible now.
    proxy          a legible stand-in for a metric that ultimately needs live
                   model runs (e.g. grounding discipline as a hallucination
                   proxy).
    simulation     a forward projection from a stated model (e.g. voice WER
                   convergence) — honest about being a projection.
    requires-live  genuinely needs running the models against real tasks;
                   read from a supplied records file or reported as N/A.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class RQResult:
    rq: str
    question: str
    metric_name: str
    value: float | None
    target: float | None
    comparator: str  # ">=" | ">" | "<" | "n/a"
    evidence: str  # measured | proxy | simulation | requires-live
    n: int = 0
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool | None:
        if self.value is None or self.target is None or self.comparator == "n/a":
            return None
        if self.comparator == ">=":
            return self.value >= self.target
        if self.comparator == ">":
            return self.value > self.target
        if self.comparator == "<":
            return self.value < self.target
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


@dataclass
class Report:
    results: list[RQResult] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    task_set_size: int = 0

    def add(self, r: RQResult) -> None:
        self.results.append(r)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "task_set_size": self.task_set_size,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary(),
        }

    def summary(self) -> dict:
        checkable = [r for r in self.results if r.passed is not None]
        return {
            "total_rqs": len(self.results),
            "checkable": len(checkable),
            "passed": sum(1 for r in checkable if r.passed),
            "failed": sum(1 for r in checkable if r.passed is False),
            "not_yet_measurable": sum(1 for r in self.results if r.passed is None),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        def _fmt(v):
            return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

        def _mark(r: RQResult) -> str:
            if r.passed is None:
                return "⏳ n/a"
            return "✅ pass" if r.passed else "❌ fail"

        lines = [
            "# Saira Evaluation Report (§14)",
            "",
            f"_Generated {self.generated_at} · task set: {self.task_set_size} tasks_",
            "",
            "| RQ | Metric | Value | Target | Result | Evidence | n |",
            "|----|--------|-------|--------|--------|----------|---|",
        ]
        for r in self.results:
            tgt = "—" if r.target is None else f"{r.comparator} {_fmt(r.target)}"
            lines.append(
                f"| {r.rq} | {r.metric_name} | {_fmt(r.value)} | {tgt} | "
                f"{_mark(r)} | {r.evidence} | {r.n} |"
            )
        s = self.summary()
        lines += [
            "",
            f"**Summary:** {s['passed']}/{s['checkable']} checkable RQs pass · "
            f"{s['not_yet_measurable']} not yet measurable (need live model runs).",
            "",
            "## Notes",
        ]
        for r in self.results:
            if r.notes:
                lines.append(f"- **{r.rq} ({r.evidence}):** {r.notes}")
        return "\n".join(lines)
