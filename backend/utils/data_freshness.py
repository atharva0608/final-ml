"""
Data Freshness Utility
======================
P-01: Centralized stale-detection and freshness metadata helpers.
All optimize endpoints inject these fields into responses so the UI
can distinguish fresh vs. stale cached data.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

STALE_THRESHOLD_SECONDS: int = int(os.getenv("AURA_STALE_THRESHOLD_SECS", "120"))


def compute_freshness(updated_at: Optional[datetime]) -> dict:
    """
    Compute freshness metadata from a UTC datetime.

    Returns a dict with three keys that must be merged into every API response:
      - data_updated_at  (ISO-8601 string with trailing Z, or None)
      - data_age_seconds (float seconds since update, or None)
      - is_stale         (True when age > STALE_THRESHOLD_SECONDS or updated_at is None)
    """
    if updated_at is None:
        return {
            "data_updated_at": None,
            "data_age_seconds": None,
            "is_stale": True,
        }
    now = datetime.utcnow()
    age = (now - updated_at).total_seconds()
    return {
        "data_updated_at": updated_at.isoformat() + "Z",
        "data_age_seconds": round(age, 1),
        "is_stale": age > STALE_THRESHOLD_SECONDS,
    }


def stale_node_filter(nodes: list, updated_at_field: str = "updated_at") -> tuple:
    """
    Split a list of node dicts into (fresh, stale_count).

    A node is considered stale when its ``updated_at_field`` value is either
    absent, unparseable, or older than STALE_THRESHOLD_SECONDS.

    Args:
        nodes:            list of dicts, each optionally containing ``updated_at_field``
        updated_at_field: key whose value is a UTC datetime or ISO-8601 string

    Returns:
        (fresh_nodes, stale_count) — fresh_nodes is a new list; originals unmodified.
    """
    now = datetime.utcnow()
    fresh: list = []
    stale_count: int = 0

    for node in nodes:
        ts = node.get(updated_at_field)
        if ts is None:
            stale_count += 1
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.rstrip("Z"))
            except ValueError:
                stale_count += 1
                continue
        age = (now - ts).total_seconds()
        if age > STALE_THRESHOLD_SECONDS:
            stale_count += 1
        else:
            fresh.append(node)

    return fresh, stale_count
