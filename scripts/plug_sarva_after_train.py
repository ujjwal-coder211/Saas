#!/usr/bin/env python3
"""One-shot: after HF push, register → eval checklist → optional promote.

Usage (PC, after RunPod training finished):
  python scripts/plug_sarva_after_train.py
  python scripts/plug_sarva_after_train.py --promote --approve
  python scripts/plug_sarva_after_train.py --version sarva-v2 --adapter Ujjwal211/aitotech-sarva-v2

Does NOT train. Only wires registry so SARVA_INFERENCE_URL can take over routing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from neuralrouter.env_loader import load_dotenv  # noqa: F401

from sarva_training.brain_eval import evaluate
from sarva_training.brain_registry import (
    load_registry,
    promote,
    register_version,
    update_metrics,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Plug trained Sarva into registry")
    p.add_argument("--version", default="sarva-v2")
    p.add_argument("--label", default="Sarva Conductor v2")
    p.add_argument("--adapter", default="Ujjwal211/aitotech-sarva-v2")
    p.add_argument("--base-model", default="nvidia/Nemotron-3-Nano-30B-A3B")
    p.add_argument("--inference-url", default="", help="Optional: set artifact.inference_url")
    p.add_argument("--eval-score", type=float, default=None)
    p.add_argument("--approve", action="store_true")
    p.add_argument("--promote", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    reg = load_registry()
    versions = reg.get("versions", {})

    if args.version not in versions:
        artifact = {
            "base_model": args.base_model,
            "adapter_repo": args.adapter,
            "train_platform": "runpod",
        }
        if args.inference_url:
            artifact["inference_url"] = args.inference_url
        metrics = {}
        if args.eval_score is not None:
            metrics["eval_score"] = args.eval_score
        row = register_version(
            args.version,
            label=args.label,
            brain_type="lora_hf",
            artifact=artifact,
            metrics=metrics or None,
            status="candidate",
            description="QLoRA conductor from RunPod — plug via SARVA_INFERENCE_URL",
        )
        print("Registered:", json.dumps(row, indent=2, default=str))
    else:
        print(f"Already registered: {args.version}")
        if args.eval_score is not None:
            update_metrics(args.version, {"eval_score": args.eval_score})
        if args.inference_url:
            v = versions[args.version]
            art = dict(v.get("artifact") or {})
            art["inference_url"] = args.inference_url
            # re-save via update_metrics path — patch artifact manually
            reg = load_registry()
            reg["versions"][args.version]["artifact"] = art
            from sarva_training.brain_registry import save_registry

            save_registry(reg)

    if args.approve:
        update_metrics(args.version, {"manual_approved": True})
        print("manual_approved=true")

    checklist = evaluate(args.version)
    print("Eval checklist:", json.dumps(checklist, indent=2))

    if args.promote:
        result = promote(args.version, force=args.force)
        print("Promoted:", json.dumps(result, indent=2, default=str))
    else:
        print("\nNext:")
        print(f"  1. Deploy inference: SARVA_INFERENCE_MOCK=0 python deploy/runpod/serve_sarva.py")
        print(f"  2. Set app env: SARVA_INFERENCE_URL=https://<your-endpoint>")
        print(f"  3. Promote: python scripts/plug_sarva_after_train.py --promote --approve")

    print("\nActive brain:", load_registry().get("active_version_id"))
    return 0 if checklist.get("ok") or not args.promote else (0 if args.force else 1)


if __name__ == "__main__":
    raise SystemExit(main())
