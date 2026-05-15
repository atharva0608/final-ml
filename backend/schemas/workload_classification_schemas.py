"""
Pydantic Schemas — Workload Classification API v4.3
====================================================
All response schemas for the WIE REST API.
Validation-in: requests are validated here before reaching DB.
Validation-out: all API responses are serialized through these models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Core classification response
# ---------------------------------------------------------------------------

class WorkloadClassificationResponse(BaseModel):
    """
    Single workload classification record returned by the API.
    All fields are sourced from WorkloadClassificationRecord (DB) via Redis.
    """

    workload_id: str                # "namespace/name"
    cluster_id: str
    namespace: str
    name: str
    controller_kind: str            # Deployment / StatefulSet / DaemonSet / Job / CronJob

    role: str                       # SYSTEM / CONTROL_PLANE / APPLICATION
    criticality_score: int          # 0–10
    tier: str                       # Platinum / Gold / Silver / Bronze
    spot_score: int                 # 0–10
    spot_friendly: bool
    confidence_score: int           # 1–10
    confidence_state: str           # DRAFT / PROVISIONAL / CONFIRMED
    data_safety: str                # STATEFUL / CACHE / EPHEMERAL

    signals_fired: List[str] = Field(default_factory=list)
    override_active: bool = False
    override_reason: Optional[str] = None

    # Content fingerprint — change detection for consumers
    input_hash: str = ""
    schema_version: str = "4.3"

    classified_at: Optional[datetime] = None
    is_simulation: bool = False

    estimated_monthly_saving_usd: float = 0.0

    # ── v4.5 spot distribution constraints ───────────────────────────────────
    min_on_demand_replicas: int = 0
    max_spot_replicas: int = 0
    spot_eligible: bool = False
    workload_class: Optional[str] = None

    class Config:
        from_attributes = True


class WorkloadClassificationListResponse(BaseModel):
    """Paginated response for the workloads list endpoint."""
    total: int
    page: int
    page_size: int
    items: List[WorkloadClassificationResponse]


# ---------------------------------------------------------------------------
# Summary response
# ---------------------------------------------------------------------------

class ClusterClassificationSummary(BaseModel):
    """
    Cluster-level aggregated view over all workload classifications.
    Returned by GET /summary.
    """
    cluster_id: str
    total_workloads: int
    tier_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description='{"Platinum": 5, "Gold": 12, "Silver": 30, "Bronze": 45}',
    )
    confidence_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description='{"DRAFT": 3, "PROVISIONAL": 10, "CONFIRMED": 79}',
    )
    role_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description='{"SYSTEM": 8, "CONTROL_PLANE": 4, "APPLICATION": 80}',
    )
    spot_friendly_count: int = 0
    spot_friendly_pct: float = 0.0
    spot_ready_count: int = 0           # CONFIRMED + spot_friendly
    last_scan_at: Optional[datetime] = None
    engine_age_hours: float = 0.0

    confirmed_count: int = 0
    provisional_count: int = 0
    draft_count: int = 0
    total_estimated_saving_usd: float = 0.0


# ---------------------------------------------------------------------------
# Detail response (single workload with scoring breakdown)
# ---------------------------------------------------------------------------

class ScoringBreakdown(BaseModel):
    """
    Per-signal scoring explanation for one workload.
    Reconstructed from signals_fired list.
    """
    role_signals: List[str] = Field(default_factory=list)
    criticality_signals: List[str] = Field(default_factory=list)
    spot_signals: List[str] = Field(default_factory=list)
    confidence_signals: List[str] = Field(default_factory=list)
    override_signals: List[str] = Field(default_factory=list)
    all_signals: List[str] = Field(default_factory=list)


class WorkloadClassificationDetail(BaseModel):
    """Full detail view for one workload — classification + scoring breakdown."""
    classification: WorkloadClassificationResponse
    scoring_breakdown: ScoringBreakdown


# ---------------------------------------------------------------------------
# Engine health metrics response
# ---------------------------------------------------------------------------

class EngineMetricsResponse(BaseModel):
    """
    Engine health metrics returned by GET /metrics.
    Populated from Redis HASH wie_metrics_key(cluster_id).
    """
    cluster_id: str
    scan_count: int = 0
    last_scan_at: Optional[str] = None
    last_scan_duration_ms: int = 0
    total_workloads: int = 0
    confirmed_count: int = 0
    provisional_count: int = 0
    draft_count: int = 0
    spot_friendly_count: int = 0
    spot_friendly_pct: float = 0.0
    db_writes: int = 0
    db_suppressed: int = 0
    suppress_rate: float = 0.0
    debounce_drops: int = 0
    rate_limit_drops: int = 0
    error_count: int = 0
    signal_freq: Dict[str, int] = Field(default_factory=dict)
    engine_age_hours: float = 0.0
    enforcement_enabled: bool = False


# ---------------------------------------------------------------------------
# Override request/response
# ---------------------------------------------------------------------------

class OverrideRequest(BaseModel):
    """
    Request body for POST /workloads/{workload_id}/override.
    All fields optional — only the provided fields are applied.
    """
    spot_override: Optional[bool] = Field(
        default=None,
        description="Force spot_friendly to this value. Safety invariants still apply.",
    )
    tier_override: Optional[str] = Field(
        default=None,
        description="Force tier to this value. Cannot override SYSTEM role workloads.",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Human-readable reason for this override (audit trail).",
    )
    expires_hours: Optional[int] = Field(
        default=None,
        ge=1,
        le=720,
        description="Override expires after this many hours (1–720). None = permanent until removed.",
    )

    @validator("tier_override")
    def validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("Platinum", "Gold", "Silver", "Bronze"):
            raise ValueError("tier_override must be one of: Platinum, Gold, Silver, Bronze")
        return v


class OverrideResponse(BaseModel):
    """Response returned after a successful override operation."""
    workload_id: str
    applied: bool
    override_active: bool
    field: str                      # "spot_override" | "tier_override" | "both"
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Spot candidates response
# ---------------------------------------------------------------------------

class SpotCandidateResponse(BaseModel):
    """
    Simplified view for spot-eligible workloads (CONFIRMED + spot_friendly).
    Returned by GET /spot-candidates.
    """
    workload_id: str
    cluster_id: str
    namespace: str
    name: str
    controller_kind: str
    tier: str
    spot_score: int
    criticality_score: int
    confidence_state: str
    data_safety: str
    signals_fired: List[str] = Field(default_factory=list)
    classified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SpotCandidatesResponse(BaseModel):
    """
    Candidate sets for downstream systems.

    - safe_candidates: automation-allowed set (CONFIRMED + spot_friendly)
    - potential_candidates: visibility set (PROVISIONAL + spot_friendly)
    """

    safe_candidates: List[SpotCandidateResponse] = Field(default_factory=list)
    potential_candidates: List[SpotCandidateResponse] = Field(default_factory=list)
