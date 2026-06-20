# Seed omni_v1_train.jsonl from legacy aitotech-sarva-data format (optional one-time)
"""Convert old expert/question/answer JSONL into curated SFT messages format."""

from __future__ import annotations

import json
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[1].parent / "aitotech-sarva-data" / "output" / "omni_v1_train.jsonl"
OUT = Path(__file__).resolve().parents[1] / "omni_training" / "data" / "seed_manual.jsonl"

OMNI_SYSTEM = (
    "You are Omni, an assistant trained on diverse expert response patterns "
    "across reasoning, coding, research, and multilingual domains."
)


def convert_row(old: dict) -> dict:
    answer = old.get("answer", "")
    thinking = old.get("thinking", [])
    if thinking and isinstance(thinking, list):
        steps = "\n".join(f"- {t}" for t in thinking)
        content = f"{steps}\n\n{answer}" if answer else steps
    else:
        content = answer

    return {
        "messages": [
            {"role": "system", "content": OMNI_SYSTEM},
            {"role": "user", "content": old.get("question", old.get("query", ""))},
            {"role": "assistant", "content": content},
        ],
        "metadata": {
            "source": "manual_seed",
            "expert": old.get("expert"),
            "language": old.get("language"),
        },
    }


def main() -> None:
    if not LEGACY.exists():
        print(f"Legacy file not found: {LEGACY}")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(LEGACY, "r", encoding="utf-8") as src, open(OUT, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            dst.write(json.dumps(convert_row(json.loads(line)), ensure_ascii=False) + "\n")
            count += 1
    print(f"Wrote {count} seed rows to {OUT}")


if __name__ == "__main__":
    main()
