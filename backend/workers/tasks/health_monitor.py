"""
Health Monitor — Pillar 5: Observability as a First-Class Feature
=================================================================

Celery task (every 5 minutes) that computes per-cluster health scores
and a global drift detection check.

Health score stored at: cluster_health:{cluster_id}
  pool_coverage_pct         — % nodes with ≥3 alternatives
  data_freshness_score      — weighted age of spot_advisor + pricing data
  execution_success_rate_24h — completed / total in last 24h
  savings_accuracy          — realized/estimated ratio (1.0 = perfect)
  ml_confidence             — average ml_score across market view pools
  overall_health            — weighted average (0–100)

Drift detection checks (every 15 minutes via separate task):
  - Actions stuck in intermediate state > 30 min → alert
  - spot_advisor data > 13 hours old → alert
  - Global pool cache < 100 pools → alert
  - realized/estimated savings ratio < 0.80 → alert
"""

import json
import time
from datetime import datetime, timedelta

from backend.core.logger import logger
from backend.workers.app import app


@app.task(name="health_monitor", bind=True, max_retries=1)
def run_health_monitor(self):
    """
    Pillar 5 — Layer 1: compute per-cluster health scores every 5 minutes.
    Stores cluster_health:{cluster_id} in Redis (TTL 600s).

    Pillar 6 — idempotency: if this exact task execution already ran, skip.
    """
    from backend.models.base import SessionLocal
    from backend.models.cluster import Cluster, ClusterStatus
    from backend.models.rebalancing_action import RebalancingAction
    from backend.core.redis_client import get_redis_client

    redis = get_redis_client()

    # Pillar 6 — idempotency guard
    task_id = self.request.id
    if task_id and redis:
        idempotency_key = f"task_done:{task_id}"
        if redis.get(idempotency_key):
            logger.info(f"[health_monitor] task_id={task_id} already ran — skipping")
            return {"status": "skipped", "reason": "idempotency"}

    db = SessionLocal()
    try:
        clusters = db.query(Cluster).filter(
            Cluster.status.notin_([ClusterStatus.DELETED, ClusterStatus.TERMINATED])
        ).all()
        for cluster in clusters:
            try:
                health = _compute_cluster_health(db, redis, cluster)
                redis.setex(
                    f"cluster_health:{cluster.id}",
                    600,
                    json.dumps(health),
                )
                if health['overall_health'] < 50:
                    logger.warning(
                        f"[health_monitor] CRITICAL: cluster={cluster.name} "
                        f"health={health['overall_health']:.0f}/100 — consider pausing rebalancing"
                    )
                elif health['overall_health'] < 70:
                    logger.warning(
                        f"[health_monitor] DEGRADED: cluster={cluster.name} "
                        f"health={health['overall_health']:.0f}/100"
                    )
            except Exception as e:
                logger.warning(f"[health_monitor] cluster={cluster.id} compute failed: {e}")
        # Pillar 6 — mark task done (1h TTL lets periodic re-runs proceed)
        if task_id and redis:
            redis.setex(f"task_done:{task_id}", 3600, "1")
        return {"status": "ok", "clusters_checked": len(clusters)}
    except Exception as e:
        logger.error(f"[health_monitor] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def _compute_cluster_health(db, redis, cluster) -> dict:
    """Compute health score for a single cluster."""
    from backend.models.rebalancing_action import RebalancingAction
    from backend.core.redis_client import key_market_view_cache

    cluster_id = str(cluster.id)
    region = getattr(cluster, 'region', 'us-east-1') or 'us-east-1'
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)

    # ── 1. Pool coverage score ──────────────────────────────────────────────
    # % of nodes that have ≥3 alternatives in the market view
    pool_coverage_pct = 0.0
    try:
        cov_raw = redis.get(f"cluster_coverage:{cluster_id}")
        if cov_raw:
            cov = json.loads(cov_raw)
            nodes = cov.get('per_node_summary', [])
            if nodes:
                covered = sum(1 for n in nodes if (n.get('alternative_count') or 0) >= 3)
                pool_coverage_pct = covered / len(nodes) * 100
        else:
            pool_coverage_pct = 50.0  # unknown = neutral
    except Exception:
        pool_coverage_pct = 50.0

    # ── 2. Data freshness score ─────────────────────────────────────────────
    data_freshness_score = 0.0
    try:
        sa_ts_raw = redis.get(f"spot:advisor:last_scraped:{region}")
        sa_age_hours = 999.0
        if sa_ts_raw:
            ts_str = sa_ts_raw.decode() if isinstance(sa_ts_raw, bytes) else sa_ts_raw
            sa_dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).replace(tzinfo=None)
            sa_age_hours = (now - sa_dt).total_seconds() / 3600

        mv_raw = redis.get(key_market_view_cache(region))
        mv_age_hours = 999.0
        if mv_raw:
            mv_data = json.loads(mv_raw)
            lu = mv_data.get('last_updated')
            if lu:
                lu_dt = datetime.fromisoformat(lu.replace('Z', '+00:00')).replace(tzinfo=None)
                mv_age_hours = (now - lu_dt).total_seconds() / 3600

        # Score: 100 if data <1h old, 0 if >13h old
        sa_score = max(0.0, 100.0 - (sa_age_hours / 13.0) * 100)
        mv_score = max(0.0, 100.0 - (mv_age_hours / 2.0) * 100)
        data_freshness_score = (sa_score * 0.5 + mv_score * 0.5)
    except Exception:
        data_freshness_score = 50.0

    # ── 3. Execution success rate (last 24h) ────────────────────────────────
    execution_success_rate_24h = 100.0
    try:
        actions = db.query(RebalancingAction).filter(
            RebalancingAction.cluster_id == cluster_id,
            RebalancingAction.started_at >= cutoff_24h,
        ).all()
        if actions:
            completed = sum(1 for a in actions if a.status == 'completed')
            execution_success_rate_24h = (completed / len(actions)) * 100
    except Exception:
        execution_success_rate_24h = 100.0

    # ── 4. Savings accuracy (realized / estimated) ──────────────────────────
    savings_accuracy = 100.0
    try:
        actions_24h = db.query(RebalancingAction).filter(
            RebalancingAction.cluster_id == cluster_id,
            RebalancingAction.started_at >= cutoff_24h,
            RebalancingAction.status == 'completed',
        ).all()
        total_est = sum(float(a.estimated_savings_hr or 0) for a in actions_24h)
        total_real = sum(float(a.realized_savings_hr or 0) for a in actions_24h)
        if total_est > 0:
            ratio = min(total_real / total_est, 1.5)
            savings_accuracy = min(100.0, ratio * 100)
    except Exception:
        savings_accuracy = 100.0

    # ── 5. ML confidence (avg ml_score from market view) ────────────────────
    ml_confidence = 70.0
    try:
        mv_raw = redis.get(key_market_view_cache(region))
        if mv_raw:
            mv_data = json.loads(mv_raw)
            pools = mv_data.get('data', [])[:50]
            if pools:
                avg_ml = sum(float(p.get('ml_score', 0.7) or 0.7) for p in pools) / len(pools)
                ml_confidence = avg_ml * 100
    except Exception:
        ml_confidence = 70.0

    # ── 6. Weighted overall health ───────────────────────────────────────────
    overall_health = (
        pool_coverage_pct      * 0.20
        + data_freshness_score * 0.20
        + execution_success_rate_24h * 0.30
        + savings_accuracy     * 0.15
        + ml_confidence        * 0.15
    )

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "region": region,
        "computed_at": now.isoformat(),
        "pool_coverage_pct": round(pool_coverage_pct, 1),
        "data_freshness_score": round(data_freshness_score, 1),
        "execution_success_rate_24h": round(execution_success_rate_24h, 1),
        "savings_accuracy": round(savings_accuracy, 1),
        "ml_confidence": round(ml_confidence, 1),
        "overall_health": round(overall_health, 1),
    }


@app.task(name="drift_detector", bind=True, max_retries=1)
def run_drift_detector(self):
    """
    Pillar 5 — Layer 2: drift detection every 15 minutes.

    Checks:
      1. Actions stuck in intermediate state > 30 min
      2. spot_advisor data > 13h old for any region
      3. Global pool cache has < 100 pools
      4. realized/estimated savings ratio < 0.80 (last 24h)
    """
    from backend.models.base import SessionLocal
    from backend.models.cluster import Cluster
    from backend.models.rebalancing_action import RebalancingAction
    from backend.core.redis_client import get_redis_client, key_market_view_cache

    redis = get_redis_client()

    # Pillar 6 — idempotency guard
    task_id = self.request.id
    if task_id and redis:
        if redis.get(f"task_done:{task_id}"):
            logger.info(f"[drift_detector] task_id={task_id} already ran — skipping")
            return {"status": "skipped", "reason": "idempotency"}

    db = SessionLocal()
    alerts = []
    now = datetime.utcnow()

    try:
        # ── Check 1: Stuck actions ──────────────────────────────────────────
        stuck_cutoff = now - timedelta(minutes=30)
        stuck_states = ('in_progress', 'waiting_agent', SM_SOURCE_CORDONED,
                        SM_SOURCE_DRAINED, SM_REPLACEMENT_LAUNCHING, SM_REPLACEMENT_READY)
        try:
            stuck = db.query(RebalancingAction).filter(
                RebalancingAction.started_at <= stuck_cutoff,
                RebalancingAction.status.in_(('in_progress', 'waiting_agent')),
            ).all()
            for s in stuck:
                duration = (now - s.started_at).total_seconds() / 60
                alerts.append(
                    f"STUCK_ACTION: action={s.id} cluster={s.cluster_id} "
                    f"state={s.current_state or s.status} stuck {duration:.0f} min"
                )
        except Exception as e:
            logger.warning(f"[drift_detector] stuck check failed: {e}")

        # ── Check 1b P3-B: Expire stuck PICKED_UP AgentActions > 30 min ────
        # If an agent picked up an action but never completed it (crash / restart),
        # the semaphore stays inflated and PlacementController is blocked.
        try:
            from backend.models.agent_action import AgentAction, AgentActionStatus
            _stuck_cutoff = now - timedelta(minutes=30)
            _stuck_aa = db.query(AgentAction).filter(
                AgentAction.status == AgentActionStatus.PICKED_UP,
                AgentAction.picked_up_at <= _stuck_cutoff,
            ).all()
            for _aa in _stuck_aa:
                _aa.status = AgentActionStatus.EXPIRED
                _aa.error_message = "auto-expired by health_monitor after 30 min in PICKED_UP"
                alerts.append(
                    f"EXPIRED_ACTION: agent_action={_aa.id} cluster={_aa.cluster_id} "
                    f"type={_aa.action_type} stuck PICKED_UP "
                    f"{(now - _aa.picked_up_at).total_seconds() / 60:.0f} min"
                )
                # Decrement per-cluster semaphore to unblock future PC/AR cycles
                try:
                    _sem_key = f"rebalance:active_count:{_aa.cluster_id}"
                    _new_val = redis.decr(_sem_key)
                    if _new_val < 0:
                        redis.set(_sem_key, 0, ex=300)
                except Exception:
                    pass
            if _stuck_aa:
                db.commit()
        except Exception as e:
            logger.warning(f"[drift_detector] PICKED_UP expiry check failed: {e}")

        # ── Check 2: Stale spot_advisor data ───────────────────────────────
        try:
            clusters = db.query(Cluster).filter(Cluster.status != 'DELETED').all()
            regions = set(c.region for c in clusters if c.region)
            for region in regions:
                ts_raw = redis.get(f"spot:advisor:last_scraped:{region}")
                if ts_raw:
                    ts = datetime.fromisoformat(
                        (ts_raw.decode() if isinstance(ts_raw, bytes) else ts_raw).replace('Z', '+00:00')
                    ).replace(tzinfo=None)
                    age_hours = (now - ts).total_seconds() / 3600
                    if age_hours > 13:
                        alerts.append(f"STALE_DATA: spot_advisor:{region} is {age_hours:.1f}h old (limit 13h)")
                else:
                    alerts.append(f"MISSING_DATA: spot:advisor:last_scraped:{region} not found")
        except Exception as e:
            logger.warning(f"[drift_detector] stale data check failed: {e}")

        # ── Check 3: Pool cache size ────────────────────────────────────────
        try:
            for region in regions:
                mv_raw = redis.get(key_market_view_cache(region))
                if mv_raw:
                    mv = json.loads(mv_raw)
                    count = len(mv.get('data', []))
                    if count < 100:
                        alerts.append(
                            f"LOW_POOLS: market_view_cache:{region} has only {count} pools (min 100)"
                        )
                else:
                    alerts.append(f"MISSING_CACHE: market_view_cache:{region} not found")
        except Exception as e:
            logger.warning(f"[drift_detector] pool cache check failed: {e}")

        # ── Check 4: Savings accuracy degradation ──────────────────────────
        try:
            cutoff = now - timedelta(hours=24)
            actions = db.query(RebalancingAction).filter(
                RebalancingAction.started_at >= cutoff,
                RebalancingAction.status == 'completed',
            ).all()
            total_est = sum(float(a.estimated_savings_hr or 0) for a in actions)
            total_real = sum(float(a.realized_savings_hr or 0) for a in actions)
            if total_est > 0:
                ratio = total_real / total_est
                if ratio < 0.80:
                    alerts.append(
                        f"SAVINGS_GAP: realized/estimated = {ratio:.2f} (threshold 0.80) "
                        f"— too many fallbacks or pool quality degraded"
                    )
        except Exception as e:
            logger.warning(f"[drift_detector] savings check failed: {e}")

        # Store drift alerts in Redis for health dashboard
        redis.setex("drift_alerts:latest", 1800, json.dumps({
            "computed_at": now.isoformat(),
            "alert_count": len(alerts),
            "alerts": alerts,
        }))

        if alerts:
            for alert in alerts:
                logger.warning(f"[drift_detector] {alert}")
        else:
            logger.info(f"[drift_detector] No drift detected")

        # Pillar 6 — mark task done
        if task_id and redis:
            redis.setex(f"task_done:{task_id}", 3600, "1")

        return {"status": "ok", "alert_count": len(alerts), "alerts": alerts}

    except Exception as e:
        logger.error(f"[drift_detector] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


# Import SM states so drift_detector can reference them
SM_SOURCE_CORDONED      = 'SOURCE_CORDONED'
SM_SOURCE_DRAINED       = 'SOURCE_DRAINED'
SM_REPLACEMENT_LAUNCHING = 'REPLACEMENT_LAUNCHING'
SM_REPLACEMENT_READY    = 'REPLACEMENT_READY'
