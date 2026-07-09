"""
Phase 4 — check train readiness + point to research report.
"""

from __future__ import annotations

import json

from sarva_training.build_dataset import TRAIN_THRESHOLDS, build
from sarva_training.research_report import build_report


def _suggest_next_version() -> str:
    from sarva_training.brain_registry import load_registry

    reg = load_registry()
    nums = []
    for vid in reg.get("versions", {}):
        if vid.startswith("sarva-v") and vid[6:].isdigit():
            nums.append(int(vid[6:]))
    n = max(nums) + 1 if nums else 2
    return f"sarva-v{n}"


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
        build_result["action"] = "run_colab_sarva_sft"
        suggested_version = _suggest_next_version()
        build_result["message"] = (
            f"{w} rows. Colab train → python sarva_training/colab_export.py → "
            f"brain_register.py {suggested_version} ... "
            "→ brain_eval.py → brain_promote.py --approve"
        )
        build_result["brain_pipeline"] = {
            "step_1": "python sarva_training/colab_export.py",
            "step_2": f"Colab SFT → brain_register.py {suggested_version} lora_hf ...",
            "step_3": f"python sarva_training/brain_eval.py {suggested_version}",
            "step_4": f"python sarva_training/brain_promote.py {suggested_version} --approve",
        }
        build_result["suggested_version_id"] = suggested_version
        build_result["brain_register_command"] = (
            f"python sarva_training/brain_register.py {suggested_version} lora_hf "
            "--label \"Sarva next\" --adapter-repo YOUR/repo --eval-score 0.85"
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
