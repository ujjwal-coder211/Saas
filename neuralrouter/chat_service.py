"""Core chat orchestration — shared by /v1/chat and /v1/chat/completions."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from omni_training.model_analyzer import analyze_model_behavior
from omni_training.schema import ResponsePattern

from neuralrouter.model_clients import call_model
from neuralrouter.router import REGISTRY, activate_experts, confidence_for, manual_expert

logger = logging.getLogger(__name__)


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


async def run_chat(message: str, force_model: str | None = None) -> ChatResult:
    start = time.time()
    sub_behaviors: list[dict] = []

    if force_model:
        experts = [manual_expert(force_model)]
    else:
        experts = activate_experts(message)

    is_collaborative = len(experts) > 1
    primary = experts[0]
    conf = confidence_for(primary)

    total_tokens = prompt_tokens = completion_tokens = None

    if not is_collaborative:
        result = await call_model(message, primary.model_id)
        final_answer = result["content"]
        total_tokens = result.get("tokens")
        prompt_tokens = result.get("prompt_tokens")
        completion_tokens = result.get("completion_tokens")
        sub_behaviors.append(
            _behavior_summary(primary.model_id, primary.expert_id, final_answer)
        )
    else:
        capped = experts[:3]
        results = await asyncio.gather(
            *[call_model(message, e.model_id) for e in capped],
            return_exceptions=True,
        )
        parts = []
        for e, r in zip(capped, results):
            if isinstance(r, dict):
                parts.append(r["content"])
                sub_behaviors.append(
                    _behavior_summary(e.model_id, e.expert_id, r["content"])
                )
            else:
                logger.error("Collaborative sub-call failed: %s", r)

        if not parts:
            result = await call_model(message, "qwen")
            final_answer = result["content"]
            total_tokens = result.get("tokens")
        else:
            synthesis_prompt = (
                "Combine these expert answers into one clear, non-redundant response:\n\n"
                + "\n\n---\n\n".join(parts)
            )
            synthesis = await call_model(synthesis_prompt, "qwen")
            final_answer = synthesis["content"]
            total_tokens = synthesis.get("tokens")
            sub_behaviors.append(
                _behavior_summary("qwen", "general-expert", final_answer)
            )

    elapsed = round(time.time() - start, 2)

    return ChatResult(
        answer=final_answer,
        brain_used=primary.model_id,
        all_experts_used=[e.model_id for e in experts],
        collaborative=is_collaborative,
        confidence=conf,
        expert_id=primary.expert_id,
        tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        response_time_s=elapsed,
        sub_model_responses=sub_behaviors,
    )
