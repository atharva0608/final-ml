"""Karpenter Integration Service - System 3: NodePool Management

Updates Karpenter NodePools with ML-approved instance types every 30 seconds.

Flow:
1. ML pipeline ranks safe pools → Top 10 instance types
2. Karpenter service syncs ML rankings → NodePool YAML
3. Karpenter reads updated NodePool → Provisions from safe list only

Features:
- Kubernetes API client for EKS clusters
- NodePool YAML generator
- ML ranking → instance-types sync
- Multi-cluster support
"""

import base64
import boto3
import yaml
from typing import List, Dict, Optional
from datetime import datetime
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
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

    def __init__(self, db: Session):
        self.db = db

    def sync_ml_rankings_to_nodepool(
        self,
        cluster_id: str,
        top_pools: List[Dict],
        nodepool_name: str = "ml-optimized"
    ) -> Dict:
        """
        Syncs ML-ranked instance types to Karpenter NodePool.

        Args:
            cluster_id: Cluster database ID
            top_pools: List of ML-scored pools from PoolRankingService
                       Format: [{'instance_type': 'm5.xlarge', 'az': 'aps1-az1', 'ml_score': 92.5}, ...]
            nodepool_name: Name of the Karpenter NodePool to update

        Returns:
            Dict with sync status, updated instance types, timestamp
        """
        try:
            # Get cluster from database
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            # Get Kubernetes API client
            api_client = self._get_k8s_client(cluster)

            # Extract unique instance types from top pools
            instance_types = list(set([pool['instance_type'] for pool in top_pools]))

            # Extract unique AZs from top pools
            azs = list(set([pool['az'] for pool in top_pools]))

            logger.info(f"Syncing {len(instance_types)} ML-approved instance types to NodePool '{nodepool_name}' in cluster {cluster.name}")

            # Update or create NodePool
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

    def _get_k8s_client(self, cluster: Cluster):
        """
        Creates Kubernetes API client for EKS cluster.

        Replicates the logic from agent_injector.py for EKS authentication.
        """
        try:
            # Get account credentials
            account = self.db.query(Account).filter(Account.id == cluster.account_id).first()
            if not account:
                raise ValueError(f"Account {cluster.account_id} not found")

            # Get platform credentials for token generation
            credentials = self._get_backend_credentials(cluster.region)

            # Generate EKS authentication token
            token = self._get_eks_token(
                cluster_name=cluster.name,
                credentials=credentials,
                region=cluster.region
            )

            # Create Kubernetes configuration
            configuration = client.Configuration()
            configuration.host = cluster.endpoint
            configuration.verify_ssl = True
            configuration.api_key = {"authorization": f"Bearer {token}"}

            # Set cluster CA certificate
            if cluster.ca_data:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, mode='w') as ca_file:
                    ca_file.write(cluster.ca_data)
                    configuration.ssl_ca_cert = ca_file.name

            # Create API client
            api_client = client.ApiClient(configuration)

            logger.info(f"Successfully created Kubernetes API client for cluster {cluster.name}")
            return api_client

        except Exception as e:
            logger.error(f"Failed to create Kubernetes API client: {e}")
            raise

    def _get_backend_credentials(self, region: str) -> Dict:
        """
        Get backend platform IAM credentials from SystemConfig.

        Returns:
            Dict with access_key, secret_key
        """
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()

        if access_key and secret_key and access_key.value and secret_key.value:
            logger.info(f"Using backend platform credentials for EKS token generation")
            return {
                'access_key': access_key.value,
                'secret_key': secret_key.value
            }
        else:
            logger.warning("Platform credentials not found, using environment/instance profile")
            return {}

    def _get_eks_token(self, cluster_name: str, credentials: Dict, region: str) -> str:
        """
        Generate Kubernetes authentication token for EKS.

        Replicates `aws eks get-token` behavior using SigV4 presigned URL.
        """
        # Create STS client with provided credentials or use default
        if credentials and 'access_key' in credentials and 'secret_key' in credentials:
            session = boto3.Session(
                aws_access_key_id=credentials['access_key'],
                aws_secret_access_key=credentials['secret_key'],
                aws_session_token=credentials.get('session_token'),
                region_name=region
            )
        else:
            logger.info("Using default AWS credentials for token generation")
            session = boto3.Session(region_name=region)

        sts_client = session.client('sts', region_name=region, config=Config(signature_version='v4'))

        # Get presigned URL for GetCallerIdentity
        service_id = sts_client.meta.service_model.service_id
        signer = RequestSigner(
            service_id,
            region,
            'sts',
            'v4',
            session.get_credentials(),
            session.events
        )

        # Generate presigned URL
        params = {
            'method': 'GET',
            'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
            'body': {},
            'headers': {
                'x-k8s-aws-id': cluster_name
            },
            'context': {}
        }

        url = signer.generate_presigned_url(
            params,
            region_name=region,
            expires_in=60,
            operation_name=''
        )

        # Encode as base64 token (k8s.io/client-go format)
        token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(
            url.encode('utf-8')
        ).decode('utf-8').rstrip('=')

        return token

    def _update_nodepool(
        self,
        api_client,
        nodepool_name: str,
        instance_types: List[str],
        azs: List[str],
        cluster: Cluster
    ) -> bool:
        """
        Updates Karpenter NodePool with ML-approved instance types.

        Returns:
            True if existing NodePool was updated, False if created new
        """
        try:
            # Create Custom Objects API client
            custom_api = client.CustomObjectsApi(api_client)

            # Define NodePool spec
            nodepool_spec = {
                "apiVersion": "karpenter.sh/v1beta1",
                "kind": "NodePool",
                "metadata": {
                    "name": nodepool_name,
                    "labels": {
                        "managed-by": "spot-optimizer",
                        "ml-optimized": "true"
                    },
                    "annotations": {
                        "last-updated": datetime.utcnow().isoformat(),
                        "updated-by": "atharvaai-ml-pipeline"
                    }
                },
                "spec": {
                    "template": {
                        "spec": {
                            "requirements": [
                                {
                                    "key": "karpenter.sh/capacity-type",
                                    "operator": "In",
                                    "values": ["spot"]
                                },
                                {
                                    "key": "node.kubernetes.io/instance-type",
                                    "operator": "In",
                                    "values": instance_types
                                },
                                {
                                    "key": "topology.kubernetes.io/zone",
                                    "operator": "In",
                                    "values": azs
                                }
                            ],
                            "nodeClassRef": {
                                "name": "default"  # Update this to match your EC2NodeClass
                            }
                        }
                    },
                    "disruption": {
                        "consolidationPolicy": "WhenUnderutilized",
                        "expireAfter": "720h"  # 30 days
                    },
                    "limits": {
                        "cpu": "1000",
                        "memory": "1000Gi"
                    }
                }
            }

            # Try to get existing NodePool
            try:
                existing = custom_api.get_namespaced_custom_object(
                    group="karpenter.sh",
                    version="v1beta1",
                    namespace="karpenter",
                    plural="nodepools",
                    name=nodepool_name
                )

                # Update existing NodePool
                logger.info(f"Updating existing NodePool '{nodepool_name}'")
                custom_api.patch_namespaced_custom_object(
                    group="karpenter.sh",
                    version="v1beta1",
                    namespace="karpenter",
                    plural="nodepools",
                    name=nodepool_name,
                    body=nodepool_spec
                )
                return True

            except ApiException as e:
                if e.status == 404:
                    # NodePool doesn't exist, create it
                    logger.info(f"Creating new NodePool '{nodepool_name}'")
                    custom_api.create_namespaced_custom_object(
                        group="karpenter.sh",
                        version="v1beta1",
                        namespace="karpenter",
                        plural="nodepools",
                        body=nodepool_spec
                    )
                    return False
                else:
                    raise

        except Exception as e:
            logger.error(f"Failed to update NodePool: {e}")
            raise

    def get_nodepool_status(self, cluster_id: str, nodepool_name: str = "ml-optimized") -> Dict:
        """
        Gets current status of Karpenter NodePool.

        Returns:
            Dict with NodePool details, instance types, last update time
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            api_client = self._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)

            # Get NodePool
            nodepool = custom_api.get_namespaced_custom_object(
                group="karpenter.sh",
                version="v1beta1",
                namespace="karpenter",
                plural="nodepools",
                name=nodepool_name
            )

            # Extract instance types from requirements
            requirements = nodepool.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
            instance_types = []
            azs = []

            for req in requirements:
                if req.get('key') == 'node.kubernetes.io/instance-type':
                    instance_types = req.get('values', [])
                if req.get('key') == 'topology.kubernetes.io/zone':
                    azs = req.get('values', [])

            return {
                'status': 'active',
                'nodepool_name': nodepool_name,
                'instance_types': instance_types,
                'availability_zones': azs,
                'last_updated': nodepool.get('metadata', {}).get('annotations', {}).get('last-updated'),
                'managed_by': nodepool.get('metadata', {}).get('labels', {}).get('managed-by')
            }

        except ApiException as e:
            if e.status == 404:
                return {
                    'status': 'not_found',
                    'nodepool_name': nodepool_name,
                    'message': 'NodePool does not exist'
                }
            else:
                raise

        except Exception as e:
            logger.error(f"Failed to get NodePool status: {e}")
            return {
                'status': 'error',
                'nodepool_name': nodepool_name,
                'error': str(e)
            }
