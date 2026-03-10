"""
Test fixtures for Spot Optimizer backend.

Provides:
- fakeredis client (drop-in Redis replacement with no external connection)
- sample_cluster fixture (in-memory SQLAlchemy cluster row)
- sample_pools fixture (list of ranked pool dicts)
- Mocked AWS boto3 clients (EC2, STS, ASG) via moto
"""
import pytest
import fakeredis
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── DB fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite engine for unit tests (no Postgres required)."""
    from backend.models.base import Base
    _engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(_engine)
    return _engine


@pytest.fixture()
def db(engine):
    """Scoped SQLAlchemy session, rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ── Redis fixture ─────────────────────────────────────────────────────────────

@pytest.fixture()
def redis_client():
    """Fakeredis client — no external Redis required."""
    client = fakeredis.FakeRedis(decode_responses=False)
    yield client
    client.flushall()


# ── Sample cluster ────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_cluster(db):
    """Persist a minimal Cluster row and return it."""
    from backend.models.cluster import Cluster
    import uuid
    cluster = Cluster(
        id=str(uuid.uuid4()),
        name="test-cluster-1",
        region="ap-south-1",
        account_id="123456789012",
        status="ACTIVE",
        node_count=3,
        spot_count=2,
        agent_installed="Y",
        auto_rebalance_enabled=True,
        auto_rightsizing_enabled=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


# ── Sample pools ──────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_pools():
    """Return a list of pool dicts matching PoolRankingResponse shape."""
    return [
        {
            "instance_type": "m5.large",
            "az": "ap-south-1a",
            "architecture": "x86_64",
            "vcpu": 2,
            "memory_gb": 8.0,
            "spot_price": 0.0320,
            "ondemand_price": 0.0960,
            "predicted_savings": 0.67,
            "risk_probability": 0.04,
            "expected_value": 0.64,
            "savings_pct": 0.67,
            "cost_estimate": 0.77,
            "ml_score": 0.81,
            "rank": 1,
            "is_flagged": False,
            "spot_advisor_rank": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "blacklisted": False,
            "price_shock": False,
        },
        {
            "instance_type": "t3.large",
            "az": "ap-south-1b",
            "architecture": "x86_64",
            "vcpu": 2,
            "memory_gb": 8.0,
            "spot_price": 0.0290,
            "ondemand_price": 0.0832,
            "predicted_savings": 0.65,
            "risk_probability": 0.08,
            "expected_value": 0.60,
            "savings_pct": 0.65,
            "cost_estimate": 0.70,
            "ml_score": 0.74,
            "rank": 2,
            "is_flagged": False,
            "spot_advisor_rank": 1,
            "timestamp": datetime.utcnow().isoformat(),
            "blacklisted": False,
            "price_shock": False,
        },
    ]


# ── Mock AWS clients ──────────────────────────────────────────────────────────

@pytest.fixture()
def mock_ec2_client():
    """Mocked boto3 EC2 client."""
    client = MagicMock()
    client.describe_instances.return_value = {"Reservations": []}
    client.describe_spot_price_history.return_value = {"SpotPriceHistory": [], "NextToken": ""}
    client.run_instances.return_value = {"Instances": [{"InstanceId": "i-mock123"}]}
    client.terminate_instances.return_value = {"TerminatingInstances": []}
    client.create_fleet.return_value = {
        "FleetId": "fleet-mock-001",
        "Instances": [{"InstanceIds": ["i-mock456"]}],
        "Errors": [],
    }
    return client


@pytest.fixture()
def mock_sts_client():
    """Mocked boto3 STS client."""
    client = MagicMock()
    client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AKIA_MOCK_KEY",
            "SecretAccessKey": "mock_secret",
            "SessionToken": "mock_token",
            "Expiration": datetime(2099, 1, 1, tzinfo=timezone.utc),
        }
    }
    return client


@pytest.fixture()
def mock_asg_client():
    """Mocked boto3 Auto Scaling client."""
    client = MagicMock()
    client.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [
            {
                "AutoScalingGroupName": "mock-asg",
                "MinSize": 1,
                "MaxSize": 5,
                "DesiredCapacity": 3,
                "SuspendedProcesses": [],
            }
        ]
    }
    client.update_auto_scaling_group.return_value = {}
    client.suspend_processes.return_value = {}
    client.resume_processes.return_value = {}
    return client
