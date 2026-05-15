import pytest
from backend.services.placement_advisor_service import (
    PlacementAdvisorService,
    WorkloadState,
    ClusterState
)

# Mock classes for testing
class MockClassification:
    def __init__(self, tier="Silver", role="WORKER", confidence_state="CONFIRMED", spot_friendly=True):
        self.tier = tier
        self.role = role
        self.confidence_state = confidence_state
        self.spot_friendly = spot_friendly
        self.workload_id = "test-wl-123"

class MockRedis:
    def get(self, *args, **kwargs):
        return None
        
@pytest.fixture
def advisor():
    return PlacementAdvisorService(redis_client=MockRedis())

@pytest.fixture
def default_workload_state():
    return WorkloadState(
        observed_replicas=10,
        hpa_min_replicas=None,
        hpa_max_replicas=None,
        pdb_min_available=None,
        current_spot_pods=0,
        current_ondemand_pods=10,
        stable_for_minutes=60,
        has_pdb=False,
        has_topology_spread=False,
        has_pod_anti_affinity=False,
        replicas=10,
        pod_cpu_usage_per_pod=None,
        pod_request_rate_per_pod=None,
        assigned_nodepool_class="spot-general"
    )

def test_compute_cv(advisor):
    # Normal values
    assert advisor._compute_cv([10.0, 10.0, 10.0]) == 0.0
    cv = advisor._compute_cv([5.0, 10.0, 15.0]) # mean=10, var=25/3 ~ 8.33, std=~2.88, cv ~ 0.288
    assert 0.28 < cv < 0.29
    
    # All zeros
    assert advisor._compute_cv([0.0, 0.0, 0.0, 0.0]) is None
    
    # Single value
    assert advisor._compute_cv([10.0]) is None

def test_compute_ondemand_baseline(advisor, default_workload_state):
    cls = MockClassification()
    
    # replicas=2
    default_workload_state.observed_replicas = 2
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 2
    
    # replicas=3 -> floor 2
    default_workload_state.observed_replicas = 3
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 2
    
    # replicas=4 -> floor 3
    default_workload_state.observed_replicas = 4
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 3
    
    # replicas=10, Silver -> max(floor, 5) = 5
    default_workload_state.observed_replicas = 10
    cls.tier = "Silver"
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 5
    
    # Platinum -> 100% On-Demand
    cls.tier = "Platinum"
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 10
    
    # Gold without strong resilience -> 70%
    cls.tier = "Gold"
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 7
    
    # Gold with strong resilience -> 50%
    default_workload_state.has_pdb = True
    default_workload_state.has_topology_spread = True
    default_workload_state.has_pod_anti_affinity = True
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 5
    
    # Bronze -> floor only
    cls.tier = "Bronze"
    assert advisor.compute_ondemand_baseline(default_workload_state, cls) == 5 # int(10*0.5)

def test_apply_traffic_skew_adjustment(advisor, default_workload_state):
    # replicas < 4 -> no adjustment
    default_workload_state.observed_replicas = 3
    assert advisor.apply_traffic_skew_adjustment(default_workload_state, 2, None, None)[0] == 2
    
    # request_rate CV > 0.35 -> bump +1
    default_workload_state.observed_replicas = 10
    assert advisor.apply_traffic_skew_adjustment(default_workload_state, 5, 0.40, None)[0] == 6
    
    # request rate below threshold -> no bump
    assert advisor.apply_traffic_skew_adjustment(default_workload_state, 5, 0.30, 0.50)[0] == 5
    
    # CPU CV > 0.40 (no request rate) -> bump +1
    assert advisor.apply_traffic_skew_adjustment(default_workload_state, 5, None, 0.45)[0] == 6
    
    # Both None -> no change
    assert advisor.apply_traffic_skew_adjustment(default_workload_state, 5, None, None)[0] == 5
    
    # Baseline already == observed -> no op check
    assert advisor.apply_traffic_skew_adjustment(default_workload_state, 10, 0.50, None)[0] == 10

def test_assign_capacity_types(advisor, default_workload_state):
    # Eligible -> correct burst split
    cls = MockClassification(role="WORKER", confidence_state="CONFIRMED", spot_friendly=True)
    od, spot = advisor.assign_capacity_types(default_workload_state, cls, 5)
    assert od == 5
    assert spot == 5
    
    # SYSTEM role -> all On-Demand
    cls.role = "SYSTEM"
    od, spot = advisor.assign_capacity_types(default_workload_state, cls, 5)
    assert od == 10
    assert spot == 0
    
    # CONTROL_PLANE role -> all On-Demand
    cls.role = "CONTROL_PLANE"
    od, spot = advisor.assign_capacity_types(default_workload_state, cls, 5)
    assert od == 10
    assert spot == 0
    
    # Not CONFIRMED -> all On-Demand
    cls.role = "WORKER"
    cls.confidence_state = "PROVISIONAL"
    od, spot = advisor.assign_capacity_types(default_workload_state, cls, 5)
    assert od == 10
    assert spot == 0
    
    # Not spot friendly -> all On-Demand
    cls.confidence_state = "CONFIRMED"
    cls.spot_friendly = False
    od, spot = advisor.assign_capacity_types(default_workload_state, cls, 5)
    assert od == 10
    assert spot == 0


def _make_cluster_state(**overrides):
    defaults = dict(
        total_running_pods=100,
        current_spot_pods=20,
        in_flight_spot_pods=0,
        unhealthy_pending_pods=0,
        node_ready_count=5,
        node_total_count=5,
        not_ready_nodes=0,
        not_ready_trend="stable",
        subnet_ips_by_az={"us-east-1a": 200, "us-east-1b": 200},
        total_nodes=5,
    )
    defaults.update(overrides)
    from datetime import datetime
    return ClusterState(**defaults, collected_at=datetime.utcnow())


def test_evaluate_cluster_guards(advisor):
    # Small cluster prod -> blocked
    state = _make_cluster_state(total_nodes=2, not_ready_nodes=0)
    result = advisor.evaluate_cluster_guards(state, "prod")
    assert result.blocked is True
    assert "small_cluster_protection" in result.warnings

    # Small cluster dev -> NOT blocked by small_cluster_protection
    result = advisor.evaluate_cluster_guards(state, "dev")
    assert not any(w == "small_cluster_protection" for w in result.warnings)

    # Node readiness instability -> blocked (>10% not ready)
    state = _make_cluster_state(total_nodes=10, not_ready_nodes=3, not_ready_trend="increasing")
    result = advisor.evaluate_cluster_guards(state, "prod")
    assert result.blocked is True
    assert "node_readiness_instability" in result.warnings

    # Subnet IP < 50 -> warning + reduce_spot_by > 0, not necessarily blocked
    state = _make_cluster_state(total_nodes=5, subnet_ips_by_az={"us-east-1a": 10})
    result = advisor.evaluate_cluster_guards(state, "prod")
    assert any("subnet_exhaustion" in w for w in result.warnings)
    assert result.reduce_spot_by > 0

    # Healthy cluster -> not blocked
    state = _make_cluster_state()
    result = advisor.evaluate_cluster_guards(state, "prod")
    assert result.blocked is False


def test_is_rollout_eligible(advisor, default_workload_state):
    cls = MockClassification(tier="Silver", confidence_state="CONFIRMED", spot_friendly=True)
    cluster = _make_cluster_state(unhealthy_pending_pods=0, not_ready_nodes=0)
    default_workload_state.stable_for_minutes = 720
    default_workload_state.pod_cpu_usage_per_pod = 0.3

    # Gate 1: not CONFIRMED -> blocked
    cls.confidence_state = "DRAFT"
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=25.0)
    assert ok is False and "not_confirmed" in reason

    # Gate 2: Platinum -> blocked
    cls.confidence_state = "CONFIRMED"
    cls.tier = "Platinum"
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=25.0)
    assert ok is False and "platinum" in reason

    # Gate 3: Gold without PDB -> blocked
    cls.tier = "Gold"
    default_workload_state.has_pdb = False
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=25.0)
    assert ok is False and "pdb" in reason

    # Gate 4: min replicas < 2 -> blocked
    cls.tier = "Silver"
    default_workload_state.observed_replicas = 1
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=25.0)
    assert ok is False and "min_replicas" in reason
    default_workload_state.observed_replicas = 10

    # Gate 5: unhealthy pending pods -> blocked
    bad_cluster = _make_cluster_state(unhealthy_pending_pods=1)
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, bad_cluster, "prod", savings_pct=25.0)
    assert ok is False and "unhealthy" in reason

    # Gate 6: cluster not stable (not_ready_nodes > 0) -> blocked
    unstable = _make_cluster_state(not_ready_nodes=1)
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, unstable, "prod", savings_pct=25.0)
    assert ok is False and "cluster_not_stable" in reason

    # Gate 7: workload not stable 12h -> blocked
    default_workload_state.stable_for_minutes = 100
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=25.0)
    assert ok is False and "unstable" in reason

    # Savings below 20% -> blocked
    default_workload_state.stable_for_minutes = 720
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=10.0)
    assert ok is False and "savings" in reason

    # All gates pass -> eligible
    ok, reason = advisor.is_rollout_eligible(default_workload_state, cls, cluster, "prod", savings_pct=25.0)
    assert ok is True and reason == ""


def test_apply_cluster_spot_cap(advisor):
    class MockWorkload:
        def __init__(self, spot_score=1.0):
            self.spot_score = spot_score

    cluster = _make_cluster_state(total_running_pods=100, current_spot_pods=10, in_flight_spot_pods=0)

    # Headroom > total requested -> no cap applied, assignments unchanged
    assignments = {"wl-a": (5, 5), "wl-b": (3, 2)}
    workloads_by_id = {"wl-a": MockWorkload(1.0), "wl-b": MockWorkload(0.5)}
    result = advisor.apply_cluster_spot_cap(assignments, cluster, "c1", 0.50, workloads_by_id)
    assert result["wl-a"][1] == 5
    assert result["wl-b"][1] == 2

    # Headroom == 0 -> all spot zeroed
    full_cluster = _make_cluster_state(total_running_pods=100, current_spot_pods=50, in_flight_spot_pods=0)
    result = advisor.apply_cluster_spot_cap(assignments, full_cluster, "c1", 0.50, workloads_by_id)
    assert result["wl-a"][1] == 0
    assert result["wl-b"][1] == 0

    # in_flight_spot_pods counts against headroom
    inflight_cluster = _make_cluster_state(total_running_pods=100, current_spot_pods=40, in_flight_spot_pods=10)
    result = advisor.apply_cluster_spot_cap(assignments, inflight_cluster, "c1", 0.50, workloads_by_id)
    total_granted = sum(v[1] for v in result.values())
    assert total_granted == 0  # 40 + 10 = 50 = cap, no headroom


def test_select_instance_families(advisor):
    class MockInstance:
        def __init__(self, name, arch, price, interruption_rate=0.1):
            self.name = name
            self.family = name.split(".")[0]
            self.arch = arch
            self.price = price
            self.interruption_rate = interruption_rate

    instances = [
        MockInstance("m5.large", "amd64", 0.10, 0.05),
        MockInstance("m5.xlarge", "amd64", 0.20, 0.05),
        MockInstance("c5.large", "amd64", 0.08, 0.10),
        MockInstance("t3.medium", "amd64", 0.04, 0.30),
        MockInstance("m6g.large", "arm64", 0.09, 0.05),  # wrong arch
    ]

    # Hard skip when effective_rate < 0.3 — all zeroed out
    all_bad_rate = lambda name: 0.2
    result = advisor.select_instance_families("amd64", instances, all_bad_rate)
    assert result == []

    # Good rates -> returns scored instances for correct arch only
    good_rate = lambda name: 0.9
    result = advisor.select_instance_families("amd64", instances, good_rate)
    names = [inst.name for inst in result]
    assert "m6g.large" not in names  # wrong arch excluded
    assert len(result) <= 5

    # Returns at most 5 instances
    many = [MockInstance(f"m5.{i}xlarge", "amd64", 0.1 + i * 0.01) for i in range(10)]
    result = advisor.select_instance_families("amd64", many, good_rate)
    assert len(result) <= 5
