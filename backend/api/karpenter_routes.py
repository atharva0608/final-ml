"""
Karpenter API Routes

FastAPI endpoints for Karpenter auto-optimization management:
- Status / configuration / deployment
- Activity feed and performance stats
- Cluster-level toggle (pause/resume)
- Karpenter mode management (dry_run / auto)
- Dry-run recommendations and manual apply
"""
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum as PyEnum
import uuid

from backend.models.base import get_db
from backend.models.user import User
from backend.models.cluster import Cluster, KarpenterMode
from backend.core.dependencies import get_current_user, RequireAccess
from backend.core.logger import logger


# ─── Instance Specs: (vcpu, memory_gb, hourly_od_usd) — ap-south-1 fallback only ──
# For accurate region-specific pricing, use _get_od_price() which reads from Redis
# (populated by the pricing worker). INSTANCE_SPECS is used for vCPU/memory specs
# and as a last-resort price fallback when Redis is unavailable.
INSTANCE_SPECS: Dict[str, tuple] = {
    "t3.nano":    (2, 0.5,  0.0058), "t3.micro":   (2, 1.0,  0.0116),
    "t3.small":   (2, 2.0,  0.0232), "t3.medium":  (2, 4.0,  0.0464),
    "t3.large":   (2, 8.0,  0.0928), "t3.xlarge":  (4, 16.0, 0.1856),
    "t3.2xlarge": (8, 32.0, 0.3712),
    "t3a.micro":  (2, 1.0,  0.0104), "t3a.small":  (2, 2.0,  0.0209),
    "t3a.medium": (2, 4.0,  0.0418), "t3a.large":  (2, 8.0,  0.0836),
    "t3a.xlarge": (4, 16.0, 0.1672), "t3a.2xlarge":(8, 32.0, 0.3344),
    "t4g.micro":  (2, 1.0,  0.0092), "t4g.small":  (2, 2.0,  0.0184),
    "t4g.medium": (2, 4.0,  0.0368), "t4g.large":  (2, 8.0,  0.0736),
    "t4g.xlarge": (4, 16.0, 0.1472), "t4g.2xlarge":(8, 32.0, 0.2944),
    "m5.large":   (2, 8.0,  0.096),  "m5.xlarge":  (4, 16.0, 0.192),
    "m5.2xlarge": (8, 32.0, 0.384),  "m5.4xlarge": (16,64.0, 0.768),
    "m6i.large":  (2, 8.0,  0.096),  "m6i.xlarge": (4, 16.0, 0.192),
    "m6i.2xlarge":(8, 32.0, 0.384),
    "m6g.medium": (1, 4.0,  0.038),  "m6g.large":  (2, 8.0,  0.077),
    "m6g.xlarge": (4, 16.0, 0.154),
    "c5.large":   (2, 4.0,  0.085),  "c5.xlarge":  (4, 8.0,  0.17),
    "c5.2xlarge": (8, 16.0, 0.34),
    "c6i.large":  (2, 4.0,  0.085),  "c6i.xlarge": (4, 8.0,  0.17),
    "c6g.medium": (1, 2.0,  0.034),  "c6g.large":  (2, 4.0,  0.068),
    "c6g.xlarge": (4, 8.0,  0.136),
    "r5.large":   (2, 16.0, 0.126),  "r5.xlarge":  (4, 32.0, 0.252),
    "r5.2xlarge": (8, 64.0, 0.504),
    "r6i.large":  (2, 16.0, 0.126),  "r6i.xlarge": (4, 32.0, 0.252),
}


def _get_od_price(instance_type: str, region: str = None, redis_client=None) -> Optional[float]:
    """Get OD hourly price from Redis (region-accurate), falling back to INSTANCE_SPECS."""
    if redis_client and region:
        for key_fmt in (f"od_price:{region}:{instance_type}",
                        f"ondemand_price:{region}:{instance_type}"):
            try:
                val = redis_client.get(key_fmt)
                if val:
                    return float(val)
            except Exception:
                pass
    specs = INSTANCE_SPECS.get(instance_type)
    return specs[2] if specs else None


def _bin_pack_instance(current_type: str, cpu_pct: float, mem_pct: float,
                        buffer_pct: float = 30.0, region: str = None,
                        redis_client=None):
    """
    Bin-pack a node based on observed CPU/memory utilization.

    Returns (recommended_type, delta_monthly_usd) where:
      - delta > 0: downsize recommended (monthly savings)
      - delta < 0: upsize recommended (monthly cost increase, but node is under-provisioned)
      - delta = 0: already optimal

    When region and redis_client are provided, uses region-accurate OD pricing
    from Redis. Falls back to INSTANCE_SPECS hardcoded ap-south-1 prices otherwise.
    """
    specs = INSTANCE_SPECS.get(current_type)
    if not specs or (cpu_pct <= 0 and mem_pct <= 0):
        return current_type, 0.0

    c_vcpu, c_mem, _fallback_hourly = specs
    c_hourly = _get_od_price(current_type, region, redis_client) or _fallback_hourly
    buf = 1.0 + buffer_pct / 100.0

    # P-M7: When one dimension is zero, use a minimal floor so bin-packing
    # still selects a type that fits the non-zero dimension.
    required_vcpu = max(0.25, (c_vcpu * max(cpu_pct, 0) / 100.0) * buf)
    required_mem  = max(0.5,  (c_mem  * max(mem_pct, 0) / 100.0) * buf)

    current_fits = (c_vcpu >= required_vcpu and c_mem >= required_mem)

    def _priced_candidates(filter_fn):
        """Build candidate list with region-accurate pricing."""
        result = []
        for t, (v, m, _fh) in INSTANCE_SPECS.items():
            h = _get_od_price(t, region, redis_client) or _fh
            if filter_fn(h):
                result.append((t, v, m, h))
        return sorted(result, key=lambda x: x[3])

    if not current_fits:
        for t_name, vcpu, mem, hourly in _priced_candidates(lambda h: h > c_hourly):
            if vcpu >= required_vcpu and mem >= required_mem:
                return t_name, round((c_hourly - hourly) * 730, 2)
        return current_type, 0.0

    else:
        for t_name, vcpu, mem, hourly in _priced_candidates(lambda h: h < c_hourly):
            if vcpu >= required_vcpu and mem >= required_mem:
                return t_name, round((c_hourly - hourly) * 730, 2)
        return current_type, 0.0


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class KarpenterModeStr(str, PyEnum):
    DRY_RUN = "dry_run"
    AUTO = "auto"


class ClusterKarpenterConfig(BaseModel):
    cluster_id: str
    strategy: str = Field(default="balanced", description="cost-first | balanced | performance-first")
    instance_families: List[str] = Field(default_factory=lambda: ["m5", "m6i", "c5", "c6i"])
    architectures: List[str] = Field(default_factory=lambda: ["amd64"])
    spot_target_pct: int = Field(default=75, ge=0, le=100)
    on_demand_fallback: bool = True
    min_vcpu: int = Field(default=2, ge=1)
    max_vcpu: int = Field(default=16, ge=1)
    min_memory_gib: int = Field(default=4, ge=1)
    max_memory_gib: int = Field(default=64, ge=1)
    consolidation_enabled: bool = True
    consolidation_threshold_pct: int = Field(default=60, ge=0, le=100)
    node_max_lifetime_days: int = Field(default=7, ge=1)
    cost_alert_monthly: Optional[float] = None
    cost_alert_hourly: Optional[float] = None
    daily_budget: Optional[float] = None


class KarpenterDeployRequest(BaseModel):
    cluster_configs: List[ClusterKarpenterConfig]
    mode: KarpenterModeStr = Field(default=KarpenterModeStr.DRY_RUN, description="dry_run (default, safe) or auto")
    gradual_rollout: bool = True
    acknowledgements: List[str] = Field(default_factory=list)


class KarpenterToggleRequest(BaseModel):
    enabled: bool


class KarpenterModeUpdateRequest(BaseModel):
    mode: KarpenterModeStr


class KarpenterApplyRequest(BaseModel):
    """For manually applying a Karpenter dry-run recommendation."""
    recommended_type: str
    reason: Optional[str] = None
    is_stateful: bool = False          # True → queue CORDON+DRAIN+TERMINATE for stateful OD resize
    instance_id: Optional[str] = None  # EC2 instance id (from frontend node.name / instance_id)
    spot_pool: Optional[Dict[str, Any]] = None  # Best spot pool (stateless only)


class KarpenterBatchApplyRequest(BaseModel):
    instance_ids: List[str]


# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/karpenter", tags=["Karpenter"])


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Get Karpenter deployment status",
    description="Returns whether Karpenter is set up, active clusters, mode, and high-level stats"
)
def get_karpenter_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns overall Karpenter status for the user's organization.
    Includes deployment state, mode, active cluster count, and summary metrics.
    """
    # Query clusters that have karpenter_mode set (meaning Karpenter is installed)
    karpenter_clusters = db.query(Cluster).filter(
        Cluster.karpenter_mode.isnot(None)
    ).all()

    if not karpenter_clusters:
        return {
            "is_setup": False,
            "status": "not_setup",
            "mode": None,
            "active_clusters": 0,
            "total_managed_nodes": 0,
            "estimated_monthly_savings": 0,
            "pending_recommendations": 0,
            "last_activity": None,
        }

    # Determine overall mode (use first cluster's mode, or mixed if different)
    modes = set(c.karpenter_mode.value for c in karpenter_clusters if c.karpenter_mode)
    overall_mode = list(modes)[0] if len(modes) == 1 else "mixed"

    return {
        "is_setup": True,
        "status": "active",
        "mode": overall_mode,
        "active_clusters": len(karpenter_clusters),
        "total_managed_nodes": sum(c.node_count or 0 for c in karpenter_clusters),
        "estimated_monthly_savings": sum(c.estimated_savings or 0 for c in karpenter_clusters),
        "pending_recommendations": 14 if overall_mode == "dry_run" else 0,  # TODO: real count from K8s events
        "last_activity": datetime.utcnow().isoformat(),
        "clusters": [
            {
                "cluster_id": c.id,
                "name": c.name,
                "mode": c.karpenter_mode.value if c.karpenter_mode else None,
                "node_count": c.node_count or 0,
            }
            for c in karpenter_clusters
        ],
    }


_KARPENTER_CONFIG_DEFAULTS = {
    "strategy": "balanced",
    "instance_families": ["m5", "m6i", "c5", "c6i", "t3", "t4g"],
    "architectures": ["amd64", "arm64"],
    "spot_target_pct": 75,
    "on_demand_fallback": True,
    "buffer_pct": 30,          # Safety headroom above P95 usage for bin-packing
    "min_vcpu": 1,
    "max_vcpu": 16,
    "min_memory_gib": 1,
    "max_memory_gib": 64,
    "consolidation_enabled": True,
    "consolidation_threshold_pct": 60,
    "node_max_lifetime_days": 7,
    "auto_rebalancing_enabled": False,   # Karpenter mode = auto
    "auto_rightsizing_enabled": False,   # Instance type bin-packing auto-apply
    "stateful_max_downscale_pct": 50,    # Max % size reduction allowed for stateful
    "stateful_spot_migration": False,    # Always manual for stateful
    "stateful_od_rightsizing": True,     # On-demand rightsizing for stateful
    "is_active": False,
}


@router.get(
    "/config",
    summary="Get Karpenter config for cluster",
    description="Returns the saved Karpenter configuration for a given cluster"
)
def get_karpenter_config(
    cluster_id: str = Query(..., description="Cluster UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get per-cluster Karpenter configuration (Redis-backed, falls back to defaults).
    DB is always the source of truth for the two automation toggles.
    """
    import json as _json
    cfg = {**_KARPENTER_CONFIG_DEFAULTS, "cluster_id": cluster_id}

    # Layer 1: Redis-stored UI settings (strategy, families, etc.)
    try:
        from backend.core.redis_client import get_redis_client as _get_redis
        _stored = _get_redis().get(f"karpenter_config:{cluster_id}")
        if _stored:
            cfg.update(_json.loads(_stored))
    except Exception:
        pass

    # Layer 2: DB overrides — always authoritative for automation toggles
    try:
        from backend.models.cluster import ClusterOptimizationSettings
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if cluster:
            opt = cluster.optimization_settings
            if opt is not None:
                # auto_rebalancing_enabled = platform auto-rebalancer toggle
                cfg["auto_rebalancing_enabled"] = bool(opt.auto_rebalance_enabled)
                # auto_rightsizing_enabled = bin-pack + Karpenter rightsizing toggle
                cfg["auto_rightsizing_enabled"] = bool(opt.auto_rightsizing_enabled)
                # optimization_target: "spot" or "on_demand" — billing model for rightsizing
                cfg["optimization_target"] = getattr(opt, 'optimization_target', 'spot') or 'spot'
                # locked when both toggles ON (synergy mode)
                cfg["optimization_target_locked"] = bool(
                    opt.auto_rebalance_enabled and opt.auto_rightsizing_enabled
                )
                # diversify_pools — DB is authoritative (auto_rebalancer reads from DB)
                cfg["diversify_pools"] = bool(getattr(opt, 'diversify_pools', False))
                # stateful rightsizing fields
                cfg["auto_stateful_rightsizing_enabled"] = bool(
                    getattr(opt, 'auto_stateful_rightsizing_enabled', False)
                )
            # Load StatefulRules for stateful policy fields
            sf = cluster.stateful_rules
            if sf:
                cfg["stateful_require_approval"] = bool(sf.require_approval)
                cfg["stateful_max_downscale_pct"] = int(sf.max_downscale_percent or 25)
            elif cluster.karpenter_mode:
                # Fallback: infer rebalancing from karpenter_mode if no opt settings row yet
                cfg["auto_rebalancing_enabled"] = cluster.karpenter_mode.value == "auto"
                cfg["optimization_target"] = "spot"
                cfg["optimization_target_locked"] = False
    except Exception:
        pass

    return cfg


@router.post(
    "/config",
    status_code=status.HTTP_201_CREATED,
    summary="Save Karpenter configuration",
    description="Save Karpenter setup wizard output for one or more clusters"
)
def save_karpenter_config(
    payload: KarpenterDeployRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Persist wizard config (called before deploy)."""
    logger.info(f"Saving Karpenter config for {len(payload.cluster_configs)} clusters")
    return {
        "saved": True,
        "cluster_count": len(payload.cluster_configs),
        "configs": [c.dict() for c in payload.cluster_configs],
    }


@router.patch(
    "/config/{cluster_id}",
    summary="Update Karpenter config for a single cluster",
    description="Partial update of Karpenter configuration, including mode switching"
)
def update_karpenter_config(
    cluster_id: str,
    updates: Dict[str, Any],
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Patch cluster-level Karpenter settings (Redis-persisted + DB-synced).

    auto_rebalancing_enabled:
        True  → karpenter_mode=auto  + ClusterOptimizationSettings.auto_rebalance_enabled=True
                 The auto-rebalancer Celery task uses ML-ranked pools; our agent does the
                 CORDON → DRAIN → TERMINATE sequence.
        False → karpenter_mode=dry_run + auto_rebalance_enabled=False (task stops running)

    auto_rightsizing_enabled:
        True  → ClusterOptimizationSettings.auto_rightsizing_enabled=True
                 Karpenter consolidation (WhenEmptyOrUnderutilized) handles bin-packing;
                 ML pool ranking refreshes the NodePool every 30 min.
        False → auto_rightsizing_enabled=False (nightly rightsizing worker skips cluster)
    """
    import json as _json
    from backend.models.cluster import ClusterOptimizationSettings
    logger.info(f"Updating Karpenter config for cluster {cluster_id}: {list(updates.keys())}")

    auto_rebalancing = updates.get("auto_rebalancing_enabled")
    auto_rightsizing = updates.get("auto_rightsizing_enabled")

    # Fetch cluster once for all DB updates
    cluster = None
    if auto_rebalancing is not None or auto_rightsizing is not None or "mode" in updates:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

        # ── KARPENTER PREREQUISITE CHECK ────────────────────────────────────
        # Execution toggles (auto_rebalancing, auto_rightsizing) require Karpenter
        # to be installed (karpenter_mode != None).  Without Karpenter the cluster
        # is view-only: WIE, placement advisor, and telemetry still run, but no
        # mutations (evictions, cordon, drain, terminate) are dispatched.
        if (auto_rebalancing is True or auto_rightsizing is True) and cluster.karpenter_mode is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Karpenter is not installed on this cluster. "
                    "Install Karpenter first to enable execution mode. "
                    "Until then the cluster runs in view-only mode "
                    "(WIE + placement recommendations, no mutations)."
                ),
            )

        # 1. Sync karpenter_mode (auto / dry_run)
        if auto_rebalancing is not None or "mode" in updates:
            new_mode = ("auto" if auto_rebalancing else "dry_run") if auto_rebalancing is not None else updates["mode"]
            try:
                cluster.karpenter_mode = KarpenterMode(new_mode)
                logger.info(f"Karpenter mode → {new_mode} for cluster {cluster_id}")
            except Exception:
                pass  # Karpenter not deployed yet — mode stays None

        # 2. Sync BOTH automation toggles to ClusterOptimizationSettings (the DB row
        #    that Celery tasks actually read — this is the source of truth for tasks).
        opt = cluster.optimization_settings
        if opt is None:
            opt = ClusterOptimizationSettings(cluster_id=cluster_id)
            db.add(opt)
        if auto_rebalancing is not None:
            opt.auto_rebalance_enabled = bool(auto_rebalancing)
            logger.info(
                f"ClusterOptimizationSettings.auto_rebalance_enabled → {auto_rebalancing} "
                f"for cluster {cluster_id} (auto-rebalancer task will {'run' if auto_rebalancing else 'skip'})"
            )
            # ── KARPENTER CONSOLIDATION CONFLICT PREVENTION ────────────────
            # When ML auto-rebalancing is ON, disable Karpenter's native consolidation
            # (WhenEmptyOrUnderutilized → WhenEmpty) to prevent conflicting provisioning.
            # When turned OFF, restore WhenEmptyOrUnderutilized so Karpenter self-manages.
            if cluster.karpenter_mode is not None:
                # Both ON and OFF → WhenEmpty + consolidateAfter=Never
                # WhenEmpty: Karpenter only removes fully-empty nodes (safe scale-down).
                # Never:     No automatic node replacement — ML rebalancer drives all changes.
                # WhenEmptyOrUnderutilized is NOT used because it causes Karpenter to
                # replace underutilized nodes on its own, which conflicts with our system.
                _target_policy = "WhenEmpty"
                _target_after  = "Never"
                try:
                    from backend.services.karpenter_service import KarpenterService
                    _ksvc = KarpenterService(db, None)
                    _ksvc.patch_consolidation_policy(
                        cluster_id=cluster_id,
                        policy=_target_policy,
                        consolidate_after=_target_after,
                    )
                    logger.info(
                        f"Patched NodePool disruption → consolidationPolicy={_target_policy}, "
                        f"consolidateAfter={_target_after} for {cluster_id} "
                        f"(ML rebalancing {'ON' if auto_rebalancing else 'OFF'})"
                    )
                except Exception as _consol_err:
                    logger.warning(f"Failed to patch consolidation policy: {_consol_err}")
        if auto_rightsizing is not None:
            opt.auto_rightsizing_enabled = bool(auto_rightsizing)
            logger.info(
                f"ClusterOptimizationSettings.auto_rightsizing_enabled → {auto_rightsizing} "
                f"for cluster {cluster_id}"
            )

        # ── SYNC diversify_pools to DB (auto_rebalancer reads from DB, not Redis) ──
        _diversify = updates.get("diversify_pools")
        _diversify_was_enabled = False  # track for immediate re-trigger below
        if _diversify is not None and opt is not None:
            _prev_diversify = bool(getattr(opt, 'diversify_pools', False))
            opt.diversify_pools = bool(_diversify)
            logger.info(f"ClusterOptimizationSettings.diversify_pools → {_diversify} for {cluster_id}")
            # Flag when turning ON (False → True) so we can flush caches immediately
            if bool(_diversify) and not _prev_diversify:
                _diversify_was_enabled = True

        # ── SYNC automation scalar settings to DB ───────────────────────────────
        for _f, _default in [
            ("min_node_count", 1),
            ("scale_down_threshold_pct", 20),
            ("scale_down_stabilization_minutes", 15),
            ("enable_ascp_auto_scaler", False),
            ("check_interval_seconds", 15),
        ]:
            _v = updates.get(_f)
            if _v is not None and opt is not None:
                setattr(opt, _f, type(_default)(_v))

        # ── SYNC auto_stateful_rightsizing_enabled ──────────────────────────────
        _auto_stateful = updates.get("auto_stateful_rightsizing_enabled")
        if _auto_stateful is not None and opt is not None:
            opt.auto_stateful_rightsizing_enabled = bool(_auto_stateful)
            logger.info(
                f"ClusterOptimizationSettings.auto_stateful_rightsizing_enabled → "
                f"{_auto_stateful} for {cluster_id}"
            )

        # ── SYNC StatefulRules (require_approval + max_downscale_percent) ──────
        _sf_req = updates.get("stateful_require_approval")
        _sf_max = updates.get("stateful_max_downscale_pct")
        if _sf_req is not None or _sf_max is not None:
            from backend.models.cluster import StatefulRules
            sf_rules = cluster.stateful_rules
            if sf_rules is None:
                sf_rules = StatefulRules(cluster_id=cluster_id)
                db.add(sf_rules)
            if _sf_req is not None:
                sf_rules.require_approval = bool(_sf_req)
            if _sf_max is not None:
                sf_rules.max_downscale_percent = int(_sf_max)

        db.commit()

    # 3. Persist full config to Redis (strategy, families, UI settings, etc.)
    try:
        from backend.core.redis_client import get_redis_client as _get_redis
        _redis = _get_redis()
        _cfg_key = f"karpenter_config:{cluster_id}"
        _existing = _json.loads(_redis.get(_cfg_key) or '{}')
        _existing.update(updates)
        _redis.set(_cfg_key, _json.dumps(_existing), ex=86400)  # BUG-6 fix: 24h TTL prevents unbounded growth
    except Exception as _e:
        logger.warning(f"Could not persist Karpenter config to Redis: {_e}")

    # 4. Immediate re-evaluation when Diversify Spot Pools is turned ON.
    #    Clear cooldown caches so the next auto_rebalancer cycle (≤15s) re-picks
    #    pools using the diversity filter right away instead of waiting 30-65 min.
    if _diversify_was_enabled:
        try:
            from backend.core.redis_client import get_redis_client as _get_redis_d
            _redis_d = _get_redis_d()

            # Clear Karpenter NodePool update cooldown so next cycle refreshes NodePool
            # with diversity-filtered pool rankings immediately.
            _np_cooldown_key = f"spot:karpenter:nodepool_updated:{cluster_id}"
            _redis_d.delete(_np_cooldown_key)

            # Clear the global ML pool ranking caches for this cluster's region
            # so the next rank_pools_for_size() call recomputes fresh rankings.
            # Two keys: tier-1 global cache (65-min TTL) + legacy per-request cache.
            _cluster_region = cluster.region or "ap-south-1"
            _redis_d.delete(f"global_pool_rankings:{_cluster_region}")
            _redis_d.delete("ascpai:pool_rankings")

            logger.info(
                f"[karpenter_routes] diversify_pools enabled for {cluster_id}: "
                f"cleared NodePool cooldown + global ranking cache — "
                f"next auto_rebalancer cycle will re-pick diverse pools immediately"
            )
        except Exception as _div_err:
            logger.warning(f"[karpenter_routes] diversify_pools cache flush failed: {_div_err}")

    return {"cluster_id": cluster_id, "updated_fields": list(updates.keys()), "success": True}


@router.post(
    "/deploy",
    summary="Deploy Karpenter to selected clusters",
    description="Triggers Karpenter installation and NodePool creation. Defaults to dry_run (Insights) mode."
)
def deploy_karpenter(
    payload: KarpenterDeployRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Kicks off Karpenter deployment:
    1. Install Karpenter controller (Helm) — in dry_run or auto mode
    2. Create IAM roles (dry_run mode skips ec2:RunInstances permission)
    3. Deploy NodePool configs
    4. Set up monitoring
    5. Persist karpenter_mode on each cluster
    """
    deploy_mode = payload.mode.value  # "dry_run" or "auto"
    logger.info(f"Deploying Karpenter in {deploy_mode} mode to {len(payload.cluster_configs)} clusters by user {current_user.id}")

    deployment_id = str(uuid.uuid4())

    # Persist mode on each target cluster
    for config in payload.cluster_configs:
        cluster = db.query(Cluster).filter(Cluster.id == config.cluster_id).first()
        if cluster:
            cluster.karpenter_mode = KarpenterMode(deploy_mode)
    db.commit()

    return {
        "deployment_id": deployment_id,
        "status": "deploying",
        "mode": deploy_mode,
        "clusters": [c.cluster_id for c in payload.cluster_configs],
        "gradual_rollout": payload.gradual_rollout,
        "estimated_time_minutes": 5,
    }


@router.post(
    "/toggle/{cluster_id}",
    summary="Pause or resume Karpenter on a cluster",
    description="Toggle Karpenter active state without removing configuration"
)
def toggle_karpenter(
    cluster_id: str,
    body: KarpenterToggleRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Pause / resume Karpenter for a single cluster."""
    action = "resumed" if body.enabled else "paused"
    logger.info(f"Karpenter {action} for cluster {cluster_id} by user {current_user.id}")
    return {"cluster_id": cluster_id, "is_active": body.enabled, "action": action}


@router.get(
    "/activity",
    summary="Get recent Karpenter activity",
    description="Returns recent optimization events across managed clusters"
)
def get_karpenter_activity(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Live activity feed for the Karpenter dashboard."""
    # Stub data — includes both dry_run and auto event types
    sample_events = [
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=3)).isoformat(),
            "cluster": "prod-web",
            "type": "consolidation",
            "mode": "auto",
            "title": "Consolidated 3 under-utilized nodes",
            "details": [
                "m5.xlarge (38% util) → Terminated",
                "m5.xlarge (35% util) → Terminated",
                "m5.xlarge (42% util) → Terminated",
                "Moved pods to c6i.large + m6i.large",
            ],
            "savings_daily": 142,
            "utilization_after": 72,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=8)).isoformat(),
            "cluster": "prod-web",
            "type": "recommendation",
            "mode": "dry_run",
            "title": "Would consolidate 2 nodes → 1",
            "details": [
                "m5.xlarge (28% util) → Would terminate",
                "c5.large (32% util) → Would terminate",
                "Pods would fit on single c6i.xlarge",
            ],
            "potential_savings_daily": 98,
            "action_required": True,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=12)).isoformat(),
            "cluster": "prod-api",
            "type": "instance_switch",
            "mode": "auto",
            "title": "Switched to Graviton instance",
            "details": ["r5.2xlarge → r6g.2xlarge (ARM64)"],
            "savings_daily": 68,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
            "cluster": "prod-api",
            "type": "right_size_suggestion",
            "mode": "dry_run",
            "title": "Would right-size i-0abc123",
            "details": [
                "Current: m5.4xlarge ($560/mo, CPU 18%, Mem 22%)",
                "Suggested: m5.xlarge ($140/mo)",
                "Savings: $420/mo",
                "Pod constraints: All satisfied",
            ],
            "potential_savings_monthly": 420,
            "action_required": True,
        },
        {
            "id": str(uuid.uuid4()),
            "timestamp": (datetime.utcnow() - timedelta(minutes=18)).isoformat(),
            "cluster": "prod-web",
            "type": "spot_replacement",
            "mode": "auto",
            "title": "Spot replacement (interruption)",
            "details": [
                "m5.large spot interrupted (AWS reclaiming)",
                "Drained pods gracefully",
                "Replaced with c6i.large spot (different AZ)",
            ],
            "zero_downtime": True,
            "reschedule_seconds": 12,
        },
    ]
    # Query audit logs for real karpenter events from DB
    from backend.models.audit_log import AuditLog

    real_events = []
    try:
        logs = db.query(AuditLog).filter(
            AuditLog.event.in_(["karpenter_consolidation", "karpenter_resize", "spot_replacement", "node_drain", "node_provision"])
        ).order_by(AuditLog.timestamp.desc()).limit(20).all()

        for log in logs:
            real_events.append({
                "id": str(log.id),
                "timestamp": log.timestamp.isoformat() if log.timestamp else datetime.utcnow().isoformat(),
                "cluster": log.resource or "unknown",
                "type": log.event.replace("karpenter_", ""),
                "mode": "auto",
                "title": log.event.replace("_", " ").title(),
                "details": [],
                "savings_daily": 0,
                "zero_downtime": True,
            })
    except Exception:
        pass

    events = real_events if real_events else sample_events
    return {"events": events, "total": len(events)}


@router.get(
    "/stats",
    summary="Get Karpenter performance stats",
    description="Weekly/monthly performance KPIs for the dashboard"
)
def get_karpenter_stats(
    period: str = Query("week", description="week | month | all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Performance KPIs for the live Karpenter dashboard."""
    from backend.models.instance import Instance

    # Get all clusters (for now, we'll get all clusters)
    # In production, filter by user's organization
    clusters = db.query(Cluster).all()

    total_nodes = sum(c.node_count or 0 for c in clusters)
    total_spot = sum(c.spot_count or 0 for c in clusters)
    total_on_demand = sum(c.on_demand_node_count or 0 for c in clusters)

    # Calculate spot coverage percentage
    spot_coverage_pct = round((total_spot / total_nodes * 100) if total_nodes > 0 else 0, 1)

    # Calculate potential savings (on-demand nodes that could be spot)
    total_potential_savings = sum(c.potential_savings_monthly or 0 for c in clusters)

    # Calculate realized savings (current spot instances)
    total_realized_savings = sum(c.realized_savings_monthly or 0 for c in clusters)

    # Calculate average CPU utilization from RUNNING instances only
    instances = db.query(Instance).filter(
        Instance.cluster_id.in_([c.id for c in clusters]),
        Instance.state.in_(['running', 'pending']),
    ).all() if clusters else []

    avg_cpu = round(sum(i.cpu_util or 0 for i in instances) / len(instances) if instances else 0, 1)

    # Calculate savings percentage
    # If we have on-demand instances, show how much we could save
    if total_on_demand > 0:
        # Typical spot vs on-demand savings is ~70%
        avg_reduction_pct = 70
    else:
        # If already all spot, we're saving maximum
        avg_reduction_pct = 0

    return {
        "period": period,
        "avg_utilization_pct": avg_cpu,
        "prev_utilization_pct": avg_cpu,  # Would need historical data
        "optimizations_count": 0,  # Would track from rebalancing_actions
        "cost_saved": round(total_realized_savings, 2),
        "spot_coverage_pct": spot_coverage_pct,
        "clusters": [
            {
                "id": c.id,
                "name": c.name,
                "potential_savings": round(c.potential_savings_monthly or 0, 2),
                "spot_coverage": round((c.spot_count / c.node_count * 100) if c.node_count > 0 else 0, 1)
            }
            for c in clusters
        ],
        "cost_trend": [],  # Would need historical cost data
        "instance_distribution": {
            "before": {"on_demand": total_on_demand + total_spot, "spot": 0},
            "after": {"on_demand": total_on_demand, "spot": total_spot},
        },
        "total_saved": round(total_realized_savings, 2),
        "avg_reduction_pct": avg_reduction_pct,
    }


@router.get(
    "/recommendations",
    summary="Get all dry-run recommendations",
    description="Returns pending Karpenter recommendations that need manual approval (dry_run mode only)"
)
def get_karpenter_recommendations(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    status_filter: Optional[str] = Query(None, description="pending | applied | dismissed"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get rightsizing recommendations for cluster nodes.
    When cluster_id is specified, returns ALL instances (spot and on-demand) for that cluster
    regardless of karpenter_mode — giving the monitoring tab real node data.
    Without cluster_id filter, only dry_run clusters are included.
    """
    from backend.models.instance import Instance

    # On-demand pricing lookup (approximate $/hour for common instance types)
    ONDEMAND_HOURLY: Dict[str, float] = {
        't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416, 't3.large': 0.0832,
        't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
        't3a.medium': 0.0376, 't3a.large': 0.0752, 't3a.xlarge': 0.1504,
        'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768,
        'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384, 'm6i.4xlarge': 0.768,
        'm6a.large': 0.0864, 'm6a.xlarge': 0.1728, 'm6a.2xlarge': 0.3456,
        'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68,
        'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34, 'c6i.4xlarge': 0.68,
        'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008,
        'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504,
        'i3.large': 0.156, 'i3.xlarge': 0.312, 'i3.2xlarge': 0.624,
    }

    # Build cluster query
    if cluster_id:
        # For a specific cluster: include it regardless of karpenter_mode
        query = db.query(Cluster).filter(Cluster.id == cluster_id)
    else:
        # Global view: only dry_run clusters show pending recommendations
        query = db.query(Cluster).filter(Cluster.karpenter_mode == KarpenterMode.DRY_RUN)

    target_clusters = query.all()

    recommendations = []
    total_potential_savings = 0

    for cluster in target_clusters:
        # Active instances only — terminated rows must not appear in rightsizing analysis
        instances = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.state.in_(['running', 'pending']),
        ).all()

        # Load WorkloadInspector classification for this cluster (node_name → status string)
        _node_classification: Dict[str, str] = {}
        try:
            import json as _json
            from backend.core.redis_client import get_redis_client as _get_redis
            _redis = _get_redis()
            _raw = _redis.get(f"spot:node_classification:{cluster.id}")
            if _raw:
                _node_classification = _json.loads(_raw)
        except Exception:
            pass  # No classification available — use default below

        # Load cluster's assigned template constraints for recommendation filtering
        # Template fields: allowed_families, allowed_zones, architectures, vcpu/memory bounds
        _tpl_allowed_families = None
        _tpl_allowed_azs = None
        _tpl_architectures = ["amd64", "arm64"]
        _tpl_max_vcpu = 128
        _tpl_max_mem = 512
        try:
            from backend.models.node_template import ClusterTemplateMapping, NodeTemplateVersion as _NTV
            _mapping = db.query(ClusterTemplateMapping).filter(
                ClusterTemplateMapping.cluster_id == cluster.id,
                ClusterTemplateMapping.is_default == True
            ).first()
            if _mapping and _mapping.version_id:
                _tv = db.query(_NTV).filter(_NTV.id == _mapping.version_id).first()
                if _tv and _tv.constraints_json:
                    _c = _tv.constraints_json
                    _tpl_architectures = _c.get('architectures') or ["amd64", "arm64"]
                    _tpl_max_vcpu = _c.get('max_vcpu') or 128
                    _tpl_max_mem = _c.get('max_memory') or 512
                    _tpl_allowed_families = _c.get('allowed_families') or None
                    _tpl_allowed_azs = _c.get('allowed_zones') or None
                    logger.debug(
                        f"Applying template '{_mapping.template_id}' constraints to cluster {cluster.id}: "
                        f"families={_tpl_allowed_families}, azs={_tpl_allowed_azs}, "
                        f"arch={_tpl_architectures}, max_vcpu={_tpl_max_vcpu}, max_mem={_tpl_max_mem}"
                    )
        except Exception as _te:
            logger.debug(f"No active template for cluster {cluster.id}: {_te}")

        # Instantiate PoolRankingService once per cluster (not per instance) —
        # ONNX model loading is expensive and increments the circuit breaker on failure.
        _pool_ranking_svc = None
        try:
            from backend.services.pool_ranking_service import PoolRankingService as _PRS, NodeTemplate as _NT
            from backend.core.redis_client import get_redis_client as _get_redis_svc
            _pool_ranking_svc = _PRS(db, _get_redis_svc())
        except Exception:
            pass

        for instance in instances:
            instance_type = instance.instance_type or 'unknown'
            # instance.lifecycle is an InstanceLifecycle enum — use .value to get the string
            lifecycle_raw = instance.lifecycle
            lifecycle = (lifecycle_raw.value if hasattr(lifecycle_raw, 'value') else str(lifecycle_raw or 'on-demand')).lower()
            is_spot = lifecycle == 'spot'

            # Calculate real monthly cost from pricing table
            hourly_od = ONDEMAND_HOURLY.get(instance_type, 0.096)  # default ~m5.large
            monthly_od = round(hourly_od * 730, 2)

            # Determine node_type from WorkloadInspector first (K8s-aware classification)
            # K8s node name often matches the EC2 instance_id (i-xxxxxxxxx)
            _cached_status = _node_classification.get(instance.instance_id or "")
            if _cached_status == "STATEFUL_PROTECTED" or _cached_status == "DRAIN_UNSAFE":
                node_type = "stateful"
            else:
                # STATELESS_ELIGIBLE, SYSTEM_PROTECTED, or no cache → stateless
                node_type = "stateless"

            cpu_pct = round(instance.cpu_util or 0.0, 1)
            mem_pct = round(instance.memory_util or 0.0, 1)

            # ── Bin-pack: find smaller right-sized instance ───────────────
            recommended_type, resize_savings = _bin_pack_instance(
                instance_type, cpu_pct, mem_pct, buffer_pct=30.0,
                region=cluster.region, redis_client=_redis
            )
            # If template restricts allowed families, validate the bin-packed result.
            # If the recommended type's family is not in allowed_families, fall back
            # to the cheapest allowed-family type that fits, or keep current type.
            if _tpl_allowed_families and recommended_type != instance_type:
                _rec_family = recommended_type.split(".")[0]
                if _rec_family not in _tpl_allowed_families:
                    # Try bin-packing restricted to allowed families
                    _specs = INSTANCE_SPECS.get(instance_type)
                    if _specs:
                        _c_vcpu, _c_mem, _c_hr = _specs
                        _buf = 1.3
                        _req_vcpu = max(0.25, (_c_vcpu * cpu_pct / 100.0) * _buf)
                        _req_mem  = max(0.5,  (_c_mem  * mem_pct / 100.0) * _buf)
                        _filtered_candidates = sorted(
                            [(t, v, m, h) for t, (v, m, h) in INSTANCE_SPECS.items()
                             if h < _c_hr and t.split(".")[0] in _tpl_allowed_families],
                            key=lambda x: x[3]
                        )
                        recommended_type = instance_type  # default: keep current
                        resize_savings = 0.0
                        for _t, _v, _m, _h in _filtered_candidates:
                            if _v >= _req_vcpu and _m >= _req_mem:
                                recommended_type = _t
                                resize_savings = round((_c_hr - _h) * 730, 2)
                                break
            hourly_rec = INSTANCE_SPECS.get(recommended_type, (None, None, hourly_od))[2]

            # ── Spot pool suggestion for stateless nodes ──────────────────
            spot_pool = None
            if node_type == "stateless" and not is_spot and _pool_ranking_svc is not None:
                try:
                    _rec_specs = INSTANCE_SPECS.get(recommended_type)
                    _max_vcpu = max(4, _rec_specs[0] * 2) if _rec_specs else 8
                    _max_mem  = max(8, _rec_specs[1] * 2) if _rec_specs else 16
                    # Merge per-instance size constraints with template-level constraints
                    _combined_max_vcpu = min(_max_vcpu, _tpl_max_vcpu)
                    _combined_max_mem  = min(_max_mem,  _tpl_max_mem)
                    _pools = _pool_ranking_svc.rank_pools(
                        node_template=_NT(
                            architecture=_tpl_architectures,
                            vcpu_range=(1, _combined_max_vcpu),
                            memory_range=(1, _combined_max_mem),
                            allowed_families=_tpl_allowed_families,
                            allowed_azs=_tpl_allowed_azs,
                        ),
                        region=getattr(cluster, 'region', None) or "ap-south-1",
                        limit=5
                    )
                    if _pools:
                        _p = _pools[0]
                        spot_pool = {
                            "instance_type": _p.pool.instance_type,
                            "az": _p.pool.az,
                            "spot_price_hourly": round(_p.pool.spot_price, 4),
                            "risk_score": round(_p.risk_probability, 3),
                            "predicted_savings_pct": round(_p.predicted_savings * 100),
                        }
                except Exception:
                    pass

            # ── Determine direction: upsize vs downsize ───────────────────
            is_upsize = (resize_savings < 0 and recommended_type != instance_type)

            # ── Compute combined savings ──────────────────────────────────
            if is_spot:
                monthly_current = round(hourly_od * 730 * 0.3, 2)
                potential_savings = 0.0
                savings_pct = 0
                reason = "Already running on spot — lifecycle optimized"
                recommended_type = instance_type  # No lifecycle change needed
            elif is_upsize:
                # Over-utilised: upsize needed — surface as a risk alert, not a savings opportunity
                monthly_current = monthly_od
                potential_savings = resize_savings  # negative (cost increase)
                savings_pct = 0
                reason = (f"⚠ Node over-utilised ({cpu_pct}% CPU / {mem_pct}% mem) — "
                          f"upsize {instance_type}→{recommended_type} recommended to maintain headroom")
            elif node_type == "stateless":
                monthly_current = monthly_od
                if spot_pool and spot_pool["spot_price_hourly"] > 0:
                    # Combined: downsize OD + migrate to spot pool
                    target_hourly = spot_pool["spot_price_hourly"]
                    potential_savings = max(0.0, round((hourly_od - target_hourly) * 730 + resize_savings, 2))
                    savings_pct = round(potential_savings / monthly_od * 100) if monthly_od > 0 else 70
                    reason = (f"Downsize to {recommended_type} + migrate to "
                              f"{spot_pool['instance_type']} spot ({spot_pool['predicted_savings_pct']}% savings)")
                else:
                    potential_savings = max(resize_savings, round(monthly_od * 0.7, 2))
                    savings_pct = round(potential_savings / monthly_od * 100) if monthly_od > 0 else 70
                    reason = (f"Downsize {instance_type}→{recommended_type} and convert to spot"
                              if recommended_type != instance_type
                              else "Convert on-demand to spot for savings")
            else:
                # Stateful: on-demand right-sizing only (no spot)
                monthly_current = monthly_od
                potential_savings = resize_savings  # Only resize savings, no spot
                savings_pct = round(potential_savings / monthly_od * 100) if monthly_od > 0 and potential_savings > 0 else 0
                reason = (f"Resize {instance_type}→{recommended_type} on-demand (stateful — no spot migration)"
                          if recommended_type != instance_type
                          else "Already right-sized for current workload")

            # EV score and impact
            ev_pct = min(99, savings_pct) if savings_pct > 0 else 0
            if is_upsize:
                impact = "Critical"   # Over-utilised → alert priority
            elif resize_savings > 10:
                impact = "High"
            else:
                impact = "Neutral"

            recommendations.append({
                "id": f"rec-{instance.id}",
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                "instance_id": instance.instance_id,
                "current_type": instance_type,
                "recommended_type": recommended_type,        # REAL bin-packed type
                "current_lifecycle": lifecycle,
                "recommended_lifecycle": "spot" if node_type == "stateless" else lifecycle,
                "cpu": cpu_pct,
                "mem": mem_pct,
                "current_cost_monthly": monthly_current,
                "recommended_cost_monthly": round(hourly_rec * 730 * (0.3 if node_type == "stateless" else 1.0), 2),
                "potential_savings": potential_savings,      # Negative if upsize
                "savings_pct": savings_pct,
                "resize_savings": resize_savings,           # Savings from bin-packing (negative = upsize)
                "is_upsize": is_upsize,                     # True when node is over-utilised
                "spot_pool": spot_pool,                     # Best spot pool for stateless nodes
                "ev_pct": ev_pct,
                "impact": impact,                           # "Critical" for upsize, "High"/"Neutral" for downsize
                "risk_prob": round((spot_pool["risk_score"] if spot_pool else 0.15) * 100),
                "status": "pending",
                "node_type": node_type,
                "created_at": datetime.utcnow().isoformat(),
                "reason": reason,
            })

            total_potential_savings += potential_savings

    return {
        "recommendations": recommendations,
        "total_count": len(recommendations),
        "pending_count": len([r for r in recommendations if r["status"] == "pending"]),
        "total_potential_savings_monthly": round(total_potential_savings, 2),
        "dry_run_clusters": [
            {
                "cluster_id": c.id,
                "name": c.name,
                "mode": c.karpenter_mode.value if c.karpenter_mode else "standard",
            }
            for c in target_clusters
        ],
    }


@router.post(
    "/apply-recommendation/{recommendation_id}",
    summary="Apply a single dry-run recommendation",
    description="Manually approve and apply a Karpenter recommendation from dry_run mode"
)
def apply_karpenter_recommendation(
    recommendation_id: str,
    payload: KarpenterApplyRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Apply a single Karpenter recommendation.
    This triggers the actual optimization that was previously only simulated in dry_run mode.
    """
    logger.info(f"Applying Karpenter recommendation {recommendation_id} by user {current_user.id}")

    # ── STATEFUL PATH: queue CORDON → DRAIN → TERMINATE for OD node resize ──
    if payload.is_stateful:
        from backend.models.instance import Instance
        from backend.models.agent_action import AgentAction, AgentActionType
        from backend.models.cluster import StatefulRules

        inst_id = payload.instance_id or recommendation_id.replace("rec-", "")
        # Look up instance by instance_id (EC2 id) or by DB id
        inst = db.query(Instance).filter(Instance.instance_id == inst_id).first()
        if inst is None:
            inst = db.query(Instance).filter(Instance.id == inst_id).first()

        if inst is None:
            raise HTTPException(status_code=404, detail=f"Instance {inst_id} not found")

        cluster_id = inst.cluster_id

        # Check require_approval gate
        sf_rules = db.query(StatefulRules).filter(StatefulRules.cluster_id == cluster_id).first()
        if sf_rules and sf_rules.require_approval:
            return {
                "recommendation_id": recommendation_id,
                "status": "pending_approval",
                "instance_id": inst_id,
                "recommended_type": payload.recommended_type,
                "message": (
                    "Stateful resize requires manual approval (require_approval=True). "
                    "Disable 'Require Approval' in Configuration → Stateful Node Policy to apply directly."
                ),
            }

        # Queue CORDON → DRAIN → TERMINATE
        cordon_action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.CORDON_NODE,
            payload={
                "instance_id": inst_id,
                "node_name": inst.node_name,
                "stateful_resize": True,
                "reason": f"stateful_rightsizing: {inst.instance_type} → {payload.recommended_type}",
            },
        )
        drain_action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.DRAIN_NODE,
            payload={
                "instance_id": inst_id,
                "node_name": inst.node_name,
                "ignore_daemonsets": True,
                "grace_period_seconds": 120,
                "stateful_resize": True,
            },
        )
        terminate_action = AgentAction(
            cluster_id=cluster_id,
            action_type=AgentActionType.TERMINATE_NODE,
            payload={
                "instance_id": inst_id,
                "node_name": inst.node_name,
                "recommended_type": payload.recommended_type,
                "stateful_resize": True,
                # TASK-1.1: termination_mode replaces decrement_asg boolean.
                # stateful resize uses "replacement" mode: detach-not-decrement.
                "termination_mode": "replacement",
                "reason": f"stateful_rightsizing: {inst.instance_type} → {payload.recommended_type}",
            },
        )
        db.add(cordon_action)
        db.add(drain_action)
        db.add(terminate_action)
        db.commit()

        logger.info(
            f"Queued CORDON+DRAIN+TERMINATE for stateful node {inst_id} "
            f"({inst.instance_type} → {payload.recommended_type}) on cluster {cluster_id}"
        )
        return {
            "recommendation_id": recommendation_id,
            "status": "queued",
            "action": "stateful_resize",
            "instance_id": inst_id,
            "recommended_type": payload.recommended_type,
            "message": (
                f"CORDON → DRAIN → TERMINATE queued for {inst_id}. "
                f"After termination the ASG will launch a replacement node. "
                f"Update your launch template to {payload.recommended_type} for the new node to be right-sized."
            ),
            "applied_by": current_user.email,
            "applied_at": datetime.utcnow().isoformat(),
        }

    # ── STATELESS / DEFAULT PATH ─────────────────────────────────────────────
    # Directly update Karpenter NodePool with the recommended type via K8s API,
    # then rely on the auto_rebalancer for CORDON+DRAIN+TERMINATE.
    from backend.models.instance import Instance

    inst_id = payload.instance_id or recommendation_id.replace("rec-", "")
    inst = db.query(Instance).filter(Instance.instance_id == inst_id).first()
    if inst is None:
        inst = db.query(Instance).filter(Instance.id == inst_id).first()

    if inst:
        cluster_id = inst.cluster_id
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        _karpenter_active = cluster and cluster.karpenter_mode is not None

        if _karpenter_active:
            # Karpenter cluster: directly update NodePool with recommended type
            try:
                from backend.services.karpenter_service import KarpenterService
                _ksvc = KarpenterService(db, None)
                _result = _ksvc.add_allowed_instance_type(
                    cluster_id=cluster_id,
                    instance_type=payload.recommended_type,
                )
                if _result:
                    return {
                        "recommendation_id": recommendation_id,
                        "status": "applied",
                        "action": "patch_nodepool",
                        "instance_id": inst_id,
                        "recommended_type": payload.recommended_type,
                        "spot_pool": payload.spot_pool,
                        "message": f"NodePool updated — Karpenter will provision {payload.recommended_type}.",
                        "applied_by": current_user.email,
                        "applied_at": datetime.utcnow().isoformat(),
                    }
                else:
                    return {
                        "recommendation_id": recommendation_id,
                        "status": "failed",
                        "message": f"Failed to update NodePool with {payload.recommended_type}.",
                    }
            except Exception as _kp_err:
                return {
                    "recommendation_id": recommendation_id,
                    "status": "failed",
                    "message": f"NodePool update error: {str(_kp_err)[:200]}",
                }

    return {
        "recommendation_id": recommendation_id,
        "status": "applying",
        "action": "consolidation",
        "estimated_completion_seconds": 120,
        "message": f"Applying recommendation: {payload.recommended_type}",
        "applied_by": current_user.email,
        "applied_at": datetime.utcnow().isoformat(),
    }


@router.post(
    "/apply-recommendations/batch",
    summary="Apply multiple dry-run recommendations at once",
    description="Bulk apply multiple Karpenter recommendations"
)
def apply_karpenter_recommendations_batch(
    payload: KarpenterBatchApplyRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Bulk apply multiple Karpenter recommendations.
    Useful for applying all recommendations at once or applying a filtered set.
    """
    logger.info(f"Batch applying {len(payload.instance_ids)} Karpenter recommendations by user {current_user.id}")

    # In production, this would:
    # 1. Validate all recommendations
    # 2. Check for conflicts (e.g., recommendations affecting same nodes)
    # 3. Apply them in optimal order
    # 4. Return a job ID for tracking progress

    job_id = str(uuid.uuid4())

    return {
        "job_id": job_id,
        "status": "processing",
        "total_recommendations": len(payload.instance_ids),
        "recommendations_queued": len(payload.instance_ids),
        "estimated_completion_minutes": 5,
        "message": f"Batch apply job created for {len(payload.instance_ids)} recommendations",
        "applied_by": current_user.email,
        "started_at": datetime.utcnow().isoformat(),
    }


@router.patch(
    "/mode/{cluster_id}",
    summary="Update Karpenter mode for a cluster",
    description="Switch between dry_run and auto mode for a specific cluster"
)
def update_karpenter_mode(
    cluster_id: str,
    payload: KarpenterModeUpdateRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update Karpenter mode for a specific cluster.
    - dry_run: Karpenter only generates recommendations, no automatic actions
    - auto: Karpenter automatically optimizes based on policies
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    if cluster.karpenter_mode is None:
        raise HTTPException(
            status_code=400,
            detail=f"Karpenter is not deployed on cluster {cluster_id}. Deploy Karpenter first."
        )

    old_mode = cluster.karpenter_mode.value
    new_mode = payload.mode.value

    if old_mode == new_mode:
        return {
            "cluster_id": cluster_id,
            "mode": new_mode,
            "message": f"Cluster already in {new_mode} mode",
            "changed": False
        }

    # Update the mode
    cluster.karpenter_mode = KarpenterMode(new_mode)
    db.commit()

    logger.info(f"Karpenter mode changed from {old_mode} to {new_mode} for cluster {cluster_id} by user {current_user.id}")

    # In production, this would also:
    # 1. Update Karpenter controller config in K8s
    # 2. Update IAM permissions (dry_run doesn't need ec2:RunInstances)
    # 3. Clear pending recommendations if switching from dry_run to auto
    # 4. Send notification to team

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "old_mode": old_mode,
        "new_mode": new_mode,
        "mode": new_mode,
        "changed": True,
        "message": f"Successfully switched from {old_mode} to {new_mode} mode",
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": current_user.email,
        "pending_recommendations_count": 0 if new_mode == "auto" else None,
    }


# ============================================================================
# Execution Plan & History Endpoints (used by RightSizingDashboard)
# ============================================================================


@router.get(
    "/execution-plan",
    summary="Get pending rightsizing execution plan",
    description="Returns PENDING/APPROVED rightsizing proposals as the execution plan"
)
def get_execution_plan(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns pending and approved rightsizing proposals as the execution plan.
    Used by the RightSizingDashboard Execution Plan tab.
    """
    try:
        from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus

        query = db.query(RightsizingProposal).filter(
            RightsizingProposal.status.in_([ProposalStatus.PENDING, ProposalStatus.APPROVED])
        )
        if cluster_id:
            query = query.filter(RightsizingProposal.cluster_id == cluster_id)

        proposals = query.order_by(RightsizingProposal.created_at.asc()).all()

        plan_items = []
        for i, p in enumerate(proposals, 1):
            plan_items.append({
                "order": i,
                "node": p.current_pool or f"node-{str(p.id)[:8]}",
                "action": f"{p.current_instance_type} → {p.proposed_instance_type}",
                "est_duration": "~45s",
                "rollback_plan": f"Re-provision {p.current_instance_type} via ASG",
                "status": p.status.value,
                "proposal_id": p.id,
                "monthly_savings": round(p.estimated_monthly_savings, 2),
                "confidence": f"{max(50, round((1.0 - (p.best_pool_risk_score or 0.3)) * 100))}%",
            })

        return {
            "plan": plan_items,
            "total": len(plan_items),
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching execution plan: {e}")
        return {"plan": [], "total": 0, "generated_at": datetime.utcnow().isoformat()}


@router.get(
    "/history",
    summary="Get rightsizing action history",
    description="Returns EXECUTED/FAILED rightsizing proposals as the action history"
)
def get_rightsizing_history(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns executed and failed rightsizing proposals for the history tab.
    Used by the RightSizingDashboard History tab.
    """
    try:
        from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus

        query = db.query(RightsizingProposal).filter(
            RightsizingProposal.status.in_([ProposalStatus.EXECUTED, ProposalStatus.FAILED])
        )
        if cluster_id:
            query = query.filter(RightsizingProposal.cluster_id == cluster_id)

        proposals = query.order_by(RightsizingProposal.executed_at.desc()).limit(50).all()

        history_items = []
        for p in proposals:
            executed_at = p.executed_at or p.evaluated_at or p.created_at
            history_items.append({
                "executed_at": executed_at.strftime("%b %d, %I:%M %p") if executed_at else "Unknown",
                "node": p.current_pool or f"node-{str(p.id)[:8]}",
                "before": p.current_instance_type,
                "after": p.proposed_instance_type,
                "time_taken": "~45s",
                "status": "Success" if p.status == ProposalStatus.EXECUTED else "Failed",
                "monthly_savings": round(p.estimated_monthly_savings, 2),
            })

        # Aggregate KPIs
        executed_count = sum(1 for p in proposals if p.status == ProposalStatus.EXECUTED)
        total_count = len(proposals)
        success_rate = round((executed_count / total_count * 100), 1) if total_count > 0 else 0
        net_savings = sum(
            p.estimated_monthly_savings for p in proposals
            if p.status == ProposalStatus.EXECUTED
        )

        return {
            "history": history_items,
            "total": len(history_items),
            "kpis": {
                "resizes_this_month": total_count,
                "net_savings_monthly": round(net_savings, 2),
                "success_rate_pct": success_rate,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching rightsizing history: {e}")
        return {
            "history": [],
            "total": 0,
            "kpis": {"resizes_this_month": 0, "net_savings_monthly": 0, "success_rate_pct": 0},
            "generated_at": datetime.utcnow().isoformat(),
        }


# ============================================================================
# Decision Engine v3 API Endpoints
# ============================================================================


@router.get("/v3/substitute/{cluster_id}/status")
async def get_substitute_status(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current substitute instance status for the cluster.

    Returns: state (IDLE/PREWARMING/READY/ACTIVE/RELEASING),
    deployed instance details, cost drift info, and prewarm timeout status.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.substitute_manager import SubstituteManager

        redis = get_redis_client()
        sub_mgr = SubstituteManager(db, redis)

        state = sub_mgr.get_state(cluster_id)
        metadata = sub_mgr._get_metadata(cluster_id)
        cost_drift = sub_mgr.check_cost_drift(cluster_id)

        # Check prewarm timeout
        timeout_key = f"spot:substitute:prewarm_timeout:{cluster_id}"
        timeout_ttl = redis.ttl(timeout_key)

        return {
            "cluster_id": cluster_id,
            "state": state.value if hasattr(state, 'value') else str(state),
            "metadata": metadata,
            "cost_drift": cost_drift,
            "prewarm_timeout_remaining": max(0, timeout_ttl) if timeout_ttl and timeout_ttl > 0 else None,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get substitute status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SubstituteDeployRequest(BaseModel):
    """Request to deploy a substitute instance."""
    target_node_name: str


@router.post("/v3/substitute/{cluster_id}/deploy")
async def deploy_substitute(
    cluster_id: str,
    payload: SubstituteDeployRequest,
    db: Session = Depends(get_db)
):
    """
    Deploy substitute instance for target node.

    Validates target node is STATELESS_ELIGIBLE before deploying.
    Selects top 3 candidates based on optimization mode.
    Each candidate validated via DryRun API before acceptance.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.substitute_manager import SubstituteManager

        redis = get_redis_client()
        sub_mgr = SubstituteManager(db, redis)

        result = sub_mgr.deploy_substitute(
            cluster_id=cluster_id,
            target_node_name=payload.target_node_name
        )

        return result
    except Exception as e:
        logger.error(f"Failed to deploy substitute for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v3/cooldown/{cluster_id}")
async def get_cooldown_status(cluster_id: str):
    """
    Get cluster cooldown status for UI display.

    Returns: whether cooldown is active, remaining seconds/minutes,
    and pool-level cooldowns if any exist.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.cooldown_controller import CooldownController

        redis = get_redis_client()
        cooldown = CooldownController(redis)

        cluster_status = cooldown.get_cluster_cooldown_status(cluster_id)

        # Check mode switch dwell cooldown
        dwell_key = f"spot:cooldown:mode_switch:{cluster_id}"
        dwell_ttl = redis.ttl(dwell_key)

        return {
            "cluster_id": cluster_id,
            "cluster_cooldown": cluster_status,
            "mode_switch_cooldown": {
                "active": dwell_ttl is not None and dwell_ttl > 0,
                "remaining_seconds": max(0, dwell_ttl) if dwell_ttl and dwell_ttl > 0 else 0
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get cooldown for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Karpenter Install / Uninstall via Agent
# ============================================================================


class KarpenterInstallRequest(BaseModel):
    karpenter_version: str = Field(default="1.0.8", description="Helm chart version to install")
    nodepool_name: str = Field(default="default", description="Name for the default NodePool created after install")


@router.post(
    "/clusters/{cluster_id}/install",
    summary="Queue Karpenter installation via agent",
    description="Creates an INSTALL_KARPENTER AgentAction; the DaemonSet agent runs helm install inside the cluster"
)
def install_karpenter(
    cluster_id: str,
    payload: KarpenterInstallRequest = KarpenterInstallRequest(),
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    if cluster.agent_installed != 'Y':
        raise HTTPException(
            status_code=400,
            detail="Agent must be installed before Karpenter can be installed. Deploy the agent first."
        )

    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

    # Check for an in-flight install action — auto-expire stale ones
    in_flight = db.query(AgentAction).filter(
        AgentAction.cluster_id == cluster_id,
        AgentAction.action_type == AgentActionType.INSTALL_KARPENTER,
        AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP])
    ).first()
    if in_flight:
        if in_flight.expires_at and datetime.utcnow() > in_flight.expires_at:
            logger.warning(
                f"Auto-expiring stuck INSTALL_KARPENTER action {in_flight.id} "
                f"(created {in_flight.created_at}, expired {in_flight.expires_at})"
            )
            in_flight.status = AgentActionStatus.EXPIRED
            in_flight.error_message = "Auto-expired: action was stuck past its expiry time"
            in_flight.completed_at = datetime.utcnow()
            db.commit()
        else:
            raise HTTPException(status_code=409, detail="Karpenter installation already in progress")

    # Pre-flight: patch the agent ClusterRole with secrets/RBAC/Karpenter permissions
    # so helm can store release state in the karpenter namespace without a full agent reinstall.
    if cluster.endpoint and cluster.ca_data:
        try:
            from backend.services.agent_injector import AgentInjectorService
            _injector = AgentInjectorService(db)
            _patch_result = _injector.patch_clusterrole(
                cluster_name=cluster.name,
                cluster_endpoint=cluster.endpoint,
                cluster_ca_data=cluster.ca_data,
                region=cluster.region or "ap-south-1",
            )
            logger.info(f"ClusterRole pre-flight patch: {_patch_result}")
        except Exception as _patch_err:
            logger.warning(f"ClusterRole pre-flight patch failed (non-fatal): {_patch_err}")

    # INSTALL-KARPENTER-01: Derive Karpenter ARNs from known naming convention.
    # KarpenterNodeRole, KarpenterControllerRole, SQS queue, and EventBridge rules
    # are now created in the main full-access-role.yaml CF stack at onboarding time.
    # Backend derives ARNs deterministically — no CF output lookup needed.
    karpenter_iam_role_arn = ""
    karpenter_node_role_arn = ""
    # Karpenter uses the bare cluster name as its INTERRUPTION_QUEUE env var
    # (set via settings.interruptionQueue in Helm). Match that here so the
    # SQS queue our auto-setup creates is always the one Karpenter expects.
    sqs_queue_name = cluster.name
    account_id = ""
    if cluster.account and cluster.account.aws_account_id:
        account_id = cluster.account.aws_account_id
        karpenter_iam_role_arn = (
            f"arn:aws:iam::{account_id}:role/KarpenterControllerRole-{cluster.name}"
        )
        karpenter_node_role_arn = (
            f"arn:aws:iam::{account_id}:role/KarpenterNodeRole-{cluster.name}"
        )
    logger.info(
        f"Karpenter install payload for cluster {cluster.name}: "
        f"sqs_queue_name={sqs_queue_name!r}, "
        f"karpenter_iam_role_arn={karpenter_iam_role_arn!r}, "
        f"karpenter_node_role_arn={karpenter_node_role_arn!r}"
    )

    # AUTO-SETUP: Ensure all Karpenter AWS prerequisites are created before install.
    # This replaces manual CloudFormation deployment — all resources are created
    # automatically: IAM roles, SQS queue, EventBridge rules, OIDC provider.
    # Idempotent — already-existing resources are silently skipped.
    try:
        from backend.services.agent_injector import AgentInjectorService as _Inj
        _inj = _Inj(db)
        _role_arn = (
            cluster.aws_role_arn
            or (cluster.account.role_arn if cluster.account else "")
            or ""
        )
        _ext_id = (
            cluster.aws_external_id
            or (cluster.account.external_id if cluster.account else "")
            or ""
        )
        if _role_arn:
            _creds = _inj._assume_role(
                role_arn=_role_arn,
                external_id=_ext_id,
                region=cluster.region or "ap-south-1",
            )
            if _creds:
                # 1. Register OIDC provider (required for IRSA)
                try:
                    _inj._ensure_oidc_provider_registered(
                        cluster_name=cluster.name,
                        region=cluster.region or "ap-south-1",
                        credentials=_creds,
                    )
                except Exception as _oidc_err:
                    logger.warning(f"OIDC registration pre-install (non-fatal): {_oidc_err}")

                # 2. Create all AWS resources (IAM, SQS, EventBridge) — auto-setup
                try:
                    _inj._ensure_karpenter_aws_prerequisites(
                        cluster_name=cluster.name,
                        region=cluster.region or "ap-south-1",
                        credentials=_creds,
                    )
                    logger.info(f"Karpenter AWS prerequisites ensured for {cluster.name}")
                except Exception as _prereq_err:
                    logger.warning(
                        f"Karpenter prerequisites auto-setup (non-fatal): {_prereq_err}. "
                        f"Will attempt install anyway."
                    )

                # 3. Update trust policy now that role is guaranteed to exist
                try:
                    _inj._update_karpenter_controller_trust_policy(
                        cluster_name=cluster.name,
                        region=cluster.region or "ap-south-1",
                        credentials=_creds,
                    )
                except Exception as _tp_err:
                    logger.warning(f"Trust policy update pre-install (non-fatal): {_tp_err}")

                # 4. Tag subnets/SGs for EC2NodeClass discovery
                try:
                    _inj._tag_karpenter_network_resources(
                        cluster_name=cluster.name,
                        region=cluster.region or "ap-south-1",
                        credentials=_creds,
                    )
                except Exception as _tag_err:
                    logger.warning(f"Network tagging pre-install (non-fatal): {_tag_err}")
    except Exception as _setup_err:
        # Log but don't block install — agent will report any remaining errors
        logger.warning(
            f"Karpenter auto-setup encountered unexpected error (non-blocking): {_setup_err}. "
            f"Proceeding with INSTALL_KARPENTER action queue."
        )

    logger.info(f"Karpenter pre-flight auto-setup complete for cluster {cluster.name}")

    action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.INSTALL_KARPENTER,
        status=AgentActionStatus.PENDING,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        payload={
            "cluster_name": cluster.name,
            "region": cluster.region or "ap-south-1",
            "karpenter_version": payload.karpenter_version,
            "nodepool_name": payload.nodepool_name,
            "karpenter_iam_role_arn": karpenter_iam_role_arn,
            "sqs_queue_name": sqs_queue_name,  # helm settings.interruptionQueue value
            "karpenter_node_role_arn": karpenter_node_role_arn,
        }
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    logger.info(f"Queued INSTALL_KARPENTER action {action.id} for cluster {cluster_id} by user {current_user.email}")

    return {
        "action_id": action.id,
        "status": "queued",
        "message": "Karpenter installation queued. The agent will run helm install inside the cluster.",
        "cluster_id": cluster_id,
        "karpenter_version": payload.karpenter_version,
        "queued_at": datetime.utcnow().isoformat(),
    }


@router.delete(
    "/clusters/{cluster_id}/install",
    summary="Queue Karpenter uninstallation via agent",
    description="Creates an UNINSTALL_KARPENTER AgentAction; the DaemonSet agent runs helm uninstall inside the cluster"
)
def uninstall_karpenter(
    cluster_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    if cluster.agent_installed != 'Y':
        raise HTTPException(status_code=400, detail="Agent must be installed to perform Karpenter uninstall")

    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

    # Check for an in-flight uninstall action — auto-expire stale ones
    in_flight = db.query(AgentAction).filter(
        AgentAction.cluster_id == cluster_id,
        AgentAction.action_type == AgentActionType.UNINSTALL_KARPENTER,
        AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP])
    ).first()
    if in_flight:
        if in_flight.expires_at and datetime.utcnow() > in_flight.expires_at:
            logger.warning(
                f"Auto-expiring stuck UNINSTALL_KARPENTER action {in_flight.id} "
                f"(created {in_flight.created_at}, expired {in_flight.expires_at})"
            )
            in_flight.status = AgentActionStatus.EXPIRED
            in_flight.error_message = "Auto-expired: action was stuck past its expiry time"
            in_flight.completed_at = datetime.utcnow()
            db.commit()
        else:
            raise HTTPException(status_code=409, detail="Karpenter uninstallation already in progress")

    action = AgentAction(
        cluster_id=cluster_id,
        action_type=AgentActionType.UNINSTALL_KARPENTER,
        status=AgentActionStatus.PENDING,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        payload={
            "release_name": "karpenter",
            "namespace": "karpenter",
        }
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    logger.info(f"Queued UNINSTALL_KARPENTER action {action.id} for cluster {cluster_id} by user {current_user.email}")

    # AUTO-CLEANUP: Delete AWS resources created by _ensure_karpenter_aws_prerequisites
    # (SQS queue, EventBridge rules). IAM roles are kept to avoid accidental data loss.
    try:
        from backend.services.agent_injector import AgentInjectorService as _Inj
        _inj = _Inj(db)
        _role_arn = (
            cluster.aws_role_arn
            or (cluster.account.role_arn if cluster.account else "")
            or ""
        )
        _ext_id = (
            cluster.aws_external_id
            or (cluster.account.external_id if cluster.account else "")
            or ""
        )
        if _role_arn:
            _creds = _inj._assume_role(
                role_arn=_role_arn,
                external_id=_ext_id,
                region=cluster.region or "ap-south-1",
            )
            if _creds:
                _inj.cleanup_karpenter_aws_resources(
                    cluster_name=cluster.name,
                    region=cluster.region or "ap-south-1",
                    credentials=_creds,
                )
    except Exception as _cleanup_err:
        logger.warning(f"Karpenter AWS cleanup on uninstall (non-fatal): {_cleanup_err}")

    # Clear karpenter_mode from cluster record
    try:
        cluster.karpenter_mode = None
        db.commit()
    except Exception:
        pass

    return {
        "action_id": action.id,
        "status": "queued",
        "message": "Karpenter uninstallation queued. The agent will run helm uninstall inside the cluster.",
        "cluster_id": cluster_id,
        "queued_at": datetime.utcnow().isoformat(),
    }


@router.get(
    "/clusters/{cluster_id}/install-status",
    summary="Get Karpenter install status for a cluster",
    description="Multi-tier detection: (1) Redis live heartbeat, (2) Server-side K8s API check, (3) AgentAction history"
)
def get_karpenter_install_status(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.models.cluster import Cluster
    from backend.core.redis_client import get_redis_client
    import json as _is_json

    _redis = None
    try:
        _redis = get_redis_client()
    except Exception:
        pass

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # ── Tier 1: Live agent heartbeat data (karpenter:live_status — 60s TTL) ──
    _live_karp_status = None
    if _redis:
        try:
            _live_raw = _redis.get(f"karpenter:live_status:{cluster_id}")
            if _live_raw:
                _live_karp_status = _is_json.loads(_live_raw)
        except Exception:
            pass

    if _live_karp_status:
        _detected = _live_karp_status.get("detected", False)
        _resp = {
            "cluster_id": cluster_id,
            "karpenter_installed": True if _detected else "missing",
            "source": "live_agent",
            "live_status": {
                "pods_running": _live_karp_status.get("pods_running", 0),
                "controller_healthy": _live_karp_status.get("controller_healthy", False),
                "webhook_healthy": _live_karp_status.get("webhook_healthy", False),
                "last_check": _live_karp_status.get("last_check"),
            },
            "last_action": None,
        }
        if not _detected:
            _resp["status"] = "missing"
            _resp["message"] = "Karpenter was installed but pods are no longer running. Reinstall recommended."
        return _resp

    # ── Tier 2: Server-side K8s API pod check (cached 120s) ──
    _k8s_check = None
    _k8s_cache_key = f"karpenter:k8s_check:{cluster_id}"
    if _redis:
        try:
            _k8s_cached = _redis.get(_k8s_cache_key)
            if _k8s_cached:
                _k8s_check = _is_json.loads(_k8s_cached)
        except Exception:
            pass

    if _k8s_check is None:
        # Run live K8s API check — query the cluster for Karpenter pods
        _k8s_check = _server_side_karpenter_check(cluster, db)
        if _redis and _k8s_check:
            try:
                _redis.setex(_k8s_cache_key, 120, _is_json.dumps(_k8s_check))
            except Exception:
                pass

    if _k8s_check and _k8s_check.get("detected"):
        _mode = _k8s_check.get("karpenter_mode", "unknown")
        # Also update DB karpenter_mode if not already set
        if cluster.karpenter_mode is None:
            from backend.models.cluster import KarpenterMode
            try:
                cluster.karpenter_mode = KarpenterMode.AUTO
                db.commit()
            except Exception:
                db.rollback()
        return {
            "cluster_id": cluster_id,
            "karpenter_installed": True,
            "source": "k8s_api",
            "karpenter_mode": _mode,
            "pods_running": _k8s_check.get("pods_running", 0),
            "last_action": None,
            "status": "installed",
            "message": f"Karpenter detected via K8s API ({_k8s_check.get('pods_running', 0)} pods running).",
        }

    # ── Tier 3: AgentAction history ──
    latest = db.query(AgentAction).filter(
        AgentAction.cluster_id == cluster_id,
        AgentAction.action_type.in_([AgentActionType.INSTALL_KARPENTER, AgentActionType.UNINSTALL_KARPENTER])
    ).order_by(AgentAction.created_at.desc()).first()

    if latest:
        action_type = latest.action_type.value
        action_status = latest.status.value

        if action_status in ("PENDING", "PICKED_UP"):
            return {
                "cluster_id": cluster_id,
                "karpenter_installed": None,
                "status": "in_progress",
                "last_action": _format_action(latest),
                "message": f"{'Installing' if action_type == 'INSTALL_KARPENTER' else 'Uninstalling'} Karpenter...",
            }
        elif action_status == "FAILED":
            return {
                "cluster_id": cluster_id,
                "karpenter_installed": False,
                "status": "failed",
                "last_action": _format_action(latest),
                "message": f"Last {action_type.lower().replace('_', ' ')} failed: {latest.error_message or 'unknown error'}",
            }

    # ── Tier 4: K8s check returned not-detected or error ──
    if _k8s_check and _k8s_check.get("error"):
        return {
            "cluster_id": cluster_id,
            "karpenter_installed": False,
            "status": "unknown",
            "last_action": _format_action(latest) if latest else None,
            "message": f"Cannot verify Karpenter status: {_k8s_check['error']}",
            "error": _k8s_check["error"],
        }

    return {
        "cluster_id": cluster_id,
        "karpenter_installed": False,
        "last_action": _format_action(latest) if latest else None,
        "status": "not_installed",
        "message": "Karpenter not detected. Install via the Karpenter Manager.",
    }


def _format_action(action) -> Optional[Dict]:
    """Format an AgentAction record for the response."""
    if not action:
        return None
    return {
        "id": action.id,
        "type": action.action_type.value,
        "status": action.status.value,
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
        "error_message": action.error_message,
        "result": action.result,
    }


def _server_side_karpenter_check(cluster, db) -> Dict[str, Any]:
    """
    Server-side K8s API check for Karpenter pods.
    Queries the cluster's K8s API directly for pods with 'karpenter' in
    the karpenter and kube-system namespaces.
    """
    try:
        from backend.services.karpenter_service import KarpenterService
        from kubernetes import client

        svc = KarpenterService(db=db)
        api_client = svc._get_k8s_client(cluster)
        core_v1 = client.CoreV1Api(api_client)

        karpenter_pods = []
        for ns in ("karpenter", "kube-system"):
            try:
                pods = core_v1.list_namespaced_pod(
                    namespace=ns,
                    label_selector="app.kubernetes.io/name=karpenter",
                    timeout_seconds=10,
                )
                karpenter_pods.extend(pods.items)
            except Exception:
                pass
            if not karpenter_pods:
                try:
                    pods = core_v1.list_namespaced_pod(
                        namespace=ns,
                        timeout_seconds=10,
                    )
                    for pod in pods.items:
                        if "karpenter" in (pod.metadata.name or "").lower():
                            karpenter_pods.append(pod)
                except Exception:
                    pass

        if karpenter_pods:
            running = sum(1 for p in karpenter_pods if p.status and p.status.phase == "Running")
            _mode = cluster.karpenter_mode.value if cluster.karpenter_mode else "auto"
            return {
                "detected": True,
                "pods_running": running,
                "total_pods": len(karpenter_pods),
                "karpenter_mode": _mode,
                "source": "k8s_api",
            }
        else:
            return {
                "detected": False,
                "pods_running": 0,
                "source": "k8s_api",
            }
    except Exception as e:
        logger.warning(f"[karpenter] Server-side K8s check failed for cluster {cluster.id}: {e}")
        return {
            "detected": False,
            "error": str(e),
            "source": "k8s_api_error",
        }


@router.get("/v3/workload-status/{cluster_id}")
async def get_workload_status(cluster_id: str):
    """
    Get current node classification data for the cluster.

    Returns node-by-node classification (STATELESS_ELIGIBLE, STATEFUL_PROTECTED,
    DRAIN_UNSAFE, SYSTEM_PROTECTED) with aggregate counts.
    """
    try:
        from backend.core.redis_client import get_redis_client
        from backend.services.workload_inspector import WorkloadInspector, NodeStatus

        redis = get_redis_client()
        inspector = WorkloadInspector(redis)

        classification = inspector.get_cached_classification(cluster_id)

        if not classification:
            return {
                "cluster_id": cluster_id,
                "classification_available": False,
                "message": "No cached classification. Scan may not have run yet.",
                "nodes": {},
                "counts": {},
                "timestamp": datetime.utcnow().isoformat()
            }

        # Count by status
        counts = {}
        for node_name, status in classification.items():
            counts[status] = counts.get(status, 0) + 1

        eligible_count = counts.get(NodeStatus.STATELESS_ELIGIBLE, 0)
        total_nodes = len(classification)

        return {
            "cluster_id": cluster_id,
            "classification_available": True,
            "nodes": classification,
            "counts": counts,
            "total_nodes": total_nodes,
            "eligible_count": eligible_count,
            "eligible_pct": round(eligible_count / total_nodes * 100, 1) if total_nodes > 0 else 0,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get workload status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# EXEC-08/09: No-Karpenter Spot Mode — ASG MixedInstancesPolicy routes
# =============================================================================
# For clusters that cannot or should not use Karpenter (legacy EKS versions,
# SCP-restricted environments, managed nodegroups with custom lifecycle hooks).
# These routes call SpotASGService which updates the ASG's MixedInstancesPolicy
# directly using the cluster's cross-account IAM role.

class EnableSpotASGPayload(BaseModel):
    nodegroup_name: str = Field(..., description="EKS managed nodegroup name (e.g. 'workers')")
    spot_instance_types: Optional[List[str]] = Field(
        None, description="Override spot instance type list; auto-selected if omitted"
    )
    on_demand_base_capacity: int = Field(
        1, ge=0, description="Minimum on-demand nodes always kept (0 = max spot coverage)"
    )
    spot_percentage: int = Field(
        70, ge=0, le=100, description="% of nodes above base that should be spot (default 70)"
    )


@router.post("/nodegroup/{cluster_id}/enable-spot")
async def enable_spot_asg(
    cluster_id: str,
    payload: EnableSpotASGPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAccess("EXECUTION")),
):
    """
    EXEC-08: Enable spot instances on an EKS managed nodegroup WITHOUT Karpenter.

    Updates the nodegroup's ASG to use MixedInstancesPolicy with
    price-capacity-optimized allocation and multiple compatible instance types.

    Use this for clusters where Karpenter cannot be installed.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from backend.services.spot_asg_service import SpotASGService
    from backend.services.agent_injector import AgentInjectorService

    region = cluster.region or "ap-south-1"

    # Build an authenticated boto3 session using the cluster's cross-account role
    try:
        _injector = AgentInjectorService(db)
        creds = _injector._assume_role(
            role_arn=cluster.aws_role_arn or "",
            external_id=cluster.aws_external_id or "",
            region=region,
        )
        if creds:
            import boto3 as _boto3
            boto_session = _boto3.Session(
                aws_access_key_id=creds["access_key"],
                aws_secret_access_key=creds["secret_key"],
                aws_session_token=creds.get("session_token"),
                region_name=region,
            )
        else:
            import boto3 as _boto3
            boto_session = _boto3.Session(region_name=region)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not assume cluster role: {e}")

    svc = SpotASGService(db_session=db)
    result = svc.enable_spot_on_nodegroup(
        boto_session=boto_session,
        cluster_name=cluster.name,
        nodegroup_name=payload.nodegroup_name,
        region=region,
        spot_instance_types=payload.spot_instance_types,
        on_demand_base_capacity=payload.on_demand_base_capacity,
        spot_percentage=payload.spot_percentage,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

    logger.info(
        f"SpotASG enabled on {cluster.name}/{payload.nodegroup_name} by {current_user.email}: "
        f"{result['spot_types']}"
    )
    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        **result,
    }


@router.post("/nodegroup/{cluster_id}/revert-to-ondemand")
async def revert_spot_asg(
    cluster_id: str,
    nodegroup_name: str = Query(..., description="EKS managed nodegroup name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAccess("EXECUTION")),
):
    """
    EXEC-09: Revert a nodegroup from spot (MixedInstancesPolicy) back to 100% on-demand.

    Sets OnDemandPercentageAboveBaseCapacity=100. Existing spot instances are
    not immediately terminated — they drain naturally as the ASG replaces them.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from backend.services.spot_asg_service import SpotASGService
    from backend.services.agent_injector import AgentInjectorService

    region = cluster.region or "ap-south-1"

    try:
        _injector = AgentInjectorService(db)
        creds = _injector._assume_role(
            role_arn=cluster.aws_role_arn or "",
            external_id=cluster.aws_external_id or "",
            region=region,
        )
        if creds:
            import boto3 as _boto3
            boto_session = _boto3.Session(
                aws_access_key_id=creds["access_key"],
                aws_secret_access_key=creds["secret_key"],
                aws_session_token=creds.get("session_token"),
                region_name=region,
            )
        else:
            import boto3 as _boto3
            boto_session = _boto3.Session(region_name=region)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not assume cluster role: {e}")

    svc = SpotASGService(db_session=db)
    result = svc.revert_to_on_demand(
        boto_session=boto_session,
        cluster_name=cluster.name,
        nodegroup_name=nodegroup_name,
        region=region,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

    logger.info(
        f"SpotASG reverted to on-demand on {cluster.name}/{nodegroup_name} by {current_user.email}"
    )
    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        **result,
    }


@router.get("/nodegroup/{cluster_id}/spot-status")
async def get_nodegroup_spot_status(
    cluster_id: str,
    nodegroup_name: str = Query(..., description="EKS managed nodegroup name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    EXEC-08: Get the current spot/on-demand configuration for a nodegroup.

    Returns whether MixedInstancesPolicy is active, the spot percentage,
    and which instance types are configured.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    from backend.services.spot_asg_service import SpotASGService
    from backend.services.agent_injector import AgentInjectorService

    region = cluster.region or "ap-south-1"

    try:
        _injector = AgentInjectorService(db)
        creds = _injector._assume_role(
            role_arn=cluster.aws_role_arn or "",
            external_id=cluster.aws_external_id or "",
            region=region,
        )
        if creds:
            import boto3 as _boto3
            boto_session = _boto3.Session(
                aws_access_key_id=creds["access_key"],
                aws_secret_access_key=creds["secret_key"],
                aws_session_token=creds.get("session_token"),
                region_name=region,
            )
        else:
            import boto3 as _boto3
            boto_session = _boto3.Session(region_name=region)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not assume cluster role: {e}")

    svc = SpotASGService(db_session=db)
    result = svc.get_nodegroup_spot_status(
        boto_session=boto_session,
        cluster_name=cluster.name,
        nodegroup_name=nodegroup_name,
        region=region,
    )
    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "nodegroup_name": nodegroup_name,
        **result,
    }


@router.get("/detect/{cluster_id}", summary="Detect if Karpenter is installed in a cluster")
def detect_karpenter(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Detect whether Karpenter is installed in the specified cluster.
    Returns detected=true/false and karpenter_mode.
    Only trusts live agent data — not stale DB column.
    """
    try:
        from backend.services.karpenter_service import KarpenterService
        svc = KarpenterService(db=db)
        result = svc.detect_karpenter_in_cluster(cluster_id, db)
        # If detection came from stale DB column, override to not detected
        if result.get("source") == "db_column" and result.get("detected"):
            result["detected"] = False
            result["warning"] = "No live agent data available — cannot confirm Karpenter status"
        return result
    except Exception as e:
        logger.error(f"[karpenter] detect endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Native Spot (No-Karpenter) helpers ──────────────────────────────────────

def _resolve_role_arn(cluster, db):
    """Return (role_arn, external_id) from cluster or its parent account."""
    role_arn = getattr(cluster, 'aws_role_arn', None)
    ext_id   = getattr(cluster, 'aws_external_id', None)
    if not role_arn and getattr(cluster, 'account_id', None):
        try:
            from backend.models.account import Account
            acct = db.query(Account).filter(Account.id == cluster.account_id).first()
            if acct:
                role_arn = getattr(acct, 'role_arn', None)
                ext_id   = getattr(acct, 'external_id', None)
        except Exception:
            pass
    return role_arn, ext_id


def _build_assumed_session(plat_key: str, plat_secret: str, role_arn: Optional[str],
                            ext_id: Optional[str], region: Optional[str]):
    """Build a boto3 Session using platform creds + optional cross-account role assumption."""
    import boto3 as _b3
    _region = region or "ap-south-1"
    if role_arn:
        sts = _b3.client("sts",
                         aws_access_key_id=plat_key,
                         aws_secret_access_key=plat_secret,
                         region_name=_region)
        kw: Dict[str, Any] = {"RoleArn": role_arn, "RoleSessionName": "spot-optimizer-native-spot"}
        if ext_id:
            kw["ExternalId"] = ext_id
        creds = sts.assume_role(**kw)["Credentials"]
        return _b3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=_region,
        )
    return _b3.Session(
        aws_access_key_id=plat_key,
        aws_secret_access_key=plat_secret,
        region_name=_region,
    )


def _auto_detect_nodegroup(cluster_name: str, boto_session, region: Optional[str]) -> Optional[str]:
    """List EKS nodegroups and return the first one."""
    try:
        eks = boto_session.client("eks", region_name=region or "ap-south-1")
        resp = eks.list_nodegroups(clusterName=cluster_name)
        groups = resp.get("nodegroups", [])
        return groups[0] if groups else None
    except Exception:
        return None


def _load_platform_session(cluster, db) -> tuple:
    """Return (plat_key, plat_secret, boto_session) or raise HTTPException."""
    from backend.models.system_config import SystemConfig
    _pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
    _ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
    plat_key    = _pk.value if _pk and _pk.value else None
    plat_secret = _ps.value if _ps and _ps.value else None
    if not plat_key:
        raise HTTPException(
            status_code=400,
            detail="Platform AWS credentials not configured. Add PLATFORM_AWS_ACCESS_KEY to system_configs."
        )
    role_arn, ext_id = _resolve_role_arn(cluster, db)
    session = _build_assumed_session(plat_key, plat_secret, role_arn, ext_id,
                                     getattr(cluster, 'region', None))
    return plat_key, plat_secret, session


# ─── Native Spot Endpoints ────────────────────────────────────────────────────

@router.get(
    "/native-spot/status/{cluster_id}",
    summary="Get native ASG spot status for a non-Karpenter cluster",
    description=(
        "Returns whether MixedInstancesPolicy spot is enabled on the cluster's managed nodegroup. "
        "For clusters that cannot or should not install Karpenter."
    ),
)
def get_native_spot_status(
    cluster_id: str,
    nodegroup_name: Optional[str] = Query(None, description="Nodegroup name; auto-detected if omitted"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    # Cache result for 5 minutes — this endpoint makes 3 live AWS API calls which
    # takes 2+ seconds and is called on every cluster detail page load.
    import json as _json_ns
    from backend.core.redis_client import get_redis_client as _get_redis
    _cache_key = f"native_spot_status:{cluster_id}:{nodegroup_name or 'auto'}"
    try:
        _r = _get_redis()
        _cached = _r.get(_cache_key)
        if _cached:
            return _json_ns.loads(_cached)
    except Exception:
        pass

    try:
        _, _, session = _load_platform_session(cluster, db)
    except HTTPException:
        return {"spot_enabled": False, "error": "Platform AWS credentials not configured", "cluster_id": cluster_id}

    ng_name = nodegroup_name or _auto_detect_nodegroup(
        getattr(cluster, 'name', cluster_id), session, getattr(cluster, 'region', None)
    )
    if not ng_name:
        return {
            "spot_enabled": False,
            "error": "Could not detect nodegroup — pass nodegroup_name explicitly",
            "cluster_id": cluster_id,
        }

    from backend.services.spot_asg_service import SpotASGService
    svc = SpotASGService(db)
    result = svc.get_nodegroup_spot_status(
        session, getattr(cluster, 'name', cluster_id), ng_name, getattr(cluster, 'region', None)
    )
    result["nodegroup_name"] = ng_name
    result["cluster_id"] = cluster_id

    # Store in Redis for 5 minutes
    try:
        _r.setex(_cache_key, 300, _json_ns.dumps(result))
    except Exception:
        pass

    return result


@router.post(
    "/native-spot/enable/{cluster_id}",
    summary="Enable native ASG spot on a non-Karpenter cluster",
    description=(
        "Updates the EKS managed nodegroup's ASG to use MixedInstancesPolicy "
        "(1 on-demand base + configurable spot %). No Karpenter, IAM roles, or SQS needed."
    ),
)
def enable_native_spot(
    cluster_id: str,
    payload: Dict[str, Any] = {},
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    _, _, session = _load_platform_session(cluster, db)

    ng_name = payload.get("nodegroup_name") or _auto_detect_nodegroup(
        getattr(cluster, 'name', cluster_id), session, getattr(cluster, 'region', None)
    )
    if not ng_name:
        raise HTTPException(status_code=400, detail="Could not detect nodegroup — pass nodegroup_name in body")

    spot_pct      = int(payload.get("spot_percentage", 70))
    od_base       = int(payload.get("on_demand_base", 1))

    from backend.services.spot_asg_service import SpotASGService
    svc = SpotASGService(db)
    result = svc.enable_spot_on_nodegroup(
        session,
        cluster_name=getattr(cluster, 'name', cluster_id),
        nodegroup_name=ng_name,
        region=getattr(cluster, 'region', None) or "ap-south-1",
        on_demand_base_capacity=od_base,
        spot_percentage=spot_pct,
    )

    if result.get("success"):
        # Turn on auto-rebalancing — the auto_rebalancer already handles non-Karpenter
        # clusters via _launch_spot_instance_direct()
        from backend.models.cluster import ClusterOptimizationSettings
        opt = cluster.optimization_settings
        if opt is None:
            opt = ClusterOptimizationSettings(cluster_id=cluster_id)
            db.add(opt)
        opt.auto_rebalance_enabled = True
        db.commit()
        logger.info(
            f"Native spot enabled on cluster {cluster_id} nodegroup {ng_name}; "
            f"auto_rebalance_enabled=True"
        )

    result["cluster_id"] = cluster_id
    result["nodegroup_name"] = ng_name
    return result


@router.post(
    "/native-spot/revert/{cluster_id}",
    summary="Revert a non-Karpenter cluster to 100% on-demand",
    description="Sets OnDemandPercentageAboveBaseCapacity=100. Existing spot nodes drain naturally.",
)
def revert_native_spot(
    cluster_id: str,
    payload: Dict[str, Any] = {},
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    _, _, session = _load_platform_session(cluster, db)

    ng_name = payload.get("nodegroup_name") or _auto_detect_nodegroup(
        getattr(cluster, 'name', cluster_id), session, getattr(cluster, 'region', None)
    )
    if not ng_name:
        raise HTTPException(status_code=400, detail="Could not detect nodegroup — pass nodegroup_name in body")

    from backend.services.spot_asg_service import SpotASGService
    svc = SpotASGService(db)
    result = svc.revert_to_on_demand(
        session,
        cluster_name=getattr(cluster, 'name', cluster_id),
        nodegroup_name=ng_name,
        region=getattr(cluster, 'region', None) or "ap-south-1",
    )

    if result.get("success"):
        opt = cluster.optimization_settings
        if opt:
            opt.auto_rebalance_enabled = False
            db.commit()

    result["cluster_id"] = cluster_id
    result["nodegroup_name"] = ng_name
    return result


# ─── Karpenter Event Ingest & Listing ────────────────────────────────────────

class KarpenterEventPayload(BaseModel):
    cluster_id: str
    event_reason: str
    event_source: Optional[str] = None
    involved_object_kind: Optional[str] = None
    involved_object_name: Optional[str] = None
    message: Optional[str] = None
    event_time: Optional[str] = None
    event_payload: Optional[Dict[str, Any]] = None


_DISRUPTIVE_REASONS = frozenset({
    'Consolidated', 'DisruptionLaunched', 'NodeClaimDeleted', 'TerminatingNodeClaim',
})
_REBALANCER_PAUSE_SECONDS = 120


@router.post(
    "/clusters/{cluster_id}/events",
    summary="Receive a Karpenter event from the agent sidecar",
    status_code=201,
    dependencies=[Depends(RequireAccess("READ"))],
)
def receive_karpenter_event(
    cluster_id: str,
    body: KarpenterEventPayload,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from backend.models.karpenter_event import KarpenterEvent

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    event_time_dt = None
    if body.event_time:
        try:
            event_time_dt = datetime.fromisoformat(body.event_time.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            pass

    ev = KarpenterEvent(
        cluster_id=cluster_id,
        event_reason=body.event_reason,
        event_source=body.event_source,
        involved_object_kind=body.involved_object_kind,
        involved_object_name=body.involved_object_name,
        message=body.message,
        event_payload=body.event_payload,
        event_time=event_time_dt,
        received_at=datetime.utcnow(),
        rebalancer_paused=False,
    )
    db.add(ev)
    db.flush()

    paused = False
    if body.event_reason in _DISRUPTIVE_REASONS:
        try:
            from backend.core.redis_client import get_redis_client
            _redis = get_redis_client()
            if _redis:
                pause_key = f"spot:karpenter_pause:{cluster_id}"
                if not _redis.exists(pause_key):
                    _redis.setex(pause_key, _REBALANCER_PAUSE_SECONDS, body.event_reason)
                    ev.rebalancer_paused = True
                    paused = True
        except Exception as _pause_err:
            logger.warning(f"[karpenter_events] Failed to set rebalancer pause key: {_pause_err}")

    db.commit()
    return {
        "id": ev.id,
        "cluster_id": cluster_id,
        "event_reason": body.event_reason,
        "rebalancer_paused": paused,
        "pause_seconds": _REBALANCER_PAUSE_SECONDS if paused else 0,
    }


@router.post(
    "/clusters/{cluster_id}/install",
    summary="Install Karpenter via Helm (queues INSTALL_KARPENTER AgentAction)",
    dependencies=[Depends(RequireAccess("WRITE"))],
)
def install_karpenter(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Queues an INSTALL_KARPENTER AgentAction. The in-cluster agent will execute the
    Helm install. Guards against re-installation when Karpenter is already running
    and against duplicate in-progress actions.

    Returns:
      - already_installed=True if Karpenter is already detected.
      - install_in_progress=True if an install action is already pending.
      - action_id + message on successful queue.
    """
    from backend.services.karpenter_service import KarpenterService
    from backend.core.redis_client import get_redis_client

    try:
        redis = get_redis_client()
    except Exception:
        redis = None

    try:
        svc = KarpenterService(db=db, redis=redis)
        result = svc.install_karpenter(cluster_id=cluster_id, db=db)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Karpenter install failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[karpenter] POST /clusters/{cluster_id}/install failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Karpenter install failed: {exc}",
        )


@router.get(
    "/clusters/{cluster_id}/install-status",
    summary="Get Karpenter installation status (3-tier detection + action status)",
    dependencies=[Depends(RequireAccess("READ"))],
)
def get_karpenter_install_status(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns combined Karpenter install status:
      - detected: whether Karpenter pods are running (3-tier: agent heartbeat → K8s API → DB)
      - karpenter_mode: current mode (dry_run / auto / none)
      - install_in_progress: spot:karpenter_installing flag is set
      - action_status: latest INSTALL_KARPENTER / UNINSTALL_KARPENTER action status
      - action_id: latest action ID (for polling)
      - pods_running, controller_healthy, source, error
    """
    from backend.services.karpenter_service import KarpenterService
    from backend.core.redis_client import get_redis_client

    try:
        redis = get_redis_client()
    except Exception:
        redis = None

    try:
        svc = KarpenterService(db=db, redis=redis)
        return svc.get_karpenter_install_status(cluster_id=cluster_id, db=db)
    except Exception as exc:
        logger.error(f"[karpenter] GET /clusters/{cluster_id}/install-status failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Karpenter install status: {exc}",
        )


@router.get(
    "/clusters/{cluster_id}/events",
    summary="List recent Karpenter events for a cluster",
    dependencies=[Depends(RequireAccess("READ"))],
)
def list_karpenter_events(
    cluster_id: str,
    limit: int = Query(50, ge=1, le=500),
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from backend.models.karpenter_event import KarpenterEvent
    from sqlalchemy import desc

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    q = db.query(KarpenterEvent).filter(KarpenterEvent.cluster_id == cluster_id)
    if reason:
        q = q.filter(KarpenterEvent.event_reason == reason)
    events = q.order_by(desc(KarpenterEvent.received_at)).limit(limit).all()

    return {
        "cluster_id": cluster_id,
        "total": len(events),
        "events": [
            {
                "id": e.id,
                "event_reason": e.event_reason,
                "event_source": e.event_source,
                "involved_object_kind": e.involved_object_kind,
                "involved_object_name": e.involved_object_name,
                "message": e.message,
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "rebalancer_paused": e.rebalancer_paused,
            }
            for e in events
        ],
    }


# ---------------------------------------------------------------------------
# GET /karpenter/{cluster_id}/takeover/preflight
# Classify all legacy_mng nodes: safe vs blocked (Issue 3)
# ---------------------------------------------------------------------------

@router.get("/{cluster_id}/takeover/preflight", summary="Pre-flight takeover blocker classification")
def takeover_preflight(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a node-by-node classification of takeover readiness.

    For each legacy_mng node still running, reports:
    - safe: True/False
    - skip_reason: None or a string like "kube_system_critical_pods:2",
      "singleton_statefulset_no_pdb:<workload_id>", "max_takeover_retries_exceeded:3"

    Response also includes the cluster's current onboarding_phase, count of
    remaining MNG nodes, and whether takeover is currently active.
    """
    from backend.models.instance import Instance
    from backend.workers.tasks.auto_rebalancer import _takeover_should_skip_node
    from backend.core.redis_client import get_redis_client

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    redis = get_redis_client()

    mng_nodes = (
        db.query(Instance)
        .filter(
            Instance.cluster_id == cluster_id,
            Instance.node_owner_type == "legacy_mng",
            Instance.state == "running",
        )
        .all()
    )

    node_classifications = []
    safe_count = 0
    blocked_count = 0
    for node in mng_nodes:
        skip_reason = _takeover_should_skip_node(node, cluster_id, redis, db)
        is_safe = skip_reason is None
        if is_safe:
            safe_count += 1
        else:
            blocked_count += 1
        node_classifications.append({
            "node_name": node.node_name,
            "instance_id": node.instance_id,
            "instance_type": node.instance_type,
            "az": node.az,
            "safe": is_safe,
            "skip_reason": skip_reason,
        })

    takeover_active = bool(redis and redis.exists(f"spot:takeover_active:{cluster_id}"))
    takeover_completed_raw = redis.get(f"spot:takeover_completed_at:{cluster_id}") if redis else None
    takeover_completed_at = None
    if takeover_completed_raw:
        try:
            import time as _time
            takeover_completed_at = datetime.utcfromtimestamp(
                float(takeover_completed_raw)
            ).isoformat()
        except Exception:
            pass

    return {
        "cluster_id": cluster_id,
        "onboarding_phase": getattr(cluster, "onboarding_phase", "unknown"),
        "takeover_active": takeover_active,
        "takeover_completed_at": takeover_completed_at,
        "mng_nodes_remaining": len(mng_nodes),
        "safe_to_proceed": safe_count,
        "blocked": blocked_count,
        "nodes": node_classifications,
    }
