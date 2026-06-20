#!/usr/bin/env python3
"""
M3 — Package vault training files for Google Colab upload.

Creates omni_training/data/colab_export/ with train JSONL + manifest.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from omni_training.vault import RESEARCH_OUTPUT_PATH, TRAIN_OUTPUT_PATH

EXPORT_DIR = Path(__file__).resolve().parent / "data" / "colab_export"


def export_colab_bundle(*, zip_output: bool = True) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    for src in (TRAIN_OUTPUT_PATH, RESEARCH_OUTPUT_PATH):
        if src.exists():
            dest = EXPORT_DIR / src.name
            shutil.copy2(src, dest)
            copied.append(src.name)

    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": copied,
        "train_path": str(TRAIN_OUTPUT_PATH),
        "research_path": str(RESEARCH_OUTPUT_PATH),
        "colab_steps": [
            "Upload colab_export.zip to Colab",
            "Run SFT on omni_v1_train.jsonl",
            "Push adapter to HuggingFace",
            "On local: python omni_training/brain_register.py omni-vN lora_hf ...",
            "python omni_training/brain_eval.py omni-vN",
            "python omni_training/brain_promote.py omni-vN --approve",
        ],
    }
    manifest_path = EXPORT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    zip_path = EXPORT_DIR.parent / "colab_export.zip"
    if zip_output:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in EXPORT_DIR.iterdir():
                zf.write(fp, arcname=f"colab_export/{fp.name}")

    return {
        "export_dir": str(EXPORT_DIR),
        "zip": str(zip_path) if zip_output else None,
        "files": copied,
        "manifest": str(manifest_path),
    }


def main() -> int:
    result = export_colab_bundle()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
