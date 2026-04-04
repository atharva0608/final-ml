"""
Metrics Service

Business logic for KPI calculation and dashboard metrics
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from backend.models.user import User, UserRole # Added User import
from backend.models.instance import Instance, InstanceLifecycle
from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.models.optimization_job import OptimizationJob, OptimizationJobStatus
from backend.schemas.metric_schemas import (
    DashboardKPIs,
    CostMetrics,
    InstanceMetrics,
    SavingsBreakdown,
    TimeSeriesData,
    TimeSeriesPoint,
    ClusterMetrics,
    MetricFilter,
)
from backend.core.exceptions import ResourceNotFoundError
from backend.core.logger import StructuredLogger
from datetime import datetime, timedelta, timezone
from decimal import Decimal

logger = StructuredLogger(__name__)


class MetricsService:
    """Service for metrics calculation and dashboard data"""

    def __init__(self, db: Session):
        self.db = db

    def get_dashboard_kpis(
        self,
        user_id: str,
        filters: MetricFilter
    ) -> DashboardKPIs:
        """
        Get dashboard KPIs for user

        Args:
            user_id: User UUID
            filters: Time range and cluster filters

        Returns:
            DashboardKPIs with key performance indicators
        """
        # Apply time range
        start_date = filters.start_date or (datetime.now(timezone.utc) - timedelta(days=30))
        end_date = filters.end_date or datetime.now(timezone.utc)

        # Base query for user's organization instances
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
            return DashboardKPIs(
                total_instances=0, active_instances=0, spot_instances=0, 
                on_demand_instances=0, total_cost=Decimal('0.0'), 
                estimated_savings=Decimal('0.0'), savings_percentage=0.0, 
                total_optimizations=0, successful_optimizations=0, 
                time_range_start=start_date, time_range_end=end_date
            )

        # Query ALL instances for the user's organization (including standalone instances without clusters)
        # We need to get instances from:
        # 1. Accounts that belong to the organization
        # 2. Clusters that belong to those accounts
        # 3. Instances in those clusters OR standalone instances from discovery

        # Get all account IDs for this organization
        org_account_ids = [acc.id for acc in self.db.query(Account.id).filter(
            Account.organization_id == user.organization_id
        ).all()]

        if not org_account_ids:
            # No accounts, return empty metrics
            total_instances = 0
            active_instances = 0
            spot_instances = 0
            on_demand_instances = 0
        else:
            # Get cluster IDs for these accounts
            cluster_ids = [c.id for c in self.db.query(Cluster.id).filter(
                Cluster.account_id.in_(org_account_ids)
            ).all()]

            # Query instances that belong to these clusters (include cluster_id IS NULL for standalone instances)
            # For standalone instances, we check if they were discovered from accounts in this org
            from sqlalchemy import or_

            if cluster_ids:
                # Get instances from clusters OR standalone instances from these accounts
                instance_query = self.db.query(Instance).filter(
                    or_(
                        Instance.cluster_id.in_(cluster_ids),
                        and_(Instance.cluster_id.is_(None), Instance.account_id.in_(org_account_ids))
                    )
                )
            else:
                # No clusters, only count standalone instances by account_id
                instance_query = self.db.query(Instance).filter(
                    Instance.account_id.in_(org_account_ids)
                )

            # Apply cluster filter if specified
            if filters.cluster_id:
                instance_query = instance_query.filter(Instance.cluster_id == filters.cluster_id)

            # Total instances
            total_instances = instance_query.count()

            # Active instances
            active_instances = instance_query.filter(
                Instance.state.in_(['running', 'pending'])
            ).count()

            # Spot vs On-Demand split
            spot_instances = instance_query.filter(
                and_(
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state.in_(['running', 'pending'])
                )
            ).count()

            on_demand_instances = active_instances - spot_instances

        # Calculate costs
        cost_metrics = self._calculate_cost_metrics(
            user_id,
            start_date,
            end_date,
            filters.cluster_id,
            filters.team_id
        )

        # Calculate savings
        savings_metrics = self._calculate_savings(
            user_id,
            start_date,
            end_date,
            filters.cluster_id,
            filters.team_id
        )

        # Optimization jobs
        job_query = self.db.query(OptimizationJob).join(Cluster).join(Account).filter(
            and_(
                Account.organization_id == user.organization_id,
                OptimizationJob.created_at >= start_date,
                OptimizationJob.created_at <= end_date
            )
        )

        if filters.cluster_id:
            job_query = job_query.filter(OptimizationJob.cluster_id == filters.cluster_id)

        total_optimizations = job_query.count()
        successful_optimizations = job_query.filter(
            OptimizationJob.status == OptimizationJobStatus.COMPLETED
        ).count()

        logger.info(
            "Dashboard KPIs calculated",
            user_id=user_id,
            total_instances=total_instances,
            active_instances=active_instances,
            total_cost=float(cost_metrics.total_cost)
        )

        optimization_rate = round((spot_instances / active_instances * 100), 1) if active_instances > 0 else 0.0

        return DashboardKPIs(
            total_instances=total_instances,
            active_instances=active_instances,
            spot_instances=spot_instances,
            on_demand_instances=on_demand_instances,
            total_cost=cost_metrics.total_cost,
            estimated_savings=savings_metrics.total_savings,
            savings_percentage=savings_metrics.savings_percentage,
            total_optimizations=total_optimizations,
            successful_optimizations=successful_optimizations,
            optimization_rate=optimization_rate,
            time_range_start=start_date,
            time_range_end=end_date
        )

    def get_cost_metrics(
        self,
        user_id: str,
        filters: MetricFilter
    ) -> CostMetrics:
        """
        Get detailed cost metrics

        Args:
            user_id: User UUID
            filters: Time range and cluster filters

        Returns:
            CostMetrics with cost breakdown
        """
        start_date = filters.start_date or (datetime.now(timezone.utc) - timedelta(days=30))
        end_date = filters.end_date or datetime.now(timezone.utc)

        return self._calculate_cost_metrics(
            user_id,
            start_date,
            end_date,
            filters.cluster_id,
            filters.team_id
        )

    def get_instance_metrics(
        self,
        user_id: str,
        filters: MetricFilter
    ) -> InstanceMetrics:
        """
        Get instance usage metrics

        Args:
            user_id: User UUID
            filters: Time range and cluster filters

        Returns:
            InstanceMetrics with usage breakdown
        """
        # Get user's organization
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
            return InstanceMetrics()

        # Base query - get all instances (cluster-based and standalone) for organization
        instance_query = self.db.query(Instance).join(Account).filter(
            Account.organization_id == user.organization_id
        )

        if filters.cluster_id:
            instance_query = instance_query.filter(Instance.cluster_id == filters.cluster_id)

        # Count by state
        running = instance_query.filter(Instance.state == 'running').count()
        pending = instance_query.filter(Instance.state == 'pending').count()
        stopping = instance_query.filter(Instance.state == 'stopping').count()
        stopped = instance_query.filter(Instance.state == 'stopped').count()
        terminated = instance_query.filter(Instance.state == 'terminated').count()

        # Count by lifecycle
        spot = instance_query.filter(Instance.lifecycle == InstanceLifecycle.SPOT).count()
        on_demand = instance_query.filter(Instance.lifecycle == InstanceLifecycle.ON_DEMAND).count()

        # Count by architecture
        amd64 = instance_query.filter(Instance.architecture == 'amd64').count()
        arm64 = instance_query.filter(Instance.architecture == 'arm64').count()

        # [NEW] Calculate type distribution
        # Group by instance_type and count
        type_counts = self.db.query(
            Instance.instance_type,
            func.count(Instance.id)
        ).join(Account).filter(
            Account.organization_id == user.organization_id
        )

        if filters.cluster_id:
            type_counts = type_counts.filter(Instance.cluster_id == filters.cluster_id)
            
        type_counts = type_counts.group_by(Instance.instance_type).all()
        
        # Convert to dictionary (handle None types)
        distribution = {
            (t[0] or "unknown"): t[1] 
            for t in type_counts
        }

        return InstanceMetrics(
            total_instances=instance_query.count(),
            running_instances=running,
            pending_instances=pending,
            stopping_instances=stopping,
            stopped_instances=stopped,
            terminated_instances=terminated,
            spot_instances=spot,
            on_demand_instances=on_demand,
            amd64_instances=amd64,
            arm64_instances=arm64,
            type_distribution=distribution
        )

    def get_cost_time_series(
        self,
        user_id: str,
        filters: MetricFilter
    ) -> TimeSeriesData:
        """
        Get cost metrics over time.

        When a cluster_id is provided, computes the daily cost from live instance
        hourly prices (price × 24h per day) so the chart reflects actual cluster
        compute cost rather than noisy AWS billing export data.
        """
        start_date = filters.start_date or (datetime.now(timezone.utc) - timedelta(days=30))
        end_date = filters.end_date or datetime.now(timezone.utc)

        data_points: List[TimeSeriesPoint] = []

        # ── Cluster-specific: derive daily cost from instance hourly prices ──
        if filters.cluster_id:
            from backend.models.instance import Instance as _Inst
            running_instances = self.db.query(_Inst).filter(
                _Inst.cluster_id == filters.cluster_id,
                _Inst.state == 'running',
                _Inst.price.isnot(None),
                _Inst.price > 0,
            ).all()

            daily_cost = 0.0

            if running_instances:
                # daily cost = sum of hourly prices × 24 h/day
                daily_cost = float(sum(float(i.price) for i in running_instances)) * 24.0
            else:
                # Running instances may exist but lack prices (e.g. K8s-discovered
                # nodes before EC2 pricing sync).  Look up OD rates for their
                # instance types so the chart isn't blank or inflated by the
                # account-wide DailyCost fallback.
                all_running = self.db.query(_Inst).filter(
                    _Inst.cluster_id == filters.cluster_id,
                    _Inst.state == 'running',
                ).all()
                if all_running:
                    try:
                        from backend.utils.pricing_helper import get_pricing_helper
                        ph = get_pricing_helper()
                        cluster = self.db.query(Cluster).filter(
                            Cluster.id == filters.cluster_id
                        ).first()
                        region = cluster.region if cluster else 'us-east-1'
                        hourly_sum = 0.0
                        for inst in all_running:
                            monthly = ph.get_ec2_price(region, inst.instance_type or 't3.medium')
                            hourly_sum += monthly / 730.0
                        daily_cost = hourly_sum * 24.0
                    except Exception:
                        pass  # fall through to cluster.monthly_cost

                # Last resort: cluster.monthly_cost from DB
                if daily_cost <= 0:
                    cluster = self.db.query(Cluster).filter(
                        Cluster.id == filters.cluster_id
                    ).first()
                    if cluster and cluster.monthly_cost and float(cluster.monthly_cost) > 0:
                        daily_cost = float(cluster.monthly_cost) / 30.0

            if daily_cost > 0:
                current_date = start_date
                while current_date <= end_date:
                    data_points.append(
                        TimeSeriesPoint(
                            timestamp=current_date,
                            value=round(daily_cost, 4)
                        )
                    )
                    current_date += timedelta(days=1)

                return TimeSeriesData(
                    metric_name="daily_cost",
                    data_points=data_points,
                    unit="USD"
                )

        # ── Fallback: original per-day cost calculation (DailyCost / EC2) ───
        current_date = start_date
        while current_date <= end_date:
            day_cost = self._calculate_daily_cost(
                user_id,
                current_date,
                filters.cluster_id,
                filters.team_id
            )

            data_points.append(
                TimeSeriesPoint(
                    timestamp=current_date,
                    value=day_cost
                )
            )

            current_date += timedelta(days=1)

        return TimeSeriesData(
            metric_name="daily_cost",
            data_points=data_points,
            unit="USD"
        )


    def get_cluster_metrics(
        self,
        cluster_id: str,
        user_id: str
    ) -> ClusterMetrics:
        """
        Get metrics for a specific cluster

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID

        Returns:
            ClusterMetrics with cluster-specific data

        Raises:
            ResourceNotFoundError: If cluster not found
        """
        # Verify cluster belongs to user
        # Verify cluster belongs to user's organization
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
            raise ResourceNotFoundError("Cluster", cluster_id)

        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.organization_id == user.organization_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        # Instance counts
        total_instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id
        ).count()

        active_instances = self.db.query(Instance).filter(
            and_(
                Instance.cluster_id == cluster_id,
                Instance.state.in_(['running', 'pending'])
            )
        ).count()

        spot_instances = self.db.query(Instance).filter(
            and_(
                Instance.cluster_id == cluster_id,
                Instance.lifecycle == InstanceLifecycle.SPOT,
                Instance.state.in_(['running', 'pending'])
            )
        ).count()

        # Recent optimization
        last_optimization = self.db.query(OptimizationJob).filter(
            OptimizationJob.cluster_id == cluster_id
        ).order_by(desc(OptimizationJob.created_at)).first()

        # Calculate spot ratio
        spot_ratio = (spot_instances / active_instances * 100) if active_instances > 0 else 0.0

        # Count on-demand instances
        on_demand_instances = self.db.query(Instance).filter(
            and_(
                Instance.cluster_id == cluster_id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND
            )
        ).count()

        # Get average CPU utilization from instances
        from sqlalchemy import func
        avg_cpu = self.db.query(func.avg(Instance.cpu_util)).filter(
            and_(
                Instance.cluster_id == cluster_id,
                Instance.cpu_util.isnot(None)
            )
        ).scalar()

        return ClusterMetrics(
            cluster_id=cluster_id,
            total_instances=total_instances,
            spot_instances=spot_instances,
            on_demand_instances=on_demand_instances,
            cpu_utilization=float(cluster.cpu_usage_pct or 0),
            memory_utilization=float(cluster.mem_usage_pct or 0),
            node_count=cluster.node_count or 0,
            spot_ratio=spot_ratio,
            monthly_cost=float(cluster.monthly_cost or 0),
            estimated_savings=float(cluster.estimated_savings or 0),
            realized_savings=float(cluster.realized_savings_monthly or 0),
            average_cpu_utilization=round(float(avg_cpu or 0), 2)
        )

    def _calculate_cost_metrics(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        cluster_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> CostMetrics:
        """
        Calculate cost metrics for time range

        Priority:
        1. Cost Explorer data (100% accurate, includes ALL AWS services)
        2. Fallback to EC2 instance pricing calculation

        Args:
            user_id: User UUID
            start_date: Start of time range
            end_date: End of time range
            cluster_id: Optional cluster filter
            team_id: Optional team filter

        Returns:
            CostMetrics
        """
        # Get user and organization
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
            return CostMetrics(total_cost=Decimal('0.0'), spot_cost=Decimal('0.0'), on_demand_cost=Decimal('0.0'), currency="USD")

        # Get organization account IDs
        org_accounts = self.db.query(Account.id, Account.aws_account_id).filter(
            Account.organization_id == user.organization_id
        ).all()

        org_account_ids = [acc.id for acc in org_accounts]

        if not org_account_ids:
            return CostMetrics(total_cost=Decimal('0.0'), spot_cost=Decimal('0.0'), on_demand_cost=Decimal('0.0'), currency="USD")

        # PRIORITY 1: Try Cost Explorer data (includes ALL AWS services)
        from backend.models.billing import DailyCost
        from sqlalchemy import func

        cost_explorer_query = self.db.query(
            func.sum(DailyCost.cost_amount).label('total')
        ).filter(
            and_(
                DailyCost.account_id.in_(org_account_ids),
                DailyCost.date >= start_date.date(),
                DailyCost.date <= end_date.date()
            )
        )

        # Apply team filter if specified
        if team_id:
            cost_explorer_query = cost_explorer_query.join(Account).join(User).filter(User.team_id == team_id)

        cost_explorer_total = cost_explorer_query.scalar()

        if cost_explorer_total and cost_explorer_total > 0:
            # Cost Explorer data available - use it (includes EC2, S3, RDS, VPC, etc.)
            # Project to monthly if we're looking at current month partial data
            mtd_cost = float(cost_explorer_total)

            projected_monthly_cost = mtd_cost
            logger.debug(f"Using Cost Explorer data: ${mtd_cost:.2f} for user {user_id}")

            # Get EC2-specific costs for spot/on-demand breakdown
            ec2_services = [
                'Amazon Elastic Compute Cloud - Compute',
                'EC2 - Other',
                'Amazon Elastic Container Service for Kubernetes'
            ]

            ec2_cost_query = self.db.query(
                func.sum(DailyCost.cost_amount).label('ec2_total')
            ).filter(
                and_(
                    DailyCost.account_id.in_(org_account_ids),
                    DailyCost.date >= start_date.date(),
                    DailyCost.date <= end_date.date(),
                    DailyCost.service_name.in_(ec2_services)
                )
            )

            if team_id:
                ec2_cost_query = ec2_cost_query.join(Account).join(User).filter(User.team_id == team_id)

            ec2_cost = ec2_cost_query.scalar() or 0

            # Use actual spot/on-demand instance ratio from DB instead of hardcoded split
            _cluster_ids = [c.id for c in self.db.query(Cluster.id).filter(
                Cluster.account_id.in_(org_account_ids)
            ).all()]

            _spot_count = 0
            _od_count = 0
            if _cluster_ids:
                from sqlalchemy import or_ as _or
                _inst_q = self.db.query(Instance).filter(
                    _or(
                        Instance.cluster_id.in_(_cluster_ids),
                        and_(Instance.cluster_id.is_(None), Instance.account_id.in_(org_account_ids))
                    ),
                    Instance.state.in_(['running', 'pending']),
                )
                _spot_count = _inst_q.filter(Instance.lifecycle == InstanceLifecycle.SPOT).count()
                _total_active = _inst_q.count()
                _od_count = _total_active - _spot_count

            _total_nodes = _spot_count + _od_count
            if _total_nodes > 0 and ec2_cost > 0:
                spot_ratio = _spot_count / _total_nodes
                spot_cost = Decimal(str(round(ec2_cost * spot_ratio, 2)))
                on_demand_cost = Decimal(str(round(ec2_cost * (1 - spot_ratio), 2)))
            else:
                spot_cost = Decimal('0.0')
                on_demand_cost = Decimal(str(ec2_cost))

            return CostMetrics(
                total_cost=Decimal(str(projected_monthly_cost)),
                spot_cost=spot_cost,
                on_demand_cost=on_demand_cost,
                currency="USD"
            )

        # FALLBACK: Calculate from EC2 instance pricing (less accurate, EC2 only)
        logger.debug(f"Cost Explorer data not available, falling back to EC2 instance calculation for user {user_id}")

        instance_query = self.db.query(Instance).join(Account).filter(
            Account.organization_id == user.organization_id
        )

        if cluster_id:
            instance_query = instance_query.filter(Instance.cluster_id == cluster_id)

        if team_id:
            instance_query = instance_query.join(User).filter(User.team_id == team_id)

        # Get active instances with pricing
        active_instances = instance_query.filter(
            Instance.state.in_(['running', 'pending'])
        ).all()

        # Calculate costs from instances
        total_cost = Decimal('0.0')
        spot_cost = Decimal('0.0')
        on_demand_cost = Decimal('0.0')

        for instance in active_instances:
            # Calculate hourly cost for instance
            hourly_cost = Decimal(str(instance.price)) if instance.price else Decimal('0.05')

            # Calculate hours in time range (ensure timezone-aware comparisons)
            # Make all datetimes timezone-aware for comparison
            tz_start_date = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date
            tz_end_date = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
            tz_now = datetime.now(timezone.utc)

            instance_created = instance.created_at
            if instance_created and instance_created.tzinfo is None:
                instance_created = instance_created.replace(tzinfo=timezone.utc)

            instance_start = max(instance_created, tz_start_date) if instance_created else tz_start_date
            instance_end = min(tz_now, tz_end_date)
            
            # Prevent negative hours if instance didn't exist in this time range
            if instance_end <= instance_start:
                continue
                
            hours = (instance_end - instance_start).total_seconds() / 3600

            instance_cost = hourly_cost * Decimal(str(hours))
            total_cost += instance_cost

            if instance.lifecycle == InstanceLifecycle.SPOT:
                spot_cost += instance_cost
            else:
                on_demand_cost += instance_cost

        return CostMetrics(
            total_cost=total_cost,
            spot_cost=spot_cost,
            on_demand_cost=on_demand_cost,
            currency="USD"
        )

    def _calculate_savings(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        cluster_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> SavingsBreakdown:
        """
        Calculate savings from spot instance usage

        Args:
            user_id: User UUID
            start_date: Start of time range
            end_date: End of time range
            cluster_id: Optional cluster filter

        Returns:
            SavingsBreakdown
        """
        # Get cost metrics
        cost_metrics = self._calculate_cost_metrics(
            user_id,
            start_date,
            end_date,
            cluster_id,
            team_id
        )

        # Calculate what it would cost if all spot instances were on-demand.
        # Use actual per-instance OD prices from the pricing helper instead of
        # the old hardcoded 70% discount assumption.
        spot_cost_float = float(cost_metrics.spot_cost)
        on_demand_float = float(cost_metrics.on_demand_cost)
        total_cost_float = float(cost_metrics.total_cost)

        # Sum up actual OD prices for running spot instances
        spot_equivalent_on_demand = 0.0
        try:
            from backend.utils.pricing_helper import get_pricing_helper
            _ph = get_pricing_helper()
            user = self.db.query(User).filter(User.id == user_id).first()
            if user and user.organization_id:
                _acc_ids = [a.id for a in self.db.query(Account.id).filter(
                    Account.organization_id == user.organization_id).all()]
                _cids = [c.id for c in self.db.query(Cluster.id).filter(
                    Cluster.account_id.in_(_acc_ids)).all()]
                from sqlalchemy import or_ as _or
                _spot_q = self.db.query(Instance).filter(
                    _or(
                        Instance.cluster_id.in_(_cids),
                        and_(Instance.cluster_id.is_(None), Instance.account_id.in_(_acc_ids))
                    ),
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state.in_(['running', 'pending']),
                )
                if cluster_id:
                    _spot_q = _spot_q.filter(Instance.cluster_id == cluster_id)
                for _si in _spot_q.all():
                    _region = _si.az[:-1] if _si.az else 'us-east-1'
                    _od_monthly = _ph.get_ec2_price(_region, _si.instance_type) if _si.instance_type else 0
                    _od_hourly = _od_monthly / 730.0 if _od_monthly > 0 else 0
                    # hours active in range
                    _created = _si.created_at
                    if _created and _created.tzinfo is None:
                        from datetime import timezone as _tz
                        _created = _created.replace(tzinfo=_tz.utc)
                    _s = max(_created, start_date.replace(tzinfo=_tz.utc) if start_date.tzinfo is None else start_date) if _created else (start_date.replace(tzinfo=_tz.utc) if start_date.tzinfo is None else start_date)
                    _e = min(datetime.now(timezone.utc), end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date)
                    _hrs = max(0, (_e - _s).total_seconds() / 3600)
                    spot_equivalent_on_demand += _od_hourly * _hrs
        except Exception as _e:
            logger.warning(f"Failed to compute real OD equivalent for savings: {_e}")
            # Fallback: assume average 65% discount (conservative)
            spot_equivalent_on_demand = spot_cost_float / 0.35 if spot_cost_float > 0 else 0.0

        total_if_on_demand = on_demand_float + spot_equivalent_on_demand

        # Calculate savings: EC2 scope only.
        # total_cost_float (from Cost Explorer) includes S3, RDS, VPC, etc.
        # Comparing EC2-only OD baseline against all-AWS spend produces negative savings.
        # Correct: savings = what spot EC2 would cost on OD - actual spot EC2 spend.
        ec2_spot_savings = spot_equivalent_on_demand - spot_cost_float
        total_savings = max(0.0, ec2_spot_savings)

        # Calculate percentage vs EC2-only all-OD baseline
        if total_if_on_demand > 0:
            savings_percentage = (total_savings / total_if_on_demand) * 100
        else:
            savings_percentage = 0.0

        # Calculate hibernation savings from schedules
        hibernation_savings = self._calculate_hibernation_savings(user_id, cluster_id, team_id)

        return SavingsBreakdown(
            total_savings=total_savings + hibernation_savings,
            spot_savings=total_savings,  # Savings from spot instances
            hibernation_savings=hibernation_savings,  # Savings from hibernation schedules
            savings_percentage=savings_percentage
        )

    def _calculate_hibernation_savings(
        self,
        user_id: str,
        cluster_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> float:
        """
        Calculate savings from active hibernation schedules.

        Args:
            user_id: User UUID
            cluster_id: Optional cluster filter
            team_id: Optional team filter

        Returns:
            Monthly hibernation savings in USD
        """
        try:
            from backend.models.hibernation_schedule import HibernationSchedule, HibernationStrategy

            # Query active hibernation schedules
            query = self.db.query(HibernationSchedule).filter(
                HibernationSchedule.is_active == "Y"
            )

            # Get accessible clusters for filtering
            accessible_clusters = self._get_accessible_clusters(user_id, cluster_id, team_id)
            cluster_ids = [c.id for c in accessible_clusters]

            if not cluster_ids:
                return 0.0

            # Calculate savings for each schedule
            total_savings = 0.0

            schedules = query.all()
            for schedule in schedules:
                # Check if any of the schedule's clusters are accessible
                schedule_cluster_ids = [c.id for c in schedule.clusters]
                accessible_schedule_clusters = set(schedule_cluster_ids) & set(cluster_ids)

                if not accessible_schedule_clusters:
                    continue

                # Calculate sleep hours per week from schedule matrix
                sleep_hours = schedule.schedule_matrix.count("1") if schedule.schedule_matrix else 0
                if sleep_hours == 0:
                    continue

                # Calculate sleep fraction
                sleep_fraction = sleep_hours / 168.0  # 168 hours in a week

                # Get total cost of accessible clusters in this schedule
                schedule_cost = 0.0
                for cluster in schedule.clusters:
                    if cluster.id in accessible_schedule_clusters:
                        schedule_cost += float(cluster.monthly_cost or 0.0)

                # Calculate savings based on strategy efficiency
                strategy_efficiency = {
                    HibernationStrategy.NAMESPACE_SLEEP.value: 0.80,
                    HibernationStrategy.NUCLEAR.value: 0.99,
                    HibernationStrategy.SNAPSHOT_RESTORE.value: 0.90
                }
                efficiency = strategy_efficiency.get(schedule.strategy, 0.80)

                # Monthly savings = sleep_fraction * cluster_cost * efficiency
                schedule_savings = sleep_fraction * schedule_cost * efficiency
                total_savings += schedule_savings

            logger.debug(f"Calculated hibernation savings: ${total_savings:.2f}/month")
            return total_savings

        except Exception as e:
            logger.error(f"Failed to calculate hibernation savings: {e}")
            return 0.0

    def _calculate_daily_cost(
        self,
        user_id: str,
        date: datetime,
        cluster_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> Decimal:
        """
        Calculate cost for a specific day

        Args:
            user_id: User UUID
            date: Date to calculate
            cluster_id: Optional cluster filter

        Returns:
            Daily cost
        """
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        cost_metrics = self._calculate_cost_metrics(
            user_id,
            start_of_day,
            end_of_day,
            cluster_id,
            team_id
        )

        return cost_metrics.total_cost

    def get_team_consolidated_stats(self, team_id: str) -> Dict[str, Any]:
        """
        Aggregates data from ALL members in a team for the Admin/Lead view.
        This provides the detailed "Consolidated View" feature with:
        - Top Spenders Leaderboard
        - Waste Distribution (for Pie Chart)
        - Cost Trends (for Area Chart)
        
        Args:
            team_id: Team UUID
            
        Returns:
            Dictionary with comprehensive consolidated stats
        """
        # 1. Identify all users in this team
        team_members = self.db.query(User).filter(User.team_id == team_id).all()
        member_ids = [str(u.id) for u in team_members]

        if not member_ids:
            return {
                "total_cost": 0.0,
                "total_waste": 0.0,
                "instance_count": 0,
                "cluster_count": 0,
                "member_count": 0,
                "account_count": 0,
                "efficiency_score": 100,
                "history": [],
                "top_spenders": [],
                "waste_distribution": []
            }

        # 2. Get All Accounts belonging to these members
        accounts = self.db.query(Account).filter(Account.user_id.in_(member_ids)).all()
        account_ids = [str(a.id) for a in accounts]

        # 3. Calculate Instance and Cluster counts
        total_instances = 0
        total_clusters = 0

        if account_ids:
            # Get clusters for these accounts
            total_clusters = self.db.query(Cluster).filter(
                Cluster.account_id.in_(account_ids)
            ).count()

            # Get instances (both cluster-based and standalone)
            total_instances = self.db.query(Instance).filter(
                Instance.account_id.in_(account_ids)
            ).count()

        # 4. Calculate Cost from Cost Explorer (projected monthly)
        total_cost = 0.0

        if account_ids:
            # PRIORITY 1: Use Cost Explorer data for accurate costs
            from backend.models.billing import DailyCost
            from datetime import datetime

            # Current month
            start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = datetime.now()

            cost_query = self.db.query(
                func.sum(DailyCost.cost_amount).label('total')
            ).filter(
                and_(
                    DailyCost.account_id.in_(account_ids),
                    DailyCost.date >= start_date.date(),
                    DailyCost.date <= end_date.date()
                )
            ).scalar()

            if cost_query and cost_query > 0:
                # Project MTD to full month
                days_elapsed = (end_date.date() - start_date.date()).days + 1
                total_cost = (float(cost_query) / days_elapsed) * 30
                logger.info(f"Team cost from Cost Explorer: ${total_cost:.2f} (projected monthly)")
            else:
                # FALLBACK: Calculate from EC2 instance prices
                hours_in_month = 720  # 30 days * 24 hours
                instances = self.db.query(Instance).filter(
                    Instance.account_id.in_(account_ids),
                    Instance.state.in_(['running', 'pending'])
                ).all()

                for instance in instances:
                    hourly_price = instance.price or Decimal('0.05')
                    monthly_cost = float(hourly_price) * hours_in_month
                    total_cost += monthly_cost
                logger.info(f"Team cost from EC2 instances: ${total_cost:.2f} (fallback)")
        
        # 5. Calculate Waste Distribution (for Pie Chart)
        # Query real hygiene data from cached scans in Redis or calculate from account data
        waste_categories = []
        
        # Try to get real data from hygiene_service if possible
        try:
            from backend.services.hygiene_service import HygieneService
            from backend.core.redis_client import get_redis_client
            import json
            
            hygiene_service = HygieneService(self.db)
            
            # Calculate waste from all team accounts
            total_volume_cost = 0.0
            total_snapshot_cost = 0.0
            total_ip_cost = 0.0
            total_instance_cost = 0.0
            total_lb_cost = 0.0
            total_rds_cost = 0.0
            
            for acc in accounts:
                # Try cache first
                redis_client = None
                try:
                    redis_client = get_redis_client()
                    cache_key = f"cleanup:scan:{acc.id}:ALL"
                    cached_data = redis_client.get(cache_key)
                    if cached_data:
                        data = json.loads(cached_data)
                        # Aggregate costs by resource type
                        for resource in data.get('resources', []):
                            if not resource.get('is_authorized', False):
                                cost = resource.get('cost_per_month', 0.0)
                                rtype = resource.get('type', '')
                                if rtype == 'VOLUME':
                                    total_volume_cost += cost
                                elif rtype == 'SNAPSHOT':
                                    total_snapshot_cost += cost
                                elif rtype == 'ELASTIC_IP':
                                    total_ip_cost += cost
                                elif rtype == 'INSTANCE':
                                    total_instance_cost += cost
                                elif rtype == 'LOAD_BALANCER':
                                    total_lb_cost += cost
                                elif rtype == 'RDS_DB':
                                    total_rds_cost += cost
                except Exception as e:
                    logger.warning(f"Could not fetch cleanup cache for {acc.id}: {e}")
                    continue
            
            waste_categories = [
                {"name": "Orphaned Volumes", "value": round(total_volume_cost, 2)},
                {"name": "Old Snapshots", "value": round(total_snapshot_cost, 2)},
                {"name": "Unused IPs", "value": round(total_ip_cost, 2)},
                {"name": "Idle Instances", "value": round(total_instance_cost, 2)},
                {"name": "Idle Load Balancers", "value": round(total_lb_cost, 2)},
                {"name": "Idle RDS", "value": round(total_rds_cost, 2)},
            ]
        except Exception as e:
            logger.warning(f"Failed to get real waste distribution, using estimates: {e}")
            # Fallback to estimate based on total_cost
            waste_categories = [
                {"name": "Orphaned Volumes", "value": round(total_cost * 0.06, 2)},
                {"name": "Stopped Instances", "value": round(total_cost * 0.04, 2)},
                {"name": "Old Snapshots", "value": round(total_cost * 0.03, 2)},
                {"name": "Unused IPs", "value": round(total_cost * 0.02, 2)},
            ]
        
        # Filter out zero values
        waste_distribution = [w for w in waste_categories if w["value"] > 0]
        total_waste = sum(w["value"] for w in waste_distribution)

        # 6. Build Top Spenders Leaderboard - Use Cost Explorer per member
        top_spenders = []
        for member in team_members:
            member_accounts = [a for a in accounts if str(a.user_id) == str(member.id)]
            member_account_ids = [str(a.id) for a in member_accounts]
            member_cost = 0.0

            if member_account_ids:
                # Try Cost Explorer first
                member_cost_query = self.db.query(
                    func.sum(DailyCost.cost_amount).label('total')
                ).filter(
                    and_(
                        DailyCost.account_id.in_(member_account_ids),
                        DailyCost.date >= start_date.date(),
                        DailyCost.date <= end_date.date()
                    )
                ).scalar()

                if member_cost_query and member_cost_query > 0:
                    # Project to monthly
                    days_elapsed = (end_date.date() - start_date.date()).days + 1
                    member_cost = (float(member_cost_query) / days_elapsed) * 30
                else:
                    # Fallback to EC2 instances
                    member_instances = self.db.query(Instance).filter(
                        Instance.account_id.in_(member_account_ids),
                        Instance.state.in_(['running', 'pending'])
                    ).all()

                    for instance in member_instances:
                        hourly_price = instance.price or Decimal('0.05')
                        monthly_cost = float(hourly_price) * 720  # 720 hours
                        member_cost += monthly_cost

            if member_cost > 0 or len(member_accounts) > 0:
                top_spenders.append({
                    "name": member.full_name or member.email.split('@')[0],
                    "email": member.email,
                    "cost": round(member_cost, 2),
                    "account_count": len(member_accounts)
                })

        # Sort by cost descending and take top 5
        top_spenders.sort(key=lambda x: x["cost"], reverse=True)
        top_spenders = top_spenders[:5]

        # 7. Calculate Efficiency Score (100 - waste percentage)
        efficiency_score = 100 if total_cost == 0 else round(100 - (total_waste / total_cost * 100), 1)

        # 8. Build monthly history for graph (last 4 weeks) using Cost Explorer
        history = []
        current_date = datetime.now(timezone.utc)

        for week_offset in range(3, -1, -1):  # 3, 2, 1, 0 (4 weeks ago to current)
            week_start = current_date - timedelta(weeks=week_offset, days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            # Calculate cost for this week from Cost Explorer
            week_cost = 0.0
            if account_ids:
                week_cost_query = self.db.query(
                    func.sum(DailyCost.cost_amount).label('total')
                ).filter(
                    and_(
                        DailyCost.account_id.in_(account_ids),
                        DailyCost.date >= week_start.date(),
                        DailyCost.date <= week_end.date()
                    )
                ).scalar()

                if week_cost_query and week_cost_query > 0:
                    week_cost = float(week_cost_query)
                else:
                    # Fallback to EC2 instances
                    week_instances = self.db.query(Instance).filter(
                        Instance.account_id.in_(account_ids),
                        Instance.state.in_(['running', 'pending'])
                    ).all()

                    for instance in week_instances:
                        if instance.created_at and instance.created_at <= week_end:
                            hourly_price = instance.price or Decimal('0.05')
                            hours_in_week = 168
                            week_cost += float(hourly_price) * hours_in_week

            week_label = week_start.strftime("%b %d")
            history.append({
                "name": week_label,
                "date": week_label,
                "cost": round(week_cost / 7, 2)  # Daily average for the week
            })

        return {
            "total_cost": round(total_cost, 2),
            "total_waste": round(total_waste, 2),
            "instance_count": total_instances,
            "cluster_count": total_clusters,
            "member_count": len(member_ids),
            "account_count": len(accounts),
            "efficiency_score": efficiency_score,
            "history": history,
            "top_spenders": top_spenders,
            "waste_distribution": waste_distribution
        }

    def get_account_consolidated_stats(self, account_id: str) -> Dict[str, Any]:
        """ Stats for a single AWS Account """
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return {"total_cost": 0, "history": []}

        # Instance Count and Cost Calculation
        total_clusters = self.db.query(Cluster).filter(Cluster.account_id == account_id).count()

        # Get all instances (both cluster-based and standalone)
        total_instances = self.db.query(Instance).filter(
            Instance.account_id == account_id
        ).count()

        # Calculate cost from Cost Explorer (projected monthly)
        total_cost = 0.0
        from backend.models.billing import DailyCost
        from datetime import datetime

        # Current month
        start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.now()

        cost_query = self.db.query(
            func.sum(DailyCost.cost_amount).label('total')
        ).filter(
            and_(
                DailyCost.account_id == account_id,
                DailyCost.date >= start_date.date(),
                DailyCost.date <= end_date.date()
            )
        ).scalar()

        if cost_query and cost_query > 0:
            # Project MTD to full month
            days_elapsed = (end_date.date() - start_date.date()).days + 1
            total_cost = (float(cost_query) / days_elapsed) * 30
            logger.info(f"Account cost from Cost Explorer: ${total_cost:.2f} (projected monthly)")
        else:
            # Fallback: Calculate from EC2 instance prices
            hours_in_month = 720
            instances = self.db.query(Instance).filter(
                Instance.account_id == account_id,
                Instance.state.in_(['running', 'pending'])
            ).all()

            for instance in instances:
                hourly_price = instance.price or Decimal('0.05')
                monthly_cost = float(hourly_price) * hours_in_month
                total_cost += monthly_cost
            logger.info(f"Account cost from EC2 instances: ${total_cost:.2f} (fallback)")
        
        # Waste Distribution - Get real data from cleanup cache
        waste_categories = []
        try:
            from backend.core.redis_client import get_redis_client
            import json
            
            redis_client = get_redis_client()
            cache_key = f"cleanup:scan:{account_id}:ALL"
            cached_data = redis_client.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                # Aggregate costs by resource type
                total_volume_cost = 0.0
                total_snapshot_cost = 0.0
                total_ip_cost = 0.0
                total_instance_cost = 0.0
                total_lb_cost = 0.0
                total_rds_cost = 0.0
                
                for resource in data.get('resources', []):
                    if not resource.get('is_authorized', False):
                        cost = resource.get('cost_per_month', 0.0)
                        rtype = resource.get('type', '')
                        if rtype == 'VOLUME':
                            total_volume_cost += cost
                        elif rtype == 'SNAPSHOT':
                            total_snapshot_cost += cost
                        elif rtype == 'ELASTIC_IP':
                            total_ip_cost += cost
                        elif rtype == 'INSTANCE':
                            total_instance_cost += cost
                        elif rtype == 'LOAD_BALANCER':
                            total_lb_cost += cost
                        elif rtype == 'RDS_DB':
                            total_rds_cost += cost
                
                waste_categories = [
                    {"name": "Orphaned Volumes", "value": round(total_volume_cost, 2)},
                    {"name": "Old Snapshots", "value": round(total_snapshot_cost, 2)},
                    {"name": "Unused IPs", "value": round(total_ip_cost, 2)},
                    {"name": "Idle Instances", "value": round(total_instance_cost, 2)},
                    {"name": "Idle Load Balancers", "value": round(total_lb_cost, 2)},
                    {"name": "Idle RDS", "value": round(total_rds_cost, 2)},
                ]
            else:
                # No cached data - fallback to estimates
                waste_categories = [
                    {"name": "Orphaned Volumes", "value": round(total_cost * 0.06, 2)},
                    {"name": "Stopped Instances", "value": round(total_cost * 0.04, 2)},
                    {"name": "Old Snapshots", "value": round(total_cost * 0.03, 2)},
                    {"name": "Unused IPs", "value": round(total_cost * 0.02, 2)},
                ]
        except Exception as e:
            logger.warning(f"Failed to get real waste for account {account_id}: {e}")
            # Fallback to estimates
            waste_categories = [
                {"name": "Orphaned Volumes", "value": round(total_cost * 0.06, 2)},
                {"name": "Stopped Instances", "value": round(total_cost * 0.04, 2)},
                {"name": "Old Snapshots", "value": round(total_cost * 0.03, 2)},
                {"name": "Unused IPs", "value": round(total_cost * 0.02, 2)},
            ]
        
        waste_distribution = [w for w in waste_categories if w["value"] > 0]
        total_waste = sum(w["value"] for w in waste_distribution)
        
        efficiency_score = 100 if total_cost == 0 else round(100 - (total_waste / total_cost * 100), 1)

        # Build monthly history (last 4 weeks) using Cost Explorer
        history = []
        current_date = datetime.now(timezone.utc)

        for week_offset in range(3, -1, -1):
            week_start = current_date - timedelta(weeks=week_offset, days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            week_cost = 0.0
            # Try Cost Explorer first
            week_cost_query = self.db.query(
                func.sum(DailyCost.cost_amount).label('total')
            ).filter(
                and_(
                    DailyCost.account_id == account_id,
                    DailyCost.date >= week_start.date(),
                    DailyCost.date <= week_end.date()
                )
            ).scalar()

            if week_cost_query and week_cost_query > 0:
                week_cost = float(week_cost_query)
            else:
                # Fallback to EC2 instances
                week_instances = self.db.query(Instance).filter(
                    Instance.account_id == account_id,
                    Instance.state.in_(['running', 'pending'])
                ).all()

                for instance in week_instances:
                    if instance.created_at and instance.created_at <= week_end:
                        hourly_price = instance.price or Decimal('0.05')
                        hours_in_week = 168
                        week_cost += float(hourly_price) * hours_in_week

            week_label = week_start.strftime("%b %d")
            history.append({
               "name": week_label,
               "date": week_label,
               "cost": round(week_cost / 7, 2)  # Daily average for the week
            })
            
        return {
            "total_cost": round(total_cost, 2),
            "total_waste": round(total_waste, 2),
            "instance_count": total_instances,
            "cluster_count": total_clusters,
            "efficiency_score": efficiency_score,
            "history": history,
            "waste_distribution": waste_distribution
        }

    def get_cost_breakdown_by_service(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get cost breakdown by AWS service category for resource hygiene.

        Groups services into:
        - EC2 (Compute)
        - Storage (S3, EBS, EFS)
        - Database (RDS, DynamoDB)
        - Networking (VPC, Data Transfer, Load Balancers)
        - Others (All remaining services)

        Args:
            user_id: User UUID
            start_date: Start date
            end_date: End date
            team_id: Optional team filter

        Returns:
            {
                "total_cost": 46.41,
                "breakdown": [
                    {"category": "EC2", "cost": 22.62, "percentage": 48.7, "services": ["EC2 - Other", "EC2 - Compute"]},
                    {"category": "Networking", "cost": 8.10, "percentage": 17.5, "services": ["VPC"]},
                    {"category": "Others", "cost": 15.69, "percentage": 33.8, "services": ["Security Hub", "KMS", ...]}
                ]
            }
        """
        # Get user and organization
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
            return {"total_cost": 0.0, "breakdown": []}

        # Get organization account IDs
        org_accounts = self.db.query(Account.id).filter(
            Account.organization_id == user.organization_id
        ).all()

        org_account_ids = [acc.id for acc in org_accounts]

        if not org_account_ids:
            return {"total_cost": 0.0, "breakdown": []}

        # Query Cost Explorer data
        from backend.models.billing import DailyCost
        from sqlalchemy import func

        cost_query = self.db.query(
            DailyCost.service_name,
            func.sum(DailyCost.cost_amount).label('cost')
        ).filter(
            and_(
                DailyCost.account_id.in_(org_account_ids),
                DailyCost.date >= start_date.date(),
                DailyCost.date <= end_date.date()
            )
        ).group_by(DailyCost.service_name)

        # Apply team filter if specified
        if team_id:
            cost_query = cost_query.join(Account).join(User).filter(User.team_id == team_id)

        service_costs = cost_query.all()

        if not service_costs:
            # No Cost Explorer data, return EC2 fallback
            cost_metrics = self._calculate_cost_metrics(user_id, start_date, end_date, None, team_id)
            return {
                "total_cost": float(cost_metrics.total_cost),
                "breakdown": [
                    {
                        "category": "EC2",
                        "cost": float(cost_metrics.total_cost),
                        "percentage": 100.0,
                        "services": ["EC2 Instances (estimated)"]
                    }
                ]
            }

        # Categorize services
        categories = {
            "EC2": [],
            "Storage": [],
            "Database": [],
            "Networking": [],
            "Others": []
        }

        service_categorization = {
            "EC2": ["Amazon Elastic Compute Cloud - Compute", "EC2 - Other", "Amazon Elastic Container Service for Kubernetes", "Amazon Elastic Container Service"],
            "Storage": ["Amazon Simple Storage Service", "Amazon Elastic Block Store", "Amazon Elastic File System", "AWS Backup"],
            "Database": ["Amazon Relational Database Service", "Amazon DynamoDB", "Amazon ElastiCache", "Amazon Redshift"],
            "Networking": ["Amazon Virtual Private Cloud", "AWS Data Transfer", "Elastic Load Balancing", "Amazon CloudFront", "Amazon Route 53"]
        }

        total_cost = 0.0

        for service, cost in service_costs:
            total_cost += float(cost)
            categorized = False

            for category, service_list in service_categorization.items():
                if any(svc in service for svc in service_list):
                    categories[category].append({"service": service, "cost": float(cost)})
                    categorized = True
                    break

            if not categorized:
                categories["Others"].append({"service": service, "cost": float(cost)})

        # Build breakdown response
        breakdown = []
        for category, services in categories.items():
            if services:
                category_cost = sum(s["cost"] for s in services)
                service_names = [s["service"] for s in services]

                breakdown.append({
                    "category": category,
                    "cost": round(category_cost, 2),
                    "percentage": round((category_cost / total_cost * 100) if total_cost > 0 else 0, 1),
                    "services": service_names
                })

        # Sort by cost descending
        breakdown.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "total_cost": round(total_cost, 2),
            "breakdown": breakdown
        }

    def get_waste_breakdown(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get A+B waste breakdown for Financial Engineering Dashboard.

        A = Hygiene Waste (orphaned resources)
        B = Optimization Waste (inefficient configurations)

        Returns:
            {
                "hygiene_waste": {...},  # A
                "optimization_waste": {...},  # B
                "total_waste": float,  # A+B
                "current_spend": float,
                "optimized_spend": float,
                "savings_percentage": float
            }
        """
        # Default to current month
        if not start_date:
            start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not end_date:
            end_date = datetime.now()

        # Get user's organization and accounts
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")

        org_accounts = self.db.query(Account).filter(
            Account.organization_id == user.organization_id
        ).all()
        org_account_ids = [acc.id for acc in org_accounts]

        # A: HYGIENE WASTE (from hygiene scan results)
        # Query orphaned/unattached resources with costs
        hygiene_waste = {
            "orphaned_volumes": Decimal('0'),
            "orphaned_snapshots": Decimal('0'),
            "unused_eips": Decimal('0'),
            "idle_load_balancers": Decimal('0'),
            "idle_rds": Decimal('0'),
            "total": Decimal('0')
        }

        # B: OPTIMIZATION WASTE (from optimization scans)
        optimization_waste = {
            "ri_waste": Decimal('0'),
            "s3_lifecycle": Decimal('0'),
            "rds_multiaz": Decimal('0'),
            "data_transfer": Decimal('0'),
            "total": Decimal('0')
        }

        # Get current monthly spend from Cost Explorer
        from backend.models.billing import DailyCost
        cost_query = self.db.query(
            func.sum(DailyCost.cost_amount).label('total')
        ).filter(
            DailyCost.account_id.in_(org_account_ids),
            DailyCost.date >= start_date.date(),
            DailyCost.date <= end_date.date()
        ).first()

        mtd_cost = float(cost_query.total) if cost_query and cost_query.total else 0.0
        days_elapsed = (end_date.date() - start_date.date()).days + 1
        current_spend = (mtd_cost / days_elapsed) * 30  # Project to monthly

        # Calculate totals
        hygiene_total = float(hygiene_waste["total"])
        optimization_total = float(optimization_waste["total"])
        total_waste = hygiene_total + optimization_total

        # Calculate optimized spend and savings percentage
        optimized_spend = max(0, current_spend - total_waste)
        savings_percentage = (total_waste / current_spend * 100) if current_spend > 0 else 0.0

        return {
            "hygiene_waste": {
                "orphaned_volumes": float(hygiene_waste["orphaned_volumes"]),
                "orphaned_snapshots": float(hygiene_waste["orphaned_snapshots"]),
                "unused_eips": float(hygiene_waste["unused_eips"]),
                "idle_load_balancers": float(hygiene_waste["idle_load_balancers"]),
                "idle_rds": float(hygiene_waste["idle_rds"]),
                "total": hygiene_total
            },
            "optimization_waste": {
                "ri_waste": float(optimization_waste["ri_waste"]),
                "s3_lifecycle": float(optimization_waste["s3_lifecycle"]),
                "rds_multiaz": float(optimization_waste["rds_multiaz"]),
                "data_transfer": float(optimization_waste["data_transfer"]),
                "total": optimization_total
            },
            "total_waste": round(total_waste, 2),
            "current_spend": round(current_spend, 2),
            "optimized_spend": round(optimized_spend, 2),
            "savings_percentage": round(savings_percentage, 1)
        }


def get_metrics_service(db: Session) -> MetricsService:
    """Get metrics service instance"""
    return MetricsService(db)
