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
        nodepool_name: str = "default",
        capacity_type: str = "spot"
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

            # v4.3 WIE observation: collect statistics on how many workloads would
            # change NodePool assignment. No enforcement in Phase 3 observation mode.
            try:
                from backend.core.redis_client import get_redis_client as _wie_redis_fn
                import json as _wie_json
                _wie_redis = _wie_redis_fn()
                _wie_would_change = {"stateful_od": 0, "stateless_spot": 0}
                for _wkey in (_wie_redis.scan_iter(f"spot:wie:classification:{cluster_id}:*", count=100)):
                    try:
                        _wd = _wie_json.loads(_wie_redis.get(_wkey) or b'{}')
                        if _wd.get("confidence_state") == "CONFIRMED":
                            _tier = _wd.get("tier", "Bronze")
                            _spot_f = _wd.get("spot_friendly", False)
                            if _tier in ("Platinum", "Gold"):
                                _wie_would_change["stateful_od"] += 1
                            elif _spot_f:
                                _wie_would_change["stateless_spot"] += 1
                    except Exception:
                        continue
                if any(_wie_would_change.values()):
                    logger.info(
                        f"[WIE observation] Karpenter NodePool assignment preview for {cluster.name}: "
                        f"stateful_od={_wie_would_change['stateful_od']} "
                        f"stateless_spot={_wie_would_change['stateless_spot']} "
                        f"(enforcement disabled — Phase 3 observation only)"
                    )
            except Exception as _wie_karp_err:
                logger.debug(f"WIE karpenter observation skipped: {_wie_karp_err}")

            updated = self._update_nodepool(
                api_client=api_client,
                nodepool_name=nodepool_name,
                instance_types=instance_types,
                azs=azs,
                cluster=cluster,
                capacity_type=capacity_type
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
                "apiVersion": "karpenter.sh/v1",
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
                        "updated-by": "ascpai-fallback",
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
                            "nodeClassRef": {
                                "group": "karpenter.k8s.aws",
                                "kind": "EC2NodeClass",
                                "name": "default"
                            }
                        }
                    },
                    "disruption": {
                        "consolidationPolicy": "WhenEmpty",
                        "consolidateAfter": "Never",
                        "expireAfter": "720h"
                    },
                    "limits": {"cpu": "1000", "memory": "1000Gi"}
                }
            }

            # Apply NodePool update
            try:
                custom_api.patch_cluster_custom_object(
                    group="karpenter.sh", version="v1",
                    plural="nodepools",
                    name=nodepool_name, body=nodepool_spec
                )
            except ApiException as e:
                if e.status == 404:
                    custom_api.create_cluster_custom_object(
                        group="karpenter.sh", version="v1",
                        plural="nodepools",
                        body=nodepool_spec
                    )
                else:
                    raise

            # Set 12-hour fallback TTL in Redis
            if self.redis:
                fallback_key = f"spot:ondemand_fallback:{cluster_id}"
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
                nodepool = custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1",
                    plural="nodepools",
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
                        "updated-by": "ascpai-fallback-revert"
                    }
                }
            }

            custom_api.patch_cluster_custom_object(
                group="karpenter.sh", version="v1",
                plural="nodepools",
                name=nodepool_name, body=patch
            )

            if self.redis:
                self.redis.delete(f"spot:ondemand_fallback:{cluster_id}")

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
        return bool(self.redis.exists(f"spot:ondemand_fallback:{cluster_id}"))

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
                # Fix #9: Resolve architecture-appropriate AMI for dry-run.
                # c8g/c7g (ARM64) require an arm64 AMI; x86 types require an x86 AMI.
                _ARM64_FAMILIES_DR = {
                    't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                    'c6gn', 'c6gd', 'c8gn', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
                }
                _family = candidate["instance_type"].split('.')[0]
                _dr_arch = "arm64" if _family in _ARM64_FAMILIES_DR else "x86_64"
                _dr_params = dict(
                    InstanceType=candidate["instance_type"],
                    DryRun=True,
                    MinCount=1,
                    MaxCount=1,
                )
                # Use SSM-resolved EKS-optimized AMI for the correct arch
                try:
                    ssm = self._get_ec2_client(region).meta.client
                    # Re-create as SSM client
                    import boto3 as _boto3_dr
                    _ssm_session = _boto3_dr.Session(region_name=region)
                    _ssm_c = _ssm_session.client('ssm', region_name=region)
                    _ami_path = (
                        f"/aws/service/eks/optimized-ami/1.31/amazon-linux-2{'023/' if _dr_arch == 'x86_64' else '-arm64/'}"
                        f"recommended/image_id"
                    )
                    _ami_resp = _ssm_c.get_parameter(Name=_ami_path)
                    _dr_params['ImageId'] = _ami_resp['Parameter']['Value']
                except Exception:
                    # Fallback: use DescribeImages to find latest EKS AMI
                    try:
                        _img_resp = ec2.describe_images(
                            Owners=['amazon'],
                            Filters=[
                                {'Name': 'name', 'Values': [f'amazon-eks-node-1.31-*']},
                                {'Name': 'architecture', 'Values': [_dr_arch]},
                                {'Name': 'state', 'Values': ['available']},
                            ],
                        )
                        _images = sorted(_img_resp.get('Images', []), key=lambda x: x.get('CreationDate', ''), reverse=True)
                        if _images:
                            _dr_params['ImageId'] = _images[0]['ImageId']
                    except Exception:
                        pass  # proceed without ImageId — may fail for ARM64 but worth trying
                ec2.run_instances(**_dr_params)
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
            nodepool = custom_api.get_cluster_custom_object(
                group="karpenter.sh",
                version="v1",
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
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh",
                version="v1",
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

        url = signer.generate_presigned_url(params, region_name=region, expires_in=900, operation_name='')
        token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8').rstrip('=')
        return token

    def _update_nodepool(
        self, api_client, nodepool_name: str,
        instance_types: List[str], azs: List[str],
        cluster: Cluster, capacity_type: str = "spot",
        consolidation_policy: Optional[str] = None,
        consolidate_after: Optional[str] = None,
    ) -> bool:
        """
        Updates Karpenter NodePool with ML-approved instance types.
        Includes rollback, retry logic, and circuit breaker checks.
        Automatically derives kubernetes.io/arch from the instance type
        families so both amd64 and arm64 nodes can be provisioned.

        Args:
            capacity_type: "spot" or "on-demand"
            consolidation_policy: "WhenEmpty" | "WhenEmptyOrUnderutilized" | None.
                When None, the existing NodePool's policy is preserved on update,
                and "WhenEmptyOrUnderutilized" is used for new NodePools.
            consolidate_after: "Never" | "30s" | None.
                When None, the existing value is preserved on update; defaults
                to "30s" for new NodePools.

        Returns:
            True if existing NodePool was updated, False if created new
        """
        # Check circuit breaker before attempting execution
        if self._check_circuit_breaker(cluster.id):
            raise Exception(f"Circuit breaker active for cluster {cluster.id} — execution blocked")

        # Derive architecture list from instance types
        _ARM64_FAMILIES = {
            't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
            'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
        }
        _archs = set()
        for itype in instance_types:
            family = itype.split('.')[0] if '.' in itype else itype
            if family in _ARM64_FAMILIES:
                _archs.add('arm64')
            else:
                _archs.add('amd64')
        arch_list = sorted(_archs) if _archs else ['amd64', 'arm64']

        try:
            custom_api = client.CustomObjectsApi(api_client)

            # Resolve consolidation settings: if not passed, preserve existing values;
            # fall back to safe defaults only when creating a brand-new NodePool.
            _existing_disruption: dict = {}
            try:
                _existing_np = custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1",
                    plural="nodepools", name=nodepool_name,
                )
                _existing_disruption = (
                    _existing_np.get("spec", {}).get("disruption", {})
                )
            except ApiException as _lookup_e:
                if _lookup_e.status != 404:
                    raise  # unexpected — re-raise

            _resolved_policy = (
                consolidation_policy
                or _existing_disruption.get("consolidationPolicy", "WhenEmpty")
            )
            _resolved_after = (
                consolidate_after
                or _existing_disruption.get("consolidateAfter", "Never")
            )

            # Bug 3 fix: only include disruption in the patch when the caller
            # explicitly requested a consolidation change.  For plain instance-type
            # updates on an *existing* NodePool we leave the disruption section out
            # so we don't race with patch_consolidation_policy() and overwrite a
            # recently-set WhenEmpty with a stale read-back.
            _has_explicit_disruption = (
                consolidation_policy is not None or consolidate_after is not None
            )

            _disruption_section = {
                "consolidationPolicy": _resolved_policy,
                "consolidateAfter": _resolved_after,
                "expireAfter": _existing_disruption.get("expireAfter", "720h"),
            }

            nodepool_spec = {
                "apiVersion": "karpenter.sh/v1",
                "kind": "NodePool",
                "metadata": {
                    "name": nodepool_name,
                    "labels": {"managed-by": "spot-optimizer", "ml-optimized": "true"},
                    "annotations": {
                        "last-updated": datetime.utcnow().isoformat(),
                        "updated-by": "ascpai-ml-pipeline"
                    }
                },
                "spec": {
                    "template": {
                        "spec": {
                            "requirements": [
                                {"key": "karpenter.sh/capacity-type", "operator": "In", "values": [capacity_type]},
                                {"key": "kubernetes.io/arch", "operator": "In", "values": arch_list},
                                {"key": "node.kubernetes.io/instance-type", "operator": "In", "values": instance_types},
                                {"key": "topology.kubernetes.io/zone", "operator": "In", "values": azs}
                            ],
                            "nodeClassRef": {
                                "group": "karpenter.k8s.aws",
                                "kind": "EC2NodeClass",
                                # K-7: read from cluster config instead of hardcoding 'default'
                                "name": (
                                    getattr(cluster, "ec2_node_class_name", None)
                                    or "default"
                                ),
                            }
                        }
                    },
                    "limits": {"cpu": "1000", "memory": "1000Gi"},
                    # K-8: weight controls Karpenter pool selection priority.
                    # OD pools (weight=100) are strongly preferred for OD-affinity pods.
                    # Spot pools (weight=10) are used for burst / spot-burst pods.
                    "weight": 100 if capacity_type == "on-demand" else 10,
                }
            }

            # Capture current state for rollback
            current_state = self._get_nodepool_state(api_client, nodepool_name)

            try:
                custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1",
                    plural="nodepools", name=nodepool_name
                )
                logger.info(f"Updating existing NodePool '{nodepool_name}' with retry logic")

                # Bug 3 fix: only include disruption in PATCH when explicitly requested.
                # This prevents overwriting a WhenEmpty policy set by
                # patch_consolidation_policy() via a stale read-back race.
                if _has_explicit_disruption:
                    nodepool_spec["spec"]["disruption"] = _disruption_section

                # Retry loop for PATCH operations
                # Enhancement 8: Non-blocking retries — attempt once, if it fails
                # raise immediately (caller uses metadata flag to retry next cycle
                # instead of blocking the Celery worker thread with time.sleep).
                try:
                    custom_api.patch_cluster_custom_object(
                        group="karpenter.sh", version="v1",
                        plural="nodepools",
                        name=nodepool_name, body=nodepool_spec
                    )
                    logger.info(f"NodePool PATCH succeeded on first attempt")
                    return True
                except Exception as e:
                    logger.warning(
                        f"NodePool PATCH failed: {e} — caller will retry next cycle"
                    )
                    self._restore_nodepool_state(api_client, nodepool_name, current_state)
                    self._record_execution_failure(cluster.id)
                    raise

            except ApiException as e:
                if e.status == 404:
                    # New NodePool — always include disruption with safe defaults
                    nodepool_spec["spec"]["disruption"] = _disruption_section
                    logger.info(f"Creating new NodePool '{nodepool_name}'")
                    custom_api.create_cluster_custom_object(
                        group="karpenter.sh", version="v1",
                        plural="nodepools",
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

            nodepool = custom_api.get_cluster_custom_object(
                group="karpenter.sh", version="v1",
                plural="nodepools", name=nodepool_name
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

    def detect_karpenter_in_cluster(self, cluster_id: str, db) -> dict:
        """
        Detect if Karpenter is installed in a cluster. Uses a 3-tier approach:
        1. Live agent heartbeat status (most authoritative — agent checks K8s pods every 30s)
        2. Short-term Redis cache (karpenter:detected:{cluster_id}, 120s TTL)
        3. DB column fallback (cluster.karpenter_mode)
        """
        try:
            from backend.core.redis_client import get_redis_client
            import json as _json

            redis = get_redis_client()

            # ── Tier 1: Live agent heartbeat status (refreshed every 30s) ──
            _live_key = f"karpenter:live_status:{cluster_id}"
            _live_raw = redis.get(_live_key) if redis else None
            if _live_raw:
                _live = _json.loads(_live_raw)
                _live_detected = _live.get('detected', False)

                from backend.models.cluster import Cluster
                cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
                _was_installed = cluster and cluster.karpenter_mode is not None
                _mode = cluster.karpenter_mode.value if cluster and cluster.karpenter_mode else 'none'

                if _live_detected:
                    result = {
                        'detected': True,
                        'cluster_id': cluster_id,
                        'karpenter_mode': _mode,
                        'source': 'live_agent',
                        'pods_running': _live.get('pods_running', 0),
                        'controller_healthy': _live.get('controller_healthy', False),
                    }
                else:
                    result = {
                        'detected': False,
                        'cluster_id': cluster_id,
                        'karpenter_mode': 'missing' if _was_installed else 'none',
                        'previously_installed': _was_installed,
                        'source': 'live_agent',
                        'error': _live.get('error'),
                        'pods_running': _live.get('pods_running', 0),
                    }

                # Update caches
                cache_key = f"karpenter:detected:{cluster_id}"
                redis.setex(cache_key, 120, _json.dumps(result))
                _installed_key = f"spot:karpenter:installed:{cluster_id}"
                if _live_detected:
                    redis.setex(_installed_key, 3600, _mode)
                elif _was_installed:
                    redis.delete(_installed_key)

                return result

            # ── Tier 2: Short-term detection cache ──
            cache_key = f"karpenter:detected:{cluster_id}"
            cached = redis.get(cache_key) if redis else None
            if cached:
                cached_result = _json.loads(cached)
                # Don't trust cached results from db_column source — they may be stale
                if cached_result.get('source') != 'db_column':
                    return cached_result

            # ── Tier 2.5: Direct K8s API check (fallback when agent can't call home) ──
            # The backend has direct K8s API access via EKS token auth.
            # Check for running Karpenter pods without needing the agent as middleman.
            from backend.models.cluster import Cluster
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return {'detected': False, 'reason': 'cluster_not_found'}

            karpenter_mode = cluster.karpenter_mode.value if cluster.karpenter_mode else 'none'

            try:
                _api_client = self._get_k8s_client(cluster)
                from kubernetes import client as _k8s_det
                _v1 = _k8s_det.CoreV1Api(_api_client)
                _karp_pods = _v1.list_namespaced_pod(
                    namespace="karpenter",
                    label_selector="app.kubernetes.io/name=karpenter",
                    timeout_seconds=10,
                )
                _running_karp = [
                    p for p in _karp_pods.items
                    if p.status and p.status.phase == 'Running'
                ]
                if _running_karp:
                    result = {
                        'detected': True,
                        'cluster_id': cluster_id,
                        'karpenter_mode': karpenter_mode,
                        'source': 'k8s_api_direct',
                        'pods_running': len(_running_karp),
                        'controller_healthy': True,
                    }
                    # Populate both caches so rebalancer and other callers see it
                    if redis:
                        redis.setex(cache_key, 120, _json.dumps(result))
                        _installed_key = f"spot:karpenter:installed:{cluster_id}"
                        redis.setex(_installed_key, 3600, karpenter_mode)
                    logger.info(
                        f"[karpenter] Direct K8s check: {len(_running_karp)} Karpenter "
                        f"pod(s) Running on cluster {cluster.name}"
                    )
                    return result
                else:
                    logger.info(
                        f"[karpenter] Direct K8s check: no Running Karpenter pods "
                        f"found on cluster {cluster.name}"
                    )
            except Exception as _k8s_det_err:
                logger.debug(
                    f"[karpenter] Direct K8s Karpenter check failed for "
                    f"{cluster.name}: {_k8s_det_err}"
                )

            # ── Tier 3: DB column fallback (no live data, no K8s access) ──
            result = {
                'detected': False,
                'cluster_id': cluster_id,
                'karpenter_mode': karpenter_mode,
                'source': 'db_column',
                'warning': 'No live agent data or direct K8s access — cannot confirm Karpenter status',
            }
            if redis:
                redis.setex(cache_key, 120, _json.dumps(result))
                _installed_key = f"spot:karpenter:installed:{cluster_id}"
                redis.delete(_installed_key)

            return result

        except Exception as e:
            logger.error(f"[karpenter] detect_karpenter_in_cluster failed: {e}")
            return {'detected': False, 'error': str(e)}

    def install_karpenter(self, cluster_id: str, db) -> Dict:
        """
        Queue an INSTALL_KARPENTER AgentAction to install Karpenter via Helm.

        Guards:
          1. Already-installed: if detect_karpenter_in_cluster() returns detected=True, skip.
          2. Duplicate in-progress: if a PENDING/PICKED_UP INSTALL_KARPENTER action exists, skip.
          3. Sets spot:karpenter_installing:{cluster_id} Redis flag (TTL=600s) so
             get_karpenter_install_status() can return install_in_progress=True.

        Returns dict with success, action_id, message, or error.
        """
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return {"success": False, "error": f"Cluster {cluster_id} not found"}

        # ── Already-installed guard ────────────────────────────────────────────
        detection = self.detect_karpenter_in_cluster(cluster_id, db)
        if detection.get("detected"):
            logger.info(
                f"[karpenter] install_karpenter called but Karpenter already running "
                f"on cluster {cluster_id} (source={detection.get('source')}) — skipping"
            )
            return {
                "success": True,
                "already_installed": True,
                "message": "Karpenter is already installed and running",
                "cluster_id": cluster_id,
                "karpenter_mode": detection.get("karpenter_mode"),
                "pods_running": detection.get("pods_running", 0),
            }

        # ── Duplicate in-progress Redis flag ──────────────────────────────────
        _install_key = f"spot:karpenter_installing:{cluster_id}"
        if self.redis:
            try:
                if self.redis.exists(_install_key):
                    return {
                        "success": True,
                        "install_in_progress": True,
                        "message": "Karpenter installation is already in progress",
                        "cluster_id": cluster_id,
                    }
            except Exception:
                pass

        # ── Duplicate in-progress DB action guard ─────────────────────────────
        pending_action = (
            db.query(AgentAction)
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.INSTALL_KARPENTER,
                AgentAction.status.in_([
                    AgentActionStatus.PENDING,
                    AgentActionStatus.PICKED_UP,
                ]),
            )
            .first()
        )
        if pending_action:
            logger.info(
                f"[karpenter] INSTALL_KARPENTER action {pending_action.id} already in "
                f"progress for cluster {cluster_id} — skipping duplicate"
            )
            return {
                "success": True,
                "install_in_progress": True,
                "action_id": pending_action.id,
                "message": "Karpenter installation is already in progress",
            }

        # ── Set in-progress flag ───────────────────────────────────────────────
        if self.redis:
            try:
                self.redis.setex(_install_key, 600, "1")
                self.redis.delete(f"karpenter:detected:{cluster_id}")
                self.redis.delete(f"karpenter:live_status:{cluster_id}")
            except Exception as _re:
                logger.warning(f"[karpenter] install flag write failed: {_re}")

        try:
            action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.INSTALL_KARPENTER,
                status=AgentActionStatus.PENDING,
                payload={"cluster_name": cluster.name},
            )
            db.add(action)
            db.commit()
            db.refresh(action)
            logger.info(
                f"[karpenter] Queued INSTALL_KARPENTER action {action.id} "
                f"for cluster {cluster_id}"
            )
            # K-1: Flag that a default NodePool must be bootstrapped after install completes.
            # auto_rebalancer checks this flag each cycle and calls bootstrap_default_nodepool().
            if self.redis:
                try:
                    self.redis.setex(
                        f"spot:karpenter_nodepool_bootstrap_needed:{cluster_id}", 7200, "1"
                    )
                except Exception:
                    pass
            return {
                "success": True,
                "action_id": action.id,
                "message": "Karpenter installation queued — agent will run Helm install",
                "bootstrap_needed": True,
            }
        except Exception as exc:
            logger.error(f"[karpenter] install_karpenter failed for cluster {cluster_id}: {exc}")
            if self.redis:
                try:
                    self.redis.delete(_install_key)
                except Exception:
                    pass
            return {"success": False, "error": str(exc)}

    def get_karpenter_install_status(self, cluster_id: str, db) -> Dict:
        """
        Return combined Karpenter install status (mirrors keda_service.get_install_status).

        Combines:
          - detect_karpenter_in_cluster() for live detection
          - spot:karpenter_installing:{cluster_id} Redis flag for in-progress state
          - Latest INSTALL_KARPENTER / UNINSTALL_KARPENTER AgentAction status
        """
        from backend.models.agent_action import AgentAction, AgentActionType

        install_in_progress = False
        if self.redis:
            try:
                install_in_progress = bool(
                    self.redis.exists(f"spot:karpenter_installing:{cluster_id}")
                )
            except Exception:
                pass

        action_status = None
        action_id = None
        try:
            latest_action = (
                db.query(AgentAction)
                .filter(
                    AgentAction.cluster_id == cluster_id,
                    AgentAction.action_type.in_([
                        AgentActionType.INSTALL_KARPENTER,
                        AgentActionType.UNINSTALL_KARPENTER,
                    ]),
                )
                .order_by(AgentAction.created_at.desc())
                .first()
            )
            if latest_action:
                action_status = (
                    latest_action.status.value
                    if hasattr(latest_action.status, "value")
                    else str(latest_action.status)
                )
                action_id = latest_action.id
                # Clear the installing flag if the action has completed or failed
                if (
                    install_in_progress
                    and action_status in ("COMPLETED", "FAILED", "completed", "failed")
                ):
                    if self.redis:
                        try:
                            self.redis.delete(f"spot:karpenter_installing:{cluster_id}")
                        except Exception:
                            pass
                    install_in_progress = False
        except Exception as exc:
            logger.warning(
                f"[karpenter] get_karpenter_install_status action query failed: {exc}"
            )

        detection = self.detect_karpenter_in_cluster(cluster_id, db)
        return {
            "cluster_id":           cluster_id,
            "detected":             detection.get("detected", False),
            "karpenter_mode":       detection.get("karpenter_mode", "none"),
            "source":               detection.get("source"),
            "pods_running":         detection.get("pods_running", 0),
            "controller_healthy":   detection.get("controller_healthy", False),
            "install_in_progress":  install_in_progress,
            "action_status":        action_status,
            "action_id":            action_id,
            "error":                detection.get("error"),
        }

    def bootstrap_default_nodepool(self, cluster_id: str) -> Dict:
        """
        K-1: Create a safe 'spot-general' NodePool after Karpenter install if none exists.

        Called by auto_rebalancer when spot:karpenter_nodepool_bootstrap_needed:{cluster_id}
        is set. Skipped if any spot NodePool already exists. Safe to call multiple times.

        Returns dict with success, created (bool), nodepool_name, or error.
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return {"success": False, "error": f"Cluster {cluster_id} not found"}

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            # Check if any spot NodePool already exists
            existing = custom_api.list_cluster_custom_object(
                group="karpenter.sh", version="v1", plural="nodepools"
            )
            spot_pools = [
                item for item in existing.get("items", [])
                if any(
                    req.get("key") == "karpenter.sh/capacity-type"
                    and "spot" in (req.get("values") or [])
                    for req in (
                        item.get("spec", {})
                        .get("template", {})
                        .get("spec", {})
                        .get("requirements", [])
                    )
                )
            ]
            if spot_pools:
                logger.info(
                    f"[karpenter] bootstrap_default_nodepool: {len(spot_pools)} spot NodePool(s) "
                    f"already exist for cluster {cluster_id} — skipping bootstrap"
                )
                if self.redis:
                    self.redis.delete(f"spot:karpenter_nodepool_bootstrap_needed:{cluster_id}")
                return {"success": True, "created": False, "existing_pools": len(spot_pools)}

            # Determine safe initial instance types from region (diverse set for first bootstrap)
            region = getattr(cluster, "region", "us-east-1") or "us-east-1"
            _safe_types = ["m5.xlarge", "m5.2xlarge", "c5.xlarge"]
            azs = self._get_region_azs(region)

            logger.info(
                f"[karpenter] K-1: bootstrapping 'spot-general' NodePool for cluster {cluster_id} "
                f"region={region} instance_types={_safe_types}"
            )
            self._update_nodepool(
                api_client=api_client,
                nodepool_name="spot-general",
                instance_types=_safe_types,
                azs=azs,
                cluster=cluster,
                capacity_type="spot",
                consolidation_policy="WhenEmptyOrUnderutilized",
                consolidate_after="30s",
            )

            # Change 7: Also bootstrap od-general NodePool for MNG takeover path.
            # od-general targets on-demand capacity only — used during takeover to
            # receive workloads from MNG nodes one at a time before spot migration.
            _od_safe_types = ["m5.xlarge", "m5.2xlarge", "m5.4xlarge"]
            try:
                self._update_nodepool(
                    api_client=api_client,
                    nodepool_name="od-general",
                    instance_types=_od_safe_types,
                    azs=azs,
                    cluster=cluster,
                    capacity_type="on-demand",
                    consolidation_policy="WhenEmpty",
                    consolidate_after="60s",
                )
                logger.info(
                    f"[karpenter] K-1: 'od-general' NodePool created for cluster {cluster_id}"
                )
            except Exception as _od_exc:
                logger.warning(
                    f"[karpenter] K-1: 'od-general' NodePool creation failed (non-fatal): {_od_exc}"
                )

            # Clear the bootstrap flag
            if self.redis:
                self.redis.delete(f"spot:karpenter_nodepool_bootstrap_needed:{cluster_id}")

            logger.info(
                f"[karpenter] K-1: 'spot-general' NodePool created for cluster {cluster_id}"
            )
            return {"success": True, "created": True, "nodepool_name": "spot-general", "od_nodepool": "od-general"}

        except Exception as exc:
            logger.error(f"[karpenter] bootstrap_default_nodepool failed for {cluster_id}: {exc}")
            return {"success": False, "error": str(exc)}

    def add_allowed_instance_type_all_spot(self, cluster_id: str, instance_type: str):
        """Add instance type to ALL spot-capable NodePools so Karpenter provisions
        the correct type regardless of which NodePool the trigger pod matches.

        Returns (success: bool, patched_nodepool_names: list[str]).
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False, []
            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)
            nps = custom_api.list_cluster_custom_object(
                group="karpenter.sh", version="v1", plural="nodepools",
            )
            spot_np_names = []
            for np_item in nps.get("items", []):
                np_name = np_item.get("metadata", {}).get("name", "")
                reqs = np_item.get("spec", {}).get("template", {}).get("spec", {}).get("requirements", [])
                for r in reqs:
                    if r.get("key") == "karpenter.sh/capacity-type" and "spot" in (r.get("values") or []):
                        spot_np_names.append(np_name)
                        break
            if not spot_np_names:
                spot_np_names = ["default"]
            any_ok = False
            patched = []
            for np_name in spot_np_names:
                ok = self.add_allowed_instance_type(cluster_id, instance_type, nodepool_name=np_name)
                if ok:
                    any_ok = True
                    patched.append(np_name)
            return any_ok, patched if patched else spot_np_names
        except Exception as e:
            logger.error(f"[karpenter] add_allowed_instance_type_all_spot failed: {e}")
            result = self.add_allowed_instance_type(cluster_id, instance_type)
            return result, ["default"]

    def set_exact_instance_type_for_plan(self, cluster_id: str, instance_type: str, nodepool_name: str = "default") -> bool:
        return self.add_allowed_instance_type(
            cluster_id=cluster_id,
            instance_type=instance_type,
            nodepool_name=nodepool_name,
            exact=True,
        )

    def add_allowed_instance_type(self, cluster_id: str, instance_type: str, nodepool_name: str = "default", exact: bool = False) -> bool:
        """
        Inject an instance type into a NodePool using full-replace semantics.

        On the first call for a given (cluster, nodepool) pair, the current types are
        snapshotted as the **baseline** in Redis (key:
        ``karpenter:nodepool_baseline:{cluster_id}:{nodepool_name}``).  Every subsequent
        non-exact call PATCHes the NodePool to exactly (baseline ∪ {instance_type}), so the
        list never grows beyond one injected type beyond what was there originally.
        When exact=True, PATCHes the NodePool to exactly [instance_type]. This is the
        execution-plan path and prevents Karpenter from choosing any baseline/fallback type.

        Returns True on success, False if NodePool not found or update fails.
        Idempotent: if the type is already present in the effective set, returns True.
        """
        _BASELINE_KEY = f"karpenter:nodepool_baseline:{cluster_id}:{nodepool_name}"
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                logger.error(f"[karpenter] add_allowed_instance_type: cluster {cluster_id} not found")
                return False

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            # Read current NodePool
            try:
                nodepool = custom_api.get_cluster_custom_object(
                    group="karpenter.sh",
                    version="v1",
                    plural="nodepools",
                    name=nodepool_name,
                )
            except ApiException as e:
                if e.status == 404:
                    logger.warning(f"[karpenter] NodePool '{nodepool_name}' not found for cluster {cluster_id}")
                    return False
                raise

            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])

            # ── Baseline snapshot (first call only) ──────────────────────────────────
            _baseline_types: list[str] = []
            _baseline_from_redis = False
            if self.redis:
                _raw = self.redis.get(_BASELINE_KEY)
                if _raw:
                    _baseline_types = json.loads(_raw)
                    _baseline_from_redis = True

            if not _baseline_from_redis:
                # Snapshot what is currently in the NodePool before we touch it.
                for req in requirements:
                    if req.get('key') == 'node.kubernetes.io/instance-type':
                        _baseline_types = sorted(req.get('values', []))
                        break
                if self.redis:
                    self.redis.setex(_BASELINE_KEY, 86400, json.dumps(_baseline_types))  # 24h TTL (W3.0c)
                    logger.info(
                        f"[karpenter] Snapshotted baseline types for NodePool '{nodepool_name}' "
                        f"cluster {cluster_id}: {_baseline_types}"
                    )

            # ── Build effective set ─────────────────────────────────────────────────
            _effective_types = [instance_type] if exact else sorted(set(_baseline_types) | {instance_type})

            # Idempotent check — skip patch if nothing changes
            _current_types: list[str] = []
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    _current_types = sorted(req.get('values', []))
                    break
            if _current_types == _effective_types:
                logger.info(
                    f"[karpenter] {instance_type} already in NodePool '{nodepool_name}' "
                    f"for cluster {cluster_id} — no patch needed"
                )
                return True

            # Update the instance-type requirement to the effective set
            _req_found = False
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    req['values'] = _effective_types
                    _req_found = True
                    break
            if not _req_found:
                requirements.append({
                    'key': 'node.kubernetes.io/instance-type',
                    'operator': 'In',
                    'values': _effective_types,
                })

            # Keep kubernetes.io/arch in sync with the effective instance types
            _ARM64_FAMILIES = {
                't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
            }
            _derived_archs: set[str] = set()
            for _it in _effective_types:
                _fam = _it.split('.')[0] if '.' in _it else _it
                _derived_archs.add('arm64' if _fam in _ARM64_FAMILIES else 'amd64')
            _arch_list = sorted(_derived_archs) if _derived_archs else ['amd64', 'arm64']
            _arch_req_found = False
            for req in requirements:
                if req.get('key') == 'kubernetes.io/arch':
                    req['values'] = _arch_list
                    _arch_req_found = True
                    break
            if not _arch_req_found:
                requirements.append({'key': 'kubernetes.io/arch', 'operator': 'In', 'values': _arch_list})

            # ── Bug 4 fix: freeze Karpenter consolidation during active injection ──
            # Save the original consolidateAfter value so remove_allowed_instance_type()
            # can restore it later.  Set consolidateAfter=Never so Karpenter does not
            # consolidate (i.e. replace nodes with cheaper types) while the rebalancer
            # is mid-migration.
            _CONSOLIDATE_AFTER_KEY = (
                f"karpenter:nodepool_consolidate_after_baseline:{cluster_id}:{nodepool_name}"
            )
            if self.redis and not self.redis.exists(_CONSOLIDATE_AFTER_KEY):
                _original_after = (
                    nodepool.get('spec', {}).get('disruption', {}).get('consolidateAfter', '30s')
                )
                self.redis.set(_CONSOLIDATE_AFTER_KEY, _original_after, ex=86400)  # 24h TTL — prevents orphaned freeze
                logger.info(
                    f"[karpenter] Saved consolidateAfter baseline '{_original_after}' "
                    f"for NodePool '{nodepool_name}' cluster {cluster_id}"
                )

            # Patch the NodePool: update instance types AND freeze consolidation
            patch_body = {
                "spec": {
                    "template": {"spec": {"requirements": requirements}},
                    "disruption": {"consolidateAfter": "Never"},
                }
            }
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh", version="v1",
                plural="nodepools", name=nodepool_name,
                body=patch_body,
            )

            # ── Read-back verification ────────────────────────────────────────────────
            try:
                verified_np = custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1", plural="nodepools", name=nodepool_name,
                )
                verified_reqs = (
                    verified_np.get('spec', {}).get('template', {})
                    .get('spec', {}).get('requirements', [])
                )
                _verified_types: list[str] = []
                _has_spot_capacity = False
                for vr in verified_reqs:
                    if vr.get('key') == 'node.kubernetes.io/instance-type':
                        _verified_types = vr.get('values', [])
                    if vr.get('key') == 'karpenter.sh/capacity-type':
                        _has_spot_capacity = 'spot' in (vr.get('values') or [])
                if instance_type not in _verified_types:
                    logger.error(
                        f"[karpenter] VERIFICATION FAILED: {instance_type} not in NodePool "
                        f"'{nodepool_name}' after patch (found: {_verified_types[:5]})"
                    )
                    return False
                if not _has_spot_capacity:
                    logger.warning(
                        f"[karpenter] NodePool '{nodepool_name}' does NOT have 'spot' in "
                        f"karpenter.sh/capacity-type — Karpenter may not provision spot nodes"
                    )
                logger.info(
                    f"[karpenter] VERIFIED: {instance_type} confirmed in NodePool '{nodepool_name}' "
                    f"for cluster {cluster_id} (effective_types={_effective_types}, "
                    f"spot_capable={_has_spot_capacity})"
                )
            except Exception as ve:
                logger.warning(f"[karpenter] Read-back verification failed: {ve} — proceeding with caution")

            logger.info(
                f"[karpenter] Added {instance_type} to NodePool '{nodepool_name}' "
                f"for cluster {cluster_id} (effective_types={_effective_types})"
            )
            # W3.0d: per-injection tracking key (2h TTL).
            # Reconciliation task scans spot:injected_type:* to find orphaned injections.
            if self.redis:
                _inject_key = f"spot:injected_type:{cluster_id}:{nodepool_name}:{instance_type}"
                self.redis.setex(_inject_key, 7200, json.dumps({
                    "cluster_id": cluster_id,
                    "nodepool_name": nodepool_name,
                    "instance_type": instance_type,
                    "injected_at": datetime.utcnow().isoformat(),
                }))
            return True

        except Exception as e:
            logger.error(f"[karpenter] add_allowed_instance_type failed: {e}")
            return False

    def remove_allowed_instance_type(self, cluster_id: str, instance_type: str, nodepool_name: str = "default") -> bool:
        """
        Restore the NodePool's instance-type list to the pre-injection baseline.

        Reads the baseline snapshot stored by ``add_allowed_instance_type`` from Redis
        (key: ``karpenter:nodepool_baseline:{cluster_id}:{nodepool_name}``) and PATCHes
        the NodePool back to exactly that list, regardless of how many types were
        injected since.  Also deletes the Redis baseline key so the next injection
        starts a fresh snapshot cycle.

        Returns True on success, False on failure.
        """
        _BASELINE_KEY = f"karpenter:nodepool_baseline:{cluster_id}:{nodepool_name}"
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False

            # ── Resolve baseline ──────────────────────────────────────────────────────
            _baseline_types: list[str] | None = None
            if self.redis:
                _raw = self.redis.get(_BASELINE_KEY)
                if _raw:
                    _baseline_types = json.loads(_raw)

            if _baseline_types is None:
                # No baseline means add_allowed_instance_type was never called (or Redis
                # lost the key).  Fall back to a single-type removal to avoid leaving
                # an orphan type if we can.
                logger.warning(
                    f"[karpenter] No baseline found for NodePool '{nodepool_name}' "
                    f"cluster {cluster_id} — falling back to single-type removal"
                )
                return self._remove_single_instance_type(cluster_id, instance_type, nodepool_name)

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            try:
                nodepool = custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1",
                    plural="nodepools", name=nodepool_name,
                )
            except ApiException as e:
                if e.status == 404:
                    # NodePool gone — clear stale baseline key and return success
                    if self.redis:
                        self.redis.delete(_BASELINE_KEY)
                    return True
                raise

            if not _baseline_types:
                # Baseline was an empty list — nothing to restore; keep NodePool untouched.
                logger.info(
                    f"[karpenter] Baseline is empty for NodePool '{nodepool_name}' "
                    f"cluster {cluster_id} — nothing to restore"
                )
                if self.redis:
                    self.redis.delete(_BASELINE_KEY)
                return True

            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])

            # Replace the instance-type requirement with the baseline list
            _req_found = False
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    req['values'] = sorted(_baseline_types)
                    _req_found = True
                    break
            if not _req_found:
                requirements.append({
                    'key': 'node.kubernetes.io/instance-type',
                    'operator': 'In',
                    'values': sorted(_baseline_types),
                })

            # Re-derive kubernetes.io/arch from baseline types
            _ARM64_FAMILIES = {
                't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
            }
            _derived_archs: set[str] = set()
            for _it in _baseline_types:
                _fam = _it.split('.')[0] if '.' in _it else _it
                _derived_archs.add('arm64' if _fam in _ARM64_FAMILIES else 'amd64')
            _arch_list = sorted(_derived_archs) if _derived_archs else ['amd64', 'arm64']
            for req in requirements:
                if req.get('key') == 'kubernetes.io/arch':
                    req['values'] = _arch_list
                    break

            # ── Bug 4 fix: restore consolidateAfter to pre-injection baseline ──
            _CONSOLIDATE_AFTER_KEY = (
                f"karpenter:nodepool_consolidate_after_baseline:{cluster_id}:{nodepool_name}"
            )
            _restore_after = "30s"  # safe default if baseline was lost
            if self.redis:
                _raw_after = self.redis.get(_CONSOLIDATE_AFTER_KEY)
                if _raw_after:
                    _restore_after = _raw_after if isinstance(_raw_after, str) else _raw_after.decode()
                self.redis.delete(_CONSOLIDATE_AFTER_KEY)

            patch_body = {
                "spec": {
                    "template": {"spec": {"requirements": requirements}},
                    "disruption": {"consolidateAfter": _restore_after},
                }
            }
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh", version="v1",
                plural="nodepools", name=nodepool_name,
                body=patch_body,
            )
            logger.info(
                f"[karpenter] Restored NodePool '{nodepool_name}' to baseline types "
                f"{_baseline_types} for cluster {cluster_id}"
            )

            # Clear the baseline key so the next injection starts a fresh cycle
            if self.redis:
                self.redis.delete(_BASELINE_KEY)

            return True

        except Exception as e:
            logger.error(f"[karpenter] remove_allowed_instance_type failed: {e}")
            return False

    def _remove_single_instance_type(
        self, cluster_id: str, instance_type: str, nodepool_name: str
    ) -> bool:
        """Fallback: remove a single instance type from a NodePool (no baseline required)."""
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            try:
                nodepool = custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1",
                    plural="nodepools", name=nodepool_name,
                )
            except ApiException as e:
                if e.status == 404:
                    return True
                raise

            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    values = set(req.get('values', []))
                    if instance_type not in values:
                        return True
                    if len(values) <= 1:
                        logger.warning(
                            f"[karpenter] Cannot remove {instance_type} — only type in '{nodepool_name}'"
                        )
                        return False
                    values.discard(instance_type)
                    req['values'] = sorted(values)
                    break
            else:
                return True

            # Re-derive arch
            _ARM64_FAMILIES = {
                't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
            }
            _remaining: set[str] = set()
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    _remaining.update(req.get('values', []))
            _derived_archs = set()
            for _it in _remaining:
                _fam = _it.split('.')[0] if '.' in _it else _it
                _derived_archs.add('arm64' if _fam in _ARM64_FAMILIES else 'amd64')
            _arch_list = sorted(_derived_archs) if _derived_archs else ['amd64', 'arm64']
            for req in requirements:
                if req.get('key') == 'kubernetes.io/arch':
                    req['values'] = _arch_list
                    break

            patch_body = {"spec": {"template": {"spec": {"requirements": requirements}}}}
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh", version="v1",
                plural="nodepools", name=nodepool_name,
                body=patch_body,
            )
            logger.info(
                f"[karpenter] (fallback) Removed {instance_type} from NodePool '{nodepool_name}' "
                f"for cluster {cluster_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[karpenter] _remove_single_instance_type failed: {e}")
            return False

    def patch_node_pool_allowed_types(
        self, cluster_id: str, instance_types: list, db,
        consolidation_policy: Optional[str] = None,
        consolidate_after: Optional[str] = None,
    ) -> dict:
        """
        Update NodePool instance-type requirements with a new allowed list.
        Directly patches the NodePool via K8s API (no longer creates an AgentAction).

        Bug 2 fix: now accepts consolidation_policy / consolidate_after so callers
        can atomically set types + disruption policy in one _update_nodepool() call.
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return {'status': 'error', 'error': f'Cluster {cluster_id} not found'}

            api_client = self._get_k8s_client(cluster)
            updated = self._update_nodepool(
                api_client=api_client,
                nodepool_name="default",
                instance_types=instance_types,
                azs=[],
                cluster=cluster,
                consolidation_policy=consolidation_policy,
                consolidate_after=consolidate_after,
            )
            return {
                'status': 'success',
                'instance_types': instance_types,
            }
        except Exception as e:
            logger.error(f"[karpenter] patch_node_pool_allowed_types failed: {e}")
            return {'status': 'error', 'error': str(e)}

    def patch_consolidation_policy(
        self,
        cluster_id: str,
        policy: str,
        nodepool_name: str = "default",
        consolidate_after: Optional[str] = None,
    ) -> dict:
        """
        Patch the disruption fields of a NodePool.

        Args:
            cluster_id: Cluster database ID
            policy: "WhenEmpty" or "WhenEmptyOrUnderutilized"
            nodepool_name: NodePool name (default: "default")
            consolidate_after: Optional consolidateAfter value, e.g. "Never" or "30s".
                               If omitted, that field is left unchanged.

        Returns:
            {"status": "success"} or {"status": "error"/"not_found", "error": str}
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return {'status': 'error', 'error': f'Cluster {cluster_id} not found'}

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            _disruption_patch: dict = {"consolidationPolicy": policy}
            if consolidate_after is not None:
                _disruption_patch["consolidateAfter"] = consolidate_after

            patch_body = {"spec": {"disruption": _disruption_patch}}
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh",
                version="v1",
                plural="nodepools",
                name=nodepool_name,
                body=patch_body,
            )
            logger.info(
                f"[karpenter] Patched NodePool '{nodepool_name}' disruption → "
                f"consolidationPolicy={policy}"
                + (f", consolidateAfter={consolidate_after}" if consolidate_after else "")
                + f" for cluster {cluster_id}"
            )
            return {'status': 'success', 'consolidation_policy': policy, 'consolidate_after': consolidate_after}
        except ApiException as e:
            if e.status == 404:
                logger.warning(
                    f"[karpenter] NodePool '{nodepool_name}' not found for cluster {cluster_id} "
                    f"— cannot patch consolidation policy"
                )
                return {'status': 'not_found', 'error': f'NodePool {nodepool_name} not found'}
            logger.error(f"[karpenter] patch_consolidation_policy failed: {e}")
            return {'status': 'error', 'error': str(e)}
        except Exception as e:
            logger.error(f"[karpenter] patch_consolidation_policy failed: {e}")
            return {'status': 'error', 'error': str(e)}

    # ── Spot trigger pod management ──────────────────────────────────────
    # Karpenter only provisions nodes when there are pending pods.
    # Existing EKS managed node group nodes are NOT managed by Karpenter,
    # so consolidation alone won't trigger spot provisioning.
    # These methods create/delete a lightweight "trigger" pod with a
    # nodeSelector for spot capacity, forcing Karpenter to provision.

    def create_spot_trigger_pod(
        self,
        cluster_id: str,
        pod_name: str,
        target_instance_type: str = "",
        nodepool_name: str = "default",
        exclude_nodes: list = None,
        cpu_request: str = "100m",
        memory_request: str = "128Mi",
    ) -> bool:
        """Create a lightweight pod requesting spot capacity to trigger Karpenter provisioning.

        Args:
            cluster_id: Cluster DB id
            pod_name: Unique name for the trigger pod
            target_instance_type: The recommended instance type (e.g. 'c7g.medium').
                When provided, the pod's nodeSelector constrains Karpenter to launch
                ONLY this type, preventing it from picking the cheapest type in the
                NodePool (e.g. c5.large instead of c7g.medium).
            nodepool_name: Which Karpenter NodePool to target.  Defaults to 'default'.
                Added to nodeSelector as 'karpenter.sh/nodepool' so the trigger pod
                lands on the correct NodePool — not 'stateless-spot' or any other pool.
            exclude_nodes: List of node names where the trigger pod must NOT be
                scheduled.  The caller must have already labelled these nodes with
                'spot-optimizer.io/existing-node=true'.  The trigger pod uses
                nodeAffinity DoesNotExist on that label so Karpenter provisions a
                brand-new node rather than placing the pod on an existing one.
                (kubernetes.io/hostname is a restricted label in Karpenter and
                cannot be used in nodeAffinity.)
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False

            api_client = self._get_k8s_client(cluster)
            v1 = client.CoreV1Api(api_client)

            # Build nodeSelector: always require spot + target the specific NodePool.
            # When target_instance_type is provided, bind the pod to that EXACT type
            # so Karpenter cannot substitute a cheaper/different instance type that
            # happens to be allowed in the NodePool.  If the NodePool sync removes
            # this type, Karpenter will throw FailedScheduling instead of pivoting.
            node_selector = {
                "karpenter.sh/capacity-type": "spot",
                "karpenter.sh/nodepool": nodepool_name,
            }
            if target_instance_type:
                node_selector["node.kubernetes.io/instance-type"] = target_instance_type

            # Build affinity: exclude existing nodes via a custom label that
            # Karpenter will NOT set on newly-provisioned nodes.
            node_affinity = None
            if exclude_nodes:
                node_affinity = client.V1NodeAffinity(
                    required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                        node_selector_terms=[
                            client.V1NodeSelectorTerm(
                                match_expressions=[
                                    client.V1NodeSelectorRequirement(
                                        key="spot-optimizer.io/existing-node",
                                        operator="DoesNotExist",
                                    ),
                                ],
                            ),
                        ],
                    ),
                )

            pod = client.V1Pod(
                metadata=client.V1ObjectMeta(
                    name=pod_name,
                    namespace="default",
                    labels={
                        "app": "spot-trigger",
                        "managed-by": "spot-optimizer",
                        "trigger-id": pod_name,
                    },
                ),
                spec=client.V1PodSpec(
                    node_selector=node_selector,
                    tolerations=[
                        client.V1Toleration(operator="Exists"),
                    ],
                    affinity=client.V1Affinity(
                        node_affinity=node_affinity,
                        pod_anti_affinity=client.V1PodAntiAffinity(
                            required_during_scheduling_ignored_during_execution=[
                                client.V1PodAffinityTerm(
                                    label_selector=client.V1LabelSelector(
                                        match_labels={"app": "spot-trigger"},
                                    ),
                                    topology_key="kubernetes.io/hostname",
                                ),
                            ],
                        ),
                    ),
                    containers=[
                        client.V1Container(
                            name="trigger",
                            image="public.ecr.aws/docker/library/busybox:latest",
                            command=["sleep", "3600"],
                            resources=client.V1ResourceRequirements(
                                requests={"cpu": cpu_request, "memory": memory_request},
                            ),
                        ),
                    ],
                    termination_grace_period_seconds=0,
                ),
            )
            v1.create_namespaced_pod(namespace="default", body=pod)
            logger.info(
                f"[karpenter] Created spot trigger pod '{pod_name}' in cluster {cluster.name} "
                f"(nodepool={nodepool_name}, instance_type={target_instance_type or 'any'})"
            )
            return True
        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.info(f"[karpenter] Trigger pod '{pod_name}' already exists")
                return True
            logger.warning(f"[karpenter] Failed to create trigger pod: {e}")
            return False
        except Exception as e:
            logger.warning(f"[karpenter] Failed to create trigger pod: {e}")
            return False

    def delete_spot_trigger_pod(self, cluster_id: str, pod_name: str) -> bool:
        """Delete a spot trigger pod after the spot node has joined."""
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False

            api_client = self._get_k8s_client(cluster)
            v1 = client.CoreV1Api(api_client)
            v1.delete_namespaced_pod(
                name=pod_name,
                namespace="default",
                grace_period_seconds=0,
            )
            logger.info(f"[karpenter] Deleted spot trigger pod '{pod_name}' from cluster {cluster.name}")
            return True
        except ApiException as e:
            if e.status == 404:
                return True  # Already gone
            logger.warning(f"[karpenter] Failed to delete trigger pod: {e}")
            return False
        except Exception as e:
            logger.warning(f"[karpenter] Failed to delete trigger pod: {e}")
            return False
