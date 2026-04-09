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
                        "consolidationPolicy": "WhenEmptyOrUnderutilized",
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
        Automatically derives kubernetes.io/arch from the instance type
        families so both amd64 and arm64 nodes can be provisioned.

        Args:
            capacity_type: "spot" or "on-demand"

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
                                "name": "default"
                            }
                        }
                    },
                    "disruption": {"consolidationPolicy": "WhenEmptyOrUnderutilized", "expireAfter": "720h"},
                    "limits": {"cpu": "1000", "memory": "1000Gi"}
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

    def add_allowed_instance_type(self, cluster_id: str, instance_type: str, nodepool_name: str = "default") -> bool:
        """
        Add a single instance type to the NodePool's allowed instance-type list.
        Called by the auto-rebalancer to ensure the target type is in the NodePool
        before Karpenter provisions a node.

        Returns True on success, False if NodePool not found or update fails.
        Idempotent: if the type is already present, returns True without patching.
        """
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

            # Extract instance-type requirement
            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
            found_req = False
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    values = set(req.get('values', []))
                    if instance_type in values:
                        logger.info(
                            f"[karpenter] {instance_type} already in NodePool '{nodepool_name}' "
                            f"for cluster {cluster_id} — no patch needed"
                        )
                        return True
                    values.add(instance_type)
                    req['values'] = sorted(values)
                    found_req = True
                    break

            if not found_req:
                # No instance-type requirement exists; create one
                requirements.append({
                    'key': 'node.kubernetes.io/instance-type',
                    'operator': 'In',
                    'values': [instance_type]
                })

            # Keep kubernetes.io/arch in sync with the instance types list
            _ARM64_FAMILIES = {
                't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
            }
            # Collect all instance types currently in the NodePool
            _all_types = set()
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    _all_types.update(req.get('values', []))
            _derived_archs = set()
            for _it in _all_types:
                _fam = _it.split('.')[0] if '.' in _it else _it
                _derived_archs.add('arm64' if _fam in _ARM64_FAMILIES else 'amd64')
            _arch_list = sorted(_derived_archs) if _derived_archs else ['amd64', 'arm64']

            # Update or create the kubernetes.io/arch requirement
            _arch_req_found = False
            for req in requirements:
                if req.get('key') == 'kubernetes.io/arch':
                    req['values'] = _arch_list
                    _arch_req_found = True
                    break
            if not _arch_req_found:
                requirements.append({
                    'key': 'kubernetes.io/arch',
                    'operator': 'In',
                    'values': _arch_list,
                })

            # Patch the NodePool
            patch_body = {
                "spec": {"template": {"spec": {"requirements": requirements}}}
            }
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh",
                version="v1",
                plural="nodepools",
                name=nodepool_name,
                body=patch_body,
            )

            # ── Read-back verification: confirm the patch actually took effect ──
            try:
                verified_np = custom_api.get_cluster_custom_object(
                    group="karpenter.sh", version="v1", plural="nodepools", name=nodepool_name,
                )
                verified_reqs = verified_np.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
                _verified_types = []
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
                    f"for cluster {cluster_id} (spot_capable={_has_spot_capacity})"
                )
            except Exception as ve:
                logger.warning(f"[karpenter] Read-back verification failed: {ve} — proceeding with caution")

            logger.info(
                f"[karpenter] Added {instance_type} to NodePool '{nodepool_name}' "
                f"for cluster {cluster_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[karpenter] add_allowed_instance_type failed: {e}")
            return False

    def remove_allowed_instance_type(self, cluster_id: str, instance_type: str, nodepool_name: str = "default") -> bool:
        """
        Remove a single instance type from the NodePool's allowed instance-type list.
        Called by _cleanup_rebalancing_resources to proactively roll back the type
        injected by Phase 1 when an action fails — preventing Karpenter from
        provisioning that type for unrelated workload scaling events.

        Returns True on success, False on failure.
        Idempotent: if the type is not present, returns True without patching.
        Refuses to remove the last instance type (NodePool must have at least one).
        """
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
                    return True  # NodePool gone — nothing to remove from
                raise

            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    values = set(req.get('values', []))
                    if instance_type not in values:
                        logger.info(
                            f"[karpenter] {instance_type} not in NodePool '{nodepool_name}' — no removal needed"
                        )
                        return True
                    if len(values) <= 1:
                        logger.warning(
                            f"[karpenter] Cannot remove {instance_type} — it's the only type in "
                            f"NodePool '{nodepool_name}'"
                        )
                        return False
                    values.discard(instance_type)
                    req['values'] = sorted(values)
                    break
            else:
                return True  # No instance-type requirement at all

            # Re-derive kubernetes.io/arch from remaining types
            _ARM64_FAMILIES = {
                't4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen',
            }
            _remaining_types = set()
            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    _remaining_types.update(req.get('values', []))
            _derived_archs = set()
            for _it in _remaining_types:
                _fam = _it.split('.')[0] if '.' in _it else _it
                _derived_archs.add('arm64' if _fam in _ARM64_FAMILIES else 'amd64')
            _arch_list = sorted(_derived_archs) if _derived_archs else ['amd64', 'arm64']
            for req in requirements:
                if req.get('key') == 'kubernetes.io/arch':
                    req['values'] = _arch_list
                    break

            patch_body = {
                "spec": {"template": {"spec": {"requirements": requirements}}}
            }
            custom_api.patch_cluster_custom_object(
                group="karpenter.sh", version="v1",
                plural="nodepools", name=nodepool_name,
                body=patch_body,
            )
            logger.info(
                f"[karpenter] Removed {instance_type} from NodePool '{nodepool_name}' "
                f"for cluster {cluster_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[karpenter] remove_allowed_instance_type failed: {e}")
            return False

    def patch_node_pool_allowed_types(self, cluster_id: str, instance_types: list, db) -> dict:
        """
        Update NodePool instance-type requirements with a new allowed list.
        Directly patches the NodePool via K8s API (no longer creates an AgentAction).
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
            )
            return {
                'status': 'success',
                'instance_types': instance_types,
            }
        except Exception as e:
            logger.error(f"[karpenter] patch_node_pool_allowed_types failed: {e}")
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
