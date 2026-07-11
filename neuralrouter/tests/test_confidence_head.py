"""Trained confidence-head tests (paper §4.3)."""

from __future__ import annotations

import json

import pytest

from neuralrouter.sarva_brain import confidence, confidence_head as ch


def test_feature_vector_shape():
    x = ch.extract_features("design a distributed system", "architecture")
    assert len(x) == len(ch.FEATURE_NAMES)
    assert x[0] == 1.0  # bias


def test_fit_learns_separable_signal(tmp_path):
    # simple → high confidence label; complex/high-stakes → low
    simple = [ch.extract_features("what is a list", "general") for _ in range(20)]
    hard = [ch.extract_features("audit this security architecture design", "security") for _ in range(20)]
    X = simple + hard
    y = [1.0] * 20 + [0.0] * 20
    head = ch.ConfidenceHead().fit(X, y)
    assert head.accuracy(X, y) >= 0.9
    # predictions ordered correctly
    assert head.predict("what is a list", "general") > head.predict(
        "audit this security architecture design", "security"
    )


def test_save_load_roundtrip(tmp_path):
    head = ch.ConfidenceHead(weights=[0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    p = tmp_path / "head.json"
    head.save(p)
    loaded = ch.ConfidenceHead.load(p)
    assert loaded is not None and loaded.weights == head.weights


def test_train_from_ledger(tmp_path):
    ledger = tmp_path / "led.jsonl"
    rows = []
    for i in range(30):
        good = i % 2 == 0
        rows.append({
            "query": "what is x" if good else "audit the security architecture of the distributed system",
            "task_type": "general" if good else "security",
            "reward_components": {"R_exec": 1.0 if good else 0.0},
        })
    ledger.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = ch.train_from_ledger(ledger, save=False)
    assert res["trained"] is True
    assert res["n"] == 30
    assert res["train_accuracy"] >= 0.9


def test_train_from_ledger_insufficient_data(tmp_path):
    ledger = tmp_path / "led.jsonl"
    ledger.write_text(json.dumps({"query": "hi", "reward_components": {"R_exec": 1.0}}), encoding="utf-8")
    res = ch.train_from_ledger(ledger, save=False)
    assert res["trained"] is False


def test_self_assess_prefers_trained_head(tmp_path, monkeypatch):
    # Train + save a head to a temp artifact, point the loader at it.
    X = [ch.extract_features("what is a list", "general")] * 10 + [
        ch.extract_features("audit security architecture", "security")
    ] * 10
    y = [1.0] * 10 + [0.0] * 10
    head = ch.ConfidenceHead().fit(X, y)
    art = tmp_path / "head.json"
    head.save(art)

    monkeypatch.setattr(ch, "ARTIFACT_PATH", art)
    monkeypatch.setattr(ch, "_CACHED", None)
    monkeypatch.setattr(ch, "_CACHED_MTIME", None)

    trained_conf = confidence.self_assess("what is a list", "general")
    heuristic_conf = confidence.self_assess("what is a list", "general", use_trained_head=False)
    # trained head is consulted (value differs from pure heuristic path)
    assert 0.0 <= trained_conf <= 1.0
    assert trained_conf != heuristic_conf


def test_self_assess_falls_back_without_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "ARTIFACT_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(ch, "_CACHED", None)
    monkeypatch.setattr(ch, "_CACHED_MTIME", None)
    # no artifact → heuristic path, still a valid confidence
    val = confidence.self_assess("what is a list", "general")
    assert 0.0 <= val <= 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
