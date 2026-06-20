"""Simple in-memory rate limiter per API key (swap for Redis in production scale)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import HTTPException, Request, status

from neuralrouter.config import RATE_LIMIT_PER_MINUTE


_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, client_id: str) -> None:
    """Raise 429 if client exceeds requests per minute."""
    if RATE_LIMIT_PER_MINUTE <= 0:
        return

    key = client_id or request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - 60.0
    bucket = _buckets[key]

    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in a minute.",
        )

    bucket.append(now)
