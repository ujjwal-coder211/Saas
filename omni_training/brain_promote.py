#!/usr/bin/env python3
"""
Promote trained Omni brain → active main brain (hot replace).

Example:
  python brain_promote.py omni-v2
  python brain_promote.py omni-v2 --approve   # sets manual_approved=true then promotes
  python brain_promote.py omni-v2 --force     # skip score check (emergency)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neuralrouter.env_loader import load_dotenv  # noqa: F401

from omni_training.brain_registry import promote, update_metrics


def main() -> int:
    p = argparse.ArgumentParser(description="Promote Omni candidate brain to active")
    p.add_argument("version_id")
    p.add_argument("--approve", action="store_true", help="Mark manual_approved before promote")
    p.add_argument("--force", action="store_true", help="Skip eval score gate")
    args = p.parse_args()

    if args.approve:
        update_metrics(args.version_id, {"manual_approved": True})

    result = promote(args.version_id, force=args.force)
    print(json.dumps(result, indent=2, default=str))
    print("\nActive brain replaced. Next API requests use:", result["promoted"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
