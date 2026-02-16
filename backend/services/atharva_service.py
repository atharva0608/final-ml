from datetime import datetime, timedelta
import random
import uuid
from typing import List, Dict, Any, Optional
from backend.schemas.atharva_schemas import (
    AtharvaStatus, RiskLevel, InstanceRanking, InstancePool, PoolType, PoolStatus,
    Recommendation, RecommendationType, RiskEvent, AtharvaSettings,
    NodeTemplate, NodeTemplateCreate, NodeTemplateUpdate, NodeTemplateRules,
    RankedPool, PoolRankingsResponse, FilteringStats, AppliedTemplate, CurrentPool,
    PoolMetadata, TrendDirection,
    PoolDetailsResponse, PoolOverview, PoolSpecifications, RiskBreakdown,
    CostAnalysis, SavingsDetail, CurrentUsage, SwitchPreview, CostImpact, RiskImpact,
    BlacklistEntry, BlacklistReason, BlacklistResponse, BlacklistAddRequest,
    SafetyCheck, PoolSwitchRequest, PoolSwitchResponse,
    ActivityEvent, ActivityEventType
)


class AtharvaService:
    def __init__(self):
        self.settings = AtharvaSettings(
            auto_rebalance=True,
            risk_threshold=75,
            notification_channels=["slack", "email"],
            excluded_node_groups=["critical-workloads"]
        )

        # In-memory stores
        self._node_templates: Dict[str, NodeTemplate] = {}
        self._blacklist: Dict[str, BlacklistEntry] = {}
        self._activity_events: List[ActivityEvent] = []

        # Seed default template
        self._seed_default_template()
        self._seed_activity_events()

    def _seed_default_template(self):
        t = NodeTemplate(
            id="tmpl-default",
            name="Production Standard",
            description="Default template for production workloads",
            active=True,
            applied_clusters=["cluster-prod-east"],
            rules=NodeTemplateRules(
                cpu_architecture=["x64"],
                vcpu_min=2, vcpu_max=16,
                memory_min_gib=4, memory_max_gib=64,
                instance_families_allowed=["m5", "m5a", "m6i", "c5", "r5"],
                instance_sizes_allowed=["large", "xlarge", "2xlarge"],
                exclude_burstable=True,
                spot_only=True,
                max_interruption_rate=0.20
            ),
            created_at=datetime.utcnow() - timedelta(days=30),
            updated_at=datetime.utcnow() - timedelta(days=2),
            created_by="admin"
        )
        self._node_templates[t.id] = t

        t2 = NodeTemplate(
            id="tmpl-dev",
            name="Dev / Test",
            description="Cost-optimized for non-critical environments",
            active=True,
            applied_clusters=[],
            rules=NodeTemplateRules(
                cpu_architecture=["x64", "arm64"],
                vcpu_min=1, vcpu_max=8,
                memory_min_gib=2, memory_max_gib=32,
                instance_families_allowed=["m5", "m5a", "m6i", "c5", "c5a", "t3"],
                instance_sizes_allowed=["large", "xlarge"],
                exclude_burstable=False,
                spot_only=True,
                max_interruption_rate=0.35
            ),
            created_at=datetime.utcnow() - timedelta(days=15),
            updated_at=datetime.utcnow() - timedelta(days=1),
            created_by="admin"
        )
        self._node_templates[t2.id] = t2

    def _seed_activity_events(self):
        now = datetime.utcnow()
        self._activity_events = [
            ActivityEvent(
                id="act-1", event_type=ActivityEventType.SYSTEM_DECISION,
                timestamp=now - timedelta(minutes=5), cluster_id="cluster-prod-east",
                description="Auto-rebalanced 3 nodes from m5.large (us-east-1d) to m5a.large (us-east-1a) due to rising interruption risk",
                details={"from_pool": "m5.large", "to_pool": "m5a.large", "nodes_affected": 3}
            ),
            ActivityEvent(
                id="act-2", event_type=ActivityEventType.POOL_BLACKLISTED,
                timestamp=now - timedelta(minutes=22), cluster_id="cluster-prod-east",
                description="Pool c5.xlarge (us-east-1d) blacklisted for 12h after termination notice",
                details={"instance_type": "c5.xlarge", "az": "us-east-1d", "reason": "termination_notice"}
            ),
            ActivityEvent(
                id="act-3", event_type=ActivityEventType.REBALANCING_COMPLETED,
                timestamp=now - timedelta(hours=1), cluster_id="cluster-prod-east",
                description="Rebalancing complete: 5 nodes migrated, saving $0.42/hr",
                details={"nodes_migrated": 5, "savings_hourly": 0.42}
            ),
            ActivityEvent(
                id="act-4", event_type=ActivityEventType.MANUAL_DECISION,
                timestamp=now - timedelta(hours=3), cluster_id="cluster-prod-east",
                description="Manual switch from r5.xlarge to m5.xlarge by admin@company.com",
                details={"user": "admin@company.com", "from_pool": "r5.xlarge", "to_pool": "m5.xlarge"}
            ),
            ActivityEvent(
                id="act-5", event_type=ActivityEventType.SYSTEM_DECISION,
                timestamp=now - timedelta(hours=6), cluster_id="cluster-prod-east",
                description="Capacity alert: us-west-2b spot capacity below 30%, shifted priorities to us-west-2a",
                details={"az": "us-west-2b", "capacity_pct": 28}
            ),
        ]

    # ─── Existing Methods ─────────────────────────────────────────────────────

    async def get_system_status(self) -> AtharvaStatus:
        risk_score = random.randint(10, 35)
        return AtharvaStatus(
            risk_score=risk_score,
            risk_level=RiskLevel.LOW if risk_score < 30 else RiskLevel.MEDIUM,
            savings_rate=round(random.uniform(55.0, 72.0), 1),
            active_optimization_count=random.randint(3, 12),
            auto_rebalance_enabled=self.settings.auto_rebalance,
            manual_mode_expires=None,
            current_cluster="cluster-prod-east",
            monitored_nodes=random.randint(12, 24),
            active_pools=random.randint(4, 8),
            last_updated=datetime.utcnow()
        )

    async def get_instance_rankings(self) -> InstanceRanking:
        safe_pools = [
            InstancePool(id="pool-a1", name="Stable-East-1a", instance_type="m5.large",
                         availability_zone="us-east-1a", price=0.045, interrupt_risk=5,
                         risk_level=RiskLevel.LOW, efficiency_score=92,
                         pool_type=PoolType.SPOT, status=PoolStatus.ACTIVE),
            InstancePool(id="pool-b2", name="Reliable-West-2b", instance_type="c6g.xlarge",
                         availability_zone="us-west-2b", price=0.082, interrupt_risk=8,
                         risk_level=RiskLevel.LOW, efficiency_score=88,
                         pool_type=PoolType.SPOT, status=PoolStatus.ACTIVE),
            InstancePool(id="pool-c3", name="Core-East-1c", instance_type="r6i.large",
                         availability_zone="us-east-1c", price=0.065, interrupt_risk=12,
                         risk_level=RiskLevel.LOW, efficiency_score=85,
                         pool_type=PoolType.SPOT, status=PoolStatus.ACTIVE),
        ]
        cheap_pools = [
            InstancePool(id="pool-x9", name="Budget-East-1d", instance_type="t3.medium",
                         availability_zone="us-east-1d", price=0.018, interrupt_risk=45,
                         risk_level=RiskLevel.MEDIUM, efficiency_score=98,
                         pool_type=PoolType.SPOT, status=PoolStatus.ACTIVE),
            InstancePool(id="pool-y8", name="Econ-West-2a", instance_type="c5.large",
                         availability_zone="us-west-2a", price=0.038, interrupt_risk=25,
                         risk_level=RiskLevel.MEDIUM, efficiency_score=95,
                         pool_type=PoolType.SPOT, status=PoolStatus.ACTIVE),
            InstancePool(id="pool-z7", name="Value-East-1b", instance_type="m6g.medium",
                         availability_zone="us-east-1b", price=0.032, interrupt_risk=30,
                         risk_level=RiskLevel.MEDIUM, efficiency_score=94,
                         pool_type=PoolType.SPOT, status=PoolStatus.ACTIVE),
        ]
        return InstanceRanking(top_safe_pools=safe_pools, top_cheap_pools=cheap_pools, last_updated=datetime.utcnow())

    async def get_recommendations(self) -> List[Recommendation]:
        return [
            Recommendation(id="rec-101", type=RecommendationType.REBALANCE,
                           title="High Risk in US-East-1d",
                           description="Spot interruption probability increased to 45%. Recommend moving to US-East-1a.",
                           impact="Prevent Downtime", confidence=92, risk_level=RiskLevel.HIGH,
                           created_at=datetime.utcnow() - timedelta(minutes=15),
                           applies_to="NodeGroup: worker-spot-v1"),
            Recommendation(id="rec-102", type=RecommendationType.RIGHTSIZE,
                           title="Underutilized Memory in Batch-Jobs",
                           description="Memory usage consistently below 40%. Switch to c6g.xlarge.",
                           impact="Save $145/mo", confidence=88, risk_level=RiskLevel.LOW,
                           created_at=datetime.utcnow() - timedelta(hours=2),
                           applies_to="Deployment: batch-processor"),
            Recommendation(id="rec-103", type=RecommendationType.TYPE_SWITCH,
                           title="Switch to Graviton Instances",
                           description="Compatible workloads detected. Migrate to ARM-based instances for better price/performance.",
                           impact="Save 20%", confidence=75, risk_level=RiskLevel.LOW,
                           created_at=datetime.utcnow() - timedelta(days=1),
                           applies_to="Namespace: backend-services"),
        ]

    async def get_risk_history(self) -> List[RiskEvent]:
        now = datetime.utcnow()
        return [
            RiskEvent(id="evt-1", timestamp=now - timedelta(minutes=5), level=RiskLevel.LOW,
                      message="Spot price fluctuation detected in us-east-1", source="MarketMonitor", resolved=True),
            RiskEvent(id="evt-2", timestamp=now - timedelta(hours=4), level=RiskLevel.MEDIUM,
                      message="Capacity constraints in us-west-2b", source="CapacityScraper", resolved=True),
            RiskEvent(id="evt-3", timestamp=now - timedelta(days=1), level=RiskLevel.HIGH,
                      message="Mass interruption warning received", source="AWS Health", resolved=True),
        ]

    async def update_settings(self, new_settings: AtharvaSettings) -> AtharvaSettings:
        self.settings = new_settings
        return self.settings

    # ─── Node Templates ───────────────────────────────────────────────────────

    async def list_node_templates(self) -> List[NodeTemplate]:
        return list(self._node_templates.values())

    async def get_node_template(self, template_id: str) -> Optional[NodeTemplate]:
        return self._node_templates.get(template_id)

    async def create_node_template(self, data: NodeTemplateCreate) -> NodeTemplate:
        template = NodeTemplate(
            id=f"tmpl-{uuid.uuid4().hex[:8]}",
            name=data.name,
            description=data.description,
            rules=data.rules,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by="current_user"
        )
        self._node_templates[template.id] = template
        return template

    async def update_node_template(self, template_id: str, data: NodeTemplateUpdate) -> Optional[NodeTemplate]:
        template = self._node_templates.get(template_id)
        if not template:
            return None
        update_data = data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(template, field, value)
        template.updated_at = datetime.utcnow()
        self._node_templates[template_id] = template
        return template

    async def delete_node_template(self, template_id: str) -> bool:
        if template_id in self._node_templates:
            del self._node_templates[template_id]
            return True
        return False

    async def apply_node_template(self, template_id: str, cluster_id: str) -> Optional[NodeTemplate]:
        template = self._node_templates.get(template_id)
        if not template:
            return None
        if cluster_id not in template.applied_clusters:
            template.applied_clusters.append(cluster_id)
            template.updated_at = datetime.utcnow()
            self._node_templates[template_id] = template
        return template

    # ─── Pool Rankings ────────────────────────────────────────────────────────

    async def get_pool_rankings(self, cluster_id: str, template_id: Optional[str] = None, limit: int = 10) -> PoolRankingsResponse:
        # Mock ranked pools with realistic data
        instance_configs = [
            ("m5.large", "m5", "us-east-1a", 2, 8.0, "x64", "Up to 10 Gbps"),
            ("m5a.large", "m5a", "us-east-1a", 2, 8.0, "x64", "Up to 10 Gbps"),
            ("m5.xlarge", "m5", "us-east-1b", 4, 16.0, "x64", "Up to 10 Gbps"),
            ("c5.large", "c5", "us-east-1a", 2, 4.0, "x64", "Up to 10 Gbps"),
            ("c5.xlarge", "c5", "us-east-1c", 4, 8.0, "x64", "Up to 10 Gbps"),
            ("m6i.large", "m6i", "us-east-1b", 2, 8.0, "x64", "Up to 12.5 Gbps"),
            ("r5.large", "r5", "us-east-1a", 2, 16.0, "x64", "Up to 10 Gbps"),
            ("m5a.xlarge", "m5a", "us-east-1c", 4, 16.0, "x64", "Up to 10 Gbps"),
            ("c5a.large", "c5a", "us-east-1b", 2, 4.0, "x64", "Up to 10 Gbps"),
            ("m5n.large", "m5n", "us-east-1a", 2, 8.0, "x64", "Up to 25 Gbps"),
        ]

        trends = [TrendDirection.IMPROVING, TrendDirection.STABLE, TrendDirection.DEGRADING]
        rankings = []

        for i, (itype, family, az, vcpu, mem, arch, net) in enumerate(instance_configs[:limit]):
            risk = round(random.uniform(0.05, 0.55), 3)
            intrate = round(random.uniform(0.02, 0.30), 3)
            cost = round(random.uniform(0.03, 0.12), 4)
            combined = round((1 - risk) * 0.7 + (1 - cost / 0.12) * 0.3, 3)

            rankings.append(RankedPool(
                rank=i + 1,
                pool_id=f"pool-{uuid.uuid4().hex[:6]}",
                instance_type=itype,
                instance_family=family,
                availability_zone=az,
                risk_score=risk,
                interruption_rate=intrate,
                hourly_cost=cost,
                combined_score=combined,
                trend=random.choice(trends),
                rank_change=random.randint(-3, 3),
                current_nodes=random.randint(0, 5) if i < 3 else 0,
                is_current=(i == 0),
                is_blacklisted=(i == 7),  # one blacklisted for demo
                blacklist_expires_at=datetime.utcnow() + timedelta(hours=8) if i == 7 else None,
                metadata=PoolMetadata(vcpu=vcpu, memory_gib=mem, network_performance=net, architecture=arch)
            ))

        # Sort by risk then cost
        rankings.sort(key=lambda p: (p.risk_score, p.hourly_cost))
        for i, pool in enumerate(rankings):
            pool.rank = i + 1

        tmpl = self._node_templates.get(template_id) if template_id else None
        applied = AppliedTemplate(id=tmpl.id, name=tmpl.name) if tmpl else None

        return PoolRankingsResponse(
            rankings=rankings,
            applied_template=applied,
            filtering_stats=FilteringStats(
                total_pools_available=287,
                after_template_filter=42,
                after_interruption_filter=31,
                after_blacklist_filter=28,
                after_uniqueness_filter=18,
                final_top_10=min(limit, len(rankings))
            ),
            current_pool=CurrentPool(instance_type="m5.large", availability_zone="us-east-1a", rank=1),
            last_updated=datetime.utcnow()
        )

    # ─── Pool Details ─────────────────────────────────────────────────────────

    async def get_pool_details(self, pool_id: str, cluster_id: str) -> PoolDetailsResponse:
        risk = round(random.uniform(0.08, 0.35), 3)
        spot_price = round(random.uniform(0.035, 0.095), 4)
        ondemand = round(spot_price * random.uniform(2.5, 3.5), 4)

        return PoolDetailsResponse(
            overview=PoolOverview(
                pool_name=f"Pool {pool_id}",
                instance_type="m5.large",
                availability_zone="us-east-1a",
                risk_score=risk,
                interruption_rate=round(random.uniform(0.03, 0.20), 3),
                hourly_cost=spot_price,
                spot_price_current=spot_price,
                ondemand_price=ondemand,
                discount_percentage=round((1 - spot_price / ondemand) * 100, 1)
            ),
            specifications=PoolSpecifications(
                vcpu=2, memory_gib=8.0, architecture="x64",
                network_performance="Up to 10 Gbps", storage="EBS only", ebs_optimized=True
            ),
            risk_breakdown=RiskBreakdown(
                overall_risk_score=risk,
                interruption_probability=round(risk * 0.8, 3),
                regional_capacity_score=round(random.uniform(0.6, 0.95), 2),
                historical_interruptions_24h=random.randint(0, 3),
                global_interruptions_1h=random.randint(0, 15),
                last_interruption=datetime.utcnow() - timedelta(hours=random.randint(2, 72))
            ),
            cost_analysis=CostAnalysis(
                hourly_cost=spot_price,
                daily_cost=round(spot_price * 24, 2),
                monthly_cost_projection=round(spot_price * 730, 2),
                savings_vs_ondemand=SavingsDetail(
                    hourly=round(ondemand - spot_price, 4),
                    monthly=round((ondemand - spot_price) * 730, 2),
                    percentage=round((1 - spot_price / ondemand) * 100, 1)
                )
            ),
            current_usage=CurrentUsage(
                nodes_in_cluster=3, total_pods=47,
                avg_cpu_utilization=round(random.uniform(35, 72), 1),
                avg_memory_utilization=round(random.uniform(40, 80), 1)
            ),
            switch_preview=SwitchPreview(
                nodes_to_migrate=3, pods_to_reschedule=47,
                estimated_duration="8-12 minutes",
                estimated_downtime="0 seconds (rolling update)",
                cost_impact=CostImpact(
                    hourly_change=round(random.uniform(-0.05, 0.02), 4),
                    monthly_change=round(random.uniform(-36.5, 14.6), 2)
                ),
                risk_impact=RiskImpact(
                    current_risk=0.15,
                    new_risk=risk,
                    change="improving" if risk < 0.15 else "degrading"
                )
            )
        )

    # ─── Blacklist ────────────────────────────────────────────────────────────

    async def get_blacklist(self, region: Optional[str] = None) -> BlacklistResponse:
        now = datetime.utcnow()
        # Clean expired
        self._blacklist = {k: v for k, v in self._blacklist.items() if v.expires_at > now}

        entries = list(self._blacklist.values())
        if region:
            entries = [e for e in entries if e.region == region]

        # Update time remaining
        for e in entries:
            delta = e.expires_at - now
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            e.time_remaining = f"{hours}h {mins}m"

        # Seed some demo entries if empty
        if not entries:
            demo = [
                BlacklistEntry(
                    pool_id="bl-c5-1d", instance_type="c5.xlarge", availability_zone="us-east-1d",
                    region="us-east-1", blacklisted_at=now - timedelta(hours=4),
                    expires_at=now + timedelta(hours=8), reason=BlacklistReason.TERMINATION_NOTICE,
                    time_remaining="8h 0m"
                ),
                BlacklistEntry(
                    pool_id="bl-r5-2b", instance_type="r5.large", availability_zone="us-west-2b",
                    region="us-west-2", blacklisted_at=now - timedelta(hours=2),
                    expires_at=now + timedelta(hours=10), reason=BlacklistReason.REBALANCE_NOTICE,
                    time_remaining="10h 0m"
                ),
            ]
            for d in demo:
                self._blacklist[d.pool_id] = d
            entries = demo

        return BlacklistResponse(blacklisted_pools=entries)

    async def add_to_blacklist(self, req: BlacklistAddRequest) -> BlacklistEntry:
        now = datetime.utcnow()
        entry = BlacklistEntry(
            pool_id=f"bl-{uuid.uuid4().hex[:6]}",
            instance_type=req.instance_type,
            availability_zone=req.availability_zone,
            region=req.region,
            blacklisted_at=now,
            expires_at=now + timedelta(hours=req.duration_hours),
            reason=req.reason,
            time_remaining=f"{req.duration_hours}h 0m"
        )
        self._blacklist[entry.pool_id] = entry
        return entry

    async def remove_from_blacklist(self, pool_id: str) -> bool:
        if pool_id in self._blacklist:
            del self._blacklist[pool_id]
            return True
        return False

    # ─── Pool Switch ──────────────────────────────────────────────────────────

    async def switch_pool(self, req: PoolSwitchRequest) -> PoolSwitchResponse:
        return PoolSwitchResponse(
            action_id=f"switch-{uuid.uuid4().hex[:8]}",
            status="initiated",
            from_pool=req.from_pool_id,
            to_pool=req.to_pool_id,
            safety_checks=[
                SafetyCheck(check="No critical jobs running", status=True, blocking=True),
                SafetyCheck(check="PDBs allow disruption", status=True, blocking=True),
                SafetyCheck(check="Sufficient capacity available", status=True, blocking=True),
            ],
            estimated_duration="8-12 minutes",
            initiated_at=datetime.utcnow()
        )

    # ─── Activity Feed ────────────────────────────────────────────────────────

    async def get_activity(self, limit: int = 5) -> List[ActivityEvent]:
        return self._activity_events[:limit]


# Global instance
atharva_service = AtharvaService()
