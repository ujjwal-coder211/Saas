#!/usr/bin/env python3
"""
M1 — Pre-promote checklist for Sarva brain candidates.

Run before brain_promote.py to verify registry, metrics, and artifact fields.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neuralrouter.env_loader import load_dotenv  # noqa: F401

from sarva_training.brain_registry import get_active_brain, list_versions, load_registry


def evaluate(version_id: str | None = None) -> dict:
    reg = load_registry()
    active_id = reg.get("active_version_id")
    target_id = version_id or _pick_candidate(reg)
    if not target_id:
        return {"ok": False, "error": "No candidate version to evaluate"}

    versions = reg.get("versions", {})
    if target_id not in versions:
        return {"ok": False, "error": f"Unknown version: {target_id}"}

    candidate = versions[target_id]
    min_score = float(os.environ.get("SARVA_BRAIN_MIN_EVAL_SCORE", "0.75"))
    metrics = candidate.get("metrics") or {}
    score = metrics.get("eval_score")
    approved = metrics.get("manual_approved") is True
    artifact = candidate.get("artifact") or {}
    btype = candidate.get("type", "rules")

    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("status_is_candidate", candidate.get("status") == "candidate", f"status={candidate.get('status')}")
    add("not_already_active", target_id != active_id, f"active={active_id}")
    add(
        "metrics_or_approval",
        approved or (score is not None and float(score) >= min_score),
        f"eval_score={score} min={min_score} manual_approved={approved}",
    )

    if btype == "lora_hf":
        add("adapter_repo_set", bool(artifact.get("adapter_repo")), str(artifact.get("adapter_repo")))
        add("base_model_set", bool(artifact.get("base_model")), str(artifact.get("base_model")))
    elif btype == "lora_local":
        add("adapter_path_set", bool(artifact.get("adapter_path")), str(artifact.get("adapter_path")))
    elif btype == "inference_url":
        add("inference_url_set", bool(artifact.get("inference_url")), str(artifact.get("inference_url")))

    passed = all(c["passed"] for c in checks)
    return {
        "ok": passed,
        "version_id": target_id,
        "active_version_id": active_id,
        "candidate": {
            "label": candidate.get("label"),
            "type": btype,
            "status": candidate.get("status"),
            "metrics": metrics,
        },
        "checks": checks,
        "promote_command": f"python sarva_training/brain_promote.py {target_id} --approve",
    }


def _pick_candidate(reg: dict) -> str | None:
    for row in list_versions("candidate"):
        return row["id"]
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Sarva brain pre-promote checklist")
    p.add_argument("version_id", nargs="?", help="Candidate version (default: first candidate)")
    args = p.parse_args()

    try:
        active = get_active_brain()
        print(f"Active brain: {active.get('id')} ({active.get('label')})")
    except Exception as exc:
        print(f"Active brain read warning: {exc}")

    result = evaluate(args.version_id)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
