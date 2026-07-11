"""Evaluation harness — paper §14 (RQ1–RQ6), scale build.

Extends the offline `sarva_training/evaluate.py` scoring core into a full,
runnable harness with:

  - a fixed ~200-task labeled benchmark (paper's "fixed 200-task benchmark"),
  - five routing baselines (random, oracle, heuristic, always-premium, learned),
  - one evaluator per research question (RQ1–RQ6),
  - a report renderer that checks every value against the pre-registered
    §14.2 targets and labels each metric's evidence class
    (measured / proxy / simulation / requires-live).

Nothing here fabricates a live-model number: metrics that genuinely need
running the models against real tasks are marked ``requires-live`` and read
from a records file when one is supplied, rather than being invented.
"""

from neuralrouter.evaluation.harness import run_all  # noqa: F401
from neuralrouter.evaluation.report import Report, RQResult  # noqa: F401
