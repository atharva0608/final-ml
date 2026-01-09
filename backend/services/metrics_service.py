"""
Metrics Service

Business logic for KPI calculation and dashboard metrics
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from backend.models.instance import Instance
from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.models.optimization_job import OptimizationJob
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
from datetime import datetime, timedelta
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
        start_date = filters.start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = filters.end_date or datetime.utcnow()

        # Base query for user's instances
        instance_query = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.user_id == user_id
        )

        # Apply cluster filter if specified
        if filters.cluster_id:
            instance_query = instance_query.filter(Cluster.id == filters.cluster_id)

        # Total instances
        total_instances = instance_query.count()

        # Active instances
        active_instances = instance_query.filter(
            Instance.state.in_(['running', 'pending'])
        ).count()

        # Spot vs On-Demand split
        spot_instances = instance_query.filter(
            and_(
                Instance.lifecycle == 'spot',
                Instance.state.in_(['running', 'pending'])
            )
        ).count()

        on_demand_instances = active_instances - spot_instances

        # Calculate costs
        cost_metrics = self._calculate_cost_metrics(
            user_id,
            start_date,
            end_date,
            filters.cluster_id
        )

        # Calculate savings
        savings_metrics = self._calculate_savings(
            user_id,
            start_date,
            end_date,
            filters.cluster_id
        )

        # Optimization jobs
        job_query = self.db.query(OptimizationJob).join(Cluster).join(Account).filter(
            and_(
                Account.user_id == user_id,
                OptimizationJob.created_at >= start_date,
                OptimizationJob.created_at <= end_date
            )
        )

        if filters.cluster_id:
            job_query = job_query.filter(OptimizationJob.cluster_id == filters.cluster_id)

        total_optimizations = job_query.count()
        successful_optimizations = job_query.filter(
            OptimizationJob.status == 'completed'
        ).count()

        logger.info(
            "Dashboard KPIs calculated",
            user_id=user_id,
            total_instances=total_instances,
            active_instances=active_instances,
            total_cost=float(cost_metrics.total_cost)
        )

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
        start_date = filters.start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = filters.end_date or datetime.utcnow()

        return self._calculate_cost_metrics(
            user_id,
            start_date,
            end_date,
            filters.cluster_id
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
        # Base query
        instance_query = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.user_id == user_id
        )

        if filters.cluster_id:
            instance_query = instance_query.filter(Cluster.id == filters.cluster_id)

        # Count by state
        running = instance_query.filter(Instance.state == 'running').count()
        pending = instance_query.filter(Instance.state == 'pending').count()
        stopping = instance_query.filter(Instance.state == 'stopping').count()
        stopped = instance_query.filter(Instance.state == 'stopped').count()
        terminated = instance_query.filter(Instance.state == 'terminated').count()

        # Count by lifecycle
        spot = instance_query.filter(Instance.lifecycle == 'spot').count()
        on_demand = instance_query.filter(Instance.lifecycle == 'on-demand').count()

        # Count by architecture
        amd64 = instance_query.filter(Instance.architecture == 'amd64').count()
        arm64 = instance_query.filter(Instance.architecture == 'arm64').count()

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
            arm64_instances=arm64
        )

    def get_cost_time_series(
        self,
        user_id: str,
        filters: MetricFilter
    ) -> TimeSeriesData:
        """
        Get cost metrics over time

        Args:
            user_id: User UUID
            filters: Time range and cluster filters

        Returns:
            TimeSeriesData with daily cost data
        """
        start_date = filters.start_date or (datetime.utcnow() - timedelta(days=30))
        end_date = filters.end_date or datetime.utcnow()

        # Generate daily time series
        # This is a simplified version - in production, you'd query actual cost data
        data_points: List[TimeSeriesPoint] = []

        current_date = start_date
        while current_date <= end_date:
            # Calculate cost for this day
            day_cost = self._calculate_daily_cost(
                user_id,
                current_date,
                filters.cluster_id
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
        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.user_id == user_id
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
                Instance.lifecycle == 'spot',
                Instance.state.in_(['running', 'pending'])
            )
        ).count()

        # Recent optimization
        last_optimization = self.db.query(OptimizationJob).filter(
            OptimizationJob.cluster_id == cluster_id
        ).order_by(desc(OptimizationJob.created_at)).first()

        return ClusterMetrics(
            cluster_id=cluster_id,
            cluster_name=cluster.name,
            total_instances=total_instances,
            active_instances=active_instances,
            spot_instances=spot_instances,
            on_demand_instances=active_instances - spot_instances,
            last_optimization=last_optimization.created_at if last_optimization else None,
            status=cluster.status.value
        )

    def _calculate_cost_metrics(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        cluster_id: Optional[str] = None
    ) -> CostMetrics:
        """
        Calculate cost metrics for time range

        Args:
            user_id: User UUID
            start_date: Start of time range
            end_date: End of time range
            cluster_id: Optional cluster filter

        Returns:
            CostMetrics
        """
        # Base query
        instance_query = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.user_id == user_id
        )

        if cluster_id:
            instance_query = instance_query.filter(Cluster.id == cluster_id)

        # Get active instances with pricing
        active_instances = instance_query.filter(
            Instance.state.in_(['running', 'pending'])
        ).all()

        # Calculate costs
        total_cost = Decimal('0.0')
        spot_cost = Decimal('0.0')
        on_demand_cost = Decimal('0.0')

        for instance in active_instances:
            # Calculate hourly cost for instance
            # This is simplified - in production, you'd use actual AWS pricing
            hourly_cost = instance.price_per_hour or Decimal('0.0')

            # Calculate hours in time range
            instance_start = max(instance.launch_time, start_date) if instance.launch_time else start_date
            instance_end = min(datetime.utcnow(), end_date)
            hours = (instance_end - instance_start).total_seconds() / 3600

            instance_cost = hourly_cost * Decimal(str(hours))
            total_cost += instance_cost

            if instance.lifecycle == 'spot':
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
        cluster_id: Optional[str] = None
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
            cluster_id
        )

        # Calculate what it would cost if all were on-demand
        # Assume 70% average spot discount
        spot_equivalent_on_demand = cost_metrics.spot_cost / Decimal('0.3')
        total_if_on_demand = cost_metrics.on_demand_cost + spot_equivalent_on_demand

        # Calculate savings
        total_savings = total_if_on_demand - cost_metrics.total_cost

        # Calculate percentage
        if total_if_on_demand > 0:
            savings_percentage = float((total_savings / total_if_on_demand) * 100)
        else:
            savings_percentage = 0.0

        return SavingsBreakdown(
            total_savings=total_savings,
            spot_savings=total_savings,  # All savings from spot
            hibernation_savings=Decimal('0.0'),  # TODO: Calculate from hibernation
            savings_percentage=savings_percentage
        )

    def _calculate_daily_cost(
        self,
        user_id: str,
        date: datetime,
        cluster_id: Optional[str] = None
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
            cluster_id
        )

        return cost_metrics.total_cost


def get_metrics_service(db: Session) -> MetricsService:
    """Get metrics service instance"""
    return MetricsService(db)
