"""
API Response Contract Utility
==============================
P-02: Standard response wrappers for all optimize-page endpoints.

Every endpoint MUST return via ok() or not_ready().
Raw dict returns are NOT allowed after P-02.

Canonical data_ready_reason strings (use exactly these values):
  ""                            — data ready (empty string, not null)
  "node_allocatable_data_pending" — node_metadata table empty
  "pricing_data_pending"          — pricing_worker not yet populated
  "hpa_data_pending"              — hpa_configs table empty
  "insufficient_history"          — < 7 days snapshot data
  "stale_data"                    — age > STALE_THRESHOLD_SECONDS
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def ok(
    data: Dict[str, Any],
    data_ready: bool = True,
    data_ready_reason: str = "",
) -> Dict[str, Any]:
    """
    Wrap a successful response payload.

    Merges ``data`` with the standard readiness envelope.
    ``data`` must already include freshness keys from compute_freshness()
    where applicable (data_updated_at, data_age_seconds, is_stale).
    """
    return {
        **data,
        "data_ready": data_ready,
        "data_ready_reason": data_ready_reason,
    }


def not_ready(
    reason: str,
    partial_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Return a not-ready response with an optional partial payload.

    ``reason`` MUST be one of the canonical strings defined in this module's
    docstring. Unknown reason strings are accepted but should be avoided.
    """
    base: Dict[str, Any] = {
        "data_ready": False,
        "data_ready_reason": reason,
        "data_updated_at": None,
        "data_age_seconds": None,
        "is_stale": True,
    }
    if partial_data:
        base.update(partial_data)
    return base


def null_safe(value: Any, default: Any = None) -> Any:
    """Return ``value`` if it is not None, otherwise ``default``."""
    return value if value is not None else default
