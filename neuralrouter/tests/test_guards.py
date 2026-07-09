"""§12 failure-mode guard tests."""

from __future__ import annotations

import pytest

from neuralrouter.sarva_brain.guards import RunGuard, routing_below_floor


def test_step_limit():
    g = RunGuard(max_steps=2)
    assert g.before_action("read_file", {"p": 1}).ok
    g.after_action("read_file", {"p": 1})
    assert g.before_action("read_file", {"p": 2}).ok
    g.after_action("read_file", {"p": 2})
    d = g.before_action("read_file", {"p": 3})
    assert not d.ok and "step_limit" in d.reason


def test_budget_ceiling():
    g = RunGuard(budget_usd=0.05, max_steps=100)
    g.after_action("call", {"m": 1}, cost=0.04)
    d = g.before_action("call", {"m": 2}, est_cost=0.03)
    assert not d.ok and "budget_ceiling" in d.reason


def test_loop_detection():
    g = RunGuard(loop_threshold=3, max_steps=100)
    for _ in range(2):
        assert g.before_action("write_file", {"path": "a"}).ok
        g.after_action("write_file", {"path": "a"})
    # third identical call trips the loop guard
    d = g.before_action("write_file", {"path": "a"})
    assert not d.ok and "loop_detected" in d.reason


def test_kill_switch():
    g = RunGuard()
    g.kill("user_stop")
    d = g.before_action("read_file", {})
    assert not d.ok and d.aborted and d.reason == "user_stop"


def test_routing_floor():
    assert routing_below_floor(0.2) is True
    assert routing_below_floor(0.9) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
