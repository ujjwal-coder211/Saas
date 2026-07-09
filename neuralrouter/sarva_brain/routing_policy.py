"""Hybrid routing policy — rules + reasoning (paper §4.2–4.3).

Not rules-only. Every plan produces an explicit reasoning trace that answers:
  1. What is the task class / complexity?
  2. Can Sarva self-handle, or must it delegate?
  3. Which model(s), and why?
  4. What is Sarva's capability bound (so it does not overclaim)?

Self-handle NEVER means "Sarva invents the full answer alone without a model".
Per paper §13 honesty: self-execution routes to a designated inexpensive model.
High confidence only skips premium / multi-expert paths — it does not claim
omniscience. That keeps hallucination pressure down and prevents the conductor
from treating itself as able to answer everything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from neuralrouter.router import REGISTRY, ExpertMatch, activate_experts, manual_expert
from neuralrouter.sarva_brain.confidence import (
    HIGH_STAKES_TASK_TYPES,
    self_assess,
    threshold_for,
)

Complexity = Literal["low", "medium", "high"]
RoutingMode = Literal["self_cheap", "single_delegate", "multi_synthesize"]

# Paper §13: self-execution → designated inexpensive model (not a local Sarva yet).
CHEAP_SELF_MODEL = "qwen"

# Paper names teachers (DeepSeek, Llama, GPT, Claude...) that are not distinct
# entries in the local model registry. Map such names to the closest registry
# model so a trained Sarva plan that emits them still routes instead of being
# silently discarded (manual_expert would otherwise raise on an unknown id).
_MODEL_ALIASES = {
    "deepseek": "nemotron",
    "deepseek-r1": "nemotron",
    "deepseek-chat": "nemotron",
    "llama": "qwen",
    "llama-3": "qwen",
    "gpt-4o": "qwen",
    "gpt4o": "qwen",
    "claude": "kimi",
    "gemma": "glm",
}


def _resolve_model(model_id: str, fallback: str = CHEAP_SELF_MODEL) -> str:
    """Map any requested model id to a known registry id (never raises)."""
    if not model_id:
        return fallback
    if model_id in REGISTRY:
        return model_id
    alias = _MODEL_ALIASES.get(model_id.lower())
    if alias and alias in REGISTRY:
        return alias
    return fallback

# Capability bound — what Sarva may claim vs must refuse to overclaim.
CAPABILITY_BOUND = (
    "Sarva is a conductor, not an oracle. It routes, verifies drafts, and "
    "refines — it does not invent facts outside provided context or tool results. "
    "If uncertain, say so and prefer delegation or search over guessing."
)

REASONING_SIGNALS = [
    "why", "how does", "explain", "prove", "derive", "compare", "trade-off",
    "tradeoff", "architecture", "design", "debug", "root cause", "analyze",
    "kyun", "kaise", "samjhao", "compare karo",
]

MULTI_STEP_SIGNALS = [
    "step by step", "then", "after that", "and also", "multi", "pipeline",
    "end to end", "refactor the entire", "migrate",
]

HALLUCINATION_RISK_SIGNALS = [
    "latest", "today", "current price", "who won", "news", "release date",
    "version of", "as of 202", "recent",
]


@dataclass
class RoutingDecisionTrace:
    """Full hybrid decision — rules score + reasoning narrative."""

    task_type: str
    complexity: Complexity
    confidence: float
    threshold: float
    self_executable: bool
    routing_mode: RoutingMode
    primary_model: str
    secondary_models: list[str] = field(default_factory=list)
    experts: list[ExpertMatch] = field(default_factory=list)
    reason_steps: list[str] = field(default_factory=list)
    capability_bound: str = CAPABILITY_BOUND
    needs_grounding: bool = False  # prefer search / tools over free recall
    policy: str = "hybrid_rules_reasoning"

    def reasoning_text(self) -> str:
        return " | ".join(self.reason_steps)


def _classify_task(query: str, output_style: str) -> str:
    q = (query or "").lower()
    if any(s in q for s in ("security", "vulnerability", "cve", "audit", "injection")):
        return "security"
    if output_style == "code" or any(
        s in q for s in ("code", "python", "bug", "function", "api", "sql", "debug")
    ):
        return "code"
    if any(s in q for s in REASONING_SIGNALS):
        return "reasoning"
    if any(s in q for s in ("browser", "click", "navigate", "screenshot")):
        return "browser"
    if any(s in q for s in ("shell", "terminal", "install", "docker")):
        return "system"
    return "general"


def _complexity(query: str, task_type: str) -> Complexity:
    q = (query or "").lower()
    words = len(q.split())
    score = 0
    if task_type in HIGH_STAKES_TASK_TYPES:
        score += 2
    if any(s in q for s in MULTI_STEP_SIGNALS):
        score += 2
    if words > 80:
        score += 2
    elif words > 40:
        score += 1
    if any(s in q for s in ("architecture", "distributed", "migrate", "refactor the entire")):
        score += 2
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _needs_grounding(query: str) -> bool:
    q = (query or "").lower()
    return any(s in q for s in HALLUCINATION_RISK_SIGNALS)


def _prefer_reasoning_model(task_type: str, complexity: Complexity, query: str) -> bool:
    q = (query or "").lower()
    if task_type in ("reasoning", "security"):
        return True
    if complexity == "high":
        return True
    return any(s in q for s in REASONING_SIGNALS)


def decide_routing(
    query: str,
    *,
    output_style: str = "prose",
    force_model: str | None = None,
    collaborative_allowed: bool = False,
    max_experts: int = 3,
    historical_success: float | None = None,
    expert_query: str | None = None,
) -> RoutingDecisionTrace:
    """Hybrid policy: keyword rules + confidence reasoning + capability bound.

    ``query`` is used for classification / confidence / grounding (user intent).
    ``expert_query`` may include work-mode keyword boosts for activate_experts only —
    never feed boosts into self-assess or they inflate complexity falsely.
    """
    steps: list[str] = []
    expert_q = expert_query if expert_query is not None else query

    if force_model:
        expert = manual_expert(force_model)
        steps.append(f"rule: forced_model={force_model}")
        steps.append("reasoning: user/system override — skip self-assess")
        return RoutingDecisionTrace(
            task_type="forced",
            complexity="medium",
            confidence=1.0,
            threshold=0.0,
            self_executable=False,
            routing_mode="single_delegate",
            primary_model=force_model,
            experts=[expert],
            reason_steps=steps,
            needs_grounding=_needs_grounding(query),
        )

    task_type = _classify_task(query, output_style)
    complexity = _complexity(query, task_type)
    steps.append(f"rule: task_type={task_type} complexity={complexity}")

    confidence = self_assess(query, task_type, historical=historical_success)
    bar = threshold_for(task_type)
    steps.append(
        f"reasoning: self_assess confidence={confidence:.2f} vs threshold={bar:.2f} "
        f"(historical={'yes' if historical_success is not None else 'none'})"
    )

    grounding = _needs_grounding(query)
    if grounding:
        steps.append(
            "reasoning: hallucination risk — prefer search/tools; do not free-recall facts"
        )

    # Capability bound: never self-handle high-stakes or high-complexity alone.
    if task_type in HIGH_STAKES_TASK_TYPES and confidence < 0.9:
        self_executable = False
        steps.append(
            "reasoning: high-stakes task — refuse overclaim; must delegate "
            "(Sarva is not sure it can answer alone)"
        )
    elif complexity == "high":
        self_executable = False
        steps.append(
            "reasoning: high complexity — Sarva cannot claim full self-answer; delegate"
        )
    elif grounding and confidence < 0.85:
        self_executable = False
        steps.append(
            "reasoning: needs grounding + mid confidence — delegate + search, no guessing"
        )
    else:
        self_executable = confidence >= bar
        if self_executable:
            steps.append(
                "reasoning: confidence clears bar — self-execute via cheap model only "
                f"({CHEAP_SELF_MODEL}), not as an oracle"
            )
        else:
            steps.append(
                "reasoning: confidence below bar — Sarva does NOT understand this well "
                "enough alone; delegate to stronger teacher"
            )

    # Rules path: keyword expert activation (boosted query OK here).
    rule_experts = activate_experts(expert_q)
    steps.append(
        "rule: keyword experts="
        + ",".join(f"{e.model_id}:{e.score}" for e in rule_experts[:3])
    )

    if self_executable:
        primary = CHEAP_SELF_MODEL
        experts = [manual_expert(primary)]
        mode: RoutingMode = "self_cheap"
        secondaries: list[str] = []
        steps.append(
            f"decision: routing_mode=self_cheap primary={primary} "
            "(paper §13: inexpensive stand-in until trained Sarva exists)"
        )
    else:
        prefer_reason = _prefer_reasoning_model(task_type, complexity, query)
        # Prefer deepseek/glm for reasoning-heavy; else top keyword match.
        if prefer_reason:
            # Registry-real ids, ordered for reasoning strength (nemotron/glm lead).
            preferred_order = ["nemotron", "glm", "kimi", "qwen", "mistral"]
            steps.append("reasoning: prefer reasoning-capable teacher for this task")
        else:
            preferred_order = [e.model_id for e in rule_experts] + [
                "qwen",
                "deepseek",
                "glm",
            ]

        picked: list[ExpertMatch] = []
        seen: set[str] = set()
        # Blend: first try preferred order against rule matches, then fill.
        by_id = {e.model_id: e for e in rule_experts}
        for mid in preferred_order:
            if mid in by_id and mid not in seen:
                picked.append(by_id[mid])
                seen.add(mid)
        for e in rule_experts:
            if e.model_id not in seen:
                picked.append(e)
                seen.add(e.model_id)

        if not picked:
            picked = [manual_expert("qwen")]

        use_multi = (
            collaborative_allowed
            and complexity == "high"
            and len(picked) > 1
            and not grounding  # grounding tasks: single + search is cleaner
        )
        if use_multi:
            experts = picked[:max_experts]
            mode = "multi_synthesize"
            primary = experts[0].model_id
            secondaries = [e.model_id for e in experts[1:]]
            steps.append(
                f"decision: routing_mode=multi_synthesize primary={primary} "
                f"secondaries={secondaries}"
            )
        else:
            experts = picked[:1]
            mode = "single_delegate"
            primary = experts[0].model_id
            secondaries = []
            steps.append(f"decision: routing_mode=single_delegate primary={primary}")

    steps.append(f"capability_bound: {CAPABILITY_BOUND[:80]}...")

    return RoutingDecisionTrace(
        task_type=task_type,
        complexity=complexity,
        confidence=confidence,
        threshold=bar,
        self_executable=self_executable,
        routing_mode=mode,
        primary_model=primary,
        secondary_models=secondaries,
        experts=experts,
        reason_steps=steps,
        needs_grounding=grounding,
    )


def parse_trained_plan_json(payload: dict) -> RoutingDecisionTrace | None:
    """Apply a trained Sarva /plan JSON over the hybrid policy (when inference is live).

    Expected fields (paper + master train): primary_model, secondary_models,
    confidence, self_executable, complexity, reason.
    """
    if not isinstance(payload, dict):
        return None
    primary = payload.get("primary_model") or payload.get("primary")
    if not primary or not isinstance(primary, str):
        return None

    confidence = float(payload.get("confidence", 0.5))
    self_exec = bool(payload.get("self_executable", payload.get("self_handled", False)))
    complexity = payload.get("complexity", "medium")
    if complexity not in ("low", "medium", "high"):
        complexity = "medium"
    secondaries = payload.get("secondary_models") or []
    if not isinstance(secondaries, list):
        secondaries = []

    # Capability bound still applies: trained model cannot force self-exec on high stakes
    # without clearing a high bar.
    task_type = str(payload.get("task_type") or "general")
    if self_exec and (task_type in HIGH_STAKES_TASK_TYPES or complexity == "high"):
        if confidence < 0.9:
            self_exec = False

    # Resolve trained-model names to registry ids so an out-of-registry name
    # (e.g. the paper's "deepseek") routes instead of raising and being dropped.
    primary = _resolve_model(primary)
    resolved_secondaries: list[str] = []
    for m in secondaries:
        rid = _resolve_model(str(m))
        if rid != primary and rid not in resolved_secondaries:
            resolved_secondaries.append(rid)
    secondaries = resolved_secondaries

    if self_exec:
        primary = CHEAP_SELF_MODEL
        experts = [manual_expert(primary)]
        mode: RoutingMode = "self_cheap"
        secondaries = []
    elif secondaries:
        experts = [manual_expert(primary)] + [manual_expert(m) for m in secondaries[:2]]
        mode = "multi_synthesize"
    else:
        experts = [manual_expert(primary)]
        mode = "single_delegate"

    reason = str(payload.get("reason") or payload.get("reasoning") or "trained_plan")
    return RoutingDecisionTrace(
        task_type=task_type,
        complexity=complexity,  # type: ignore[arg-type]
        confidence=confidence,
        threshold=threshold_for(task_type),
        self_executable=self_exec,
        routing_mode=mode,
        primary_model=primary,
        secondary_models=[str(s) for s in secondaries],
        experts=experts,
        reason_steps=[
            "policy: trained_sarva_json",
            f"reasoning: {reason}",
            f"decision: mode={mode} primary={primary}",
            f"capability_bound: {CAPABILITY_BOUND[:80]}...",
        ],
        needs_grounding=False,
        policy="trained_plus_bounds",
    )
