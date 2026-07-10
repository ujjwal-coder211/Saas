"""CLI: python -m neuralrouter.evaluation [--json] [--out DIR] [options]."""

from __future__ import annotations

import argparse
from pathlib import Path

from neuralrouter.evaluation.harness import run_all


def main() -> int:
    ap = argparse.ArgumentParser(description="Saira §14 evaluation harness")
    ap.add_argument("--tasks", help="JSONL task set (default: fixed 200-task benchmark)")
    ap.add_argument("--rlef-history", help="JSONL of {routing_accuracy} per evaluated cycle (RQ3)")
    ap.add_argument("--records", help="JSONL execution records for recovery-rate (§14.2)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    ap.add_argument("--out", help="write report to this directory (both .json and .md)")
    args = ap.parse_args()

    report = run_all(
        tasks_path=args.tasks,
        rlef_history_path=args.rlef_history,
        records_path=args.records,
    )

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "eval_report.json").write_text(report.to_json(), encoding="utf-8")
        (out / "eval_report.md").write_text(report.to_markdown(), encoding="utf-8")
        print(f"wrote {out/'eval_report.json'} and {out/'eval_report.md'}")
    else:
        print(report.to_json() if args.json else report.to_markdown())

    s = report.summary()
    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
