#!/usr/bin/env python3
"""Validate Sarva JSONL: line-level JSON, required fields, and that every
JSON-bearing <sarva:*> block parses. Usage: python validate.py out/*.jsonl"""
import sys, json, re, glob

TAG = re.compile(r"<sarva:(\w+)>(.*?)</sarva:\1>", re.DOTALL)
JSON_TAGS = {"assess", "classify", "route", "synthesis", "reward"}
REQUIRED = {"id", "schema", "stage", "category", "messages"}

def validate(path):
    n, bad = 0, 0
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            n += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  ! {path}:{ln} invalid JSON: {e}"); bad += 1; continue
            missing = REQUIRED - rec.keys()
            if missing:
                print(f"  ! {path}:{ln} missing {missing}"); bad += 1; continue
            asst = next((m["content"] for m in rec["messages"] if m["role"] == "assistant"), "")
            for tag, body in TAG.findall(asst):
                if tag in JSON_TAGS:
                    try:
                        json.loads(body)
                    except json.JSONDecodeError as e:
                        print(f"  ! {path}:{ln} <sarva:{tag}> not JSON: {e}"); bad += 1
            # ordering invariant: assess before classify before route
            order = [t for t, _ in TAG.findall(asst)]
            idx = {t: order.index(t) for t in ("assess", "classify") if t in order}
            if {"assess", "classify"} <= idx.keys() and idx["assess"] > idx["classify"]:
                print(f"  ! {path}:{ln} assess must precede classify"); bad += 1
    print(f"  {path}: {n} rows, {bad} problems")
    return bad

if __name__ == "__main__":
    paths = []
    for a in sys.argv[1:]:
        paths += glob.glob(a)
    total = sum(validate(p) for p in paths)
    print("OK" if total == 0 else f"{total} problems")
    sys.exit(1 if total else 0)
