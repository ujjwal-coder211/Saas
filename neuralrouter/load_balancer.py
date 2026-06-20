"""Provider health, circuit breaker, and load-shedding for multi-user scale."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    failures: int = 0
    last_failure: float = 0.0
    open_until: float = 0.0


class ProviderBalancer:
    """
    Tracks failing providers; temporarily skips unhealthy ones.
    When many users hit the API, unhealthy routes fail fast instead of hanging.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._circuits: dict[str, CircuitState] = {}

    def _state(self, provider_key: str) -> CircuitState:
        if provider_key not in self._circuits:
            self._circuits[provider_key] = CircuitState()
        return self._circuits[provider_key]

    def is_available(self, provider_key: str) -> bool:
        st = self._state(provider_key)
        if st.open_until and time.time() < st.open_until:
            return False
        if st.open_until and time.time() >= st.open_until:
            st.open_until = 0.0
            st.failures = 0
        return True

    def record_success(self, provider_key: str) -> None:
        st = self._state(provider_key)
        st.failures = 0
        st.open_until = 0.0

    def record_failure(self, provider_key: str) -> None:
        st = self._state(provider_key)
        st.failures += 1
        st.last_failure = time.time()
        if st.failures >= self.failure_threshold:
            st.open_until = time.time() + self.cooldown_seconds
            logger.warning("Circuit OPEN for %s (%ss)", provider_key, self.cooldown_seconds)

    def status(self) -> dict:
        now = time.time()
        return {
            k: {
                "failures": v.failures,
                "open": bool(v.open_until and now < v.open_until),
                "open_until_in_s": max(0, int(v.open_until - now)) if v.open_until else 0,
            }
            for k, v in self._circuits.items()
        }


balancer = ProviderBalancer()

# Global in-flight cap (all users) — protects server + API spend
_global_semaphore: asyncio.Semaphore | None = None


def get_global_semaphore(max_concurrent: int) -> asyncio.Semaphore:
    global _global_semaphore
    if _global_semaphore is None:
        _global_semaphore = asyncio.Semaphore(max_concurrent)
    return _global_semaphore
