"""
Phase 3 — SFT dataset + Phase 3b — research dataset for Sarva v2+ training.

Research file includes model behavior vectors so new Sarva versions learn
HOW each brain answers, not only user Q&A text.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sarva_training.vault import (
    CURATED_PATH,
    RESEARCH_OUTPUT_PATH,
    TRAIN_OUTPUT_PATH,
    vault_read_all,
)

TRAIN_THRESHOLDS = {
    "manual_review": 1000,
    "sft_round_2": 10000,
}


def _behavior_system_prompt(row: dict) -> str:
    mb = row.get("model_behavior") or {}
    arch = row.get("architecture_snapshot") or {}
    tags = ", ".join(mb.get("capability_tags") or [])
    return (
        "You are Sarva. Respond using patterns learned from expert models. "
        f"Source brain: {arch.get('display_name', row.get('model_used'))}. "
        f"Style: {mb.get('answer_style', 'direct')}, verbosity: {mb.get('verbosity', 'medium')}. "
        f"Capabilities: {tags or 'general'}."
    )


def to_sft_example(row: dict) -> dict:
    arch = row.get("architecture_snapshot") or {}
    mb = row.get("model_behavior") or {}
    sat = row.get("satisfaction") or {}
    research = row.get("research_notes") or {}

    return {
        "messages": [
            {"role": "system", "content": _behavior_system_prompt(row)},
            {"role": "user", "content": row["query"]},
            {"role": "assistant", "content": row["model_response"]},
        ],
        "metadata": {
            "row_id": row.get("row_id"),
            "source_model": row.get("model_used"),
            "source_architecture": arch.get("architecture_family"),
            "expert_id": row.get("expert_id"),
            "quality_score": row.get("quality_score"),
            "model_answer_style": mb.get("answer_style"),
            "style_alignment": mb.get("registry_style_alignment"),
            "user_satisfaction": sat.get("combined_score"),
            "train_weight": research.get("train_weight"),
        },
    }


def to_research_record(row: dict) -> dict:
    """Rich record for analysis + weighted training — not minimal SFT."""
    return {
        "row_id": row.get("row_id"),
        "query": row.get("query"),
        "model_used": row.get("model_used"),
        "architecture": row.get("architecture_snapshot"),
        "model_behavior": row.get("model_behavior"),
        "satisfaction": row.get("satisfaction"),
        "research_notes": row.get("research_notes"),
        "quality_score": row.get("quality_score"),
        "sft_example": to_sft_example(row),
    }


def build(threshold_check: int | None = None) -> dict:
    rows = vault_read_all(CURATED_PATH)
    if not rows:
        return {"written": 0, "message": "No curated data — run curate.py first."}

    written = research_written = 0
    with open(TRAIN_OUTPUT_PATH, "w", encoding="utf-8") as train_out, open(
        RESEARCH_OUTPUT_PATH, "w", encoding="utf-8"
    ) as research_out:
        for row in rows:
            if not row.get("train_eligible"):
                continue
            train_out.write(json.dumps(to_sft_example(row), ensure_ascii=False) + "\n")
            research_out.write(json.dumps(to_research_record(row), ensure_ascii=False) + "\n")
            written += 1
            research_written += 1

    result = {
        "written": written,
        "research_written": research_written,
        "output_path": str(TRAIN_OUTPUT_PATH),
        "research_path": str(RESEARCH_OUTPUT_PATH),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": TRAIN_THRESHOLDS,
    }
    if threshold_check is not None:
        result["ready_to_train"] = written >= threshold_check
    result["ready_for_manual_review"] = written >= TRAIN_THRESHOLDS["manual_review"]
    result["ready_for_sft_round_2"] = written >= TRAIN_THRESHOLDS["sft_round_2"]
    return result


if __name__ == "__main__":
    print(json.dumps(build(threshold_check=1000), indent=2))
