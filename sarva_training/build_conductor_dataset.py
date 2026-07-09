#!/usr/bin/env python3
"""
Build final conductor training JSONL — bootstrap (user seed) + SARVA + HF/GitHub exports.

Outputs:
  data/export/routing_train.jsonl
  data/export/synthesis_train.jsonl
  data/export/cot_train.jsonl
  data/export/conductor_v1_train.jsonl
  data/export/dataset_manifest.json
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sarva_training.conductor_schema import ROUTING_SYSTEM, SYNTHESIS_SYSTEM
from sarva_training.ingest_post_train import load_jsonl, _is_routing_row, _is_synthesis_row

SEED_DIR = Path(__file__).resolve().parent / "data" / "seed"
EXPORT_DIR = Path(__file__).resolve().parent / "data" / "export"
SARVA_DIR = Path(__file__).resolve().parents[1].parent / "aitotech-sarva-data"

EXPERT_TO_ROUTING: dict[str, dict] = {
    "coding": {"primary_model": "qwen", "secondary_models": ["nemotron"], "parallel": True, "complexity": "medium", "reasoning_mode": "on"},
    "reasoning": {"primary_model": "nemotron", "secondary_models": [], "parallel": False, "complexity": "medium", "reasoning_mode": "on"},
    "business_ca": {"primary_model": "kimi", "secondary_models": ["mistral"], "parallel": False, "complexity": "medium", "reasoning_mode": "off"},
    "government": {"primary_model": "kimi", "secondary_models": [], "parallel": False, "complexity": "medium", "reasoning_mode": "off"},
    "education": {"primary_model": "qwen", "secondary_models": ["kimi"], "parallel": False, "complexity": "medium", "reasoning_mode": "off"},
    "indian_law": {"primary_model": "glm", "secondary_models": ["kimi"], "parallel": False, "complexity": "high", "reasoning_mode": "on"},
    "science": {"primary_model": "nemotron", "secondary_models": ["qwen"], "parallel": True, "complexity": "medium", "reasoning_mode": "on"},
    "languages": {"primary_model": "qwen", "secondary_models": [], "parallel": False, "complexity": "low", "reasoning_mode": "off"},
}


def _hash_question(text: str) -> str:
    norm = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _dedup_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        msgs = row.get("messages") or []
        user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
        h = _hash_question(user)
        if h in seen:
            continue
        seen.add(h)
        out.append(row)
    return out


def sarva_to_cot(row: dict) -> dict | None:
    thinking = row.get("thinking") or []
    answer = row.get("answer") or ""
    if not isinstance(thinking, list) or len(thinking) < 2 or len(answer) < 50:
        return None
    steps = "\n".join(f"- {t}" for t in thinking)
    content = f"{steps}\n\n{answer}"
    lang = row.get("language", "english")
    return {
        "messages": [
            {"role": "system", "content": f"You are Sarva. Respond clearly in {lang}. Show reasoning then answer."},
            {"role": "user", "content": row.get("question", "")},
            {"role": "assistant", "content": content},
        ],
        "metadata": {"source": row.get("source", "sarva"), "expert": row.get("expert"), "type": "cot"},
    }


def sarva_to_routing(row: dict) -> dict | None:
    expert = row.get("expert", "reasoning")
    plan = EXPERT_TO_ROUTING.get(expert)
    if not plan:
        return None
    question = row.get("question", "")
    payload = {**plan, "reason": f"SARVA expert={expert} mapped routing"}
    payload["reasoning_mode"] = "on" if plan.get("reasoning_mode") else "off"
    return {
        "messages": [
            {"role": "system", "content": ROUTING_SYSTEM},
            {"role": "user", "content": f"Query: {question}\n\nReturn routing JSON:"},
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "metadata": {"source": "sarva_augment", "expert": expert, "type": "routing"},
    }


def load_sarva_rows() -> list[dict]:
    paths = [
        SARVA_DIR / "output" / "sarva_v1_train.jsonl",
        SARVA_DIR / "reasoning" / "indian_reasoning_samples.jsonl",
        SARVA_DIR / "data" / "export" / "hf_normalized.jsonl",
    ]
    rows: list[dict] = []
    for path in paths:
        if path.exists():
            rows.extend(load_jsonl(path))
    return rows


def classify_and_split(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    routing, synthesis, cot = [], [], []
    for row in rows:
        if _is_routing_row(row):
            routing.append(row)
        elif _is_synthesis_row(row):
            synthesis.append(row)
        else:
            cot.append(row)
    return routing, synthesis, cot


def build(*, bootstrap_only: bool = False) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []

    bootstrap = EXPORT_DIR / "conductor_bootstrap_train.jsonl"
    if bootstrap.exists():
        all_rows.extend(load_jsonl(bootstrap))
    else:
        combined = SEED_DIR / "sarva_combined_train.jsonl"
        if combined.exists():
            all_rows.extend(load_jsonl(combined))

    sarva_count = 0
    if not bootstrap_only:
        for sarva in load_sarva_rows():
            cot = sarva_to_cot(sarva)
            route = sarva_to_routing(sarva)
            if cot:
                all_rows.append(cot)
                sarva_count += 1
            if route:
                all_rows.append(route)

        hf_export = SARVA_DIR / "data" / "export" / "hf_conductor.jsonl"
        if hf_export.exists():
            all_rows.extend(load_jsonl(hf_export))

    all_rows = _dedup_rows(all_rows)
    routing, synthesis, cot = classify_and_split(all_rows)

    paths = {
        "routing": EXPORT_DIR / "routing_train.jsonl",
        "synthesis": EXPORT_DIR / "synthesis_train.jsonl",
        "cot": EXPORT_DIR / "cot_train.jsonl",
        "combined": EXPORT_DIR / "conductor_v1_train.jsonl",
    }

    for name, subset in [("routing", routing), ("synthesis", synthesis), ("cot", cot)]:
        with paths[name].open("w", encoding="utf-8") as f:
            for row in subset:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with paths["combined"].open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_rows),
        "routing": len(routing),
        "synthesis": len(synthesis),
        "cot": len(cot),
        "sarva_augmented": sarva_count,
        "bootstrap_only": bootstrap_only,
        "files": {k: str(v) for k, v in paths.items()},
    }
    manifest_path = EXPORT_DIR / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap-only", action="store_true", help="Option A: user seed only")
    args = p.parse_args()
    print(json.dumps(build(bootstrap_only=args.bootstrap_only), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
