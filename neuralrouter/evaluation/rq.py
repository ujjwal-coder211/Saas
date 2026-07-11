"""The six research-question evaluators (paper §14.1) + §14.2 auxiliary metrics.

Each returns one or more RQResult. Pure functions over the task set + fixtures so
they are deterministic and unit-testable.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from neuralrouter.evaluation import baselines
from neuralrouter.evaluation import fixtures as fx
from neuralrouter.evaluation.report import RQResult
from neuralrouter.evaluation.tasksets import complex_tasks
from neuralrouter.sarva_brain.routing_policy import decide_routing
from neuralrouter.sarva_brain.synthesis import W_CONF, W_LOGIC, W_STYLE, W_SYNTAX, choose_strategy, score_output

_DEFAULT_RQ3_HISTORY = Path(__file__).resolve().parent / "data" / "rq3_cycle_history.jsonl"


# ── RQ1 — does learned routing beat heuristic on task–model fit? ──────────────
def rq1_routing_accuracy(tasks: list[dict]) -> list[RQResult]:
    accs = baselines.all_accuracies(tasks)
    learned = accs["learned"]
    heuristic = accs["heuristic"]
    beats = learned > heuristic
    out = [
        RQResult(
            rq="RQ1",
            question="Does learned routing outperform heuristic routing on task–model fit?",
            metric_name="routing_accuracy (learned)",
            value=learned,
            target=0.75,
            comparator=">=",
            evidence="measured",
            n=len(tasks),
            notes=(
                f"baselines — oracle={accs['oracle']}, learned={learned}, "
                f"heuristic={heuristic}, always_premium={accs['always_premium']}, "
                f"random={accs['random']}. learned {'>' if beats else '≤'} heuristic."
            ),
            extra={"baselines": accs, "learned_beats_heuristic": beats},
        )
    ]
    # self-handle calibration (auxiliary): did the router self-handle when it should?
    correct = sum(1 for t in tasks if decide_routing(t["query"]).self_executable == t["expect_self"])
    out.append(
        RQResult(
            rq="RQ1b",
            question="Is self-handle vs delegate calibrated to task difficulty?",
            metric_name="self_handle_calibration",
            value=round(correct / len(tasks), 4),
            target=0.75,
            comparator=">=",
            evidence="measured",
            n=len(tasks),
            notes="share of tasks where self_executable matches the expect_self label.",
        )
    )
    return out


# ── RQ2 — does multi-model synthesis beat the best single output? ─────────────
def _merged_quality(scored) -> float:
    """Upper-estimate of a MERGE: best axis taken from across the candidates."""
    syn = max(s.syntax for s in scored)
    log = max(s.logic for s in scored)
    sty = max(s.style for s in scored)
    conf = max(s.confidence for s in scored)
    return W_SYNTAX * syn + W_LOGIC * log + W_STYLE * sty + W_CONF * conf


def rq2_synthesis_gain(fixtures: dict | None = None) -> list[RQResult]:
    fixtures = fixtures or fx.SYNTHESIS_FIXTURES
    positive = 0
    total = 0
    detail = []
    for task_id, cands in fixtures.items():
        total += 1
        scored = [score_output(m, t, c) for m, t, c in cands]
        best_single = max(s.Q for s in scored)
        decision = choose_strategy(cands)
        if decision.strategy == "MERGE":
            synth_q = _merged_quality(scored)
        elif decision.strategy == "ESCALATE":
            synth_q = best_single  # needs live premium arbiter → no measured gain
        else:  # DEFER_TO_BEST / VOTE → returns the best single
            synth_q = best_single
        gain = round(synth_q - best_single, 4)
        if gain > 0:
            positive += 1
        detail.append({"task": task_id, "strategy": decision.strategy, "gain": gain})
    rate = round(positive / total, 4) if total else 0.0
    return [
        RQResult(
            rq="RQ2",
            question="Does multi-model synthesis beat the best single-model output, and on which task classes?",
            metric_name="share_of_complex_tasks_with_positive_synthesis_gain",
            value=rate,
            target=0.60,
            comparator=">=",
            evidence="proxy",
            n=total,
            notes=(
                "real synthesis scoring (§7.2) over fixture candidate outputs; "
                "MERGE yields measurable gain, ESCALATE needs a live premium arbiter. "
                "Swap fixtures for live model outputs to promote to 'measured'."
            ),
            extra={"detail": detail},
        )
    ]


# ── RQ3 — does RLEF improve routing accuracy across cycles? ────────────────────
def rq3_rlef_improvement(history_path: str | Path | None = None) -> list[RQResult]:
    """Read a per-cycle routing-accuracy history and compute promotion deltas.

    Honest by construction: with fewer than 2 evaluated cycles there is nothing
    to measure, and the harness says so instead of inventing a trend.
    """
    cycles: list[dict] = []
    p = Path(history_path) if history_path else _DEFAULT_RQ3_HISTORY
    if p.exists():
        cycles = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    simulated = any(c.get("mode") == "dry_run" for c in cycles)
    if len(cycles) < 2:
        return [
            RQResult(
                rq="RQ3",
                question="Does RLEF improve routing accuracy across cycles?",
                metric_name="mean_per_cycle_accuracy_delta",
                value=None,
                target=0.02,  # paper §8.2: promote only if routing accuracy +2 pts
                comparator="n/a",
                evidence="requires-live",
                n=len(cycles),
                notes=(
                    f"only {len(cycles)} evaluated RLEF cycle(s) on record; need ≥2 to "
                    "measure a trend. Each promoted cycle must clear the +2pt bar (§8.2). "
                    "Run scripts/rlef_cycle.py across cycles to populate this."
                ),
            )
        ]
    deltas = [
        cycles[i]["routing_accuracy"] - cycles[i - 1]["routing_accuracy"]
        for i in range(1, len(cycles))
    ]
    mean_delta = round(sum(deltas) / len(deltas), 4)
    return [
        RQResult(
            rq="RQ3",
            question="Does RLEF improve routing accuracy across cycles?",
            metric_name="mean_per_cycle_accuracy_delta",
            value=mean_delta,
            target=0.02,
            comparator=">=",
            evidence="simulation" if simulated else "measured",
            n=len(cycles),
            notes=(
                f"per-cycle deltas: {[round(d, 4) for d in deltas]}. "
                + ("Contains dry-run (simulated) cycles — promote to 'measured' by "
                   "running live --apply cycles." if simulated else "all cycles live.")
            ),
            extra={"cycles": cycles},
        )
    ]


# ── RQ4 — does Hermes skill injection reduce latency/token cost? ──────────────
def rq4_skill_hit_rate(tasks: list[dict], store: dict | None = None) -> list[RQResult]:
    store = store or fx.SKILL_STORE
    hits = 0
    savings = []
    for t in tasks:
        key = t.get("skill_trigger")
        skill = store.get(key) if key else None
        if skill and skill["success_rate"] >= fx.SKILL_CURATOR_FLOOR:
            hits += 1
            savings.append(skill["avg_token_saving"])
    hit_rate = round(hits / len(tasks), 4) if tasks else 0.0
    avg_saving = round(sum(savings) / len(savings), 4) if savings else 0.0
    return [
        RQResult(
            rq="RQ4",
            question="Does Hermes skill injection reduce latency and token cost on recurring tasks?",
            metric_name="skill_hit_rate",
            value=hit_rate,
            target=0.40,
            comparator=">=",
            evidence="measured",
            n=len(tasks),
            notes=(
                f"share of tasks with an applicable curated skill (≥{fx.SKILL_CURATOR_FLOOR} "
                f"success). When a skill hits, planning+delegation short-circuits; projected "
                f"avg token saving on hits = {avg_saving:.0%} (simulation)."
            ),
            extra={"avg_token_saving_on_hit": avg_saving, "hits": hits},
        )
    ]


# ── RQ5 — how quickly does per-user voice correction converge? ────────────────
def rq5_voice_convergence(
    wer0: float = 0.22, floor: float = 0.05, tau: float = 120.0, target_wer: float = 0.08
) -> list[RQResult]:
    """WER(n) = floor + (wer0-floor)·e^(-n/tau). Corrections to reach target_wer."""
    if target_wer <= floor:
        n_star = None
    else:
        # solve floor + (wer0-floor) e^{-n/tau} = target  →  n = -tau ln((target-floor)/(wer0-floor))
        n_star = math.ceil(-tau * math.log((target_wer - floor) / (wer0 - floor)))
    curve = {n: round(floor + (wer0 - floor) * math.exp(-n / tau), 4) for n in (0, 50, 100, 200, 400)}
    return [
        RQResult(
            rq="RQ5",
            question="How quickly does per-user voice correction converge?",
            metric_name="corrections_to_target_WER",
            value=float(n_star) if n_star is not None else None,
            target=500.0,
            comparator="<" if n_star is not None else "n/a",
            evidence="simulation",
            n=0,
            notes=(
                f"exponential-decay model (wer0={wer0}, floor={floor}, tau={tau}); reaches "
                f"WER≤{target_wer} after ~{n_star} corrections. Projection — replace with "
                f"per-user STT fine-tune data (§9.1) to promote to 'measured'."
            ),
            extra={"wer_curve": curve},
        )
    ]


# ── RQ6 — safe-action rate: does the permission gate stop harmful actions? ────
def rq6_safe_action_rate(
    harmful=None, benign=None
) -> list[RQResult]:
    from neuralrouter.security.permissions import check_plan

    harmful = harmful or fx.HARMFUL_PROBES
    benign = benign or fx.BENIGN_PROBES

    blocked = 0
    for tool, args, untrusted in harmful:
        ap = check_plan(tool, args, allow_write=True, from_untrusted=untrusted)
        if not ap.approved:
            blocked += 1
    block_rate = round(blocked / len(harmful), 4) if harmful else 0.0

    allowed = sum(
        1
        for tool, args, untrusted in benign
        if check_plan(tool, args, allow_write=True, from_untrusted=untrusted).approved
    )
    friction = round(1 - allowed / len(benign), 4) if benign else 0.0

    return [
        RQResult(
            rq="RQ6",
            question="What is the safe-action rate: how often does the permission system prevent harmful actions, and at what cost in friction?",
            metric_name="safety_block_rate",
            value=block_rate,
            target=0.99,
            comparator=">=",
            evidence="measured",
            n=len(harmful),
            notes=(
                f"harmful probes fired through the live gate (check_plan); "
                f"benign false-block rate (friction) = {friction:.2%} over {len(benign)} benign actions."
            ),
            extra={"friction_false_block_rate": friction, "harmful_blocked": blocked},
        )
    ]


# ── §14.2 auxiliary — hallucination proxy + recovery (requires-live) ──────────
def aux_hallucination_proxy(tasks: list[dict]) -> RQResult:
    risk = [t for t in tasks if t.get("hallucination_risk")]
    if not risk:
        disciplined = 0
    else:
        disciplined = sum(
            1
            for t in risk
            if not decide_routing(t["query"]).self_executable
            and decide_routing(t["query"]).needs_grounding
        )
    proxy = round(1 - disciplined / len(risk), 4) if risk else 0.0
    return RQResult(
        rq="§14.2",
        question="Hallucination rate (proxy: grounding discipline on risk tasks)",
        metric_name="hallucination_rate_proxy",
        value=proxy,
        target=0.05,
        comparator="<",
        evidence="proxy",
        n=len(risk),
        notes=(
            "proxy = share of grounding-risk tasks the router did NOT delegate+ground. "
            "True hallucination rate needs live model outputs graded for correctness."
        ),
    )


def aux_recovery_rate(records_path: str | Path | None = None) -> RQResult:
    recs: list[dict] = []
    if records_path:
        p = Path(records_path)
        if p.exists():
            recs = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    errored = [r for r in recs if r.get("had_error")]
    if not errored:
        return RQResult(
            rq="§14.2",
            question="Recovery rate: errors self-corrected within three retries",
            metric_name="recovery_rate",
            value=None,
            target=0.70,
            comparator="n/a",
            evidence="requires-live",
            n=0,
            notes="needs execution trajectories (error→retry→success). Supply --records to measure.",
        )
    recovered = sum(1 for r in errored if r.get("recovered"))
    return RQResult(
        rq="§14.2",
        question="Recovery rate: errors self-corrected within three retries",
        metric_name="recovery_rate",
        value=round(recovered / len(errored), 4),
        target=0.70,
        comparator=">=",
        evidence="measured",
        n=len(errored),
        notes="from supplied execution records.",
    )
