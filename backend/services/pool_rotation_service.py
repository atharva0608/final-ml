"""
Pool Rotation Service - Auto-Failover & Fresh Pool Cache Management
====================================================================

Maintains fresh pool availability and automatically rotates to backup AZs
when primary AZs become fully blacklisted.

Features:
- Real-time blacklist monitoring across all AZs
- Auto-rotation to backup AZs (configurable via node template)
- Fresh pool cache (15-min TTL) with proactive refresh
- Cascade dampener activation when >70% pools blacklisted
- Notification system for rotation events

Design:
- Runs as background task every 5 minutes (Celery beat)
- Maintains Redis cache: "pool_rotation:{cluster_id}" with status
- Integrates with blacklist_service for real-time blacklist checks
- Respects template flagging_rules configuration
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from redis import Redis
from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.services.blacklist_service import BlacklistService
from backend.models.cluster import Cluster


class PoolRotationService:
    """
    Manages pool rotation and fresh pool cache for resilient pool selection.

    Key responsibilities:
    1. Monitor blacklist status per AZ
    2. Auto-rotate to backup AZs when primary is unhealthy
    3. Maintain fresh pool cache (always >= min_viable_pools)
    4. Trigger cascade dampener when needed
    5. Send notifications on rotation events
    """

    ROTATION_CHECK_INTERVAL = 300  # 5 minutes (Celery beat schedule)
    FRESH_POOL_CACHE_TTL = 900     # 15 minutes
    MIN_VIABLE_POOLS_DEFAULT = 10
    CASCADE_THRESHOLD_DEFAULT = 0.70  # 70%

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.blacklist_service = BlacklistService(redis)

    def check_and_rotate(self, cluster_id: str, region: str = "ap-south-1") -> Dict:
        """
        Check if rotation is needed and execute if necessary.

        Args:
            cluster_id: Cluster ID to check
            region: AWS region

        Returns:
            Dict with rotation status and actions taken
        """
        try:
            # ── SAFETY GATE 1: Substitute Mutual Exclusion ───────────────────
            substitute_state = self.redis.get(f"spot:substitute:state:{cluster_id}")
            substitute_state = (substitute_state.decode('utf-8') if isinstance(substitute_state, bytes) else substitute_state) or "IDLE"
            if substitute_state not in ("IDLE", "FAILED", "COMPLETED"):
                logger.info(
                    f"Deferring rotation for {cluster_id}: substitute in {substitute_state}"
                )
                return {"status": "DEFERRED", "reason": "SUBSTITUTE_ACTIVE"}

            # ── SAFETY GATE 2: Stabilization lock ────────────────────────────
            # Another system (auto_rebalancer, right-sizing) executed recently — wait
            from backend.services.cooldown_controller import CooldownController
            _cooldown = CooldownController(self.redis)
            is_locked, remaining = _cooldown.is_stabilization_locked(cluster_id)
            if is_locked:
                logger.info(
                    f"Deferring rotation for {cluster_id}: stabilization lock active "
                    f"({remaining}s remaining) — cluster stabilizing after recent operation"
                )
                return {"status": "DEFERRED", "reason": "STABILIZATION_LOCK", "remaining_seconds": remaining}

            # ── SAFETY GATE 3: OptimizerCoordinator phase ────────────────────
            # Don't re-rank pools while combined EV is being computed mid-phase
            try:
                from backend.models.optimizer_state import OptimizerState
                _opt_state = self.db.query(OptimizerState).filter(
                    OptimizerState.cluster_id == cluster_id
                ).first()
                if _opt_state and _opt_state.current_phase in ("RIGHTSIZING_EVALUATION", "COMBINED_EXECUTION"):
                    logger.info(
                        f"Deferring rotation for {cluster_id}: optimizer in phase "
                        f"{_opt_state.current_phase} — pool re-rank would corrupt EV calculation"
                    )
                    return {"status": "DEFERRED", "reason": f"OPTIMIZER_PHASE_{_opt_state.current_phase}"}
            except Exception:
                pass  # OptimizerState table may not exist on all deployments

            # Get cluster and its template config
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return {"error": "Cluster not found", "cluster_id": cluster_id}

            # Extract flagging rules from template
            flagging_rules = self._get_flagging_rules(cluster)
            if not flagging_rules.get("auto_rotation_enabled", True):
                return {"status": "auto_rotation_disabled", "cluster_id": cluster_id}

            # Get current pool distribution
            pool_status = self._analyze_pool_health(cluster_id, region, flagging_rules)

            # Check if rotation is needed
            rotation_needed = self._is_rotation_needed(pool_status, flagging_rules)

            result = {
                "cluster_id": cluster_id,
                "region": region,
                "rotation_needed": rotation_needed,
                "pool_status": pool_status,
                "timestamp": datetime.utcnow().isoformat()
            }

            if rotation_needed:
                logger.warning(
                    f"Pool rotation NEEDED for cluster {cluster_id}: "
                    f"viable_pools={pool_status['viable_pool_count']}, "
                    f"min_threshold={pool_status['min_viable_threshold']}"
                )

                # Execute rotation under distributed lock so auto_rebalancer can't
                # simultaneously cordon/drain the same nodes (RC-4)
                from backend.services.distributed_locks import distributed_lock
                lock_key = f"lock:node_action:{cluster_id}"
                try:
                    with distributed_lock(lock_key, timeout=120):
                        rotation_result = self._execute_rotation(cluster_id, region, pool_status, flagging_rules)
                except RuntimeError:
                    logger.warning(
                        f"Pool rotation for {cluster_id} deferred: node-action lock held by another system"
                    )
                    return {"status": "DEFERRED", "reason": "LOCK_CONTENTION"}

                result["rotation_executed"] = True
                result["rotation_result"] = rotation_result

                # Acquire stabilization lock — prevents right-sizing and auto_rebalancer
                # from acting on this cluster while it stabilizes after rotation (RC-7)
                _cooldown.acquire_stabilization_lock(cluster_id, reason="pool_rotation")

                # Send notification
                self._notify_rotation(cluster_id, rotation_result)

            else:
                # Update fresh pool cache anyway (proactive refresh)
                self._refresh_pool_cache(cluster_id, region, pool_status)
                result["rotation_executed"] = False
                result["cache_refreshed"] = True

            # Store rotation status in Redis
            self._store_rotation_status(cluster_id, result)

            return result

        except Exception as e:
            logger.error(f"Error in check_and_rotate for cluster {cluster_id}: {e}")
            return {
                "error": str(e),
                "cluster_id": cluster_id,
                "timestamp": datetime.utcnow().isoformat()
            }

    def _get_flagging_rules(self, cluster: Cluster) -> Dict:
        """
        Extract flagging rules from cluster's active node template.

        Returns default rules if template not configured.
        """
        try:
            # Get active template mapping
            active_mapping = next(
                (m for m in cluster.template_mappings if m.is_default),
                None
            )

            if not active_mapping or not active_mapping.version:
                # Return defaults
                return self._default_flagging_rules()

            # Extract constraints_json → flagging_rules
            constraints = active_mapping.version.constraints_json or {}
            flagging_rules = constraints.get("flagging_rules", {})

            # Merge with defaults
            defaults = self._default_flagging_rules()
            defaults.update(flagging_rules)

            return defaults

        except Exception as e:
            logger.warning(f"Error extracting flagging rules for cluster {cluster.id}: {e}")
            return self._default_flagging_rules()

    def _default_flagging_rules(self) -> Dict:
        """Default flagging rules configuration."""
        return {
            "max_risk_threshold": 0.50,
            "max_interruption_rate": 15,
            "min_ml_score": 0.30,
            "blacklist_respect": "soft",
            "blacklist_penalty_pct": 20.0,
            "diversity_enforcement": "strict",
            "max_az_concentration": 50,
            "max_family_concentration": 40,
            "auto_rotation_enabled": True,
            "backup_az_count": 2,
            "min_viable_pools": 10,
            "cascade_dampener_enabled": True,
            "cascade_threshold_pct": 70.0
        }

    def _analyze_pool_health(self, cluster_id: str, region: str, flagging_rules: Dict) -> Dict:
        """
        Analyze current pool health across all AZs.

        Returns:
            {
                "total_pools": int,
                "viable_pool_count": int,
                "blacklisted_count": int,
                "blacklist_ratio": float,
                "az_status": {
                    "aps1-az1": {"total": 10, "blacklisted": 8, "viable": 2},
                    "aps1-az2": {"total": 10, "blacklisted": 1, "viable": 9},
                    ...
                },
                "primary_az": str,
                "backup_azs": list[str],
                "cascade_risk": bool,
                "min_viable_threshold": int
            }
        """
        # Get all AZs in region
        all_azs = self._get_region_azs(region)

        # Get blacklist status per AZ
        blacklist_status = self.blacklist_service.get_blacklist_status(region)
        blacklisted_by_az = {}
        for entry in blacklist_status:
            az = entry.get("az", "")
            blacklisted_by_az[az] = blacklisted_by_az.get(az, 0) + 1

        # Analyze each AZ
        az_status = {}
        total_pools = 0
        viable_pool_count = 0
        blacklisted_count = 0

        for az in all_azs:
            # Estimate total pools per AZ (from instance catalog)
            # In production, this would query actual candidate pool count
            estimated_pools_per_az = 15  # 15 instance types per AZ (m5, c5, r5 families)

            blacklisted_in_az = blacklisted_by_az.get(az, 0)
            viable_in_az = max(0, estimated_pools_per_az - blacklisted_in_az)

            az_status[az] = {
                "total": estimated_pools_per_az,
                "blacklisted": blacklisted_in_az,
                "viable": viable_in_az
            }

            total_pools += estimated_pools_per_az
            viable_pool_count += viable_in_az
            blacklisted_count += blacklisted_in_az

        # Calculate blacklist ratio
        blacklist_ratio = blacklisted_count / total_pools if total_pools > 0 else 0.0

        # Determine primary and backup AZs
        # Sort AZs by viable pool count (descending)
        sorted_azs = sorted(
            all_azs,
            key=lambda az: az_status[az]["viable"],
            reverse=True
        )

        primary_az = sorted_azs[0] if sorted_azs else all_azs[0]
        backup_count = flagging_rules.get("backup_az_count", 2)
        backup_azs = sorted_azs[1:1+backup_count] if len(sorted_azs) > 1 else []

        # Check cascade risk
        cascade_threshold = flagging_rules.get("cascade_threshold_pct", 70.0) / 100.0
        cascade_risk = blacklist_ratio > cascade_threshold

        return {
            "total_pools": total_pools,
            "viable_pool_count": viable_pool_count,
            "blacklisted_count": blacklisted_count,
            "blacklist_ratio": blacklist_ratio,
            "az_status": az_status,
            "primary_az": primary_az,
            "backup_azs": backup_azs,
            "cascade_risk": cascade_risk,
            "min_viable_threshold": flagging_rules.get("min_viable_pools", 10)
        }

    def _is_rotation_needed(self, pool_status: Dict, flagging_rules: Dict) -> bool:
        """
        Determine if rotation is needed based on pool health.

        Rotation triggers:
        1. Viable pool count < min_viable_threshold
        2. Primary AZ has <30% viable pools
        3. Cascade risk detected (>70% blacklisted globally)
        """
        viable_count = pool_status["viable_pool_count"]
        min_threshold = pool_status["min_viable_threshold"]

        # Trigger 1: Below minimum viable threshold
        if viable_count < min_threshold:
            return True

        # Trigger 2: Primary AZ unhealthy
        primary_az = pool_status["primary_az"]
        primary_status = pool_status["az_status"].get(primary_az, {})
        primary_viable_ratio = (
            primary_status["viable"] / primary_status["total"]
            if primary_status.get("total", 0) > 0
            else 0.0
        )

        if primary_viable_ratio < 0.30:  # <30% viable in primary AZ
            return True

        # Trigger 3: Cascade risk
        if pool_status["cascade_risk"]:
            return True

        return False

    def _execute_rotation(
        self,
        cluster_id: str,
        region: str,
        pool_status: Dict,
        flagging_rules: Dict
    ) -> Dict:
        """
        Execute pool rotation strategy.

        Actions:
        1. Promote backup AZs to primary selection
        2. Update cluster metadata with new primary AZ
        3. Clear Redis pool ranking cache (forces re-rank with new AZ priority)
        4. Activate cascade dampener if needed
        5. Log rotation event

        Returns:
            Dict with rotation details
        """
        primary_az = pool_status["primary_az"]
        backup_azs = pool_status["backup_azs"]
        cascade_risk = pool_status["cascade_risk"]

        actions_taken = []

        # Action 1: Promote first backup AZ to primary
        if backup_azs:
            new_primary_az = backup_azs[0]
            logger.info(f"Rotating primary AZ: {primary_az} → {new_primary_az}")

            # Update cluster metadata with new primary AZ
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if cluster:
                metadata = cluster.metadata or {}
                metadata["primary_az"] = new_primary_az
                metadata["previous_primary_az"] = primary_az
                metadata["last_rotation_at"] = datetime.utcnow().isoformat()
                cluster.metadata = metadata
                self.db.commit()

            actions_taken.append(f"Promoted {new_primary_az} to primary AZ")
        else:
            logger.warning(f"No backup AZs available for cluster {cluster_id}")
            new_primary_az = primary_az
            actions_taken.append("No backup AZ available - keeping current primary")

        # Action 2: Clear pool ranking cache (forces re-rank)
        cache_key = f"atharvaai:pool_rankings:{cluster_id}"
        self.redis.delete(cache_key)
        actions_taken.append("Cleared pool ranking cache")

        # Action 3: Activate cascade dampener if needed
        if cascade_risk and flagging_rules.get("cascade_dampener_enabled", True):
            self.blacklist_service.suspend_blacklisting(region)
            actions_taken.append("Activated cascade dampener (30 min suspension)")

        # Action 4: Force re-rank with expanded AZ list
        self._expand_az_selection(cluster_id, backup_azs)
        actions_taken.append(f"Expanded AZ selection to include: {', '.join(backup_azs)}")

        return {
            "old_primary_az": primary_az,
            "new_primary_az": new_primary_az,
            "backup_azs": backup_azs,
            "cascade_dampener_active": cascade_risk,
            "actions_taken": actions_taken,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _expand_az_selection(self, cluster_id: str, backup_azs: List[str]):
        """
        Update cluster's allowed AZ list to include backup AZs.

        This ensures the next pool ranking call will consider backup AZs.
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return

            metadata = cluster.metadata or {}
            current_azs = metadata.get("allowed_azs", [])

            # Merge with backups
            expanded_azs = list(set(current_azs + backup_azs))
            metadata["allowed_azs"] = expanded_azs
            metadata["az_expansion_at"] = datetime.utcnow().isoformat()

            cluster.metadata = metadata
            self.db.commit()

            logger.info(f"Expanded AZ selection for cluster {cluster_id}: {expanded_azs}")

        except Exception as e:
            logger.error(f"Error expanding AZ selection for cluster {cluster_id}: {e}")
            self.db.rollback()

    def _refresh_pool_cache(self, cluster_id: str, region: str, pool_status: Dict):
        """
        Proactively refresh the fresh pool cache.

        Stores top 20 viable pools from all healthy AZs in Redis.
        """
        cache_key = f"fresh_pools:{cluster_id}"

        try:
            # Get viable pools from all AZs
            # In production, this would call pool_ranking_service.rank_pools()
            # For now, store metadata about viable AZs

            cache_data = {
                "cluster_id": cluster_id,
                "region": region,
                "viable_pool_count": pool_status["viable_pool_count"],
                "primary_az": pool_status["primary_az"],
                "backup_azs": pool_status["backup_azs"],
                "refreshed_at": datetime.utcnow().isoformat(),
                "ttl_seconds": self.FRESH_POOL_CACHE_TTL
            }

            self.redis.setex(
                cache_key,
                self.FRESH_POOL_CACHE_TTL,
                json.dumps(cache_data)
            )

            logger.debug(f"Refreshed fresh pool cache for cluster {cluster_id}")

        except Exception as e:
            logger.error(f"Error refreshing pool cache for cluster {cluster_id}: {e}")

    def _store_rotation_status(self, cluster_id: str, status: Dict):
        """Store rotation status in Redis for UI consumption."""
        status_key = f"pool_rotation_status:{cluster_id}"
        self.redis.setex(status_key, 3600, json.dumps(status))  # 1 hour TTL

    def _notify_rotation(self, cluster_id: str, rotation_result: Dict):
        """
        Send notification about rotation event.

        In production, this would:
        - Send Slack/email notification
        - Create audit log entry
        - Trigger webhook
        """
        logger.critical(
            f"POOL ROTATION EXECUTED for cluster {cluster_id}: "
            f"{rotation_result['old_primary_az']} → {rotation_result['new_primary_az']}"
        )

        # Store notification in Redis for UI to fetch
        notif_key = f"notifications:rotation:{cluster_id}"
        notification = {
            "type": "pool_rotation",
            "severity": "high",
            "cluster_id": cluster_id,
            "message": f"Pool auto-rotation: {rotation_result['old_primary_az']} → {rotation_result['new_primary_az']}",
            "details": rotation_result,
            "timestamp": datetime.utcnow().isoformat()
        }

        self.redis.setex(notif_key, 86400, json.dumps(notification))  # 24 hour TTL

    def get_rotation_status(self, cluster_id: str) -> Optional[Dict]:
        """
        Get current rotation status for a cluster.

        Used by UI to display rotation state.
        """
        status_key = f"pool_rotation_status:{cluster_id}"
        status_data = self.redis.get(status_key)

        if status_data:
            return json.loads(status_data)

        return None

    def _get_region_azs(self, region: str) -> List[str]:
        """Get all availability zones for a region.

        WARNING (Task 4.7): Hardcoded fallback. TODO: Query EC2 describe_availability_zones
        dynamically and cache in Redis with 24h TTL.
        """
        # Hardcoded fallback — acceptable as boot default, but should be replaced
        # with ec2.describe_availability_zones() cached in Redis (24h TTL).
        logger.debug(
            f"[_get_region_azs] Using hardcoded AZ list for region={region} "
            f"(fallback — dynamic discovery not yet implemented)"
        )
        if region == "ap-south-1":
            return ["aps1-az1", "aps1-az2", "aps1-az3"]
        else:
            return [f"{region}a", f"{region}b", f"{region}c"]

    # ==================== Admin/Debug Methods ====================

    def force_rotation(self, cluster_id: str, region: str = "ap-south-1") -> Dict:
        """
        Force immediate rotation (admin/testing only).

        Bypasses health checks and executes rotation immediately.
        """
        logger.warning(f"FORCE ROTATION requested for cluster {cluster_id}")

        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return {"error": "Cluster not found"}

        flagging_rules = self._get_flagging_rules(cluster)
        pool_status = self._analyze_pool_health(cluster_id, region, flagging_rules)

        rotation_result = self._execute_rotation(cluster_id, region, pool_status, flagging_rules)
        self._notify_rotation(cluster_id, rotation_result)

        return {
            "forced": True,
            "cluster_id": cluster_id,
            "rotation_result": rotation_result,
            "timestamp": datetime.utcnow().isoformat()
        }

    def get_all_rotation_statuses(self) -> List[Dict]:
        """
        Get rotation status for all clusters (admin view).
        """
        clusters = self.db.query(Cluster).all()
        statuses = []

        for cluster in clusters:
            status = self.get_rotation_status(cluster.id)
            if status:
                statuses.append(status)

        return statuses
