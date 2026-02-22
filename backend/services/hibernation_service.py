"""
Hibernation Schedule Service

Manages hibernation schedules for clusters, including CRUD operations,
conflict detection, next execution time calculation, and savings estimation.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import pytz
import uuid
from backend.models.hibernation_schedule import (
    HibernationSchedule,
    HibernationStrategy,
    ScheduleType
)
from backend.models.cluster import Cluster
from backend.models.hibernation_schedule_clusters import hibernation_schedule_clusters
from backend.core.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    ConflictError
)
import logging

logger = logging.getLogger(__name__)


class HibernationService:
    """Service for managing hibernation schedules"""

    def __init__(self, db: Session):
        self.db = db

    def list_schedules(
        self,
        cluster_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[HibernationSchedule], int]:
        """
        List hibernation schedules with optional filtering

        Args:
            cluster_id: Filter by cluster ID
            is_active: Filter by active status
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (schedules list, total count)
        """
        query = self.db.query(HibernationSchedule)

        # Filter by cluster
        if cluster_id:
            query = query.join(
                hibernation_schedule_clusters,
                HibernationSchedule.id == hibernation_schedule_clusters.c.schedule_id
            ).filter(hibernation_schedule_clusters.c.cluster_id == cluster_id)

        # Filter by active status
        if is_active is not None:
            query = query.filter(
                HibernationSchedule.is_active == ("Y" if is_active else "N")
            )

        # Get total count
        total = query.count()

        # Paginate
        offset = (page - 1) * page_size
        schedules = query.order_by(
            HibernationSchedule.created_at.desc()
        ).offset(offset).limit(page_size).all()

        return schedules, total

    def get_schedule(self, schedule_id: str) -> HibernationSchedule:
        """Get schedule by ID"""
        schedule = self.db.query(HibernationSchedule).filter(
            HibernationSchedule.id == schedule_id
        ).first()

        if not schedule:
            raise ResourceNotFoundError("HibernationSchedule", schedule_id)

        return schedule

    def create_schedule(
        self,
        name: str,
        schedule_matrix: str,
        strategy: HibernationStrategy,
        cluster_ids: List[str],
        description: Optional[str] = None,
        schedule_type: ScheduleType = ScheduleType.WEEKLY,
        date_overrides: Optional[Dict[str, int]] = None,
        timezone: str = "UTC",
        pre_warm_minutes: int = 30,
        is_active: bool = True
    ) -> HibernationSchedule:
        """Create a new hibernation schedule"""
        # Validate inputs
        self._validate_schedule_matrix(schedule_matrix, schedule_type)
        self._validate_timezone(timezone)
        self._validate_clusters(cluster_ids)

        # Check for conflicts
        conflicts = self.check_conflicts(cluster_ids, schedule_matrix, schedule_type)
        if conflicts:
            conflict_names = [c["schedule_name"] for c in conflicts]
            raise ConflictError(
                f"Schedule conflicts with existing schedules: {', '.join(conflict_names)}"
            )

        # Create schedule
        schedule = HibernationSchedule(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            schedule_type=schedule_type.value,
            schedule_matrix=schedule_matrix,
            date_overrides=date_overrides or {},
            timezone=timezone,
            pre_warm_minutes=pre_warm_minutes,
            is_active="Y" if is_active else "N",
            strategy=strategy.value,
            saved_state={},
            az_affinity={}
        )

        self.db.add(schedule)

        # Attach clusters
        for cluster_id in cluster_ids:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if cluster:
                schedule.clusters.append(cluster)

        self.db.commit()
        self.db.refresh(schedule)

        logger.info(f"Created hibernation schedule: {schedule.id} ({schedule.name})")
        return schedule

    def update_schedule(self, schedule_id: str, **updates) -> HibernationSchedule:
        """Update an existing schedule"""
        schedule = self.get_schedule(schedule_id)

        # Handle cluster updates
        if "cluster_ids" in updates:
            cluster_ids = updates.pop("cluster_ids")
            self._validate_clusters(cluster_ids)

            # Clear and reassign clusters
            schedule.clusters = []
            for cluster_id in cluster_ids:
                cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
                if cluster:
                    schedule.clusters.append(cluster)

        # Convert is_active
        if "is_active" in updates:
            updates["is_active"] = "Y" if updates["is_active"] else "N"

        # Convert enums
        if "strategy" in updates:
            updates["strategy"] = updates["strategy"].value
        if "schedule_type" in updates:
            updates["schedule_type"] = updates["schedule_type"].value

        # Update fields
        for key, value in updates.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)

        schedule.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(schedule)

        return schedule

    def delete_schedule(self, schedule_id: str) -> None:
        """Delete a hibernation schedule"""
        schedule = self.get_schedule(schedule_id)
        schedule.clusters = []
        self.db.delete(schedule)
        self.db.commit()
        logger.info(f"Deleted hibernation schedule: {schedule_id}")

    def toggle_schedule(self, schedule_id: str, is_active: bool) -> HibernationSchedule:
        """Activate or pause a schedule"""
        schedule = self.get_schedule(schedule_id)
        schedule.is_active = "Y" if is_active else "N"
        schedule.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def check_conflicts(
        self,
        cluster_ids: List[str],
        schedule_matrix: str,
        schedule_type: ScheduleType,
        exclude_schedule_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Check for schedule conflicts on the same clusters"""
        conflicts = []

        query = self.db.query(HibernationSchedule).join(
            hibernation_schedule_clusters,
            HibernationSchedule.id == hibernation_schedule_clusters.c.schedule_id
        ).filter(
            hibernation_schedule_clusters.c.cluster_id.in_(cluster_ids),
            HibernationSchedule.is_active == "Y"
        )

        if exclude_schedule_id:
            query = query.filter(HibernationSchedule.id != exclude_schedule_id)

        existing_schedules = query.all()

        for existing in existing_schedules:
            overlap = self._check_matrix_overlap(
                schedule_matrix,
                existing.schedule_matrix,
                schedule_type,
                ScheduleType(existing.schedule_type)
            )

            if overlap > 0:
                conflicts.append({
                    "schedule_id": existing.id,
                    "schedule_name": existing.name,
                    "overlap_hours": overlap
                })

        return conflicts

    def calculate_weekly_savings(self, schedule: HibernationSchedule) -> Dict[str, Any]:
        """Calculate estimated weekly savings"""
        matrix = schedule.schedule_matrix
        sleep_hours = matrix.count("1")

        total_hourly_cost = 0.0
        for cluster in schedule.clusters:
            if cluster.monthly_cost:
                total_hourly_cost += cluster.monthly_cost / 730

        strategy = HibernationStrategy(schedule.strategy)
        savings_map = {
            HibernationStrategy.NAMESPACE_SLEEP: 0.80,
            HibernationStrategy.NUCLEAR: 0.70,
            HibernationStrategy.SNAPSHOT_RESTORE: 0.95
        }
        savings_percentage = savings_map.get(strategy, 0.80)

        weekly_savings = sleep_hours * total_hourly_cost * savings_percentage
        annual_savings = weekly_savings * 52

        return {
            "sleep_hours_per_week": sleep_hours,
            "awake_hours_per_week": 168 - sleep_hours,
            "hourly_cost": total_hourly_cost,
            "weekly_savings": weekly_savings,
            "annual_savings": annual_savings,
            "savings_percentage": (sleep_hours / 168) * savings_percentage * 100
        }

    def compare_strategies(self) -> List[Dict[str, Any]]:
        """Return comparison data for all hibernation strategies"""
        return [
            {
                "strategy": "NAMESPACE_SLEEP",
                "name": "Namespace Sleep",
                "description": "Scales all workload replicas to 0",
                "savings_percentage": 80,
                "wake_time_minutes": 2,
                "risk_level": "low"
            },
            {
                "strategy": "NUCLEAR",
                "name": "Node Scale-Down",
                "description": "Terminates worker nodes",
                "savings_percentage": 70,
                "wake_time_minutes": 5,
                "risk_level": "medium"
            },
            {
                "strategy": "SNAPSHOT_RESTORE",
                "name": "Full Hibernation",
                "description": "Stops entire cluster",
                "savings_percentage": 95,
                "wake_time_minutes": 15,
                "risk_level": "high"
            }
        ]

    # Private helpers
    def _validate_schedule_matrix(self, matrix: str, schedule_type: ScheduleType) -> None:
        """Validate schedule matrix format"""
        expected = {ScheduleType.WEEKLY: 168, ScheduleType.DAILY: 31, ScheduleType.MONTHLY: 744}
        if schedule_type in expected and len(matrix) != expected[schedule_type]:
            raise ValidationError(f"Matrix must be {expected[schedule_type]} characters")
        if not all(c in "01" for c in matrix):
            raise ValidationError("Matrix must only contain '0' and '1'")

    def _validate_timezone(self, timezone: str) -> None:
        """Validate timezone"""
        try:
            pytz.timezone(timezone)
        except:
            raise ValidationError(f"Invalid timezone: {timezone}")

    def _validate_clusters(self, cluster_ids: List[str]) -> None:
        """Validate clusters exist"""
        if not cluster_ids:
            raise ValidationError("At least one cluster required")
        count = self.db.query(Cluster).filter(Cluster.id.in_(cluster_ids)).count()
        if count != len(cluster_ids):
            raise ValidationError("Invalid cluster IDs")


    def _check_matrix_overlap(self, m1: str, m2: str, t1: ScheduleType, t2: ScheduleType) -> int:
        """Check overlap between matrices"""
        if t1 != ScheduleType.WEEKLY or t2 != ScheduleType.WEEKLY:
            return 0
        return sum(1 for i in range(min(len(m1), len(m2))) if m1[i] == "1" and m2[i] == "1")

    def get_savings_history(self, months: int, organization_id: str) -> List[Dict[str, Any]]:
        """
        Get historical hibernation savings for last N months.
        Aggregates data from audit_logs table where event IN ('hibernation_sleep', 'hibernation_wake').
        """
        from backend.models.audit_log import AuditLog
        from sqlalchemy import func, extract
        from datetime import datetime, timedelta
        import calendar

        cutoff_date = datetime.utcnow() - timedelta(days=months * 30)

        # Query audit logs for hibernation events
        logs = self.db.query(AuditLog).filter(
            and_(
                AuditLog.resource_type == 'HIBERNATION',
                AuditLog.event.in_(['hibernation_sleep', 'hibernation_wake']),
                AuditLog.timestamp >= cutoff_date
            )
        ).all()

        # Aggregate savings by month
        monthly_savings = {}
        for log in logs:
            if log.metadata and 'estimated_savings' in log.metadata:
                month_key = log.timestamp.strftime('%Y-%m')
                month_name = log.timestamp.strftime('%b')
                if month_key not in monthly_savings:
                    monthly_savings[month_key] = {
                        'month': month_name,
                        'savings': 0,
                        'sleep_hours': 0
                    }
                monthly_savings[month_key]['savings'] += float(log.metadata.get('estimated_savings', 0))
                monthly_savings[month_key]['sleep_hours'] += int(log.metadata.get('sleep_hours', 0))

        # Fill missing months with zeros
        result = []
        for i in range(months):
            date = datetime.utcnow() - timedelta(days=(months - i - 1) * 30)
            month_key = date.strftime('%Y-%m')
            month_name = date.strftime('%b')

            if month_key in monthly_savings:
                result.append(monthly_savings[month_key])
            else:
                result.append({
                    'month': month_name,
                    'savings': 0,
                    'sleep_hours': 0
                })

        return result

    def get_active_hibernation_status(self, organization_id: str) -> Dict[str, Any]:
        """
        Get status of currently active hibernation operation (if any).
        Checks cluster.is_hibernating flag and hibernation_state JSON for progress.
        """
        # Find clusters currently hibernating
        active_cluster = self.db.query(Cluster).filter(
            and_(
                Cluster.is_hibernating == True,
                Cluster.hibernation_lock.isnot(None)
            )
        ).first()

        if not active_cluster or not active_cluster.hibernation_state:
            return {
                'in_progress': False,
                'schedule_name': None,
                'strategy': None,
                'progress_pct': 0,
                'nodes_processed': 0,
                'total_nodes': 0,
                'elapsed_seconds': 0,
                'estimated_remaining': 0
            }

        # Extract progress from hibernation_state JSON
        state = active_cluster.hibernation_state or {}
        started_at = active_cluster.hibernation_lock_acquired_at
        elapsed = 0
        if started_at:
            elapsed = int((datetime.utcnow() - started_at).total_seconds())

        nodes_processed = state.get('nodes_processed', 0)
        total_nodes = state.get('total_nodes', 1)
        progress_pct = int((nodes_processed / total_nodes) * 100) if total_nodes > 0 else 0

        # Estimate remaining time (assume linear progress)
        estimated_remaining = 0
        if progress_pct > 0 and progress_pct < 100:
            estimated_remaining = int((elapsed / progress_pct) * (100 - progress_pct))

        return {
            'in_progress': True,
            'cluster_id': active_cluster.id,
            'cluster_name': active_cluster.name,
            'schedule_name': state.get('schedule_name', 'Manual Operation'),
            'strategy': state.get('strategy', 'NAMESPACE_SLEEP'),
            'progress_pct': progress_pct,
            'nodes_processed': nodes_processed,
            'total_nodes': total_nodes,
            'elapsed_seconds': elapsed,
            'estimated_remaining': estimated_remaining
        }


def get_hibernation_service(db: Session) -> HibernationService:
    """Get hibernation service instance"""
    return HibernationService(db)
