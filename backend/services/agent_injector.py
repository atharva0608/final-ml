"""
Agent Injector Service

This service handles automatic agent installation into EKS clusters
using AWS cross-account role assumption and Kubernetes API.

Flow:
1. Assume customer's cross-account IAM role
2. Create EKS access entry for our backend role
3. Generate Kubernetes authentication token
4. Deploy agent manifests via Kubernetes API
"""

import os
import base64
import logging
import secrets
from typing import Dict, Optional, Tuple
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.signers import RequestSigner
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AgentInjectorService:
    """
    Service to automatically install the Spot Optimizer agent
    into discovered EKS clusters.
    """

    AGENT_IMAGE = "atharva608/spot-optimizer-agent:v1.0.0"
    NAMESPACE = "spot-optimizer"
    
    # AWS policy for cluster admin access
    CLUSTER_ADMIN_POLICY = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

    def __init__(self, db_session):
        self.db = db_session
        self.backend_role_arn = os.getenv('AWS_BACKEND_ROLE_ARN')
        self.backend_url = os.getenv('BACKEND_PUBLIC_URL', 'https://localhost:8000')

        # If role ARN is missing, try to detect it
        if not self.backend_role_arn:
            try:
                # Use platform credentials to check our own identity
                from backend.models.system_config import SystemConfig
                
                access_key = db_session.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
                secret_key = db_session.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
                region = db_session.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
                
                region_name = region.value if region and region.value else 'us-east-1'
                
                if access_key and secret_key and access_key.value and secret_key.value:
                    sts_client = boto3.client(
                        'sts',
                        aws_access_key_id=access_key.value,
                        aws_secret_access_key=secret_key.value,
                        region_name=region_name
                    )
                else:
                    sts_client = boto3.client('sts', region_name=region_name)
                
                identity = sts_client.get_caller_identity()
                self.backend_role_arn = identity['Arn']
                
                # Transform assumed-role ARN to role ARN if needed
                # arn:aws:sts::123:assumed-role/RoleName/Session -> arn:aws:iam::123:role/RoleName
                if ':assumed-role/' in self.backend_role_arn:
                    parts = self.backend_role_arn.split('/')
                    role_name = parts[1]
                    account = self.backend_role_arn.split(':')[4]
                    self.backend_role_arn = f"arn:aws:iam::{account}:role/{role_name}"
                    
                logger.info(f"Auto-detected backend IAM role: {self.backend_role_arn}")
            except Exception as e:
                logger.warning(f"Could not auto-detect backend IAM role: {e}")

    def inject_agent(
        self,
        cluster_id: str,
        cluster_name: str,
        cluster_arn: str,
        cluster_endpoint: str,
        cluster_ca_data: str,
        role_arn: str,
        external_id: str,
        region: str,
        api_key: str
    ) -> Dict:
        """
        Main method to inject agent into an EKS cluster.
        
        Args:
            cluster_id: Internal cluster UUID
            cluster_name: EKS cluster name
            cluster_arn: EKS cluster ARN
            cluster_endpoint: Kubernetes API endpoint
            cluster_ca_data: Base64 encoded CA certificate
            role_arn: Customer's cross-account role ARN
            external_id: External ID for role assumption
            api_key: API key for agent authentication
            
        Returns:
            Dict with status and message
        """
        try:
            logger.info(f"Starting agent injection for cluster {cluster_name}")
            
            # Step 1: Assume customer's cross-account role
            logger.info("Step 1: Assuming cross-account role...")
            assumed_credentials = self._assume_role(role_arn, external_id)
            
            # Step 2: Create EKS access entry for our backend
            logger.info("Step 2: Creating EKS access entry...")
            self._create_access_entry(
                cluster_name=cluster_name,
                credentials=assumed_credentials,
                region=region
            )
            
            # Step 3: Generate Kubernetes token
            logger.info("Step 3: Generating Kubernetes token...")
            k8s_token = self._get_eks_token(
                cluster_name=cluster_name,
                credentials=assumed_credentials,
                region=region
            )
            
            # Step 4: Deploy agent manifests
            logger.info("Step 4: Deploying agent manifests...")
            self._deploy_agent(
                cluster_id=cluster_id,
                cluster_endpoint=cluster_endpoint,
                cluster_ca_data=cluster_ca_data,
                k8s_token=k8s_token,
                api_key=api_key
            )
            
            logger.info(f"Agent successfully injected into cluster {cluster_name}")
            return {
                "status": "success",
                "message": f"Agent installed in cluster {cluster_name}"
            }
            
        except Exception as e:
            logger.error(f"Failed to inject agent: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    def _assume_role(self, role_arn: str, external_id: str) -> Dict:
        """
        Assume customer's cross-account IAM role using platform credentials.
        
        Returns:
            Dict with temporary credentials
        """
        # Get platform credentials from SystemConfig
        from backend.models.base import get_db
        from backend.models.system_config import SystemConfig
        
        db = next(get_db())
        
        access_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        region = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        
        region_name = region.value if region and region.value else 'us-east-1'
        
        if access_key and secret_key and access_key.value and secret_key.value:
            logger.info("Using platform credentials from SystemConfig for STS")
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value,
                region_name=region_name
            )
        else:
            logger.warning("Platform credentials not found, falling back to env/instance profile")
            sts_client = boto3.client('sts', region_name=region_name)
        
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SpotOptimizerAgentInjector',
            ExternalId=external_id,
            DurationSeconds=3600  # 1 hour
        )
        
        return {
            'access_key': response['Credentials']['AccessKeyId'],
            'secret_key': response['Credentials']['SecretAccessKey'],
            'session_token': response['Credentials']['SessionToken']
        }

    def _create_access_entry(
        self,
        cluster_name: str,
        credentials: Dict,
        region: str
    ) -> None:
        """
        Create an EKS access entry to allow our backend role to manage the cluster.
        """
        eks_client = boto3.client(
            'eks',
            aws_access_key_id=credentials['access_key'],
            aws_secret_access_key=credentials['secret_key'],
            aws_session_token=credentials['session_token'],
            region_name=region
        )
        
        # Create access entry (idempotent via try/except)
        try:
            eks_client.create_access_entry(
                clusterName=cluster_name,
                principalArn=self.backend_role_arn,
                type='STANDARD'
            )
        except eks_client.exceptions.ResourceInUseException:
            logger.info("Access entry already exists (ResourceInUse)")
            # Fall through to ensure policy association
        except Exception as e:
            # Handle potential AccessDenied or other errors by logging but not crashing immediately 
            # if we can try association. 
            # But wait, if we lack Create permission, we likely fail here.
            # However, the reported error was specific to Describe.
            if "ResourceInUse" in str(e):
                 logger.info("Access entry already exists (caught via string)")
            else:
                 # If we can't describe AND can't create, we might still try associating policy
                 # assuming it exists? No, better to raise or log.
                 # Re-raising for now, assuming Create permission exists.
                 logger.warning(f"Error creating access entry: {e}")
                 if "AccessDenied" not in str(e):
                     raise
        
        # Associate cluster admin policy
        eks_client.associate_access_policy(
            clusterName=cluster_name,
            principalArn=self.backend_role_arn,
            policyArn=self.CLUSTER_ADMIN_POLICY,
            accessScope={
                'type': 'cluster'
            }
        )
        
        logger.info(f"Created access entry for {self.backend_role_arn}")

    def _get_eks_token(self, cluster_name: str, credentials: Dict, region: str) -> str:
        """
        Generate a Kubernetes authentication token for EKS.
        
        This replicates the behavior of `aws eks get-token`.
        """
        # Create STS client with assumed credentials
        session = boto3.Session(
            aws_access_key_id=credentials['access_key'],
            aws_secret_access_key=credentials['secret_key'],
            aws_session_token=credentials['session_token'],
            region_name=region
        )
        
        sts_client = session.client('sts', region_name=region, config=Config(signature_version='v4'))
        
        # Get the presigned URL for GetCallerIdentity
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

    def _deploy_agent(
        self,
        cluster_id: str,
        cluster_endpoint: str,
        cluster_ca_data: str,
        k8s_token: str,
        api_key: str
    ) -> None:
        """
        Deploy the Spot Optimizer agent to the cluster using Kubernetes API.
        """
        try:
            from kubernetes import client as k8s_client
            from kubernetes.client import Configuration, ApiClient
        except ImportError:
            raise ImportError("kubernetes package is required. Install with: pip install kubernetes")
        
        # Configure Kubernetes client
        config = Configuration()
        config.host = cluster_endpoint
        config.api_key = {"authorization": f"Bearer {k8s_token}"}
        config.ssl_ca_cert = self._decode_ca_cert(cluster_ca_data)
        config.verify_ssl = True
        
        api_client = ApiClient(configuration=config)
        
        # Create namespace
        core_v1 = k8s_client.CoreV1Api(api_client)
        try:
            core_v1.create_namespace(
                body=k8s_client.V1Namespace(
                    metadata=k8s_client.V1ObjectMeta(name=self.NAMESPACE)
                )
            )
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:  # 409 = already exists
                raise
        
        # Create secret
        try:
            core_v1.create_namespaced_secret(
                namespace=self.NAMESPACE,
                body=k8s_client.V1Secret(
                    metadata=k8s_client.V1ObjectMeta(name="spot-agent-secret"),
                    string_data={"API_KEY": api_key}
                )
            )
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
        
        # Create configmap
        ws_url = self.backend_url.replace('https://', 'wss://').replace('http://', 'ws://')
        backend_ws_url = f"{ws_url}/ws/cluster/{cluster_id}"
        
        try:
            core_v1.create_namespaced_config_map(
                namespace=self.NAMESPACE,
                body=k8s_client.V1ConfigMap(
                    metadata=k8s_client.V1ObjectMeta(name="spot-agent-config"),
                    data={
                        "BACKEND_URL": backend_ws_url,
                        "CLUSTER_ID": cluster_id
                    }
                )
            )
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
        
        # Create ServiceAccount
        try:
            core_v1.create_namespaced_service_account(
                namespace=self.NAMESPACE,
                body=k8s_client.V1ServiceAccount(
                    metadata=k8s_client.V1ObjectMeta(name="spot-agent-sa")
                )
            )
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
        
        # Create ClusterRole and ClusterRoleBinding
        rbac_v1 = k8s_client.RbacAuthorizationV1Api(api_client)
        
        cluster_role = k8s_client.V1ClusterRole(
            metadata=k8s_client.V1ObjectMeta(name="spot-agent-role"),
            rules=[
                k8s_client.V1PolicyRule(
                    api_groups=["", "apps", "batch", "extensions"],
                    resources=["nodes", "pods", "deployments", "replicasets", "daemonsets", "statefulsets", "jobs"],
                    verbs=["get", "list", "watch"]
                ),
                k8s_client.V1PolicyRule(
                    api_groups=[""],
                    resources=["pods/eviction"],
                    verbs=["create"]
                )
            ]
        )
        
        try:
            rbac_v1.create_cluster_role(body=cluster_role)
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
        
        cluster_role_binding = k8s_client.V1ClusterRoleBinding(
            metadata=k8s_client.V1ObjectMeta(name="spot-agent-binding"),
            subjects=[
                k8s_client.V1Subject(
                    kind="ServiceAccount",
                    name="spot-agent-sa",
                    namespace=self.NAMESPACE
                )
            ],
            role_ref=k8s_client.V1RoleRef(
                kind="ClusterRole",
                name="spot-agent-role",
                api_group="rbac.authorization.k8s.io"
            )
        )
        
        try:
            rbac_v1.create_cluster_role_binding(body=cluster_role_binding)
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
        
        # Create DaemonSet (Changed from Deployment)
        apps_v1 = k8s_client.AppsV1Api(api_client)
        
        daemonset = k8s_client.V1DaemonSet(
            metadata=k8s_client.V1ObjectMeta(
                name="spot-agent",
                namespace=self.NAMESPACE
            ),
            spec=k8s_client.V1DaemonSetSpec(
                selector=k8s_client.V1LabelSelector(
                    match_labels={"app": "spot-agent"}
                ),
                template=k8s_client.V1PodTemplateSpec(
                    metadata=k8s_client.V1ObjectMeta(
                        labels={"app": "spot-agent"}
                    ),
                    spec=k8s_client.V1PodSpec(
                        service_account_name="spot-agent-sa",
                        host_network=True,  # DaemonSet often needs host network for metrics
                        tolerations=[
                            k8s_client.V1Toleration(
                                operator="Exists"  # Run on all nodes (including tainted ones)
                            )
                        ],
                        containers=[
                            k8s_client.V1Container(
                                name="agent",
                                image=self.AGENT_IMAGE,
                                image_pull_policy="Always",
                                env=[
                                    k8s_client.V1EnvVar(
                                        name="API_KEY",
                                        value_from=k8s_client.V1EnvVarSource(
                                            secret_key_ref=k8s_client.V1SecretKeySelector(
                                                name="spot-agent-secret",
                                                key="API_KEY"
                                            )
                                        )
                                    ),
                                    k8s_client.V1EnvVar(
                                        name="BACKEND_URL",
                                        value_from=k8s_client.V1EnvVarSource(
                                            config_map_key_ref=k8s_client.V1ConfigMapKeySelector(
                                                name="spot-agent-config",
                                                key="BACKEND_URL"
                                            )
                                        )
                                    ),
                                    k8s_client.V1EnvVar(
                                        name="CLUSTER_ID",
                                        value_from=k8s_client.V1EnvVarSource(
                                            config_map_key_ref=k8s_client.V1ConfigMapKeySelector(
                                                name="spot-agent-config",
                                                key="CLUSTER_ID"
                                            )
                                        )
                                    ),
                                    k8s_client.V1EnvVar(
                                        name="NODE_NAME",
                                        value_from=k8s_client.V1EnvVarSource(
                                            field_ref=k8s_client.V1ObjectFieldSelector(
                                                field_path="spec.nodeName"
                                            )
                                        )
                                    )
                                ],
                                resources=k8s_client.V1ResourceRequirements(
                                    requests={"cpu": "50m", "memory": "64Mi"},
                                    limits={"cpu": "200m", "memory": "256Mi"}
                                )
                            )
                        ]
                    )
                )
            )
        )
        
        try:
            apps_v1.create_namespaced_daemon_set(
                namespace=self.NAMESPACE,
                body=daemonset
            )
        except k8s_client.exceptions.ApiException as e:
            if e.status == 409:
                # Update existing daemonset
                apps_v1.replace_namespaced_daemon_set(
                    name="spot-agent",
                    namespace=self.NAMESPACE,
                    body=daemonset
                )
            else:
                raise
        
        logger.info("Agent deployment created successfully")

    def _decode_ca_cert(self, ca_data: str) -> str:
        """
        Decode base64 CA certificate and write to temp file.
        Returns path to temp file.
        """
        import tempfile
        
        ca_bytes = base64.b64decode(ca_data)
        
        # Write to temp file
        fd, path = tempfile.mkstemp(suffix='.crt')
        with os.fdopen(fd, 'wb') as f:
            f.write(ca_bytes)
        
        return path
