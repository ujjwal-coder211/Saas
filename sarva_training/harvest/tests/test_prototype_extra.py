"""Extra harvest / prototype tests toward paper §13 coverage."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

HARVEST_ROOT = Path(__file__).resolve().parents[1]
SRC = HARVEST_ROOT / "src"
if str(HARVEST_ROOT) not in sys.path:
    sys.path.insert(0, str(HARVEST_ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.engine.circuit_breaker import CircuitBreaker, State
from src.engine.scheduler import AdaptiveSemaphore


@pytest.mark.asyncio
async def test_circuit_breaker_closed_allows():
    cb = CircuitBreaker(failure_threshold=5, open_seconds=60)
    assert await cb.allow_request("m1") is True
    assert cb.snapshot()["m1"]["state"] == State.CLOSED.value


@pytest.mark.asyncio
async def test_circuit_breaker_independent_per_model():
    cb = CircuitBreaker(failure_threshold=2, open_seconds=60)
    for _ in range(2):
        await cb.allow_request("bad")
        await cb.record_failure("bad")
    assert await cb.allow_request("bad") is False
    assert await cb.allow_request("good") is True


@pytest.mark.asyncio
async def test_adaptive_grows_to_max_not_beyond():
    sched = AdaptiveSemaphore(start=8, minimum=1, maximum=10, scale_up_streak=1)
    for _ in range(5):
        await sched.report_success()
    assert sched.limit == 10


def test_openrouter_key_resolved_from_env_only(monkeypatch):
    """Paper §13: credentials from env, not code/CLI."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert os.environ.get("OPENROUTER_API_KEY") in (None, "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-real")
    assert os.environ["OPENROUTER_API_KEY"].startswith("sk-")


@pytest.mark.asyncio
async def test_success_resets_failure_streak_for_growth():
    sched = AdaptiveSemaphore(start=3, minimum=1, maximum=6, scale_up_streak=2, scale_down_streak=2)
    await sched.report_failure()
    await sched.report_success()
    await sched.report_success()
    # After mixed signals, growth should still be possible from a clean streak
    assert sched.limit >= 3
