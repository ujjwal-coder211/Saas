#!/usr/bin/env python3
"""Validate and ingest user conductor seed JSONL (routing + synthesis messages format)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEED_DIR = Path(__file__).resolve().parent / "data" / "seed"
EXPORT_DIR = Path(__file__).resolve().parent / "data" / "export"


def _is_routing_row(row: dict) -> bool:
    sys_msg = (row.get("messages") or [{}])[0].get("content", "").lower()
    return "routing" in sys_msg or "routing json" in sys_msg


def _is_synthesis_row(row: dict) -> bool:
    sys_msg = (row.get("messages") or [{}])[0].get("content", "").lower()
    return "synthesize" in sys_msg or "multiple expert" in sys_msg


def _validate_routing_json(content: str) -> tuple[bool, str]:
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as exc:
        return False, str(exc)
    required = {"primary_model", "complexity", "reason"}
    if not required.issubset(obj.keys()):
        return False, f"missing keys: {required - obj.keys()}"
    return True, ""


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSON: {exc}") from exc
    return rows


def validate_rows(rows: list[dict]) -> dict:
    stats = {"total": len(rows), "routing": 0, "synthesis": 0, "cot": 0, "invalid": 0, "errors": []}
    for i, row in enumerate(rows, 1):
        msgs = row.get("messages")
        if not isinstance(msgs, list) or len(msgs) < 3:
            stats["invalid"] += 1
            stats["errors"].append(f"row {i}: messages must have 3+ turns")
            continue
        assistant = msgs[-1].get("content", "")
        if _is_routing_row(row):
            ok, err = _validate_routing_json(assistant)
            if ok:
                stats["routing"] += 1
            else:
                stats["invalid"] += 1
                stats["errors"].append(f"row {i} routing: {err}")
        elif _is_synthesis_row(row):
            if len(assistant) >= 80:
                stats["synthesis"] += 1
            else:
                stats["invalid"] += 1
                stats["errors"].append(f"row {i} synthesis: answer too short")
        else:
            stats["cot"] += 1
    return stats


def ingest(*, routing_path: Path | None = None, synthesis_path: Path | None = None, combined_path: Path | None = None) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    routing_path = routing_path or SEED_DIR / "routing_data.jsonl"
    synthesis_path = synthesis_path or SEED_DIR / "synthesis_data.jsonl"
    combined_path = combined_path or SEED_DIR / "sarva_combined_train.jsonl"

    if combined_path.exists():
        rows = load_jsonl(combined_path)
        source = str(combined_path)
    else:
        rows = load_jsonl(routing_path) + load_jsonl(synthesis_path)
        source = f"{routing_path}+{synthesis_path}"

    stats = validate_rows(rows)
    out_path = EXPORT_DIR / "conductor_bootstrap_train.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "source": source,
        "output": str(out_path),
        "stats": stats,
        "ready_for_colab": stats["invalid"] == 0,
    }
    manifest_path = EXPORT_DIR / "bootstrap_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest user conductor seed JSONL")
    p.add_argument("--routing", type=Path, default=None)
    p.add_argument("--synthesis", type=Path, default=None)
    p.add_argument("--combined", type=Path, default=None)
    args = p.parse_args()
    result = ingest(routing_path=args.routing, synthesis_path=args.synthesis, combined_path=args.combined)
    print(json.dumps(result, indent=2))
    return 0 if result["stats"]["invalid"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
