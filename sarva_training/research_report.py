"""
Aggregate research report — model behavior analytics across all curated rows.
Run after curate.py to understand which brains teach Sarva best.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from sarva_training.vault import CURATED_PATH, vault_read_all

REPORT_PATH = CURATED_PATH.parent / "research_report.json"


def build_report() -> dict:
    rows = vault_read_all(CURATED_PATH)
    if not rows:
        return {"message": "No curated rows", "models": {}}

    by_model: dict[str, list] = defaultdict(list)
    for row in rows:
        by_model[row.get("model_used", "unknown")].append(row)

    model_stats = {}
    for model_id, model_rows in by_model.items():
        eligible = [r for r in model_rows if r.get("train_eligible")]
        alignments = [
            (r.get("model_behavior") or {}).get("registry_style_alignment", 0)
            for r in model_rows
        ]
        satisfactions = [
            (r.get("satisfaction") or {}).get("combined_score", 0.5) for r in model_rows
        ]
        styles: dict[str, int] = defaultdict(int)
        for r in model_rows:
            style = (r.get("model_behavior") or {}).get("answer_style", "unknown")
            styles[style] += 1

        model_stats[model_id] = {
            "total_interactions": len(model_rows),
            "train_eligible": len(eligible),
            "avg_style_alignment": round(sum(alignments) / max(len(alignments), 1), 3),
            "avg_user_satisfaction": round(sum(satisfactions) / max(len(satisfactions), 1), 3),
            "answer_styles_observed": dict(styles),
            "recommendation": (
                "strong_teacher"
                if len(eligible) >= 10
                and sum(satisfactions) / max(len(satisfactions), 1) > 0.65
                else "collect_more_data"
            ),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_rows": len(rows),
        "eligible_rows": sum(1 for r in rows if r.get("train_eligible")),
        "models": model_stats,
        "next_action": _next_action(rows),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["report_path"] = str(REPORT_PATH)
    return report


def _next_action(rows: list) -> str:
    eligible = sum(1 for r in rows if r.get("train_eligible"))
    if eligible >= 10000:
        return "run_colab_sarva_v2_sft"
    if eligible >= 1000:
        return "manual_review_then_train"
    return f"collect_more_logs ({eligible}/1000 for review)"


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2))
