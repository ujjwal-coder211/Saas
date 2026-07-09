"""
src/engine/scheduler.py

Adaptive concurrency control. Wraps an asyncio.Semaphore-like gate whose
permit count grows on sustained success and shrinks on sustained failure,
bounded by [min_workers, max_workers].

This avoids two failure modes of a fixed worker pool:
  - too many workers -> hammer a rate-limited API into constant 429s
  - too few workers   -> leave throughput on the table
"""

import asyncio


class AdaptiveSemaphore:
    def __init__(self, start: int, minimum: int, maximum: int,
                 scale_up_streak: int = 20, scale_down_streak: int = 5):
        self._min = max(1, minimum)
        self._max = max(self._min, maximum)
        self._current = min(max(start, self._min), self._max)

        self._sem = asyncio.Semaphore(self._current)
        self._lock = asyncio.Lock()

        self._success_streak = 0
        self._failure_streak = 0
        self._scale_up_streak = scale_up_streak
        self._scale_down_streak = scale_down_streak
        self._pending_shrink = 0  # permits to withhold on next release() calls

    async def acquire(self):
        await self._sem.acquire()

    def release(self):
        if self._pending_shrink > 0:
            # Absorb a scheduled shrink instead of returning this permit,
            # so total outstanding capacity actually decreases by one.
            self._pending_shrink -= 1
            return
        self._sem.release()

    @property
    def limit(self) -> int:
        return self._current

    async def report_success(self):
        async with self._lock:
            self._failure_streak = 0
            self._success_streak += 1
            if self._success_streak >= self._scale_up_streak and self._current < self._max:
                if self._pending_shrink > 0:
                    # A shrink was scheduled but its permit hasn't actually
                    # been withheld yet — cancel it. No semaphore permit
                    # needs to move since none was removed yet.
                    self._pending_shrink -= 1
                    self._current += 1
                else:
                    self._current += 1
                    self._sem.release()  # grow the pool by one real permit
                self._success_streak = 0

    async def report_failure(self):
        async with self._lock:
            self._success_streak = 0
            self._failure_streak += 1
            if self._failure_streak >= self._scale_down_streak and self._current > self._min:
                # Shrink the pool by one permit. asyncio.Semaphore has no
                # non-blocking "take one back" primitive, so we track the
                # deficit and let the *next* `release()` call absorb it
                # instead of returning the permit to the semaphore. This
                # keeps the effective ceiling accurate without ever
                # blocking here or over/under-counting permits.
                self._pending_shrink += 1
                self._current -= 1
                self._failure_streak = 0

    def snapshot(self) -> dict:
        return {
            "current_limit": self._current,
            "min": self._min,
            "max": self._max,
            "success_streak": self._success_streak,
            "failure_streak": self._failure_streak,
        }


class WorkerPool:
    """Spins up N worker coroutines that pull from a shared asyncio.Queue."""

    def __init__(self, worker_fn, num_workers: int):
        self.worker_fn = worker_fn
        self.num_workers = num_workers
        self._tasks: list[asyncio.Task] = []

    def start(self, *args, **kwargs) -> list[asyncio.Task]:
        self._tasks = [
            asyncio.create_task(self.worker_fn(*args, worker_id=i, **kwargs))
            for i in range(self.num_workers)
        ]
        return self._tasks

    async def stop(self, queue: asyncio.Queue):
        # Sentinel-based shutdown: one None per worker.
        for _ in self._tasks:
            await queue.put(None)
        await asyncio.gather(*self._tasks, return_exceptions=True)
