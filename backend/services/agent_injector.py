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
import json
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

    AGENT_IMAGE = "atharva608/spot-optimizer-agent:latest"
    # NOTE: orchestrator image not yet published separately; using agent image
    # with ROLE=orchestrator env var until atharva608/spot-optimizer-orchestrator is built.
    ORCHESTRATOR_IMAGE = "atharva608/spot-optimizer-agent:latest"
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

        Phase 7: Enhanced with OIDC Federation support

        Args:
            cluster_id: Internal cluster UUID
            cluster_name: EKS cluster name
            cluster_arn: EKS cluster ARN
            cluster_endpoint: Kubernetes API endpoint
            cluster_ca_data: Base64 encoded CA certificate
            role_arn: Customer's cross-account role ARN
            external_id: External ID for role assumption
            api_key: API key for agent authentication (legacy, will be deprecated)

        Returns:
            Dict with status and message
        """
        try:
            logger.info(f"Starting agent injection for cluster {cluster_name}")

            # Step 1: Assume customer's cross-account role
            logger.info(f"Step 1: Assuming cross-account role (Region: {region})...")
            assumed_credentials = self._assume_role(role_arn, external_id, region)

            # Step 2: Grant our backend role access to the cluster.
            # RBAC-02: Auth mode detection — older clusters or clusters explicitly set to
            # CONFIG_MAP mode do not support the Access Entry API and will fail with
            # "UnsupportedAvailabilityZoneException" or "InvalidParameterException".
            # We auto-detect and fall back to patching the aws-auth ConfigMap.
            logger.info("Step 2: Granting backend cluster access (auth-mode aware)...")
            self._ensure_cluster_access(
                cluster_name=cluster_name,
                credentials=assumed_credentials,
                cluster_endpoint=cluster_endpoint,
                cluster_ca_data=cluster_ca_data,
                region=region
            )

            # Step 2a: KARPENTER-OIDC-REGISTER-01 — register OIDC provider in IAM.
            # Must happen before the trust policy update (Step 2b) because the trust
            # policy references the provider ARN which only exists after registration.
            logger.info("Step 2a: Ensuring OIDC provider is registered in IAM...")
            try:
                self._ensure_oidc_provider_registered(
                    cluster_name=cluster_name,
                    region=region,
                    credentials=assumed_credentials,
                )
            except Exception as _oidc_err:
                logger.warning(f"OIDC provider registration failed (non-fatal): {_oidc_err}")

            # Step 2b-tag: Auto-tag cluster subnets and security group with karpenter.sh/discovery
            # Required for EC2NodeClass to discover network resources. Idempotent — safe on every connect.
            try:
                self._tag_karpenter_network_resources(
                    cluster_name=cluster_name,
                    region=region,
                    credentials=assumed_credentials,
                )
            except Exception as _tag_err:
                logger.warning(f"Karpenter network tagging failed (non-fatal): {_tag_err}")

            # Step 2c: AUTO-SETUP — create all required Karpenter AWS prerequisites
            # (IAM node role, controller role, SQS queue, EventBridge rules).
            # These are required for Karpenter to start without CrashLoopBackOff.
            # Idempotent: already-existing resources are silently skipped.
            logger.info("Step 2c: Ensuring Karpenter AWS prerequisites...")
            try:
                self._ensure_karpenter_aws_prerequisites(
                    cluster_name=cluster_name,
                    region=region,
                    credentials=assumed_credentials,
                )
            except Exception as _prereq_err:
                logger.warning(f"Karpenter prerequisites setup failed (non-fatal): {_prereq_err}")

            # Step 2d: FIX-MULTI-CLUSTER-01 — patch KarpenterControllerRole trust policy
            # directly via iam:UpdateAssumeRolePolicy for THIS cluster only.
            # Each cluster has its own role (KarpenterControllerRole-{cluster_name}) so
            # patching one never overwrites another cluster's trust policy.
            # Role is now guaranteed to exist from Step 2c, so this should always succeed.
            try:
                self._update_karpenter_controller_trust_policy(
                    cluster_name=cluster_name,
                    region=region,
                    credentials=assumed_credentials,
                )
            except Exception as _iam_err:
                logger.warning(f"KarpenterControllerRole trust policy update failed (non-fatal): {_iam_err}")

            # Step 3: Setup OIDC Federation (Phase 7)
            logger.info("Step 3: Setting up OIDC federation for agent authentication...")
            oidc_issuer = self._setup_oidc_federation(
                cluster_id=cluster_id,
                cluster_name=cluster_name,
                credentials=assumed_credentials,
                region=region
            )

            # Step 4: Get backend credentials and generate Kubernetes token
            # IMPORTANT: Token must be generated using backend's own IAM credentials,
            # not the assumed role credentials, because the access entry was created
            # for the backend IAM principal
            logger.info("Step 4: Generating Kubernetes token using backend credentials...")
            backend_credentials = self._get_backend_credentials(region)
            k8s_token = self._get_eks_token(
                cluster_name=cluster_name,
                credentials=backend_credentials,
                region=region
            )

            # Step 5: Deploy agent manifests
            logger.info("Step 5: Deploying agent manifests...")
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
                "message": f"Agent installed in cluster {cluster_name}",
                "oidc_issuer": oidc_issuer
            }

        except Exception as e:
            logger.error(f"Failed to inject agent: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    def _assume_role(self, role_arn: str, external_id: str, region: str = 'us-east-1') -> Dict:
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
        # Platform region is where the BACKEND runs.
        # But for assuming the role, we should use the region where we want to act?
        # Actually STS is global, but regional endpoints reduce latency.
        # The user specifically requested using 'cluster.region'.
        platform_region = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        
        platform_region_name = platform_region.value if platform_region and platform_region.value else 'us-east-1'
        
        # Use cluster region if provided, else platform region
        target_region = region if region else platform_region_name

        if access_key and secret_key and access_key.value and secret_key.value:
            logger.info(f"Using platform credentials for STS in region {target_region}")
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value,
                region_name=target_region
            )
        else:
            logger.warning(f"Platform credentials not found, using env/instance profile in {target_region}")
            sts_client = boto3.client('sts', region_name=target_region)
        
        assume_kwargs = {
            'RoleArn': role_arn,
            'RoleSessionName': 'SpotOptimizerAgentInjector',
            'DurationSeconds': 3600  # 1 hour
        }
        if external_id:  # STS rejects ExternalId="" (must be >= 2 chars)
            assume_kwargs['ExternalId'] = external_id

        try:
            response = sts_client.assume_role(**assume_kwargs)
            return {
                'access_key': response['Credentials']['AccessKeyId'],
                'secret_key': response['Credentials']['SecretAccessKey'],
                'session_token': response['Credentials']['SessionToken']
            }
        except Exception as assume_err:
            from botocore.exceptions import ClientError as BotoClientError
            if isinstance(assume_err, BotoClientError):
                error_code = assume_err.response['Error']['Code']
                if error_code in ('AccessDenied', 'AccessDeniedException'):
                    # Same-account fallback: check if caller and role are in the same account.
                    # If so, use env/instance-profile credentials directly instead of AssumeRole.
                    try:
                        caller = sts_client.get_caller_identity()
                        role_account_id = role_arn.split(':')[4]
                        if caller['Account'] == role_account_id:
                            logger.warning(
                                f"AssumeRole AccessDenied for same-account role {role_arn}. "
                                "Falling back to env credentials directly. "
                                "To fix permanently: attach 'sts:AssumeRole' policy to your "
                                f"IAM user for role {role_arn}"
                            )
                            # Return empty dict → callers use boto3 default credential chain
                            return {}
                    except Exception:
                        pass
            raise assume_err

    def _get_backend_credentials(self, region: str) -> Dict:
        """
        Get the backend platform's own IAM credentials.

        Returns:
            Dict with backend credentials (access_key, secret_key, no session_token for static creds)
        """
        from backend.models.base import get_db
        from backend.models.system_config import SystemConfig

        db = next(get_db())

        access_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()

        if access_key and secret_key and access_key.value and secret_key.value:
            logger.info(f"Using backend platform credentials for K8s token generation")
            return {
                'access_key': access_key.value,
                'secret_key': secret_key.value,
                'session_token': None  # Static credentials don't have session token
            }
        else:
            # Fallback to environment/instance profile credentials
            logger.warning(f"Platform credentials not found in SystemConfig, using default credentials")
            # Return empty dict to signal use of default credentials
            return {}

    def _get_cluster_auth_mode(self, eks_client, cluster_name: str) -> str:
        """
        Return the EKS cluster's authentication mode.

        RBAC-02: EKS clusters have three possible auth modes:
          API              — Only EKS Access Entry API (modern, EKS ≥ 1.28 default)
          API_AND_CONFIG_MAP — Both API and aws-auth ConfigMap (transition mode)
          CONFIG_MAP       — Only aws-auth ConfigMap (legacy, EKS < 1.28 or explicitly set)

        Clusters in CONFIG_MAP-only mode will return HTTP 400 if you try to call
        create_access_entry — we must use the ConfigMap patch path instead.

        Returns one of: 'API' | 'API_AND_CONFIG_MAP' | 'CONFIG_MAP'
        Defaults to 'CONFIG_MAP' if the field is absent (safest fallback).
        """
        try:
            resp = eks_client.describe_cluster(name=cluster_name)
            return resp["cluster"].get("accessConfig", {}).get("authenticationMode", "CONFIG_MAP")
        except Exception as e:
            logger.warning(f"Could not read EKS auth mode for {cluster_name}: {e}. Defaulting to CONFIG_MAP path.")
            return "CONFIG_MAP"

    def _ensure_cluster_access(
        self,
        cluster_name: str,
        credentials: Dict,
        cluster_endpoint: str,
        cluster_ca_data: str,
        region: str
    ) -> None:
        """
        Grant our backend IAM role access to the cluster using the correct method.

        RBAC-02: Chooses between:
          - Access Entry API  (API or API_AND_CONFIG_MAP mode)
          - aws-auth ConfigMap patch (CONFIG_MAP-only mode)
        """
        if credentials and "access_key" in credentials:
            eks_client = boto3.client(
                "eks",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
                region_name=region,
            )
        else:
            eks_client = boto3.client("eks", region_name=region)

        auth_mode = self._get_cluster_auth_mode(eks_client, cluster_name)

        if auth_mode in ("API", "API_AND_CONFIG_MAP"):
            logger.info(f"Cluster {cluster_name} auth mode: {auth_mode} — using Access Entry API")
            self._create_access_entry(
                cluster_name=cluster_name,
                credentials=credentials,
                region=region,
            )
        else:
            logger.info(f"Cluster {cluster_name} auth mode: {auth_mode} — falling back to aws-auth ConfigMap")
            self._patch_aws_auth_configmap(
                cluster_endpoint=cluster_endpoint,
                cluster_ca_data=cluster_ca_data,
                credentials=credentials,
                region=region,
                role_arn=self.backend_role_arn,
            )

    def _update_karpenter_controller_trust_policy(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> bool:
        """
        FIX-MULTI-CLUSTER-01: Patch KarpenterControllerRole-{cluster_name} trust policy
        with the real OIDC provider for this specific cluster.

        WHY iam:UpdateAssumeRolePolicy instead of CF update_stack():
          - Each cluster has its OWN role: KarpenterControllerRole-{cluster_name}
          - Patching the role directly means cluster-A and cluster-B never interfere
          - CF update_stack() has ONE KarpenterControllerRole per stack — connecting
            cluster-B would overwrite cluster-A's trust policy, breaking its Karpenter
          - iam:UpdateAssumeRolePolicy patches exactly one role, leaves all others intact

        Returns True if trust policy updated, False if role not found (CF not deployed).
        Non-fatal: caller wraps in try/except and logs a warning.
        """
        if credentials and "access_key" in credentials:
            eks_client = boto3.client(
                "eks",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
                region_name=region,
            )
            iam_client = boto3.client(
                "iam",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
            )
            sts_client = boto3.client(
                "sts",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
                region_name=region,
            )
        else:
            eks_client = boto3.client("eks", region_name=region)
            iam_client = boto3.client("iam")
            sts_client = boto3.client("sts", region_name=region)

        # Get account ID from assumed session (customer's account, not platform account)
        account_id = sts_client.get_caller_identity()["Account"]

        # Fetch OIDC issuer URL from EKS and strip the https:// scheme
        # Result: "oidc.eks.ap-south-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E"
        try:
            cluster_info = eks_client.describe_cluster(name=cluster_name)
            oidc_issuer = (
                cluster_info["cluster"]
                .get("identity", {})
                .get("oidc", {})
                .get("issuer", "")
            )
            if not oidc_issuer:
                logger.warning(f"Cluster {cluster_name} has no OIDC issuer configured")
                return False
            oidc_host = oidc_issuer.replace("https://", "").rstrip("/")
        except Exception as e:
            logger.error(f"Failed to get OIDC issuer for cluster {cluster_name}: {e}")
            return False

        role_name = f"KarpenterControllerRole-{cluster_name}"

        # Build the correct trust policy for this cluster's OIDC endpoint.
        # Condition keys are PLAIN STRINGS (not !Sub expressions) — required by IAM API.
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": f"arn:aws:iam::{account_id}:oidc-provider/{oidc_host}"
                    },
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            f"{oidc_host}:aud": "sts.amazonaws.com",
                            f"{oidc_host}:sub": "system:serviceaccount:karpenter:karpenter",
                        }
                    },
                }
            ],
        }

        try:
            iam_client.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=json.dumps(trust_policy),
            )
            logger.info(
                f"Updated trust policy for {role_name}: OIDC provider = {oidc_host}"
            )
            return True

        except iam_client.exceptions.NoSuchEntityException:
            logger.warning(
                f"{role_name} not found in account {account_id}. "
                f"Deploy the SpotOptimizer CloudFormation stack with ClusterName={cluster_name} "
                f"before installing Karpenter."
            )
            return False

    # -------------------------------------------------------------------------
    # KARPENTER-OIDC-REGISTER-01: OIDC provider registration helpers
    # -------------------------------------------------------------------------

    def _get_oidc_thumbprint(self, oidc_url: str) -> str:
        """
        Return the SHA1 thumbprint of the OIDC endpoint's TLS certificate.
        IAM CreateOpenIDConnectProvider requires the root CA thumbprint.
        Falls back to a well-known AWS EKS root CA thumbprint when the TLS
        handshake is not reachable from the backend container.
        """
        import ssl
        import hashlib
        import socket
        from urllib.parse import urlparse

        # Well-known thumbprint for the AWS EKS OIDC root CA (valid as of 2025).
        # IAM accepts up to 5 thumbprints; this is the canonical fallback.
        _AWS_EKS_ROOT_THUMBPRINT = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"

        try:
            parsed = urlparse(oidc_url if oidc_url.startswith("https://") else f"https://{oidc_url}")
            hostname = parsed.hostname
            if not hostname:
                return _AWS_EKS_ROOT_THUMBPRINT
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((hostname, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    der_cert = ssock.getpeercert(binary_form=True)
                    return hashlib.sha1(der_cert).hexdigest()
        except Exception as e:
            logger.warning(
                f"Could not fetch OIDC thumbprint from {oidc_url}: {e}. "
                f"Using AWS EKS root CA fallback."
            )
            return _AWS_EKS_ROOT_THUMBPRINT

    def _ensure_oidc_provider_registered(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> str:
        """
        KARPENTER-OIDC-REGISTER-01: Ensure the EKS cluster's OIDC provider is
        registered in the customer's IAM account.  This is a prerequisite for
        IRSA (Karpenter + any webhook that uses --set serviceAccount.annotations…).

        Returns the OIDC host (without https://) or "" on failure.
        Non-fatal — caller should wrap in try/except and log a warning.
        """
        if credentials and "access_key" in credentials:
            eks_client = boto3.client(
                "eks",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
                region_name=region,
            )
            iam_client = boto3.client(
                "iam",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
            )
            sts_client = boto3.client(
                "sts",
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
                region_name=region,
            )
        else:
            eks_client = boto3.client("eks", region_name=region)
            iam_client = boto3.client("iam")
            sts_client = boto3.client("sts", region_name=region)

        # Get OIDC issuer URL from EKS
        cluster_info = eks_client.describe_cluster(name=cluster_name)
        oidc_issuer = (
            cluster_info["cluster"]
            .get("identity", {})
            .get("oidc", {})
            .get("issuer", "")
        )
        if not oidc_issuer:
            logger.warning(
                f"Cluster {cluster_name} has no OIDC issuer configured. "
                f"Enable OIDC on the EKS cluster before installing Karpenter."
            )
            return ""
        oidc_host = oidc_issuer.replace("https://", "").rstrip("/")
        account_id = sts_client.get_caller_identity()["Account"]
        provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{oidc_host}"

        # Check whether already registered
        try:
            existing = iam_client.list_open_id_connect_providers().get(
                "OpenIDConnectProviderList", []
            )
            for p in existing:
                if p.get("Arn") == provider_arn:
                    logger.info(f"OIDC provider already registered: {provider_arn}")
                    return oidc_host
        except Exception as list_err:
            logger.warning(f"Could not list OIDC providers (will attempt create): {list_err}")

        # Not registered — create it
        thumbprint = self._get_oidc_thumbprint(oidc_issuer)
        try:
            iam_client.create_open_id_connect_provider(
                Url=oidc_issuer,
                ClientIDList=["sts.amazonaws.com"],
                ThumbprintList=[thumbprint],
                Tags=[
                    {"Key": "ManagedBy", "Value": "SpotOptimizer"},
                    {"Key": "ClusterName", "Value": cluster_name},
                ],
            )
            logger.info(
                f"Created OIDC provider: {provider_arn} (thumbprint: {thumbprint})"
            )
        except Exception as create_err:
            # EntityAlreadyExists means a concurrent call beat us — fine
            if "EntityAlreadyExists" in str(create_err):
                logger.info(f"OIDC provider already exists (concurrent create): {provider_arn}")
            else:
                raise

        return oidc_host

    def _tag_karpenter_network_resources(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> None:
        """
        Tags nodegroup subnets and cluster security group with karpenter.sh/discovery:{cluster_name}.
        Called automatically on every agent install/connect — idempotent.
        Without these tags EC2NodeClass stays Ready=False and Karpenter cannot provision nodes.
        """
        import boto3 as _boto3
        # Support both key naming conventions:
        #   _assume_role() returns: access_key / secret_key / session_token
        #   AWS STS response uses: AccessKeyId / SecretAccessKey / SessionToken
        _ak = credentials.get('access_key') or credentials.get('AccessKeyId')
        _sk = credentials.get('secret_key') or credentials.get('SecretAccessKey')
        _st = credentials.get('session_token') or credentials.get('SessionToken')
        _eks = _boto3.client('eks', region_name=region,
            aws_access_key_id=_ak,
            aws_secret_access_key=_sk,
            aws_session_token=_st,
        )
        _ec2 = _boto3.client('ec2', region_name=region,
            aws_access_key_id=_ak,
            aws_secret_access_key=_sk,
            aws_session_token=_st,
        )

        discovery_tag = [{'Key': 'karpenter.sh/discovery', 'Value': cluster_name}]

        # Get cluster security group
        cluster_info = _eks.describe_cluster(name=cluster_name)
        cluster_sg = cluster_info['cluster']['resourcesVpcConfig']['clusterSecurityGroupId']

        # Get subnets from the cluster's nodegroups (ASG VPCZoneIdentifier is the source of truth)
        subnet_ids = set()
        try:
            nodegroup_names = _eks.list_nodegroups(clusterName=cluster_name).get('nodegroups', [])
            for ng_name in nodegroup_names:
                ng = _eks.describe_nodegroup(clusterName=cluster_name, nodegroupName=ng_name)
                subnet_ids.update(ng['nodegroup'].get('subnets', []))
        except Exception:
            pass

        if not subnet_ids:
            # Fallback: get subnets from the cluster VPC via ASG
            try:
                import boto3 as _b3
                _asg = _b3.client('autoscaling', region_name=region,
                    aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials.get('SessionToken'),
                )
                _asgs = _asg.describe_auto_scaling_groups()['AutoScalingGroups']
                for _g in _asgs:
                    _tags = {t['Key']: t['Value'] for t in _g.get('Tags', [])}
                    if _tags.get('eks:cluster-name') == cluster_name or cluster_name in _g['AutoScalingGroupName']:
                        for _subnet in _g.get('VPCZoneIdentifier', '').split(','):
                            if _subnet.strip():
                                subnet_ids.add(_subnet.strip())
            except Exception:
                pass

        resources_to_tag = [cluster_sg] + list(subnet_ids)
        if resources_to_tag:
            _ec2.create_tags(Resources=resources_to_tag, Tags=discovery_tag)
            logger.info(
                f"[agent_injector] Tagged {len(subnet_ids)} subnets + SG "
                f"with karpenter.sh/discovery={cluster_name}"
            )

    def _verify_karpenter_trust_policy(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> dict:
        """
        KARPENTER-TRUST-VERIFY-01: Verify that KarpenterControllerRole-{cluster_name}
        trust policy contains the correct OIDC provider for this cluster.

        Used by the install_karpenter precheck (fix_B2) to give a clear error
        before queuing the INSTALL_KARPENTER action.

        Returns a dict:
          { "valid": bool, "reason": str, "expected_oidc": str, "actual_principal": str }
        """
        try:
            if credentials and "access_key" in credentials:
                eks_client = boto3.client(
                    "eks",
                    aws_access_key_id=credentials["access_key"],
                    aws_secret_access_key=credentials["secret_key"],
                    aws_session_token=credentials.get("session_token"),
                    region_name=region,
                )
                iam_client = boto3.client(
                    "iam",
                    aws_access_key_id=credentials["access_key"],
                    aws_secret_access_key=credentials["secret_key"],
                    aws_session_token=credentials.get("session_token"),
                )
                sts_client = boto3.client(
                    "sts",
                    aws_access_key_id=credentials["access_key"],
                    aws_secret_access_key=credentials["secret_key"],
                    aws_session_token=credentials.get("session_token"),
                    region_name=region,
                )
            else:
                eks_client = boto3.client("eks", region_name=region)
                iam_client = boto3.client("iam")
                sts_client = boto3.client("sts", region_name=region)

            account_id = sts_client.get_caller_identity()["Account"]

            # Fetch expected OIDC issuer from EKS
            cluster_info = eks_client.describe_cluster(name=cluster_name)
            oidc_issuer = (
                cluster_info["cluster"]
                .get("identity", {})
                .get("oidc", {})
                .get("issuer", "")
            )
            if not oidc_issuer:
                return {
                    "valid": False,
                    "reason": "Cluster has no OIDC issuer configured",
                    "expected_oidc": "",
                    "actual_principal": "",
                }
            expected_oidc_host = oidc_issuer.replace("https://", "").rstrip("/")
            expected_provider_arn = (
                f"arn:aws:iam::{account_id}:oidc-provider/{expected_oidc_host}"
            )

            # Fetch actual trust policy
            role_name = f"KarpenterControllerRole-{cluster_name}"
            try:
                role_resp = iam_client.get_role(RoleName=role_name)
            except iam_client.exceptions.NoSuchEntityException:
                return {
                    "valid": False,
                    "reason": f"Role {role_name} does not exist. Deploy the CF stack first.",
                    "expected_oidc": expected_oidc_host,
                    "actual_principal": "",
                }

            import urllib.parse as _urlparse
            trust_doc_str = role_resp["Role"].get("AssumeRolePolicyDocument", "{}")
            if isinstance(trust_doc_str, str):
                trust_doc = json.loads(_urlparse.unquote(trust_doc_str))
            else:
                trust_doc = trust_doc_str

            # Scan statements for the OIDC Federated principal
            for stmt in trust_doc.get("Statement", []):
                principal = stmt.get("Principal", {})
                federated = principal.get("Federated", "")
                if "oidc-provider" in federated:
                    if federated == expected_provider_arn:
                        return {
                            "valid": True,
                            "reason": "Trust policy is correct",
                            "expected_oidc": expected_oidc_host,
                            "actual_principal": federated,
                        }
                    elif "PLACEHOLDER" in federated:
                        return {
                            "valid": False,
                            "reason": (
                                "Trust policy still uses PLACEHOLDER. "
                                "Reconnect the cluster to trigger automatic trust policy update."
                            ),
                            "expected_oidc": expected_oidc_host,
                            "actual_principal": federated,
                        }
                    else:
                        return {
                            "valid": False,
                            "reason": (
                                f"Trust policy references wrong OIDC provider. "
                                f"Expected: {expected_provider_arn}. Got: {federated}"
                            ),
                            "expected_oidc": expected_oidc_host,
                            "actual_principal": federated,
                        }

            return {
                "valid": False,
                "reason": "No Federated OIDC principal found in trust policy",
                "expected_oidc": expected_oidc_host,
                "actual_principal": "",
            }

        except Exception as e:
            return {
                "valid": False,
                "reason": str(e),
                "expected_oidc": "",
                "actual_principal": "",
            }

    def _patch_aws_auth_configmap(
        self,
        cluster_endpoint: str,
        cluster_ca_data: str,
        credentials: Dict,
        region: str,
        role_arn: str,
    ) -> None:
        """
        Patch the aws-auth ConfigMap to add our backend role.

        Fallback for CONFIG_MAP-only EKS clusters (pre-1.28 or explicitly configured).
        Appends our role to mapRoles if not already present (idempotent).

        Why system:masters: The backend needs full admin access to deploy the
        agent DaemonSet into any namespace. system:masters grants ClusterAdmin.
        In production, scope this to a custom ClusterRole for least privilege.
        """
        import yaml
        import kubernetes

        # Build a one-off Kubernetes client using the assumed credentials token
        k8s_token = self._get_eks_token(
            cluster_name=cluster_endpoint.split(".")[0].replace("https://", ""),
            credentials=credentials,
            region=region,
        )
        ca_bytes = __import__("base64").b64decode(cluster_ca_data)
        configuration = kubernetes.client.Configuration()
        configuration.host = cluster_endpoint
        configuration.ssl_ca_cert = None
        configuration.verify_ssl = True
        import tempfile, os
        ca_file = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
        ca_file.write(ca_bytes)
        ca_file.close()
        configuration.ssl_ca_cert = ca_file.name
        configuration.api_key = {"authorization": f"Bearer {k8s_token}"}

        with kubernetes.client.ApiClient(configuration) as api_client:
            v1 = kubernetes.client.CoreV1Api(api_client)
            try:
                cm = v1.read_namespaced_config_map(name="aws-auth", namespace="kube-system")
            except kubernetes.client.exceptions.ApiException:
                logger.error("aws-auth ConfigMap not found — cluster may not be initialized")
                return

            map_roles = yaml.safe_load(cm.data.get("mapRoles", "[]")) or []
            if any(r.get("rolearn") == role_arn for r in map_roles):
                logger.info(f"Role {role_arn} already in aws-auth mapRoles, skipping")
                return

            map_roles.append({
                "rolearn":  role_arn,
                "username": "spot-optimizer",
                "groups":   ["system:masters"],
            })
            cm.data["mapRoles"] = yaml.dump(map_roles, default_flow_style=False)
            v1.patch_namespaced_config_map(name="aws-auth", namespace="kube-system", body=cm)
            logger.info(f"Patched aws-auth ConfigMap to add role: {role_arn}")

        try:
            os.unlink(ca_file.name)
        except Exception:
            pass

    def _create_access_entry(
        self,
        cluster_name: str,
        credentials: Dict,
        region: str
    ) -> None:
        """
        Create an EKS access entry to allow our backend role to manage the cluster.
        """
        if credentials and 'access_key' in credentials:
            eks_client = boto3.client(
                'eks',
                aws_access_key_id=credentials['access_key'],
                aws_secret_access_key=credentials['secret_key'],
                aws_session_token=credentials.get('session_token'),
                region_name=region
            )
        else:
            eks_client = boto3.client('eks', region_name=region)
        
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

    def _setup_oidc_federation(
        self,
        cluster_id: str,
        cluster_name: str,
        credentials: Dict,
        region: str
    ) -> Optional[str]:
        """
        Setup OIDC federation for secure agent authentication.

        Phase 7 Agent Security: This method configures OIDC provider
        and IAM role for service account-based authentication.

        For now, this is a stub that skips OIDC setup.
        Agent will use API key authentication instead.

        Returns:
            OIDC issuer URL if configured, None otherwise
        """
        logger.info("OIDC federation setup skipped - using API key authentication")
        logger.info("To enable OIDC: Implement full OIDC provider configuration")

        # TODO Phase 7: Implement full OIDC setup
        # 1. Get cluster OIDC provider URL
        # 2. Create/update OIDC provider in IAM
        # 3. Create IAM role for service account
        # 4. Configure trust relationship
        # 5. Return OIDC issuer URL

        return None

    def _get_eks_token(self, cluster_name: str, credentials: Dict, region: str) -> str:
        """
        Generate a Kubernetes authentication token for EKS.

        This replicates the behavior of `aws eks get-token`.
        """
        # Create STS client with provided credentials or use default
        if credentials and 'access_key' in credentials and 'secret_key' in credentials:
            # Use explicit credentials
            session = boto3.Session(
                aws_access_key_id=credentials['access_key'],
                aws_secret_access_key=credentials['secret_key'],
                aws_session_token=credentials.get('session_token'),  # May be None for static creds
                region_name=region
            )
        else:
            # Use default credentials (environment variables, instance profile, etc.)
            logger.info("Using default AWS credentials for token generation")
            session = boto3.Session(region_name=region)

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
        
        # Create temp file for CA cert
        import tempfile
        ca_cert_path = None
        
        try:
            with tempfile.NamedTemporaryFile(delete=False) as ca_cert_file:
                ca_cert_file.write(base64.b64decode(cluster_ca_data))
                ca_cert_file.flush()
                ca_cert_path = ca_cert_file.name

            # Configure Kubernetes client
            config = Configuration()
            config.host = cluster_endpoint
            config.api_key = {"authorization": f"Bearer {k8s_token}"}
            config.ssl_ca_cert = ca_cert_path
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
                            "BACKEND_URL": self.backend_url,  # HTTP URL for heartbeats
                            "BACKEND_WS_URL": backend_ws_url,  # WebSocket URL for real-time comms
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
                rules=self._build_clusterrole_rules(k8s_client)
            )
            
            try:
                rbac_v1.create_cluster_role(body=cluster_role)
            except k8s_client.exceptions.ApiException as e:
                if e.status == 409:
                    # Already exists — patch it so updated rules (e.g. secrets) take effect
                    rbac_v1.patch_cluster_role(name="spot-agent-role", body=cluster_role)
                    logger.info("Patched existing ClusterRole spot-agent-role with updated rules")
                else:
                    raise

            cluster_role_binding = k8s_client.V1ClusterRoleBinding(
                metadata=k8s_client.V1ObjectMeta(name="spot-agent-binding"),
                subjects=[
                    k8s_client.RbacV1Subject(
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
                if e.status == 409:
                    # Already exists — patch to keep subjects/roleRef in sync
                    rbac_v1.patch_cluster_role_binding(name="spot-agent-binding", body=cluster_role_binding)
                    logger.info("Patched existing ClusterRoleBinding spot-agent-binding")
                else:
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
                                        # BACKWARD COMPATIBILITY: Provide API_TOKEN and API_URL for config.py validation
                                        k8s_client.V1EnvVar(
                                            name="API_TOKEN",
                                            value_from=k8s_client.V1EnvVarSource(
                                                secret_key_ref=k8s_client.V1SecretKeySelector(
                                                    name="spot-agent-secret",
                                                    key="API_KEY"
                                                )
                                            )
                                        ),
                                        k8s_client.V1EnvVar(
                                            name="API_URL",
                                            value_from=k8s_client.V1EnvVarSource(
                                                config_map_key_ref=k8s_client.V1ConfigMapKeySelector(
                                                    name="spot-agent-config",
                                                    key="BACKEND_URL"
                                                )
                                            )
                                        ),
                                        k8s_client.V1EnvVar(
                                            name="BACKEND_WS_URL",
                                            value_from=k8s_client.V1EnvVarSource(
                                                config_map_key_ref=k8s_client.V1ConfigMapKeySelector(
                                                    name="spot-agent-config",
                                                    key="BACKEND_WS_URL"
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
                                        ),
                                        k8s_client.V1EnvVar(
                                            name="HOST_PROC",
                                            value="/host/proc"
                                        )
                                    ],
                                    resources=k8s_client.V1ResourceRequirements(
                                        requests={"cpu": "50m", "memory": "64Mi"},
                                        limits={"cpu": "200m", "memory": "256Mi"}
                                    ),
                                    volume_mounts=[
                                        k8s_client.V1VolumeMount(
                                            name="host-proc",
                                            mount_path="/host/proc",
                                            read_only=True
                                        )
                                    ]
                                )
                            ],
                            volumes=[
                                k8s_client.V1Volume(
                                    name="host-proc",
                                    host_path=k8s_client.V1HostPathVolumeSource(path="/proc")
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

            # ── Orchestrator Deployment (singleton, 1 replica) ───────────
            # Responsible for polling pending-commands and executing K8s
            # actions (cordon/drain/patch-nodepool) inside the cluster.
            orchestrator_deployment = k8s_client.V1Deployment(
                metadata=k8s_client.V1ObjectMeta(
                    name="spot-orchestrator",
                    namespace=self.NAMESPACE,
                    labels={"app": "spot-orchestrator"}
                ),
                spec=k8s_client.V1DeploymentSpec(
                    replicas=1,
                    selector=k8s_client.V1LabelSelector(
                        match_labels={"app": "spot-orchestrator"}
                    ),
                    template=k8s_client.V1PodTemplateSpec(
                        metadata=k8s_client.V1ObjectMeta(
                            labels={"app": "spot-orchestrator"}
                        ),
                        spec=k8s_client.V1PodSpec(
                            service_account_name="spot-agent-sa",
                            containers=[
                                k8s_client.V1Container(
                                    name="orchestrator",
                                    image=self.ORCHESTRATOR_IMAGE,
                                    image_pull_policy="Always",
                                    ports=[k8s_client.V1ContainerPort(container_port=8080, name="http")],
                                    env=[
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
                                            name="BACKEND_URL",
                                            value_from=k8s_client.V1EnvVarSource(
                                                config_map_key_ref=k8s_client.V1ConfigMapKeySelector(
                                                    name="spot-agent-config",
                                                    key="BACKEND_URL"
                                                )
                                            )
                                        ),
                                        k8s_client.V1EnvVar(
                                            name="BACKEND_WS_URL",
                                            value_from=k8s_client.V1EnvVarSource(
                                                config_map_key_ref=k8s_client.V1ConfigMapKeySelector(
                                                    name="spot-agent-config",
                                                    key="BACKEND_WS_URL"
                                                )
                                            )
                                        ),
                                        k8s_client.V1EnvVar(
                                            name="API_KEY",
                                            value_from=k8s_client.V1EnvVarSource(
                                                secret_key_ref=k8s_client.V1SecretKeySelector(
                                                    name="spot-agent-secret",
                                                    key="API_KEY"
                                                )
                                            )
                                        ),
                                    ],
                                    resources=k8s_client.V1ResourceRequirements(
                                        requests={"cpu": "100m", "memory": "128Mi"},
                                        limits={"cpu": "500m", "memory": "512Mi"}
                                    ),
                                    readiness_probe=k8s_client.V1Probe(
                                        http_get=k8s_client.V1HTTPGetAction(
                                            path="/healthz",
                                            port=8080
                                        ),
                                        initial_delay_seconds=5,
                                        period_seconds=10
                                    ),
                                    liveness_probe=k8s_client.V1Probe(
                                        http_get=k8s_client.V1HTTPGetAction(
                                            path="/healthz",
                                            port=8080
                                        ),
                                        initial_delay_seconds=15,
                                        period_seconds=20
                                    ),
                                )
                            ]
                        )
                    )
                )
            )

            try:
                apps_v1.create_namespaced_deployment(
                    namespace=self.NAMESPACE,
                    body=orchestrator_deployment
                )
                logger.info("Orchestrator Deployment created successfully")
            except k8s_client.exceptions.ApiException as e:
                if e.status == 409:
                    apps_v1.replace_namespaced_deployment(
                        name="spot-orchestrator",
                        namespace=self.NAMESPACE,
                        body=orchestrator_deployment
                    )
                    logger.info("Orchestrator Deployment updated (already existed)")
                else:
                    logger.warning(f"Orchestrator Deployment creation failed (non-fatal): {e}")

            logger.info("Agent deployment created successfully")

        finally:
            # Cleanup temp certificate file
            if ca_cert_path and os.path.exists(ca_cert_path):
                try:
                    os.remove(ca_cert_path)
                except OSError:
                    pass


    def uninstall_agent(
        self,
        cluster_name: str,
        cluster_endpoint: str,
        cluster_ca_data: str,
        role_arn: str,
        external_id: str,
        region: str
    ) -> Dict:
        """
        Uninstall the agent from the cluster.
        """
        try:
            logger.info(f"Starting agent uninstallation for cluster {cluster_name}")

            # Step 1: Assume customer's cross-account role
            logger.info(f"Assuming cross-account role for uninstall (Region: {region})...")
            assumed_credentials = self._assume_role(role_arn, external_id, region)

            # Step 2: Get backend credentials and generate Kubernetes token
            logger.info("Generating Kubernetes token...")
            backend_credentials = self._get_backend_credentials(region)
            k8s_token = self._get_eks_token(
                cluster_name=cluster_name,
                credentials=backend_credentials,
                region=region
            )

            # Step 3: Remove agent resources
            logger.info("Removing agent resources...")
            self._remove_agent_resources(
                cluster_endpoint=cluster_endpoint,
                cluster_ca_data=cluster_ca_data,
                k8s_token=k8s_token
            )

            return {
                "status": "success",
                "message": f"Agent uninstalled from cluster {cluster_name}"
            }

        except Exception as e:
            logger.error(f"Failed to uninstall agent: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    @staticmethod
    def _build_clusterrole_rules(k8s_client_mod):
        """
        Single source of truth for all ClusterRole rules needed by spot-agent-sa.
        Covers: agent operation + helm 3 release storage + Karpenter full install.
        """
        c = k8s_client_mod
        return [
            # Core: nodes, pods, events, namespaces
            c.V1PolicyRule(
                api_groups=[""],
                resources=["nodes", "pods", "pods/eviction", "events", "namespaces",
                           "services", "endpoints", "persistentvolumes", "persistentvolumeclaims"],
                verbs=["get", "list", "watch", "patch", "create", "delete", "update"]
            ),
            # Core: secrets, configmaps, serviceaccounts (Helm 3 release storage + Karpenter)
            c.V1PolicyRule(
                api_groups=[""],
                resources=["secrets", "configmaps", "serviceaccounts"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            # Apps: daemonsets, deployments, etc. (Helm installs Karpenter as a Deployment)
            c.V1PolicyRule(
                api_groups=["apps", "extensions"],
                resources=["daemonsets", "deployments", "replicasets", "statefulsets"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            # Policy: PDBs
            c.V1PolicyRule(
                api_groups=["policy"],
                resources=["poddisruptionbudgets"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            # Metrics API
            c.V1PolicyRule(
                api_groups=["metrics.k8s.io"],
                resources=["pods", "nodes"],
                verbs=["get", "list"]
            ),
            # CRDs — required for Karpenter helm install (installs ec2nodeclasses, nodepools, nodeclaims CRDs)
            c.V1PolicyRule(
                api_groups=["apiextensions.k8s.io"],
                resources=["customresourcedefinitions"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            # Karpenter CRD instances
            c.V1PolicyRule(
                api_groups=["karpenter.sh", "karpenter.k8s.aws"],
                resources=["nodepools", "nodeclaims", "ec2nodeclasses",
                           "nodepools/status", "nodeclaims/status"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            # RBAC — Karpenter creates its own ClusterRole/Binding during install.
            # 'escalate' allows granting permissions the SA doesn't itself hold (required for Helm installers).
            # 'bind' allows binding roles to subjects.
            c.V1PolicyRule(
                api_groups=["rbac.authorization.k8s.io"],
                resources=["clusterroles", "clusterrolebindings", "roles", "rolebindings"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete", "bind", "escalate"]
            ),
            # Admission webhooks — Karpenter registers mutating/validating webhooks
            c.V1PolicyRule(
                api_groups=["admissionregistration.k8s.io"],
                resources=["mutatingwebhookconfigurations", "validatingwebhookconfigurations"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
            # Leader election (Karpenter controller uses leases)
            c.V1PolicyRule(
                api_groups=["coordination.k8s.io"],
                resources=["leases"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
            ),
        ]

    def patch_clusterrole(
        self,
        cluster_name: str,
        cluster_endpoint: str,
        cluster_ca_data: str,
        region: str
    ) -> Dict:
        """
        Patch the spot-agent ClusterRole in-cluster with the full, up-to-date permission
        set (including secrets/configmaps/RBAC/Karpenter CRDs).  Called as a pre-flight
        step before Karpenter install so we don't require a full agent reinstall.
        """
        try:
            from kubernetes import client as k8s_client
            from kubernetes.client import Configuration, ApiClient
            import tempfile, os

            backend_credentials = self._get_backend_credentials(region)
            k8s_token = self._get_eks_token(
                cluster_name=cluster_name,
                credentials=backend_credentials,
                region=region
            )

            with tempfile.NamedTemporaryFile(delete=False, suffix=".crt") as f:
                f.write(base64.b64decode(cluster_ca_data))
                f.flush()
                ca_cert_path = f.name

            try:
                cfg = Configuration()
                cfg.host = cluster_endpoint
                cfg.api_key = {"authorization": f"Bearer {k8s_token}"}
                cfg.ssl_ca_cert = ca_cert_path
                cfg.verify_ssl = True
                api_client = ApiClient(configuration=cfg)
                rbac_v1 = k8s_client.RbacAuthorizationV1Api(api_client)

                cluster_role = k8s_client.V1ClusterRole(
                    metadata=k8s_client.V1ObjectMeta(name="spot-agent-role"),
                    rules=self._build_clusterrole_rules(k8s_client)
                )

                try:
                    rbac_v1.patch_cluster_role(name="spot-agent-role", body=cluster_role)
                    logger.info(f"[patch_clusterrole] Patched ClusterRole spot-agent-role for {cluster_name}")
                except k8s_client.exceptions.ApiException as e:
                    if e.status == 404:
                        rbac_v1.create_cluster_role(body=cluster_role)
                        logger.info(f"[patch_clusterrole] Created ClusterRole spot-agent-role for {cluster_name}")
                    else:
                        raise

                return {"status": "success", "message": "ClusterRole patched with Karpenter permissions"}
            finally:
                try:
                    os.unlink(ca_cert_path)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"[patch_clusterrole] Non-fatal: {e} — continuing with Karpenter install")
            return {"status": "warning", "message": str(e)}

    def _remove_agent_resources(
        self,
        cluster_endpoint: str,
        cluster_ca_data: str,
        k8s_token: str
    ) -> None:
        """
        Remove agent resources from the cluster using Kubernetes API.
        """
        try:
            from kubernetes import client as k8s_client
            from kubernetes.client import Configuration, ApiClient
        except ImportError:
            raise ImportError("kubernetes package is required")

        # Create temp file for CA cert
        import tempfile
        ca_cert_path = None
        
        try:
            with tempfile.NamedTemporaryFile(delete=False) as ca_cert_file:
                ca_cert_file.write(base64.b64decode(cluster_ca_data))
                ca_cert_file.flush()
                ca_cert_path = ca_cert_file.name

            # Configure Kubernetes client
            config = Configuration()
            config.host = cluster_endpoint
            config.api_key = {"authorization": f"Bearer {k8s_token}"}
            config.ssl_ca_cert = ca_cert_path
            config.verify_ssl = True
            
            api_client = ApiClient(configuration=config)
            core_v1 = k8s_client.CoreV1Api(api_client)
            rbac_v1 = k8s_client.RbacAuthorizationV1Api(api_client)

            # 1. Delete Namespace (cascades to Deployment/DaemonSet/Secret/ConfigMap/ServiceAccount)
            try:
                logger.info(f"Deleting namespace {self.NAMESPACE}...")
                core_v1.delete_namespace(name=self.NAMESPACE)
            except k8s_client.exceptions.ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error deleting namespace: {e}")

            # 2. Delete ClusterRoleBinding
            try:
                logger.info("Deleting ClusterRoleBinding spot-agent-binding...")
                rbac_v1.delete_cluster_role_binding(name="spot-agent-binding")
            except k8s_client.exceptions.ApiException as e:
                 if e.status != 404:
                    logger.warning(f"Error deleting ClusterRoleBinding: {e}")

            # 3. Delete ClusterRole
            try:
                logger.info("Deleting ClusterRole spot-agent-role...")
                rbac_v1.delete_cluster_role(name="spot-agent-role")
            except k8s_client.exceptions.ApiException as e:
                 if e.status != 404:
                    logger.warning(f"Error deleting ClusterRole: {e}")

        finally:
            if ca_cert_path and os.path.exists(ca_cert_path):
                try:
                    os.remove(ca_cert_path)
                except OSError:
                    pass

    # -------------------------------------------------------------------------
    # KARPENTER-AUTO-SETUP: Create all AWS prerequisites on agent connect
    # -------------------------------------------------------------------------

    def _ensure_karpenter_aws_prerequisites(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> None:
        """
        Idempotently creates all AWS prerequisites Karpenter needs to run:
          1. KarpenterNodeRole-{cluster_name}       — IAM role for EC2 nodes Karpenter provisions
          2. KarpenterNodeInstanceProfile-{cluster_name}  — instance profile wrapping the node role
          3. KarpenterControllerRole-{cluster_name} — IRSA role for the Karpenter controller pod
          4. SQS queue {cluster_name}               — Karpenter interruption queue
          5. EventBridge rules for spot/health/rebalance events

        Called automatically on every agent connect.  All operations are idempotent;
        already-existing resources are silently skipped.

        Non-fatal: caller wraps in try/except and logs a warning.
        """
        import json as _json
        import boto3 as _boto3

        _ak = credentials.get('access_key') or credentials.get('AccessKeyId')
        _sk = credentials.get('secret_key') or credentials.get('SecretAccessKey')
        _st = credentials.get('session_token') or credentials.get('SessionToken')

        iam = _boto3.client('iam',
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        sts = _boto3.client('sts', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        sqs = _boto3.client('sqs', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        eb = _boto3.client('events', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        eks = _boto3.client('eks', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)

        account_id = sts.get_caller_identity()["Account"]

        # ── 1. KarpenterNodeRole ─────────────────────────────────────────────
        node_role_name = f"KarpenterNodeRole-{cluster_name}"
        node_role_arn = f"arn:aws:iam::{account_id}:role/{node_role_name}"
        _node_required_policies = [
            "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
            "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        ]
        try:
            iam.get_role(RoleName=node_role_name)
            logger.info(f"[karpenter-prereqs] Node role {node_role_name} already exists")
            # Idempotent: ensure all required policies are attached (handles manually created roles)
            _existing_policies = {
                p["PolicyArn"]
                for p in iam.list_attached_role_policies(RoleName=node_role_name).get("AttachedPolicies", [])
            }
            for policy_arn in _node_required_policies:
                if policy_arn not in _existing_policies:
                    iam.attach_role_policy(RoleName=node_role_name, PolicyArn=policy_arn)
                    logger.info(f"[karpenter-prereqs] Attached missing policy {policy_arn} to {node_role_name}")
        except iam.exceptions.NoSuchEntityException:
            node_trust = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }
            iam.create_role(
                RoleName=node_role_name,
                AssumeRolePolicyDocument=_json.dumps(node_trust),
                Description=f"Node role for Karpenter-provisioned nodes in {cluster_name}",
                Tags=[{"Key": "karpenter.sh/cluster", "Value": cluster_name},
                      {"Key": "ManagedBy", "Value": "SpotOptimizer"}],
            )
            for policy_arn in _node_required_policies:
                iam.attach_role_policy(RoleName=node_role_name, PolicyArn=policy_arn)
            logger.info(f"[karpenter-prereqs] Created node role {node_role_name}")

        # ── 2. KarpenterNodeInstanceProfile ─────────────────────────────────
        profile_name = f"KarpenterNodeInstanceProfile-{cluster_name}"
        try:
            iam.get_instance_profile(InstanceProfileName=profile_name)
            logger.info(f"[karpenter-prereqs] Instance profile {profile_name} already exists")
        except iam.exceptions.NoSuchEntityException:
            iam.create_instance_profile(
                InstanceProfileName=profile_name,
                Tags=[{"Key": "ManagedBy", "Value": "SpotOptimizer"}],
            )
            iam.add_role_to_instance_profile(
                InstanceProfileName=profile_name, RoleName=node_role_name)
            logger.info(f"[karpenter-prereqs] Created instance profile {profile_name}")

        # Add node role to aws-auth so Karpenter-provisioned nodes can join cluster
        try:
            self._add_node_role_to_aws_auth(
                cluster_name=cluster_name, region=region,
                node_role_arn=node_role_arn, credentials=credentials)
        except Exception as _auth_err:
            logger.warning(f"[karpenter-prereqs] aws-auth update failed (non-fatal): {_auth_err}")

        # ── 3. KarpenterControllerRole ───────────────────────────────────────
        ctrl_role_name = f"KarpenterControllerRole-{cluster_name}"
        try:
            iam.get_role(RoleName=ctrl_role_name)
            logger.info(f"[karpenter-prereqs] Controller role {ctrl_role_name} already exists")
        except iam.exceptions.NoSuchEntityException:
            # Fetch OIDC issuer for trust policy
            _oidc_host = ""
            try:
                _c = eks.describe_cluster(name=cluster_name)
                _issuer = _c["cluster"].get("identity", {}).get("oidc", {}).get("issuer", "")
                _oidc_host = _issuer.replace("https://", "").rstrip("/")
            except Exception:
                pass

            if _oidc_host:
                ctrl_trust = {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {
                            "Federated": f"arn:aws:iam::{account_id}:oidc-provider/{_oidc_host}"
                        },
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringEquals": {
                                f"{_oidc_host}:aud": "sts.amazonaws.com",
                                f"{_oidc_host}:sub": "system:serviceaccount:karpenter:karpenter",
                            }
                        }
                    }]
                }
            else:
                # Placeholder trust (will be updated by _update_karpenter_controller_trust_policy)
                ctrl_trust = {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }]
                }

            iam.create_role(
                RoleName=ctrl_role_name,
                AssumeRolePolicyDocument=_json.dumps(ctrl_trust),
                Description=f"Karpenter controller IRSA role for cluster {cluster_name}",
                Tags=[{"Key": "karpenter.sh/cluster", "Value": cluster_name},
                      {"Key": "ManagedBy", "Value": "SpotOptimizer"}],
            )

            # Inline policy: full Karpenter controller permissions
            ctrl_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowScopedEC2InstanceActions",
                        "Effect": "Allow",
                        "Resource": [
                            f"arn:aws:ec2:{region}::image/*",
                            f"arn:aws:ec2:{region}::snapshot/*",
                            f"arn:aws:ec2:{region}:*:security-group/*",
                            f"arn:aws:ec2:{region}:*:subnet/*",
                            f"arn:aws:ec2:{region}:*:launch-template/*",
                            f"arn:aws:ec2:{region}:*:instance/*",
                            f"arn:aws:ec2:{region}:*:volume/*",
                            f"arn:aws:ec2:{region}:*:network-interface/*",
                            f"arn:aws:ec2:{region}:*:spot-instances-request/*",
                            f"arn:aws:ec2:{region}:*:fleet/*",
                        ],
                        "Action": [
                            "ec2:RunInstances", "ec2:CreateFleet",
                            "ec2:CreateLaunchTemplate",
                        ]
                    },
                    {
                        "Sid": "AllowScopedEC2InstanceActionsWithTags",
                        "Effect": "Allow",
                        "Resource": [
                            f"arn:aws:ec2:{region}:*:instance/*",
                            f"arn:aws:ec2:{region}:*:launch-template/*",
                            f"arn:aws:ec2:{region}:*:volume/*",
                            f"arn:aws:ec2:{region}:*:fleet/*",
                            f"arn:aws:ec2:{region}:*:network-interface/*",
                            f"arn:aws:ec2:{region}:*:spot-instances-request/*",
                            f"arn:aws:ec2:{region}:*:security-group/*",
                        ],
                        "Action": [
                            "ec2:TerminateInstances",
                            "ec2:DeleteLaunchTemplate",
                            "ec2:CreateTags",
                        ],
                    },
                    {
                        "Sid": "AllowEC2ReadActions",
                        "Effect": "Allow",
                        "Resource": "*",
                        "Action": [
                            "ec2:DescribeImages",
                            "ec2:DescribeInstances",
                            "ec2:DescribeInstanceTypeOfferings",
                            "ec2:DescribeInstanceTypes",
                            "ec2:DescribeLaunchTemplates",
                            "ec2:DescribeSecurityGroups",
                            "ec2:DescribeSpotPriceHistory",
                            "ec2:DescribeSubnets",
                            "ec2:DescribeAvailabilityZones",
                            "pricing:GetProducts",
                        ]
                    },
                    {
                        "Sid": "AllowIAMInstanceProfile",
                        "Effect": "Allow",
                        "Resource": "*",
                        "Action": [
                            "iam:GetInstanceProfile",
                            "iam:CreateInstanceProfile",
                            "iam:AddRoleToInstanceProfile",
                            "iam:RemoveRoleFromInstanceProfile",
                            "iam:DeleteInstanceProfile",
                            "iam:TagInstanceProfile",
                        ]
                    },
                    {
                        "Sid": "AllowIAMPassRole",
                        "Effect": "Allow",
                        "Resource": node_role_arn,
                        "Action": ["iam:PassRole"],
                    },
                    {
                        "Sid": "AllowSQS",
                        "Effect": "Allow",
                        "Resource": [
                            f"arn:aws:sqs:{region}:{account_id}:{cluster_name}",
                            f"arn:aws:sqs:{region}:{account_id}:KarpenterInterruptionQueue-{cluster_name}",
                        ],
                        "Action": [
                            "sqs:DeleteMessage", "sqs:GetQueueUrl",
                            "sqs:GetQueueAttributes", "sqs:ReceiveMessage",
                        ]
                    },
                    {
                        "Sid": "AllowEKS",
                        "Effect": "Allow",
                        "Resource": "*",
                        "Action": [
                            "eks:DescribeCluster",
                            "eks:ListClusters",
                        ]
                    },
                ]
            }
            iam.put_role_policy(
                RoleName=ctrl_role_name,
                PolicyName="KarpenterControllerPolicy",
                PolicyDocument=_json.dumps(ctrl_policy),
            )
            logger.info(f"[karpenter-prereqs] Created controller role {ctrl_role_name}")

        # ── 4. SQS interruption queue ────────────────────────────────────────
        # Karpenter's INTERRUPTION_QUEUE env var is set to the bare cluster name
        # (settings.interruptionQueue = cluster_name in Helm). Use the same bare
        # name here so the queue always exists before Karpenter starts up.
        sqs_queue_name = cluster_name
        try:
            _q = sqs.get_queue_url(QueueName=sqs_queue_name)
            queue_url = _q["QueueUrl"]
            logger.info(f"[karpenter-prereqs] SQS queue {sqs_queue_name} already exists")
        except sqs.exceptions.QueueDoesNotExist:
            _resp = sqs.create_queue(
                QueueName=sqs_queue_name,
                Attributes={
                    "MessageRetentionPeriod": "300",  # 5 minutes (interruption notices expire fast)
                    "VisibilityTimeout": "30",
                },
                tags={"ManagedBy": "SpotOptimizer", "karpenter.sh/cluster": cluster_name},
            )
            queue_url = _resp["QueueUrl"]
            logger.info(f"[karpenter-prereqs] Created SQS queue {sqs_queue_name}: {queue_url}")

        # Queue policy: allow EventBridge to send messages
        queue_arn = f"arn:aws:sqs:{region}:{account_id}:{sqs_queue_name}"
        q_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": ["events.amazonaws.com", "sqs.amazonaws.com"]},
                "Action": "sqs:SendMessage",
                "Resource": queue_arn,
            }]
        }
        try:
            sqs.set_queue_attributes(
                QueueUrl=queue_url,
                Attributes={"Policy": _json.dumps(q_policy)}
            )
        except Exception as _qp:
            logger.warning(f"[karpenter-prereqs] SQS policy set failed (non-fatal): {_qp}")

        # ── 5. EventBridge rules ─────────────────────────────────────────────
        _eb_rules = [
            {
                "name": f"KarpenterInterruptionRule-{cluster_name}",
                "pattern": _json.dumps({
                    "source": ["aws.ec2"],
                    "detail-type": [
                        "EC2 Spot Instance Interruption Warning",
                        "EC2 Instance Rebalance Recommendation",
                        "EC2 Instance State-change Notification",
                    ]
                }),
            },
            {
                "name": f"KarpenterHealthRule-{cluster_name}",
                "pattern": _json.dumps({
                    "source": ["aws.health"],
                    "detail-type": ["AWS Health Event"],
                    "detail": {
                        "service": ["EC2"],
                        "eventTypeCategory": ["scheduledChange"]
                    }
                }),
            },
        ]
        for rule_def in _eb_rules:
            try:
                eb.put_rule(
                    Name=rule_def["name"],
                    EventPattern=rule_def["pattern"],
                    State="ENABLED",
                    Description=f"Karpenter interruption events for {cluster_name}",
                    Tags=[{"Key": "ManagedBy", "Value": "SpotOptimizer"}],
                )
                eb.put_targets(
                    Rule=rule_def["name"],
                    Targets=[{"Id": "KarpenterInterruptionQueue", "Arn": queue_arn}],
                )
                logger.info(f"[karpenter-prereqs] EventBridge rule {rule_def['name']} configured")
            except Exception as _eb_err:
                logger.warning(
                    f"[karpenter-prereqs] EventBridge rule {rule_def['name']} failed: {_eb_err}")

        logger.info(
            f"[karpenter-prereqs] All prerequisites ensured for cluster {cluster_name}"
        )

    def _add_node_role_to_aws_auth(
        self,
        cluster_name: str,
        region: str,
        node_role_arn: str,
        credentials: Dict,
    ) -> None:
        """
        Add the KarpenterNodeRole to aws-auth ConfigMap (or EKS Access Entry API)
        so that nodes Karpenter provisions can join the cluster.
        Idempotent — silently skips if already present.
        """
        import boto3 as _boto3
        _ak = credentials.get('access_key') or credentials.get('AccessKeyId')
        _sk = credentials.get('secret_key') or credentials.get('SecretAccessKey')
        _st = credentials.get('session_token') or credentials.get('SessionToken')
        eks = _boto3.client('eks', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)

        auth_mode = self._get_cluster_auth_mode(eks, cluster_name)

        if auth_mode in ("API", "API_AND_CONFIG_MAP"):
            # Use EKS Access Entry API — add node role as EC2_LINUX type
            try:
                eks.create_access_entry(
                    clusterName=cluster_name,
                    principalArn=node_role_arn,
                    type='EC2_LINUX',
                )
                logger.info(
                    f"[karpenter-prereqs] Created EC2_LINUX access entry for node role {node_role_arn}"
                )
            except eks.exceptions.ResourceInUseException:
                logger.info(
                    f"[karpenter-prereqs] Node role access entry already exists for {node_role_arn}"
                )
        else:
            # Patch aws-auth ConfigMap
            import yaml
            try:
                from kubernetes import client as k8s_client
                _cluster_info = eks.describe_cluster(name=cluster_name)
                _endpoint = _cluster_info["cluster"]["endpoint"]
                _ca = _cluster_info["cluster"]["certificateAuthority"]["data"]
                _token = self._get_eks_token(
                    cluster_name=cluster_name, credentials=credentials, region=region)
                _k8s_creds = {
                    'access_key': _ak, 'secret_key': _sk, 'session_token': _st}
                import tempfile, os as _os
                ca_bytes = __import__("base64").b64decode(_ca)
                _ca_file = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
                _ca_file.write(ca_bytes)
                _ca_file.close()
                _cfg = k8s_client.Configuration()
                _cfg.host = _endpoint
                _cfg.ssl_ca_cert = _ca_file.name
                _cfg.api_key = {"authorization": f"Bearer {_token}"}
                with k8s_client.ApiClient(_cfg) as _api:
                    v1 = k8s_client.CoreV1Api(_api)
                    try:
                        cm = v1.read_namespaced_config_map(
                            name="aws-auth", namespace="kube-system")
                        map_roles = yaml.safe_load(cm.data.get("mapRoles", "[]")) or []
                        if any(r.get("rolearn") == node_role_arn for r in map_roles):
                            logger.info(
                                f"[karpenter-prereqs] Node role already in aws-auth")
                            return
                        map_roles.append({
                            "rolearn": node_role_arn,
                            "username": "system:node:{{EC2PrivateDNSName}}",
                            "groups": ["system:bootstrappers", "system:nodes"],
                        })
                        cm.data["mapRoles"] = yaml.dump(map_roles, default_flow_style=False)
                        v1.patch_namespaced_config_map(
                            name="aws-auth", namespace="kube-system", body=cm)
                        logger.info(
                            f"[karpenter-prereqs] Added node role to aws-auth: {node_role_arn}")
                    except Exception as _cm_err:
                        logger.warning(
                            f"[karpenter-prereqs] aws-auth ConfigMap patch failed: {_cm_err}")
                try:
                    _os.unlink(_ca_file.name)
                except Exception:
                    pass
            except Exception as _k8s_err:
                logger.warning(
                    f"[karpenter-prereqs] aws-auth update failed: {_k8s_err}")

    def cleanup_karpenter_aws_resources(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> None:
        """Backward-compatible alias — delegates to delete_all_cluster_karpenter_resources."""
        self.delete_all_cluster_karpenter_resources(cluster_name, region, credentials)

    def delete_all_cluster_karpenter_resources(
        self,
        cluster_name: str,
        region: str,
        credentials: Dict,
    ) -> dict:
        """
        Fully delete all AWS resources created by the platform for this cluster's
        Karpenter setup.  Called on:
          - Karpenter uninstall (DELETE /clusters/{id}/install)
          - Agent removal   (DELETE /clusters/{id}/agent)
          - Cluster deletion (DELETE /clusters/{id})

        Resources deleted (all are cluster-scoped, nothing shared between clusters):
          1. EventBridge rules  KarpenterInterruptionRule-{cluster_name}
                                KarpenterHealthRule-{cluster_name}
          2. SQS queue          KarpenterInterruptionQueue-{cluster_name}  (+ bare name fallback)
          3. IAM instance profile  KarpenterNodeInstanceProfile-{cluster_name}
             (role removed from profile before profile deletion)
          4. IAM roles          KarpenterNodeRole-{cluster_name}
                                KarpenterControllerRole-{cluster_name}
             (managed/inline policies detached/deleted before role deletion)
          5. EKS access entry   for KarpenterNodeRole ARN (if cluster still accessible)
          6. karpenter.sh/discovery tags  removed from subnets + cluster SG

        OIDC providers are NOT deleted because they may be shared by multiple clusters
        in the same AWS account.

        Returns a dict with keys "deleted" and "errors" listing what succeeded/failed.
        """
        import json as _json
        import boto3 as _boto3
        from botocore.exceptions import ClientError as _CE

        _ak = credentials.get('access_key') or credentials.get('AccessKeyId')
        _sk = credentials.get('secret_key') or credentials.get('SecretAccessKey')
        _st = credentials.get('session_token') or credentials.get('SessionToken')

        iam = _boto3.client('iam',
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        sqs = _boto3.client('sqs', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        eb  = _boto3.client('events', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        eks = _boto3.client('eks', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        ec2 = _boto3.client('ec2', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)
        sts = _boto3.client('sts', region_name=region,
            aws_access_key_id=_ak, aws_secret_access_key=_sk, aws_session_token=_st)

        deleted = []
        errors  = []

        def _ok(msg):
            logger.info(f"[karpenter-cleanup] {msg}")
            deleted.append(msg)

        def _warn(msg):
            logger.warning(f"[karpenter-cleanup] {msg}")
            errors.append(msg)

        # ── 1. EventBridge rules ─────────────────────────────────────────────
        for rule_name in [
            f"KarpenterInterruptionRule-{cluster_name}",
            f"KarpenterHealthRule-{cluster_name}",
        ]:
            try:
                _tgts = eb.list_targets_by_rule(Rule=rule_name).get("Targets", [])
                if _tgts:
                    eb.remove_targets(Rule=rule_name, Ids=[t["Id"] for t in _tgts])
                eb.delete_rule(Name=rule_name)
                _ok(f"Deleted EventBridge rule {rule_name}")
            except _CE as e:
                if e.response['Error']['Code'] in ('ResourceNotFoundException',):
                    _ok(f"EventBridge rule {rule_name} already absent")
                else:
                    _warn(f"EventBridge rule {rule_name}: {e}")
            except Exception as e:
                _warn(f"EventBridge rule {rule_name}: {e}")

        # ── 2. SQS queue ─────────────────────────────────────────────────────
        # Try bare cluster name first (new convention), then the old prefixed name for backward compat
        for _q_name in [cluster_name, f"KarpenterInterruptionQueue-{cluster_name}"]:
            try:
                _q_url = sqs.get_queue_url(QueueName=_q_name)["QueueUrl"]
                sqs.delete_queue(QueueUrl=_q_url)
                _ok(f"Deleted SQS queue {_q_name}")
                break
            except _CE as e:
                if 'NonExistentQueue' in str(e) or 'QueueDoesNotExist' in str(e):
                    continue
                _warn(f"SQS queue {_q_name}: {e}")
                break
            except Exception as e:
                _warn(f"SQS queue {_q_name}: {e}")
                break

        # ── 3. IAM instance profile ──────────────────────────────────────────
        profile_name = f"KarpenterNodeInstanceProfile-{cluster_name}"
        try:
            _prof = iam.get_instance_profile(InstanceProfileName=profile_name)
            for _r in _prof['InstanceProfile'].get('Roles', []):
                iam.remove_role_from_instance_profile(
                    InstanceProfileName=profile_name, RoleName=_r['RoleName'])
            iam.delete_instance_profile(InstanceProfileName=profile_name)
            _ok(f"Deleted IAM instance profile {profile_name}")
        except _CE as e:
            if 'NoSuchEntity' in str(e):
                _ok(f"Instance profile {profile_name} already absent")
            else:
                _warn(f"Instance profile {profile_name}: {e}")
        except Exception as e:
            _warn(f"Instance profile {profile_name}: {e}")

        # ── 4. IAM roles ─────────────────────────────────────────────────────
        # KarpenterNodeRole — detach managed policies, then delete
        node_role = f"KarpenterNodeRole-{cluster_name}"
        try:
            _attached = iam.list_attached_role_policies(RoleName=node_role).get(
                'AttachedPolicies', [])
            for _p in _attached:
                iam.detach_role_policy(RoleName=node_role, PolicyArn=_p['PolicyArn'])
            # Also delete any inline policies
            for _ip in iam.list_role_policies(RoleName=node_role).get('PolicyNames', []):
                iam.delete_role_policy(RoleName=node_role, PolicyName=_ip)
            iam.delete_role(RoleName=node_role)
            _ok(f"Deleted IAM role {node_role}")
        except _CE as e:
            if 'NoSuchEntity' in str(e):
                _ok(f"IAM role {node_role} already absent")
            else:
                _warn(f"IAM role {node_role}: {e}")
        except Exception as e:
            _warn(f"IAM role {node_role}: {e}")

        # KarpenterControllerRole — delete inline policy, then delete role
        ctrl_role = f"KarpenterControllerRole-{cluster_name}"
        try:
            for _ip in iam.list_role_policies(RoleName=ctrl_role).get('PolicyNames', []):
                iam.delete_role_policy(RoleName=ctrl_role, PolicyName=_ip)
            _attached_ctrl = iam.list_attached_role_policies(RoleName=ctrl_role).get(
                'AttachedPolicies', [])
            for _p in _attached_ctrl:
                iam.detach_role_policy(RoleName=ctrl_role, PolicyArn=_p['PolicyArn'])
            iam.delete_role(RoleName=ctrl_role)
            _ok(f"Deleted IAM role {ctrl_role}")
        except _CE as e:
            if 'NoSuchEntity' in str(e):
                _ok(f"IAM role {ctrl_role} already absent")
            else:
                _warn(f"IAM role {ctrl_role}: {e}")
        except Exception as e:
            _warn(f"IAM role {ctrl_role}: {e}")

        # ── 5. EKS access entry for node role ────────────────────────────────
        try:
            account_id = sts.get_caller_identity()["Account"]
            node_role_arn = f"arn:aws:iam::{account_id}:role/{node_role}"
            eks.delete_access_entry(clusterName=cluster_name, principalArn=node_role_arn)
            _ok(f"Deleted EKS access entry for {node_role_arn}")
        except _CE as e:
            if 'ResourceNotFoundException' in str(e) or 'ResourceNotFound' in str(e):
                _ok("EKS access entry for node role already absent")
            else:
                _warn(f"EKS access entry: {e}")
        except Exception as e:
            _warn(f"EKS access entry: {e}")

        # ── 6. Remove karpenter.sh/discovery tags from subnets + cluster SG ──
        try:
            _cluster_info = eks.describe_cluster(name=cluster_name)
            _vpc_cfg = _cluster_info['cluster'].get('resourcesVpcConfig', {})
            _sg = _vpc_cfg.get('clusterSecurityGroupId', '')
            _subnet_ids = set()
            for _ng in eks.list_nodegroups(clusterName=cluster_name).get('nodegroups', []):
                _ng_detail = eks.describe_nodegroup(
                    clusterName=cluster_name, nodegroupName=_ng)
                _subnet_ids.update(
                    _ng_detail['nodegroup'].get('subnets', []))
            _resources = ([_sg] if _sg else []) + list(_subnet_ids)
            if _resources:
                ec2.delete_tags(
                    Resources=_resources,
                    Tags=[{'Key': 'karpenter.sh/discovery'}]
                )
                _ok(f"Removed karpenter.sh/discovery tag from {len(_resources)} resources")
        except _CE as e:
            if 'ResourceNotFoundException' in str(e):
                _ok("Cluster already deleted from EKS — skipping tag removal")
            else:
                _warn(f"Tag removal: {e}")
        except Exception as e:
            _warn(f"Tag removal: {e}")

        logger.info(
            f"[karpenter-cleanup] Finished for cluster {cluster_name}: "
            f"{len(deleted)} deleted, {len(errors)} warnings"
        )
        return {"deleted": deleted, "errors": errors}
