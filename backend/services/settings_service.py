"""
Settings Service

Business logic for user settings, profile management, and integrations.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from backend.models.user import User
from backend.schemas.auth_schemas import UserProfile
from backend.schemas.settings_schemas import (
    UserProfileUpdate,
    Integration,
    IntegrationCreate,
    IntegrationList,
    IntegrationType,
    IntegrationStatus
)
from backend.core.exceptions import ResourceNotFoundError, ResourceAlreadyExistsError
from backend.core.logger import StructuredLogger

logger = StructuredLogger(__name__)

# In-memory mock storage for integrations (since no DB model exists yet)
# Structure: { user_id: [Integration] }
_MOCK_INTEGRATIONS_DB: Dict[str, List[Integration]] = {}

class SettingsService:
    """Service for managing user settings and integrations"""

    def __init__(self, db: Session):
        self.db = db

    def get_profile(self, user_id: str) -> UserProfile:
        """
        Get current user profile
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)

        return UserProfile(
            id=user.id,
            email=user.email,
            role=user.role.value,
            organization_id=user.organization_id,
            organization_name=user.organization.name if user.organization else None,
            created_at=user.created_at
        )

    def update_profile(self, user_id: str, update_data: UserProfileUpdate) -> UserProfile:
        """
        Update user profile
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)

        if update_data.email:
            # Check for email uniqueness
            existing = self.db.query(User).filter(User.email == update_data.email).first()
            if existing and existing.id != user_id:
                raise ResourceAlreadyExistsError("User", update_data.email)
            user.email = update_data.email
        
        user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)

        return self.get_profile(user_id)

    def get_integrations(self, user_id: str) -> IntegrationList:
        """
        Get list of integrations (Mocked)
        """
        # Ensure list exists for user
        if user_id not in _MOCK_INTEGRATIONS_DB:
            _MOCK_INTEGRATIONS_DB[user_id] = []
        
        items = _MOCK_INTEGRATIONS_DB[user_id]
        return IntegrationList(items=items, total=len(items))

    def add_integration(self, user_id: str, data: IntegrationCreate) -> Integration:
        """
        Add new integration (Mocked)
        """
        if user_id not in _MOCK_INTEGRATIONS_DB:
            _MOCK_INTEGRATIONS_DB[user_id] = []

        # Check dupes
        for integ in _MOCK_INTEGRATIONS_DB[user_id]:
            if integ.name == data.name and integ.type == data.type:
                raise ResourceAlreadyExistsError("Integration", data.name)

        new_integration = Integration(
            id=str(uuid.uuid4()),
            type=data.type,
            name=data.name,
            status=IntegrationStatus.ACTIVE,
            created_at=datetime.utcnow(),
            config={k: "****" for k in data.config} # Mask config in mock
        )

        _MOCK_INTEGRATIONS_DB[user_id].append(new_integration)
        
        logger.info(f"Added mock integration {new_integration.id} for user {user_id}")
        return new_integration

    def delete_integration(self, user_id: str, integration_id: str) -> None:
        """
        Delete integration (Mocked)
        """
        if user_id not in _MOCK_INTEGRATIONS_DB:
            raise ResourceNotFoundError("Integration", integration_id)

        original_len = len(_MOCK_INTEGRATIONS_DB[user_id])
        _MOCK_INTEGRATIONS_DB[user_id] = [
            i for i in _MOCK_INTEGRATIONS_DB[user_id] if i.id != integration_id
        ]

        if len(_MOCK_INTEGRATIONS_DB[user_id]) == original_len:
            raise ResourceNotFoundError("Integration", integration_id)

        logger.info(f"Deleted mock integration {integration_id} for user {user_id}")

def get_settings_service(db: Session):
    return SettingsService(db)
