"""§9 voice + §14 eval tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_voice_event_shaping():
    from neuralrouter.voice.pipeline import transcription_to_event

    ev = transcription_to_event({"text": "open the file", "engine": "faster-whisper", "low_confidence": ["file"]}, user_id="u1")
    assert ev["modality"] == "voice" and ev["type"] == "text"
    assert ev["content"] == "open the file"
    assert ev["meta"]["low_confidence"] == ["file"]


def test_voice_corrections(tmp_path, monkeypatch):
    monkeypatch.setenv("SARVA_VOICE_CORRECTIONS", str(tmp_path / "corr.jsonl"))
    import importlib

    from neuralrouter.voice import pipeline as p

    importlib.reload(p)
    assert p.record_correction("cache", "catch", user_id="u1")
    assert not p.record_correction("same", "same")  # no-op
    assert p.correction_count("u1") == 1


def test_voice_high_risk_visual_confirm():
    from neuralrouter.voice.pipeline import requires_visual_confirmation

    assert requires_visual_confirmation("run_terminal", "voice") is True
    assert requires_visual_confirmation("read_file", "voice") is False


def test_voice_stt_degrades():
    from neuralrouter.voice.pipeline import transcribe

    r = transcribe("/nonexistent.wav")
    assert r["ok"] is False and "error" in r


def test_eval_metrics_and_targets():
    from sarva_training.evaluate import evaluate

    records = [
        {"chosen_model": "qwen", "oracle_model": "qwen", "quality": 0.9, "cost_usd": 0.001,
         "baseline_quality": 0.92, "baseline_cost_usd": 0.02, "skill_applicable": True},
        {"chosen_model": "kimi", "oracle_model": "kimi", "quality": 0.8, "cost_usd": 0.002,
         "baseline_quality": 0.85, "baseline_cost_usd": 0.02,
         "harmful_attempted": True, "harmful_blocked": True,
         "had_error": True, "recovered": True},
        {"chosen_model": "qwen", "oracle_model": "mistral", "quality": 0.6, "cost_usd": 0.001,
         "baseline_quality": 0.8, "baseline_cost_usd": 0.02},
    ]
    out = evaluate(records)
    m = out["metrics"]
    assert m["n"] == 3
    assert m["routing_accuracy"] == round(2 / 3, 4)   # 2 of 3 match oracle
    assert m["safety_block_rate"] == 1.0              # 1/1 harmful blocked
    assert m["recovery_rate"] == 1.0                  # 1/1 recovered
    assert m["cost_efficiency_reduction"] > 0.9       # far cheaper than premium
    assert out["passes"]["safety_block_rate"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
