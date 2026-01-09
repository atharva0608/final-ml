"""
Admin Service

Business logic for super admin operations and user management
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, or_, func
from backend.models.user import User, UserRole, OrgRole
from backend.models.organization import Organization
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.instance import Instance
from backend.schemas.admin_schemas import (
    ClientList,
    ClientSummary,
    ClientFilter,
    ClientStats,
    PlatformStats,
    UserManagement,
    OrganizationList,
    OrganizationSummary,
    OrganizationFilter,
)
from backend.core.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    UnauthorizedError,
)
from backend.core.crypto import hash_password
from backend.core.logger import StructuredLogger
from datetime import datetime, timedelta
from decimal import Decimal

logger = StructuredLogger(__name__)


class AdminService:
    """Service for admin portal operations"""

    def __init__(self, db: Session):
        self.db = db

    def verify_super_admin(self, user: User) -> None:
        """
        Verify user has super admin role

        Args:
            user: User to verify

        Raises:
            UnauthorizedError: If user is not super admin
        """
        if user.role != UserRole.SUPER_ADMIN:
            raise UnauthorizedError("Super admin access required")

    def list_clients(
        self,
        requesting_user: User,
        filters: ClientFilter
    ) -> ClientList:
        """
        List all client users with filters

        Args:
            requesting_user: User making the request (must be super admin)
            filters: Filter criteria

        Returns:
            ClientList with paginated results

        Raises:
            UnauthorizedError: If not super admin
        """
        self.verify_super_admin(requesting_user)

        # Base query for client users
        query = self.db.query(User).filter(User.role == UserRole.CLIENT)

        # Apply filters
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(
                or_(
                    User.email.ilike(search_pattern),
                    User.id.ilike(search_pattern)
                )
            )

        if filters.is_active is not None:
            query = query.filter(
                User.is_active == ("Y" if filters.is_active else "N")
            )

        if filters.created_after:
            query = query.filter(User.created_at >= filters.created_after)

        if filters.created_before:
            query = query.filter(User.created_at <= filters.created_before)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        users = query.order_by(desc(User.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        # Convert to client summaries with stats
        client_summaries = []
        for user in users:
            stats = self._get_client_stats(user.id)
            client_summaries.append(
                ClientSummary(
                    id=user.id,
                    email=user.email,
                    organization_name=user.organization.name if user.organization else None,
                    is_active=user.is_active == "Y",
                    created_at=user.created_at,
                    last_login=None,
                    total_clusters=stats.total_clusters,
                    total_instances=stats.total_instances,
                    total_cost=stats.total_cost
                )
            )

        logger.info(
            "Clients listed",
            admin_id=requesting_user.id,
            total_clients=total,
            page=filters.page
        )

        return ClientList(
            clients=client_summaries,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def get_client_details(
        self,
        requesting_user: User,
        client_id: str
    ) -> UserManagement:
        """
        Get detailed information about a client

        Args:
            requesting_user: User making the request (must be super admin)
            client_id: Client user ID

        Returns:
            UserManagement with full client details

        Raises:
            UnauthorizedError: If not super admin
            ResourceNotFoundError: If client not found
        """
        self.verify_super_admin(requesting_user)

        user = self.db.query(User).filter(User.id == client_id).first()
        if not user:
            raise ResourceNotFoundError("User", client_id)

        stats = self._get_client_stats(client_id)

        return UserManagement(
            id=user.id,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active == "Y",
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login=None,
            stats=stats
        )

    def toggle_client_status(
        self,
        requesting_user: User,
        client_id: str
    ) -> UserManagement:
        """
        Activate or deactivate a client user

        Args:
            requesting_user: User making the request (must be super admin)
            client_id: Client user ID

        Returns:
            Updated UserManagement

        Raises:
            UnauthorizedError: If not super admin
            ResourceNotFoundError: If client not found
        """
        self.verify_super_admin(requesting_user)

        user = self.db.query(User).filter(User.id == client_id).first()
        if not user:
            raise ResourceNotFoundError("User", client_id)

        # Toggle active status
        user.is_active = "N" if user.is_active == "Y" else "Y"
        user.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(user)

        logger.info(
            "Client status toggled",
            admin_id=requesting_user.id,
            client_id=client_id,
            is_active=user.is_active == "Y"
        )

        stats = self._get_client_stats(client_id)

        return UserManagement(
            id=user.id,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active == "Y",
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login=None,
            stats=stats
        )

    def reset_client_password(
        self,
        requesting_user: User,
        client_id: str,
        new_password: str
    ) -> bool:
        """
        Reset a client's password

        Args:
            requesting_user: User making the request (must be super admin)
            client_id: Client user ID
            new_password: New password

        Returns:
            True if successful

        Raises:
            UnauthorizedError: If not super admin
            ResourceNotFoundError: If client not found
            ValidationError: If password invalid
        """
        self.verify_super_admin(requesting_user)

        user = self.db.query(User).filter(User.id == client_id).first()
        if not user:
            raise ResourceNotFoundError("User", client_id)

        # Validate password strength
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters")

        # Hash and update password
        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()

        self.db.commit()

        logger.info(
            "Client password reset",
            admin_id=requesting_user.id,
            client_id=client_id
        )

        return True

    def get_platform_stats(
        self,
        requesting_user: User
    ) -> PlatformStats:
        """
        Get platform-wide statistics

        Args:
            requesting_user: User making the request (must be super admin)

        Returns:
            PlatformStats with aggregated metrics

        Raises:
            UnauthorizedError: If not super admin
        """
        self.verify_super_admin(requesting_user)

        # User stats
        total_users = self.db.query(User).filter(User.role == UserRole.CLIENT).count()
        active_users = self.db.query(User).filter(
            and_(
                User.role == UserRole.CLIENT,
                User.is_active == "Y"
            )
        ).count()

        # Recent signups (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_signups = self.db.query(User).filter(
            and_(
                User.role == UserRole.CLIENT,
                User.created_at >= thirty_days_ago
            )
        ).count()

        # Cluster stats
        total_clusters = self.db.query(Cluster).count()
        active_clusters = self.db.query(Cluster).filter(
            Cluster.status.in_(['ACTIVE', 'DISCOVERED'])
        ).count()

        # Instance stats
        total_instances = self.db.query(Instance).count()
        running_instances = self.db.query(Instance).count()
        spot_instances = self.db.query(Instance).filter(
            Instance.lifecycle == 'spot'
        ).count()

        # Calculate total cost (simplified)
        total_cost = self._calculate_platform_cost()

        logger.info(
            "Platform stats retrieved",
            admin_id=requesting_user.id,
            total_users=total_users,
            total_clusters=total_clusters
        )

        return PlatformStats(
            total_users=total_users,
            active_users=active_users,
            recent_signups=recent_signups,
            total_clusters=total_clusters,
            active_clusters=active_clusters,
            total_instances=total_instances,
            running_instances=running_instances,
            spot_instances=spot_instances,
            total_cost=total_cost
        )

    def list_organizations(
        self,
        requesting_user: User,
        filters: OrganizationFilter
    ) -> OrganizationList:
        """
        List all organizations
        """
        self.verify_super_admin(requesting_user)

        query = self.db.query(Organization)

        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(
                or_(
                    Organization.name.ilike(search_pattern),
                    Organization.slug.ilike(search_pattern)
                )
            )

        total = query.count()

        orgs = query.order_by(desc(Organization.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        org_summaries = []
        for org in orgs:
            # Find owner using explicit owner_user_id
            owner = None
            if org.owner_user_id:
                owner = self.db.query(User).filter(User.id == org.owner_user_id).first()
            
            # Fallback: Look for ORG_ADMIN if owner_user_id not set (legacy)
            if not owner:
                owner = self.db.query(User).filter(
                    and_(
                        User.organization_id == org.id,
                        User.org_role == OrgRole.ORG_ADMIN
                    )
                ).first()
            
            # Counts
            total_users = self.db.query(User).filter(User.organization_id == org.id).count()
            total_clusters = self.db.query(Cluster).join(Account).filter(Account.organization_id == org.id).count()
            total_instances = self.db.query(Instance).join(Cluster).join(Account).filter(Account.organization_id == org.id).count()

            org_summaries.append(
                OrganizationSummary(
                    id=org.id,
                    name=org.name,
                    slug=org.slug,
                    owner_email=owner.email if owner else None,
                    total_users=total_users,
                    total_clusters=total_clusters,
                    total_instances=total_instances,
                    created_at=org.created_at,
                    is_active=org.status == "active"
                )
            )

        return OrganizationList(
            organizations=org_summaries,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def _get_client_stats(self, user_id: str) -> ClientStats:
        """
        Get statistics for a specific client (via their Organization)
        """
        # Find user and org
        user = self.db.query(User).filter(User.id == user_id).first()
        org_id = user.organization_id if user else None

        if not org_id:
             return ClientStats(
                client_id=user_id,
                savings_trend=[],
                active_policies=0,
                total_accounts=0,
                total_clusters=0,
                total_instances=0,
                running_instances=0,
                total_cost=Decimal('0.0')
            )

        # Account count
        total_accounts = self.db.query(Account).filter(
            Account.organization_id == org_id
        ).count()

        # Cluster count
        total_clusters = self.db.query(Cluster).join(Account).filter(
            Account.organization_id == org_id
        ).count()

        # Instance count
        total_instances = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.organization_id == org_id
        ).count()

        running_instances = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.organization_id == org_id
        ).count()

        # Calculate cost (simplified)
        instances = self.db.query(Instance).join(Cluster).join(Account).filter(
            Account.organization_id == org_id
        ).all()

        total_cost = Decimal('0.0')
        for instance in instances:
            if instance.price:
                total_cost += Decimal(str(instance.price)) * Decimal('720')

        return ClientStats(
            client_id=user_id,
            savings_trend=[],
            active_policies=0,
            total_accounts=total_accounts,
            total_clusters=total_clusters,
            total_instances=total_instances,
            running_instances=running_instances,
            total_cost=total_cost
        )

    def _calculate_platform_cost(self) -> Decimal:
        """
        Calculate total platform cost

        Returns:
            Total estimated monthly cost
        """
        running_instances = self.db.query(Instance).all()

        total_cost = Decimal('0.0')
        for instance in running_instances:
            if instance.price:
                # Estimate monthly cost (720 hours)
                total_cost += Decimal(str(instance.price)) * Decimal('720')

        return total_cost

        return total_cost

    def get_billing_info(self, requesting_user: User) -> 'BillingResponse':
        """
        Get billing information (Mock implementation for now)
        """
        self.verify_super_admin(requesting_user)
        # Mock data matching frontend hardcoded values
        return {
            "stats": {
                "mrr": "$48,250",
                "mrr_growth": "+12%",
                "active_subs": 842,
                "subs_growth": "+5%",
                "failed_charges": 3
            },
            "plans": [
                {"name": 'Free Tier', "price": '$0', "nodes": '5', "clients": 124, "status": 'Active'},
                {"name": 'Pro Plan', "price": '$299', "nodes": '50', "clients": 650, "status": 'Active'},
                {"name": 'Enterprise', "price": 'Custom', "nodes": 'Unlimited', "clients": 68, "status": 'Active'},
            ],
            "upsell_opportunities": [
                {"client": 'Acme Corp', "plan": 'Free Tier', "usage": '95%', "nodes": '4/5', "client_initial": "A"},
                {"client": 'Startup Inc', "plan": 'Pro Plan', "usage": '92%', "nodes": '46/50', "client_initial": "S"},
            ]
        }

    def get_dashboard_stats(self, requesting_user: User) -> 'DashboardResponse':
        """
        Get admin dashboard statistics (Merging real stats with mock chart/feed)
        """
        self.verify_super_admin(requesting_user)
        
        # Get real stats
        platform_stats = self.get_platform_stats(requesting_user)
        
        # Mock chart and feed (until we have real historical data logic)
        return {
            "stats": platform_stats,
            "savings_chart": [
                {"name": 'Mon', "savings": 4000},
                {"name": 'Tue', "savings": 3000},
                {"name": 'Wed', "savings": 2000},
                {"name": 'Thu', "savings": 2780},
                {"name": 'Fri', "savings": 1890},
                {"name": 'Sat', "savings": 2390},
                {"name": 'Sun', "savings": 3490},
            ],
            "activity_feed": [
                {"id": 1, "user": 'Acme Corp', "action": 'Optimized Cluster', "detail": 'Replaced 5x m5.large with spot', "time": '2 mins ago', "type": 'optimization'},
                {"id": 2, "user": 'Startup Inc', "action": 'Connected AWS', "detail": 'New cluster onboarding', "time": '15 mins ago', "type": 'onboarding'},
                {"id": 3, "user": 'TechFlow', "action": 'Policy Update', "detail": 'Changed risk tolerance to Medium', "time": '1 hour ago', "type": 'config'},
                {"id": 4, "user": 'Global Logistics', "action": 'Agent Updated', "detail": 'Auto-updated to v1.4.2', "time": '2 hours ago', "type": 'system'},
            ]
        }
def get_admin_service(db: Session) -> AdminService:
    """Get admin service instance"""
    return AdminService(db)
