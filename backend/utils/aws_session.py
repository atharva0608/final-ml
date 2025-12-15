"""
AWS Session Management - Agentless Cross-Account Access

Implements secure cross-account AWS access using STS AssumeRole with ExternalID
for confused deputy protection. This is the ONLY way to access AWS resources.

Security Rules:
1. ExternalID is MANDATORY for all cross-account access
2. No long-lived credentials allowed
3. All sessions use temporary STS credentials
4. Sessions expire after 1 hour (AWS default)
"""

import boto3
from typing import Optional
from sqlalchemy.orm import Session
from database.models import Account
import uuid


def get_cross_account_session(
    account_id: str,
    region: str,
    db: Session
) -> boto3.Session:
    """
    Get a boto3 session for cross-account access using STS AssumeRole

    This is the ONLY authorized way to access AWS resources. Direct boto3.client()
    calls are FORBIDDEN in production code.

    Args:
        account_id: AWS Account ID (12 digits)
        region: AWS region (e.g., 'ap-south-1')
        db: Database session to fetch account configuration

    Returns:
        boto3.Session with temporary credentials

    Raises:
        ValueError: If account not found or ExternalID missing
        ClientError: If AssumeRole fails (invalid credentials, missing trust policy, etc.)

    Example:
        >>> session = get_cross_account_session("123456789012", "ap-south-1", db)
        >>> ec2 = session.client('ec2')
        >>> instances = ec2.describe_instances()

    Security:
        - Uses ExternalID to prevent confused deputy attacks
        - Temporary credentials expire after 1 hour
        - All actions are audited via CloudTrail with external_id in request
    """
    # Fetch account configuration from database
    account = db.query(Account).filter(
        Account.account_id == account_id,
        Account.is_active == True
    ).first()

    if not account:
        raise ValueError(f"Account {account_id} not found or inactive")

    # Verify ExternalID is present (mandatory for security)
    if not account.external_id:
        raise ValueError(f"Account {account_id} missing ExternalID - cannot assume role without confused deputy protection")

    # Verify role ARN is present
    if not account.role_arn:
        raise ValueError(f"Account {account_id} missing role_arn")

    # Create STS client (uses default credentials or instance profile)
    sts_client = boto3.client('sts')

    # Assume role with ExternalID
    try:
        response = sts_client.assume_role(
            RoleArn=account.role_arn,
            RoleSessionName=f"SpotOptimizer-{account_id}-{uuid.uuid4().hex[:8]}",
            ExternalId=account.external_id,
            DurationSeconds=3600  # 1 hour (maximum for AssumeRole)
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to assume role for account {account_id}: {str(e)}\n"
            f"Verify:\n"
            f"  1. Role ARN is correct: {account.role_arn}\n"
            f"  2. Trust policy allows AssumeRole with ExternalID: {account.external_id}\n"
            f"  3. IAM role has necessary permissions\n"
        )

    # Extract temporary credentials
    credentials = response['Credentials']

    # Create boto3 session with temporary credentials
    session = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region
    )

    return session


def get_ec2_client(account_id: str, region: str, db: Session):
    """
    Get EC2 client for cross-account access

    Convenience wrapper around get_cross_account_session for EC2 operations.

    Args:
        account_id: AWS Account ID
        region: AWS region
        db: Database session

    Returns:
        boto3 EC2 client
    """
    session = get_cross_account_session(account_id, region, db)
    return session.client('ec2')


def get_pricing_client(account_id: str, db: Session):
    """
    Get Pricing client for cross-account access

    Note: Pricing API is only available in us-east-1 and ap-south-1

    Args:
        account_id: AWS Account ID
        db: Database session

    Returns:
        boto3 Pricing client
    """
    session = get_cross_account_session(account_id, 'us-east-1', db)
    return session.client('pricing', region_name='us-east-1')


def validate_account_access(account_id: str, region: str, db: Session) -> dict:
    """
    Validate that cross-account access is working

    Performs a lightweight test (GetCallerIdentity) to verify STS AssumeRole works.

    Args:
        account_id: AWS Account ID
        region: AWS region
        db: Database session

    Returns:
        dict with validation results

    Example:
        >>> result = validate_account_access("123456789012", "ap-south-1", db)
        >>> print(result)
        {
            "valid": True,
            "assumed_role_arn": "arn:aws:sts::123456789012:assumed-role/SpotOptimizerRole/...",
            "account": "123456789012"
        }
    """
    try:
        session = get_cross_account_session(account_id, region, db)
        sts = session.client('sts')

        identity = sts.get_caller_identity()

        return {
            "valid": True,
            "assumed_role_arn": identity['Arn'],
            "account": identity['Account'],
            "user_id": identity['UserId']
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }
