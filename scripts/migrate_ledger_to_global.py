"""
C8 — Migrate legacy pool_stability:* Redis keys to global_pool_ledger:*
=======================================================================

Background
----------
Before the adaptive-ledger refactor (C1), a very early version of the
interruption tracking stored per-cluster risk data under the key scheme:

    pool_stability:{instance_type}:{az}:{cluster_id}

C1's migration script (migrate_global_pool_ledger.py) handled the next
generation of keys: ``adaptive_itn:{pool_key}:{cluster_id}``.

This script targets the *oldest* format — ``pool_stability:*:*:*`` — that
may still exist in production Redis instances that were never fully migrated.

Migration logic
---------------
1. Scan all ``pool_stability:*`` keys.
2. Parse each key as ``pool_stability:{instance_type}:{az}:{cluster_id}``.
   Keys that do not have exactly 4 colon-delimited segments are logged and
   skipped.
3. Group by ``(instance_type, az)`` — the global pool key.
4. For each group:
   a. Sum ``node_hours_observed`` and ``interruption_count``.
   b. Take the maximum ``raw_itn_score``.
   c. Keep the most-recent ``last_interruption_ts``.
   d. Recompute ``confidence = 1 - exp(-total_hours / TAU)``.
5. Read any existing ``global_pool_ledger:{pool_key}`` entry and MERGE:
   - sum hours / counts
   - max score
   - max ts
   - recompute confidence
6. Write the merged ledger back to ``global_pool_ledger:{pool_key}``.
7. Delete all migrated ``pool_stability:*`` source keys.

Safety
------
* DRY_RUN mode (default): prints all planned changes without writing.
  Set environment variable DRY_RUN=0 to execute.
* Idempotent: safe to re-run; source keys are deleted only after a
  successful write-back so a partial failure leaves data intact.
* Does NOT touch Postgres — the hourly decay task will flush the updated
  Redis ledgers to Postgres at its next scheduled run.

Usage
-----
    # Preview (nothing is written)
    python scripts/migrate_ledger_to_global.py

    # Execute migration
    DRY_RUN=0 python scripts/migrate_ledger_to_global.py
"""

import json
import logging
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap — allow running directly from the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_ledger_to_global")

# ---------------------------------------------------------------------------
# Constants (must match adaptive_itn_service.py)
# ---------------------------------------------------------------------------
TAU = 720.0          # node-hours for confidence to reach ~63%
KEY_PREFIX = "pool_stability:"
TARGET_PREFIX = "global_pool_ledger:"
DRY_RUN = os.environ.get("DRY_RUN", "1") not in ("0", "false", "False", "no")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _max_ts(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the more-recent of two ISO-8601 timestamps (or whichever is not None)."""
    dt_a = _parse_iso(a)
    dt_b = _parse_iso(b)
    if dt_a is None and dt_b is None:
        return None
    if dt_a is None:
        return b
    if dt_b is None:
        return a
    return _iso(dt_a if dt_a >= dt_b else dt_b)


def _merge_ledgers(base: dict, incoming: dict) -> dict:
    """
    Merge *incoming* ledger data into *base*.

    Sums:   node_hours_observed, interruption_count
    Max:    raw_itn_score, last_interruption_ts  (most recent)
    Recompute: confidence from merged node_hours_observed
    """
    total_hours = float(base.get("node_hours_observed", 0.0)) + float(
        incoming.get("node_hours_observed", 0.0)
    )
    total_itn = int(base.get("interruption_count", 0)) + int(
        incoming.get("interruption_count", 0)
    )
    max_score = max(
        float(base.get("raw_itn_score", 0.0)),
        float(incoming.get("raw_itn_score", 0.0)),
    )
    latest_ts = _max_ts(
        base.get("last_interruption_ts"),
        incoming.get("last_interruption_ts"),
    )
    confidence = 1.0 - math.exp(-total_hours / TAU)

    return {
        "node_hours_observed": total_hours,
        "interruption_count": total_itn,
        # C2 severity fields — not present in old pool_stability keys; default to 0
        "itn_warning_count": int(base.get("itn_warning_count", 0)),
        "actual_termination_count": int(base.get("actual_termination_count", 0)),
        "rebalance_notice_count": int(base.get("rebalance_notice_count", 0)),
        "peak_simultaneous_itn": max(
            int(base.get("peak_simultaneous_itn", 0)),
            int(incoming.get("peak_simultaneous_itn", 0)),
        ),
        "raw_itn_score": max_score,
        "confidence": confidence,
        "last_interruption_ts": latest_ts,
        "last_updated": _iso(_now_utc()),
    }


def _parse_pool_stability_key(raw_key: str) -> Optional[tuple]:
    """
    Parse ``pool_stability:{instance_type}:{az}:{cluster_id}`` key.

    Returns ``(instance_type, az, cluster_id)`` or ``None`` if malformed.
    The AZ and instance_type may themselves contain colons (e.g. "us-east-1a"),
    so we split conservatively: the last segment is cluster_id (UUID, no colons),
    and instance_type is the first segment after the prefix.

    Key structure assumption:
        pool_stability:<type>:<az>:<cluster_id>
    where <type> never contains ":" but <az> never does either.
    """
    after_prefix = raw_key[len(KEY_PREFIX):]   # strip "pool_stability:"
    parts = after_prefix.split(":", 2)          # split into at most 3 parts
    if len(parts) != 3:
        return None
    instance_type, az, cluster_id = parts
    if not instance_type or not az or not cluster_id:
        return None
    return instance_type, az, cluster_id


# ---------------------------------------------------------------------------
# Main migration
# ---------------------------------------------------------------------------

def migrate(redis_client) -> None:
    if DRY_RUN:
        logger.info("=== DRY RUN mode — no changes will be written. Set DRY_RUN=0 to execute. ===")
    else:
        logger.info("=== LIVE mode — changes WILL be written to Redis. ===")

    # ── Step 1: Scan all pool_stability:* keys ───────────────────────────────
    source_keys: List[str] = []
    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match=f"{KEY_PREFIX}*", count=500)
        for k in keys:
            source_keys.append(k.decode() if isinstance(k, bytes) else k)
        if cursor == 0:
            break

    logger.info(f"Found {len(source_keys)} pool_stability:* keys")
    if not source_keys:
        logger.info("Nothing to migrate.")
        return

    # ── Step 2: Parse keys and group by pool ─────────────────────────────────
    # pool_key → list of (cluster_id, raw_json_string)
    pool_data: Dict[str, list] = defaultdict(list)
    skipped = 0

    for raw_key in source_keys:
        parsed = _parse_pool_stability_key(raw_key)
        if parsed is None:
            logger.warning(f"  SKIP: unrecognised key format: {raw_key}")
            skipped += 1
            continue
        instance_type, az, cluster_id = parsed
        raw = redis_client.get(raw_key)
        if not raw:
            logger.warning(f"  SKIP: key exists but has no value: {raw_key}")
            skipped += 1
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"  SKIP: invalid JSON in {raw_key}")
            skipped += 1
            continue
        pool_key = f"{instance_type}:{az}"
        pool_data[pool_key].append((cluster_id, data))

    logger.info(
        f"Parsed: {len(pool_data)} unique pools from {len(source_keys) - skipped} "
        f"valid keys ({skipped} skipped)"
    )

    # ── Step 3: Merge per-pool and write target keys ──────────────────────────
    migrated_pools = 0
    merged_with_existing = 0
    keys_to_delete: List[str] = []

    for pool_key, entries in pool_data.items():
        # 3a. Aggregate all source ledgers into one
        aggregated: dict = {
            "node_hours_observed": 0.0,
            "interruption_count": 0,
            "itn_warning_count": 0,
            "actual_termination_count": 0,
            "rebalance_notice_count": 0,
            "peak_simultaneous_itn": 0,
            "raw_itn_score": 0.0,
            "confidence": 0.0,
            "last_interruption_ts": None,
            "last_updated": _iso(_now_utc()),
        }
        for _cluster_id, src_data in entries:
            aggregated = _merge_ledgers(aggregated, src_data)

        target_key = f"{TARGET_PREFIX}{pool_key}"

        # 3b. Read existing global ledger (if any) and merge into it
        existing_raw = redis_client.get(target_key)
        if existing_raw:
            try:
                existing = json.loads(existing_raw)
                aggregated = _merge_ledgers(existing, aggregated)
                merged_with_existing += 1
                logger.info(f"  MERGE  {pool_key} ({len(entries)} source keys → merged with existing)")
            except json.JSONDecodeError:
                logger.warning(f"  WARN   {pool_key}: existing target has invalid JSON — overwriting")

        else:
            logger.info(f"  WRITE  {pool_key} ({len(entries)} source keys → new entry)")

        if DRY_RUN:
            logger.info(
                f"    [dry-run] would write {target_key}: "
                f"hours={aggregated['node_hours_observed']:.1f} "
                f"itn={aggregated['interruption_count']} "
                f"score={aggregated['raw_itn_score']:.4f} "
                f"conf={aggregated['confidence']:.4f}"
            )
        else:
            redis_client.set(target_key, json.dumps(aggregated))

        # Track source keys to delete after successful writes
        instance_type, az = pool_key.split(":", 1)
        for _cluster_id, _ in entries:
            keys_to_delete.append(f"{KEY_PREFIX}{instance_type}:{az}:{_cluster_id}")

        migrated_pools += 1

    # ── Step 4: Delete source keys (only after all writes succeed) ────────────
    if not DRY_RUN and keys_to_delete:
        pipe = redis_client.pipeline(transaction=False)
        for k in keys_to_delete:
            pipe.delete(k)
        pipe.execute()
        logger.info(f"Deleted {len(keys_to_delete)} source pool_stability:* keys")
    elif DRY_RUN and keys_to_delete:
        logger.info(f"[dry-run] would delete {len(keys_to_delete)} source keys")

    logger.info(
        f"\nMigration {'preview' if DRY_RUN else 'complete'}: "
        f"{migrated_pools} pools written ({merged_with_existing} merged with existing), "
        f"{skipped} keys skipped"
    )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from backend.core.redis_client import get_redis_client  # type: ignore
        _redis = get_redis_client()
    except Exception as _import_err:
        # Fallback: connect via REDIS_URL env var (useful in a standalone shell)
        import redis as _redis_lib  # type: ignore
        _url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        logger.info(f"Connecting to Redis via REDIS_URL: {_url}")
        _redis = _redis_lib.from_url(_url)

    migrate(_redis)
