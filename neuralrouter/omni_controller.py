"""
Routely Router — task planner.

Decides: work mode scope, web search, best free model routing, output strategy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from neuralrouter.router import ExpertMatch, activate_experts, manual_expert
from neuralrouter.search.web_search import SearchResult, needs_web_search
from neuralrouter.omni_brain.confidence import self_assess, threshold_for
from neuralrouter.omni_brain.loader import active_brain_summary, brain_directives_for_plan
from neuralrouter.work_modes import WorkMode, build_scope, routing_query_boost

SearchMode = Literal["auto", "on", "off"]
OutputStyle = Literal["code", "prose", "structured", "hinglish"]


@dataclass
class OmniPlan:
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
    brain_version_id: str = "omni-rules-v0"
    brain_type: str = "rules"
    confidence: float = 0.6
    self_handled: bool = False

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


def plan_turn(
    query: str,
    *,
    force_model: str | None = None,
    search_mode: SearchMode = "auto",
    work_mode: WorkMode = "auto",
    max_experts: int = 3,
) -> OmniPlan:
    """
    Omni Controller entry — call before run_chat.
    Returns routing + search + style + scope decisions.
    """
    scope = build_scope(work_mode, query)
    directives: list[str] = [
        "You are Routely by Aitotech. The user sees only Routely — never name internal model names.",
        "If web search context is provided, prefer it for time-sensitive facts.",
    ]
    directives.extend(scope.system_directives)
    brain_meta = active_brain_summary()
    directives.extend(brain_directives_for_plan())
    brain_id = brain_meta.get("version_id", "omni-rules-v0")
    brain_type = brain_meta.get("type", "rules")

    routing_query = routing_query_boost(query, scope)

    if force_model:
        experts = [manual_expert(force_model)]
        reasoning = f"forced_model={force_model}"
        collaborative = False
    else:
        experts = activate_experts(routing_query)
        reasoning = f"router picked {len(experts)} expert(s) for mode={scope.mode}"
        collaborative = scope.collaborative and len(experts) > 1

    if collaborative:
        experts = experts[:max_experts]
        directives.append("Synthesize expert perspectives into one clear Omni answer.")
    else:
        experts = experts[:1] if experts else experts

    style = _detect_output_style(query)
    if style == "hinglish":
        directives.append("Respond naturally in Hinglish unless user asks English only.")
    elif style == "code":
        directives.append("Prefer working code blocks with brief explanation.")

    # Confidence-based self-routing (paper v4 §3.3). Heuristic self-assessment:
    # high confidence + low stakes → Omni can self-handle; else delegate to a teacher.
    assess_type = "code" if style == "code" else "general"
    confidence = self_assess(query, assess_type)
    bar = threshold_for(assess_type)
    self_handled = confidence >= bar and not force_model
    reasoning += f"; confidence={confidence:.2f}/{bar:.2f} self_handled={self_handled}"

    effective_search = search_mode
    if scope.mode == "explain" and search_mode == "auto":
        effective_search = "off"

    use_search = needs_web_search(query, effective_search) and scope.allow_search
    if use_search:
        reasoning += "; web_search=on"
        directives.append("Ground answers in Aksh Search results when relevant.")

    reasoning = f"brain={brain_id}; mode={scope.mode}; " + reasoning

    return OmniPlan(
        query=query,
        experts=experts,
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
        confidence=confidence,
        self_handled=self_handled,
    )


def apply_search_context(plan: OmniPlan, result: SearchResult) -> OmniPlan:
    ctx = result.as_context_block()
    return OmniPlan(
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
    )


def build_system_prompt(plan: OmniPlan) -> str:
    parts = list(plan.system_directives)
    if plan.search_context:
        parts.append(plan.search_context)
    return "\n\n".join(parts)
