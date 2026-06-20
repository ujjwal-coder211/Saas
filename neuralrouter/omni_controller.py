"""
Omni Controller — Aksh main brain.

Decides: web search, expert routing, output strategy, tool/skill hints.
Phase A: heuristics + registry. Phase C+: fine-tuned Omni LoRA as controller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from neuralrouter.router import ExpertMatch, activate_experts, manual_expert
from neuralrouter.search.web_search import SearchResult, needs_web_search

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
    system_directives: list[str] = field(default_factory=list)
    search_context: str = ""
    reasoning: str = ""

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
    max_experts: int = 3,
) -> OmniPlan:
    """
    Omni Controller entry — call before run_chat.
    Returns routing + search + style decisions.
    """
    directives: list[str] = [
        "You are Aksh by Aitotech. Be accurate, concise, and helpful.",
        "If web search context is provided, prefer it for time-sensitive facts.",
    ]

    if force_model:
        experts = [manual_expert(force_model)]
        reasoning = f"forced_model={force_model}"
    else:
        experts = activate_experts(query)
        reasoning = f"router picked {len(experts)} expert(s)"

    collaborative = len(experts) > 1
    if collaborative:
        experts = experts[:max_experts]
        directives.append("Synthesize expert perspectives without redundancy.")

    style = _detect_output_style(query)
    if style == "hinglish":
        directives.append("Respond naturally in Hinglish unless user asks English only.")
    elif style == "code":
        directives.append("Prefer working code blocks with brief explanation.")

    use_search = needs_web_search(query, search_mode)
    if use_search:
        reasoning += "; web_search=on"
        directives.append("Ground answers in Aksh Search results when relevant.")

    return OmniPlan(
        query=query,
        experts=experts,
        use_web_search=use_search,
        search_mode=search_mode,
        output_style=style,
        collaborative=collaborative,
        system_directives=directives,
        reasoning=reasoning,
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
        system_directives=plan.system_directives,
        search_context=ctx,
        reasoning=plan.reasoning + f"; search_hits={len(result.snippets)}",
    )


def build_system_prompt(plan: OmniPlan) -> str:
    parts = list(plan.system_directives)
    if plan.search_context:
        parts.append(plan.search_context)
    return "\n\n".join(parts)
