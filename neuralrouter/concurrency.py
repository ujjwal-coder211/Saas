"""Per-client + global concurrency — fair load when many users connect."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, status

from neuralrouter.config import MAX_CONCURRENT_PER_CLIENT, MAX_GLOBAL_CONCURRENT

_client_semaphores: dict[str, asyncio.Semaphore] = {}
_global_sem: asyncio.Semaphore | None = None


def _client_sem(client_id: str) -> asyncio.Semaphore:
    if client_id not in _client_semaphores:
        _client_semaphores[client_id] = asyncio.Semaphore(MAX_CONCURRENT_PER_CLIENT)
    return _client_semaphores[client_id]


def _global_semaphore() -> asyncio.Semaphore:
    global _global_sem
    if _global_sem is None:
        _global_sem = asyncio.Semaphore(MAX_GLOBAL_CONCURRENT)
    return _global_sem


class ConcurrencyGuard:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self._held_client = False
        self._held_global = False

    async def __aenter__(self):
        if MAX_GLOBAL_CONCURRENT > 0:
            try:
                await asyncio.wait_for(_global_semaphore().acquire(), timeout=0.01)
                self._held_global = True
            except asyncio.TimeoutError:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Server busy — too many users right now. Retry shortly.",
                )

        if MAX_CONCURRENT_PER_CLIENT > 0:
            try:
                await asyncio.wait_for(_client_sem(self.client_id).acquire(), timeout=0.01)
                self._held_client = True
            except asyncio.TimeoutError:
                if self._held_global:
                    _global_semaphore().release()
                    self._held_global = False
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many parallel requests on your API key.",
                )
        return self

    async def __aexit__(self, *args):
        if self._held_client:
            _client_sem(self.client_id).release()
        if self._held_global:
            _global_semaphore().release()


def active_users_summary() -> dict:
    return {
        "tracked_clients": len(_client_semaphores),
        "max_concurrent_per_client": MAX_CONCURRENT_PER_CLIENT,
        "max_global_concurrent": MAX_GLOBAL_CONCURRENT,
    }
