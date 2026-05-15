#!/usr/bin/env python3
"""
C1 — One-time migration: adaptive_itn ledger → global_pool_ledger
===================================================================
Run ONCE on deploy after updating adaptive_itn_service.py to use the
global_pool_ledger:{instance_type}:{az} Redis key.

What this script does
---------------------
1. Redis rename
   Scans all ``adaptive_itn:*`` keys and renames them to
   ``global_pool_ledger:*`` -- preserving all existing payload data.
   Any key that already has a ``global_pool_ledger:`` counterpart is
   *merged* (sums hours/count, max score, recomputes confidence).

2. Postgres merge
   Reads every row from ``adaptive_itn_ledger`` where pool_key contains
   more than one colon (old format: ``instance_type:az:cluster_id``).
   Groups by the first two colon-delimited segments (the global key).
   For each group:
     - sum node_hours_observed, interruption_count
     - take max raw_itn_score
     - recompute confidence = 1 − exp(−node_hours / TAU)
     - keep the most recent last_interruption_ts
   Upserts the merged row; deletes the per-cluster rows.

   Rows already in the short format (``instance_type:az``) are left as-is.

Safety
------
* Idempotent: safe to re-run.
* Dry-run mode: set DRY_RUN=1 to see the plan without writing changes.
* Rolls back Postgres transaction on any error.
"""

from __future__ import annotations

import json
import math
import os
import sys
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("migrate_global_pool_ledger")

DRY_RUN: bool = os.getenv("DRY_RUN", "0") == "1"

TAU = 720.0  # must match adaptive_itn_service.py

# ── Redis prefix constants ───────────────────────────────────────
OLD_PREFIX = "adaptive_itn:"
NEW_PREFIX = "global_pool_ledger:"


def _confidence(node_hours: float) -> float:
    return 1.0 - math.exp(-node_hours / TAU)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _merge_ledgers(ledgers: list[dict]) -> dict:
    """Merge a list of ledger dicts into one global ledger."""
    node_hours = sum(float(l.get("node_hours_observed", 0)) for l in ledgers)
    itn_count  = sum(int(l.get("interruption_count", 0)) for l in ledgers)
    raw_score  = max(float(l.get("raw_itn_score", 0.0)) for l in ledgers)
    last_itn_ts: Optional[datetime] = None
    for l in ledgers:
        ts = _parse_iso(l.get("last_interruption_ts"))
        if ts and (last_itn_ts is None or ts > last_itn_ts):
            last_itn_ts = ts
    confidence = _confidence(node_hours)
    return {
        "node_hours_observed": node_hours,
        "interruption_count": itn_count,
        "raw_itn_score": raw_score,
        "confidence": confidence,
        "last_interruption_ts": _iso(last_itn_ts),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# 1. Redis migration
# ══════════════════════════════════════════════════════════════════

def migrate_redis(redis_client) -> None:
    log.info("=== Redis migration ===")
    cursor = 0
    renamed = 0
    merged  = 0
    skipped = 0

    while True:
        cursor, keys = redis_client.scan(cursor, match=f"{OLD_PREFIX}*", count=500)
        for raw_key in keys:
            old_key   = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            pool_key  = old_key[len(OLD_PREFIX):]
            new_key   = f"{NEW_PREFIX}{pool_key}"

            old_raw  = redis_client.get(old_key)
            if not old_raw:
                skipped += 1
                continue

            try:
                old_ledger = json.loads(old_raw)
            except Exception:
                log.warning(f"  Could not parse {old_key} — skipping")
                skipped += 1
                continue

            existing_raw = redis_client.get(new_key)
            if existing_raw:
                # Destination already exists — merge, don't overwrite
                try:
                    existing_ledger = json.loads(existing_raw)
                except Exception:
                    existing_ledger = {}
                merged_ledger = _merge_ledgers([existing_ledger, old_ledger])
                log.info(f"  MERGE  {old_key} → {new_key}  "
                         f"(hours: {existing_ledger.get('node_hours_observed',0):.0f} + "
                         f"{old_ledger.get('node_hours_observed',0):.0f} → "
                         f"{merged_ledger['node_hours_observed']:.0f})")
                if not DRY_RUN:
                    redis_client.set(new_key, json.dumps(merged_ledger))
                    redis_client.delete(old_key)
                merged += 1
            else:
                log.info(f"  RENAME {old_key} → {new_key}")
                if not DRY_RUN:
                    redis_client.rename(old_key, new_key)
                renamed += 1

        if cursor == 0:
            break

    log.info(f"Redis complete:  renamed={renamed}  merged={merged}  skipped={skipped}")
    if DRY_RUN:
        log.info("  (DRY_RUN — no changes written)")


# ══════════════════════════════════════════════════════════════════
# 2. Postgres migration
# ══════════════════════════════════════════════════════════════════

def migrate_postgres(db) -> None:
    log.info("=== Postgres migration ===")
    from backend.models.adaptive_itn_ledger import AdaptiveItnLedger

    rows = db.query(AdaptiveItnLedger).all()

    # Separate clean global rows from legacy per-cluster rows
    global_rows: dict[str, AdaptiveItnLedger] = {}          # key   → row
    cluster_rows: dict[str, list[AdaptiveItnLedger]] = defaultdict(list)  # global_key → [rows]

    for row in rows:
        parts = row.pool_key.split(":")
        if len(parts) == 2:
            # Already global format: instance_type:az
            global_rows[row.pool_key] = row
        elif len(parts) >= 3:
            # Legacy format: instance_type:az:cluster_id  (or more segments)
            global_key = f"{parts[0]}:{parts[1]}"
            cluster_rows[global_key].append(row)
        else:
            log.warning(f"  Unrecognised pool_key format — skipping: {row.pool_key}")

    if not cluster_rows:
        log.info("  No per-cluster rows found — Postgres already clean.")
        return

    merged_count   = 0
    deleted_count  = 0

    for global_key, legacy in cluster_rows.items():
        log.info(f"  Merging {len(legacy)} per-cluster rows → {global_key}")

        # Build ledger dicts from ORM rows
        source_ledgers = []
        for r in legacy:
            source_ledgers.append({
                "node_hours_observed": float(r.node_hours_observed or 0),
                "interruption_count":  int(r.interruption_count or 0),
                "raw_itn_score":       float(r.raw_itn_score or 0),
                "last_interruption_ts": _iso(r.last_interruption_ts),
            })

        # Include existing global row if present
        if global_key in global_rows:
            grow = global_rows[global_key]
            source_ledgers.append({
                "node_hours_observed": float(grow.node_hours_observed or 0),
                "interruption_count":  int(grow.interruption_count or 0),
                "raw_itn_score":       float(grow.raw_itn_score or 0),
                "last_interruption_ts": _iso(grow.last_interruption_ts),
            })

        merged = _merge_ledgers(source_ledgers)

        if DRY_RUN:
            log.info(f"    [DRY_RUN] would upsert {global_key}  "
                     f"hours={merged['node_hours_observed']:.1f}  "
                     f"itn_count={merged['interruption_count']}  "
                     f"raw_score={merged['raw_itn_score']:.3f}  "
                     f"confidence={merged['confidence']:.3f}")
            for r in legacy:
                log.info(f"    [DRY_RUN] would delete {r.pool_key}")
            continue

        # Upsert the merged global row
        target = global_rows.get(global_key)
        if target is None:
            target = AdaptiveItnLedger(pool_key=global_key)
            db.add(target)

        target.node_hours_observed = merged["node_hours_observed"]
        target.interruption_count  = merged["interruption_count"]
        target.raw_itn_score       = merged["raw_itn_score"]
        target.confidence          = merged["confidence"]
        last_itn = _parse_iso(merged["last_interruption_ts"])
        if last_itn:
            target.last_interruption_ts = last_itn
        merged_count += 1

        # Delete the per-cluster rows
        for r in legacy:
            db.delete(r)
            deleted_count += 1

    if not DRY_RUN:
        try:
            db.commit()
            log.info(f"Postgres complete: upserted={merged_count}  deleted={deleted_count}")
        except Exception as exc:
            db.rollback()
            log.error(f"Postgres commit failed — rolled back: {exc}")
            raise
    else:
        log.info(f"Postgres plan: would upsert={merged_count}  delete={deleted_count}  (DRY_RUN)")


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

def main() -> None:
    if DRY_RUN:
        log.info("*** DRY RUN MODE — no changes will be written ***")

    # Bootstrap app context (works when run from the repo root with venv active)
    import django  # noqa: ensure env is set before imports below
    from backend.core.redis_client import get_redis_client
    from backend.models.base import SessionLocal

    redis_client = get_redis_client()
    db = SessionLocal()

    try:
        migrate_redis(redis_client)
        migrate_postgres(db)
        log.info("Migration complete.")
    finally:
        db.close()


if __name__ == "__main__":
    # Add repo root to sys.path so backend.* imports resolve
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    main()
