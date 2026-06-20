"""
Model behavior analyzer — research layer for Omni Training Program.

Studies HOW each model answers (capability, style, structure), not just
the user question. Output feeds curated rows + research dataset for new Omni versions.
"""

from __future__ import annotations

import re
from typing import Any

from omni_training.schema import ModelBehaviorProfile, ResponsePattern, SatisfactionSignals


def _capability_tags(query: str, response: str, model_meta: dict, expert_id: str) -> list[str]:
    tags: set[str] = set()
    q = query.lower()
    r = response.lower()

    for domain in model_meta.get("specialty_domains", []):
        tags.add(domain.lower().split("/")[0].strip())

    if any(k in q for k in ("code", "python", "react", "debug", "api")):
        tags.add("coding")
    if any(k in q for k in ("calculate", "solve", "equation", "prove", "math")):
        tags.add("reasoning")
    if re.search(r"[\u0900-\u097F]", query + response):
        tags.add("multilingual")
    if expert_id and expert_id != "general-expert":
        tags.add(expert_id.replace("-", "_"))

    style = model_meta.get("response_style", {})
    if "chain-of-thought" in style.get("typical_format", ""):
        tags.add("chain_of_thought")
    if "```" in response:
        tags.add("code_output")

    return sorted(tags)[:12]


def _verbosity(length: int) -> str:
    if length < 400:
        return "short"
    if length < 2000:
        return "medium"
    return "long"


def _registry_alignment(response: str, pattern: ResponsePattern, model_meta: dict) -> float:
    score = 0.5
    style = model_meta.get("response_style", {})
    typical = style.get("typical_format", "").lower()
    tends = style.get("tends_to", "").lower()

    if "chain-of-thought" in typical and pattern.is_chain_of_thought:
        score += 0.2
    if "code" in typical and pattern.structure == "code_block":
        score += 0.2
    if "step" in tends and pattern.is_chain_of_thought:
        score += 0.1
    if "hindi" in tends and pattern.language in ("hi", "hinglish"):
        score += 0.15
    if pattern.structure == "list" and "structured" in typical:
        score += 0.1

    return min(1.0, score)


def analyze_model_behavior(
    query: str,
    model_response: str,
    model_used: str,
    expert_id: str,
    architecture_snapshot: dict,
    response_pattern: ResponsePattern,
    collaborative: bool = False,
    all_experts_used: list[str] | None = None,
    tokens_used: int | None = None,
    latency_s: float | None = None,
) -> ModelBehaviorProfile:
    meta = architecture_snapshot or {}
    alignment = _registry_alignment(model_response, response_pattern, meta)

    answer_style = "direct"
    if response_pattern.is_chain_of_thought:
        answer_style = "chain_of_thought"
    elif response_pattern.structure == "code_block":
        answer_style = "code_centric"
    elif response_pattern.structure == "list":
        answer_style = "structured_list"

    role = "primary"
    if collaborative and all_experts_used and model_used != all_experts_used[0]:
        role = "collaborative_contributor"
    elif collaborative:
        role = "collaborative_primary"

    return ModelBehaviorProfile(
        capability_tags=_capability_tags(query, model_response, meta, expert_id),
        answer_style=answer_style,
        verbosity=_verbosity(response_pattern.length_chars),
        uses_examples=bool(re.search(r"for example|उदाहरण|e\.g\.", model_response, re.I)),
        uses_markdown_structure=bool(re.search(r"^#+\s|^\*\*", model_response, re.M)),
        registry_style_alignment=round(alignment, 3),
        expert_domain=expert_id,
        collaborative_role=role,
        tokens_used=tokens_used,
        latency_s=latency_s,
    )


def analyze_satisfaction(user_behavior: dict) -> SatisfactionSignals:
    behavior = user_behavior or {}
    implicit = 0.5

    if behavior.get("thumbs") == "up":
        implicit = 0.9
    elif behavior.get("thumbs") == "down":
        implicit = 0.1

    if behavior.get("retry"):
        implicit -= 0.25

    rt = behavior.get("response_time_s")
    if rt and rt > 25:
        implicit -= 0.1

    spent = behavior.get("time_spent_s")
    if spent and spent > 8:
        implicit += 0.1

    implicit = max(0.0, min(1.0, implicit))

    explicit = 0.5
    if behavior.get("thumbs") == "up":
        explicit = 1.0
    elif behavior.get("thumbs") == "down":
        explicit = 0.0

    combined = round(0.6 * explicit + 0.4 * implicit, 3) if behavior.get("thumbs") else round(implicit, 3)

    return SatisfactionSignals(
        thumbs=behavior.get("thumbs"),
        retry=bool(behavior.get("retry")),
        time_spent_s=spent,
        response_time_s=rt,
        implicit_score=round(implicit, 3),
        combined_score=combined,
    )


def research_notes_for_row(
    query: str,
    model_behavior: ModelBehaviorProfile,
    satisfaction: SatisfactionSignals,
    architecture_snapshot: dict,
) -> dict:
    """Human + machine readable research summary for dataset versioning."""
    meta = architecture_snapshot or {}
    return {
        "teaching_focus": (
            f"Learn {meta.get('display_name', model_behavior.expert_domain)} style: "
            f"{model_behavior.answer_style}, {model_behavior.verbosity} answers"
        ),
        "capability_vector": model_behavior.capability_tags,
        "style_alignment": model_behavior.registry_style_alignment,
        "user_satisfaction": satisfaction.combined_score,
        "train_weight": round(
            0.5 * satisfaction.combined_score
            + 0.3 * model_behavior.registry_style_alignment
            + 0.2 * (1.0 if satisfaction.thumbs == "up" else 0.5),
            3,
        ),
        "query_length": len(query),
        "architecture_family": meta.get("architecture_family"),
    }
