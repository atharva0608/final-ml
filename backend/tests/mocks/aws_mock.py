"""
Reusable AWS mock helpers for unit tests.

Usage:
    from backend.tests.mocks.aws_mock import build_ec2_client, build_sts_client, build_asg_client
"""
from unittest.mock import MagicMock
from datetime import datetime, timezone


def build_ec2_client(
    spot_price: float = 0.032,
    instance_id: str = "i-mock123",
    fleet_id: str = "fleet-mock-001",
) -> MagicMock:
    """Return a pre-configured mock boto3 EC2 client."""
    client = MagicMock()

    client.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": instance_id,
                        "State": {"Name": "running"},
                        "InstanceType": "m5.large",
                        "Placement": {"AvailabilityZone": "ap-south-1a"},
                        "InstanceLifecycle": "spot",
                    }
                ]
            }
        ]
    }

    client.describe_spot_price_history.return_value = {
        "SpotPriceHistory": [
            {
                "InstanceType": "m5.large",
                "AvailabilityZone": "ap-south-1a",
                "SpotPrice": str(spot_price),
                "Timestamp": datetime.now(timezone.utc),
            }
        ],
        "NextToken": "",
    }

    client.run_instances.return_value = {
        "Instances": [{"InstanceId": instance_id}]
    }

    client.terminate_instances.return_value = {
        "TerminatingInstances": [{"InstanceId": instance_id, "CurrentState": {"Name": "shutting-down"}}]
    }

    client.create_fleet.return_value = {
        "FleetId": fleet_id,
        "Instances": [{"InstanceIds": [instance_id]}],
        "Errors": [],
    }

    client.describe_launch_templates.return_value = {
        "LaunchTemplates": [{"LaunchTemplateId": "lt-mock001", "LaunchTemplateName": "spot-optimizer-lt"}]
    }

    return client


def build_sts_client(
    access_key: str = "AKIA_MOCK_KEY",
    secret_key: str = "mock_secret",
    session_token: str = "mock_session_token",
) -> MagicMock:
    """Return a pre-configured mock boto3 STS client."""
    client = MagicMock()
    client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": access_key,
            "SecretAccessKey": secret_key,
            "SessionToken": session_token,
            "Expiration": datetime(2099, 1, 1, tzinfo=timezone.utc),
        },
        "AssumedRoleUser": {
            "AssumedRoleId": "AROA_MOCK:session",
            "Arn": "arn:aws:sts::123456789012:assumed-role/mock-role/session",
        },
    }
    client.get_caller_identity.return_value = {
        "Account": "123456789012",
        "Arn": "arn:aws:iam::123456789012:role/mock-role",
        "UserId": "AROA_MOCK",
    }
    return client


def build_asg_client(
    asg_name: str = "mock-asg",
    min_size: int = 1,
    max_size: int = 5,
    desired: int = 3,
) -> MagicMock:
    """Return a pre-configured mock boto3 AutoScaling client."""
    client = MagicMock()
    client.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [
            {
                "AutoScalingGroupName": asg_name,
                "MinSize": min_size,
                "MaxSize": max_size,
                "DesiredCapacity": desired,
                "SuspendedProcesses": [],
                "Instances": [],
                "Tags": [],
            }
        ]
    }
    client.update_auto_scaling_group.return_value = {}
    client.suspend_processes.return_value = {}
    client.resume_processes.return_value = {}
    client.set_desired_capacity.return_value = {}
    return client
