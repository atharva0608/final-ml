"""
Redis Read Safety Wrapper
=========================
P-05: Null-safe helpers for all Redis reads in optimize_routes.py and helpers.

Redis can return None on:
  - Key not yet set (cold start)
  - Key expired
  - Redis restart / FLUSHDB
  - Network blip

Calling json.loads(None) raises TypeError.
These wrappers prevent that crash and return a safe default instead.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def safe_get_json(redis_client, key: str, default: Any = None) -> Any:
    """
    GET key → JSON decode. Returns ``default`` on miss, decode error, or Redis error.
    """
    try:
        raw = redis_client.get(key)
        if raw is None:
            return default
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("safe_get_json decode error key=%s: %s", key, exc)
        return default
    except Exception as exc:
        logger.warning("safe_get_json redis error key=%s: %s", key, exc)
        return default


def safe_hgetall(redis_client, key: str, default: Optional[dict] = None) -> dict:
    """
    HGETALL key → dict. Returns ``default`` (empty dict by default) on miss or error.
    """
    _default = default if default is not None else {}
    try:
        result = redis_client.hgetall(key)
        return result if result else _default
    except Exception as exc:
        logger.warning("safe_hgetall redis error key=%s: %s", key, exc)
        return _default


def safe_lrange_json(
    redis_client, key: str, start: int, end: int, default: Optional[List] = None
) -> List[Any]:
    """
    LRANGE key start end → list of JSON-decoded elements.
    Elements that fail to decode are skipped (not returned).
    Returns ``default`` (empty list) if Redis errors or key is absent.
    """
    _default = default if default is not None else []
    try:
        raw_entries = redis_client.lrange(key, start, end)
        if not raw_entries:
            return _default
        decoded = []
        for entry in raw_entries:
            try:
                decoded.append(json.loads(entry))
            except (json.JSONDecodeError, TypeError):
                pass
        return decoded
    except Exception as exc:
        logger.warning("safe_lrange_json redis error key=%s: %s", key, exc)
        return _default


def safe_ttl(redis_client, key: str) -> Optional[int]:
    """
    TTL key → int seconds remaining, or None if key does not exist (-2) or has no TTL (-1).
    Treats -2 (key missing) as None.
    Treats -1 (no expiry) as None.
    """
    try:
        ttl = redis_client.ttl(key)
        if ttl is None or ttl < 0:
            return None
        return ttl
    except Exception as exc:
        logger.warning("safe_ttl redis error key=%s: %s", key, exc)
        return None
