"""
tests/test_scheduler.py

Verifies the adaptive concurrency logic actually grows and shrinks the
effective worker ceiling (this exposed a real bug during review: the
original shrink implementation called a non-existent Semaphore method
and was a silent no-op).
"""

import pytest

from src.engine.scheduler import AdaptiveSemaphore


@pytest.mark.asyncio
async def test_pool_grows_on_success_streak():
    sched = AdaptiveSemaphore(start=5, minimum=1, maximum=10, scale_up_streak=3)
    assert sched.limit == 5

    for _ in range(3):
        await sched.report_success()

    assert sched.limit == 6  # grew by one after hitting the streak


@pytest.mark.asyncio
async def test_pool_shrinks_on_failure_streak():
    sched = AdaptiveSemaphore(start=5, minimum=1, maximum=10, scale_down_streak=3)
    assert sched.limit == 5

    for _ in range(3):
        await sched.report_failure()

    assert sched.limit == 4  # ceiling shrank by one immediately

    # The semaphore was initialized with 5 real permits, so acquiring 5
    # still succeeds right away — the shrink only takes effect the next
    # time a permit is *released*, which is what avoids blocking here.
    for _ in range(5):
        await sched.acquire()

    # Release all 5: one of them gets absorbed by the pending shrink
    # instead of going back into the pool, so only 4 come back.
    for _ in range(5):
        sched.release()

    import asyncio
    for _ in range(4):
        await asyncio.wait_for(sched.acquire(), timeout=0.05)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sched.acquire(), timeout=0.05)


@pytest.mark.asyncio
async def test_shrink_never_goes_below_minimum():
    sched = AdaptiveSemaphore(start=2, minimum=2, maximum=10, scale_down_streak=1)
    for _ in range(5):
        await sched.report_failure()
    assert sched.limit == 2  # never drops below `minimum`
