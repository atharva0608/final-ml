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

        instance_query = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.organization_id == user.organization_id
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

        # Base query
        instance_query = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.organization_id == user.organization_id
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
        spot = instance_query.filter(Instance.lifecycle == InstanceLifecycle.SPOT).count()
        on_demand = instance_query.filter(Instance.lifecycle == InstanceLifecycle.ON_DEMAND).count()

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
        cluster_id: Optional[str] = None,
        team_id: Optional[str] = None
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
        # Get user and organization
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
            return CostMetrics(total_cost=Decimal('0.0'), spot_cost=Decimal('0.0'), on_demand_cost=Decimal('0.0'), currency="USD")

        # Base query
        instance_query = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.organization_id == user.organization_id
        )

        if cluster_id:
            instance_query = instance_query.filter(Cluster.id == cluster_id)

        if team_id:
            # Filter by team via Account -> User -> Team
            instance_query = instance_query.join(User).filter(User.team_id == team_id)

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

        # Calculate what it would cost if all were on-demand
        # Assume 70% average spot discount
        spot_cost_float = float(cost_metrics.spot_cost)
        on_demand_float = float(cost_metrics.on_demand_cost)
        total_cost_float = float(cost_metrics.total_cost)
        
        spot_equivalent_on_demand = spot_cost_float / 0.3 if spot_cost_float > 0 else 0.0
        total_if_on_demand = on_demand_float + spot_equivalent_on_demand

        # Calculate savings
        total_savings = total_if_on_demand - total_cost_float

        # Calculate percentage
        if total_if_on_demand > 0:
            savings_percentage = (total_savings / total_if_on_demand) * 100
        else:
            savings_percentage = 0.0

        return SavingsBreakdown(
            total_savings=total_savings,
            spot_savings=total_savings,  # All savings from spot
            hibernation_savings=0.0,  # TODO: Calculate from hibernation
            savings_percentage=savings_percentage
        )

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
            total_instances = self.db.query(Instance).filter(
                Instance.account_id.in_(account_ids)
            ).count()
            
            total_clusters = self.db.query(Cluster).filter(
                Cluster.account_id.in_(account_ids)
            ).count()

        # 4. Calculate Cost (simulated - in production, sum from CostMetric table)
        avg_hourly_cost = Decimal('0.05')  # Average hourly cost per instance
        hours_in_month = 720
        total_cost = float(total_instances * avg_hourly_cost * hours_in_month)
        
        # 5. Calculate Waste Distribution (for Pie Chart)
        # Query real cleanup data from cached scans in Redis or calculate from account data
        waste_categories = []
        
        # Try to get real data from cleanup_service if possible
        try:
            from backend.services.cleanup_service import CleanupService
            from backend.core.redis_client import get_redis_client
            import json
            
            cleanup_service = CleanupService(self.db)
            
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

        # 6. Build Top Spenders Leaderboard
        # In production, query CostMetric grouped by user
        top_spenders = []
        for i, member in enumerate(team_members[:5]):  # Top 5
            member_accounts = [a for a in accounts if str(a.user_id) == str(member.id)]
            member_instances = 0
            for acc in member_accounts:
                member_instances += self.db.query(Instance).filter(
                    Instance.account_id == str(acc.id)
                ).count()
            
            member_cost = float(member_instances * avg_hourly_cost * hours_in_month)
            if member_cost > 0 or len(member_accounts) > 0:
                top_spenders.append({
                    "name": member.full_name or member.email.split('@')[0],
                    "email": member.email,
                    "cost": round(member_cost, 2),
                    "account_count": len(member_accounts)
                })
        
        # Sort by cost descending
        top_spenders.sort(key=lambda x: x["cost"], reverse=True)

        # 7. Calculate Efficiency Score (100 - waste percentage)
        efficiency_score = 100 if total_cost == 0 else round(100 - (total_waste / total_cost * 100), 1)

        # 8. Build weekly history for graph
        history = []
        for week in range(4):
            week_factor = 0.25 * (week + 1)  # Simulates growing cost over weeks
            history.append({
                "name": f"Week {week + 1}",
                "date": f"Week {week + 1}",
                "cost": round(total_cost * week_factor, 2)
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
            
        # Instance Count
        total_instances = self.db.query(Instance).filter(Instance.account_id == account_id).count()
        total_clusters = self.db.query(Cluster).filter(Cluster.account_id == account_id).count()
        
        # Cost (Mock)
        avg_hourly_cost = Decimal('0.05')
        hours_in_month = 720
        total_cost = float(total_instances * avg_hourly_cost * hours_in_month)
        
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
        
        history = []
        for week in range(4):
            week_factor = 0.25 * (week + 1)
            history.append({
               "name": f"Week {week + 1}",
               "date": f"Week {week + 1}",
               "cost": round(total_cost * week_factor, 2)
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


def get_metrics_service(db: Session) -> MetricsService:
    """Get metrics service instance"""
    return MetricsService(db)
