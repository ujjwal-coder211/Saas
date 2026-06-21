"""Redis-backed rate limiting with in-memory fallback."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from neuralrouter.config import RATE_LIMIT_PER_MINUTE, REDIS_URL
from saas.auth.context import AuthContext

logger = logging.getLogger(__name__)

_memory_buckets: dict[str, deque[float]] = defaultdict(deque)
_redis = None


def _get_redis():
    global _redis
    if _redis is None and REDIS_URL:
        try:
            import redis

            _redis = redis.from_url(REDIS_URL, decode_responses=True)
            _redis.ping()
            logger.info("Redis rate limiter connected")
        except Exception as exc:
            logger.warning("Redis unavailable, using in-memory rate limit: %s", exc)
            _redis = False
    return _redis if _redis is not False else None


def rate_limit(request: Request, auth: AuthContext) -> None:
    limit = auth.rate_limit_per_minute or RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return

    key = f"rl:{auth.client_label}"
    r = _get_redis()

    if r:
        try:
            pipe = r.pipeline()
            now = int(time.time())
            window = now - 60
            pipe.zremrangebyscore(key, 0, window)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, 120)
            _, _, count, _ = pipe.execute()
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Upgrade plan or wait.",
                )
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Redis rate limit failed, using memory: %s", exc)

    # In-memory fallback
    now_f = time.time()
    window_start = now_f - 60.0
    bucket = _memory_buckets[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in a minute.",
        )
    bucket.append(now_f)
