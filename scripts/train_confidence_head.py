"""Train Sarva's confidence head from the RLEF decision log (paper §4.3).

Usage:
    python scripts/train_confidence_head.py [--ledger PATH] [--no-save]

Fits a logistic confidence calibrator on features extracted from logged routing
outcomes and writes the artifact that confidence.self_assess picks up
automatically. Reports insufficient-data honestly rather than saving a degenerate
head.
"""

from __future__ import annotations

import argparse
import json

from neuralrouter.sarva_brain.confidence_head import train_from_ledger


def main() -> int:
    ap = argparse.ArgumentParser(description="Train the Sarva confidence head (§4.3)")
    ap.add_argument("--ledger", help="RLEF ledger JSONL (default: configured LEDGER_PATH)")
    ap.add_argument("--no-save", action="store_true", help="report metrics without writing the artifact")
    args = ap.parse_args()
    result = train_from_ledger(args.ledger, save=not args.no_save)
    print(json.dumps(result, indent=2))
    return 0 if result.get("trained") else 2


if __name__ == "__main__":
    raise SystemExit(main())
