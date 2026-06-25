#!/usr/bin/env python3
"""
Package conductor training JSONL for Google Colab upload.

Creates omni_training/data/colab_export/ with train JSONL + manifest + Colab instructions.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent / "data" / "colab_export"
DATA_EXPORT = Path(__file__).resolve().parent / "data" / "export"
BOOTSTRAP = DATA_EXPORT / "conductor_bootstrap_train.jsonl"
FULL = DATA_EXPORT / "conductor_v1_train.jsonl"


def export_colab_bundle(*, use_full: bool = True, zip_output: bool = True) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    src = FULL if use_full and FULL.exists() else BOOTSTRAP
    if not src.exists():
        return {"error": f"No dataset at {src} — run ingest/build first."}

    dest_name = "conductor_v1_train.jsonl" if use_full else "conductor_bootstrap_train.jsonl"
    dest = EXPORT_DIR / dest_name
    shutil.copy2(src, dest)

    manifest_src = DATA_EXPORT / "dataset_manifest.json"
    manifest = {}
    if manifest_src.exists():
        manifest = json.loads(manifest_src.read_text(encoding="utf-8"))

    row_count = manifest.get("total") if use_full else None
    if not use_full and BOOTSTRAP.exists():
        row_count = sum(1 for line in BOOTSTRAP.open(encoding="utf-8") if line.strip())

    colab_manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "dataset_file": dest_name,
        "row_count": row_count,
        "routing": manifest.get("routing"),
        "synthesis": manifest.get("synthesis"),
        "cot": manifest.get("cot"),
        "base_model": "nvidia/Nemotron-3-Nano-30B-A3B",
        "adapter_start": "Ujjwal211/aitotech-omni-v1",
        "adapter_push": "Ujjwal211/aitotech-omni-v2",
        "colab_steps": [
            "Upload colab_export.zip to Colab",
            "Open deploy/colab/OMNI_CONDUCTOR_TRAIN.md and run cells",
            "Train on conductor_v1_train.jsonl",
            "Push adapter to HuggingFace",
            "brain_register.py omni-v2 → brain_promote after RunPod deploy",
        ],
    }
    manifest_path = EXPORT_DIR / "colab_manifest.json"
    manifest_path.write_text(json.dumps(colab_manifest, indent=2), encoding="utf-8")

    zip_name = "colab_export_full.zip" if use_full else "colab_export_bootstrap.zip"
    zip_path = DATA_EXPORT / zip_name
    if zip_output:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in EXPORT_DIR.iterdir():
                zf.write(fp, arcname=f"colab_export/{fp.name}")

    return {
        "export_dir": str(EXPORT_DIR),
        "zip": str(zip_path) if zip_output else None,
        "source": str(src),
        "rows": row_count,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", action="store_true", help="Use 500-row bootstrap only")
    args = p.parse_args()
    result = export_colab_bundle(use_full=not args.bootstrap)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
