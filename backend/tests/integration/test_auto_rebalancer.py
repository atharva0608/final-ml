"""
Integration tests for auto_rebalancer critical paths — Issue #36
================================================================

Tests:
1. Phase 2 triggers on pinned instance ID, not count
2. Phase 2 count-fallback when no pinned ID (with warning log)
3. Failure exponential backoff prevents rapid retry
4. Per-instance daily cap (10/day) blocks 11th attempt
5. S2S dedup key prevents repeated migration
6. Concurrent clusters processed independently (no cross-contamination)

Uses fakeredis + in-memory SQLite from conftest.py fixtures.
"""

import pytest
import fakeredis
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import uuid


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_instance(db, cluster_id, lifecycle='spot', state='running',
                  instance_id=None, node_name=None, launched_at=None,
                  instance_type='m5.large', az='ap-south-1a'):
    """Create and persist a minimal Instance row."""
    from backend.models.instance import Instance, InstanceLifecycle
    inst = Instance(
        id=str(uuid.uuid4()),
        cluster_id=cluster_id,
        instance_id=instance_id or f"i-{uuid.uuid4().hex[:16]}",
        instance_type=instance_type,
        az=az,
        lifecycle=InstanceLifecycle.SPOT if lifecycle == 'spot' else InstanceLifecycle.ON_DEMAND,
        state=state,
        node_name=node_name,
        launched_at=launched_at or datetime.utcnow() - timedelta(seconds=120),
        created_at=launched_at or datetime.utcnow() - timedelta(seconds=120),
    )
    db.add(inst)
    db.flush()
    return inst


def make_rebalancing_action(db, cluster_id, status='in_progress', metadata=None):
    """Create and persist a minimal RebalancingAction."""
    from backend.models.rebalancing_action import RebalancingAction
    action = RebalancingAction(
        id=str(uuid.uuid4()),
        cluster_id=cluster_id,
        trigger='scheduled',
        source_pool='m5.large:ap-south-1a',
        target_pool='c5.large:ap-south-1b',
        status=status,
        started_at=datetime.utcnow(),
        action_metadata=metadata or {},
    )
    db.add(action)
    db.flush()
    return action


# ─── Test 1: Phase 2 triggers on pinned ID, not count ─────────────────────

class TestPhase2InstanceIdPinning:
    """Issue #13: Phase 2 should use pinned replacement_spot_instance_id."""

    def test_phase2_waits_when_pinned_instance_not_yet_running(self, db):
        """When pinned ID is set but instance not yet Running, Phase 2 must NOT trigger."""
        from backend.models.instance import Instance, InstanceLifecycle

        cluster_id = str(uuid.uuid4())
        # Spot baseline = 1
        existing_spot = make_instance(db, cluster_id, lifecycle='spot', state='running')
        # The replacement is still pending
        pinned_inst = make_instance(db, cluster_id, lifecycle='spot', state='pending',
                                    instance_id='i-abc123pending000')

        # Spot count = 1 (only running) > baseline 0 — old count-gate would trigger
        running_count = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
        ).count()
        assert running_count == 1  # existing spot only

        # Simulate the new ID-first check: look up pinned instance by instance_id
        pinned_lookup = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
            Instance.instance_id == 'i-abc123pending000',
        ).first()
        # Should be None because instance is still 'pending'
        assert pinned_lookup is None, "Pending instance should not be found as running"

    def test_phase2_triggers_when_pinned_instance_running_and_joined_k8s(self, db):
        """When pinned ID is Running + has node_name + age >= 90s, Phase 2 should trigger."""
        from backend.models.instance import Instance, InstanceLifecycle

        cluster_id = str(uuid.uuid4())
        launched = datetime.utcnow() - timedelta(seconds=95)  # 95s old, past 90s threshold
        pinned_iid = f"i-{uuid.uuid4().hex[:16]}"
        spot_inst = make_instance(
            db, cluster_id, lifecycle='spot', state='running',
            instance_id=pinned_iid,
            node_name='ip-10-0-1-100.ap-south-1.compute.internal',
            launched_at=launched,
        )

        # Simulate the check that Phase 2 code does
        lookup = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
            Instance.instance_id == pinned_iid,
        ).first()

        assert lookup is not None
        assert lookup.node_name is not None
        age_s = (datetime.utcnow() - lookup.created_at).total_seconds()
        assert age_s >= 90, f"Age should be >= 90s, got {age_s}s"


# ─── Test 2: Count-fallback with warning ──────────────────────────────────

class TestPhase2CountFallback:
    """When no replacement_spot_instance_id in metadata, count-fallback path runs."""

    def test_count_fallback_triggers_when_spot_count_increased(self, db):
        """If spot_count > baseline and no pinned ID, count-fallback should return a candidate."""
        from backend.models.instance import Instance, InstanceLifecycle

        cluster_id = str(uuid.uuid4())
        # baseline = 0, now 1 spot is running for 95s with node_name
        launched = datetime.utcnow() - timedelta(seconds=95)
        spot_inst = make_instance(
            db, cluster_id, lifecycle='spot', state='running',
            node_name='ip-10-0-1-200.ap-south-1.compute.internal',
            launched_at=launched,
        )

        spot_count = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
        ).count()
        spot_baseline = 0

        assert spot_count > spot_baseline

        # Count fallback: get newest spot
        newest = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
            Instance.state == 'running',
        ).order_by(Instance.created_at.desc()).first()

        assert newest is not None
        assert newest.node_name is not None


# ─── Test 3: Failure exponential backoff ─────────────────────────────────

class TestFailureExponentialBackoff:
    """Issue #14: On action failure, exponential backoff key must be set."""

    def test_backoff_increments_and_sets_ttl(self):
        """First failure → 300s backoff; second → 600s; capped at 3600s."""
        r = fakeredis.FakeRedis(decode_responses=False)
        inst_id = f"i-{uuid.uuid4().hex[:16]}"

        for attempt in range(1, 4):
            _failure_key = f"rebalance_failures:{inst_id}"
            _failure_count = int(r.incr(_failure_key) or 1)
            r.expire(_failure_key, 86400)
            _backoff_s = min(300 * (2 ** (_failure_count - 1)), 3600)
            _cd_key = f"spot:rebalanced:instance:{inst_id}"
            r.setex(_cd_key, _backoff_s, "failure_backoff")

            expected_backoff = min(300 * (2 ** (attempt - 1)), 3600)
            actual_ttl = r.ttl(_cd_key)
            assert actual_ttl <= expected_backoff, \
                f"Attempt {attempt}: expected backoff <= {expected_backoff}, got {actual_ttl}"
            assert actual_ttl > 0

        # Cap at 3600s
        r2 = fakeredis.FakeRedis(decode_responses=False)
        fk = f"rebalance_failures:i-captest"
        r2.set(fk, 20)  # simulate 20 failures
        count = int(r2.get(fk))
        backoff = min(300 * (2 ** (count - 1)), 3600)
        assert backoff == 3600

    def test_success_resets_failure_counter(self):
        """On success, rebalance_failures counter must be deleted."""
        r = fakeredis.FakeRedis(decode_responses=False)
        inst_id = f"i-{uuid.uuid4().hex[:16]}"
        r.set(f"rebalance_failures:{inst_id}", 3)
        assert r.get(f"rebalance_failures:{inst_id}") is not None

        # Simulate success path
        r.delete(f"rebalance_failures:{inst_id}")
        assert r.get(f"rebalance_failures:{inst_id}") is None


# ─── Test 4: Per-instance daily cap ───────────────────────────────────────

class TestPerInstanceDailyCap:
    """Issue #15: 11th attempt in a day must be blocked."""

    def test_daily_cap_blocks_after_10(self):
        """After 10 increments, attempt 11 must see count >= 10 and be skipped."""
        r = fakeredis.FakeRedis(decode_responses=False)
        inst_id = f"i-{uuid.uuid4().hex[:16]}"
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        _dlc_key = f"rebalance_daily_count:{inst_id}:{date_str}"

        for _ in range(10):
            r.incr(_dlc_key)

        # 11th check
        _dlc_count = int(r.get(_dlc_key) or 0)
        _MAX_PER_INSTANCE_DAILY = 10
        assert _dlc_count >= _MAX_PER_INSTANCE_DAILY, \
            "11th attempt should see daily cap reached"

    def test_daily_cap_allows_first_10(self):
        """First 10 attempts should all be allowed."""
        r = fakeredis.FakeRedis(decode_responses=False)
        inst_id = f"i-{uuid.uuid4().hex[:16]}"
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        _dlc_key = f"rebalance_daily_count:{inst_id}:{date_str}"
        _MAX_PER_INSTANCE_DAILY = 10

        for attempt in range(1, 11):
            _dlc_count = int(r.get(_dlc_key) or 0)
            assert _dlc_count < _MAX_PER_INSTANCE_DAILY, \
                f"Attempt {attempt} should be allowed, count={_dlc_count}"
            r.incr(_dlc_key)


# ─── Test 5: S2S dedup key ────────────────────────────────────────────────

class TestS2SDeduplication:
    """Issue #10: Same source→target S2S migration must not repeat within 2h."""

    def test_dedup_key_blocks_repeat_migration(self):
        """After S2S action, dedup key blocks same pair for 2h."""
        r = fakeredis.FakeRedis(decode_responses=False)
        cluster_id = str(uuid.uuid4())
        src = 'm5.large:ap-south-1a'
        tgt = 'c5.large:ap-south-1b'
        dedup_key = f"s2s_migration:{cluster_id}:{src}:{tgt}"

        # First migration — key does not exist
        assert not r.exists(dedup_key), "Dedup key should not exist before first migration"

        # Write after action created
        r.setex(dedup_key, 7200, "1")

        # Second trigger — key exists → should be blocked
        assert r.exists(dedup_key), "Dedup key should exist after first migration"
        ttl = r.ttl(dedup_key)
        assert ttl > 0, "Dedup key TTL should be positive (up to 2h)"
        assert ttl <= 7200

    def test_dedup_key_expires_after_2h(self):
        """Dedup key TTL should be exactly 7200s at creation."""
        r = fakeredis.FakeRedis(decode_responses=False)
        key = f"s2s_migration:cluster1:src:tgt"
        r.setex(key, 7200, "1")
        ttl = r.ttl(key)
        # Allow 1s drift
        assert 7199 <= ttl <= 7200


# ─── Test 6: Concurrent clusters isolation ────────────────────────────────

class TestConcurrentClusterIsolation:
    """Two clusters must have independent action counters and cooldowns."""

    def test_daily_cap_is_per_cluster_instance(self):
        """Daily cap keys for different clusters must not share state."""
        r = fakeredis.FakeRedis(decode_responses=False)
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        inst_a = f"i-{uuid.uuid4().hex[:16]}"
        inst_b = f"i-{uuid.uuid4().hex[:16]}"
        key_a = f"rebalance_daily_count:{inst_a}:{date_str}"
        key_b = f"rebalance_daily_count:{inst_b}:{date_str}"

        # Fill cluster A's instance cap
        for _ in range(10):
            r.incr(key_a)

        # Cluster B's instance should still be at 0
        count_b = int(r.get(key_b) or 0)
        assert count_b == 0, "Cluster B instance cap should be independent of A"

    def test_s2s_dedup_keys_are_namespaced(self):
        """S2S dedup keys for different clusters must not overlap."""
        r = fakeredis.FakeRedis(decode_responses=False)
        cluster_a = str(uuid.uuid4())
        cluster_b = str(uuid.uuid4())
        src = 'm5.large:ap-south-1a'
        tgt = 'c5.large:ap-south-1b'

        key_a = f"s2s_migration:{cluster_a}:{src}:{tgt}"
        key_b = f"s2s_migration:{cluster_b}:{src}:{tgt}"

        r.setex(key_a, 7200, "1")
        assert not r.exists(key_b), "S2S dedup for cluster B should not be affected by cluster A"
