"""
Phase 2 — CURATE with model-behavior + user-satisfaction scoring.
"""

from __future__ import annotations

import json
from pathlib import Path

from omni_training.logger import load_feedback_patches
from omni_training.vault import CURATED_PATH, RAW_LOG_PATH, vault_read_all, vault_rewrite

MIN_RESPONSE_CHARS = 20
MAX_RESPONSE_CHARS = 20000


def score_row(row: dict) -> float:
    response = row.get("model_response", "")
    if len(response) < MIN_RESPONSE_CHARS:
        return 0.0

    score = 0.35

    sat = row.get("satisfaction") or {}
    combined = sat.get("combined_score")
    if combined is not None:
        score += 0.35 * float(combined)
    else:
        behavior = row.get("user_behavior", {}) or {}
        if behavior.get("thumbs") == "up":
            score += 0.35
        elif behavior.get("thumbs") == "down":
            score -= 0.4
        if behavior.get("retry"):
            score -= 0.15

    mb = row.get("model_behavior") or {}
    alignment = mb.get("registry_style_alignment", 0)
    score += 0.2 * float(alignment)

    research = row.get("research_notes") or {}
    train_weight = research.get("train_weight")
    if train_weight is not None:
        score = 0.5 * score + 0.5 * float(train_weight)

    if len(response) > MAX_RESPONSE_CHARS:
        score -= 0.15

    if row.get("router_confidence", 0) >= 0.7:
        score += 0.05

    return max(0.0, min(1.0, round(score, 4)))


def deduplicate(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for row in rows:
        key = row.get("query", "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _merge_feedback(rows: list[dict]) -> list[dict]:
    patches = load_feedback_patches()
    for row in rows:
        rid = row.get("row_id")
        if rid and rid in patches:
            behavior = row.get("user_behavior") or {}
            patch = patches[rid]
            for k in ("thumbs", "retry", "time_spent_s"):
                if k in patch:
                    behavior[k] = patch[k]
            row["user_behavior"] = behavior
    return rows


def curate(quality_threshold: float = 0.62) -> dict:
    rows = vault_read_all(RAW_LOG_PATH)
    if not rows:
        return {"total": 0, "eligible": 0, "message": "No raw log yet."}

    rows = _merge_feedback(rows)
    rows = deduplicate(rows)

    eligible_count = 0
    for row in rows:
        row["quality_score"] = score_row(row)
        row["train_eligible"] = row["quality_score"] >= quality_threshold
        if row["train_eligible"]:
            eligible_count += 1

    vault_rewrite(CURATED_PATH, rows)

    by_model: dict[str, int] = {}
    for row in rows:
        if row.get("train_eligible"):
            m = row.get("model_used", "unknown")
            by_model[m] = by_model.get(m, 0) + 1

    return {
        "total": len(rows),
        "eligible": eligible_count,
        "output": str(CURATED_PATH),
        "eligible_by_model": by_model,
    }


if __name__ == "__main__":
    result = curate()
    print(json.dumps(result, indent=2))
