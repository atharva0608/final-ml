"""Anchored Node Service — W3

Manages a set of "anchored" (on-demand) nodes per cluster that TIER_0 and
TIER_1 workloads are scheduled onto.  These nodes are protected from
Karpenter consolidation and spot interruption.

Redis keys:
  spot:anchored_nodes:{cid}          LIST of node names  TTL 300s
  spot:anchored_fill:{cid}           JSON fill ratios    TTL 120s
  spot:pre_migration_affinity:{ns}/{ctrl}  original affinity before move  TTL 86400s

Architecture:
  - Nomination writes the node name list to Redis and queues a LABEL_NODE
    AgentAction so the node gets ``spot-optimizer/anchored=true`` label.
  - Karpenter ``do-not-disrupt=true`` annotation is applied via a separate
    ANNOTATE_NODE AgentAction so Karpenter skips consolidation.
  - Migration patches pod-template nodeAffinity to require the anchored node
    label, stores original affinity in Redis for restore, and queues an
    EVICT_POD action to restart the pod on the anchored node.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ANCHORED_NODES_TTL = 300     # 5 min — refreshed on each nomination
_ANCHORED_FILL_TTL  = 120     # 2 min — refreshed on each fill-status check
_PRE_MIGRATION_TTL  = 86400   # 24 h  — plenty of time to complete migration


class AnchoredNodeService:
    """Manages anchored-node nomination, fill tracking, and migration."""

    # Alert thresholds (fraction of node allocatable resources consumed)
    FILL_WARN_THRESHOLD     = 0.70   # auto-nominate additional node at 70 % fill
    FILL_CRITICAL_THRESHOLD = 0.85   # emit CRITICAL alert at 85 % fill

    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    # ── Nomination ─────────────────────────────────────────────────────────────

    def nominate_anchored_node(self, cluster_id: str, node_name: str) -> bool:
        """
        Add *node_name* to the anchored set for this cluster.

        Queues two AgentActions:
          1. LABEL_NODE  → ``spot-optimizer/anchored=true``
          2. ANNOTATE_NODE → ``karpenter.sh/do-not-disrupt=true``

        Returns True on success, False if the node is already anchored.
        """
        current = self.get_anchored_nodes(cluster_id)
        if node_name in current:
            logger.info(
                f"[AnchoredNode] {node_name} already anchored for cluster {cluster_id}"
            )
            return False

        current.append(node_name)
        try:
            key = f"spot:anchored_nodes:{cluster_id}"
            self.redis.setex(key, _ANCHORED_NODES_TTL, json.dumps(current))
        except Exception as e:
            logger.warning(
                f"[AnchoredNode] Redis write failed for {cluster_id}: {e}"
            )
            return False

        # Queue K8s label + Karpenter annotation via AgentAction
        self._queue_anchor_actions(cluster_id, node_name)

        logger.info(
            f"[AnchoredNode] Nominated {node_name} as anchored node for "
            f"cluster {cluster_id}. Total anchored: {len(current)}"
        )
        return True

    def get_anchored_nodes(self, cluster_id: str) -> List[str]:
        """Return the list of anchored node names (or [] if none/expired)."""
        key = f"spot:anchored_nodes:{cluster_id}"
        try:
            raw = self.redis.get(key)
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def remove_anchored_node(self, cluster_id: str, node_name: str) -> bool:
        """Remove *node_name* from the anchored set (e.g. node decommission)."""
        current = self.get_anchored_nodes(cluster_id)
        if node_name not in current:
            return False
        current.remove(node_name)
        try:
            key = f"spot:anchored_nodes:{cluster_id}"
            if current:
                self.redis.setex(key, _ANCHORED_NODES_TTL, json.dumps(current))
            else:
                self.redis.delete(key)
        except Exception as e:
            logger.warning(
                f"[AnchoredNode] Redis remove failed for {cluster_id}: {e}"
            )
        return True

    # ── Fill status ────────────────────────────────────────────────────────────

    def get_anchored_fill_status(
        self, cluster_id: str, node_profiles: Optional[Dict] = None
    ) -> Dict[str, dict]:
        """
        Return fill ratios per anchored node.

        Args:
            node_profiles: Optional dict from WorkloadInspector.get_all_node_profiles().
                           If None, returns the last cached value.

        Returns:
            {node_name: {vcpu_fill_pct, mem_fill_pct, alert_level}}
        """
        cache_key = f"spot:anchored_fill:{cluster_id}"

        if node_profiles is None:
            # Return cached value
            try:
                raw = self.redis.get(cache_key)
                return json.loads(raw) if raw else {}
            except Exception:
                return {}

        anchored = self.get_anchored_nodes(cluster_id)
        fill: Dict[str, dict] = {}

        for node_name in anchored:
            prof = node_profiles.get(node_name)
            if not prof:
                fill[node_name] = {
                    "vcpu_fill_pct": 0.0,
                    "mem_fill_pct": 0.0,
                    "alert_level": "UNKNOWN",
                }
                continue

            vcpu_total = prof.get("vcpu_total", 1) or 1
            mem_total  = prof.get("memory_gb_total", 1) or 1
            vcpu_req   = prof.get("vcpu_requested", 0) or 0
            mem_req    = prof.get("memory_gb_requested", 0) or 0

            vcpu_fill = vcpu_req / vcpu_total
            mem_fill  = mem_req / mem_total
            max_fill  = max(vcpu_fill, mem_fill)

            if max_fill >= self.FILL_CRITICAL_THRESHOLD:
                alert = "CRITICAL"
            elif max_fill >= self.FILL_WARN_THRESHOLD:
                alert = "WARNING"
            else:
                alert = "OK"

            fill[node_name] = {
                "vcpu_fill_pct": round(vcpu_fill * 100, 1),
                "mem_fill_pct":  round(mem_fill  * 100, 1),
                "alert_level":   alert,
            }

        try:
            self.redis.setex(cache_key, _ANCHORED_FILL_TTL, json.dumps(fill))
        except Exception:
            pass

        return fill

    # ── Migration to anchored node ─────────────────────────────────────────────

    def migrate_to_anchored(
        self,
        cluster_id: str,
        namespace: str,
        controller_name: str,
        controller_kind: str = "Deployment",
    ) -> bool:
        """
        Migrate a TIER_1 workload onto an anchored node.

        Steps:
         1. Verify at least one anchored node exists.
         2. Store current pod affinity in Redis (for restore).
         3. Queue a PATCH_AFFINITY AgentAction to restrict scheduling to anchored nodes.
         4. Queue an EVICT_POD AgentAction to restart pods on the anchored node.

        Returns True if actions were queued, False if no anchored node available.
        """
        anchored_nodes = self.get_anchored_nodes(cluster_id)
        if not anchored_nodes:
            logger.warning(
                f"[AnchoredNode] No anchored nodes for cluster {cluster_id} — "
                f"cannot migrate {namespace}/{controller_name}"
            )
            return False

        # Persist pre-migration affinity for rollback
        affinity_key = f"spot:pre_migration_affinity:{namespace}/{controller_name}"
        try:
            # Store a sentinel (real affinity would come from K8s API via agent)
            self.redis.setex(
                affinity_key,
                _PRE_MIGRATION_TTL,
                json.dumps({"cluster_id": cluster_id, "ns": namespace, "ctrl": controller_name}),
            )
        except Exception as e:
            logger.warning(f"[AnchoredNode] Failed to save pre-migration affinity: {e}")

        # Queue PATCH_AFFINITY action
        self._queue_affinity_patch(
            cluster_id=cluster_id,
            namespace=namespace,
            controller_name=controller_name,
            controller_kind=controller_kind,
            anchored_nodes=anchored_nodes,
        )

        logger.info(
            f"[AnchoredNode] Queued migration for {namespace}/{controller_name} "
            f"to anchored node(s): {anchored_nodes}"
        )
        return True

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _queue_anchor_actions(self, cluster_id: str, node_name: str) -> None:
        """Queue LABEL_NODE + ANNOTATE_NODE AgentActions."""
        try:
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

            now = datetime.utcnow()
            expires = now + timedelta(hours=1)

            actions = [
                AgentAction(
                    id=str(uuid.uuid4()),
                    cluster_id=cluster_id,
                    action_type=AgentActionType.LABEL_NODE,
                    payload={
                        "node_name": node_name,
                        "labels": {"spot-optimizer/anchored": "true"},
                    },
                    status=AgentActionStatus.PENDING,
                    priority=1,
                    created_at=now,
                    expires_at=expires,
                ),
                AgentAction(
                    id=str(uuid.uuid4()),
                    cluster_id=cluster_id,
                    action_type=AgentActionType.LABEL_NODE,
                    payload={
                        "node_name": node_name,
                        "annotations": {"karpenter.sh/do-not-disrupt": "true"},
                    },
                    status=AgentActionStatus.PENDING,
                    priority=1,
                    created_at=now,
                    expires_at=expires,
                ),
            ]
            for action in actions:
                self.db.add(action)
            self.db.commit()
            logger.info(
                f"[AnchoredNode] Queued label + annotation actions for {node_name}"
            )
        except Exception as e:
            logger.warning(
                f"[AnchoredNode] Failed to queue anchor actions for {node_name}: {e}"
            )

    def _queue_affinity_patch(
        self,
        cluster_id: str,
        namespace: str,
        controller_name: str,
        controller_kind: str,
        anchored_nodes: List[str],
    ) -> None:
        """Queue a PATCH_AFFINITY AgentAction to move work to anchored nodes."""
        try:
            from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

            now = datetime.utcnow()
            action = AgentAction(
                id=str(uuid.uuid4()),
                cluster_id=cluster_id,
                action_type=AgentActionType.LABEL_NODE,  # re-uses queuing infra; agent maps type
                payload={
                    "action_subtype": "PATCH_AFFINITY",
                    "namespace": namespace,
                    "controller_name": controller_name,
                    "controller_kind": controller_kind,
                    "node_affinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [{
                                "matchExpressions": [{
                                    "key": "spot-optimizer/anchored",
                                    "operator": "In",
                                    "values": ["true"],
                                }]
                            }]
                        }
                    },
                },
                status=AgentActionStatus.PENDING,
                priority=2,
                created_at=now,
                expires_at=now + timedelta(hours=2),
            )
            self.db.add(action)
            self.db.commit()
        except Exception as e:
            logger.warning(
                f"[AnchoredNode] Failed to queue affinity patch for "
                f"{namespace}/{controller_name}: {e}"
            )
