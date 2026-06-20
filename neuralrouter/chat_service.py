"""Core chat orchestration — Omni Controller → experts → answer."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from omni_training.model_analyzer import analyze_model_behavior
from omni_training.schema import ResponsePattern

from neuralrouter.model_clients import call_model
from neuralrouter.omni_controller import OmniPlan, apply_search_context, build_system_prompt, plan_turn
from neuralrouter.omni_brain.loader import omni_native_plan_hint
from neuralrouter.router import REGISTRY, confidence_for
from neuralrouter.search.web_search import aksh_search

logger = logging.getLogger(__name__)

SearchMode = Literal["auto", "on", "off"]


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
    omni_plan: dict | None = None
    web_search_used: bool = False


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


async def _run_with_plan(plan: OmniPlan) -> ChatResult:
    start = time.time()
    sub_behaviors: list[dict] = []
    experts = plan.experts
    primary = experts[0]
    conf = confidence_for(primary)

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
                "Combine these expert answers into one clear, non-redundant response:\n\n"
                + "\n\n---\n\n".join(parts)
            )
            synthesis = await call_model(synthesis_prompt, "qwen", system_prompt=system_prompt)
            final_answer = synthesis["content"]
            total_tokens = synthesis.get("tokens")
            sub_behaviors.append(_behavior_summary("qwen", "general-expert", final_answer))

    elapsed = round(time.time() - start, 2)

    return ChatResult(
        answer=final_answer,
        brain_used=primary.model_id,
        all_experts_used=[e.model_id for e in experts],
        collaborative=plan.collaborative,
        confidence=conf,
        expert_id=primary.expert_id,
        tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        response_time_s=elapsed,
        sub_model_responses=sub_behaviors,
        omni_plan={
            "reasoning": plan.reasoning,
            "output_style": plan.output_style,
            "search_mode": plan.search_mode,
            "brain_version_id": plan.brain_version_id,
            "brain_type": plan.brain_type,
        },
        web_search_used=bool(plan.search_context),
    )


async def run_chat(
    message: str,
    force_model: str | None = None,
    search_mode: SearchMode = "auto",
) -> ChatResult:
    plan = plan_turn(message, force_model=force_model, search_mode=search_mode)

    hint = await omni_native_plan_hint(message)
    if hint:
        plan = OmniPlan(
            query=plan.query,
            experts=plan.experts,
            use_web_search=plan.use_web_search,
            search_mode=plan.search_mode,
            output_style=plan.output_style,
            collaborative=plan.collaborative,
            system_directives=plan.system_directives + [hint],
            search_context=plan.search_context,
            reasoning=plan.reasoning + "; omni_inference_hint=on",
            brain_version_id=plan.brain_version_id,
            brain_type=plan.brain_type,
        )

    if plan.use_web_search:
        try:
            search_result = await aksh_search(message)
            plan = apply_search_context(plan, search_result)
        except Exception:
            logger.exception("Aksh Search failed — continuing without web context")

    return await _run_with_plan(plan)
