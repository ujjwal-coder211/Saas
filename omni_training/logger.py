"""
Interaction logger — captures USER signals + MODEL behavior for Omni research.
Writes to signed vault (not world-readable plain logs when HMAC key set).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from omni_training.model_analyzer import (
    analyze_model_behavior,
    analyze_satisfaction,
    research_notes_for_row,
)
from omni_training.schema import ResponsePattern, TrainingRow
from omni_training.vault import (
    FEEDBACK_PATH,
    RAW_LOG_PATH,
    vault_append,
    vault_read_all,
    vault_rewrite,
)

REGISTRY_DIR = Path(__file__).parent / "models_registry"
_registry_cache: dict = {}


def _load_architecture_snapshot(model_id: str) -> dict:
    if model_id not in _registry_cache:
        path = REGISTRY_DIR / f"{model_id}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                _registry_cache[model_id] = json.load(f)
        else:
            _registry_cache[model_id] = {}
    return _registry_cache[model_id]


def _detect_language(text: str) -> str:
    has_devanagari = bool(re.search(r"[\u0900-\u097F]", text))
    has_latin = bool(re.search(r"[a-zA-Z]", text))
    if has_devanagari and has_latin:
        return "hinglish"
    if has_devanagari:
        return "hi"
    return "en"


def _detect_structure(text: str) -> str:
    if "```" in text:
        return "code_block"
    if re.search(r"^\s*[-*\d]+[\.\)]\s", text, re.MULTILINE):
        return "list"
    return "prose"


def _looks_like_chain_of_thought(text: str) -> bool:
    markers = ["step 1", "step 2", "first,", "therefore", "इसलिए", "पहला कदम", "think"]
    lower = text.lower()
    return any(m in lower for m in markers)


def _extract_code_ast_summary(text: str) -> dict | None:
    code_blocks = re.findall(r"```(\w+)?\n(.*?)```", text, re.DOTALL)
    if not code_blocks:
        return None
    return {
        "num_code_blocks": len(code_blocks),
        "languages": list({lang or "unknown" for lang, _ in code_blocks}),
        "needs_full_ast_parse": True,
    }


def build_row(
    query: str,
    model_response: str,
    model_used: str,
    expert_id: str,
    router_confidence: float,
    collaborative: bool = False,
    all_experts_used: list[str] | None = None,
    user_behavior: dict | None = None,
    tokens_used: int | None = None,
    sub_model_responses: list[dict] | None = None,
) -> TrainingRow:
    behavior_in = user_behavior or {}
    arch = _load_architecture_snapshot(model_used)

    pattern = ResponsePattern(
        is_chain_of_thought=_looks_like_chain_of_thought(model_response),
        language=_detect_language(model_response),
        length_chars=len(model_response),
        structure=_detect_structure(model_response),
    )

    model_behavior = analyze_model_behavior(
        query=query,
        model_response=model_response,
        model_used=model_used,
        expert_id=expert_id,
        architecture_snapshot=arch,
        response_pattern=pattern,
        collaborative=collaborative,
        all_experts_used=all_experts_used,
        tokens_used=tokens_used,
        latency_s=behavior_in.get("response_time_s"),
    )

    satisfaction = analyze_satisfaction(behavior_in)
    research = research_notes_for_row(query, model_behavior, satisfaction, arch)

    if sub_model_responses:
        research["contributor_behaviors"] = [
            {
                "model": s.get("model_id"),
                "style": s.get("answer_style"),
                "alignment": s.get("registry_style_alignment"),
            }
            for s in sub_model_responses
        ]

    return TrainingRow(
        query=query,
        model_response=model_response,
        model_used=model_used,
        expert_id=expert_id,
        router_confidence=router_confidence,
        collaborative=collaborative,
        all_experts_used=all_experts_used or [model_used],
        architecture_snapshot=arch,
        response_pattern=pattern,
        model_behavior=model_behavior,
        satisfaction=satisfaction,
        user_behavior=behavior_in,
        code_ast=_extract_code_ast_summary(model_response),
        research_notes=research,
    )


def log_interaction(
    query: str,
    model_response: str,
    model_used: str,
    expert_id: str,
    router_confidence: float,
    collaborative: bool = False,
    all_experts_used: list[str] | None = None,
    user_behavior: dict | None = None,
    tokens_used: int | None = None,
    sub_model_responses: list[dict] | None = None,
    tenant_id: str | None = None,
    training_opt_in: bool = False,
) -> str:
    row = build_row(
        query,
        model_response,
        model_used,
        expert_id,
        router_confidence,
        collaborative,
        all_experts_used,
        user_behavior,
        tokens_used,
        sub_model_responses,
    )
    payload = row.to_dict()
    if tenant_id:
        payload["tenant_id"] = tenant_id
        payload["training_opt_in"] = training_opt_in
        if not training_opt_in:
            payload["query"] = "[redacted — training opt-out]"
            payload["model_response"] = "[redacted — training opt-out]"

    vault_append(RAW_LOG_PATH, payload)
    return row.row_id


def record_feedback(
    row_id: str,
    thumbs: str | None = None,
    retry: bool | None = None,
    time_spent_s: float | None = None,
) -> bool:
    patch = {"row_id": row_id}
    if thumbs is not None:
        patch["thumbs"] = thumbs
    if retry is not None:
        patch["retry"] = retry
    if time_spent_s is not None:
        patch["time_spent_s"] = time_spent_s

    vault_append(FEEDBACK_PATH, patch)
    return _apply_feedback_to_raw(row_id, patch)


def _apply_feedback_to_raw(row_id: str, patch: dict) -> bool:
    rows = vault_read_all(RAW_LOG_PATH)
    if not rows:
        return False

    found = False
    for row in rows:
        if row.get("row_id") == row_id:
            found = True
            behavior = row.get("user_behavior") or {}
            if "thumbs" in patch:
                behavior["thumbs"] = patch["thumbs"]
            if "retry" in patch:
                behavior["retry"] = patch["retry"]
            if "time_spent_s" in patch:
                behavior["time_spent_s"] = patch["time_spent_s"]
            row["user_behavior"] = behavior

            from omni_training.model_analyzer import analyze_satisfaction, research_notes_for_row
            from omni_training.schema import ModelBehaviorProfile, SatisfactionSignals

            mb_raw = row.get("model_behavior") or {}
            mb = ModelBehaviorProfile(**mb_raw) if mb_raw else None
            sat = analyze_satisfaction(behavior)
            row["satisfaction"] = sat.__dict__ if hasattr(sat, "__dict__") else sat
            if mb:
                row["research_notes"] = research_notes_for_row(
                    row.get("query", ""), mb, sat, row.get("architecture_snapshot") or {}
                )

    if found:
        vault_rewrite(RAW_LOG_PATH, rows)
    return found


def load_feedback_patches() -> dict[str, dict]:
    patches: dict[str, dict] = {}
    for p in vault_read_all(FEEDBACK_PATH):
        rid = p.get("row_id")
        if rid:
            patches.setdefault(rid, {}).update(p)
    return patches


# Re-export paths for admin / scripts
DATA_DIR = RAW_LOG_PATH.parent.parent
