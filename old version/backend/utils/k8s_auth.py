"""
Kubernetes Authentication Helper

This module provides authentication utilities for connecting to Amazon EKS clusters
using AWS STS tokens. It generates the necessary kubeconfig and provides authenticated
Kubernetes clients.

Key Features:
1. STS Token Generation: Uses AWS IAM credentials to generate EKS tokens
2. KubeConfig Builder: Creates temporary kubeconfig for EKS cluster access
3. Client Factory: Returns authenticated kubernetes.client instances
"""

import base64
import tempfile
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    print("⚠️  Warning: kubernetes Python package not installed")
    print("   Install with: pip install kubernetes==26.1.0")

import boto3
from botocore.signers import RequestSigner
from botocore.model import ServiceId

from database.models import Account


class K8sAuthError(Exception):
    """Raised when Kubernetes authentication fails"""
    pass


def get_eks_token(cluster_name: str, region: str, aws_access_key_id: str,
                  aws_secret_access_key: str, aws_session_token: Optional[str] = None) -> str:
    """
    Generate an EKS authentication token using AWS STS

    This creates a presigned URL for the EKS cluster and extracts the token
    that Kubernetes can use for authentication.

    Args:
        cluster_name: Name of the EKS cluster
        region: AWS region (e.g., 'us-east-1')
        aws_access_key_id: AWS access key
        aws_secret_access_key: AWS secret key
        aws_session_token: Optional session token (for assumed roles)

    Returns:
        Base64-encoded authentication token

    Raises:
        K8sAuthError: If token generation fails
    """
    try:
        # Create STS client
        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region
        )

        client_sts = session.client('sts', region_name=region)
        service_id = ServiceId('sts')

        # Create presigned URL for EKS authentication
        signer = RequestSigner(
            service_id,
            region,
            'sts',
            'v4',
            session.get_credentials(),
            session.events
        )

        params = {
            'method': 'GET',
            'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
            'body': {},
            'headers': {
                'x-k8s-aws-id': cluster_name
            },
            'context': {}
        }

        signed_url = signer.generate_presigned_url(
            params,
            region_name=region,
            expires_in=60,
            operation_name=''
        )

        # Extract token from URL (remove https:// prefix and encode)
        token = base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8')

        # Remove padding
        return 'k8s-aws-v1.' + token.rstrip('=')

    except Exception as e:
        raise K8sAuthError(f"Failed to generate EKS token: {e}")


def get_eks_cluster_endpoint(cluster_name: str, region: str, aws_access_key_id: str,
                              aws_secret_access_key: str, aws_session_token: Optional[str] = None) -> Dict[str, str]:
    """
    Get EKS cluster endpoint and CA certificate

    Args:
        cluster_name: Name of the EKS cluster
        region: AWS region
        aws_access_key_id: AWS access key
        aws_secret_access_key: AWS secret key
        aws_session_token: Optional session token

    Returns:
        Dict with 'endpoint' and 'certificate_authority' keys

    Raises:
        K8sAuthError: If cluster info cannot be retrieved
    """
    try:
        eks_client = boto3.client(
            'eks',
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

        response = eks_client.describe_cluster(name=cluster_name)
        cluster = response['cluster']

        return {
            'endpoint': cluster['endpoint'],
            'certificate_authority': cluster['certificateAuthority']['data']
        }

    except Exception as e:
        raise K8sAuthError(f"Failed to get EKS cluster info: {e}")


def create_kubeconfig(cluster_name: str, cluster_endpoint: str,
                      cluster_ca: str, token: str) -> str:
    """
    Create a temporary kubeconfig file

    Args:
        cluster_name: Name of the EKS cluster
        cluster_endpoint: Cluster API endpoint URL
        cluster_ca: Base64-encoded CA certificate
        token: Authentication token

    Returns:
        Path to temporary kubeconfig file
    """
    kubeconfig_content = f"""
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: {cluster_endpoint}
    certificate-authority-data: {cluster_ca}
  name: {cluster_name}
contexts:
- context:
    cluster: {cluster_name}
    user: {cluster_name}-user
  name: {cluster_name}
current-context: {cluster_name}
users:
- name: {cluster_name}-user
  user:
    token: {token}
"""

    # Write to temporary file
    fd, path = tempfile.mkstemp(suffix='.kubeconfig', text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(kubeconfig_content)
    except Exception:
        os.close(fd)
        raise

    return path


def get_k8s_client(cluster_name: str, region: str, account: Account,
                   db: Session) -> client.CoreV1Api:
    """
    Get authenticated Kubernetes client for EKS cluster

    This is the main entry point for getting a K8s client. It handles:
    1. AWS credential retrieval (via STS AssumeRole)
    2. EKS token generation
    3. Cluster endpoint lookup
    4. Kubeconfig creation
    5. Client initialization

    Args:
        cluster_name: Name of the EKS cluster
        region: AWS region
        account: Database account record (contains AWS credentials)
        db: Database session

    Returns:
        Authenticated kubernetes.client.CoreV1Api instance

    Raises:
        K8sAuthError: If authentication fails
        ImportError: If kubernetes package not installed
    """
    if not KUBERNETES_AVAILABLE:
        raise ImportError(
            "kubernetes Python package is required but not installed. "
            "Install with: pip install kubernetes==26.1.0"
        )

    try:
        # Get AWS credentials (via STS AssumeRole if needed)
        from utils.aws_session import get_aws_credentials

        creds = get_aws_credentials(
            account_id=account.account_id,
            region=region,
            db=db
        )

        # Get cluster info
        cluster_info = get_eks_cluster_endpoint(
            cluster_name=cluster_name,
            region=region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds.get('SessionToken')
        )

        # Generate EKS token
        token = get_eks_token(
            cluster_name=cluster_name,
            region=region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds.get('SessionToken')
        )

        # Create temporary kubeconfig
        kubeconfig_path = create_kubeconfig(
            cluster_name=cluster_name,
            cluster_endpoint=cluster_info['endpoint'],
            cluster_ca=cluster_info['certificate_authority'],
            token=token
        )

        # Load kubeconfig and create client
        config.load_kube_config(config_file=kubeconfig_path)
        k8s_client = client.CoreV1Api()

        # Clean up temporary kubeconfig after loading
        try:
            os.unlink(kubeconfig_path)
        except Exception:
            pass  # Best effort cleanup

        return k8s_client

    except Exception as e:
        raise K8sAuthError(f"Failed to create Kubernetes client: {e}")


def get_apps_v1_client(cluster_name: str, region: str, account: Account,
                       db: Session) -> client.AppsV1Api:
    """
    Get authenticated Kubernetes Apps/v1 API client (for Deployments, etc.)

    Args:
        cluster_name: Name of the EKS cluster
        region: AWS region
        account: Database account record
        db: Database session

    Returns:
        Authenticated kubernetes.client.AppsV1Api instance
    """
    if not KUBERNETES_AVAILABLE:
        raise ImportError("kubernetes Python package is required")

    # First get CoreV1Api to initialize config
    get_k8s_client(cluster_name, region, account, db)

    # Now return AppsV1Api (config is already loaded)
    return client.AppsV1Api()


# For testing
if __name__ == '__main__':
    print("="*80)
    print("KUBERNETES AUTHENTICATION HELPER")
    print("="*80)
    print("\nThis module provides EKS cluster authentication using AWS STS.")
    print("\nKey Functions:")
    print("  - get_eks_token(): Generate EKS authentication token")
    print("  - get_eks_cluster_endpoint(): Get cluster API endpoint and CA")
    print("  - create_kubeconfig(): Create temporary kubeconfig file")
    print("  - get_k8s_client(): Get authenticated Kubernetes client (main entry point)")
    print("\nUsage:")
    print("  from utils.k8s_auth import get_k8s_client")
    print("  k8s_client = get_k8s_client(cluster_name, region, account, db)")
    print("  nodes = k8s_client.list_node()")
    print("\nPrerequisites:")
    print("  - pip install kubernetes==26.1.0")
    print("  - AWS credentials with EKS access")
    print("  - Proper IAM permissions for cluster access")
    print("="*80)
