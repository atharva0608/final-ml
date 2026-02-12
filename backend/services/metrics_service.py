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
                instance_query = self.db.query(Instance).filter(
                    Instance.cluster_id.in_(cluster_ids)
                )
            else:
                # No clusters, only count standalone instances
                # Note: Standalone instances don't have a direct account_id link in current schema
                # They should be assigned to a cluster during discovery
                instance_query = self.db.query(Instance).filter(Instance.id == None)  # Returns no results

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

        # Base query - get all instances (cluster-based and standalone)
        instance_query = self.db.query(Instance).join(Account).filter(
            Account.organization_id == user.organization_id
        )

        if cluster_id:
            instance_query = instance_query.filter(Instance.cluster_id == cluster_id)

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
            # Convert price to Decimal to avoid type mismatch
            hourly_cost = Decimal(str(instance.price)) if instance.price else Decimal('0.05')

            # Calculate hours in time range
            instance_start = max(instance.created_at, start_date) if instance.created_at else start_date
            instance_end = min(datetime.utcnow(), end_date)
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
            # Get clusters for these accounts
            total_clusters = self.db.query(Cluster).filter(
                Cluster.account_id.in_(account_ids)
            ).count()

            # Get instances (both cluster-based and standalone)
            total_instances = self.db.query(Instance).filter(
                Instance.account_id.in_(account_ids)
            ).count()

        # 4. Calculate Cost from actual instance prices
        total_cost = 0.0
        hours_in_month = 720  # 30 days * 24 hours

        if account_ids:
            # Sum actual instance prices (hourly rate * hours in month)
            # Get all instances (both cluster-based and standalone)
            instances = self.db.query(Instance).filter(
                Instance.account_id.in_(account_ids),
                Instance.state.in_(['running', 'pending'])
            ).all()

            for instance in instances:
                # Use actual instance price if available, otherwise use fallback
                hourly_price = instance.price or Decimal('0.05')
                monthly_cost = float(hourly_price) * hours_in_month
                total_cost += monthly_cost
        
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

        # 6. Build Top Spenders Leaderboard - Calculate from actual instance costs
        top_spenders = []
        for member in team_members:
            member_accounts = [a for a in accounts if str(a.user_id) == str(member.id)]
            member_cost = 0.0

            for acc in member_accounts:
                # Get all instances (both cluster-based and standalone)
                member_instances = self.db.query(Instance).filter(
                    Instance.account_id == str(acc.id),
                    Instance.state.in_(['running', 'pending'])
                ).all()

                for instance in member_instances:
                    hourly_price = instance.price or Decimal('0.05')
                    monthly_cost = float(hourly_price) * hours_in_month
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

        # 8. Build monthly history for graph (last 4 weeks)
        history = []
        current_date = datetime.utcnow()

        for week_offset in range(3, -1, -1):  # 3, 2, 1, 0 (4 weeks ago to current)
            week_start = current_date - timedelta(weeks=week_offset, days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            # Calculate cost for this week based on instances that were running
            week_cost = 0.0
            if account_ids:
                # Get all instances (both cluster-based and standalone)
                week_instances = self.db.query(Instance).filter(
                    Instance.account_id.in_(account_ids),
                    Instance.state.in_(['running', 'pending'])
                ).all()

                for instance in week_instances:
                    # Check if instance was created before week end
                    if instance.created_at and instance.created_at <= week_end:
                        hourly_price = instance.price or Decimal('0.05')
                        # Calculate hours this instance ran during the week (max 168 hours per week)
                        hours_in_week = 168
                        week_cost += float(hourly_price) * hours_in_week

            week_label = week_start.strftime("%b %d")
            history.append({
                "name": week_label,
                "date": week_label,
                "cost": round(week_cost / 7, 2)  # Divide by 7 to get daily average for the week
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

        # Calculate real cost from instance prices
        total_cost = 0.0
        hours_in_month = 720

        # Get all instances (both cluster-based and standalone)
        instances = self.db.query(Instance).filter(
            Instance.account_id == account_id,
            Instance.state.in_(['running', 'pending'])
        ).all()

        for instance in instances:
            hourly_price = instance.price or Decimal('0.05')
            monthly_cost = float(hourly_price) * hours_in_month
            total_cost += monthly_cost
        
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

        # Build monthly history (last 4 weeks)
        history = []
        current_date = datetime.utcnow()

        for week_offset in range(3, -1, -1):
            week_start = current_date - timedelta(weeks=week_offset, days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            week_cost = 0.0
            # Get all instances (both cluster-based and standalone)
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
               "cost": round(week_cost / 7, 2)
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
