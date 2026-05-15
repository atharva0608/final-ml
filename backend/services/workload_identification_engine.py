"""
Workload Identification Engine v4.3
====================================
Read-only, deterministic, confidence-first engine.
No ML, no eBPF, no mutations.

Scoring dimensions:
  - criticality:  0–10  (how important is this workload?)
  - spot_score:   0–10  (how safe is it on spot?)
  - confidence:   1–10  → DRAFT / PROVISIONAL / CONFIRMED

Confidence states gate downstream actions:
  DRAFT       (<5)  — engine observing, no actions
  PROVISIONAL (5–7) — suggestions only, no automation
  CONFIRMED   (≥8)  — full automation permitted

All timestamps MUST be UTC. Never use datetime.now() in this file.
Source of truth: documents/changes.md v4.3
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

# ---------------------------------------------------------------------------
# Structured logger — all engine log events use this
# ---------------------------------------------------------------------------
logger = structlog.get_logger("wie")


# ---------------------------------------------------------------------------
# UTC helper — enforced throughout the engine
# ---------------------------------------------------------------------------
def utc_now() -> datetime:
    """Return current UTC time. The ONLY permitted way to get current time in this file."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return utc_now().isoformat()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Namespaces that are always SYSTEM role — reuse set from workload_classifier.py
DEFAULT_SYSTEM_NAMESPACES: frozenset = frozenset({
    "kube-system", "kube-public", "kube-node-lease",
    "karpenter", "spot-optimizer", "cert-manager", "monitoring",
    "istio-system", "linkerd",
})

# Priority class names that indicate system-critical scheduling
SYSTEM_PRIORITY_CLASSES: frozenset = frozenset({
    "system-node-critical",
    "system-cluster-critical",
})

# Sidecar container names to exclude from restart counts / container analysis
SIDECAR_CONTAINERS: frozenset = frozenset({
    "istio-proxy", "istio-init", "vault-agent", "filebeat",
    "datadog-agent", "newrelic-infrastructure", "splunk-fluentd",
    "fluentbit-sidecar", "cloudwatch-agent",
})

# Cache-layer image name patterns (controller name or app label matching)
CACHE_IMAGE_PATTERNS: frozenset = frozenset({
    "redis", "memcached", "dragonfly", "keydb", "hazelcast",
    "varnish", "twemproxy", "mcrouter",
})

# Sentinel value: no metrics ever collected for this workload
METRICS_ABSENT_VALUE = 999

# Staleness thresholds (minutes)
METRICS_STALE_THRESHOLD_MINUTES = 60     # > 1 hour → confidence penalty
METRICS_FORCE_DRAFT_THRESHOLD = 999      # Never collected → force DRAFT

# Schema version — all output must carry this
SCHEMA_VERSION = "4.4"
SUPPORTED_SCHEMA_VERSION = SCHEMA_VERSION  # used by sanitize_classification_output()

# Minimum signals required for a valid classification
MIN_EXPECTED_SIGNALS = 3

# Confidence state thresholds
CONFIDENCE_THRESHOLD_DRAFT = 5       # < 5 → DRAFT
CONFIDENCE_THRESHOLD_PROVISIONAL = 8 # < 8 → PROVISIONAL; ≥ 8 → CONFIRMED

# Cold start: cluster engine must be running for 24h before CONFIRMED is allowed
COLD_START_HOURS = 24


# ---------------------------------------------------------------------------
# Task 1.1 — WorkloadInput dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkloadInput:
    """
    All inputs required by the scoring pipeline for one workload (controller).
    Populated by WorkloadDataCollector before being passed to classify_workload().

    Fields marked Optional[T] = None are safe to omit — scoring functions guard
    explicitly and skip the signal rather than guessing.

    `annotations` carries K8s metadata.annotations (used by override system).
    `owner_labels` carries K8s metadata.labels (used for selector matching).
    These are DIFFERENT fields and must be populated independently.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    workload_id: str            # "namespace/name" — unique within cluster
    cluster_id: str
    namespace: str
    name: str
    controller_kind: str        # Deployment / StatefulSet / DaemonSet / Job / CronJob

    # ── Scheduling ──────────────────────────────────────────────────────────
    priority_class: Optional[str] = None            # pod.spec.priorityClassName
    priority_class_value: Optional[int] = None      # resolved PriorityClass.value

    # ── Replica state ────────────────────────────────────────────────────────
    replicas: int = 1
    ready_replicas: Optional[int] = None            # None = unknown

    # ── Resilience ───────────────────────────────────────────────────────────
    has_pdb: bool = False
    pdb_min_available: Optional[int] = None         # numeric minAvailable
    pdb_max_unavailable: Optional[int] = None       # numeric maxUnavailable (0 = strict)
    has_topology_spread: bool = False
    topology_min_domains: Optional[int] = None      # topologySpreadConstraints.minDomains
    has_pod_anti_affinity: bool = False

    # ── Exposure ─────────────────────────────────────────────────────────────
    service_type: Optional[str] = None              # ClusterIP / NodePort / LoadBalancer
    has_ingress: bool = False
    inbound_services: int = 0                       # distinct Services routing to this workload

    # ── Data safety ──────────────────────────────────────────────────────────
    data_safety: str = "EPHEMERAL"                  # STATEFUL / CACHE / EPHEMERAL
    has_pvc: bool = False

    # ── Workload age ─────────────────────────────────────────────────────────
    workload_age_hours: float = 0.0
    workload_age_days: float = 0.0

    # ── Stability ────────────────────────────────────────────────────────────
    stable_for_minutes: int = 0                     # minutes since last restart/replica change
    last_restart_reason: Optional[str] = None       # OOMKilled / CrashLoopBackOff / etc.
    restart_rate_normalized: Optional[float] = None # vs cluster baseline; None = no baseline yet
    restart_count_per_hour: float = 0.0

    # ── Metrics quality ──────────────────────────────────────────────────────
    metrics_stale_minutes: int = METRICS_ABSENT_VALUE  # default = no metrics collected

    # ── Readiness probe ──────────────────────────────────────────────────────
    readiness_initial_delay: Optional[int] = None   # initialDelaySeconds; None = no probe

    # ── Traffic (optional — requires service mesh) ───────────────────────────
    outbound_dominant_pct: Optional[float] = None   # % of traffic to single upstream
    # ENFORCEMENT: When None, NO outbound signal may be emitted. Complete omission.

    # ── Leader election ──────────────────────────────────────────────────────
    ready_endpoint_count: int = 0                   # from EndpointSlice

    # ── Zone placement ───────────────────────────────────────────────────────
    observed_zones: List[str] = field(default_factory=list)  # node zone labels observed
    has_declared_spread: bool = False               # topology spread OR pod anti-affinity

    # ── Labels & annotations ─────────────────────────────────────────────────
    owner_labels: Dict[str, str] = field(default_factory=dict)   # metadata.labels
    annotations: Dict[str, str] = field(default_factory=dict)    # metadata.annotations

    # ── CronJob / Job specific ───────────────────────────────────────────────
    current_run_minutes: Optional[int] = None       # active Job duration
    has_retry_policy: bool = False                  # backoffLimit > 0

    # ── Computed fields (set by detect_* helpers before scoring) ─────────────
    missing_critical_fields: bool = False
    conflicting_signals: bool = False

    # ── Classifier bridge (set by orchestrator from workload_classifier.py output) ──
    detected_app_type: Optional[str] = None
    # Examples: "postgresql", "kafka", "redis", "celery_worker", "stateless_service"
    # None = classifier did not run or returned no match (treat as unknown)

    classifier_confidence: float = 0.0
    # 0.0–1.0 from compute_classification_confidence() in workload_classifier.py
    # 0.0 = not classified; 1.0 = annotation override (certain)


# ---------------------------------------------------------------------------
# Task 1.2 — WorkloadClassification output dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkloadClassification:
    """
    Output of classify_workload(). Immutable after enforce_confidence() runs.
    schema_version is always "4.3".
    is_simulation is True only for calls with mode="simulation".
    """

    # Identity
    workload_id: str
    cluster_id: str
    namespace: str
    name: str
    controller_kind: str

    # Scoring results
    role: str                       # SYSTEM / CONTROL_PLANE / APPLICATION
    criticality_score: int          # 0–10
    tier: str                       # Platinum / Gold / Silver / Bronze
    spot_score: int                 # 0–10
    spot_friendly: bool
    confidence_score: int           # 1–10
    confidence_state: str           # DRAFT / PROVISIONAL / CONFIRMED
    data_safety: str                # STATEFUL / CACHE / EPHEMERAL

    # Traceability
    signals_fired: List[str] = field(default_factory=list)

    # Override
    override_active: bool = False
    override_reason: Optional[str] = None

    # ── Placement intent signals (new in v4.4) ───────────────────────────────────────
    az_spread_required: bool = False    # Must be spread across >= 2 AZs for safe operation
    disruption_safe: bool = False       # Safe to remove one pod right now

    # ── Spot distribution constraints (new in v4.5) ──────────────────────────────────
    min_on_demand_replicas: int = 0     # Minimum OD replicas required for safety
    max_spot_replicas: int = 0          # Maximum spot replicas allowed
    total_replicas: int = 0             # Snapshot replica count at classification time
    spot_eligible: bool = False         # Derived: max_spot_replicas > 0

    # ── Workload class (v4.6) — drives PPE PodSelector + DE execution strategy ──────
    # "db" | "stateful" | "stateless" | "mixed"
    workload_class: str = "stateless"

    # ── PDB snapshot (propagated from WorkloadInput at classify time) ──────────────────
    has_pdb: bool = False

    # Metadata
    classified_at: datetime = field(default_factory=utc_now)
    input_hash: str = ""
    schema_version: str = SCHEMA_VERSION
    is_simulation: bool = False     # Set to True when mode="simulation"


# ---------------------------------------------------------------------------
# Task 1.2a — Tier mapping
# ---------------------------------------------------------------------------

def criticality_to_tier(criticality_score: int) -> str:
    """
    Map raw criticality score (0–10) to human tier label.
    Called in classify_workload() after compute_criticality().
    """
    if criticality_score >= 9:
        return "Platinum"
    elif criticality_score >= 6:
        return "Gold"
    elif criticality_score >= 3:
        return "Silver"
    else:
        return "Bronze"


# ---------------------------------------------------------------------------
# Task 1.2b — data_safety classification
# ---------------------------------------------------------------------------

# Classifier-confirmed stateful app types
_CLASSIFIER_STATEFUL_TYPES: frozenset = frozenset({
    "postgresql", "mysql", "oracle", "sqlserver", "mongodb",
    "cassandra", "elasticsearch", "couchdb", "timeseries_db",
    "graph_db", "etcd", "zookeeper", "stateful_with_pvc",
    "stateful_ha", "stateful_with_db_migration",
})
_CLASSIFIER_CACHE_TYPES: frozenset = frozenset({"redis"})


def determine_data_safety(workload: WorkloadInput) -> str:
    """
    Derive data_safety from workload properties.
    Priority: classifier output (if confident) → structural signals → patterns.
    Returns: STATEFUL | CACHE | EPHEMERAL
    """
    # Classifier bridge — use classifier result if confidence is sufficient
    if workload.detected_app_type and workload.classifier_confidence >= 0.3:
        if workload.detected_app_type in _CLASSIFIER_STATEFUL_TYPES:
            return "STATEFUL"
        if (workload.detected_app_type in _CLASSIFIER_CACHE_TYPES
                and not workload.has_pvc
                and workload.controller_kind != "StatefulSet"):
            return "CACHE"
        # Queue workers and web services → fall through to structural check

    # StatefulSet or any PVC attachment = stateful regardless of image
    if workload.controller_kind == "StatefulSet" or workload.has_pvc:
        return "STATEFUL"

    # Cache pattern: check workload name and app.kubernetes.io/name label
    name_lower = workload.name.lower()
    for pattern in CACHE_IMAGE_PATTERNS:
        if pattern in name_lower:
            return "CACHE"

    app_label = workload.owner_labels.get("app.kubernetes.io/name", "").lower()
    for pattern in CACHE_IMAGE_PATTERNS:
        if pattern in app_label:
            return "CACHE"

    return "EPHEMERAL"


# ---------------------------------------------------------------------------
# Task 1.2c — Missing fields + conflicting signals detection
# ---------------------------------------------------------------------------

def detect_missing_critical_fields(workload: WorkloadInput) -> bool:
    """
    Returns True if 2+ fields critical to accurate scoring are missing (None).
    Missing = engine operating with incomplete information → lower confidence.

    Threshold 2+: a single missing field is common and acceptable.
    2+ signals a data collection problem.
    """
    critical_fields = [
        workload.priority_class,       # None = unknown scheduling priority
        workload.last_restart_reason,  # None = restart history unavailable
    ]
    none_count = sum(1 for f in critical_fields if f is None)

    # ready_replicas unknown also counts
    if workload.ready_replicas is None:
        none_count += 1

    # metrics_stale_minutes == METRICS_ABSENT_VALUE = no data ever
    if workload.metrics_stale_minutes == METRICS_ABSENT_VALUE:
        none_count += 1

    return none_count >= 2


def detect_conflicting_signals(workload: WorkloadInput) -> bool:
    """
    Returns True when 2+ signals contradict each other — indicating genuinely
    ambiguous classification state.

    Per spec: Deployment + PVC alone does NOT trigger this (common pattern:
    Kafka sidecars, ML model caches). Requires 2+ independent contradictions.
    """
    conflicts = 0

    # Deployment with PVC — ambiguous statefulness
    if workload.controller_kind == "Deployment" and workload.has_pvc:
        conflicts += 1

    # Has PDB but replicas == 1 — PDB is meaningless, operator confusion
    if workload.has_pdb and workload.replicas == 1:
        conflicts += 1

    # StatefulSet but no PVC — possibly miscategorized controller kind
    if workload.controller_kind == "StatefulSet" and not workload.has_pvc:
        conflicts += 1

    # High-priority class but no PDB in non-system namespace
    if (workload.priority_class_value is not None
            and workload.priority_class_value > 1000
            and not workload.has_pdb):
        conflicts += 1

    return conflicts >= 2


# ---------------------------------------------------------------------------
# Task 1.2a (additional) — compute_workload_age helper
# ---------------------------------------------------------------------------

def compute_workload_age(creation_timestamp: datetime) -> Tuple[float, float]:
    """
    Compute workload age from K8s creationTimestamp.
    K8s timestamps are always UTC. We return (hours, days).

    NEVER use datetime.now() — UTC only.
    """
    now = utc_now()
    # Ensure creation_timestamp is timezone-aware
    if creation_timestamp.tzinfo is None:
        creation_timestamp = creation_timestamp.replace(tzinfo=timezone.utc)
    delta = now - creation_timestamp
    hours = delta.total_seconds() / 3600
    days = delta.total_seconds() / 86400
    return hours, days


# ---------------------------------------------------------------------------
# Task 1.9 — Input hashing (forward declared here; used by Task 1.13)
# ---------------------------------------------------------------------------

def compute_input_hash(workload: WorkloadInput) -> str:
    """
    Hash the slow-changing, classification-relevant fields of WorkloadInput.
    Excludes frequently-changing fields (replicas, ready_replicas, stable_for_minutes)
    to avoid unnecessary DB writes on every pod restart.

    Returns: "sha256:<hex>" string.
    """
    fields = {
        "namespace": workload.namespace,
        "controller_kind": workload.controller_kind,
        "priority_class": workload.priority_class,
        "has_pdb": workload.has_pdb,
        "pdb_max_unavailable": workload.pdb_max_unavailable,
        "has_topology_spread": workload.has_topology_spread,
        "has_pod_anti_affinity": workload.has_pod_anti_affinity,
        "service_type": workload.service_type,
        "has_ingress": workload.has_ingress,
        "data_safety": workload.data_safety,
        "has_pvc": workload.has_pvc,
        "owner_labels": sorted((workload.owner_labels or {}).items()),
    }
    payload = json.dumps(fields, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def should_write(
    new: WorkloadClassification,
    prev: Optional[WorkloadClassification],
) -> bool:
    """
    DB write suppression — only write when something meaningful changed.
    Per spec Section 5.6: skip if input_hash matches AND no meaningful delta.

    IMPORTANT: hash match only short-circuits when output fields are ALSO unchanged.
    A scoring-logic fix (e.g. is_spot_friendly rule change) can produce a different
    spot_friendly even with the same inputs — the hash alone is not sufficient to
    suppress the write in that case.
    """
    if prev is None:
        return True  # First time — always write

    score_delta = (
        abs(new.spot_score - prev.spot_score)
        + abs(new.criticality_score - prev.criticality_score)
    )
    spot_changed = new.spot_friendly != prev.spot_friendly
    tier_changed = new.tier != prev.tier
    state_changed = new.confidence_state != prev.confidence_state
    az_changed = getattr(new, 'az_spread_required', False) != getattr(prev, 'az_spread_required', False)
    disruption_changed = getattr(new, 'disruption_safe', False) != getattr(prev, 'disruption_safe', False)

    output_changed = score_delta >= 1 or spot_changed or tier_changed or state_changed or az_changed or disruption_changed

    # If hash matches AND no output changed → safe to suppress
    if new.input_hash and new.input_hash == prev.input_hash and not output_changed:
        return False

    return output_changed


# ---------------------------------------------------------------------------
# Task 1.10 (forward) — Redis key helpers
# See redis_keys.py for full registry; helpers used throughout this file.
# ---------------------------------------------------------------------------

def wie_classification_key(cluster_id: str, ns: str, ctrl: str) -> str:
    return f"spot:wie:classification:{cluster_id}:{ns}/{ctrl}"


def wie_pod_state_key(cluster_id: str, ns: str, ctrl: str) -> str:
    return f"spot:wie:pod_state:{cluster_id}:{ns}/{ctrl}"


def wie_override_key(cluster_id: str, workload_id: str) -> str:
    return f"spot:wie:override:{cluster_id}:{workload_id}"


def wie_circuit_breaker_key(cluster_id: str) -> str:
    return f"spot:wie:circuit_breaker:{cluster_id}"


def wie_engine_age_key(cluster_id: str) -> str:
    return f"spot:wie:engine_age:{cluster_id}"


def wie_debounce_key(cluster_id: str, workload_id: str) -> str:
    return f"spot:wie:debounce:{cluster_id}:{workload_id}"


def wie_rate_limit_key(cluster_id: str) -> str:
    return f"spot:wie:rate_limit:{cluster_id}"


def wie_metrics_key(cluster_id: str) -> str:
    return f"spot:wie:metrics:{cluster_id}"


def wie_prev_scores_key(cluster_id: str) -> str:
    return f"spot:wie:prev_scores:{cluster_id}"


# ---------------------------------------------------------------------------
# Task 1.3 — Scoring functions
# ---------------------------------------------------------------------------

def get_system_namespaces(cluster_id: str, redis) -> Set[str]:
    """
    Load per-cluster system namespace set.
    Fallback chain: Redis override → DEFAULT_SYSTEM_NAMESPACES.
    """
    key = f"spot:wie:system_namespaces:{cluster_id}"
    cached = redis.get(key) if redis else None
    if cached:
        try:
            return set(json.loads(cached))
        except (json.JSONDecodeError, TypeError):
            pass
    return set(DEFAULT_SYSTEM_NAMESPACES)


def determine_role(
    workload: WorkloadInput,
    system_namespaces: Optional[Set[str]] = None,
) -> str:
    """
    Classify workload role: SYSTEM | CONTROL_PLANE | APPLICATION

    SYSTEM:        DaemonSet, system namespace, system priority class
    CONTROL_PLANE: High-priority non-DaemonSet system components
                   (kube-controller-manager, scheduler, etcd)
    APPLICATION:   Everything else
    """
    if system_namespaces is None:
        system_namespaces = DEFAULT_SYSTEM_NAMESPACES

    # DaemonSet — always SYSTEM, runs on every node
    if workload.controller_kind == "DaemonSet":
        return "SYSTEM"

    # System namespace — always SYSTEM
    if workload.namespace in system_namespaces:
        return "SYSTEM"

    # System priority class — SYSTEM or CONTROL_PLANE
    if workload.priority_class in SYSTEM_PRIORITY_CLASSES:
        # Distinguish control plane components by name patterns
        ctrl_plane_names = {
            "kube-controller-manager", "kube-scheduler", "etcd",
            "kube-apiserver", "cloud-controller-manager",
        }
        if workload.name in ctrl_plane_names:
            return "CONTROL_PLANE"
        return "SYSTEM"

    # Check labels for operator-managed system components
    if workload.owner_labels.get("app.kubernetes.io/component") in {
        "controller-manager", "scheduler", "etcd", "apiserver",
    }:
        return "CONTROL_PLANE"

    return "APPLICATION"


def compute_criticality(
    workload: WorkloadInput,
    role: str,
    system_namespaces: Optional[Set[str]] = None,
) -> int:
    """
    Compute criticality score 0–10.

    Starting point: 5 (average)
    Adjustments based on:
      - Role (SYSTEM → 10, CONTROL_PLANE → 9)
      - Priority class value
      - PDB strictness (pdb_max_unavailable == 0)
      - External exposure (LoadBalancer / Ingress)
      - Hub detection (many inbound services)
      - Data safety (stateful → high criticality)
      - Singleton pattern (replicas == 1 with exposure)
    """
    if system_namespaces is None:
        system_namespaces = DEFAULT_SYSTEM_NAMESPACES

    # SYSTEM and CONTROL_PLANE are always maximally critical
    if role == "SYSTEM":
        return 10
    if role == "CONTROL_PLANE":
        return 9

    score = 5  # baseline for APPLICATION

    # ── Priority class boost ─────────────────────────────────────────────────
    if workload.priority_class_value is not None:
        if workload.priority_class_value >= 10000:
            score += 3
        elif workload.priority_class_value >= 1000:
            score += 2
        elif workload.priority_class_value >= 100:
            score += 1

    # ── PDB strictness boost ─────────────────────────────────────────────────
    if workload.has_pdb:
        if workload.pdb_max_unavailable == 0:
            score += 2  # strict PDB — operator declared zero-downtime requirement
        else:
            score += 1  # PDB exists but allows some disruption

    # ── External exposure boost ──────────────────────────────────────────────
    if workload.service_type == "LoadBalancer" or workload.has_ingress:
        score += 2  # externally reachable — user-facing traffic
    elif workload.service_type == "NodePort":
        score += 1

    # ── Hub detection (many inbound services routes) ─────────────────────────
    # Gate: >= 2 inbound services required before applying hub penalty
    if workload.inbound_services >= 5:
        score += 2  # central hub — many consumers depend on this
    elif workload.inbound_services >= 3:
        score += 1

    # ── Stateful data safety boost ───────────────────────────────────────────
    if workload.data_safety == "STATEFUL":
        score += 2
    elif workload.data_safety == "CACHE":
        score += 1  # cache miss on eviction hurts downstream

    # ── Singleton with external exposure — high blast radius ─────────────────
    # Gate: >= 2 inbound services required (per reviewer feedback)
    if (workload.replicas == 1
            and workload.inbound_services >= 2
            and (workload.service_type in ("LoadBalancer", "NodePort") or workload.has_ingress)):
        score += 1

    return max(0, min(10, score))


# Operator-managed quorum systems — never spot-safe regardless of replica count or PDB
_QUORUM_APP_TYPES: frozenset = frozenset({
    "postgresql", "mysql", "oracle", "sqlserver", "mongodb",
    "cassandra", "elasticsearch", "etcd", "zookeeper",
    "kafka",  # Kafka leader election makes spot eviction very expensive
})


def _is_stateful_spot_safe(workload: WorkloadInput) -> bool:
    """
    Stateful workloads can run on spot only when strong resilience signals exist.

    Hard block: operator-managed quorum systems are never spot-safe regardless
    of replica count or PDB. These systems have leader re-election delays and
    split-brain risk that cannot be mitigated by infrastructure resilience alone.
    """
    # Classifier-confirmed quorum systems — hard block
    # Only apply when classifier confidence is high enough to trust the signal
    if (workload.detected_app_type in _QUORUM_APP_TYPES
            and workload.classifier_confidence >= 0.4):
        return False

    # Original structural check for non-classified stateful workloads
    return (
        workload.replicas >= 3
        and workload.has_pdb
        and workload.has_declared_spread
        and len(workload.observed_zones) >= 2
    )


def compute_spot_score(workload: WorkloadInput, role: str) -> int:
    """
    Compute spot-friendliness score 0–10.

    SYSTEM workloads = 0 always (never spot).
    Starting score varies by controller kind, then adjusted.

    Stateful cap:
      - If stateful AND strong resilience signals exist: cap at 4 (controlled allowance)
      - Otherwise: cap at 0 (not spot-safe)
    """
    # SYSTEM / CONTROL_PLANE = never spot
    if role in ("SYSTEM", "CONTROL_PLANE"):
        return 0

    # ── Base score by controller kind ────────────────────────────────────────
    base_scores = {
        "Deployment": 6,
        "ReplicaSet": 6,
        "StatefulSet": 1,   # starts at 1 — very limited spot eligibility
        "DaemonSet": 0,     # never spot (also role=SYSTEM, but belt+suspenders)
        "Job": 7,           # batch, spot-friendly by design
        "CronJob": 7,
    }
    score = base_scores.get(workload.controller_kind, 5)

    # ── Resilience gate: has_pdb + replicas >= 2 ────────────────────────────
    is_resilient = workload.has_pdb and workload.replicas >= 2
    if is_resilient:
        score += 1

    # ── Topology spread bonus ────────────────────────────────────────────────
    if workload.has_topology_spread or workload.has_pod_anti_affinity:
        score += 1

    # ── Multi-AZ bonus (requires BOTH declared + observed) ───────────────────
    if workload.has_declared_spread and len(workload.observed_zones) >= 2:
        score += 1

    # ── Readiness delay penalties / bonuses ──────────────────────────────────
    if workload.readiness_initial_delay is not None:
        if workload.readiness_initial_delay > 60:
            score -= 2  # very slow cold start — eviction recovery is expensive
        elif workload.readiness_initial_delay > 30:
            score -= 1  # slow cold start
        elif workload.readiness_initial_delay < 30:
            score += 1  # fast readiness — bounces quickly from spot eviction

    # ── Restart rate penalty ─────────────────────────────────────────────────
    if workload.restart_rate_normalized is not None:
        if workload.restart_rate_normalized > 2.0:
            score -= 2  # much worse than cluster baseline
        elif workload.restart_rate_normalized > 1.5:
            score -= 1
    else:
        # Absolute fallback (no baseline yet)
        if workload.controller_kind == "StatefulSet":
            if workload.restart_count_per_hour > 1.0:
                score -= 1
        elif workload.controller_kind in ("Deployment", "ReplicaSet"):
            if workload.restart_count_per_hour > 2.0:
                score -= 1

    # ── Outbound traffic concentration penalty (only if Istio available) ─────
    # ENFORCEMENT: when None, NO signal emitted, no score change.
    if workload.outbound_dominant_pct is not None:
        if workload.outbound_dominant_pct > 0.80:
            score -= 2  # tightly coupled to single upstream
        elif workload.outbound_dominant_pct > 0.60:
            score -= 1

    # ── Leader election guard ────────────────────────────────────────────────
    # Only 1 ready endpoint = likely leader in leader-elected workload.
    # Only apply if workload has inbound services (to distinguish from new deployments).
    if workload.ready_endpoint_count == 1 and workload.inbound_services > 0:
        score -= 2  # leader eviction = service disruption

    # ── CronJob duration heuristic ───────────────────────────────────────────
    # Long-running CronJobs are riskier on spot (mid-run eviction = full restart)
    # Reduce reliance on duration; annotation override preferred.
    if (workload.controller_kind == "CronJob"
            and workload.current_run_minutes is not None
            and workload.current_run_minutes > 120):
        score -= 1

    # ── Stateful cap (controlled allowance) ──────────────────────────────────
    if workload.data_safety == "STATEFUL":
        if _is_stateful_spot_safe(workload):
            score = min(score, 2)  # cap at 2 — matches compute_spot_score_with_signals prod path
        else:
            score = min(score, 0)

    return max(0, min(10, score))


def is_spot_friendly(spot_score: int, workload: WorkloadInput) -> bool:
    """
    Spot-friendly requires an explicit resilience signal.

    Rule S — Stateful-spot-safe: _is_stateful_spot_safe() + score >= 2 (cap matches prod path).

    Rule A — Resilient workloads:
      - spot_score >= 4 AND (PDB exists) AND (replicas >= 2)

    Rule B — Stateless Deployments (no PDB required):
      - spot_score >= 6 AND data_safety == EPHEMERAL
        AND controller_kind in (Deployment, ReplicaSet)
      Brief downtime during eviction is acceptable; not stateful, no quorum risk.
    """
    # Rule S: stateful workloads that pass the safety gate
    if workload.data_safety == "STATEFUL" and _is_stateful_spot_safe(workload) and spot_score >= 2:
        return True

    has_resilience_signal = workload.has_pdb and workload.replicas >= 2
    is_stateless_spot_ready = (
        workload.data_safety == "EPHEMERAL"
        and workload.controller_kind in ("Deployment", "ReplicaSet")
        and spot_score >= 6
    )
    return spot_score >= 4 and (has_resilience_signal or is_stateless_spot_ready)


_DB_APP_MARKERS: frozenset = frozenset({
    "redis", "postgres", "postgresql", "mysql", "mariadb",
    "mongodb", "mongo", "elasticsearch", "kafka", "zookeeper",
    "cassandra", "etcd", "memcached",
})

# Orchestration / infrastructure controllers that must anchor on OD.
# These are single-source-of-truth controllers — eviction = cluster-wide failure.
_ANCHOR_WORKLOAD_PATTERNS: frozenset = frozenset([
    "karpenter", "cluster-autoscaler", "argocd", "argo-cd",
    "flux", "helm-controller", "kustomize-controller", "source-controller",
    "notification-controller", "image-reflector", "image-automation",
    "cert-manager", "external-secrets", "vault-agent-injector",
    "istiod", "istio-pilot", "linkerd-controller", "cilium-operator",
    "prometheus-operator", "grafana-operator", "victoriametrics-operator",
    "coredns", "aws-load-balancer-controller", "ingress-nginx",
    "velero", "crossplane", "cluster-api",
])


def _is_anchor_workload(name: str, detected_app_type: str = "") -> bool:
    """True when the workload is an infrastructure orchestration controller."""
    name_lower = (name or "").lower()
    app_lower  = (detected_app_type or "").lower()
    return any(p in name_lower or p in app_lower for p in _ANCHOR_WORKLOAD_PATTERNS)


def compute_spot_distribution(
    workload: WorkloadInput,
    classification: "WorkloadClassification",
) -> Tuple[int, int]:
    """
    Returns (min_on_demand_replicas, max_spot_replicas).

    Translates workload resilience signals into concrete numeric targets for
    the Pod Placement Engine. WIE acts as a constraint generator, not a binary gate.

    Priority order:
      1. Singleton (replicas <= 1) → always full OD — zero-redundancy hard block.
      2. SYSTEM / CONTROL_PLANE role → full OD — never touched by PPE.
      3. DB/Redis app type or PVC → full OD — data safety hard block.
      4. STATEFUL → strict rules based on PDB and resilience.
      5. replicas == 2 + no PDB → single OD anchor, 1 spot.
      6. No PDB → conservative: 1 OD anchor, rest spot.
      7. With PDB → PDB min-available becomes the OD floor.
    """
    replicas = workload.replicas

    # ── Hard block: singleton ────────────────────────────────────────────────
    if replicas <= 1:
        return 1, 0

    # ── SYSTEM / CONTROL_PLANE: never place on spot ──────────────────────────
    if classification.role in ("SYSTEM", "CONTROL_PLANE"):
        return replicas, 0

    # ── Anchor workloads (orchestration controllers) ───────────────────────────
    # e.g. Karpenter, ArgoCD controller, Flux, cert-manager — same criticality as DB.
    # Single replica: always full OD (no redundancy, eviction = cluster-wide failure).
    # Multiple replicas: keep 1 safe OD anchor + allow rest on spot (HA argo/karpenter).
    if _is_anchor_workload(workload.name, workload.detected_app_type or ""):
        if replicas == 1:
            return 1, 0
        return 1, replicas - 1

    # ── Hard block: DB/data-store app types — ALWAYS full OD, no exceptions ─
    # Any workload whose detected_app_type is a stateful data store must never
    # land on spot. This is not configurable via override.
    _detected = (workload.detected_app_type or "").lower()
    if any(m in _detected for m in _DB_APP_MARKERS) or workload.has_pvc:
        return replicas, 0

    # ── STATEFUL workloads (StatefulSet without DB markers) ──────────────────
    # Rule: 50% OD floor (ceil), 50% spot ceiling (floor). Resilience guard first.
    if workload.data_safety == "STATEFUL" or workload.controller_kind == "StatefulSet":
        if not _is_stateful_spot_safe(workload):
            return replicas, 0
        min_od = math.ceil(replicas * 0.5)
        max_spot = replicas - min_od
        return min_od, max(0, max_spot)

    # ── STATELESS workloads (Deployment, ReplicaSet, no PVC, no stateful markers) ─
    if workload.controller_kind in ("Deployment", "ReplicaSet"):
        is_resilient = workload.has_pdb and replicas >= 2
        if is_resilient:
            # All pods are spot-eligible: PDB guarantees quorum during evictions.
            # min_od=0 → FULLY SPOT in UI.
            return 0, replicas
        else:
            # No PDB: keep a 20% OD safety floor (at least 1) → PARTIALLY SPOT.
            min_od = max(1, math.ceil(replicas * 0.2))
            return min_od, max(0, replicas - min_od)

    # ── MIXED / unknown → use cluster placement_policy ratios ────────────────
    # Conservative fallback: 1 OD anchor + rest spot if PDB present, else full OD.
    if not workload.has_pdb:
        return replicas, 0
    if workload.pdb_min_available is not None:
        min_od = workload.pdb_min_available
    else:
        min_od = max(1, replicas // 2)

    max_spot = replicas - min_od
    return min_od, max(0, max_spot)


def compute_confidence(workload: WorkloadInput) -> int:
    """
    Compute confidence score 1–10.
    Starts at 8, penalized for unreliable signals.

    This score reflects HOW MUCH the engine trusts its own classification,
    not how good the workload is.
    """
    score = 8  # start with "good enough" baseline

    # ── Metrics staleness penalty ────────────────────────────────────────────
    # Missing metrics are treated as neutral (no penalty). Only explicit staleness
    # (minutes value present and beyond thresholds) is penalized.
    if (
        workload.metrics_stale_minutes is not None
        and workload.metrics_stale_minutes < METRICS_ABSENT_VALUE
        and workload.metrics_stale_minutes > 20
    ):
        score -= 3
    elif (
        workload.metrics_stale_minutes is not None
        and workload.metrics_stale_minutes < METRICS_ABSENT_VALUE
        and workload.metrics_stale_minutes > 10
    ):
        score -= 2

    # Missing critical fields are treated as neutral (no penalty).

    # ── Conflicting signals penalty ──────────────────────────────────────────
    if workload.conflicting_signals:
        score -= 2

    # ── New workload penalty (< 24h old) ─────────────────────────────────────
    if workload.workload_age_hours < 24:
        score -= 2
    elif workload.workload_age_hours < 72:
        score -= 1

    # ── Instability penalty ──────────────────────────────────────────────────
    if workload.last_restart_reason in ("CrashLoopBackOff", "OOMKilled"):
        score -= 1  # actively unhealthy workload

    # ── Multi-AZ confidence boost ────────────────────────────────────────────
    # Only when BOTH declared spread AND multiple observed zones
    if workload.has_declared_spread and len(workload.observed_zones) >= 2:
        score += 1

    return max(1, min(10, score))


def compute_confidence_state(confidence: int) -> str:
    """
    Map confidence score to state string.
    DRAFT       < 5  — engine observing, no actions permitted
    PROVISIONAL 5–7  — suggestions only
    CONFIRMED   ≥ 8  — full automation permitted
    """
    if confidence < CONFIDENCE_THRESHOLD_DRAFT:
        return "DRAFT"
    elif confidence < CONFIDENCE_THRESHOLD_PROVISIONAL:
        return "PROVISIONAL"
    else:
        return "CONFIRMED"


def derive_az_spread_required(workload: WorkloadInput) -> bool:
    """
    True when this workload has declared it must be spread across zones AND
    is currently observed across >= 2 zones.

    Derivation:
    - has_declared_spread: topology spread constraints OR pod anti-affinity
      (declared = scheduler is actively enforcing zone separation)
    - observed_zones >= 2: pods are actually in multiple zones right now
    Both must be true — declared spread with all pods in one zone is a
    misconfiguration, not a guarantee.

    Used by: Phase 2 placement advisor to determine if zone spread constraints
    must be applied to NodePool and pod affinity rules.
    """
    return workload.has_declared_spread and len(workload.observed_zones) >= 2


def derive_disruption_safe(workload: WorkloadInput) -> bool:
    """
    True when it is safe to remove exactly one pod from this workload right now.

    Three conditions must all hold:
    1. ready_replicas - 1 >= pdb_min_available (removal respects PDB)
       If no PDB: ready_replicas >= 2 (at least one pod survives)
    2. stable_for_minutes >= 30 (no recent churn — workload is settled)
    3. replicas >= 2 (a singleton cannot lose any pod safely)

    This does NOT account for traffic skew.
    Used by: Phase 2 rollout engine to decide whether to proceed to the next
    pod in a controlled rolling restart.
    """
    if workload.replicas < 2:
        return False
    if workload.stable_for_minutes < 30:
        return False
    if workload.ready_replicas is None:
        return False
    if workload.has_pdb and workload.pdb_min_available is not None:
        return (workload.ready_replicas - 1) >= workload.pdb_min_available
    return workload.ready_replicas >= 2


def get_confidence_state_with_coldstart(
    confidence: int,
    cluster_engine_age_hours: float,
) -> str:
    """
    Cold start protection: if engine has been running for less than 24h,
    cap confidence state at PROVISIONAL even if score would give CONFIRMED.

    This prevents the engine from acting on insufficient observation time.
    """
    state = compute_confidence_state(confidence)
    if cluster_engine_age_hours < COLD_START_HOURS and state == "CONFIRMED":
        return "PROVISIONAL"
    return state


def order_for_evaluation(
    workloads: List[WorkloadInput],
    prev_scores: Dict[str, int],
) -> List[WorkloadInput]:
    """
    Sort workloads by previous criticality score (highest first).
    Not a correctness requirement — a performance/priority optimization.
    """
    return sorted(
        workloads,
        key=lambda w: prev_scores.get(w.workload_id, 0),
        reverse=True,
    )


def get_prev_scores(cluster_id: str, redis, db) -> Dict[str, int]:
    """
    Load previous criticality scores for evaluation ordering.
    Fallback chain: Redis → DB → empty dict (natural order = acceptable).
    """
    from backend.models.workload_classification import WorkloadClassificationRecord

    # 1. Redis (fast, TTL 15 min)
    cached = redis.get(wie_prev_scores_key(cluster_id))
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. DB fallback
    try:
        rows = (
            db.query(
                WorkloadClassificationRecord.workload_id,
                WorkloadClassificationRecord.criticality_score,
            )
            .filter_by(cluster_id=cluster_id)
            .all()
        )
        if rows:
            scores = {r.workload_id: r.criticality_score for r in rows}
            redis.setex(
                wie_prev_scores_key(cluster_id),
                900,
                json.dumps(scores),
            )
            return scores
    except Exception as e:
        logger.warning("get_prev_scores_db_error", cluster_id=cluster_id, error=str(e))

    return {}


# ---------------------------------------------------------------------------
# Task 1.11 — Cold start engine age tracking
# ---------------------------------------------------------------------------

def get_cluster_engine_age_hours(cluster_id: str, redis) -> float:
    """
    Return how many hours the engine has been observing this cluster.
    Uses SETNX — first run sets the key; subsequent calls read it.
    Key never expires (no TTL) — persists across backend restarts.
    """
    key = wie_engine_age_key(cluster_id)
    existing = redis.get(key)
    if existing:
        try:
            started_str = existing.decode() if isinstance(existing, bytes) else existing
            started = datetime.fromisoformat(started_str)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            delta = utc_now() - started
            return delta.total_seconds() / 3600
        except (ValueError, TypeError):
            pass

    # First observation — set the timestamp via SETNX
    now_iso = utc_now_iso()
    redis.setnx(key, now_iso)
    return 0.0


# ---------------------------------------------------------------------------
# Task 1.2 — Staleness penalty (applied in orchestrator before cold start)
# ---------------------------------------------------------------------------

def apply_staleness_penalty(
    workload: WorkloadInput,
    confidence: int,
) -> Tuple[int, Optional[str]]:
    """
    Apply confidence penalty for absent or very stale metrics.
    Called as Step 4a in classify_workload(), BEFORE cold start check.

    Returns (adjusted_confidence, state_override_or_None).
    state_override="DRAFT" means force DRAFT regardless of score.
    """
    stale = workload.metrics_stale_minutes

    # Missing metrics are treated as neutral (no forced DRAFT, no penalty).
    if stale >= METRICS_FORCE_DRAFT_THRESHOLD:
        return confidence, None

    if stale >= METRICS_STALE_THRESHOLD_MINUTES:
        penalty = min(3, stale // 60)  # -1 per hour stale, cap at -3
        confidence = max(1, confidence - penalty)
        return confidence, None

    return confidence, None


# ---------------------------------------------------------------------------
# Task 1.12 — Override system
# ---------------------------------------------------------------------------

OVERRIDE_ANNOTATIONS = {
    "spot_override": "aura.io/spot-override",    # "true" | "false"
    "tier_override": "aura.io/tier-override",     # Platinum | Gold | Silver | Bronze
    "role_override": "aura.io/role-override",     # APPLICATION (only allowed override)
}


def _load_override(cluster_id: str, workload_id: str, redis) -> Optional[Dict[str, Any]]:
    """
    Load active override from Redis. Returns None if no override or TTL expired.
    """
    key = wie_override_key(cluster_id, workload_id)
    raw = redis.get(key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        # Check expires_at if present
        expires_at = data.get("expires_at")
        if expires_at:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if utc_now() > exp:
                redis.delete(key)
                return None
        return data
    except (json.JSONDecodeError, TypeError):
        return None


def _validate_override_safety(
    workload: WorkloadInput,
    classification: WorkloadClassification,
    override: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Validate that the requested override does not violate safety invariants.
    Returns (is_safe, rejection_reason).
    """
    spot_override = override.get("spot_override")
    tier_override = override.get("tier_override")

    # Cannot force STATEFUL workload to spot unless strong resilience signals exist
    if spot_override is True and workload.data_safety == "STATEFUL" and not _is_stateful_spot_safe(workload):
        return False, "Cannot force STATEFUL workload to spot without strong resilience signals"

    # Cannot force singleton to spot — no resilience possible with 1 replica
    if spot_override is True and workload.replicas == 1:
        return False, "Cannot force singleton (replicas=1) to spot — guaranteed outage on eviction"

    # Cannot override SYSTEM role tier (these are always system-critical)
    if tier_override and classification.role == "SYSTEM":
        return False, "Cannot override tier for SYSTEM role workloads"

    return True, None


def apply_overrides(
    workload: WorkloadInput,
    classification: WorkloadClassification,
    redis=None,
) -> WorkloadClassification:
    """
    Apply active overrides from:
    1. Redis (runtime overrides via API — takes priority)
    2. K8s annotations (aura.io/* annotations on the controller)

    Overrides are bounded — safety invariants always win.
    Simulation mode: overrides are skipped entirely.
    """
    if classification.is_simulation:
        return classification  # never apply overrides in simulation

    # ── Redis override (API-set, highest priority) ───────────────────────────
    override_data = None
    if redis:
        override_data = _load_override(workload.cluster_id, workload.workload_id, redis)

    # ── Annotation override (K8s-native, lower priority) ─────────────────────
    if not override_data:
        ann = workload.annotations or {}
        if OVERRIDE_ANNOTATIONS["spot_override"] in ann or OVERRIDE_ANNOTATIONS["tier_override"] in ann:
            spot_ann = ann.get(OVERRIDE_ANNOTATIONS["spot_override"])
            tier_ann = ann.get(OVERRIDE_ANNOTATIONS["tier_override"])
            override_data = {}
            if spot_ann is not None:
                override_data["spot_override"] = spot_ann.lower() == "true"
            if tier_ann:
                override_data["tier_override"] = tier_ann

    if not override_data:
        return classification

    # ── Safety validation before applying ────────────────────────────────────
    is_safe, reason = _validate_override_safety(workload, classification, override_data)
    if not is_safe:
        logger.warning(
            "override_rejected",
            workload_id=workload.workload_id,
            reason=reason,
            override=override_data,
        )
        classification.signals_fired.append(f"override_rejected:{reason}")
        return classification

    # ── Apply override ────────────────────────────────────────────────────────
    spot_override = override_data.get("spot_override")
    tier_override = override_data.get("tier_override")

    if spot_override is True:
        classification.spot_friendly = True
        classification.signals_fired.append("manual_override:spot=true")
    elif spot_override is False:
        classification.spot_friendly = False
        classification.signals_fired.append("manual_override:spot=false")

    if tier_override:
        classification.tier = tier_override
        classification.signals_fired.append(f"manual_override:tier={tier_override}")

    classification.override_active = True
    classification.override_reason = override_data.get("reason", "operator override")

    return classification


# ---------------------------------------------------------------------------
# Task 1.14a — Pipeline exit safety gates
# ---------------------------------------------------------------------------

def enforce_safety_invariants(
    workload: WorkloadInput,
    classification: WorkloadClassification,
) -> WorkloadClassification:
    """
    Hard invariants that NOTHING can violate — not scoring, not overrides.
    Runs as Step 8 (after overrides, before confidence gate).
    Catches unsafe spot_friendly=True from any source: scoring bugs, weight
    edge cases, or overrides that slipped through.
    """
    override_requested_spot = any(
        s == "manual_override:spot=true" for s in classification.signals_fired
    )
    blocked = False

    # Stateful workloads may only be spot-friendly when strong resilience signals exist
    if workload.data_safety == "STATEFUL" and classification.spot_friendly and not _is_stateful_spot_safe(workload):
        classification.spot_friendly = False
        classification.max_spot_replicas = 0
        classification.min_on_demand_replicas = workload.replicas
        classification.workload_class = "stateful"
        blocked = True
        classification.signals_fired.append("override_blocked:stateful_without_resilience")

    # ── Singleton hard block ───────────────────────────────────────────────────
    # replicas == 1 is NEVER safe for spot regardless of data_safety or override.
    # Ephemeral singletons have zero redundancy — eviction causes guaranteed downtime.
    # Catches overrides that slipped through _validate_override_safety().
    if workload.replicas == 1 and classification.spot_friendly:
        classification.spot_friendly = False
        classification.max_spot_replicas = 0
        classification.min_on_demand_replicas = 1
        blocked = True
        classification.signals_fired.append("invariant_blocked:singleton_never_spot")

    # Signal reconciliation — track when override intent was blocked
    if override_requested_spot and blocked:
        classification.signals_fired.append("override_effective:false")

    return classification


def enforce_confidence(classification: WorkloadClassification) -> WorkloadClassification:
    """
    Confidence gate now only controls automation, not classification truth.
    Keep spot_friendly as the computed suitability signal for UI/analysis,
    while action paths must still require CONFIRMED via can_act()/is_spot_eligible().
    """
    return classification


# ---------------------------------------------------------------------------
# Task 1.15 — can_act / can_suggest
# ---------------------------------------------------------------------------

def can_act(classification: WorkloadClassification) -> bool:
    """True only for CONFIRMED classifications. Required for any automated action."""
    return classification.confidence_state == "CONFIRMED"


def can_suggest(classification: WorkloadClassification) -> bool:
    """True for PROVISIONAL or CONFIRMED. Used for UI suggestions only."""
    return classification.confidence_state in ("PROVISIONAL", "CONFIRMED")


# ---------------------------------------------------------------------------
# Task 1.16 — No-guessing enforcement
# ---------------------------------------------------------------------------

def validate_no_synthetic_defaults(workload: WorkloadInput) -> None:
    """
    Log a warning when numeric fields are exactly 0 in a way that looks suspicious.
    The engine NEVER synthesizes data — it emits warnings and lets the signal be absent.

    This catches silent collection bugs where a field was not collected but
    defaulted to 0 (e.g., inbound_services=0 meaning "not collected" vs "truly 0").
    """
    suspect_fields = {
        "restart_count_per_hour": workload.restart_count_per_hour,
        "inbound_services": workload.inbound_services,
        "ready_endpoint_count": workload.ready_endpoint_count,
    }
    for fname, val in suspect_fields.items():
        if val == 0:
            logger.debug(
                "zero_field_check",
                workload_id=workload.workload_id,
                field=fname,
                note="Value is 0 — verify this is genuine, not a collection gap",
            )


# ---------------------------------------------------------------------------
# Task 1.26 — Signals completeness validation
# ---------------------------------------------------------------------------

REQUIRED_SIGNAL_GROUPS = {
    "role": lambda s: any(x.startswith("role:") for x in s),
    "tier": lambda s: any(x.startswith("tier:") or x.startswith("criticality:") for x in s),
    "spot_friendly": lambda s: any(x.startswith("spot_friendly:") or x.startswith("spot:") for x in s),
}


def validate_signals_completeness(signals: List[str]) -> None:
    """
    Validate that the scoring pipeline produced a minimum signal set.
    Each required group must have at least one signal.

    Raises ValueError if any group is missing — indicates a bug in the pipeline.
    """
    if len(signals) < MIN_EXPECTED_SIGNALS:
        raise ValueError(
            f"Signals completeness check failed: only {len(signals)} signals emitted "
            f"(minimum {MIN_EXPECTED_SIGNALS}). Signals: {signals}. "
            f"This indicates a bug in the scoring pipeline."
        )

    for group_name, check_fn in REQUIRED_SIGNAL_GROUPS.items():
        if not check_fn(signals):
            raise ValueError(
                f"Missing required signal group '{group_name}'. "
                f"Every classification must include role, tier, and spot_friendly signals. "
                f"Got: {signals}"
            )


# ---------------------------------------------------------------------------
# Task 1.14 — Signals traceability: _with_signals variants
# ---------------------------------------------------------------------------

def determine_role_with_signals(
    workload: WorkloadInput,
    system_namespaces: Optional[Set[str]] = None,
) -> Tuple[str, List[str]]:
    """determine_role() + signal emission."""
    role = determine_role(workload, system_namespaces)
    signals = [f"role:{role}"]
    if workload.controller_kind == "DaemonSet":
        signals.append("role_reason:daemonset")
    elif workload.namespace in (system_namespaces or DEFAULT_SYSTEM_NAMESPACES):
        signals.append("role_reason:system_namespace")
    elif workload.priority_class in SYSTEM_PRIORITY_CLASSES:
        signals.append("role_reason:system_priority_class")
    return role, signals


def compute_criticality_with_signals(
    workload: WorkloadInput,
    role: str,
    system_namespaces: Optional[Set[str]] = None,
) -> Tuple[int, List[str]]:
    """compute_criticality() + signal emission for each scoring branch."""
    signals = []

    if role == "SYSTEM":
        return 10, ["criticality:10", "criticality_reason:system_role"]
    if role == "CONTROL_PLANE":
        return 9, ["criticality:9", "criticality_reason:control_plane"]

    score = 5
    signals.append("criticality_base:5")

    if workload.priority_class_value is not None:
        if workload.priority_class_value >= 10000:
            score += 3
            signals.append("priority_class_value:+3")
        elif workload.priority_class_value >= 1000:
            score += 2
            signals.append("priority_class_value:+2")
        elif workload.priority_class_value >= 100:
            score += 1
            signals.append("priority_class_value:+1")

    if workload.has_pdb:
        if workload.pdb_max_unavailable == 0:
            score += 2
            signals.append("pdb_strict:+2")
        else:
            score += 1
            signals.append("pdb_present:+1")

    if workload.service_type == "LoadBalancer" or workload.has_ingress:
        score += 2
        signals.append("external_exposure:+2")
    elif workload.service_type == "NodePort":
        score += 1
        signals.append("nodeport_exposure:+1")

    if workload.inbound_services >= 5:
        score += 2
        signals.append(f"hub_heavy:{workload.inbound_services}_services:+2")
    elif workload.inbound_services >= 3:
        score += 1
        signals.append(f"hub_moderate:{workload.inbound_services}_services:+1")

    if workload.data_safety == "STATEFUL":
        score += 2
        signals.append("stateful:+2")
    elif workload.data_safety == "CACHE":
        score += 1
        signals.append("cache:+1")

    if (workload.replicas == 1
            and workload.inbound_services >= 2
            and (workload.service_type in ("LoadBalancer", "NodePort") or workload.has_ingress)):
        score += 1
        signals.append("singleton_exposed:+1")

    final = max(0, min(10, score))
    signals.append(f"criticality:{final}")
    return final, signals


def compute_spot_score_with_signals(
    workload: WorkloadInput,
    role: str,
) -> Tuple[int, List[str]]:
    """compute_spot_score() + signal emission for each branch."""
    signals = []

    if role in ("SYSTEM", "CONTROL_PLANE"):
        return 0, ["spot_friendly:false", "spot_reason:system_role"]

    base_scores = {
        "Deployment": 6, "ReplicaSet": 6, "StatefulSet": 1,
        "DaemonSet": 0, "Job": 7, "CronJob": 7,
    }
    score = base_scores.get(workload.controller_kind, 5)
    signals.append(f"spot_base:{workload.controller_kind}:{score}")

    is_resilient = workload.has_pdb and workload.replicas >= 2
    if is_resilient:
        score += 1
        signals.append("resilience_gate:passed:+1")
    elif workload.has_pdb or workload.replicas >= 2:
        # Partial resilience — has one indicator but not both; no penalty
        signals.append("resilience_gate:partial:+0")
    else:
        # No resilience features — no penalty for ephemeral Deployments/Jobs
        signals.append("resilience_gate:none:+0")

    if workload.has_topology_spread or workload.has_pod_anti_affinity:
        score += 1
        signals.append("topology_spread:+1")

    if workload.has_declared_spread and len(workload.observed_zones) >= 2:
        score += 1
        signals.append(f"multi_az:{len(workload.observed_zones)}_zones:+1")

    if workload.readiness_initial_delay is not None:
        if workload.readiness_initial_delay > 60:
            score -= 2
            signals.append(f"slow_readiness:{workload.readiness_initial_delay}s:-2")
        elif workload.readiness_initial_delay > 30:
            score -= 1
            signals.append(f"slow_readiness:{workload.readiness_initial_delay}s:-1")
        elif workload.readiness_initial_delay < 30:
            score += 1
            signals.append(f"fast_readiness:{workload.readiness_initial_delay}s:+1")

    if workload.restart_rate_normalized is not None:
        if workload.restart_rate_normalized > 2.0:
            score -= 2
            signals.append(f"restart_rate_high:{workload.restart_rate_normalized:.1f}x:-2")
        elif workload.restart_rate_normalized > 1.5:
            score -= 1
            signals.append(f"restart_rate_elevated:{workload.restart_rate_normalized:.1f}x:-1")
    else:
        if workload.controller_kind == "StatefulSet" and workload.restart_count_per_hour > 1.0:
            score -= 1
            signals.append(f"restart_absolute:{workload.restart_count_per_hour:.1f}/hr:-1")
        elif workload.controller_kind in ("Deployment", "ReplicaSet") and workload.restart_count_per_hour > 2.0:
            score -= 1
            signals.append(f"restart_absolute:{workload.restart_count_per_hour:.1f}/hr:-1")

    # outbound_dominant_pct — ONLY emit signal when not None
    if workload.outbound_dominant_pct is not None:
        if workload.outbound_dominant_pct > 0.80:
            score -= 2
            signals.append(f"outbound_concentrated:{workload.outbound_dominant_pct:.2f}:-2")
        elif workload.outbound_dominant_pct > 0.60:
            score -= 1
            signals.append(f"outbound_concentrated:{workload.outbound_dominant_pct:.2f}:-1")

    if workload.ready_endpoint_count == 1 and workload.inbound_services > 0:
        score -= 2
        signals.append("leader_election_single_endpoint:-2")

    if (workload.controller_kind == "CronJob"
            and workload.current_run_minutes is not None
            and workload.current_run_minutes > 120):
        score -= 1
        signals.append(f"cronjob_long_running:{workload.current_run_minutes}min:-1")

    if workload.data_safety == "STATEFUL":
        if _is_stateful_spot_safe(workload):
            score = min(score, 2)
            signals.append("stateful_spot_cap:2")
        else:
            score = min(score, 0)
            signals.append("stateful_no_spot:0")

    final = max(0, min(10, score))
    spot = is_spot_friendly(final, workload)
    signals.append(f"spot_friendly:{str(spot).lower()}")
    return final, signals


# ---------------------------------------------------------------------------
# Task 1.17 — ClassificationGuard
# ---------------------------------------------------------------------------

class ClassificationGuard:
    """
    Centralized consumer guard for classification-based decisions.
    Every consumer MUST use these methods instead of raw confidence_state checks.
    Prevents any consumer from bypassing confidence gates.
    """

    @staticmethod
    def is_actionable(classification: WorkloadClassification) -> bool:
        """Can automated actions be taken on this workload?"""
        return classification.confidence_state == "CONFIRMED"

    @staticmethod
    def is_visible(classification: WorkloadClassification) -> bool:
        """Should this workload be visible in the UI at all?"""
        return True  # always visible — UI shows all states with appropriate indicators

    @staticmethod
    def is_spot_eligible(classification: WorkloadClassification) -> bool:
        """Eligibility is purely about spot suitability (no confidence gate)."""
        return bool(classification.spot_friendly)

    @staticmethod
    def is_drainable(classification: WorkloadClassification) -> bool:
        """
        Can the node hosting this workload be drained for spot migration?
        Platinum = never. Gold + not spot = needs approval. Others = safe.
        """
        if classification.confidence_state != "CONFIRMED":
            return False
        if classification.tier == "Platinum":
            return False
        if classification.tier == "Gold" and not classification.spot_friendly:
            return False
        return True

    @staticmethod
    def get_consumer_action(classification: WorkloadClassification) -> str:
        """Human-readable action string for logging/audit."""
        if classification.confidence_state == "DRAFT":
            return "IGNORE"
        if classification.confidence_state == "PROVISIONAL":
            return "SUGGEST_ONLY"
        return "ACTIONABLE"


# ---------------------------------------------------------------------------
# Task 1.18 — Simulation isolation contract
# ---------------------------------------------------------------------------

class SimulationIsolationContract:
    """
    Enforces that simulation results are never persisted or served.
    Used to validate simulation boundaries at runtime.
    """

    @staticmethod
    def assert_not_simulation(classification: WorkloadClassification, context: str) -> None:
        """Raise RuntimeError if called with a simulation result."""
        if classification.is_simulation:
            raise RuntimeError(
                f"[{context}] Simulation result must never be persisted or served. "
                f"workload_id={classification.workload_id}"
            )


def simulate_classification(
    workload: WorkloadInput,
    system_namespaces: Optional[Set[str]] = None,
) -> WorkloadClassification:
    """
    Run classification in simulation mode.
    Returns a tagged WorkloadClassification — NEVER written to DB or Redis.
    Overrides are skipped. Metrics are not emitted.
    """
    return classify_workload(workload, system_namespaces=system_namespaces, mode="simulation")


# ---------------------------------------------------------------------------
# Task 1.24 — Circuit breaker
# ---------------------------------------------------------------------------

class EngineCircuitBreaker:
    """
    Per-cluster circuit breaker. When tripped, classification loop pauses.
    Auto-resets after TTL (600s = 10 min).
    Consumers continue reading last-known-good data from Redis.
    """

    TRIP_THRESHOLD_PCT = 0.20    # >20% errors in a cycle → trip
    TRIP_TTL_SECONDS = 600       # 10 min auto-reset

    def __init__(self, cluster_id: str, redis):
        self.cluster_id = cluster_id
        self.redis = redis
        self._key = wie_circuit_breaker_key(cluster_id)

    def is_tripped(self) -> bool:
        return bool(self.redis.exists(self._key))

    def check_and_trip(self, error_count: int, total_workloads: int) -> bool:
        """Trip if error rate exceeds threshold. Returns True if tripped."""
        if total_workloads == 0:
            return False
        error_rate = error_count / total_workloads
        if error_rate > self.TRIP_THRESHOLD_PCT:
            self.redis.setex(self._key, self.TRIP_TTL_SECONDS, "1")
            logger.error(
                "circuit_breaker_tripped",
                cluster_id=self.cluster_id,
                error_rate=round(error_rate, 3),
                error_count=error_count,
                total=total_workloads,
            )
            return True
        return False

    def reset(self) -> None:
        """Manually reset the breaker."""
        self.redis.delete(self._key)
        logger.info("circuit_breaker_reset", cluster_id=self.cluster_id)


# ---------------------------------------------------------------------------
# Task 1.29 — Structured logging helpers
# ---------------------------------------------------------------------------

def log_classification_start(cluster_id: str, total: int) -> None:
    logger.info("wie_cycle_start", cluster_id=cluster_id, workload_count=total)


def log_classification_complete(
    cluster_id: str, workload_id: str, tier: str,
    confidence_state: str, spot_friendly: bool,
    duration_ms: int,
) -> None:
    logger.info(
        "wie_classification_complete",
        cluster_id=cluster_id,
        workload_id=workload_id,
        tier=tier,
        confidence_state=confidence_state,
        spot_friendly=spot_friendly,
        duration_ms=duration_ms,
    )


def log_override_applied(cluster_id: str, workload_id: str, override: Dict) -> None:
    logger.info("wie_override_applied", cluster_id=cluster_id, workload_id=workload_id, override=override)


def log_circuit_breaker_skip(cluster_id: str) -> None:
    logger.warning("wie_circuit_breaker_active", cluster_id=cluster_id)


def log_redis_write(cluster_id: str, workload_id: str, key: str) -> None:
    logger.debug("wie_redis_write", cluster_id=cluster_id, workload_id=workload_id, key=key)


def log_db_write_suppressed(cluster_id: str, workload_id: str, reason: str) -> None:
    logger.debug("wie_db_write_suppressed", cluster_id=cluster_id, workload_id=workload_id, reason=reason)


def log_pod_state_cache_miss(cluster_id: str, ns: str, ctrl: str) -> None:
    logger.warning("wie_pod_state_cache_miss", cluster_id=cluster_id, namespace=ns, controller=ctrl)


def log_stale_classification_cleanup(cluster_id: str, removed: int) -> None:
    logger.info("wie_stale_cleanup", cluster_id=cluster_id, removed=removed)


def log_graceful_degradation(cluster_id: str, mode: str, reason: str) -> None:
    logger.warning("wie_graceful_degradation", cluster_id=cluster_id, mode=mode, reason=reason)


def log_cycle_error(cluster_id: str, error: Exception) -> None:
    logger.error("wie_cycle_error", cluster_id=cluster_id, error=str(error))


def log_signal_warning(cluster_id: str, workload_id: str, warning: str) -> None:
    logger.warning("wie_signal_warning", cluster_id=cluster_id, workload_id=workload_id, warning=warning)


# ---------------------------------------------------------------------------
# Task 1.30 — Graceful degradation
# ---------------------------------------------------------------------------

class GracefulDegradation:
    """
    Handle partial failures gracefully. Engine degrades, never crashes.
    """

    SKIP_WRITES = "SKIP_WRITES"
    USE_CACHE = "USE_CACHE"
    CONTINUE = "CONTINUE"

    @staticmethod
    def handle_redis_failure(cluster_id: str, error: Exception) -> None:
        """Log Redis failure. Slow loop should skip this cycle gracefully."""
        log_graceful_degradation(cluster_id, "redis_failure", str(error))

    @staticmethod
    def handle_db_failure(cluster_id: str, error: Exception) -> None:
        """DB failure: Redis writes continue, DB writes skipped."""
        log_graceful_degradation(cluster_id, "db_failure", str(error))

    @staticmethod
    def handle_partial_k8s_failure(
        cluster_id: str,
        error_count: int,
        total_workloads: int,
        results: list,
    ) -> str:
        """
        If > 50% of workloads failed collection, skip all writes for this cycle.
        Partial results are unreliable — better to use last-known-good cache.
        """
        if total_workloads == 0:
            return GracefulDegradation.SKIP_WRITES
        failure_pct = error_count / total_workloads
        if failure_pct > 0.50:
            log_graceful_degradation(
                cluster_id,
                "partial_k8s_failure",
                f"{failure_pct:.0%} errors ({error_count}/{total_workloads})",
            )
            return GracefulDegradation.SKIP_WRITES
        return GracefulDegradation.CONTINUE


# ---------------------------------------------------------------------------
# Task 1.25 + 1.31 — API boundary confidence enforcement + serialization
# ---------------------------------------------------------------------------

SUPPORTED_SCHEMA_VERSION = SCHEMA_VERSION  # single source of truth — SCHEMA_VERSION = 4.4


def serialize_classification(classification: WorkloadClassification) -> dict:
    """
    Canonical serialization of WorkloadClassification.
    EVERY output path (Redis, API, streaming) MUST use this function.
    This is the ONLY place where the output contract is defined.
    Format drift is eliminated by using a single serializer everywhere.
    """
    return {
        "workload_id": classification.workload_id,
        "cluster_id": classification.cluster_id,
        "namespace": classification.namespace,
        "name": classification.name,
        "controller_kind": classification.controller_kind,
        "role": classification.role,
        "tier": classification.tier,
        "criticality_score": classification.criticality_score,
        "spot_score": classification.spot_score,
        "spot_friendly": classification.spot_friendly,
        "confidence": classification.confidence_score,
        "confidence_state": classification.confidence_state,
        "data_safety": classification.data_safety,
        "has_pdb": classification.has_pdb,
        "signals_fired": classification.signals_fired,
        "input_hash": classification.input_hash,
        "override_active": classification.override_active,
        "override_reason": classification.override_reason,
        "schema_version": classification.schema_version,
        "classified_at": classification.classified_at.isoformat() if classification.classified_at else None,
        "is_simulation": classification.is_simulation,
        "az_spread_required": classification.az_spread_required,
        "disruption_safe": classification.disruption_safe,
        "min_on_demand_replicas": classification.min_on_demand_replicas,
        "max_spot_replicas": classification.max_spot_replicas,
        "total_replicas": classification.total_replicas,
        "spot_eligible": classification.spot_eligible,
        "workload_class": classification.workload_class,
    }


def sanitize_classification_output(classification: dict) -> dict:
    """
    SANITIZATION CONTRACT — read before modifying this function.

    MAY do:
    - Clear placement_plan for DRAFT/PROVISIONAL (action safety, not visibility)
    - Add schema_warning field on version mismatch
    - Format fields for API serialization

    MUST NOT do:
    - Change spot_friendly (owner: WIE engine)
    - Change tier, role, confidence_state, spot_score, criticality_score
    - Apply safety logic by mutating boolean flags (that belongs in consumers)
    - Set spot_friendly=False for DRAFT/PROVISIONAL workloads

    Violation of this contract = P0 bug. See plan.md §0 Invariant 1.
    Root cause of 2026-04-21 bug: a previous version of this function was setting
    spot_friendly=False for DRAFT/PROVISIONAL. That logic was REMOVED. Do NOT re-add it.
    Confidence gating for automation safety uses is_spot_eligible() — not this function.
    """
    state = classification.get("confidence_state")
    version = classification.get("schema_version")

    # Schema version mismatch — downgrade confidence_state to DRAFT for safety.
    # spot_friendly is intentionally NOT overridden here: Invariant 1 forbids it.
    # confidence_state=DRAFT is sufficient to block all automation (is_spot_eligible() gates on CONFIRMED).
    if version and version != SUPPORTED_SCHEMA_VERSION:
        logger.warning(
            "schema_version_mismatch",
            got=version,
            expected=SUPPORTED_SCHEMA_VERSION,
        )
        classification["confidence_state"] = "DRAFT"
        classification["placement_plan"] = None
        classification["_schema_warning"] = f"Unsupported version {version}"
        return classification

    # Placement plan clearing for non-CONFIRMED (action safety)
    # spot_friendly is preserved as the true classification result for UI visibility.
    # Automation safety is enforced via is_spot_eligible() which requires CONFIRMED.
    if state in ("DRAFT", "PROVISIONAL"):
        classification["placement_plan"] = None

    return classification


def read_classification_from_redis(
    redis,
    cluster_id: str,
    ns: str,
    ctrl: str,
) -> Optional[dict]:
    """
    Safe Redis read with JSON validation + confidence enforcement.
    Returns None on error — caller must handle gracefully.
    """
    key = wie_classification_key(cluster_id, ns, ctrl)
    raw = redis.get(key)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("wie_corrupted_redis_json", key=key)
        redis.delete(key)
        return None

    required = {"workload_id", "confidence_state", "tier", "spot_friendly", "schema_version"}
    if not required.issubset(data.keys()):
        logger.error("wie_incomplete_classification", key=key, missing=required - data.keys())
        return None

    return sanitize_classification_output(data)


# ---------------------------------------------------------------------------
# Task 1.19 — Pod state schema versioning
# ---------------------------------------------------------------------------

POD_STATE_SCHEMA_VERSION = 1

POD_STATE_REQUIRED_FIELDS = {
    "restart_count", "restart_count_per_hour", "ready_pods",
    "total_pods", "observed_zones", "last_restart_reason",
    "stable_for_minutes", "last_updated", "schema_version",
}


def validate_pod_state(data: dict) -> bool:
    """
    Validate pod_state JSON from Redis against expected schema.
    Returns False if any required field is missing or schema version mismatch.
    """
    if not isinstance(data, dict):
        return False
    if not POD_STATE_REQUIRED_FIELDS.issubset(data.keys()):
        return False
    if data.get("schema_version") != POD_STATE_SCHEMA_VERSION:
        return False
    return True


# ---------------------------------------------------------------------------
# Task 1.13 — Main classification pipeline orchestrator
# ---------------------------------------------------------------------------

def classify_workload(
    workload: WorkloadInput,
    system_namespaces: Optional[Set[str]] = None,
    cluster_engine_age_hours: float = 0.0,
    redis=None,
    mode: str = "production",
) -> WorkloadClassification:
    """
    Single entry point for workload classification.

    Pipeline steps:
      Step 1: No-guessing check
      Step 2: Role determination
      Step 3: Criticality scoring
      Step 4: Confidence scoring
      Step 4a: Staleness penalty (MUST be before cold start)
      Step 5: Cold start enforcement
      Step 6: Spot scoring
      Step 7: Build classification object
      Step 8: Override (production mode only)
      Step 9: Post-pipeline safety invariants (always)
      Step 10: Global confidence enforcement (always, last)

    mode="simulation": overrides skipped, is_simulation=True, no writes.
    mode="production": full pipeline including overrides.
    """
    # ── Step 1: No-guessing check ──────────────────────────────────────────
    validate_no_synthetic_defaults(workload)

    # ── Step 2: Role ───────────────────────────────────────────────────────
    role, role_signals = determine_role_with_signals(workload, system_namespaces)

    # ── Step 3: Criticality → Tier ─────────────────────────────────────────
    criticality, crit_signals = compute_criticality_with_signals(workload, role, system_namespaces)
    tier = criticality_to_tier(criticality)

    # ── Step 4: Confidence ─────────────────────────────────────────────────
    confidence = compute_confidence(workload)

    # ── Step 4a: Staleness penalty (MUST be before cold start) ────────────
    confidence, staleness_override = apply_staleness_penalty(workload, confidence)

    # ── Step 5: Confidence state (with cold start enforcement) ────────────
    if staleness_override:
        confidence_state = staleness_override  # DRAFT overrides cold start
    else:
        confidence_state = get_confidence_state_with_coldstart(
            confidence, cluster_engine_age_hours
        )

    # ── Step 6: Spot score ─────────────────────────────────────────────────
    spot_score, spot_signals = compute_spot_score_with_signals(workload, role)
    spot = is_spot_friendly(spot_score, workload)

    # Aggregate signals
    signals: List[str] = []
    signals.extend(role_signals)
    signals.extend(crit_signals)
    signals.extend(spot_signals)
    signals.append(f"tier:{tier}")

    if staleness_override:
        signals.append(f"metrics_absent:force_{staleness_override}")
    elif workload.metrics_stale_minutes >= METRICS_STALE_THRESHOLD_MINUTES:
        signals.append(f"metrics_stale:{workload.metrics_stale_minutes}min")

    # ── Step 5a: Signals completeness validation ───────────────────────────
    validate_signals_completeness(signals)

    # Derive placement intent signals (C2 + C3)
    az_spread_req = derive_az_spread_required(workload)
    disruption_safe_val = derive_disruption_safe(workload)

    signals.append("az_spread_required:true" if az_spread_req else "az_spread_required:false")
    if disruption_safe_val:
        signals.append("disruption_safe:true")
    else:
        signals.append(
            f"disruption_safe:false"
            f"(stable={workload.stable_for_minutes}m,"
            f"ready={workload.ready_replicas},"
            f"replicas={workload.replicas})"
        )

    # Classifier bridge signal (C4)
    if workload.detected_app_type:
        signals.append(
            f"classifier_app_type:{workload.detected_app_type}"
            f":confidence={workload.classifier_confidence:.2f}"
        )
    else:
        signals.append("classifier_app_type:unknown")

    # ── Step 7: Build classification object ────────────────────────────────
    classification = WorkloadClassification(
        workload_id=workload.workload_id,
        cluster_id=workload.cluster_id,
        namespace=workload.namespace,
        name=workload.name,
        controller_kind=workload.controller_kind,
        role=role,
        criticality_score=criticality,
        tier=tier,
        spot_score=spot_score,
        spot_friendly=spot,
        confidence_score=confidence,
        confidence_state=confidence_state,
        data_safety=workload.data_safety,
        signals_fired=signals,
        override_active=False,
        override_reason=None,
        az_spread_required=az_spread_req,
        disruption_safe=disruption_safe_val,
        classified_at=utc_now(),
        input_hash=compute_input_hash(workload),
        schema_version=SCHEMA_VERSION,
        is_simulation=(mode == "simulation"),
    )

    # ── Step 7b: Spot distribution constraints ─────────────────────────────
    min_od, max_spot = compute_spot_distribution(workload, classification)
    # Validation: min_od + max_spot must equal total_replicas. Clamp on mismatch.
    _total = workload.replicas
    if min_od + max_spot != _total:
        logger.warning(
            "compute_spot_distribution_mismatch",
            min_od=min_od, max_spot=max_spot, replicas=_total,
            action="clamping max_spot",
        )
        max_spot = _total - min_od
    classification.min_on_demand_replicas = min_od
    classification.max_spot_replicas = max_spot
    classification.total_replicas = _total
    classification.spot_eligible = max_spot > 0
    classification.has_pdb = workload.has_pdb
    classification.signals_fired.append(f"spot_distribution:od={min_od},spot={max_spot}")

    # ── Step 7c: Derive workload_class ──────────────────────────────────────
    # Used by PPE PodSelector and Distribution Engine to select execution strategy.
    # DaemonSets and system-role workloads get class "system" — they must never
    # enter the movement plan. This is the authoritative gate; PPE and DE also
    # gate on controller_kind for defence-in-depth.
    _detected_app = (workload.detected_app_type or "").lower()
    if workload.controller_kind == "DaemonSet" or role in ("SYSTEM", "CONTROL_PLANE"):
        wclass = "system"
    elif any(m in _detected_app for m in _DB_APP_MARKERS) or workload.has_pvc:
        wclass = "db"
    elif (
        workload.data_safety == "STATEFUL"
        or workload.controller_kind == "StatefulSet"
    ):
        wclass = "stateful"
    elif _is_anchor_workload(workload.name, workload.detected_app_type or ""):
        wclass = "anchor"
    elif workload.controller_kind in ("Deployment", "ReplicaSet"):
        wclass = "stateless"
    else:
        wclass = "mixed"
    classification.workload_class = wclass
    classification.signals_fired.append(f"workload_class:{wclass}")

    # ── Step 8: Override (production mode only) ────────────────────────────
    if mode == "production":
        classification = apply_overrides(workload, classification, redis=redis)

    # ── Step 9: Post-pipeline safety invariants (ALWAYS) ──────────────────
    classification = enforce_safety_invariants(workload, classification)

    # ── Step 10: Global confidence enforcement (CRITICAL — last gate) ──────
    classification = enforce_confidence(classification)

    return classification


# ---------------------------------------------------------------------------
# Task 1.7 — Restart rate baseline
# ---------------------------------------------------------------------------

def compute_restart_baseline(
    cluster_id: str,
    controller_kind: str,
    redis,
    db,
) -> Optional[float]:
    """
    Median restart rate per hour for this (cluster, controller_kind) pair.
    Computed hourly by Celery task. Stored in Redis with 60-min TTL.

    Returns None if no data available (new cluster or first run).
    When None, callers use absolute fallback thresholds.
    """
    key = f"spot:restart_baseline:{cluster_id}:{controller_kind}"
    cached = redis.get(key)
    if cached:
        try:
            return float(cached)
        except (ValueError, TypeError):
            pass
    return None


def update_restart_baselines(cluster_id: str, redis, db) -> None:
    """
    Recompute restart rate baselines for all controller kinds in this cluster.
    Called by Celery beat task `update-restart-baseline-hourly`.
    """
    from backend.models.pod_metric import PodMetric
    from sqlalchemy import func

    kinds = ["Deployment", "StatefulSet", "ReplicaSet", "DaemonSet", "Job", "CronJob"]
    for kind in kinds:
        try:
            # Median restart rate for the last hour
            from datetime import timedelta
            one_hour_ago = utc_now() - timedelta(hours=1)

            rows = (
                db.query(PodMetric.controller_name, func.avg(PodMetric.restart_count))
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.controller_kind == kind,
                    PodMetric.timestamp >= one_hour_ago,
                )
                .group_by(PodMetric.controller_name)
                .all()
            )
            if not rows:
                continue

            rates = [float(r[1] or 0) for r in rows]
            rates.sort()
            # Median
            n = len(rates)
            median = rates[n // 2] if n % 2 == 1 else (rates[n // 2 - 1] + rates[n // 2]) / 2

            key = f"spot:restart_baseline:{cluster_id}:{kind}"
            redis.setex(key, 3600, str(median))
        except Exception as e:
            logger.warning(
                "restart_baseline_error",
                cluster_id=cluster_id,
                kind=kind,
                error=str(e),
            )


# ---------------------------------------------------------------------------
# Task 1.8 — Event debouncer + rate limiter
# ---------------------------------------------------------------------------

class EventDebouncer:
    """
    Per-workload debounce window. Collapses burst events into single recompute.
    Window is cluster-size aware per spec feedback.
    """

    def __init__(self, cluster_id: str, redis, workload_count: int = 0):
        self.cluster_id = cluster_id
        self.redis = redis
        self.window = self._compute_window(workload_count)

    @staticmethod
    def _compute_window(workload_count: int) -> int:
        if workload_count > 200:
            return 30
        elif workload_count >= 50:
            return 20
        return 15

    def should_process(self, workload_id: str) -> bool:
        """Returns True if this workload should be recomputed (not debounced)."""
        key = wie_debounce_key(self.cluster_id, workload_id)
        if self.redis.exists(key):
            return False  # within debounce window — skip
        self.redis.setex(key, self.window, "1")
        return True


class ClusterRateLimiter:
    """
    Per-cluster aggregate task rate cap.
    Prevents thundering herd from large rollouts.
    """

    MAX_RECOMPUTE_TASKS_PER_CLUSTER_PER_MINUTE = 200

    def __init__(self, cluster_id: str, redis):
        self.cluster_id = cluster_id
        self.redis = redis

    def is_allowed(self) -> bool:
        """Returns True if another task is within the rate limit."""
        key = wie_rate_limit_key(self.cluster_id)
        current = self.redis.get(key)
        count = int(current) if current else 0
        if count >= self.MAX_RECOMPUTE_TASKS_PER_CLUSTER_PER_MINUTE:
            return False
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        pipe.execute()
        return True


# ---------------------------------------------------------------------------
# Task 1.28 — Fast/slow loop snapshot consistency
# ---------------------------------------------------------------------------

def _snapshot_pod_states(cluster_id: str, redis) -> Dict[str, dict]:
    """
    Read ALL pod_state keys for this cluster in one pipeline call at cycle start.
    Returns a frozen snapshot — not affected by fast loop writes during scoring.
    Deep copy ensures no reference sharing between workload scoring calls.
    """
    pattern = f"spot:wie:pod_state:{cluster_id}:*"
    keys = redis.keys(pattern)
    if not keys:
        return {}

    pipeline = redis.pipeline()
    for key in keys:
        pipeline.get(key)
    values = pipeline.execute()

    snapshot: Dict[str, dict] = {}
    for key, raw in zip(keys, values):
        if raw:
            try:
                key_str = key.decode() if isinstance(key, bytes) else key
                data = json.loads(raw)
                if validate_pod_state(data):
                    # Key format: spot:wie:pod_state:{cluster_id}:{ns}/{ctrl}
                    suffix = key_str.split(":", 4)[-1]
                    snapshot[suffix] = copy.deepcopy(data)
                else:
                    logger.warning("wie_invalid_pod_state", key=key_str)
            except (json.JSONDecodeError, TypeError, IndexError):
                continue

    return snapshot


# ---------------------------------------------------------------------------
# Task 1.21 — Metrics staleness helper (already in apply_staleness_penalty above)
# Task 1.22 — UTC helpers (already in module header as utc_now / utc_now_iso)
# Task 1.23 — input_hash consumer patterns (documented in plan.md; helper below)
# ---------------------------------------------------------------------------

def consumer_hash_matches(
    redis,
    cluster_id: str,
    ns: str,
    ctrl: str,
    new_hash: str,
) -> bool:
    """
    Pattern 1 — write suppression: check if Redis hash matches before any work.
    Returns True if the stored hash matches new_hash (no recompute needed).
    """
    data = read_classification_from_redis(redis, cluster_id, ns, ctrl)
    if not data:
        return False
    return data.get("input_hash") == new_hash


# ---------------------------------------------------------------------------
# Task 1.27 — Override safety (already defined above as _validate_override_safety)
# Task 1.20 — Override expiry (already handled in _load_override via expires_at)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 3.3 — Engine metrics collection
# ---------------------------------------------------------------------------

def _collect_and_emit_metrics(
    cluster_id: str,
    results: List[WorkloadClassification],
    cycle_start: float,
    error_count: int,
    db_writes: int,
    db_suppressed: int,
    debounce_drops: int,
    rate_limit_drops: int,
    redis,
    enforcement_enabled: bool = False,
) -> None:
    """
    Compute and write engine health metrics at the end of each slow loop.
    Written as a Redis HASH with 1-hour TTL.
    enforcement_enabled: reflects whether WIE enforcement is active (False = observation mode).
    """
    duration_ms = int((time.monotonic() - cycle_start) * 1000)
    total = len(results)

    confirmed = sum(1 for r in results if r.confidence_state == "CONFIRMED")
    provisional = sum(1 for r in results if r.confidence_state == "PROVISIONAL")
    draft = sum(1 for r in results if r.confidence_state == "DRAFT")
    spot_count = sum(1 for r in results if r.spot_friendly)

    signal_freq: Dict[str, int] = {}
    for r in results:
        for sig in r.signals_fired:
            prefix = sig.split(":")[0]
            signal_freq[prefix] = signal_freq.get(prefix, 0) + 1

    engine_age_hours = get_cluster_engine_age_hours(cluster_id, redis)

    scan_count_key = f"spot:wie:metrics:{cluster_id}:scan_total"
    scan_total = redis.incr(scan_count_key)

    metrics_key = wie_metrics_key(cluster_id)
    redis.hset(
        metrics_key,
        mapping={
            "scan_count": scan_total,
            "last_scan_at": utc_now_iso(),
            "last_scan_duration_ms": duration_ms,
            "total_workloads": total,
            "confirmed_count": confirmed,
            "provisional_count": provisional,
            "draft_count": draft,
            "spot_friendly_count": spot_count,
            "spot_friendly_pct": round(spot_count / total, 4) if total else 0,
            "db_writes": db_writes,
            "db_suppressed": db_suppressed,
            "suppress_rate": round(
                db_suppressed / (db_writes + db_suppressed), 4
            ) if (db_writes + db_suppressed) else 0,
            "debounce_drops": debounce_drops,
            "rate_limit_drops": rate_limit_drops,
            "error_count": error_count,
            "signal_freq": json.dumps(signal_freq),
            "engine_age_hours": round(engine_age_hours, 2),
            "enforcement_enabled": int(enforcement_enabled),
        },
    )
    redis.expire(metrics_key, 3600)


# ---------------------------------------------------------------------------
# WorkloadIdentificationEngine — main class (orchestrates slow/fast loops)
# ---------------------------------------------------------------------------

class WorkloadIdentificationEngine:
    """
    Main engine class. Instantiated once per slow/fast loop invocation.
    Injected with redis, k8s_client, db — no global state.
    """

    def __init__(self, redis, db, k8s_client=None):
        self.redis = redis
        self.db = db
        self.k8s_client = k8s_client

    # ── Slow loop ─────────────────────────────────────────────────────────

    def slow_loop_classify(self, cluster_id: str) -> None:
        """
        Full classification cycle. Runs every 10 min.
        Steps:
          1. Circuit breaker check
          2. Snapshot pod_state from Redis
          3. Load prev scores for evaluation order
          4. Collect workloads
          5. Classify each workload
          6. Write to DB + Redis
          7. Emit metrics
        """
        cycle_start = time.monotonic()
        breaker = EngineCircuitBreaker(cluster_id, self.redis)

        if breaker.is_tripped():
            log_circuit_breaker_skip(cluster_id)
            return

        results: List[WorkloadClassification] = []
        error_count = 0
        db_writes = 0
        db_suppressed = 0
        debounce_drops = 0
        rate_limit_drops = 0

        # Snapshot pod states at cycle start (consistency)
        try:
            pod_state_snapshot = _snapshot_pod_states(cluster_id, self.redis)
        except Exception as e:
            GracefulDegradation.handle_redis_failure(cluster_id, e)
            return

        # Engine age
        engine_age_hours = get_cluster_engine_age_hours(cluster_id, self.redis)
        system_namespaces = get_system_namespaces(cluster_id, self.redis)

        # Load workloads (from DB / K8s — implemented in WorkloadDataCollector)
        try:
            workloads = self._collect_workloads(cluster_id, pod_state_snapshot)
        except Exception as e:
            log_cycle_error(cluster_id, e)
            GracefulDegradation.handle_partial_k8s_failure(cluster_id, 1, 1, [])
            return

        prev_scores = get_prev_scores(cluster_id, self.redis, self.db)
        ordered_workloads = order_for_evaluation(workloads, prev_scores)
        total = len(ordered_workloads)
        log_classification_start(cluster_id, total)

        for workload in ordered_workloads:
            t0 = time.monotonic()
            try:
                workload.missing_critical_fields = detect_missing_critical_fields(workload)
                workload.conflicting_signals = detect_conflicting_signals(workload)

                # Classifier bridge (C4) — run before determine_data_safety so it can use the result
                try:
                    from backend.classification.workload_classifier import classify_workload as classifier_classify
                    profile = self._build_classifier_profile(workload, pod_state_snapshot)
                    if profile:
                        classifier_result = classifier_classify(profile)
                        workload.detected_app_type = classifier_result.get("detected_app_type")
                        workload.classifier_confidence = classifier_result.get("classification_confidence", 0.0)
                except Exception as cls_err:
                    logger.warning("classifier_bridge_error", extra={"workload_id": workload.workload_id, "error": str(cls_err)})
                    workload.detected_app_type = None
                    workload.classifier_confidence = 0.0

                workload.data_safety = determine_data_safety(workload)

                classification = classify_workload(
                    workload,
                    system_namespaces=system_namespaces,
                    cluster_engine_age_hours=engine_age_hours,
                    redis=self.redis,
                    mode="production",
                )
                results.append(classification)
                duration_ms = int((time.monotonic() - t0) * 1000)
                log_classification_complete(
                    cluster_id, workload.workload_id,
                    classification.tier, classification.confidence_state,
                    classification.spot_friendly, duration_ms,
                )
            except Exception as e:
                error_count += 1
                log_cycle_error(cluster_id, e)
                if breaker.check_and_trip(error_count, total):
                    return

        # Graceful degradation: skip writes if too many errors
        action = GracefulDegradation.handle_partial_k8s_failure(
            cluster_id, error_count, total, results
        )
        if action == GracefulDegradation.SKIP_WRITES:
            return

        # Persist results
        try:
            written, suppressed = self._write_to_db(results)
            db_writes += written
            db_suppressed += suppressed
        except Exception as e:
            GracefulDegradation.handle_db_failure(cluster_id, e)

        try:
            self._write_to_redis(results)
        except Exception as e:
            GracefulDegradation.handle_redis_failure(cluster_id, e)

        # Update prev_scores cache
        new_scores = {r.workload_id: r.criticality_score for r in results}
        self.redis.setex(wie_prev_scores_key(cluster_id), 900, json.dumps(new_scores))

        # Stale classification cleanup — remove DB records for deleted workloads
        try:
            active_ids = {r.workload_id for r in results}
            self._cleanup_stale_classifications(cluster_id, active_ids)
        except Exception as e:
            logger.warning(f"wie_stale_cleanup_failed cluster_id={cluster_id} error={e}")

        # Emit metrics
        _collect_and_emit_metrics(
            cluster_id, results, cycle_start,
            error_count=error_count,
            db_writes=db_writes,
            db_suppressed=db_suppressed,
            debounce_drops=debounce_drops,
            rate_limit_drops=rate_limit_drops,
            redis=self.redis,
        )

    def _write_to_redis(self, results: List[WorkloadClassification]) -> None:
        """
        Write classifications to Redis. Last safety gate before consumers read.
        Simulation results are NEVER written.
        """
        pipeline = self.redis.pipeline()
        for classification in results:
            # Hard simulation guard
            SimulationIsolationContract.assert_not_simulation(classification, "_write_to_redis")

            data = serialize_classification(classification)
            data = sanitize_classification_output(data)

            key = wie_classification_key(
                classification.cluster_id,
                classification.namespace,
                classification.name,
            )
            pipeline.setex(key, 900, json.dumps(data))
        pipeline.execute()

    def _write_to_db(
        self,
        results: List[WorkloadClassification],
    ) -> Tuple[int, int]:
        """
        Persist classifications to DB with write suppression.
        Returns (writes, suppressed) counts.
        Simulation results are NEVER written.
        """
        from backend.models.workload_classification import WorkloadClassificationRecord

        written = 0
        suppressed = 0

        for classification in results:
            # Hard simulation guard
            SimulationIsolationContract.assert_not_simulation(classification, "_write_to_db")

            try:
                # Fetch previous record
                prev = (
                    self.db.query(WorkloadClassificationRecord)
                    .filter_by(
                        cluster_id=classification.cluster_id,
                        workload_id=classification.workload_id,
                    )
                    .first()
                )

                prev_obj = None
                if prev:
                    # Build a minimal WorkloadClassification for comparison
                    prev_obj = WorkloadClassification(
                        workload_id=prev.workload_id,
                        cluster_id=prev.cluster_id,
                        namespace=prev.namespace,
                        name=prev.name,
                        controller_kind=prev.controller_kind,
                        role=prev.role,
                        criticality_score=prev.criticality_score,
                        tier=prev.tier,
                        spot_score=prev.spot_score,
                        spot_friendly=prev.spot_friendly,
                        confidence_score=prev.confidence_score,
                        confidence_state=prev.confidence_state,
                        data_safety=prev.data_safety,
                        input_hash=prev.input_hash,
                    )

                if not should_write(classification, prev_obj):
                    log_db_write_suppressed(
                        classification.cluster_id,
                        classification.workload_id,
                        "hash_match_no_delta",
                    )
                    suppressed += 1
                    continue

                if prev:
                    prev.role = classification.role
                    prev.criticality_score = classification.criticality_score
                    prev.tier = classification.tier
                    prev.spot_score = classification.spot_score
                    prev.spot_friendly = classification.spot_friendly
                    prev.confidence_score = classification.confidence_score
                    prev.confidence_state = classification.confidence_state
                    prev.data_safety = classification.data_safety
                    prev.signals_fired = classification.signals_fired
                    prev.override_active = classification.override_active
                    prev.override_reason = classification.override_reason
                    prev.input_hash = classification.input_hash
                    prev.schema_version = classification.schema_version
                    prev.classified_at = classification.classified_at
                    prev.az_spread_required = classification.az_spread_required
                    prev.disruption_safe = classification.disruption_safe
                    prev.min_on_demand_replicas = classification.min_on_demand_replicas
                    prev.max_spot_replicas = classification.max_spot_replicas
                    prev.workload_class = classification.workload_class
                    prev.spot_eligible = classification.spot_eligible
                    prev.total_replicas = classification.total_replicas
                else:
                    record = WorkloadClassificationRecord(
                        id=str(uuid.uuid4()),
                        cluster_id=classification.cluster_id,
                        workload_id=classification.workload_id,
                        namespace=classification.namespace,
                        name=classification.name,
                        controller_kind=classification.controller_kind,
                        role=classification.role,
                        criticality_score=classification.criticality_score,
                        tier=classification.tier,
                        spot_score=classification.spot_score,
                        spot_friendly=classification.spot_friendly,
                        confidence_score=classification.confidence_score,
                        confidence_state=classification.confidence_state,
                        data_safety=classification.data_safety,
                        signals_fired=classification.signals_fired,
                        override_active=classification.override_active,
                        override_reason=classification.override_reason,
                        input_hash=classification.input_hash,
                        schema_version=classification.schema_version,
                        classified_at=classification.classified_at,
                        az_spread_required=classification.az_spread_required,
                        disruption_safe=classification.disruption_safe,
                        min_on_demand_replicas=classification.min_on_demand_replicas,
                        max_spot_replicas=classification.max_spot_replicas,
                        workload_class=classification.workload_class,
                        spot_eligible=classification.spot_eligible,
                        total_replicas=classification.total_replicas,
                    )
                    self.db.add(record)

                self.db.flush()
                written += 1
            except Exception as e:
                logger.error(
                    "wie_db_write_error",
                    workload_id=classification.workload_id,
                    error=str(e),
                )

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            GracefulDegradation.handle_db_failure("", e)

        return written, suppressed

    @staticmethod
    def _build_classifier_profile(
        workload: WorkloadInput,
        pod_state_snapshot: Dict[str, dict],
    ) -> Optional[Dict]:
        """
        Translate WorkloadInput → classifier profile dict.
        Returns None if insufficient data to run classifier (graceful skip).
        """
        pod_state = pod_state_snapshot.get(workload.workload_id, {})
        return {
            "controller_kind": workload.controller_kind,
            "namespace": workload.namespace,
            "pvc_count": 1 if workload.has_pvc else 0,
            "volume_claim_templates": (
                workload.controller_kind == "StatefulSet" and workload.has_pvc
            ),
            "keda_managed": pod_state.get("keda_managed", False),
            "scaled_object_trigger_types": pod_state.get("keda_trigger_types", []),
            "crd_owner_kind": pod_state.get("crd_owner_kind"),
            "pod_labels": workload.owner_labels,
            "pod_annotations": workload.annotations,
            "readiness_initial_delay_s": workload.readiness_initial_delay or 0,
        }

    def _cleanup_stale_classifications(self, cluster_id: str, active_workload_ids: set) -> None:
        """
        Remove DB classification records for workloads that no longer exist in
        this cluster. Called at the end of each slow loop.
        Redis keys auto-expire via TTL — no explicit Redis cleanup needed.
        """
        from backend.models.workload_classification import WorkloadClassificationRecord

        CHUNK_SIZE = 100
        all_ids = list(active_workload_ids)

        try:
            # Find all DB record IDs for this cluster
            existing = (
                self.db.query(WorkloadClassificationRecord.workload_id)
                .filter_by(cluster_id=cluster_id)
                .all()
            )
            existing_ids = {row.workload_id for row in existing}
            stale_ids = existing_ids - active_workload_ids

            if not stale_ids:
                return

            logger.info(f"wie_stale_cleanup cluster_id={cluster_id} stale_count={len(stale_ids)}")

            # Delete in chunks to avoid huge IN clauses
            stale_list = list(stale_ids)
            for i in range(0, len(stale_list), CHUNK_SIZE):
                chunk = stale_list[i : i + CHUNK_SIZE]
                self.db.query(WorkloadClassificationRecord).filter(
                    WorkloadClassificationRecord.cluster_id == cluster_id,
                    WorkloadClassificationRecord.workload_id.in_(chunk),
                ).delete(synchronize_session=False)

            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise

    def _collect_workloads(
        self,
        cluster_id: str,
        pod_state_snapshot: Dict[str, dict],
    ) -> List[WorkloadInput]:
        """
        Collect workloads from pod_metrics DB table + pod_state Redis snapshot.
        Aggregates individual pod rows into per-controller WorkloadInput objects.
        """
        from backend.models.pod_metric import PodMetric
        from sqlalchemy import func, distinct

        # Prefer fresh data (last 10 min). If no recent data, fall back to
        # the most recent collection window available (agent may be offline).
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

        fresh_count = (
            self.db.query(func.count(PodMetric.id))
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.timestamp >= cutoff,
                PodMetric.controller_name.isnot(None),
                PodMetric.controller_name != "",
            )
            .scalar()
        )

        if not fresh_count:
            # No recent data — find the latest timestamp and use a 10-min
            # window around it so we still get a consistent snapshot.
            latest_ts = (
                self.db.query(func.max(PodMetric.timestamp))
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.controller_name.isnot(None),
                    PodMetric.controller_name != "",
                )
                .scalar()
            )
            if latest_ts:
                cutoff = latest_ts.replace(tzinfo=timezone.utc) - timedelta(minutes=10)
                logger.info(
                    f"wie_collect_workloads using historical data "
                    f"cluster_id={cluster_id} latest_ts={latest_ts}"
                )
            else:
                logger.info(f"wie_collect_workloads no pod_metrics at all cluster_id={cluster_id}")
                return []

        # Get distinct workloads with their latest pod data
        workload_rows = (
            self.db.query(
                PodMetric.namespace,
                PodMetric.controller_kind,
                PodMetric.controller_name,
                func.count(distinct(PodMetric.pod_name)).label("pod_count"),
                func.max(PodMetric.timestamp).label("latest_ts"),
            )
            .filter(
                PodMetric.cluster_id == cluster_id,
                PodMetric.timestamp >= cutoff,
                PodMetric.controller_name.isnot(None),
                PodMetric.controller_name != "",
                PodMetric.controller_kind.isnot(None),
                PodMetric.controller_kind != "",
            )
            .group_by(
                PodMetric.namespace,
                PodMetric.controller_kind,
                PodMetric.controller_name,
            )
            .all()
        )

        if not workload_rows:
            logger.info(f"wie_collect_workloads no pod_metrics found cluster_id={cluster_id}")
            return []

        workloads: List[WorkloadInput] = []

        for row in workload_rows:
            ns = row.namespace
            kind = row.controller_kind
            name = row.controller_name
            workload_id = f"{ns}/{name}"

            # Get the latest pod record per unique pod for this workload
            # to extract metadata and compute aggregates
            latest_pods = (
                self.db.query(PodMetric)
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.namespace == ns,
                    PodMetric.controller_kind == kind,
                    PodMetric.controller_name == name,
                    PodMetric.timestamp >= cutoff,
                )
                .order_by(PodMetric.timestamp.desc())
                .limit(50)
                .all()
            )

            # Deduplicate to latest record per pod_name
            seen_pods: Dict[str, PodMetric] = {}
            for pod in latest_pods:
                if pod.pod_name not in seen_pods:
                    seen_pods[pod.pod_name] = pod

            pod_records = list(seen_pods.values())
            if not pod_records:
                continue

            # Extract metadata from the first pod that has it
            meta: Dict[str, Any] = {}
            scheduling: Dict[str, Any] = {}
            for pr in pod_records:
                if pr.pod_metadata:
                    meta = pr.pod_metadata if isinstance(pr.pod_metadata, dict) else {}
                    scheduling = meta.get("__scheduling", {}) if isinstance(meta.get("__scheduling"), dict) else {}
                    if meta:
                        break

            labels = meta.get("labels", {}) if isinstance(meta.get("labels"), dict) else {}
            has_pvc = bool(meta.get("has_pvc", False))
            # PDB: if any pod in the workload reports has_pdb, the workload has a PDB.
            has_pdb = any(
                bool((pr.pod_metadata or {}).get("has_pdb", False))
                for pr in pod_records
            )
            readiness_delay = meta.get("readiness_initial_delay_s")
            tsc = meta.get("topology_spread_constraints")
            affinity = meta.get("affinity")

            # Scheduling metadata
            has_topology_spread = bool(scheduling.get("has_topology_spread", False)) or bool(tsc)
            has_pod_anti_affinity = bool(scheduling.get("has_pod_anti_affinity", False))

            # Check for pod anti-affinity in affinity field
            if affinity and isinstance(affinity, dict):
                pod_anti = affinity.get("podAntiAffinity")
                if pod_anti:
                    has_pod_anti_affinity = True

            # Observed zones from node names (use pod_state if available)
            pod_state = pod_state_snapshot.get(workload_id, {})
            observed_zones = pod_state.get("zones", pod_state.get("observed_zones", []))
            if not observed_zones:
                # Derive from unique node names as proxy
                observed_zones = list({pr.node_name for pr in pod_records if pr.node_name})

            # Replica counts — prefer spec_replicas from pod_state (controller desired count)
            # over len(pod_records) which only counts pods with recent metric samples.
            spec_replicas = pod_state.get("spec_replicas") or pod_state.get("desired_replicas")
            replicas = int(spec_replicas) if spec_replicas else len(pod_records)
            ready_count = pod_state.get("ready_pods", pod_state.get("ready_count"))
            if ready_count is None:
                # Count pods in Running phase
                ready_count = sum(
                    1 for pr in pod_records
                    if pr.pod_metadata and isinstance(pr.pod_metadata, dict)
                    and pr.pod_metadata.get("phase") == "Running"
                )

            # Restart info from pod_state cache
            restart_count = pod_state.get("restart_count", 0)

            # Priority class from labels/annotations (not directly in pod_metrics)
            priority_class = None

            # Service exposure — check for common service-related labels
            service_type = None
            has_ingress = False

            # Data safety
            data_safety = "EPHEMERAL"
            if kind == "StatefulSet" or has_pvc:
                data_safety = "STATEFUL"
            else:
                # Check for cache-layer patterns
                name_lower = name.lower()
                for pattern in CACHE_IMAGE_PATTERNS:
                    if pattern in name_lower:
                        data_safety = "CACHE"
                        break

            # Workload age from earliest metric timestamp
            earliest_ts = (
                self.db.query(func.min(PodMetric.timestamp))
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.namespace == ns,
                    PodMetric.controller_name == name,
                )
                .scalar()
            )
            age_hours = 0.0
            if earliest_ts:
                age_delta = datetime.now(timezone.utc) - earliest_ts.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, age_delta.total_seconds() / 3600)

            # Metrics staleness
            latest_ts = row.latest_ts
            metrics_stale_minutes = METRICS_ABSENT_VALUE
            if latest_ts:
                stale_delta = datetime.now(timezone.utc) - latest_ts.replace(tzinfo=timezone.utc)
                metrics_stale_minutes = max(0, int(stale_delta.total_seconds() / 60))

            wi = WorkloadInput(
                workload_id=workload_id,
                cluster_id=cluster_id,
                namespace=ns,
                name=name,
                controller_kind=kind,
                replicas=replicas,
                ready_replicas=ready_count,
                has_pdb=has_pdb,
                has_topology_spread=has_topology_spread,
                has_pod_anti_affinity=has_pod_anti_affinity,
                has_pvc=has_pvc,
                data_safety=data_safety,
                workload_age_hours=age_hours,
                workload_age_days=age_hours / 24.0,
                restart_count_per_hour=restart_count / max(1.0, age_hours),
                metrics_stale_minutes=metrics_stale_minutes,
                readiness_initial_delay=readiness_delay,
                observed_zones=observed_zones,
                owner_labels=labels,
                annotations={},
                priority_class=priority_class,
                service_type=service_type,
                has_ingress=has_ingress,
                has_declared_spread=has_topology_spread or has_pod_anti_affinity,
            )
            workloads.append(wi)

        logger.info(
            f"wie_collect_workloads cluster_id={cluster_id} "
            f"workloads_found={len(workloads)}"
        )
        return workloads

    # ── Fast loop ─────────────────────────────────────────────────────────

    def fast_loop_update(self, cluster_id: str) -> None:
        """
        Lightweight loop running every 2 min.
        ONLY updates pod_state cache in Redis. No scoring. No DB writes.
        Allows slow loop to use fresh pod state without direct K8s calls.
        """
        try:
            from backend.models.pod_metric import PodMetric

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            rows = (
                self.db.query(
                    PodMetric.namespace,
                    PodMetric.controller_kind,
                    PodMetric.controller_name,
                    PodMetric.pod_name,
                    PodMetric.node_name,
                    PodMetric.pod_metadata,
                )
                .filter(
                    PodMetric.cluster_id == cluster_id,
                    PodMetric.timestamp >= cutoff,
                    PodMetric.controller_name.isnot(None),
                    PodMetric.controller_name != "",
                )
                .all()
            )

            # Group by (namespace, controller_name)
            groups: Dict[str, list] = {}
            for row in rows:
                if not row.controller_name:
                    continue
                key = f"{row.namespace}/{row.controller_name}"
                groups.setdefault(key, []).append(row)

            pipeline = self.redis.pipeline()
            updated = 0
            for workload_key, pod_rows in groups.items():
                try:
                    ns, ctrl = workload_key.split("/", 1)
                    ready_count = sum(
                        1 for r in pod_rows
                        if r.pod_metadata and isinstance(r.pod_metadata, dict)
                        and r.pod_metadata.get("phase") == "Running"
                    )
                    total_count = len(set(r.pod_name for r in pod_rows))
                    zones = list({r.node_name for r in pod_rows if r.node_name})

                    state = {
                        "restart_count": 0,
                        "restart_count_per_hour": 0.0,
                        "ready_pods": ready_count,
                        "total_pods": total_count,
                        "observed_zones": zones,
                        "last_restart_reason": None,
                        "stable_for_minutes": 0,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "schema_version": POD_STATE_SCHEMA_VERSION,
                    }
                    pod_state_key = wie_pod_state_key(cluster_id, ns, ctrl)
                    pipeline.setex(pod_state_key, 300, json.dumps(state))
                    updated += 1
                except Exception:
                    continue

            pipeline.execute()
            logger.debug(f"wie_fast_loop_complete cluster_id={cluster_id} updated={updated}")
        except Exception as e:
            logger.warning(f"wie_fast_loop_error cluster_id={cluster_id} error={e}")

    def _fetch_pod_state_direct(
        self,
        cluster_id: str,
        namespace: str,
        controller_name: str,
    ) -> Optional[dict]:
        """
        Fallback for when pod_state cache key is missing.
        Fetches live pod state from K8s API directly.
        Called by slow loop when cache miss detected.
        """
        # TODO Task 1.5: implement live K8s pod state fetch
        log_pod_state_cache_miss(cluster_id, namespace, controller_name)
        return None
