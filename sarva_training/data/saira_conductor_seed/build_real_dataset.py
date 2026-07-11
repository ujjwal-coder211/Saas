#!/usr/bin/env python3
"""
build_real_dataset.py — assemble a REAL (non-template) conductor training set.

Wires the convert_public.py Stage-1 mapper to accessible public §10.1 corpora and
merges the result with the structural seed (Stage 2/3/4 + seed Stage-1 refactoring/
architecture, for which no clean public source is bundled). Output is one JSONL in
the same conductor schema the seed uses, ready for train_sarva.py via DATA_PATH.

Real §10.1 sources used (public, no gating):
    code_generation  <- ise-uiuc/Magicoder-OSS-Instruct-75K   (problem/solution)
    debugging        <- princeton-nlp/SWE-bench_Lite          (problem_statement/patch)
    code_review      <- m-a-p/CodeFeedback-Filtered-Instruction (query/answer)

Each source is wrapped in try/except: if a dataset is unavailable in the current
environment the source is skipped (logged), so the build degrades gracefully rather
than failing. Run with --limit small first to smoke-test, then full.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import convert_public as C  # noqa: E402  (real mappers)

SEED_DIR = _HERE


def _load(name: str, **kw):
    from datasets import load_dataset

    return load_dataset(name, **kw)


def gen_code_generation(limit: int) -> list[dict]:
    """Magicoder-OSS-Instruct → code_generation (self-handled local execution)."""
    out = []
    try:
        ds = _load("ise-uiuc/Magicoder-OSS-Instruct-75K", split="train", streaming=True)
        for i, ex in enumerate(ds):
            if i >= limit:
                break
            prob = (ex.get("problem") or "").strip()
            sol = (ex.get("solution") or "").strip()
            if prob and sol:
                out.append(C.code_task_to_record(prob, sol, "code_generation", gate="execute_local"))
    except Exception as e:
        print(f"[skip] code_generation/Magicoder: {type(e).__name__}: {str(e)[:120]}")
    print(f"  code_generation: {len(out)}")
    return out


def gen_debugging(limit: int) -> list[dict]:
    """SWE-bench_Lite → debugging (delegated then refined — these are hard)."""
    out = []
    for split in ("test", "dev", "train"):
        try:
            ds = _load("princeton-nlp/SWE-bench_Lite", split=split)
            for i, ex in enumerate(ds):
                if i >= limit:
                    break
                prob = (ex.get("problem_statement") or "").strip()
                patch = (ex.get("patch") or "").strip()
                if prob and patch:
                    prompt = f"Fix this issue:\n{prob[:2000]}"
                    sol = f"```diff\n{patch[:3000]}\n```"
                    out.append(C.code_task_to_record(prompt, sol, "debugging",
                                                     gate="delegate", teacher="deepseek-v3"))
            break  # first available split wins
        except Exception as e:
            print(f"[skip] debugging/SWE-bench({split}): {type(e).__name__}: {str(e)[:100]}")
    print(f"  debugging: {len(out)}")
    return out


def gen_code_review(limit: int) -> list[dict]:
    """CodeFeedback → code_review (delegated then refined)."""
    out = []
    try:
        ds = _load("m-a-p/CodeFeedback-Filtered-Instruction", split="train", streaming=True)
        for i, ex in enumerate(ds):
            if i >= limit:
                break
            q = (ex.get("query") or "").strip()
            a = (ex.get("answer") or "").strip()
            if q and a:
                out.append(C.code_task_to_record(q[:2000], a[:3000], "code_review",
                                                 gate="delegate", teacher="qwen2.5-coder-32b"))
    except Exception as e:
        print(f"[skip] code_review/CodeFeedback: {type(e).__name__}: {str(e)[:120]}")
    print(f"  code_review: {len(out)}")
    return out


def load_seed_subset(keep_stage1_categories={"refactoring", "architecture"}) -> list[dict]:
    """Keep the structural seed rows we are NOT replacing with real corpora:
    all of Stage 2/3/4 + the Stage-1 categories with no clean public source."""
    files = {
        1: "stage1_coding.seed.jsonl",
        2: "stage2_tooluse.seed.jsonl",
        3: "stage3_routing.seed.jsonl",
        4: "stage4_rlef.seed.jsonl",
    }
    out = []
    for stage, fn in files.items():
        p = os.path.join(SEED_DIR, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if stage == 1 and r.get("category") not in keep_stage1_categories:
                continue  # drop seed code_gen/debug/review — replaced by real corpora
            out.append(r)
    print(f"  seed kept (stage2-4 + stage1 refactor/arch): {len(out)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1500, help="max rows per real source")
    ap.add_argument("--out", default=os.path.join(SEED_DIR, "..", "export", "saira_conductor_real_v1_train.jsonl"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"Building real-corpora dataset (limit={args.limit}/source)...")
    rows: list[dict] = []
    rows += gen_code_generation(args.limit)
    rows += gen_debugging(args.limit)
    rows += gen_code_review(args.limit)
    real_n = len(rows)
    rows += load_seed_subset()

    random.Random(args.seed).shuffle(rows)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nTOTAL {len(rows)} rows ({real_n} real + {len(rows)-real_n} seed) -> {out}")
    # composition
    comp: dict = {}
    for r in rows:
        comp[r.get("category")] = comp.get(r.get("category"), 0) + 1
    print("composition:", json.dumps(comp, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
