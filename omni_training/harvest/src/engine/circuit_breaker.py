"""
src/engine/circuit_breaker.py

Per-model 3-state circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED/OPEN.

- CLOSED:     normal operation, failures are counted.
- OPEN:       too many recent failures; calls are rejected until `open_seconds`
              has elapsed.
- HALF_OPEN:  a limited number of "probe" calls are allowed through. A
              successful probe closes the circuit again; a failed probe
              re-opens it.

This is intentionally dependency-free (no asyncio.sleep loops) so it can be
checked cheaply on every request without blocking a worker.
"""

import time
import asyncio
from enum import Enum
from dataclasses import dataclass, field


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ModelState:
    state: State = State.CLOSED
    failure_count: int = 0
    opened_at: float = 0.0
    probes_in_flight: int = 0


class CircuitBreaker:
    """Thread-safe (within a single event loop) per-model circuit breaker."""

    def __init__(self, failure_threshold: int = 5, open_seconds: float = 60.0,
                 half_open_max_probes: int = 1):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.half_open_max_probes = half_open_max_probes
        self._models: dict[str, _ModelState] = {}
        self._lock = asyncio.Lock()

    def _get(self, model: str) -> _ModelState:
        if model not in self._models:
            self._models[model] = _ModelState()
        return self._models[model]

    async def allow_request(self, model: str) -> bool:
        """Call before making a request. Returns True if the request may proceed."""
        async with self._lock:
            ms = self._get(model)

            if ms.state == State.CLOSED:
                return True

            if ms.state == State.OPEN:
                if time.monotonic() - ms.opened_at >= self.open_seconds:
                    # Transition to HALF_OPEN and allow a single probe through.
                    ms.state = State.HALF_OPEN
                    ms.probes_in_flight = 1
                    return True
                return False

            if ms.state == State.HALF_OPEN:
                if ms.probes_in_flight < self.half_open_max_probes:
                    ms.probes_in_flight += 1
                    return True
                return False

        return False

    async def record_success(self, model: str) -> None:
        async with self._lock:
            ms = self._get(model)
            ms.failure_count = 0
            ms.probes_in_flight = 0
            ms.state = State.CLOSED

    async def record_failure(self, model: str) -> None:
        async with self._lock:
            ms = self._get(model)

            if ms.state == State.HALF_OPEN:
                # Probe failed: back to OPEN, reset the clock.
                ms.state = State.OPEN
                ms.opened_at = time.monotonic()
                ms.probes_in_flight = 0
                return

            ms.failure_count += 1
            if ms.failure_count >= self.failure_threshold:
                ms.state = State.OPEN
                ms.opened_at = time.monotonic()
                ms.failure_count = 0

    def snapshot(self) -> dict:
        """Non-blocking read of current state, useful for metrics/logging."""
        return {
            model: {
                "state": ms.state.value,
                "failure_count": ms.failure_count,
            }
            for model, ms in self._models.items()
        }
