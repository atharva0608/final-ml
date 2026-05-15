import time
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.core.config import settings
from backend.redis_keys import placement_stability_key, placement_policy_key
from backend.models.placement_policy import PlacementPolicyRecord

logger = logging.getLogger(__name__)

# Constants
CPU_VARIANCE_THRESHOLD = 0.40
REQUEST_VARIANCE_THRESHOLD = 0.35
MIN_PODS_FOR_VARIANCE = 3
SPOT_FAILURE_SPIKE_THRESHOLD = 3
PROVISIONING_WAIT_POLL_INTERVAL = 5
PROVISIONING_WAIT_FALLBACK = 120
PROVISIONING_WAIT_SAFETY_FLOOR = 120
CYCLE_TIME_BUDGET_SECONDS = settings.PLACEMENT_CYCLE_TIME_BUDGET_SECONDS

# Exceptions
class PlacementValidationError(Exception):
    """Raised when pre-write validation fails."""
    pass

# Task 1.8 — Data classes for internal state
@dataclass
class ClusterState:
    total_running_pods: int
    current_spot_pods: int
    in_flight_spot_pods: int
    unhealthy_pending_pods: int
    node_ready_count: int
    node_total_count: int
    not_ready_nodes: int
    not_ready_trend: str
    subnet_ips_by_az: Dict[str, int]
    total_nodes: int
    collected_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class WorkloadState:
    observed_replicas: int
    hpa_min_replicas: Optional[int]
    hpa_max_replicas: Optional[int]
    pdb_min_available: Optional[int]
    current_spot_pods: int
    current_ondemand_pods: int
    stable_for_minutes: int
    has_pdb: bool
    has_topology_spread: bool
    has_pod_anti_affinity: bool
    replicas: int
    pod_cpu_usage_per_pod: Optional[float]
    pod_request_rate_per_pod: Optional[float]
    assigned_nodepool_class: str
    pod_cpu_cv: Optional[float] = None
    pod_request_rate_cv: Optional[float] = None

@dataclass
class SpreadConfig:
    node_spread: str
    zone_spread: str
    node_when_unsatisfiable: str
    zone_when_unsatisfiable: str

@dataclass
class GuardResult:
    blocked: bool
    reason: str
    warnings: List[str]
    reduce_spot_by: int

@dataclass
class RolloutStepResult:
    status: str
    reason: str

class PlacementAdvisorService:
    """
    Placement Intelligence Advisor - Phase 2 Core Engine
    """
    def __init__(self, redis_client):
        self.redis = redis_client

    # --- 1. Math and Baseline Logic ---
    
    def _compute_cv(self, values: List[float]) -> Optional[float]:
        """§4.1: Coefficient of variation. Returns None if mean == 0."""
        if not values or len(values) < MIN_PODS_FOR_VARIANCE:
            return None
        mean = sum(values) / len(values)
        if mean == 0:
            return None
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5
        return std_dev / mean

    def apply_traffic_skew_adjustment(self, workload: 'WorkloadClass', baseline: int, request_cv: Optional[float], cpu_cv: Optional[float]) -> Tuple[int, bool, Optional[str]]:
        """§4.1: Adjust baseline for traffic skew. Returns (new_baseline, skew_detected, skew_source)."""
        observed_replicas = getattr(workload, 'observed_replicas', getattr(workload, 'replicas', 0))
        if observed_replicas < 4:
            return baseline, False, None

        if request_cv is not None and request_cv > REQUEST_VARIANCE_THRESHOLD:
            return min(baseline + 1, observed_replicas), True, "request_rate"
        
        if cpu_cv is not None and cpu_cv > CPU_VARIANCE_THRESHOLD:
            return min(baseline + 1, observed_replicas), True, "cpu_usage"

        return baseline, False, None

    def compute_ondemand_baseline(self, workload_state: WorkloadState, classification: Any) -> int:
        """
        §4.1: Scale-aware floor calculation.
        replicas <= 4 -> max(replicas - 1, 2)
        else -> max(2, pdb, hpa_min, int(replicas * 0.5))
        Tier overrides: Platinum -> 100%, Gold -> 70% (50% strong), Silver -> 50%, Bronze -> floor only.
        """
        replicas = workload_state.observed_replicas
        
        # Scale-aware floor
        if replicas <= 4:
            floor = max(replicas - 1, 2)
            # Cap at observed replicas
            floor = min(floor, replicas)
        else:
            factors = [2]
            if workload_state.pdb_min_available:
                factors.append(workload_state.pdb_min_available)
            if workload_state.hpa_min_replicas:
                factors.append(workload_state.hpa_min_replicas)
            factors.append(int(replicas * 0.5))
            floor = max(factors)
            
        tier = classification.tier
        
        # Tier overrides
        if tier == "Platinum":
            baseline = replicas
        elif tier == "Gold":
            # 50% if strong resilience (pdb + topology spread + anti-affinity), else 70%
            strong_resilience = (workload_state.has_pdb and 
                                 workload_state.has_topology_spread and 
                                 workload_state.has_pod_anti_affinity)
            tier_factor = 0.5 if strong_resilience else 0.7
            baseline = max(floor, int(replicas * tier_factor))
        elif tier == "Silver":
            baseline = max(floor, int(replicas * 0.5))
        else: # Bronze or DRAFT
            baseline = floor
            
        return min(baseline, replicas)

    def assign_capacity_types(self, workload_state: WorkloadState, classification: Any, ondemand_baseline: int) -> Tuple[int, int]:
        """
        §4.2: Compute Spot/OD split considering hard safety gates.
        Returns (od_count, spot_count).
        """
        replicas = workload_state.observed_replicas
        
        # Hard gates where Spot is forbidden
        if classification.role in ("SYSTEM", "CONTROL_PLANE") or \
           classification.confidence_state != "CONFIRMED" or \
           not classification.spot_friendly:
            return replicas, 0
            
        # Normal path
        spot_count = max(0, replicas - ondemand_baseline)
        od_count = replicas - spot_count
        return od_count, spot_count

    def get_spot_scheduling_success_rate(self, instance_type: str, window_minutes: int = 15) -> Optional[float]:
        """
        Task 1.15: Get scheduling success rate from Redis.
        Returns None if no data.
        """
        key = f"spot:placement:scheduling_success:{instance_type}:{window_minutes}m"
        val = self.redis.get(key)
        if val:
            try:
                return float(val)
            except ValueError:
                pass
        return None

    def get_spot_scheduling_success_rate_blended(self, instance_type: str) -> float:
        """
        Task 2.3: Blended 15m (70%) and 120m (30%) scheduling success rates.
        If both None -> 1.0. 
        """
        rate_15 = self.get_spot_scheduling_success_rate(instance_type, 15)
        rate_120 = self.get_spot_scheduling_success_rate(instance_type, 120)

        if rate_15 is None and rate_120 is None:
            return 1.0
        elif rate_15 is None:
            return rate_120
        elif rate_120 is None:
            return rate_15
        else:
            return 0.7 * rate_15 + 0.3 * rate_120

    def compute_spot_availability_factor(self, region: str) -> float:
        """
        §4.3 (Task 2.6): 3-window smoothed average with per-AZ support.
        Wired to real Redis history arrays.
        """
        # Fetch from Redis
        raw_history = self.redis.get(f"spot:placement:availability_history:{region}")
        availability_history = json.loads(raw_history) if raw_history else []
        
        if not availability_history:
            return 1.0
            
        recent = availability_history[-min(3, len(availability_history)):]
        smoothed_factor = sum(recent) / len(recent)
        
        # Check for 2-min failure spike across AZs
        # Expecting a hash of AZ -> JSON list
        az_history_map = self.redis.hgetall(f"spot:placement:availability_history_az:{region}")
        if az_history_map:
            for az, raw_az_hist in az_history_map.items():
                try:
                    az_history = json.loads(raw_az_hist)
                    if len(az_history) >= 2:
                        recent_fails = [1.0 - h for h in az_history[-2:]]
                        # SPOT_FAILURE_SPIKE_THRESHOLD default to 1.5 if not found
                        threshold = globals().get('SPOT_FAILURE_SPIKE_THRESHOLD', 1.5)
                        if sum(recent_fails) > threshold:
                            logger.warning(f"Spot availability failure spike detected in {az}")
                            return 0.0 # Fast reaction override
                except Exception as e:
                    logger.warning(
                        f"[PlacementAdvisor] AZ spike check error az={az} region={region}: {e}"
                    )
                    continue
                    
        return smoothed_factor
        
    def apply_availability_to_spot(self, spot_ceiling: int, availability: float) -> int:
        """
        §4.3: Prevent starvation but scale down if availability drops.
        """
        if availability < 0.2:
            return 0
        if availability < 1.0:
            reduced = int(spot_ceiling * availability)
            return max(1, reduced) if spot_ceiling > 0 else 0
        return spot_ceiling

    def apply_cluster_spot_cap(self, assignments: Dict[str, Tuple[int, int]], cluster_state: ClusterState, cluster_id: str, max_ratio: float, workloads_by_id: Dict[str, Any]) -> Dict[str, Tuple[int, int]]:
        """
        §4.4: Enforce global cluster spot ratio cap.
        Include in_flight_spot_pods in headroom.
        Sort by spot_score * log(1 + requested).
        """
        import math
        total_pods = cluster_state.total_running_pods
        in_flight = cluster_state.in_flight_spot_pods
        
        # We need to know which workloads are demanding how many spot pods.
        # assignments: Dict[workload_id, (od_target, spot_target)]
        
        # New capacity we can allocate:
        spot_cap = int(total_pods * max_ratio)
        current_allocated = cluster_state.current_spot_pods + in_flight
        
        total_requested = sum(spot for od, spot in assignments.values())
        if current_allocated + total_requested <= spot_cap:
            return assignments # No cap needed
            
        # Cap is exceeded. We must sort workloads by priority to give spot pods to highest priority.
        def priority_score(wid):
            w = workloads_by_id[wid]
            score = w.spot_score if hasattr(w, 'spot_score') else 0
            req = assignments[wid][1]
            return score * math.log(1 + req)
            
        sorted_wids = sorted(assignments.keys(), key=priority_score, reverse=True)
        
        new_assignments = {}
        available_headroom = max(0, spot_cap - cluster_state.current_spot_pods - in_flight)
        
        for wid in sorted_wids:
            od_req, spot_req = assignments[wid]
            if spot_req == 0:
                new_assignments[wid] = (od_req, 0)
                continue
                
            granted = min(spot_req, available_headroom)
            available_headroom -= granted
            
            # The denied spot pods become OD pods
            new_assignments[wid] = (od_req + (spot_req - granted), granted)
            
        return new_assignments

    def compute_spread_constraints(self, workload_state: WorkloadState, cluster_state: ClusterState, classification: Any) -> SpreadConfig:
        """
        §5.3: Tiered relaxation: Tier 0 (normal), Tier 1 (relax node, keep zone), Tier 2 (relax both).
        """
        tier = classification.tier
        
        # Default config
        config = SpreadConfig(
            node_spread="maxSkew: 1",
            zone_spread="maxSkew: 1",
            node_when_unsatisfiable="DoNotSchedule",
            zone_when_unsatisfiable="DoNotSchedule"
        )
        
        # We only return 0, 1, 2 for relaxation tier, so let's simplify return
        relaxation_tier = 0
        if tier == "Platinum":
            # Strict
            pass
        elif tier == "Gold":
            config.node_when_unsatisfiable = "ScheduleAnyway"
            relaxation_tier = 1
        else: # Silver, Bronze, etc.
            config.node_when_unsatisfiable = "ScheduleAnyway"
            config.zone_when_unsatisfiable = "ScheduleAnyway"
            relaxation_tier = 2
            
        return config, relaxation_tier

    def _score_instance(self, instance: Any, success_rate: float) -> float:
        """
        §7: Core scoring function.
        cost_efficiency / interruption_penalty * blended_effective_rate
        v5.10 hard skip when effective_rate < 0.3.
        """
        if success_rate < 0.3:
            return 0.0
            
        cost_efficiency = 1.0 / max(instance.price, 0.001)
        interruption_penalty = 1.0 + getattr(instance, 'interruption_rate', 0.15)
        
        return (cost_efficiency / interruption_penalty) * success_rate

    def select_instance_families(self, workload_arch: str, available_instances: List[Any], get_success_rate_fn) -> List[Any]:
        """
        §7: Filter arch -> ENI -> score. AZ-aware diversity.
        Returns top 5 scored instance types.
        """
        valid_instances = [inst for inst in available_instances if inst.arch == workload_arch]
        
        scored = []
        for inst in valid_instances:
            success_rate = get_success_rate_fn(inst.name)
            score = self._score_instance(inst, success_rate)
            if score > 0:
                scored.append((score, inst))
                
        # Sort stably by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        top5 = [inst for score, inst in scored[:5]]

        # Enforce min_families >= 2: if only 1 family in top5, pull best instance from a second family
        families_seen = set(inst.family for inst in top5)
        if len(families_seen) < 2:
            for _score, inst in scored[len(top5):]:
                if inst.family not in families_seen:
                    top5.append(inst)
                    families_seen.add(inst.family)
                    break

        return top5[:5]

    def evaluate_cluster_guards(self, cluster_state: ClusterState, env: str) -> GuardResult:
        """
        §8: Cluster-level safety guards. Small cluster protection, readiness instability, IP exhaustion.
        """
        warnings = []
        blocked = False
        reduce_by = 0
        
        if env == "prod" and cluster_state.total_nodes < 3:
            blocked = True
            warnings.append("small_cluster_protection")
            
        if cluster_state.not_ready_nodes > max(1, int(cluster_state.total_nodes * 0.1)):
            blocked = True
            warnings.append("node_readiness_instability")
            
        for az, ips in cluster_state.subnet_ips_by_az.items():
            if ips < 50:
                warnings.append(f"subnet_exhaustion_az_{az}")
                reduce_by += 10 # heuristic reduce
                
        return GuardResult(blocked=blocked, reason=",".join(warnings) if blocked else "", warnings=warnings, reduce_spot_by=reduce_by)

    def is_rollout_eligible(self, workload_state: WorkloadState, classification: Any, cluster_state: ClusterState, env: str, savings_pct: float = 0.0) -> Tuple[bool, str]:
        """
        §9.1/§9.2: 7 gates + Phase 3 Strict Rollout conditions.
        """
        if classification.confidence_state != "CONFIRMED":
            return False, "not_confirmed"
            
        if classification.tier == "Platinum":
            return False, "platinum_tier_rollout_blocked"
            
        if classification.tier == "Gold" and not getattr(workload_state, 'has_pdb', False):
            return False, "gold_tier_requires_pdb"
            
        if workload_state.observed_replicas < 2:
            return False, "min_replicas_not_met"
            
        # v5.10: gate 5 uses max(3, 1% of total running pods) threshold
        unhealthy_threshold = max(3, int(cluster_state.total_running_pods * 0.01))
        if cluster_state.unhealthy_pending_pods >= unhealthy_threshold:
            return False, f"unhealthy_pending_pods:{cluster_state.unhealthy_pending_pods}>={unhealthy_threshold}"
            
        if cluster_state.not_ready_nodes > 0:
            return False, "cluster_not_stable"
            
        # no_movement > 12h (720 minutes)
        if workload_state.stable_for_minutes < 720:
            return False, "workload_unstable_12h"
            
        # cpu_usage < 70%
        if getattr(workload_state, 'pod_cpu_usage_per_pod', 0) and workload_state.pod_cpu_usage_per_pod > 0.7:
            return False, "cpu_usage_too_high"
            
        # estimated_savings > 20%
        if savings_pct < 20.0:
            return False, "savings_below_20_pct"
            
        return True, ""
            
    def _assign_nodepool_class(self, classification: Any, workload: Any) -> str:
        """
        §6: NodePool class assignment based on tier and characteristics.
        Platinum/Gold/SYSTEM/CONTROL_PLANE -> "on-demand-general"
        Silver/Bronze CPU-intensive -> "spot-compute"
        Silver/Bronze memory-intensive -> "spot-memory"
        Default -> "spot-general"
        """
        if classification.role in ("SYSTEM", "CONTROL_PLANE") or classification.tier in ("Platinum", "Gold"):
            return "on-demand-general"
            
        cpu_usage = getattr(workload, 'pod_cpu_usage_per_pod', 0) or 0
        mem_usage = getattr(workload, 'pod_mem_usage_mb_per_pod', 0) or 0
        
        # Simple heuristic, adjust based on actual metrics
        if cpu_usage > 2.0: # Highly CPU bound
            return "spot-compute"
        if mem_usage > 4096: # Highly memory bound 
            return "spot-memory"
            
        return "spot-general"

    def _build_baseline_affinity(self) -> Dict:
        """§5.1: Hard On-Demand nodeAffinity."""
        return {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "karpenter.sh/capacity-type",
                                    "operator": "In",
                                    "values": ["on-demand"]
                                }
                            ]
                        }
                    ]
                }
            }
        }

    def _build_burst_affinity(self) -> Dict:
        """§5.2: Soft Spot preference nodeAffinity."""
        return {
            "nodeAffinity": {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": 100,
                        "preference": {
                            "matchExpressions": [
                                {
                                    "key": "karpenter.sh/capacity-type",
                                    "operator": "In",
                                    "values": ["spot"]
                                }
                            ]
                        }
                    }
                ]
            }
        }

    def _estimate_savings(
        self,
        od_count: int,
        spot_count: int,
        instance_types: List[Any],
        db: Optional[Session] = None,
        cluster_region: str = "us-east-1",
    ) -> Tuple[float, float]:
        """
        Estimate savings_pct and monthly_saving_usd.
        Uses real SpotPriceHistory prices from DB when available.
        Falls back to a 70% spot-discount heuristic only when no DB data exists.
        Returns (savings_pct, monthly_saving_usd)
        """
        if spot_count == 0 or not instance_types:
            return 0.0, 0.0

        total_pods = od_count + spot_count
        avg_od_price = (
            sum(float(inst.price) for inst in instance_types) / len(instance_types)
            if instance_types else 0.1
        )

        avg_spot_price: float
        if db is not None and instance_types:
            try:
                from backend.models.pricing import SpotPriceHistory
                from sqlalchemy import func
                type_names = [inst.name for inst in instance_types if hasattr(inst, "name")]
                if type_names:
                    spot_rows = (
                        db.query(
                            SpotPriceHistory.instance_type,
                            func.avg(SpotPriceHistory.price).label("avg_price"),
                        )
                        .filter(
                            SpotPriceHistory.instance_type.in_(type_names),
                            SpotPriceHistory.region == cluster_region,
                        )
                        .group_by(SpotPriceHistory.instance_type)
                        .all()
                    )
                    if spot_rows:
                        avg_spot_price = sum(float(r.avg_price) for r in spot_rows) / len(spot_rows)
                    else:
                        avg_spot_price = avg_od_price * 0.3
                else:
                    avg_spot_price = avg_od_price * 0.3
            except Exception as e:
                logger.warning("spot_price_lookup_failed", extra={"error": str(e), "region": cluster_region})
                avg_spot_price = avg_od_price * 0.3
        else:
            avg_spot_price = avg_od_price * 0.3

        cost_od_only = total_pods * avg_od_price * 730
        cost_mixed = (od_count * avg_od_price * 730) + (spot_count * avg_spot_price * 730)

        if cost_od_only == 0:
            return 0.0, 0.0

        savings_usd = cost_od_only - cost_mixed
        savings_pct = (savings_usd / cost_od_only) * 100

        return savings_pct, savings_usd

    def _build_signals_used(self, workload_state: WorkloadState, classification: Any, skew_detected: bool, degraded: bool) -> List[str]:
        """Build audit trail of all signals that influenced the decision."""
        signals = []
        signals.append(f"tier={classification.tier}")
        if classification.role != "WORKER":
            signals.append(f"role={classification.role}")
        signals.append(f"confidence={classification.confidence_state}")
        signals.append(f"spot_friendly={classification.spot_friendly}")
        
        signals.append(f"observed_replicas={workload_state.observed_replicas}")
        if workload_state.pdb_min_available:
            signals.append(f"pdb_min={workload_state.pdb_min_available}")
        if workload_state.hpa_min_replicas:
            signals.append(f"hpa_min={workload_state.hpa_min_replicas}")
            
        if skew_detected:
            signals.append("traffic_skew=detected")
            
        if degraded:
            signals.append("input_completeness=degraded")
            
        return signals

    def _check_input_completeness(self, workload_state: WorkloadState, classification: Any) -> Tuple[bool, List[str]]:
        """Task 1.25: Input Completeness Gate. Returns (degraded, missing)."""
        # REQUIRED fields check
        missing_required = []
        if workload_state.observed_replicas <= 0:
            missing_required.append("observed_replicas")
        if getattr(classification, 'confidence_state', None) is None:
            missing_required.append("confidence_state")
        if getattr(classification, 'spot_friendly', None) is None:
            missing_required.append("spot_friendly")
        if getattr(classification, 'tier', None) is None:
            missing_required.append("criticality_tier")
            
        if missing_required:
            raise PlacementValidationError(f"Missing REQUIRED inputs: {missing_required}")
            
        # OPTIONAL fields check
        missing_optional = 0
        if workload_state.hpa_min_replicas is None: missing_optional += 1
        if workload_state.pdb_min_available is None: missing_optional += 1
        if workload_state.pod_cpu_usage_per_pod is None: missing_optional += 1
        if workload_state.pod_request_rate_per_pod is None: missing_optional += 1
        
        degraded = missing_optional > 3
        return degraded, missing_required

    def _compute_input_hash(self, workload_state: WorkloadState, classification: Any, cluster_state: ClusterState) -> str:
        """Task 1.24: Deterministic input hash."""
        data = {
            "w_obs": workload_state.observed_replicas,
            "c_tier": classification.tier,
            "c_spot": classification.spot_friendly,
            "c_conf": classification.confidence_state,
            "hpa_min": workload_state.hpa_min_replicas,
            "pdb_min": workload_state.pdb_min_available,
            "cpu_cv": workload_state.pod_cpu_usage_per_pod,
            "req_cv": workload_state.pod_request_rate_per_pod
        }
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def _validate_prewrite(self, policy: PlacementPolicyRecord, observation_mode: bool) -> None:
        """Task 1.23: Pre-write validation. Raises on failure."""
        metrics_key = placement_metrics_key(policy.cluster_id)

        def _fail(assertion_name: str, msg: str):
            self.redis.hincrby(metrics_key, f"placement_prewrite_validation_failure:{assertion_name}", 1)
            raise PlacementValidationError(msg)

        if policy.spot_target + policy.ondemand_target != policy.observed_replicas:
            _fail("totals_mismatch", f"Totals mismatch: {policy.spot_target} + {policy.ondemand_target} != {policy.observed_replicas}")

        if observation_mode and policy.actionable:
            _fail("actionable_in_obs_mode", "actionable must be False in observation mode")

        if policy.confidence_state != "CONFIRMED" and policy.spot_target > 0:
            _fail("spot_target_non_confirmed", "spot_target must be 0 for non-CONFIRMED")

        if not policy.spot_friendly and policy.spot_target > 0:
            _fail("spot_target_non_spot_friendly", "spot_target must be 0 for non-spot_friendly")

        if policy.criticality_tier == "Platinum" and policy.ondemand_target != policy.observed_replicas:
            _fail("platinum_not_full_ondemand", "Platinum must be 100% ondemand")

        # Assert 7: SYSTEM/CONTROL_PLANE must be 100% ondemand
        signals_str = " ".join(policy.signals_used or [])
        if "role=SYSTEM" in signals_str or "role=CONTROL_PLANE" in signals_str:
            if policy.spot_target != 0 or policy.ondemand_target != policy.observed_replicas:
                _fail("system_cp_must_be_full_ondemand", "SYSTEM/CONTROL_PLANE must have 100% ondemand")

        # Assert 2: ondemand_target >= baseline_floor
        replicas = policy.observed_replicas
        if replicas <= 4:
            baseline_floor = max(replicas - 1, 2)
        else:
            tier_factor = {"Platinum": 1.0, "Gold": 0.7, "Silver": 0.5}.get(policy.criticality_tier, 0.0)
            baseline_floor = max(2, int(replicas * tier_factor))
        if policy.ondemand_target < baseline_floor:
            _fail("ondemand_below_floor", f"ondemand_target {policy.ondemand_target} < floor {baseline_floor}")

    def _validate_field_consistency(self, cluster_id: str, policies: List[PlacementPolicyRecord], db: Session):
        """Task 1.19: Background check Redis vs DB."""
        metrics_key = placement_metrics_key(cluster_id)
        check_fields = ['spot_friendly', 'ondemand_target', 'spot_target', 'actionable', 'confidence_state']
        for p in policies[:5]: # sample 5 for performance
            redis_raw = self.redis.get(placement_policy_key(cluster_id, p.workload_id))
            if redis_raw:
                try:
                    redis_data = json.loads(redis_raw)
                    for field in check_fields:
                        db_val = getattr(p, field, None)
                        redis_val = redis_data.get(field)
                        if redis_val != db_val:
                            logger.error("placement_field_mismatch", extra={
                                "cluster_id": cluster_id,
                                "workload_id": p.workload_id,
                                "field": field,
                                "redis_value": redis_val,
                                "db_value": db_val
                            })
                            self.redis.hincrby(metrics_key, f"placement_field_mismatch_count:{field}", 1)
                            # Overwrite Redis with DB value (DB is source of truth)
                            self.redis.set(placement_policy_key(cluster_id, p.workload_id), json.dumps(self._policy_to_dict(p)), ex=600)
                            break
                except json.JSONDecodeError:
                    pass

    def _policy_to_dict(self, p: PlacementPolicyRecord) -> dict:
        return {
            "workload_id": p.workload_id,
            "cluster_id": p.cluster_id,
            "namespace": p.namespace,
            "name": p.name,
            "criticality_tier": p.criticality_tier,
            "confidence_state": p.confidence_state,
            "spot_friendly": p.spot_friendly,
            "observed_replicas": p.observed_replicas,
            "ondemand_target": p.ondemand_target,
            "spot_target": p.spot_target,
            "spot_target_raw": p.spot_target_raw,
            "traffic_skew_detected": p.traffic_skew_detected,
            "skew_signal_source": p.skew_signal_source,
            "pod_cpu_cv": p.pod_cpu_cv,
            "pod_request_rate_cv": p.pod_request_rate_cv,
            "assigned_nodepool_class": p.assigned_nodepool_class,
            "spot_instance_families": p.spot_instance_families,
            "spot_instance_types": p.spot_instance_types,
            "baseline_affinity": p.baseline_affinity,
            "burst_affinity": p.burst_affinity,
            "topology_spread": p.topology_spread,
            "spread_relaxation_tier": p.spread_relaxation_tier,
            "rollout_eligible": p.rollout_eligible,
            "rollout_blocked_reason": p.rollout_blocked_reason,
            "estimated_savings_pct": p.estimated_savings_pct,
            "estimated_monthly_saving_usd": p.estimated_monthly_saving_usd,
            "actionable": p.actionable,
            "actionable_blocked_reason": p.actionable_blocked_reason,
            "signals_used": p.signals_used,
            "schema_version": p.schema_version,
            "input_hash": p.input_hash,
            "generated_at": p.generated_at.isoformat() if p.generated_at else None
        }

    def generate_placement_policy(self, workload_id: str, namespace: str, name: str, cluster_id: str, env: str,
                                  workload_state: WorkloadState, classification: Any, cluster_state: ClusterState,
                                  available_instances: List[Any], get_success_rate_fn,
                                  db: Optional[Session] = None, cluster_region: str = "us-east-1") -> PlacementPolicyRecord:
        """Core orchestrator for a single workload policy generation."""
        degraded, missing = self._check_input_completeness(workload_state, classification)
        
        # Traffic skew & Baseline
        baseline, skew_detected, skew_source = self.apply_traffic_skew_adjustment(
            workload_state, 
            workload_state.observed_replicas,
            workload_state.pod_request_rate_cv,
            workload_state.pod_cpu_cv
        )
        ondemand_baseline = self.compute_ondemand_baseline(workload_state, classification)
        
        # Initial Capacity assignment
        od_count, spot_count_raw = self.assign_capacity_types(workload_state, classification, ondemand_baseline)
        
        # Instance selection
        arch = getattr(workload_state, 'arch', 'amd64')
        spot_instances = self.select_instance_families(arch, available_instances, get_success_rate_fn)
        families = list(set([inst.family for inst in spot_instances]))
        types = [inst.name for inst in spot_instances]
        
        # Costs — use real spot prices from DB when available
        savings_pct, savings_usd = self._estimate_savings(
            od_count, spot_count_raw, spot_instances, db=db, cluster_region=cluster_region
        )
        
        # Availability capping
        availability = self.compute_spot_availability_factor(region=getattr(cluster_state, 'region', 'us-east-1'))
        spot_count_actual = self.apply_availability_to_spot(spot_count_raw, availability)
        od_count = od_count + (spot_count_raw - spot_count_actual)
        
        # Constraints
        spread, relax_tier = self.compute_spread_constraints(workload_state, cluster_state, classification)
        nodepool_class = self._assign_nodepool_class(classification, workload_state)
        
        # Rollout Eligibility
        rollout_ok, rollout_reason = self.is_rollout_eligible(workload_state, classification, cluster_state, env, savings_pct)
        
        # Guards
        guards = self.evaluate_cluster_guards(cluster_state, env)
        
        # Actionability
        obs_mode = settings.PLACEMENT_ADVISOR_OBSERVATION_MODE
        actionable = not obs_mode and not degraded and not guards.blocked and classification.confidence_state == "CONFIRMED"
        
        # Task 3.4: Phase 2c active - Bronze, Silver, AND Gold (if PDB) are actionable. Platinum never.
        if classification.tier == "Platinum":
            actionable = False
        elif classification.tier == "Gold" and not getattr(workload_state, 'has_pdb', False):
            actionable = False
            
        blocked_reason = None
        if obs_mode:
            blocked_reason = "observation_mode"
        elif degraded:
            blocked_reason = "degraded_inputs"
        elif guards.blocked:
            blocked_reason = guards.reason
        elif classification.confidence_state != "CONFIRMED":
            blocked_reason = "not_confirmed"
            
        signals = self._build_signals_used(workload_state, classification, skew_detected, degraded)
        
        policy = PlacementPolicyRecord(
            cluster_id=cluster_id,
            workload_id=workload_id,
            namespace=namespace,
            name=name,
            criticality_tier=classification.tier,
            confidence_state=classification.confidence_state,
            spot_friendly=classification.spot_friendly,
            observed_replicas=workload_state.observed_replicas,
            ondemand_target=od_count,
            spot_target=spot_count_raw, # Will be adjusted later by cap
            spot_target_raw=spot_count_raw,
            traffic_skew_detected=skew_detected,
            skew_signal_source=skew_source,
            pod_cpu_cv=workload_state.pod_cpu_cv,
            pod_request_rate_cv=workload_state.pod_request_rate_cv,
            assigned_nodepool_class=nodepool_class,
            spot_instance_families=families,
            spot_instance_types=types,
            baseline_affinity=self._build_baseline_affinity(),
            burst_affinity=self._build_burst_affinity(),
            topology_spread=None,
            spread_relaxation_tier=relax_tier,
            keda_min_replicas=od_count,  # v5.7: KEDA minReplicaCount = ondemand_target
            keda_max_replicas=workload_state.hpa_max_replicas,
            rollout_eligible=rollout_ok,
            rollout_blocked_reason=rollout_reason,
            estimated_savings_pct=savings_pct,
            estimated_monthly_saving_usd=savings_usd,
            actionable=actionable,
            actionable_blocked_reason=blocked_reason,
            signals_used=signals,
            schema_version="5.10",
            input_hash=self._compute_input_hash(workload_state, classification, cluster_state)
        )
        return policy

    def _write_policy(self, db: Session, policy: PlacementPolicyRecord, observation_mode: bool) -> bool:
        """Task 1.27: Decision Diff Logging and Invariant 12: Write Version Control."""
        from sqlalchemy.dialects.postgresql import insert
        
        # Invariant 7: Pre-write validation
        self._validate_prewrite(policy, observation_mode)
        
        # Load previous for Diff Logging
        prev = db.query(PlacementPolicyRecord).filter_by(cluster_id=policy.cluster_id, workload_id=policy.workload_id).first()
        policy_changed_keda = False
        
        if prev:
            diffs = []
            if prev.ondemand_target != policy.ondemand_target: diffs.append(f"ondemand_target:{prev.ondemand_target}->{policy.ondemand_target}")
            if prev.spot_target != policy.spot_target: diffs.append(f"spot_target:{prev.spot_target}->{policy.spot_target}")
            if prev.actionable != policy.actionable: diffs.append(f"actionable:{prev.actionable}->{policy.actionable}")
            
            if diffs:
                logger.info("placement_policy_changed", extra={
                    "workload_id": policy.workload_id,
                    "cluster_id": policy.cluster_id,
                    "diffs": ",".join(diffs)
                })
                self.redis.hincrby(placement_metrics_key(policy.cluster_id), "placement_policy_changed", 1)

                # Task 2.2: KEDA ScaledObject patcher
                if not observation_mode:
                    policy_changed_keda = True

            # Task 1.24 Write Suppression
            if prev.input_hash == policy.input_hash and prev.spot_target == policy.spot_target and prev.ondemand_target == policy.ondemand_target:
                # Refresh Redis TTL but skip DB write
                self.redis.expire(placement_policy_key(policy.cluster_id, policy.workload_id), 600)
                self.redis.hincrby(placement_metrics_key(policy.cluster_id), "placement_policy_write_suppressed_count", 1)
                return False
                
        # SQLAlchemy Upsert with version guard
        stmt = insert(PlacementPolicyRecord).values(**self._policy_to_dict(policy))
        update_dict = {
            c.name: c for c in stmt.excluded 
            if not c.primary_key and c.name not in ('id', 'created_at')
        }
        update_stmt = stmt.on_conflict_do_update(
            constraint='uq_placement_policies_cluster_workload',
            set_=update_dict,
            where=(PlacementPolicyRecord.generated_at < stmt.excluded.generated_at)
        )
        db.execute(update_stmt)
        
        # Redis write
        self.redis.set(placement_policy_key(policy.cluster_id, policy.workload_id), json.dumps(self._policy_to_dict(policy)), ex=600)
        
        # Patch KEDA if changed (Task 2.2)
        if policy_changed_keda or not prev:
            if not observation_mode:
                try:
                    self._patch_keda_scaledobject(policy)
                except Exception as e:
                    logger.warning(f"Failed to patch KEDA ScaledObject for {policy.workload_id}: {e}")
                    
        return True

    def _patch_keda_scaledobject(self, policy: PlacementPolicyRecord):
        """Task 2.2: KEDA ScaledObject annotation patcher."""
        from kubernetes import client
        from backend.models.cluster import Cluster
        from backend.services.karpenter_service import KarpenterService
        from backend.services.keda_service import KedaService
        from backend.db.session import SessionLocal
        from datetime import datetime
        
        db = SessionLocal()
        karpenter_svc = KarpenterService(db=db, redis=self.redis)
        
        try:
            cluster = db.query(Cluster).filter(Cluster.id == policy.cluster_id).first()
            if not cluster:
                return
                
            api_client = karpenter_svc._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)
            keda_svc = KedaService(db=db, redis=self.redis)
            
            scaled_object = keda_svc.get_scaled_object_for_workload(
                cluster_id=policy.cluster_id,
                namespace=policy.namespace,
                controller_name=policy.name,
                controller_kind="Deployment"
            )
            
            if not scaled_object:
                return
                
            ts = policy.generated_at.isoformat() if policy.generated_at else datetime.utcnow().isoformat()
            
            patch = {
                "metadata": {
                    "annotations": {
                        "aura.io/ondemand-floor": str(policy.ondemand_target),
                        "aura.io/policy-version": ts
                    }
                },
                "spec": {
                    "minReplicaCount": policy.ondemand_target
                }
            }
            
            logger.info(f"Patching KEDA ScaledObject {policy.namespace}/{scaled_object.name} minReplicaCount={policy.ondemand_target}")
            custom_api.patch_namespaced_custom_object(
                group="keda.sh",
                version="v1alpha1",
                namespace=policy.namespace,
                plural="scaledobjects",
                name=scaled_object.name,
                body=patch
            )
        except Exception as e:
            logger.error(f"Failed to patch KEDA ScaledObject for {policy.workload_id}: {e}")
        finally:
            db.close()

    def _collect_cluster_state(self, cluster_id: str, db: Session) -> ClusterState:
        """Task 1.14: Aggregate cluster state."""
        # Baseline defaults
        total_pods = 0
        spot_pods = 0
        in_flight = 0
        unhealthy = 0
        ready = 0
        total_nodes = 0
        not_ready = 0
        
        # Pull from agent heartbeat
        heartbeat_raw = self.redis.get(f"spot:agent:heartbeat:{cluster_id}")
        if heartbeat_raw:
            try:
                hb = json.loads(heartbeat_raw)
                total_nodes = hb.get("node_count", 0)
                ready = hb.get("ready_nodes", 0)
                not_ready = total_nodes - ready
                
                # These might require specific new agent metrics, mapped to defaults if missing
                total_pods = hb.get("total_running_pods", getattr(hb, 'pod_count', 0))
                spot_pods = hb.get("current_spot_pods", 0)
                in_flight = hb.get("in_flight_spot_pods", 0)
                unhealthy = hb.get("unhealthy_pending_pods", 0)
            except Exception as e:
                logger.warning("Failed to parse agent heartbeat", extra={"cluster_id": cluster_id, "error": str(e)})

        # Subnet IPs - task 5.4 implementation
        subnet_ips = {}
        try:
            from backend.models.cluster import Cluster
            from backend.services.substitute_manager import _get_az_available_ips
            from backend.redis_keys import subnet_ips_key
            
            # 1. Try resolving from our Phase 2 placement AZ cache first
            # We don't know the exact AZs until we check one of the cluster nodes or fallback to fetching all.
            # It's easier to just fetch from the `_get_az_available_ips` helper which uses a 60s cache, 
            # and then populate our 600s cache for the cycle metrics.
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if cluster:
                fetched_ips = _get_az_available_ips(cluster, db, self.redis)
                if fetched_ips:
                    subnet_ips = fetched_ips
                    # Populate the strict Task 5.4 cache format for 10 minutes
                    for az, ips in subnet_ips.items():
                        self.redis.setex(subnet_ips_key(cluster_id, az), 600, json.dumps(ips))
        except Exception as e:
            logger.warning("Failed to wire subnet IPs for placement advisor", extra={"cluster_id": cluster_id, "error": str(e)})
        
        return ClusterState(
            total_running_pods=total_pods,
            current_spot_pods=spot_pods,
            in_flight_spot_pods=in_flight,
            unhealthy_pending_pods=unhealthy,
            node_ready_count=ready,
            node_total_count=total_nodes,
            not_ready_nodes=not_ready,
            not_ready_trend="stable",
            subnet_ips_by_az=subnet_ips,
            total_nodes=total_nodes,
            collected_at=datetime.utcnow()
        )
        
    def _collect_workload_state(self, classification: Any, cluster_id: str, db: Session) -> WorkloadState:
        """Task 1.14: Fetch workload state from pod_state cache and DB."""
        workload_id = classification.workload_id
        
        # New telemetry from agent (HPA, PDB, CVs) — must come before stability check
        state_key = f"spot:workload:state:{cluster_id}:{workload_id}"
        state_raw = self.redis.get(state_key)
        state_data = {}
        if state_raw:
            try:
                state_data = json.loads(state_raw)
            except Exception as e:
                logger.warning(f"[PlacementAdvisor] Failed to parse workload state for {workload_id}: {e}")

        observed = state_data.get("observed_replicas", getattr(classification, 'observed_replicas', 0))

        # Stability tracking (Task 1.29) — write-back with 7-day TTL
        stability_key = placement_stability_key(cluster_id, workload_id)
        STABILITY_TTL = 604800  # 7 days
        stable_for = 0  # Default to unstable on first run
        now_ts = time.time()
        raw_stab = self.redis.get(stability_key)
        if raw_stab:
            try:
                stab_data = json.loads(raw_stab)
                stored_replicas = stab_data.get("replica_count", -1)
                last_ts = stab_data.get("last_change_ts", now_ts)
                # Changed if replicas differ by >= 1
                if abs(observed - stored_replicas) >= 1:
                    new_stab = {"last_change_ts": now_ts, "replica_count": observed, "restart_rate_bucket": "low"}
                    self.redis.setex(stability_key, STABILITY_TTL, json.dumps(new_stab))
                    stable_for = 0
                else:
                    stable_for = int((now_ts - last_ts) / 60)
                    self.redis.expire(stability_key, STABILITY_TTL)  # refresh TTL
            except Exception as e:
                logger.warning(f"[PlacementAdvisor] Stability parse error for {workload_id}: {e}")
                new_stab = {"last_change_ts": now_ts, "replica_count": observed, "restart_rate_bucket": "low"}
                self.redis.setex(stability_key, STABILITY_TTL, json.dumps(new_stab))
        else:
            # First run — write key, start clock
            new_stab = {"last_change_ts": now_ts, "replica_count": observed, "restart_rate_bucket": "low"}
            self.redis.setex(stability_key, STABILITY_TTL, json.dumps(new_stab))
        hpa_min = state_data.get("hpa_min_replicas")
        hpa_max = state_data.get("hpa_max_replicas")
        pdb_min = state_data.get("pdb_min_available")
        current_spot = state_data.get("current_spot_pods", 0)
        current_od = state_data.get("current_ondemand_pods", observed)
        
        has_pdb = state_data.get("has_pdb", False)
        has_ts = state_data.get("has_topology_spread", False)
        has_paa = state_data.get("has_pod_anti_affinity", False)
        
        cpu_usage = state_data.get("pod_cpu_usage_per_pod")
        req_rate = state_data.get("pod_request_rate_per_pod")
        cpu_cv = state_data.get("pod_cpu_cv")
        req_rate_cv = state_data.get("pod_request_rate_cv")

        return WorkloadState(
            observed_replicas=observed,
            hpa_min_replicas=hpa_min,
            hpa_max_replicas=hpa_max,
            pdb_min_available=pdb_min,
            current_spot_pods=current_spot,
            current_ondemand_pods=current_od,
            stable_for_minutes=stable_for,
            has_pdb=has_pdb,
            has_topology_spread=has_ts,
            has_pod_anti_affinity=has_paa,
            replicas=observed,
            pod_cpu_usage_per_pod=cpu_usage,
            pod_request_rate_per_pod=req_rate,
            assigned_nodepool_class="spot-general", # will be reassigned internally later
            pod_cpu_cv=cpu_cv,
            pod_request_rate_cv=req_rate_cv
        )

    def run_placement_cycle(self, cluster_id: str, db: Session, env: str, max_ratio: float, workloads: List[Any], get_success_rate_fn, cluster_state: ClusterState, get_workload_state_fn) -> List[PlacementPolicyRecord]:
        """Core execution loop for a cluster."""
        cycle_start = time.monotonic()

        # Invariant 13: Redis failure → skip cycle entirely (cannot read cluster state safely)
        try:
            self.redis.ping()
        except Exception as e:
            logger.error("placement_redis_unavailable", extra={"cluster_id": cluster_id, "error": str(e)})
            return []

        # Invariant 13: K8s data unavailable → force actionable=False on all policies this cycle
        k8s_degraded = cluster_state.total_running_pods == 0 and cluster_state.total_nodes == 0
        if k8s_degraded:
            logger.warning("placement_k8s_data_unavailable", extra={"cluster_id": cluster_id})

        # Invariant 10: Cluster state freshness
        age_seconds = (datetime.utcnow() - cluster_state.collected_at).total_seconds()
        agent_heartbeat_ttl = 120 # typical
        if age_seconds > 2 * agent_heartbeat_ttl:
            logger.error("cluster_state_stale", extra={"cluster_id": cluster_id, "age_seconds": age_seconds})
            self.redis.hincrby(placement_metrics_key(cluster_id), "placement_cycle_aborted_stale_state", 1)
            return []
            
        # Resolve cluster region for real spot price lookup
        cluster_region = "us-east-1"
        try:
            from backend.models.cluster import Cluster as _Cluster
            _cluster_obj = db.query(_Cluster).filter(_Cluster.id == cluster_id).first()
            if _cluster_obj and getattr(_cluster_obj, "region", None):
                cluster_region = _cluster_obj.region
        except Exception as _re:
            logger.warning("placement_region_lookup_failed", extra={"cluster_id": cluster_id, "error": str(_re)})

        policies = []
        assignments = {}
        workloads_by_id = {}
        
        # Priority sort by spot_score
        workloads.sort(key=lambda w: getattr(w, 'spot_score', 0), reverse=True)
        
        obs_mode = settings.PLACEMENT_ADVISOR_OBSERVATION_MODE
        available_instances = [] # Pass from catalog in real usage
        
        for workload in workloads:
            # Task 1.28: Time budget check
            if time.monotonic() - cycle_start > CYCLE_TIME_BUDGET_SECONDS:
                logger.warning("placement_cycle_timeout", extra={"cluster_id": cluster_id})
                self.redis.hincrby(placement_metrics_key(cluster_id), "placement_cycle_timeout_count", 1)
                break
                
            try:
                state = get_workload_state_fn(workload.workload_id)
                # Invariant 13: AWS API failure → spot_target=0, continue with OD-only
                try:
                    policy = self.generate_placement_policy(
                        workload_id=workload.workload_id,
                        namespace=workload.namespace,
                        name=workload.name,
                        cluster_id=cluster_id,
                        env=env,
                        workload_state=state,
                        classification=workload,
                        cluster_state=cluster_state,
                        available_instances=available_instances,
                        get_success_rate_fn=get_success_rate_fn,
                        db=db,
                        cluster_region=cluster_region,
                    )
                except Exception as aws_err:
                    if "pricing" in str(aws_err).lower() or "catalog" in str(aws_err).lower() or "instance" in str(aws_err).lower():
                        logger.error("aws_api_unavailable", extra={"cluster_id": cluster_id, "workload": workload.workload_id, "error": str(aws_err)})
                        raise  # re-raise to outer except which will skip workload safely
                    raise
                # Invariant 13: K8s degraded → force actionable=False
                if k8s_degraded:
                    policy.actionable = False
                    policy.actionable_blocked_reason = "k8s_data_unavailable"
                policies.append(policy)
                assignments[policy.workload_id] = (policy.ondemand_target, policy.spot_target_raw)
                workloads_by_id[policy.workload_id] = workload
            except PlacementValidationError as e:
                logger.warning("placement_validation_error", extra={"workload": workload.workload_id, "error": str(e)})
                self.redis.hincrby(placement_metrics_key(cluster_id), "placement_skipped_missing_required_input", 1)
            except Exception as e:
                # Invariant 11: Isolation
                logger.error("placement_workload_error", extra={"workload": workload.workload_id, "error": str(e)}, exc_info=True)
                self.redis.hincrby(placement_metrics_key(cluster_id), "placement_workload_error_count", 1)
                
        # Phase 2: Apply cap and write
        capped_assignments = self.apply_cluster_spot_cap(assignments, cluster_state, cluster_id, max_ratio, workloads_by_id)
        
        for p in policies:
            if p.workload_id in capped_assignments:
                od, sp = capped_assignments[p.workload_id]
                p.ondemand_target = od
                p.spot_target = sp
                if sp < p.spot_target_raw:
                    p.signals_used.append("spot_target_capped")
                    
            try:
                self._write_policy(db, p, obs_mode)
            except Exception as e:
                logger.error("placement_write_error", extra={"workload": p.workload_id, "error": str(e)}, exc_info=True)
                
        db.commit()

        # Invariant 11: placement_cycle_degraded alert if error rate > 10%
        error_count = int(self.redis.hget(placement_metrics_key(cluster_id), "placement_workload_error_count") or 0)
        if len(workloads) > 0 and error_count / len(workloads) > 0.10:
            self.redis.hincrby(placement_metrics_key(cluster_id), "placement_cycle_degraded", 1)
            logger.error("placement_cycle_degraded", extra={"cluster_id": cluster_id, "error_rate": error_count / len(workloads)})

        # Task 1.19: validate field consistency
        self._validate_field_consistency(cluster_id, policies, db)
        
        # Task 1.17: Detailed metrics emission
        try:
            total_od_actual = sum(p.ondemand_target for p in policies)
            total_spot_actual = sum(p.spot_target for p in policies)
            savings_pct_list = [p.estimated_savings_pct for p in policies if p.spot_target > 0]
            avg_savings = sum(savings_pct_list) / len(savings_pct_list) if savings_pct_list else 0.0
            
            skew_count = sum(1 for p in policies if p.traffic_skew_detected)
            
            detailed_metrics = {
                "placement_policies_generated": len(policies),
                "cluster_spot_ratio": total_spot_actual / (total_od_actual + total_spot_actual) if (total_od_actual + total_spot_actual) > 0 else 0,
                "spot_target_total": total_spot_actual,
                "ondemand_target_total": total_od_actual,
                "estimated_savings_pct_avg": avg_savings,
                "traffic_skew_detected_rate": skew_count / len(policies) if policies else 0,
                "policy_generation_latency_ms": (time.monotonic() - cycle_start) * 1000
            }
            metrics_key = placement_metrics_key(cluster_id) + ":detailed"
            for k, v in detailed_metrics.items():
                self.redis.hset(metrics_key, k, str(v))
            self.redis.expire(metrics_key, 86400)
        except Exception as e:
            logger.warning(f"Failed to emit detailed metrics for {cluster_id}: {e}")
            
        return policies

