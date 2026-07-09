"""
Routely Router — Sarva task planner (paper §3–4).

Hybrid policy: keyword rules + confidence reasoning + capability bounds.
Self-handle routes to a cheap model only — never claims Sarva can answer everything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from neuralrouter.router import ExpertMatch
from neuralrouter.sarva_brain.loader import active_brain_summary, brain_directives_for_plan
from neuralrouter.sarva_brain.routing_policy import (
    CAPABILITY_BOUND,
    RoutingDecisionTrace,
    decide_routing,
)
from neuralrouter.search.web_search import SearchResult, needs_web_search
from neuralrouter.work_modes import WorkMode, build_scope, routing_query_boost

SearchMode = Literal["auto", "on", "off"]
OutputStyle = Literal["code", "prose", "structured", "hinglish"]


@dataclass
class SarvaPlan:
    """Single decision packet for one user turn."""

    query: str
    experts: list[ExpertMatch]
    use_web_search: bool
    search_mode: SearchMode
    output_style: OutputStyle
    collaborative: bool
    work_mode: WorkMode = "ship"
    scope_summary: str = ""
    system_directives: list[str] = field(default_factory=list)
    search_context: str = ""
    reasoning: str = ""
    brain_version_id: str = "sarva-rules-v0"
    brain_type: str = "rules"
    confidence: float = 0.6
    self_handled: bool = False
    task_type: str = "general"
    complexity: str = "medium"
    routing_mode: str = "single_delegate"
    routing_policy: str = "hybrid_rules_reasoning"
    capability_bound: str = CAPABILITY_BOUND

    @property
    def primary_model(self) -> str:
        return self.experts[0].model_id if self.experts else "qwen"


def _detect_output_style(query: str) -> OutputStyle:
    q = query.lower()
    if re.search(r"[\u0900-\u097F]", query):
        return "hinglish"
    if any(k in q for k in ("code", "python", "react", "function", "debug", "api", "sql")):
        return "code"
    if any(k in q for k in ("list", "steps", "compare", "vs", "table")):
        return "structured"
    return "prose"


def _apply_trace(
    *,
    query: str,
    trace: RoutingDecisionTrace,
    scope,
    style: OutputStyle,
    search_mode: SearchMode,
    brain_id: str,
    brain_type: str,
    directives: list[str],
) -> SarvaPlan:
    collaborative = (
        trace.routing_mode == "multi_synthesize" and len(trace.experts) > 1
    )

    effective_search = search_mode
    if scope.mode == "explain" and search_mode == "auto":
        effective_search = "off"

    use_search = needs_web_search(query, effective_search) and scope.allow_search
    if trace.needs_grounding and search_mode != "off" and scope.allow_search:
        use_search = True

    if use_search:
        directives.append("Ground answers in search results when relevant — do not invent facts.")

    reasoning = (
        f"brain={brain_id}; mode={scope.mode}; policy={trace.policy}; "
        + trace.reasoning_text()
    )
    if use_search:
        reasoning += "; web_search=on"

    return SarvaPlan(
        query=query,
        experts=trace.experts,
        use_web_search=use_search,
        search_mode=effective_search,
        output_style=style,
        collaborative=collaborative,
        work_mode=scope.mode,
        scope_summary=scope.summary,
        system_directives=directives,
        reasoning=reasoning,
        brain_version_id=brain_id,
        brain_type=brain_type,
        confidence=trace.confidence,
        self_handled=trace.self_executable,
        task_type=trace.task_type,
        complexity=trace.complexity,
        routing_mode=trace.routing_mode,
        routing_policy=trace.policy,
        capability_bound=trace.capability_bound,
    )


def plan_turn(
    query: str,
    *,
    force_model: str | None = None,
    search_mode: SearchMode = "auto",
    work_mode: WorkMode = "auto",
    max_experts: int = 3,
    historical_success: float | None = None,
    trained_trace: RoutingDecisionTrace | None = None,
) -> SarvaPlan:
    """
    Sarva Controller entry — hybrid rules + reasoning before run_chat.
    """
    scope = build_scope(work_mode, query)
    directives: list[str] = [
        "You are Routely by Aitotech. The user sees only Routely — never name internal model names.",
        "If web search context is provided, prefer it for time-sensitive facts.",
        CAPABILITY_BOUND,
    ]
    directives.extend(scope.system_directives)
    brain_meta = active_brain_summary()
    directives.extend(brain_directives_for_plan())
    brain_id = brain_meta.get("version_id", "sarva-rules-v0")
    brain_type = brain_meta.get("type", "rules")

    # Boost is ONLY for keyword expert matching — never for confidence/classify.
    expert_query = routing_query_boost(query, scope)
    style = _detect_output_style(query)
    if style == "hinglish":
        directives.append("Respond naturally in Hinglish unless user asks English only.")
    elif style == "code":
        directives.append("Prefer working code blocks with brief explanation.")

    # Blend RLEF empirical prior into confidence when caller did not pass one.
    if historical_success is None:
        try:
            from sarva_training.rlef import historical_self_success

            historical_success = historical_self_success()
        except Exception:
            historical_success = None

    if trained_trace is not None and not force_model:
        trace = trained_trace
        directives.append("Routing decision came from trained Sarva plan JSON (with capability bounds).")
    else:
        trace = decide_routing(
            query,
            output_style=style,
            force_model=force_model,
            collaborative_allowed=scope.collaborative,
            max_experts=max_experts,
            historical_success=historical_success,
            expert_query=expert_query,
        )

    if trace.self_executable:
        directives.append(
            "Self-handle path: answer carefully via the assigned inexpensive model. "
            "If unsure, say so — do not hallucinate."
        )
    elif trace.routing_mode == "multi_synthesize":
        directives.append("Synthesize expert perspectives into one clear Sarva answer.")

    return _apply_trace(
        query=query,
        trace=trace,
        scope=scope,
        style=style,
        search_mode=search_mode,
        brain_id=brain_id,
        brain_type=brain_type,
        directives=directives,
    )


def apply_search_context(plan: SarvaPlan, result: SearchResult) -> SarvaPlan:
    ctx = result.as_context_block()
    return SarvaPlan(
        query=plan.query,
        experts=plan.experts,
        use_web_search=plan.use_web_search,
        search_mode=plan.search_mode,
        output_style=plan.output_style,
        collaborative=plan.collaborative,
        work_mode=plan.work_mode,
        scope_summary=plan.scope_summary,
        system_directives=plan.system_directives,
        search_context=ctx,
        reasoning=plan.reasoning + f"; search_hits={len(result.snippets)}",
        brain_version_id=plan.brain_version_id,
        brain_type=plan.brain_type,
        confidence=plan.confidence,
        self_handled=plan.self_handled,
        task_type=plan.task_type,
        complexity=plan.complexity,
        routing_mode=plan.routing_mode,
        routing_policy=plan.routing_policy,
        capability_bound=plan.capability_bound,
    )


def build_system_prompt(plan: SarvaPlan) -> str:
    parts = list(plan.system_directives)
    if plan.search_context:
        parts.append(plan.search_context)
    return "\n\n".join(parts)
