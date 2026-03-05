"""Karpenter Integration Service - System 3: NodePool Management

Updates Karpenter NodePools with ML-approved instance types.

Flow:
1. ML pipeline ranks safe pools → Top 10 instance types
2. Karpenter service syncs ML rankings → NodePool YAML
3. Karpenter reads updated NodePool → Provisions from safe list only
4. On-demand fallback: if no safe spot pools → switch to on-demand per template

Features:
- Kubernetes API client for EKS clusters
- NodePool YAML generator
- ML ranking → instance-types sync
- On-demand fallback with 12-hour TTL auto-revert
- Multi-cluster support
"""

import base64
import boto3
import json
import subprocess
import time
import yaml
from typing import List, Dict, Optional
from datetime import datetime
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.signers import RequestSigner
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
from sqlalchemy.orm import Session

from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.models.system_config import SystemConfig
from backend.core.logger import logger


class KarpenterService:
    """Manages Karpenter NodePool updates based on ML rankings."""

    FALLBACK_TTL_SECONDS = 12 * 3600  # 12 hours
    MAX_PATCH_RETRIES = 2
    RETRY_DELAYS = [5, 15]  # seconds

    def __init__(self, db: Session, redis=None):
        self.db = db
        self.redis = redis

    def sync_ml_rankings_to_nodepool(
        self,
        cluster_id: str,
        top_pools: List[Dict],
        nodepool_name: str = "default"
    ) -> Dict:
        """
        Syncs ML-ranked instance types to Karpenter NodePool.

        Args:
            cluster_id: Cluster database ID
            top_pools: List of ML-scored pools from PoolRankingService
            nodepool_name: Name of the Karpenter NodePool to update

        Returns:
            Dict with sync status, updated instance types, timestamp
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            api_client = self._get_k8s_client(cluster)
            instance_types = list(set([pool['instance_type'] for pool in top_pools]))
            azs = list(set([pool['az'] for pool in top_pools]))

            logger.info(
                f"Syncing {len(instance_types)} ML-approved instance types "
                f"to NodePool '{nodepool_name}' in cluster {cluster.name}"
            )

            updated = self._update_nodepool(
                api_client=api_client,
                nodepool_name=nodepool_name,
                instance_types=instance_types,
                azs=azs,
                cluster=cluster
            )

            return {
                'status': 'success',
                'cluster_id': cluster_id,
                'cluster_name': cluster.name,
                'nodepool_name': nodepool_name,
                'instance_types': instance_types,
                'availability_zones': azs,
                'pool_count': len(top_pools),
                'created_new': not updated,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to sync ML rankings to NodePool: {e}")
            return {
                'status': 'error',
                'cluster_id': cluster_id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    # ── On-Demand Fallback Methods ──────────────────────────────────────

    def switch_to_ondemand(
        self,
        cluster_id: str,
        template_instance_types: List[str],
        template_azs: Optional[List[str]] = None,
        nodepool_name: str = "default"
    ) -> Dict:
        """
        Switch NodePool from spot to on-demand instances.

        Called when no safe spot pools are found. All workloads switch to
        on-demand instances that match the same node template constraints.

        Args:
            cluster_id: Cluster database ID
            template_instance_types: Instance types allowed by node template
            template_azs: AZs allowed by node template (None = all region AZs)
            nodepool_name: Name of the Karpenter NodePool

        Returns:
            Dict with fallback status
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)
            azs = template_azs or self._get_region_azs(cluster.region)

            # Build NodePool with ON-DEMAND capacity type
            nodepool_spec = {
                "apiVersion": "karpenter.sh/v1beta1",
                "kind": "NodePool",
                "metadata": {
                    "name": nodepool_name,
                    "labels": {
                        "managed-by": "spot-optimizer",
                        "ml-optimized": "true",
                        "fallback-mode": "on-demand"
                    },
                    "annotations": {
                        "last-updated": datetime.utcnow().isoformat(),
                        "updated-by": "atharvaai-fallback",
                        "fallback-reason": "no-safe-spot-pools"
                    }
                },
                "spec": {
                    "template": {
                        "spec": {
                            "requirements": [
                                {
                                    "key": "karpenter.sh/capacity-type",
                                    "operator": "In",
                                    "values": ["on-demand"]
                                },
                                {
                                    "key": "node.kubernetes.io/instance-type",
                                    "operator": "In",
                                    "values": template_instance_types
                                },
                                {
                                    "key": "topology.kubernetes.io/zone",
                                    "operator": "In",
                                    "values": azs
                                }
                            ],
                            "nodeClassRef": {"name": "default"}
                        }
                    },
                    "disruption": {
                        "consolidationPolicy": "WhenUnderutilized",
                        "expireAfter": "720h"
                    },
                    "limits": {"cpu": "1000", "memory": "1000Gi"}
                }
            }

            # Apply NodePool update
            try:
                custom_api.patch_namespaced_custom_object(
                    group="karpenter.sh", version="v1beta1",
                    namespace="karpenter", plural="nodepools",
                    name=nodepool_name, body=nodepool_spec
                )
            except ApiException as e:
                if e.status == 404:
                    custom_api.create_namespaced_custom_object(
                        group="karpenter.sh", version="v1beta1",
                        namespace="karpenter", plural="nodepools",
                        body=nodepool_spec
                    )
                else:
                    raise

            # Set 12-hour fallback TTL in Redis
            if self.redis:
                fallback_key = f"ondemand_fallback:{cluster_id}"
                fallback_data = {
                    "cluster_id": cluster_id,
                    "cluster_name": cluster.name,
                    "nodepool_name": nodepool_name,
                    "activated_at": datetime.utcnow().isoformat(),
                    "instance_types": template_instance_types,
                    "azs": azs
                }
                self.redis.setex(fallback_key, self.FALLBACK_TTL_SECONDS, json.dumps(fallback_data))

            logger.warning(
                f"ON-DEMAND FALLBACK activated for cluster {cluster.name}. "
                f"Instance types: {template_instance_types}. "
                f"Will auto-revert to spot in 12 hours."
            )

            return {
                "status": "fallback_activated",
                "cluster_id": cluster_id,
                "capacity_type": "on-demand",
                "instance_types": template_instance_types,
                "ttl_hours": self.FALLBACK_TTL_SECONDS / 3600,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to switch to on-demand: {e}")
            return {
                "status": "error",
                "cluster_id": cluster_id,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def revert_to_spot(
        self,
        cluster_id: str,
        nodepool_name: str = "default"
    ) -> Dict:
        """
        Revert NodePool from on-demand back to spot.

        Called when fallback TTL expires (12 hours) or manually.
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            try:
                nodepool = custom_api.get_namespaced_custom_object(
                    group="karpenter.sh", version="v1beta1",
                    namespace="karpenter", plural="nodepools",
                    name=nodepool_name
                )
            except ApiException as e:
                if e.status == 404:
                    return {"status": "not_found", "message": f"NodePool {nodepool_name} not found"}
                raise

            # Extract current instance types and AZs
            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
            instance_types, azs = [], []
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    instance_types = req.get('values', [])
                if req.get('key') == 'topology.kubernetes.io/zone':
                    azs = req.get('values', [])

            # Patch back to spot
            patch = {
                "spec": {
                    "template": {
                        "spec": {
                            "requirements": [
                                {"key": "karpenter.sh/capacity-type", "operator": "In", "values": ["spot"]},
                                {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": instance_types},
                                {"key": "topology.kubernetes.io/zone", "operator": "In", "values": azs}
                            ]
                        }
                    }
                },
                "metadata": {
                    "annotations": {
                        "last-updated": datetime.utcnow().isoformat(),
                        "updated-by": "atharvaai-fallback-revert"
                    }
                }
            }

            custom_api.patch_namespaced_custom_object(
                group="karpenter.sh", version="v1beta1",
                namespace="karpenter", plural="nodepools",
                name=nodepool_name, body=patch
            )

            if self.redis:
                self.redis.delete(f"ondemand_fallback:{cluster_id}")

            logger.info(f"Reverted cluster {cluster.name} from on-demand to spot.")
            return {
                "status": "reverted_to_spot",
                "cluster_id": cluster_id,
                "capacity_type": "spot",
                "instance_types": instance_types,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to revert to spot: {e}")
            return {"status": "error", "cluster_id": cluster_id, "error": str(e)}

    def is_in_fallback_mode(self, cluster_id: str) -> bool:
        """Check if cluster is currently in on-demand fallback mode."""
        if not self.redis:
            return False
        return bool(self.redis.exists(f"ondemand_fallback:{cluster_id}"))

    def _get_region_azs(self, region: str) -> List[str]:
        """Get default AZs for region."""
        if region == "ap-south-1":
            return ["aps1-az1", "aps1-az2", "aps1-az3"]
        return [f"{region}a", f"{region}b", f"{region}c"]

    # ── Execution Layer Safety Methods ──────────────────────────────────

    def _final_capacity_check(self, candidate_list: List[Dict], region: str) -> Optional[Dict]:
        """
        Final execution-level DryRun.

        LAYER ISOLATION:
        ✗ Does NOT update spot:dryrun_count:{region}
        ✗ Does NOT update spot:dryrun_failures_24h:{pool}
        ✗ Does NOT blacklist directly (except after 2+ failures)
        ✓ ONLY updates spot:execution_fail:{pool_id} (TTL 1h)
        ✓ Escalates to 6h blacklist ONLY if execution_failures >= 2 within 1h

        Args:
            candidate_list: List of candidate pools with instance_type and az
            region: AWS region

        Returns:
            First pool that passes capacity check, or None if all fail
        """
        if not self.redis:
            logger.warning("Redis not available for execution capacity checks")
            return candidate_list[0] if candidate_list else None

        from backend.services.blacklist_service import BlacklistService

        for candidate in candidate_list:
            pool_id = f"{candidate['instance_type']}:{candidate['az']}"

            # Skip pools with active execution penalties
            fail_key = f"spot:execution_fail:{pool_id}"
            if self.redis.exists(fail_key):
                fail_count = int(self.redis.get(fail_key) or 0)
                if fail_count >= 2:
                    logger.info(f"Skipping {pool_id} — execution penalty active (failures={fail_count})")
                    continue

            try:
                ec2 = self._get_ec2_client(region)
                ec2.run_instances(
                    InstanceType=candidate["instance_type"],
                    DryRun=True,
                    MinCount=1,
                    MaxCount=1
                )
            except ClientError as e:
                if "DryRunOperation" in str(e):
                    # Capacity confirmed — this pool is viable
                    logger.info(f"Execution capacity check PASSED: {pool_id}")
                    return candidate

                # Execution failure — temporary penalty ONLY
                logger.warning(f"Execution capacity check FAILED: {pool_id} — {str(e)}")
                fail_count = self.redis.incr(fail_key)
                if fail_count == 1:
                    self.redis.expire(fail_key, 3600)  # 1 hour TTL

                # Escalate to 6h blacklist after 2+ failures within 1h
                if fail_count >= 2:
                    logger.error(f"Repeated execution failures for {pool_id} — escalating to 6h blacklist")
                    BlacklistService(self.redis).blacklist_pool_tiered_safe(
                        candidate["instance_type"],
                        candidate["az"],
                        region,
                        reason="repeated_execution_failure",
                        ttl_hours=6,
                        source="execution"
                    )
                continue
            except Exception as e:
                logger.error(f"Unexpected error in execution capacity check for {pool_id}: {e}")
                continue

        logger.error("All candidate pools failed execution capacity check")
        return None

    def _validate_drain(self, node_name: str) -> bool:
        """
        kubectl drain --dry-run to catch PDB/finalizer issues before commit.

        Args:
            node_name: Kubernetes node name to validate

        Returns:
            True if drain would succeed, False otherwise
        """
        try:
            result = subprocess.run(
                ["kubectl", "drain", node_name, "--ignore-daemonsets", "--dry-run=client"],
                capture_output=True,
                timeout=30,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"Drain dry-run failed for {node_name}: {result.stderr}")
                return False
            logger.info(f"Drain dry-run passed for {node_name}")
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"Drain dry-run timed out for {node_name}")
            return False
        except Exception as e:
            logger.error(f"Drain dry-run error for {node_name}: {e}")
            return False

    def _check_circuit_breaker(self, cluster_id: str) -> bool:
        """
        Per-cluster circuit breaker: if >10 execution failures in 10 min, disable spot.

        Args:
            cluster_id: Cluster database ID

        Returns:
            True if circuit breaker is tripped (should block execution), False otherwise
        """
        if not self.redis:
            return False

        breaker_key = f"spot:cluster_circuit_breaker:{cluster_id}"
        if self.redis.get(breaker_key):
            logger.warning(f"Circuit breaker ACTIVE for cluster {cluster_id}")
            return True

        fail_window_key = f"spot:exec_fail_window:{cluster_id}"
        fail_count = int(self.redis.get(fail_window_key) or 0)

        if fail_count >= 10:
            self.redis.setex(breaker_key, 1800, "active")  # 30 min disable
            logger.critical(f"CIRCUIT BREAKER TRIPPED: cluster={cluster_id}, failures={fail_count}")
            return True

        return False

    def _record_execution_failure(self, cluster_id: str):
        """
        Record execution failure for circuit breaker tracking.

        Args:
            cluster_id: Cluster database ID
        """
        if not self.redis:
            return

        key = f"spot:exec_fail_window:{cluster_id}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 600)  # 10 min window
        logger.warning(f"Execution failure recorded for cluster {cluster_id} (count={count}/10)")

    def _get_nodepool_state(self, api_client, nodepool_name: str) -> Optional[Dict]:
        """
        Capture current NodePool state for rollback.

        Args:
            api_client: Kubernetes API client
            nodepool_name: Name of the NodePool

        Returns:
            Current NodePool spec, or None if not found
        """
        try:
            custom_api = client.CustomObjectsApi(api_client)
            nodepool = custom_api.get_namespaced_custom_object(
                group="karpenter.sh",
                version="v1beta1",
                namespace="karpenter",
                plural="nodepools",
                name=nodepool_name
            )
            return nodepool.get('spec')
        except ApiException as e:
            if e.status == 404:
                logger.info(f"NodePool {nodepool_name} does not exist (new creation)")
                return None
            logger.error(f"Failed to get NodePool state: {e}")
            raise

    def _restore_nodepool_state(self, api_client, nodepool_name: str, previous_state: Optional[Dict]):
        """
        Restore NodePool to previous state after failed patch.

        Args:
            api_client: Kubernetes API client
            nodepool_name: Name of the NodePool
            previous_state: Previous NodePool spec to restore
        """
        if not previous_state:
            logger.info("No previous state to restore (NodePool was new)")
            return

        try:
            custom_api = client.CustomObjectsApi(api_client)
            patch_body = {"spec": previous_state}
            custom_api.patch_namespaced_custom_object(
                group="karpenter.sh",
                version="v1beta1",
                namespace="karpenter",
                plural="nodepools",
                name=nodepool_name,
                body=patch_body
            )
            logger.info(f"Successfully rolled back NodePool {nodepool_name} to previous state")
        except Exception as e:
            logger.error(f"CRITICAL: Rollback failed for NodePool {nodepool_name}: {e}")
            raise

    def _get_ec2_client(self, region: str):
        """
        Get AWS EC2 client for capacity checks.

        Args:
            region: AWS region

        Returns:
            boto3 EC2 client
        """
        credentials = self._get_backend_credentials(region)
        if credentials and 'access_key' in credentials and 'secret_key' in credentials:
            return boto3.client(
                'ec2',
                region_name=region,
                aws_access_key_id=credentials['access_key'],
                aws_secret_access_key=credentials['secret_key'],
                aws_session_token=credentials.get('session_token')
            )
        else:
            return boto3.client('ec2', region_name=region)

    # ── Internal helpers ────────────────────────────────────────────────

    def _get_k8s_client(self, cluster: Cluster):
        """Creates Kubernetes API client for EKS cluster."""
        try:
            account = self.db.query(Account).filter(Account.id == cluster.account_id).first()
            if not account:
                raise ValueError(f"Account {cluster.account_id} not found")

            credentials = self._get_backend_credentials(cluster.region)
            token = self._get_eks_token(
                cluster_name=cluster.name,
                credentials=credentials,
                region=cluster.region
            )

            configuration = client.Configuration()
            configuration.host = cluster.endpoint
            configuration.api_key = {"authorization": f"Bearer {token}"}

            if cluster.ca_data:
                # ca_data from EKS describe_cluster is Base64-encoded PEM.
                # Write raw decoded bytes in binary mode — matches agent_injector approach.
                import tempfile, base64
                try:
                    ca_bytes = base64.b64decode(cluster.ca_data)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.crt') as ca_file:
                        ca_file.write(ca_bytes)
                        ca_cert_path = ca_file.name
                    configuration.ssl_ca_cert = ca_cert_path
                    configuration.verify_ssl = True
                except Exception as ssl_ex:
                    logger.warning(
                        f"[Karpenter] Failed to write CA cert for cluster {cluster.name} "
                        f"({ssl_ex}); disabling SSL verification."
                    )
                    configuration.verify_ssl = False
            else:
                # No CA cert stored — skip TLS verification rather than crash
                logger.warning(
                    f"[Karpenter] Cluster {cluster.name} has no ca_data; "
                    "disabling SSL verification. Re-discover the cluster to populate CA cert."
                )
                configuration.verify_ssl = False

            api_client = client.ApiClient(configuration)
            logger.info(f"Successfully created Kubernetes API client for cluster {cluster.name}")
            return api_client

        except Exception as e:
            logger.error(f"Failed to create Kubernetes API client: {e}")
            raise

    def _get_backend_credentials(self, region: str) -> Dict:
        """Get backend platform IAM credentials from SystemConfig."""
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()

        if access_key and secret_key and access_key.value and secret_key.value:
            return {'access_key': access_key.value, 'secret_key': secret_key.value}
        else:
            logger.warning("Platform credentials not found, using environment/instance profile")
            return {}

    def _get_eks_token(self, cluster_name: str, credentials: Dict, region: str) -> str:
        """Generate Kubernetes authentication token for EKS via SigV4 presigned URL."""
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
        token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8').rstrip('=')
        return token

    def _update_nodepool(
        self, api_client, nodepool_name: str,
        instance_types: List[str], azs: List[str],
        cluster: Cluster, capacity_type: str = "spot"
    ) -> bool:
        """
        Updates Karpenter NodePool with ML-approved instance types.
        Includes rollback, retry logic, and circuit breaker checks.

        Args:
            capacity_type: "spot" or "on-demand"

        Returns:
            True if existing NodePool was updated, False if created new
        """
        # Check circuit breaker before attempting execution
        if self._check_circuit_breaker(cluster.id):
            raise Exception(f"Circuit breaker active for cluster {cluster.id} — execution blocked")

        try:
            custom_api = client.CustomObjectsApi(api_client)

            nodepool_spec = {
                "apiVersion": "karpenter.sh/v1beta1",
                "kind": "NodePool",
                "metadata": {
                    "name": nodepool_name,
                    "labels": {"managed-by": "spot-optimizer", "ml-optimized": "true"},
                    "annotations": {
                        "last-updated": datetime.utcnow().isoformat(),
                        "updated-by": "atharvaai-ml-pipeline"
                    }
                },
                "spec": {
                    "template": {
                        "spec": {
                            "requirements": [
                                {"key": "karpenter.sh/capacity-type", "operator": "In", "values": [capacity_type]},
                                {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": instance_types},
                                {"key": "topology.kubernetes.io/zone", "operator": "In", "values": azs}
                            ],
                            "nodeClassRef": {"name": "default"}
                        }
                    },
                    "disruption": {"consolidationPolicy": "WhenUnderutilized", "expireAfter": "720h"},
                    "limits": {"cpu": "1000", "memory": "1000Gi"}
                }
            }

            # Capture current state for rollback
            current_state = self._get_nodepool_state(api_client, nodepool_name)

            try:
                custom_api.get_namespaced_custom_object(
                    group="karpenter.sh", version="v1beta1",
                    namespace="karpenter", plural="nodepools", name=nodepool_name
                )
                logger.info(f"Updating existing NodePool '{nodepool_name}' with retry logic")

                # Retry loop for PATCH operations
                for attempt in range(self.MAX_PATCH_RETRIES + 1):
                    try:
                        custom_api.patch_namespaced_custom_object(
                            group="karpenter.sh", version="v1beta1",
                            namespace="karpenter", plural="nodepools",
                            name=nodepool_name, body=nodepool_spec
                        )
                        logger.info(f"NodePool PATCH succeeded on attempt {attempt + 1}")
                        return True

                    except Exception as e:
                        if attempt < self.MAX_PATCH_RETRIES:
                            delay = self.RETRY_DELAYS[attempt]
                            logger.warning(
                                f"PATCH attempt {attempt + 1} failed, retry in {delay}s: {e}"
                            )
                            time.sleep(delay)
                        else:
                            logger.error(
                                f"PATCH failed after {self.MAX_PATCH_RETRIES + 1} attempts, "
                                f"initiating rollback: {e}"
                            )
                            self._restore_nodepool_state(api_client, nodepool_name, current_state)
                            self._record_execution_failure(cluster.id)
                            raise

            except ApiException as e:
                if e.status == 404:
                    logger.info(f"Creating new NodePool '{nodepool_name}'")
                    custom_api.create_namespaced_custom_object(
                        group="karpenter.sh", version="v1beta1",
                        namespace="karpenter", plural="nodepools",
                        body=nodepool_spec
                    )
                    return False
                else:
                    raise

        except Exception as e:
            logger.error(f"Failed to update NodePool: {e}")
            raise

    def get_nodepool_status(self, cluster_id: str, nodepool_name: str = "default") -> Dict:
        """Gets current status of Karpenter NodePool."""
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            nodepool = custom_api.get_namespaced_custom_object(
                group="karpenter.sh", version="v1beta1",
                namespace="karpenter", plural="nodepools", name=nodepool_name
            )

            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
            instance_types, azs, capacity_type = [], [], "spot"

            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    instance_types = req.get('values', [])
                if req.get('key') == 'topology.kubernetes.io/zone':
                    azs = req.get('values', [])
                if req.get('key') == 'karpenter.sh/capacity-type':
                    capacity_type = req.get('values', ['spot'])[0]

            in_fallback = self.is_in_fallback_mode(cluster_id)

            return {
                'status': 'active',
                'nodepool_name': nodepool_name,
                'instance_types': instance_types,
                'availability_zones': azs,
                'capacity_type': capacity_type,
                'in_fallback_mode': in_fallback,
                'last_updated': nodepool.get('metadata', {}).get('annotations', {}).get('last-updated'),
                'managed_by': nodepool.get('metadata', {}).get('labels', {}).get('managed-by')
            }

        except ApiException as e:
            if e.status == 404:
                return {'status': 'not_found', 'nodepool_name': nodepool_name, 'message': 'NodePool does not exist'}
            else:
                raise

        except Exception as e:
            logger.error(f"Failed to get NodePool status: {e}")
            return {'status': 'error', 'nodepool_name': nodepool_name, 'error': str(e)}
