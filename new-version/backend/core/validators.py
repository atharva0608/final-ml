"""
Custom Validators

Validation functions for business logic and data integrity
"""
import re
from typing import Optional, List
from datetime import datetime
import pytz


def validate_aws_account_id(account_id: str) -> bool:
    """
    Validate AWS account ID format

    Args:
        account_id: AWS account ID

    Returns:
        True if valid, False otherwise
    """
    # AWS account IDs are 12 digits
    return bool(re.match(r'^\d{12}$', account_id))


def validate_aws_role_arn(role_arn: str) -> bool:
    """
    Validate AWS IAM role ARN format

    Args:
        role_arn: AWS IAM role ARN

    Returns:
        True if valid, False otherwise
    """
    # Format: arn:aws:iam::123456789012:role/RoleName
    pattern = r'^arn:aws:iam::\d{12}:role/[\w+=,.@-]+$'
    return bool(re.match(pattern, role_arn))


def validate_aws_region(region: str) -> bool:
    """
    Validate AWS region name

    Args:
        region: AWS region name

    Returns:
        True if valid, False otherwise
    """
    # Common AWS regions
    valid_regions = {
        # US regions
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
        # EU regions
        'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1', 'eu-north-1', 'eu-south-1',
        # Asia Pacific
        'ap-south-1', 'ap-northeast-1', 'ap-northeast-2', 'ap-northeast-3',
        'ap-southeast-1', 'ap-southeast-2', 'ap-east-1',
        # Canada
        'ca-central-1',
        # South America
        'sa-east-1',
        # Middle East
        'me-south-1',
        # Africa
        'af-south-1',
        # GovCloud
        'us-gov-east-1', 'us-gov-west-1'
    }
    return region in valid_regions


def validate_instance_id(instance_id: str) -> bool:
    """
    Validate EC2 instance ID format

    Args:
        instance_id: EC2 instance ID

    Returns:
        True if valid, False otherwise
    """
    # Format: i-0abc123456def7890 (i- followed by 17 hex chars)
    return bool(re.match(r'^i-[0-9a-f]{17}$', instance_id))


def validate_vpc_id(vpc_id: str) -> bool:
    """
    Validate VPC ID format

    Args:
        vpc_id: VPC ID

    Returns:
        True if valid, False otherwise
    """
    # Format: vpc-0abc123 (vpc- followed by 8 or 17 hex chars)
    return bool(re.match(r'^vpc-[0-9a-f]{8,17}$', vpc_id))


def validate_cluster_name(name: str) -> tuple[bool, Optional[str]]:
    """
    Validate Kubernetes cluster name

    Args:
        name: Cluster name

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Cluster names must be 1-255 characters
    if not name or len(name) > 255:
        return False, "Cluster name must be 1-255 characters"

    # Must start and end with alphanumeric
    if not re.match(r'^[a-zA-Z0-9]', name) or not re.match(r'[a-zA-Z0-9]$', name):
        return False, "Cluster name must start and end with alphanumeric character"

    # Can contain alphanumeric, hyphens, and underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return False, "Cluster name can only contain alphanumeric, hyphens, and underscores"

    return True, None


def validate_timezone(timezone: str) -> bool:
    """
    Validate timezone string using pytz

    Args:
        timezone: Timezone string (e.g., 'America/New_York')

    Returns:
        True if valid, False otherwise
    """
    try:
        pytz.timezone(timezone)
        return True
    except pytz.exceptions.UnknownTimeZoneError:
        return False


def validate_schedule_matrix(matrix: List[int]) -> tuple[bool, Optional[str]]:
    """
    Validate hibernation schedule matrix

    Args:
        matrix: 168-element array of 0s and 1s

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Must have exactly 168 elements (7 days * 24 hours)
    if len(matrix) != 168:
        return False, f"Schedule matrix must have exactly 168 elements, got {len(matrix)}"

    # All values must be 0 or 1
    for i, val in enumerate(matrix):
        if val not in [0, 1]:
            return False, f"Matrix element at index {i} must be 0 or 1, got {val}"

    return True, None


def validate_cron_expression(expression: str) -> tuple[bool, Optional[str]]:
    """
    Validate cron expression format

    Args:
        expression: Cron expression (e.g., '0 0 * * *')

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Basic cron validation (5 fields)
    parts = expression.split()
    if len(parts) != 5:
        return False, "Cron expression must have 5 fields: minute hour day month weekday"

    # Each field should be valid (basic check)
    valid_patterns = [
        r'^(\*|([0-5]?\d)(,([0-5]?\d))*|([0-5]?\d)-([0-5]?\d)|\*/\d+)$',  # minute (0-59)
        r'^(\*|(1?\d|2[0-3])(,(1?\d|2[0-3]))*|(1?\d|2[0-3])-(1?\d|2[0-3])|\*/\d+)$',  # hour (0-23)
        r'^(\*|([1-9]|[12]\d|3[01])(,([1-9]|[12]\d|3[01]))*|([1-9]|[12]\d|3[01])-([1-9]|[12]\d|3[01])|\*/\d+)$',  # day (1-31)
        r'^(\*|([1-9]|1[0-2])(,([1-9]|1[0-2]))*|([1-9]|1[0-2])-([1-9]|1[0-2])|\*/\d+)$',  # month (1-12)
        r'^(\*|[0-6](,[0-6])*|[0-6]-[0-6]|\*/\d+)$',  # weekday (0-6)
    ]

    for i, (part, pattern) in enumerate(zip(parts, valid_patterns)):
        if not re.match(pattern, part):
            return False, f"Invalid cron field at position {i + 1}: {part}"

    return True, None


def validate_percentage(value: float, min_val: float = 0.0, max_val: float = 100.0) -> bool:
    """
    Validate percentage value

    Args:
        value: Percentage value
        min_val: Minimum allowed value (default: 0.0)
        max_val: Maximum allowed value (default: 100.0)

    Returns:
        True if valid, False otherwise
    """
    return min_val <= value <= max_val


def validate_spot_percentage(value: int) -> tuple[bool, Optional[str]]:
    """
    Validate spot instance percentage

    Args:
        value: Spot percentage (0-100)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not 0 <= value <= 100:
        return False, "Spot percentage must be between 0 and 100"

    # Warn if percentage is very high (risk of interruptions)
    if value > 90:
        return True, "Warning: Spot percentage >90% may increase interruption risk"

    return True, None


def validate_instance_type(instance_type: str) -> bool:
    """
    Validate EC2 instance type format

    Args:
        instance_type: EC2 instance type (e.g., 'm5.xlarge')

    Returns:
        True if valid, False otherwise
    """
    # Format: family.size (e.g., m5.xlarge, c5n.18xlarge, t3a.micro)
    pattern = r'^[a-z][0-9][a-z]?\.(micro|small|medium|large|x?large|[0-9]+x?large|metal)$'
    return bool(re.match(pattern, instance_type))


def validate_k8s_version(version: str) -> bool:
    """
    Validate Kubernetes version format

    Args:
        version: Kubernetes version (e.g., '1.28', '1.29.1')

    Returns:
        True if valid, False otherwise
    """
    # Format: major.minor or major.minor.patch
    pattern = r'^1\.\d+(\.\d+)?$'
    return bool(re.match(pattern, version))


def validate_ip_address(ip: str) -> bool:
    """
    Validate IPv4 address format

    Args:
        ip: IP address string

    Returns:
        True if valid IPv4, False otherwise
    """
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False

    # Check each octet is 0-255
    octets = ip.split('.')
    return all(0 <= int(octet) <= 255 for octet in octets)


def validate_cidr_block(cidr: str) -> bool:
    """
    Validate CIDR block format

    Args:
        cidr: CIDR block (e.g., '10.0.0.0/16')

    Returns:
        True if valid, False otherwise
    """
    pattern = r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$'
    if not re.match(pattern, cidr):
        return False

    # Split IP and prefix
    ip, prefix = cidr.split('/')

    # Validate IP
    if not validate_ip_address(ip):
        return False

    # Validate prefix (0-32)
    return 0 <= int(prefix) <= 32


def validate_email_domain(email: str, allowed_domains: Optional[List[str]] = None) -> bool:
    """
    Validate email domain against allowed list

    Args:
        email: Email address
        allowed_domains: List of allowed domains (None = all allowed)

    Returns:
        True if domain is allowed, False otherwise
    """
    if allowed_domains is None:
        return True

    # Extract domain from email
    if '@' not in email:
        return False

    domain = email.split('@')[1].lower()
    return domain in [d.lower() for d in allowed_domains]


def validate_password_strength(password: str) -> tuple[bool, List[str]]:
    """
    Validate password strength

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Length check
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    # Uppercase check
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")

    # Lowercase check
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")

    # Digit check
    if not re.search(r'[0-9]', password):
        errors.append("Password must contain at least one digit")

    # Special character check (optional but recommended)
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password should contain at least one special character")

    return len(errors) == 0, errors


def validate_uuid(uuid_string: str) -> bool:
    """
    Validate UUID format

    Args:
        uuid_string: UUID string

    Returns:
        True if valid UUID, False otherwise
    """
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(pattern, uuid_string.lower()))
