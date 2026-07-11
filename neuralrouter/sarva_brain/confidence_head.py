"""Trained confidence head (paper §4.3 — "first item of future work").

The heuristic in ``confidence.py`` is a lexical proxy. This module replaces it
with an actually-*trained* calibrator: a logistic-regression head fit by gradient
descent on features extracted from the decision log (the RLEF ledger), predicting
P(Sarva self-handles this task well). Weights are fit from data, not hand-set.

Honest scope: this is a lightweight feature-based head trained in-process (no GPU,
no heavy deps), not a hidden-state head on the transformer. It is the trainable,
data-driven confidence estimator the paper asks for at this stage; a transformer
self-assessment head remains a further step. The integration point is designed so
that swapping in a stronger head changes only the artifact, not the call sites.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from neuralrouter.sarva_brain.confidence import (
    COMPLEXITY_SIGNALS,
    HIGH_STAKES_TASK_TYPES,
    SIMPLE_SIGNALS,
)

_DEFAULT_ARTIFACT = Path(__file__).resolve().parents[2] / "sarva_training" / "data" / "confidence_head.json"
ARTIFACT_PATH = Path(os.environ.get("SARVA_CONFIDENCE_HEAD", str(_DEFAULT_ARTIFACT)))

_CODE_SIGNALS = ("code", "python", "bug", "function", "api", "sql", "debug")
_REASON_SIGNALS = ("why", "how", "explain", "prove", "compare", "design", "architecture")
_GROUNDING_SIGNALS = ("latest", "today", "current price", "news", "recent", "as of 202")

FEATURE_NAMES = [
    "bias",
    "complexity_hits",
    "simple_hits",
    "long_query",
    "short_query",
    "high_stakes",
    "code_signal",
    "reason_signal",
    "grounding_signal",
]


def extract_features(query: str, task_type: str = "general") -> list[float]:
    q = (query or "").lower()
    words = len(q.split())
    return [
        1.0,  # bias term
        min(1.0, sum(1 for s in COMPLEXITY_SIGNALS if s in q) / 2.0),
        min(1.0, sum(1 for s in SIMPLE_SIGNALS if s in q) / 2.0),
        1.0 if words > 40 else 0.0,
        1.0 if words < 12 else 0.0,
        1.0 if task_type in HIGH_STAKES_TASK_TYPES else 0.0,
        1.0 if any(s in q for s in _CODE_SIGNALS) else 0.0,
        1.0 if any(s in q for s in _REASON_SIGNALS) else 0.0,
        1.0 if any(s in q for s in _GROUNDING_SIGNALS) else 0.0,
    ]


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


class ConfidenceHead:
    def __init__(self, weights: list[float] | None = None, feature_names: list[str] | None = None):
        self.feature_names = feature_names or list(FEATURE_NAMES)
        self.weights = weights or [0.0] * len(self.feature_names)

    def predict(self, query: str, task_type: str = "general") -> float:
        x = extract_features(query, task_type)
        z = sum(w * xi for w, xi in zip(self.weights, x))
        return round(_sigmoid(z), 4)

    # ── training (pure-python logistic regression) ────────────────────────────
    def fit(self, X: list[list[float]], y: list[float], *, epochs: int = 400, lr: float = 0.3, l2: float = 1e-3) -> "ConfidenceHead":
        n = len(X)
        if n == 0:
            return self
        d = len(X[0])
        self.weights = [0.0] * d
        for _ in range(epochs):
            grad = [0.0] * d
            for xi, yi in zip(X, y):
                p = _sigmoid(sum(w * v for w, v in zip(self.weights, xi)))
                err = p - yi
                for j in range(d):
                    grad[j] += err * xi[j]
            for j in range(d):
                self.weights[j] -= lr * (grad[j] / n + l2 * self.weights[j])
        return self

    def accuracy(self, X: list[list[float]], y: list[float], threshold: float = 0.5) -> float:
        if not X:
            return 0.0
        correct = 0
        for xi, yi in zip(X, y):
            p = _sigmoid(sum(w * v for w, v in zip(self.weights, xi)))
            correct += int((p >= threshold) == (yi >= 0.5))
        return round(correct / len(X), 4)

    # ── persistence ───────────────────────────────────────────────────────────
    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path or ARTIFACT_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"feature_names": self.feature_names, "weights": self.weights}, indent=2),
            encoding="utf-8",
        )
        return p

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ConfidenceHead | None":
        p = Path(path or ARTIFACT_PATH)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(weights=data["weights"], feature_names=data.get("feature_names"))
        except Exception:
            return None


def build_dataset(ledger: str | Path | None = None) -> tuple[list[list[float]], list[float]]:
    """Features + labels from the RLEF decision log.

    Label = 1 when execution succeeded (R_exec == 1.0), else 0 — i.e. the head
    learns which tasks tend to be answered well, which is exactly the self-handle
    confidence signal.
    """
    from sarva_training.rlef import LEDGER_PATH

    p = Path(ledger or LEDGER_PATH)
    X: list[list[float]] = []
    y: list[float] = []
    if not p.exists():
        return X, y
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        query = row.get("query", "")
        tt = str(row.get("task_type") or "general").split(":")[-1]
        comps = row.get("reward_components") or {}
        r_exec = comps.get("R_exec")
        if r_exec is None:
            r_exec = 1.0 if row.get("execution_result") == "ok" else 0.0
        X.append(extract_features(query, tt))
        y.append(1.0 if float(r_exec) >= 0.99 else 0.0)
    return X, y


def train_from_ledger(ledger: str | Path | None = None, *, save: bool = True) -> dict:
    """Train the head from the ledger and (optionally) save the artifact."""
    X, y = build_dataset(ledger)
    if len(X) < 10 or len(set(y)) < 2:
        return {
            "trained": False,
            "reason": f"insufficient data (n={len(X)}, classes={len(set(y))}); need ≥10 rows and both outcomes",
        }
    head = ConfidenceHead().fit(X, y)
    acc = head.accuracy(X, y)
    out = {"trained": True, "n": len(X), "train_accuracy": acc, "weights": dict(zip(FEATURE_NAMES, head.weights))}
    if save:
        out["artifact"] = str(head.save())
    return out


# module-level cache so the hot path doesn't re-read the artifact each call
_CACHED: ConfidenceHead | None = None
_CACHED_MTIME: float | None = None


def load_head(path: str | Path | None = None) -> ConfidenceHead | None:
    """Return the trained head if an artifact exists (cached on mtime)."""
    global _CACHED, _CACHED_MTIME
    p = Path(path or ARTIFACT_PATH)
    if not p.exists():
        return None
    mtime = p.stat().st_mtime
    if _CACHED is not None and _CACHED_MTIME == mtime:
        return _CACHED
    _CACHED = ConfidenceHead.load(p)
    _CACHED_MTIME = mtime
    return _CACHED


if __name__ == "__main__":
    print(json.dumps(train_from_ledger(), indent=2))
