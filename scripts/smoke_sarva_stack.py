#!/usr/bin/env python3
"""Local smoke — hybrid routing + security + context + optional mock inference.

  python scripts/smoke_sarva_stack.py
  python scripts/smoke_sarva_stack.py --with-mock-server   # needs free port 8001
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _check_routing() -> dict:
    from neuralrouter.sarva_controller import plan_turn
    from neuralrouter.security.permissions import check_plan

    cases = [
        "what is a list",
        "audit SQL injection vulnerability",
        "latest nvidia stock price today",
    ]
    out = []
    for q in cases:
        p = plan_turn(q)
        out.append(
            {
                "q": q,
                "mode": p.routing_mode,
                "model": p.primary_model,
                "self": p.self_handled,
                "conf": round(p.confidence, 2),
                "policy": p.routing_policy,
            }
        )
    denied = check_plan("run_terminal", {"command": "rm -rf /"}, allow_write=True)
    return {"plans": out, "destructive_blocked": not denied.approved}


def _check_rlef_dir() -> dict:
    from sarva_training.rlef import LEDGER_PATH, build_and_log

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = build_and_log(
        query="smoke test",
        task_type="ship:prose:general",
        models=["qwen"],
        collaborative=False,
        answer="ok",
        quality_alignment=0.8,
        latency_s=0.1,
        tokens=10,
        brain_version_id="sarva-rules-v0",
        user_id="smoke",
    )
    return {"ledger": str(LEDGER_PATH), "wrote": rec is not None, "exists": LEDGER_PATH.exists()}


def _check_schema() -> dict:
    from sarva_training.conductor_schema import RoutingDecision, ROUTING_SYSTEM

    d = RoutingDecision(confidence=0.9, self_executable=True)
    return {
        "has_confidence": "confidence" in d.to_dict(),
        "has_self_executable": "self_executable" in d.to_dict(),
        "system_mentions_confidence": "confidence" in ROUTING_SYSTEM,
    }


def _check_master_data() -> dict:
    p = ROOT / "sarva_training" / "data" / "export" / "sarva_master_train.jsonl"
    n = sum(1 for _ in open(p, encoding="utf-8")) if p.exists() else 0
    return {"path": str(p), "exists": p.exists(), "rows": n}


def _check_mock_inference() -> dict:
    import importlib.util

    path = ROOT / "deploy" / "runpod" / "serve_sarva.py"
    spec = importlib.util.spec_from_file_location("serve_sarva", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Force mock before load executes main — module reads MOCK at import
    import os

    os.environ["SARVA_INFERENCE_MOCK"] = "1"
    spec.loader.exec_module(mod)
    plan = mod.plan_query("what is HTTP")
    return {
        "plan_keys": sorted(plan.keys()),
        "primary": plan.get("primary_model"),
        "mock": plan.get("mock", True),
        "self_executable": plan.get("self_executable"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-mock-server", action="store_true")
    args = ap.parse_args()

    report = {
        "routing": _check_routing(),
        "rlef": _check_rlef_dir(),
        "schema": _check_schema(),
        "master_data": _check_master_data(),
    }
    if args.with_mock_server:
        report["mock_inference"] = _check_mock_inference()

    print(json.dumps(report, indent=2))
    ok = (
        report["rlef"]["wrote"]
        and report["schema"]["has_confidence"]
        and report["master_data"]["exists"]
        and report["routing"]["destructive_blocked"]
    )
    print("\nSMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
