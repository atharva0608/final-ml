"""
Lab Service

Business logic for ML experimentation and A/B testing
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from backend.models.lab_experiment import LabExperiment, ExperimentStatus
from backend.models.ml_model import MLModel
from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.schemas.lab_schemas import (
    ExperimentCreate,
    ExperimentUpdate,
    ExperimentResponse,
    ExperimentList,
    ExperimentFilter,
    ExperimentResults,
    VariantPerformance,
)
from backend.core.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
)
from backend.core.logger import StructuredLogger
from datetime import datetime
import uuid
from decimal import Decimal

logger = StructuredLogger(__name__)


class LabService:
    """Service for ML experimentation and A/B testing"""

    def __init__(self, db: Session):
        self.db = db

    def create_experiment(
        self,
        user_id: str,
        experiment_data: ExperimentCreate
    ) -> ExperimentResponse:
        """
        Create a new experiment

        Args:
            user_id: User UUID
            experiment_data: Experiment creation data

        Returns:
            ExperimentResponse with created experiment

        Raises:
            ResourceNotFoundError: If cluster or models not found
            ResourceAlreadyExistsError: If experiment name already exists
            ValidationError: If validation fails
        """
        # Verify cluster belongs to user
        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == experiment_data.cluster_id,
                Account.user_id == user_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", experiment_data.cluster_id)

        # Check for duplicate experiment name
        existing = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                Account.user_id == user_id,
                LabExperiment.name == experiment_data.name
            )
        ).first()

        if existing:
            raise ResourceAlreadyExistsError("Experiment", experiment_data.name)

        # Validate variant allocation percentages
        total_allocation = experiment_data.control_percentage + experiment_data.variant_percentage
        if total_allocation != 100:
            raise ValidationError(
                f"Control and variant percentages must sum to 100, got {total_allocation}"
            )

        # Validate models exist
        control_model = self.db.query(MLModel).filter(
            MLModel.id == experiment_data.control_model_id
        ).first()

        if not control_model:
            raise ResourceNotFoundError("MLModel", experiment_data.control_model_id)

        variant_model = self.db.query(MLModel).filter(
            MLModel.id == experiment_data.variant_model_id
        ).first()

        if not variant_model:
            raise ResourceNotFoundError("MLModel", experiment_data.variant_model_id)

        # Create experiment
        new_experiment = LabExperiment(
            id=str(uuid.uuid4()),
            cluster_id=experiment_data.cluster_id,
            name=experiment_data.name,
            description=experiment_data.description,
            control_model_id=experiment_data.control_model_id,
            variant_model_id=experiment_data.variant_model_id,
            control_percentage=experiment_data.control_percentage,
            variant_percentage=experiment_data.variant_percentage,
            status=ExperimentStatus.DRAFT,
            config=experiment_data.config or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_experiment)
        self.db.commit()
        self.db.refresh(new_experiment)

        logger.info(
            "Experiment created",
            experiment_id=new_experiment.id,
            name=experiment_data.name,
            cluster_id=experiment_data.cluster_id,
            user_id=user_id
        )

        return self._to_response(new_experiment)

    def get_experiment(self, experiment_id: str, user_id: str) -> ExperimentResponse:
        """
        Get experiment by ID

        Args:
            experiment_id: Experiment UUID
            user_id: User UUID

        Returns:
            ExperimentResponse

        Raises:
            ResourceNotFoundError: If experiment not found
        """
        experiment = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                LabExperiment.id == experiment_id,
                Account.user_id == user_id
            )
        ).first()

        if not experiment:
            raise ResourceNotFoundError("Experiment", experiment_id)

        return self._to_response(experiment)

    def list_experiments(
        self,
        user_id: str,
        filters: ExperimentFilter
    ) -> ExperimentList:
        """
        List experiments with filters and pagination

        Args:
            user_id: User UUID
            filters: Filter criteria

        Returns:
            ExperimentList with paginated results
        """
        query = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            Account.user_id == user_id
        )

        # Apply filters
        if filters.cluster_id:
            query = query.filter(LabExperiment.cluster_id == filters.cluster_id)
        if filters.status:
            query = query.filter(LabExperiment.status == filters.status)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(LabExperiment.name.ilike(search_pattern))

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        experiments = query.order_by(desc(LabExperiment.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        # Convert to response schemas
        experiment_responses = [self._to_response(exp) for exp in experiments]

        return ExperimentList(
            experiments=experiment_responses,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def update_experiment(
        self,
        experiment_id: str,
        user_id: str,
        update_data: ExperimentUpdate
    ) -> ExperimentResponse:
        """
        Update experiment

        Args:
            experiment_id: Experiment UUID
            user_id: User UUID
            update_data: Update data

        Returns:
            Updated ExperimentResponse

        Raises:
            ResourceNotFoundError: If experiment not found
            ValidationError: If validation fails
        """
        experiment = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                LabExperiment.id == experiment_id,
                Account.user_id == user_id
            )
        ).first()

        if not experiment:
            raise ResourceNotFoundError("Experiment", experiment_id)

        # Can only update if not running or completed
        if experiment.status in [ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED]:
            raise ValidationError(
                f"Cannot update experiment in {experiment.status.value} status"
            )

        # Validate updates
        update_dict = update_data.model_dump(exclude_unset=True)

        # Validate variant percentages if updated
        if "control_percentage" in update_dict or "variant_percentage" in update_dict:
            control = update_dict.get("control_percentage", experiment.control_percentage)
            variant = update_dict.get("variant_percentage", experiment.variant_percentage)
            if control + variant != 100:
                raise ValidationError(
                    f"Control and variant percentages must sum to 100, got {control + variant}"
                )

        # Apply updates
        for field, value in update_dict.items():
            setattr(experiment, field, value)

        experiment.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(experiment)

        logger.info(
            "Experiment updated",
            experiment_id=experiment_id,
            updated_fields=list(update_dict.keys()),
            user_id=user_id
        )

        return self._to_response(experiment)

    def delete_experiment(self, experiment_id: str, user_id: str) -> bool:
        """
        Delete experiment

        Args:
            experiment_id: Experiment UUID
            user_id: User UUID

        Returns:
            True if deleted

        Raises:
            ResourceNotFoundError: If experiment not found
            ValidationError: If experiment is running
        """
        experiment = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                LabExperiment.id == experiment_id,
                Account.user_id == user_id
            )
        ).first()

        if not experiment:
            raise ResourceNotFoundError("Experiment", experiment_id)

        # Cannot delete running experiment
        if experiment.status == ExperimentStatus.RUNNING:
            raise ValidationError("Cannot delete running experiment. Stop it first.")

        experiment_name = experiment.name

        self.db.delete(experiment)
        self.db.commit()

        logger.info(
            "Experiment deleted",
            experiment_id=experiment_id,
            name=experiment_name,
            user_id=user_id
        )

        return True

    def start_experiment(self, experiment_id: str, user_id: str) -> ExperimentResponse:
        """
        Start an experiment

        Args:
            experiment_id: Experiment UUID
            user_id: User UUID

        Returns:
            Updated ExperimentResponse

        Raises:
            ResourceNotFoundError: If experiment not found
            ValidationError: If experiment cannot be started
        """
        experiment = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                LabExperiment.id == experiment_id,
                Account.user_id == user_id
            )
        ).first()

        if not experiment:
            raise ResourceNotFoundError("Experiment", experiment_id)

        # Can only start if in DRAFT status
        if experiment.status != ExperimentStatus.DRAFT:
            raise ValidationError(
                f"Can only start experiments in DRAFT status, current: {experiment.status.value}"
            )

        experiment.status = ExperimentStatus.RUNNING
        experiment.start_time = datetime.utcnow()
        experiment.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(experiment)

        logger.info(
            "Experiment started",
            experiment_id=experiment_id,
            name=experiment.name,
            user_id=user_id
        )

        return self._to_response(experiment)

    def stop_experiment(self, experiment_id: str, user_id: str) -> ExperimentResponse:
        """
        Stop a running experiment

        Args:
            experiment_id: Experiment UUID
            user_id: User UUID

        Returns:
            Updated ExperimentResponse

        Raises:
            ResourceNotFoundError: If experiment not found
            ValidationError: If experiment is not running
        """
        experiment = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                LabExperiment.id == experiment_id,
                Account.user_id == user_id
            )
        ).first()

        if not experiment:
            raise ResourceNotFoundError("Experiment", experiment_id)

        # Can only stop if running
        if experiment.status != ExperimentStatus.RUNNING:
            raise ValidationError(
                f"Can only stop running experiments, current: {experiment.status.value}"
            )

        experiment.status = ExperimentStatus.COMPLETED
        experiment.end_time = datetime.utcnow()
        experiment.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(experiment)

        logger.info(
            "Experiment stopped",
            experiment_id=experiment_id,
            name=experiment.name,
            user_id=user_id
        )

        return self._to_response(experiment)

    def get_experiment_results(
        self,
        experiment_id: str,
        user_id: str
    ) -> ExperimentResults:
        """
        Get experiment results and analysis

        Args:
            experiment_id: Experiment UUID
            user_id: User UUID

        Returns:
            ExperimentResults with performance comparison

        Raises:
            ResourceNotFoundError: If experiment not found
        """
        experiment = self.db.query(LabExperiment).join(Cluster).join(Account).filter(
            and_(
                LabExperiment.id == experiment_id,
                Account.user_id == user_id
            )
        ).first()

        if not experiment:
            raise ResourceNotFoundError("Experiment", experiment_id)

        # Calculate results from experiment metrics
        # This is simplified - in production, you'd aggregate actual experiment data

        control_performance = VariantPerformance(
            variant_name="Control",
            model_id=experiment.control_model_id,
            allocation_percentage=experiment.control_percentage,
            total_predictions=experiment.results.get("control_predictions", 0) if experiment.results else 0,
            avg_cost=Decimal(str(experiment.results.get("control_avg_cost", 0.0))) if experiment.results else Decimal("0.0"),
            avg_savings=Decimal(str(experiment.results.get("control_avg_savings", 0.0))) if experiment.results else Decimal("0.0"),
            success_rate=experiment.results.get("control_success_rate", 0.0) if experiment.results else 0.0
        )

        variant_performance = VariantPerformance(
            variant_name="Variant",
            model_id=experiment.variant_model_id,
            allocation_percentage=experiment.variant_percentage,
            total_predictions=experiment.results.get("variant_predictions", 0) if experiment.results else 0,
            avg_cost=Decimal(str(experiment.results.get("variant_avg_cost", 0.0))) if experiment.results else Decimal("0.0"),
            avg_savings=Decimal(str(experiment.results.get("variant_avg_savings", 0.0))) if experiment.results else Decimal("0.0"),
            success_rate=experiment.results.get("variant_success_rate", 0.0) if experiment.results else 0.0
        )

        # Determine winner
        winner = None
        if experiment.status == ExperimentStatus.COMPLETED:
            if variant_performance.avg_savings > control_performance.avg_savings:
                winner = "Variant"
            else:
                winner = "Control"

        return ExperimentResults(
            experiment_id=experiment.id,
            experiment_name=experiment.name,
            status=experiment.status.value,
            start_time=experiment.start_time,
            end_time=experiment.end_time,
            control_performance=control_performance,
            variant_performance=variant_performance,
            winner=winner
        )

    def _to_response(self, experiment: LabExperiment) -> ExperimentResponse:
        """
        Convert LabExperiment model to ExperimentResponse schema

        Args:
            experiment: LabExperiment model

        Returns:
            ExperimentResponse schema
        """
        return ExperimentResponse(
            id=experiment.id,
            cluster_id=experiment.cluster_id,
            name=experiment.name,
            description=experiment.description,
            control_model_id=experiment.control_model_id,
            variant_model_id=experiment.variant_model_id,
            control_percentage=experiment.control_percentage,
            variant_percentage=experiment.variant_percentage,
            status=experiment.status.value,
            config=experiment.config,
            start_time=experiment.start_time,
            end_time=experiment.end_time,
            results=experiment.results,
            created_at=experiment.created_at,
            updated_at=experiment.updated_at
        )


def get_lab_service(db: Session) -> LabService:
    """Get lab service instance"""
    return LabService(db)
