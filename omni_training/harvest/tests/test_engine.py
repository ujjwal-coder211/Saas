"""
tests/test_engine.py

Basic unit tests. Run with: pytest tests/
"""

import asyncio
import pytest

from src.engine.circuit_breaker import CircuitBreaker, State
from src.utils.metrics import MetricsTracker


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, open_seconds=60)
    model = "test-model"

    for _ in range(3):
        assert await cb.allow_request(model) is True
        await cb.record_failure(model)

    assert await cb.allow_request(model) is False
    assert cb.snapshot()[model]["state"] == State.OPEN.value


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovers():
    cb = CircuitBreaker(failure_threshold=1, open_seconds=0.01)
    model = "test-model"

    await cb.allow_request(model)
    await cb.record_failure(model)
    assert await cb.allow_request(model) is False

    await asyncio.sleep(0.02)
    assert await cb.allow_request(model) is True  # probe allowed (HALF_OPEN)
    await cb.record_success(model)
    assert cb.snapshot()[model]["state"] == State.CLOSED.value


def test_metrics_cost_calculation():
    pricing = {"my-model": {"prompt_per_1k": 1.0, "completion_per_1k": 2.0},
               "default": {"prompt_per_1k": 0.0, "completion_per_1k": 0.0}}
    tracker = MetricsTracker(pricing=pricing)

    response = {"usage": {"prompt_tokens": 1000, "completion_tokens": 500}}
    record = tracker.compute("my-model", response)

    assert record.prompt_tokens == 1000
    assert record.completion_tokens == 500
    assert record.estimated_cost_usd == pytest.approx(1.0 + 1.0)  # 1*1.0 + 0.5*2.0

    totals = tracker.totals()
    assert totals["requests"] == 1
    assert totals["total_tokens"] == 1500
