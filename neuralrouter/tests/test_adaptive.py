"""§6.2 adaptive permission promotion tests."""

from __future__ import annotations

import importlib

import pytest


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("SARVA_TRUST_STORE", str(tmp_path / "trust.jsonl"))
    monkeypatch.setenv("SARVA_PROMOTE_AFTER", "3")
    monkeypatch.setenv("SARVA_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from neuralrouter.security import adaptive as a

    importlib.reload(a)
    return a


def test_promotes_after_consistent_approvals(monkeypatch, tmp_path):
    a = _fresh(monkeypatch, tmp_path)
    assert not a.is_promoted("write_file", context="proj1")
    for _ in range(3):
        a.record_approval("write_file", context="proj1", approved=True, risk="medium")
    assert a.is_promoted("write_file", context="proj1")
    assert "write_file|proj1" in a.promoted_pairs()


def test_denial_blocks_promotion(monkeypatch, tmp_path):
    a = _fresh(monkeypatch, tmp_path)
    for _ in range(3):
        a.record_approval("write_file", context="p", approved=True, risk="medium")
    a.record_approval("write_file", context="p", approved=False, risk="medium")
    assert not a.is_promoted("write_file", context="p")


def test_high_risk_never_promoted(monkeypatch, tmp_path):
    a = _fresh(monkeypatch, tmp_path)
    for _ in range(5):
        a.record_approval("browser_execute", context="p", approved=True, risk="high")
    assert not a.is_promoted("browser_execute", context="p")


def test_gate_exposes_promotion(monkeypatch, tmp_path):
    _fresh(monkeypatch, tmp_path)
    from neuralrouter.security.permissions import check_plan

    for _ in range(3):
        ap = check_plan("write_file", {"path": "x"}, allow_write=True, context="c1")
        assert ap.approved
    # after enough approvals the gate reports the pair as promoted
    ap = check_plan("write_file", {"path": "x"}, allow_write=True, context="c1")
    assert ap.audit.get("promoted") is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
