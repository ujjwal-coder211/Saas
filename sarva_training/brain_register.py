#!/usr/bin/env python3
"""
After Colab training — register new Sarva brain as candidate (not active yet).

Example:
  python brain_register.py sarva-v2 lora_hf \\
    --label "Sarva v2" \\
    --adapter-repo Ujjwal211/aitotech-sarva-v2 \\
    --base-model nvidia/Nemotron-3-Nano-30B-A3B \\
    --eval-score 0.82
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neuralrouter.env_loader import load_dotenv  # noqa: F401

from sarva_training.brain_registry import register_version, update_metrics


def main() -> int:
    p = argparse.ArgumentParser(description="Register trained Sarva brain as candidate")
    p.add_argument("version_id", help="e.g. sarva-v2")
    p.add_argument("brain_type", choices=["lora_hf", "lora_local", "inference_url", "rules"])
    p.add_argument("--label", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--base-model", default="")
    p.add_argument("--adapter-repo", default="")
    p.add_argument("--adapter-path", default="")
    p.add_argument("--inference-url", default="")
    p.add_argument("--eval-score", type=float, default=None)
    args = p.parse_args()

    artifact: dict = {}
    if args.base_model:
        artifact["base_model"] = args.base_model
    if args.adapter_repo:
        artifact["adapter_repo"] = args.adapter_repo
    if args.adapter_path:
        artifact["adapter_path"] = args.adapter_path
    if args.inference_url:
        artifact["inference_url"] = args.inference_url

    metrics = {}
    if args.eval_score is not None:
        metrics["eval_score"] = args.eval_score

    row = register_version(
        args.version_id,
        label=args.label,
        brain_type=args.brain_type,
        artifact=artifact or None,
        metrics=metrics or None,
        status="candidate",
        description=args.description,
    )
    print(json.dumps({"registered": row, "next": "Review then: python brain_promote.py " + args.version_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
