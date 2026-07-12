"""Core chat orchestration — Sarva Controller → experts → answer."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from sarva_training.model_analyzer import analyze_model_behavior
from sarva_training.rlef import build_and_log
from sarva_training.schema import ResponsePattern

from neuralrouter.model_clients import call_model
from neuralrouter.project_context import enrich_message_with_project
from neuralrouter.router import REGISTRY, confidence_for
from neuralrouter.sarva_brain.context_budget import budget_context
from neuralrouter.sarva_brain.loader import sarva_native_plan_trace
from neuralrouter.sarva_brain.refine import refine
from neuralrouter.sarva_controller import (
    SarvaPlan,
    apply_search_context,
    build_system_prompt,
    plan_turn,
)
from neuralrouter.search.web_search import aksh_search
from neuralrouter.work_modes import WorkMode, build_scope, scope_confirmation

logger = logging.getLogger(__name__)

SearchMode = Literal["auto", "on", "off"]
PUBLIC_MODEL_ID = "routely"


@dataclass
class ChatResult:
    answer: str
    brain_used: str
    all_experts_used: list[str]
    collaborative: bool
    confidence: float
    expert_id: str
    tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    response_time_s: float
    sub_model_responses: list[dict] = field(default_factory=list)
    sarva_plan: dict | None = None
    web_search_used: bool = False
    verified: bool | None = None
    verification_issues: list = field(default_factory=list)


def _behavior_summary(model_id: str, expert_id: str, content: str) -> dict:
    pattern = ResponsePattern(
        is_chain_of_thought="step 1" in content.lower() or "therefore" in content.lower(),
        language="en",
        length_chars=len(content),
        structure="code_block" if "```" in content else "prose",
    )
    arch = REGISTRY.get(model_id, {})
    mb = analyze_model_behavior(
        query="",
        model_response=content,
        model_used=model_id,
        expert_id=expert_id,
        architecture_snapshot=arch,
        response_pattern=pattern,
    )
    return {
        "model_id": model_id,
        "expert_id": expert_id,
        "answer_style": mb.answer_style,
        "registry_style_alignment": mb.registry_style_alignment,
        "capability_tags": mb.capability_tags,
    }


async def _run_with_plan(plan: SarvaPlan) -> ChatResult:
    start = time.time()
    sub_behaviors: list[dict] = []
    experts = plan.experts
    if not experts:
        from neuralrouter.router import manual_expert

        experts = [manual_expert("qwen")]
    primary = experts[0]
    conf = max(confidence_for(primary), plan.confidence)

    total_tokens = prompt_tokens = completion_tokens = None
    system_prompt = build_system_prompt(plan)
    user_message = plan.query

    if not plan.collaborative:
        result = await call_model(user_message, primary.model_id, system_prompt=system_prompt)
        final_answer = result["content"]
        total_tokens = result.get("tokens")
        prompt_tokens = result.get("prompt_tokens")
        completion_tokens = result.get("completion_tokens")
        sub_behaviors.append(_behavior_summary(primary.model_id, primary.expert_id, final_answer))
    else:
        capped = experts[:3]
        results = await asyncio.gather(
            *[
                call_model(user_message, e.model_id, system_prompt=system_prompt)
                for e in capped
            ],
            return_exceptions=True,
        )
        parts = []
        for e, r in zip(capped, results):
            if isinstance(r, dict):
                parts.append(r["content"])
                sub_behaviors.append(_behavior_summary(e.model_id, e.expert_id, r["content"]))
            else:
                logger.error("Collaborative sub-call failed: %s", r)

        if not parts:
            result = await call_model(user_message, "qwen", system_prompt=system_prompt)
            final_answer = result["content"]
            total_tokens = result.get("tokens")
        else:
            synthesis_prompt = (
                "Combine these expert answers into one clear, non-redundant response. "
                "Do not invent facts that none of the experts stated.\n\n"
                + "\n\n---\n\n".join(parts)
            )
            synthesis = await call_model(synthesis_prompt, "qwen", system_prompt=system_prompt)
            final_answer = synthesis["content"]
            total_tokens = synthesis.get("tokens")
            sub_behaviors.append(_behavior_summary("qwen", "general-expert", final_answer))

    elapsed = round(time.time() - start, 2)
    internal_experts = [e.model_id for e in experts]

    # Refinement layer (paper §4.3): verify the answer as a draft before returning.
    verification = refine(final_answer, plan.output_style, plan.query)
    if verification["issues"]:
        # Honest flag — do not silently rewrite; surface issues in plan metadata.
        logger.info("Sarva refine issues: %s", verification["issues"])

    return ChatResult(
        answer=final_answer,
        brain_used=PUBLIC_MODEL_ID,
        all_experts_used=internal_experts,
        collaborative=plan.collaborative,
        confidence=conf,
        expert_id=primary.expert_id,
        tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        response_time_s=elapsed,
        sub_model_responses=sub_behaviors,
        sarva_plan={
            "reasoning": plan.reasoning,
            "output_style": plan.output_style,
            "search_mode": plan.search_mode,
            "work_mode": plan.work_mode,
            "scope_summary": plan.scope_summary,
            "brain_version_id": plan.brain_version_id,
            "brain_type": plan.brain_type,
            "confidence": plan.confidence,
            "self_handled": plan.self_handled,
            "task_type": plan.task_type,
            "complexity": plan.complexity,
            "routing_mode": plan.routing_mode,
            "routing_policy": plan.routing_policy,
            "capability_bound": plan.capability_bound,
            "primary_model": plan.primary_model,
        },
        web_search_used=bool(plan.search_context),
        verified=verification["verified"],
        verification_issues=verification["issues"],
    )


async def run_chat(
    message: str,
    force_model: str | None = None,
    search_mode: SearchMode = "auto",
    file_context: str | None = None,
    rules: str | None = None,
    history: list[dict] | None = None,
    work_mode: WorkMode = "auto",
    user_id: str | None = None,
    project_id: str | None = None,
) -> ChatResult:
    enriched, effective_rules = enrich_message_with_project(
        message,
        user_id,
        project_id,
        rules=rules,
        include_index=True,
    )

    # Paper §11 — budget history / workspace / rules instead of unbounded concat.
    workspace_bits: list[str] = []
    if file_context:
        workspace_bits.append(f"@file context:\n{file_context.strip()}")
    elif effective_rules and not project_id:
        workspace_bits.append(f"Project rules (.akshrules):\n{effective_rules.strip()}")

    # If enrich already folded project context into enriched, treat the delta as codebase.
    codebase = ""
    user_core = message
    if enriched != message and user_id and project_id:
        # enriched = summary + index + rules + user message — keep as codebase+workspace budget
        codebase = enriched.rsplit("User message:", 1)[0].strip()
        user_core = message

    budgeted = budget_context(
        user_message=user_core,
        skills="",  # Hermes skill injection hook (filled when skill store is wired)
        codebase=codebase,
        history=history,
        workspace="\n\n".join(workspace_bits),
    )
    plan_query = budgeted.as_prompt_block()
    if budgeted.truncated:
        logger.info("Context budget truncated: %s est=%s", budgeted.truncated, budgeted.token_estimate)

    trained = await sarva_native_plan_trace(plan_query)
    plan = plan_turn(
        plan_query,
        force_model=force_model,
        search_mode=search_mode,
        work_mode=work_mode,
        trained_trace=trained,
    )

    if plan.use_web_search:
        try:
            search_result = await aksh_search(message)
            plan = apply_search_context(plan, search_result)
        except Exception:
            logger.exception("Aksh Search failed — continuing without web context")

    result = await _run_with_plan(plan)

    # RLEF: log a RoutingRecord for every turn. Best-effort.
    try:
        alignments = [
            b.get("registry_style_alignment", 0.0)
            for b in result.sub_model_responses
            if isinstance(b, dict)
        ]
        quality_alignment = sum(alignments) / len(alignments) if alignments else 0.5
        build_and_log(
            query=message,
            task_type=f"{plan.work_mode}:{plan.output_style}:{plan.task_type}",
            models=result.all_experts_used,
            collaborative=result.collaborative,
            answer=result.answer,
            quality_alignment=quality_alignment,
            latency_s=result.response_time_s,
            tokens=result.tokens,
            brain_version_id=plan.brain_version_id,
            user_id=user_id,
            exec_success=(False if result.verified is False else None),
        )
    except Exception:
        logger.debug("RLEF logging skipped", exc_info=True)

    # Work-mode banner (e.g. "[Aksh Ship] ...") removed from user-facing answers —
    # it read as noise. Mode still drives routing/rules internally.
    return result
