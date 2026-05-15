"""
Rate Limiting Utility — P-23
=============================
Token-bucket-style rate limiter using Redis INCR + EXPIRE.
Raises HTTP 429 when the per-key call count exceeds the window limit.
"""
from __future__ import annotations

import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def check_rate_limit(
    redis_client,
    key: str,
    max_calls: int,
    window_seconds: int,
) -> None:
    """
    Increment a Redis counter for *key* and raise HTTP 429 if the count
    exceeds *max_calls* within the rolling *window_seconds* window.

    The first call within a window sets the TTL automatically via EXPIRE
    (called only when count == 1 so we don't reset an existing window).

    Args:
        redis_client:    A live Redis client or None (no-op when None).
        key:             Unique rate-limit bucket key per endpoint + caller.
        max_calls:       Maximum allowed calls in the window.
        window_seconds:  Window duration in seconds.

    Raises:
        HTTPException(429) when the limit is exceeded.
    """
    if redis_client is None:
        return

    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, window_seconds)
        if count > max_calls:
            logger.warning("rate_limit_exceeded key=%s count=%d limit=%d", key, count, max_calls)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_calls} requests per {window_seconds}s.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("rate_limit_check_error key=%s: %s — failing open", key, exc)
