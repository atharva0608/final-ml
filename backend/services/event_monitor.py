"""
Event Monitor Service
=====================

Handles spot interruption termination notices and volatility regime detection.

Key Features:
- Emergency termination path that bypasses normal pipeline (delta, savings, cooldown)
- Immediate substitute activation on termination notice
- Deterministic blacklisting (bypasses cascade suspension)
- Node classification safety checks (refuses to auto-replace stateful nodes)
- Volatility regime detection for policy tightening

CRITICAL: Termination path overrides:
- ✓ Bypasses delta threshold check
- ✓ Bypasses savings check
- ✓ Bypasses cluster cooldown
- ✓ Bypasses MODEL_MISMATCH protection
- ✗ DOES check node classification (safety first)
"""

import json
import numpy as np
import base64
import boto3
import time
from botocore.config import Config
from botocore.signers import RequestSigner
from kubernetes import client
from kubernetes.client.rest import ApiException
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from redis import Redis

from backend.core.logger import logger
from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.models.system_config import SystemConfig
from backend.services.blacklist_service import BlacklistService
from backend.services.cooldown_controller import CooldownController
from backend.services.workload_inspector import WorkloadInspector, NodeStatus
from backend.services.global_pool_cache_service import GlobalPoolCacheService


class EventMonitor:
    """
    Event monitoring service for spot interruptions and volatility detection.

    Provides emergency response capabilities that bypass normal optimization
    constraints for termination events, while maintaining safety guardrails.
    """

    VOLATILITY_TTL_HOURS = 2  # Flag lifetime (survives one ranking cycle)
    VOLATILITY_PERCENTILE = 95  # Threshold for high volatility regime
    TERMINATION_BLACKLIST_HOURS = 24  # Fixed 24h for termination events

    def __init__(self, db: Session, redis: Redis):
        """
        Initialize EventMonitor.

        Args:
            db: SQLAlchemy database session
            redis: Redis client instance
        """
        self.db = db
        self.redis = redis
        self.blacklist = BlacklistService(redis)
        self.cooldown = CooldownController(redis)
        self.workload_inspector = WorkloadInspector(redis)
        self.cache = GlobalPoolCacheService(db, redis)

    def handle_termination_notice(
        self,
        cluster_id: str,
        instance_type: str,
        az: str,
        region: str,
        node_name: Optional[str] = None
    ) -> Dict:
        """
        Handle spot instance termination notice (2-minute warning).

        TERMINATION PATH — OVERRIDES NORMAL SCORING PIPELINE:
        - Bypasses delta threshold check
        - Bypasses savings check
        - Bypasses cluster cooldown
        - Bypasses MODEL_MISMATCH protection
        - Immediate substitute activation
        - But DOES check node classification for safety

        Flow:
        0. Check node classification → if not STATELESS_ELIGIBLE, emit alert and return
        1. Pre-drain validation (kubectl drain --dry-run)
        2. Immediate substitute activation (if available)
        3. Cordon + drain current node
        4. Blacklist failed pool (24h, BYPASSES cascade suspension flag)
        5. Override cluster cooldown (emergency clear)
        6. Invalidate global cache (trigger reranking)
        7. Detect volatility regime for region
        8. Log termination event

        This path NEVER waits for ML delta, scoring approval, or model version check.
        But it WILL refuse to auto-replace stateful/protected nodes.
        Safety > cost optimization.

        Args:
            cluster_id: Cluster identifier
            instance_type: EC2 instance type being terminated
            az: Availability zone
            region: AWS region
            node_name: Optional Kubernetes node name

        Returns:
            Dict with termination handling results
        """
        pool_key = f"{instance_type}:{az}"

        logger.warning(
            f"TERMINATION NOTICE received for {pool_key} in cluster {cluster_id}"
        )

        result = {
            "cluster_id": cluster_id,
            "pool_key": pool_key,
            "region": region,
            "timestamp": datetime.utcnow().isoformat(),
            "action": None,
            "reason": None,
            "substitute_activated": False,
            "node_drained": False,
            "pool_blacklisted": False,
            "cooldown_overridden": False,
            "cache_invalidated": False,
            "volatility_detected": False
        }

        # Step 0: Check node classification (CRITICAL SAFETY CHECK)
        classification = self.workload_inspector.get_cached_classification(cluster_id)

        if not classification:
            # No classification available — FAIL CLOSED
            logger.error(
                f"Node classification unavailable for cluster {cluster_id}, "
                "cannot safely handle termination"
            )
            result["action"] = "alert_only"
            result["reason"] = "classification_unavailable"
            self._emit_alert(cluster_id, pool_key, "no_classification")
            return result

        if node_name:
            node_status = classification.get(node_name)

            if node_status != NodeStatus.STATELESS_ELIGIBLE:
                # Node is stateful or protected — DO NOT auto-replace
                logger.warning(
                    f"Node {node_name} is {node_status}, refusing auto-replacement. "
                    "Manual intervention required."
                )
                result["action"] = "alert_only"
                result["reason"] = f"node_protected_{node_status}"
                self._emit_alert(cluster_id, pool_key, f"protected_node_{node_status}")
                return result

        # Node is safe to optimize or classification not required
        logger.info(f"Node {node_name or 'unknown'} is safe to optimize, proceeding...")

        # Step 1: Pre-drain validation
        drain_validation = self._validate_drain(cluster_id, node_name)

        if not drain_validation["safe"]:
            logger.error(
                f"Pre-drain validation failed for {node_name}: {drain_validation['reason']}"
            )
            result["action"] = "validation_failed"
            result["reason"] = drain_validation["reason"]
            self._emit_alert(cluster_id, pool_key, "drain_validation_failed")
            return result

        # Step 2: Immediate substitute activation (if SubstituteManager exists)
        # NOTE: SubstituteManager may not exist yet — gracefully handle
        substitute_result = self._activate_substitute(cluster_id, region)
        result["substitute_activated"] = substitute_result.get("activated", False)

        # Step 3: Cordon + drain node
        if node_name:
            drain_result = self._drain_node(cluster_id, node_name)
            result["node_drained"] = drain_result.get("success", False)

            if not result["node_drained"]:
                logger.error(f"Failed to drain node {node_name}")
                self._emit_alert(cluster_id, pool_key, "drain_failed")

        # Step 4: Blacklist pool (DETERMINISTIC — bypasses cascade suspension)
        blacklist_result = self.blacklist.blacklist_pool(
            instance_type=instance_type,
            az=az,
            region=region,
            reason="spot_termination_notice"
        )
        result["pool_blacklisted"] = True

        logger.warning(
            f"Pool {pool_key} BLACKLISTED for {self.TERMINATION_BLACKLIST_HOURS}h "
            "(termination event — deterministic blacklist)"
        )

        # Step 5: Override cluster cooldown (emergency clear)
        self.cooldown.override_for_emergency(cluster_id)
        result["cooldown_overridden"] = True

        logger.info(f"Cluster {cluster_id} cooldown OVERRIDDEN for emergency response")

        # Step 6: Invalidate global cache (force reranking)
        self.cache.invalidate_cache(region)
        result["cache_invalidated"] = True

        logger.info(f"Global pool cache INVALIDATED for {region}")

        # Step 7: Detect volatility regime
        self.detect_volatility_regime(region)
        volatility_key = f"spot:volatility_regime:{region}"
        result["volatility_detected"] = self.redis.exists(volatility_key)

        # Step 8: Log termination event
        self._log_termination_event(cluster_id, pool_key, region, result)

        result["action"] = "terminated_and_replaced"
        result["reason"] = "spot_termination_notice_handled"

        logger.info(
            f"Termination notice handled successfully for {pool_key} in cluster {cluster_id}"
        )

        return result

    def detect_volatility_regime(self, region: str):
        """
        Detect high volatility regime for region-level policy tightening.

        Volatility percentile calculation:
        1. Compute rolling 24h standard deviation of spot prices
        2. Compare against 30-day distribution of daily stddevs
        3. If current 24h stddev > 95th percentile → set regime flag

        TTL: 2 hours (longer than 1h to survive one ranking cycle)
        Called: every 1h by scheduler AND after any termination event

        Args:
            region: AWS region code
        """
        try:
            logger.info(f"Detecting volatility regime for {region}...")

            # Get 24h spot price history
            prices_24h = self._get_spot_prices_last_24h(region)

            if len(prices_24h) < 10:
                logger.warning(
                    f"Insufficient price data for volatility detection ({len(prices_24h)} points)"
                )
                return

            # Compute 24h standard deviation
            stddev_24h = np.std(prices_24h)

            # Get 30-day historical stddevs
            historical_stddevs = self._get_daily_stddevs_30d(region)

            if len(historical_stddevs) < 10:
                logger.warning(
                    f"Insufficient historical data for volatility baseline ({len(historical_stddevs)} days)"
                )
                return

            # Compute 95th percentile threshold
            p95_threshold = np.percentile(historical_stddevs, self.VOLATILITY_PERCENTILE)

            # Check if current volatility exceeds threshold
            if stddev_24h > p95_threshold:
                # Set high volatility flag
                volatility_key = f"spot:volatility_regime:{region}"
                ttl_seconds = self.VOLATILITY_TTL_HOURS * 3600

                self.redis.setex(volatility_key, ttl_seconds, "active")

                logger.warning(
                    f"HIGH VOLATILITY REGIME detected for {region}: "
                    f"24h stddev={stddev_24h:.4f} > p95={p95_threshold:.4f} "
                    f"(flag TTL: {self.VOLATILITY_TTL_HOURS}h)"
                )

                # Track detection event
                self._emit_metric("volatility_regime_detected", region=region)
            else:
                logger.info(
                    f"Volatility normal for {region}: "
                    f"24h stddev={stddev_24h:.4f} <= p95={p95_threshold:.4f}"
                )

        except Exception as e:
            logger.error(f"Error detecting volatility regime for {region}: {e}", exc_info=True)

    def _get_spot_prices_last_24h(self, region: str) -> List[float]:
        """
        Get spot price history for last 24 hours.

        In production, this would query AWS Pricing API or local cache.
        For now, use Redis cache if available or return empty list.

        Args:
            region: AWS region

        Returns:
            List of spot prices (hourly samples)
        """
        try:
            # Try to get from Redis cache
            cache_key = f"spot:price_history_24h:{region}"
            cached = self.redis.get(cache_key)

            if cached:
                return json.loads(cached)

            # TODO: Query AWS Pricing API or pricing_collector service
            # For now, return empty list (graceful degradation)
            logger.warning(f"No 24h price history available for {region}")
            return []

        except Exception as e:
            logger.error(f"Error fetching 24h price history: {e}")
            return []

    def _get_daily_stddevs_30d(self, region: str) -> List[float]:
        """
        Get 30-day historical daily standard deviations.

        In production, this would query aggregated price volatility data.
        For now, use Redis cache if available or return empty list.

        Args:
            region: AWS region

        Returns:
            List of daily stddevs for last 30 days
        """
        try:
            # Try to get from Redis cache
            cache_key = f"spot:price_stddev_30d:{region}"
            cached = self.redis.get(cache_key)

            if cached:
                return json.loads(cached)

            # TODO: Query aggregated volatility data
            # For now, return empty list (graceful degradation)
            logger.warning(f"No 30d volatility baseline available for {region}")
            return []

        except Exception as e:
            logger.error(f"Error fetching 30d volatility baseline: {e}")
            return []

    # ── Kubernetes Authentication Helpers ───────────────────────────────

    def _get_backend_credentials(self, region: str) -> Dict:
        """Get backend platform IAM credentials from SystemConfig."""
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()

        if access_key and secret_key and access_key.value and secret_key.value:
            return {'access_key': access_key.value, 'secret_key': secret_key.value}
        return {}

    def _get_eks_token(self, cluster_name: str, credentials: Dict, region: str) -> str:
        """Generate Kubernetes authentication token for EKS via SigV4."""
        if credentials and 'access_key' in credentials and 'secret_key' in credentials:
            session = boto3.Session(
                aws_access_key_id=credentials['access_key'],
                aws_secret_access_key=credentials['secret_key'],
                aws_session_token=credentials.get('session_token'),
                region_name=region
            )
        else:
            session = boto3.Session(region_name=region)

        sts_client = session.client('sts', region_name=region, config=Config(signature_version='v4'))
        service_id = sts_client.meta.service_model.service_id
        signer = RequestSigner(service_id, region, 'sts', 'v4', session.get_credentials(), session.events)

        params = {
            'method': 'GET',
            'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
            'body': {},
            'headers': {'x-k8s-aws-id': cluster_name},
            'context': {}
        }

        url = signer.generate_presigned_url(params, region_name=region, expires_in=60, operation_name='')
        return 'k8s-aws-v1.' + base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8').rstrip('=')

    def _get_k8s_client(self, cluster_id: str):
        """Creates Kubernetes API client for EKS cluster."""
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        credentials = self._get_backend_credentials(cluster.region)
        token = self._get_eks_token(cluster.name, credentials, cluster.region)

        configuration = client.Configuration()
        configuration.host = cluster.endpoint
        configuration.api_key = {"authorization": f"Bearer {token}"}

        if cluster.ca_data:
            # ca_data from EKS is Base64-encoded PEM — write raw bytes in binary mode
            import tempfile, base64
            try:
                ca_bytes = base64.b64decode(cluster.ca_data)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.crt') as ca_file:
                    ca_file.write(ca_bytes)
                    ca_cert_path = ca_file.name
                configuration.ssl_ca_cert = ca_cert_path
                configuration.verify_ssl = True
            except Exception as ssl_ex:
                logger.warning(f"[EventMonitor] Failed to write CA cert ({ssl_ex}); disabling SSL verification.")
                configuration.verify_ssl = False
        else:
            logger.warning(f"[EventMonitor] Cluster {cluster.id} has no ca_data; disabling SSL verification.")
            configuration.verify_ssl = False

        return client.ApiClient(configuration)

    def _validate_drain(self, cluster_id: str, node_name: Optional[str]) -> Dict:
        """
        Pre-drain validation by checking PodDisruptionBudgets.
        """
        if not node_name:
            return {"safe": True, "reason": "no_node_specified"}
            
        try:
            api_client = self._get_k8s_client(cluster_id)
            core_v1 = client.CoreV1Api(api_client)
            policy_v1 = client.PolicyV1Api(api_client)
            
            # Get pods on the node
            field_selector = f"spec.nodeName={node_name}"
            pods = core_v1.list_pod_for_all_namespaces(field_selector=field_selector)
            
            # Check PDBs for each pod
            all_pdbs = policy_v1.list_pod_disruption_budget_for_all_namespaces()
            
            for pod in pods.items:
                # Ignore daemonsets and succeeded/failed pods
                if any(ref.kind == 'DaemonSet' for ref in pod.metadata.owner_references or []):
                    continue
                if pod.status.phase in ['Succeeded', 'Failed']:
                    continue
                    
                # Check if any PDB blocks eviction
                for pdb in all_pdbs.items:
                    if pdb.metadata.namespace == pod.metadata.namespace:
                        # Simplified PDB check: if allowed disruptions is 0, we can't drain safely
                        if pdb.status.disruptions_allowed == 0:
                            logger.warning(f"PDB {pdb.metadata.name} blocks eviction for pod {pod.metadata.name}")
                            return {
                                "safe": False,
                                "reason": f"pdb_blocks_eviction_for_pod_{pod.metadata.name}"
                            }
                            
            return {"safe": True, "reason": "pdb_checks_passed"}
            
        except Exception as e:
            logger.error(f"Error validating drain for {node_name}: {e}")
            # Fail closed on validation errors
            return {"safe": False, "reason": "api_error"}

    def _activate_substitute(self, cluster_id: str, region: str) -> Dict:
        """
        Activate substitute node using SubstituteManager.
        """
        try:
            from backend.services.substitute_manager import SubstituteManager
            substitute_mgr = SubstituteManager(self.db, self.redis)
            # Find the target node name if prewarming
            # In an emergency, we just promote whatever is ready
            status = substitute_mgr.get_substitute_status(cluster_id)
            if status and status.get("state") == "READY":
                result = substitute_mgr.promote_substitute(cluster_id)
                return {
                    "activated": result.get("success", False),
                    "reason": result.get("message")
                }
            return {"activated": False, "reason": "no_substitute_ready"}
        except ImportError:
            logger.warning("SubstituteManager not available")
            return {"activated": False, "reason": "manager_not_found"}
        except Exception as e:
            logger.error(f"Error activating substitute: {e}")
            return {"activated": False, "reason": "activation_error"}

    def _drain_node(self, cluster_id: str, node_name: str) -> Dict:
        """
        Cordon and drain Kubernetes node using Eviction API.
        """
        if not node_name:
            return {"success": False, "reason": "no_node_specified"}
            
        try:
            api_client = self._get_k8s_client(cluster_id)
            core_v1 = client.CoreV1Api(api_client)
            
            # 1. Cordon the node (PATCH unschedulable)
            body = {
                "spec": {
                    "unschedulable": True
                }
            }
            core_v1.patch_node(node_name, body)
            logger.info(f"Cordoned node {node_name} in cluster {cluster_id}")
            
            # 2. Evict Pods
            field_selector = f"spec.nodeName={node_name}"
            pods = core_v1.list_pod_for_all_namespaces(field_selector=field_selector)
            
            for pod in pods.items:
                # Skip daemonsets and already terminated pods
                if any(ref.kind == 'DaemonSet' for ref in pod.metadata.owner_references or []):
                    continue
                if pod.status.phase in ['Succeeded', 'Failed']:
                    continue
                    
                eviction = client.V1Eviction(
                    metadata=client.V1ObjectMeta(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace
                    )
                )
                
                try:
                    core_v1.create_namespaced_pod_eviction(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        body=eviction
                    )
                    logger.debug(f"Evicted pod {pod.metadata.namespace}/{pod.metadata.name}")
                except ApiException as e:
                    if e.status != 429: # Ignore TooManyRequests for now
                        logger.warning(f"Failed to evict {pod.metadata.name}: {e}")
            
            return {"success": True, "reason": "cordoned_and_evicted"}
            
        except ApiException as e:
            logger.error(f"K8s API error draining node {node_name}: {e}")
            return {"success": False, "reason": "k8s_api_error"}
        except Exception as e:
            logger.error(f"Error draining node {node_name}: {e}")
            return {"success": False, "reason": "internal_error"}

    def _emit_alert(self, cluster_id: str, pool_key: str, alert_type: str):
        """
        Emit alert for manual intervention required.

        In production, this would trigger PagerDuty, Slack, or SNS notification.
        For now, log alert (graceful degradation).

        Args:
            cluster_id: Cluster identifier
            pool_key: Pool key (instance_type:az)
            alert_type: Alert type identifier
        """
        logger.critical(
            f"ALERT: Manual intervention required for cluster {cluster_id}, "
            f"pool {pool_key}, type={alert_type}"
        )

        # TODO: Integrate with alerting system
        # - PagerDuty incident creation
        # - Slack webhook
        # - SNS topic publish

    def _log_termination_event(
        self,
        cluster_id: str,
        pool_key: str,
        region: str,
        result: Dict
    ):
        """
        Log termination event to Redis for audit trail.

        In production, this would also write to termination_events table.
        For now, use Redis only (graceful degradation).

        Args:
            cluster_id: Cluster identifier
            pool_key: Pool key
            region: AWS region
            result: Termination handling result
        """
        try:
            event_key = f"spot:termination_events:{cluster_id}"
            event_data = {
                "pool_key": pool_key,
                "region": region,
                "timestamp": result["timestamp"],
                "action": result["action"],
                "reason": result["reason"],
                "substitute_activated": result["substitute_activated"],
                "node_drained": result["node_drained"],
                "pool_blacklisted": result["pool_blacklisted"]
            }

            # Append to event list (keep last 100 events)
            self.redis.lpush(event_key, json.dumps(event_data))
            self.redis.ltrim(event_key, 0, 99)

            logger.info(f"Termination event logged for cluster {cluster_id}")

        except Exception as e:
            logger.error(f"Error logging termination event: {e}")

    def _emit_metric(self, metric_name: str, **tags):
        """
        Emit metric for monitoring.

        In production, this would push to CloudWatch, Prometheus, or Datadog.
        For now, increment Redis counter (graceful degradation).

        Args:
            metric_name: Metric identifier
            **tags: Metric tags (region, cluster_id, etc.)
        """
        try:
            # Increment counter in Redis
            metric_key = f"spot:metrics:{metric_name}"
            self.redis.incr(metric_key)

            # Store tags in hash
            if tags:
                tag_key = f"spot:metrics:{metric_name}:tags"
                self.redis.hset(tag_key, mapping=tags)

            logger.debug(f"Metric emitted: {metric_name} {tags}")

        except Exception as e:
            logger.error(f"Error emitting metric {metric_name}: {e}")

    def get_volatility_status(self, region: str) -> Dict:
        """
        Get current volatility status for region.

        Args:
            region: AWS region

        Returns:
            Dict with volatility status
        """
        volatility_key = f"spot:volatility_regime:{region}"
        ttl = self.redis.ttl(volatility_key)

        return {
            "region": region,
            "high_volatility": ttl > 0,
            "ttl_seconds": max(ttl, 0) if ttl > 0 else 0,
            "ttl_minutes": max(ttl, 0) // 60 if ttl > 0 else 0
        }

    def get_termination_history(self, cluster_id: str, limit: int = 10) -> List[Dict]:
        """
        Get termination event history for cluster.

        Args:
            cluster_id: Cluster identifier
            limit: Maximum events to return

        Returns:
            List of termination events (most recent first)
        """
        try:
            event_key = f"spot:termination_events:{cluster_id}"
            events = self.redis.lrange(event_key, 0, limit - 1)

            return [json.loads(event) for event in events]

        except Exception as e:
            logger.error(f"Error fetching termination history: {e}")
            return []
