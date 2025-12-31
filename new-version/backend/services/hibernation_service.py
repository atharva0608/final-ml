"""
Hibernation Service

Business logic for hibernation schedule management
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from backend.models.hibernation_schedule import HibernationSchedule
from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.schemas.hibernation_schemas import (
    HibernationScheduleCreate,
    HibernationScheduleUpdate,
    HibernationScheduleResponse,
    HibernationScheduleList,
    HibernationScheduleFilter,
)
from backend.core.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
)
from backend.core.validators import validate_schedule_matrix, validate_timezone
from backend.core.logger import StructuredLogger
from datetime import datetime
import uuid

logger = StructuredLogger(__name__)


class HibernationService:
    """Service for hibernation schedule management"""

    def __init__(self, db: Session):
        self.db = db

    def create_schedule(
        self,
        user_id: str,
        schedule_data: HibernationScheduleCreate
    ) -> HibernationScheduleResponse:
        """
        Create a new hibernation schedule

        Args:
            user_id: User UUID
            schedule_data: Schedule creation data

        Returns:
            HibernationScheduleResponse with created schedule

        Raises:
            ResourceNotFoundError: If cluster not found
            ResourceAlreadyExistsError: If schedule already exists for cluster
            ValidationError: If validation fails
        """
        # Verify cluster belongs to user
        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == schedule_data.cluster_id,
                Account.user_id == user_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", schedule_data.cluster_id)

        # Check for existing schedule on this cluster
        existing = self.db.query(HibernationSchedule).filter(
            HibernationSchedule.cluster_id == schedule_data.cluster_id
        ).first()

        if existing:
            raise ResourceAlreadyExistsError(
                "HibernationSchedule",
                f"cluster {cluster.name}"
            )

        # Validate schedule matrix
        is_valid, error_msg = validate_schedule_matrix(schedule_data.schedule_matrix)
        if not is_valid:
            raise ValidationError(error_msg)

        # Validate timezone
        if not validate_timezone(schedule_data.timezone):
            raise ValidationError(f"Invalid timezone: {schedule_data.timezone}")

        # Validate pre-warm minutes
        if schedule_data.pre_warm_minutes < 0:
            raise ValidationError(
                f"pre_warm_minutes cannot be negative: {schedule_data.pre_warm_minutes}"
            )
        if schedule_data.pre_warm_minutes > 60:
            raise ValidationError(
                f"pre_warm_minutes cannot exceed 60: {schedule_data.pre_warm_minutes}"
            )

        # Create schedule
        new_schedule = HibernationSchedule(
            id=str(uuid.uuid4()),
            cluster_id=schedule_data.cluster_id,
            schedule_matrix=schedule_data.schedule_matrix,
            timezone=schedule_data.timezone,
            pre_warm_minutes=schedule_data.pre_warm_minutes,
            is_active=schedule_data.is_active,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_schedule)
        self.db.commit()
        self.db.refresh(new_schedule)

        logger.info(
            "Hibernation schedule created",
            schedule_id=new_schedule.id,
            cluster_id=schedule_data.cluster_id,
            timezone=schedule_data.timezone,
            pre_warm_minutes=schedule_data.pre_warm_minutes,
            user_id=user_id
        )

        return self._to_response(new_schedule)

    def get_schedule(self, schedule_id: str, user_id: str) -> HibernationScheduleResponse:
        """
        Get schedule by ID

        Args:
            schedule_id: Schedule UUID
            user_id: User UUID

        Returns:
            HibernationScheduleResponse

        Raises:
            ResourceNotFoundError: If schedule not found
        """
        schedule = self.db.query(HibernationSchedule).join(Cluster).join(Account).filter(
            and_(
                HibernationSchedule.id == schedule_id,
                Account.user_id == user_id
            )
        ).first()

        if not schedule:
            raise ResourceNotFoundError("HibernationSchedule", schedule_id)

        return self._to_response(schedule)

    def get_schedule_by_cluster(
        self,
        cluster_id: str,
        user_id: str
    ) -> Optional[HibernationScheduleResponse]:
        """
        Get schedule for a specific cluster

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID

        Returns:
            HibernationScheduleResponse or None

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

        schedule = self.db.query(HibernationSchedule).filter(
            HibernationSchedule.cluster_id == cluster_id
        ).first()

        if not schedule:
            return None

        return self._to_response(schedule)

    def list_schedules(
        self,
        user_id: str,
        filters: HibernationScheduleFilter
    ) -> HibernationScheduleList:
        """
        List schedules with filters and pagination

        Args:
            user_id: User UUID
            filters: Filter criteria

        Returns:
            HibernationScheduleList with paginated results
        """
        query = self.db.query(HibernationSchedule).join(Cluster).join(Account).filter(
            Account.user_id == user_id
        )

        # Apply filters
        if filters.cluster_id:
            query = query.filter(HibernationSchedule.cluster_id == filters.cluster_id)
        if filters.is_active is not None:
            query = query.filter(
                HibernationSchedule.is_active == ("Y" if filters.is_active else "N")
            )
        if filters.timezone:
            query = query.filter(HibernationSchedule.timezone == filters.timezone)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        schedules = query.order_by(desc(HibernationSchedule.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        # Convert to response schemas
        schedule_responses = [self._to_response(schedule) for schedule in schedules]

        return HibernationScheduleList(
            schedules=schedule_responses,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def update_schedule(
        self,
        schedule_id: str,
        user_id: str,
        update_data: HibernationScheduleUpdate
    ) -> HibernationScheduleResponse:
        """
        Update schedule

        Args:
            schedule_id: Schedule UUID
            user_id: User UUID
            update_data: Update data

        Returns:
            Updated HibernationScheduleResponse

        Raises:
            ResourceNotFoundError: If schedule not found
            ValidationError: If validation fails
        """
        schedule = self.db.query(HibernationSchedule).join(Cluster).join(Account).filter(
            and_(
                HibernationSchedule.id == schedule_id,
                Account.user_id == user_id
            )
        ).first()

        if not schedule:
            raise ResourceNotFoundError("HibernationSchedule", schedule_id)

        # Validate updates
        update_dict = update_data.model_dump(exclude_unset=True)

        if "schedule_matrix" in update_dict:
            is_valid, error_msg = validate_schedule_matrix(update_dict["schedule_matrix"])
            if not is_valid:
                raise ValidationError(error_msg)

        if "timezone" in update_dict:
            if not validate_timezone(update_dict["timezone"]):
                raise ValidationError(f"Invalid timezone: {update_dict['timezone']}")

        if "pre_warm_minutes" in update_dict:
            if update_dict["pre_warm_minutes"] < 0 or update_dict["pre_warm_minutes"] > 60:
                raise ValidationError(
                    f"pre_warm_minutes must be between 0 and 60: {update_dict['pre_warm_minutes']}"
                )

        # Apply updates
        for field, value in update_dict.items():
            setattr(schedule, field, value)

        schedule.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(schedule)

        logger.info(
            "Hibernation schedule updated",
            schedule_id=schedule_id,
            updated_fields=list(update_dict.keys()),
            user_id=user_id
        )

        return self._to_response(schedule)

    def delete_schedule(self, schedule_id: str, user_id: str) -> bool:
        """
        Delete schedule

        Args:
            schedule_id: Schedule UUID
            user_id: User UUID

        Returns:
            True if deleted

        Raises:
            ResourceNotFoundError: If schedule not found
        """
        schedule = self.db.query(HibernationSchedule).join(Cluster).join(Account).filter(
            and_(
                HibernationSchedule.id == schedule_id,
                Account.user_id == user_id
            )
        ).first()

        if not schedule:
            raise ResourceNotFoundError("HibernationSchedule", schedule_id)

        cluster_name = schedule.cluster.name

        self.db.delete(schedule)
        self.db.commit()

        logger.info(
            "Hibernation schedule deleted",
            schedule_id=schedule_id,
            cluster_name=cluster_name,
            user_id=user_id
        )

        return True

    def toggle_schedule(self, schedule_id: str, user_id: str) -> HibernationScheduleResponse:
        """
        Toggle schedule active status

        Args:
            schedule_id: Schedule UUID
            user_id: User UUID

        Returns:
            Updated HibernationScheduleResponse

        Raises:
            ResourceNotFoundError: If schedule not found
        """
        schedule = self.db.query(HibernationSchedule).join(Cluster).join(Account).filter(
            and_(
                HibernationSchedule.id == schedule_id,
                Account.user_id == user_id
            )
        ).first()

        if not schedule:
            raise ResourceNotFoundError("HibernationSchedule", schedule_id)

        # Toggle active status
        schedule.is_active = "N" if schedule.is_active == "Y" else "Y"
        schedule.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(schedule)

        logger.info(
            "Hibernation schedule toggled",
            schedule_id=schedule_id,
            is_active=schedule.is_active == "Y",
            user_id=user_id
        )

        return self._to_response(schedule)

    def get_active_schedules(self) -> List[HibernationSchedule]:
        """
        Get all active schedules for processing

        Returns:
            List of active schedules
        """
        return self.db.query(HibernationSchedule).filter(
            HibernationSchedule.is_active == "Y"
        ).all()

    def _to_response(self, schedule: HibernationSchedule) -> HibernationScheduleResponse:
        """
        Convert HibernationSchedule model to HibernationScheduleResponse schema

        Args:
            schedule: HibernationSchedule model

        Returns:
            HibernationScheduleResponse schema
        """
        return HibernationScheduleResponse(
            id=schedule.id,
            cluster_id=schedule.cluster_id,
            schedule_matrix=schedule.schedule_matrix,
            timezone=schedule.timezone,
            pre_warm_minutes=schedule.pre_warm_minutes,
            is_active=schedule.is_active == "Y",
            created_at=schedule.created_at,
            updated_at=schedule.updated_at
        )


def get_hibernation_service(db: Session) -> HibernationService:
    """Get hibernation service instance"""
    return HibernationService(db)
