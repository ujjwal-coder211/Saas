"""
Phase 4 — check train readiness + point to research report.
"""

from __future__ import annotations

import json

from omni_training.build_dataset import TRAIN_THRESHOLDS, build
from omni_training.research_report import build_report


def check_and_report() -> dict:
    build_result = build(threshold_check=TRAIN_THRESHOLDS["manual_review"])
    research = build_report()
    build_result["research"] = {
        "report_path": research.get("report_path"),
        "next_action": research.get("next_action"),
        "eligible_rows": research.get("eligible_rows"),
    }
    w = build_result.get("written", 0)

    if w >= TRAIN_THRESHOLDS["sft_round_2"]:
        build_result["action"] = "run_colab_omni_v2_sft"
        build_result["message"] = (
            f"{w} rows. Upload vault/omni_v1_train.jsonl + omni_v1_research.jsonl to Colab."
        )
    elif w >= TRAIN_THRESHOLDS["manual_review"]:
        build_result["action"] = "manual_review_then_train"
        build_result["message"] = f"{w} rows — review research_report.json then train."
    else:
        build_result["action"] = "collect_logs"
        build_result["message"] = research.get("next_action", "collect more logs")

    return build_result


if __name__ == "__main__":
    print(json.dumps(check_and_report(), indent=2))
