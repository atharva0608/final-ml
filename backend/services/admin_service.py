"""
Admin Service

Business logic for super admin operations and user management
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, or_, func
from backend.models.user import User, UserRole
from backend.models.organization import Organization
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.instance import Instance, InstanceLifecycle
from backend.schemas.admin_schemas import (
    ClientList, ClientSummary, ClientFilter, ClientStats,
    PlatformStats, UserManagement, OrganizationList,
    OrganizationSummary, OrganizationFilter,
)
from backend.core.exceptions import ResourceNotFoundError, ValidationError, UnauthorizedError
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
        if user.role != UserRole.SUPER_ADMIN:
            raise UnauthorizedError("Super admin access required")

    def list_clients(self, requesting_user: User, filters: ClientFilter) -> ClientList:
        self.verify_super_admin(requesting_user)
        # Include both legacy CLIENT role and ORG_ADMIN (primary tenant owners)
        query = self.db.query(User).filter(User.role.in_([UserRole.CLIENT, UserRole.ORG_ADMIN]))
        
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(or_(User.email.ilike(search_pattern), User.id.ilike(search_pattern)))
        if filters.is_active is not None:
            query = query.filter(User.is_active == ("Y" if filters.is_active else "N"))
        if filters.created_after:
            query = query.filter(User.created_at >= filters.created_after)
        if filters.created_before:
            query = query.filter(User.created_at <= filters.created_before)
        
        total = query.count()
        users = query.order_by(desc(User.created_at)).offset((filters.page - 1) * filters.page_size).limit(filters.page_size).all()
        
        client_summaries = []
        for user in users:
            stats = self._get_client_stats(user.id)
            client_summaries.append(ClientSummary(
                id=user.id, email=user.email,
                organization_name=user.organization.name if user.organization else None,
                is_active=user.is_active == "Y", created_at=user.created_at, last_login=None,
                total_clusters=stats.total_clusters, total_instances=stats.total_instances, total_cost=stats.total_cost,
                # Frontend aliases
                account_count=stats.total_accounts,
                cluster_count=stats.total_clusters,
                instance_count=stats.total_instances,
                monthly_cost=stats.total_cost
            ))
        
        return ClientList(
            clients=client_summaries, 
            total=total, 
            total_count=total,
            total_pages=max(1, (total + filters.page_size - 1) // filters.page_size),
            page=filters.page, 
            page_size=filters.page_size
        )

    def get_client_details(self, requesting_user: User, client_id: str) -> UserManagement:
        self.verify_super_admin(requesting_user)
        user = self.db.query(User).filter(User.id == client_id).first()
        if not user:
            raise ResourceNotFoundError("User", client_id)
        stats = self._get_client_stats(client_id)
        return UserManagement(
            id=user.id, email=user.email, role=user.role.value,
            is_active=user.is_active == "Y", created_at=user.created_at,
            updated_at=user.updated_at, last_login=None, stats=stats
        )

    def toggle_client_status(self, requesting_user: User, client_id: str) -> UserManagement:
        self.verify_super_admin(requesting_user)
        user = self.db.query(User).filter(User.id == client_id).first()
        if not user:
            raise ResourceNotFoundError("User", client_id)
        user.is_active = "N" if user.is_active == "Y" else "Y"
        user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)
        stats = self._get_client_stats(client_id)
        return UserManagement(
            id=user.id, email=user.email, role=user.role.value,
            is_active=user.is_active == "Y", created_at=user.created_at,
            updated_at=user.updated_at, last_login=None, stats=stats
        )

    def reset_client_password(self, requesting_user: User, client_id: str, new_password: str) -> bool:
        self.verify_super_admin(requesting_user)
        user = self.db.query(User).filter(User.id == client_id).first()
        if not user:
            raise ResourceNotFoundError("User", client_id)
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def get_platform_stats(self, requesting_user: User) -> PlatformStats:
        self.verify_super_admin(requesting_user)
        # Include both legacy CLIENT role and ORG_ADMIN (primary tenant owners)
        target_roles = [UserRole.CLIENT, UserRole.ORG_ADMIN]
        
        total_users = self.db.query(User).filter(User.role.in_(target_roles)).count()
        active_users = self.db.query(User).filter(and_(User.role.in_(target_roles), User.is_active == "Y")).count()
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_signups = self.db.query(User).filter(and_(User.role.in_(target_roles), User.created_at >= thirty_days_ago)).count()
        total_clusters = self.db.query(Cluster).count()
        active_clusters = self.db.query(Cluster).filter(Cluster.status.in_(['ACTIVE', 'DISCOVERED'])).count()
        total_instances = self.db.query(Instance).count()
        running_instances = self.db.query(Instance).count()
        spot_instances = self.db.query(Instance).filter(Instance.lifecycle == InstanceLifecycle.SPOT).count()
        total_cost = self._calculate_platform_cost()
        return PlatformStats(
            total_users=total_users, active_users=active_users, recent_signups=recent_signups,
            total_clusters=total_clusters, active_clusters=active_clusters,
            total_instances=total_instances, running_instances=running_instances,
            spot_instances=spot_instances, total_cost=total_cost
        )

    def list_organizations(self, requesting_user: User, filters: OrganizationFilter) -> OrganizationList:
        self.verify_super_admin(requesting_user)
        query = self.db.query(Organization)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(or_(Organization.name.ilike(search_pattern), Organization.slug.ilike(search_pattern)))
        total = query.count()
        orgs = query.order_by(desc(Organization.created_at)).offset((filters.page - 1) * filters.page_size).limit(filters.page_size).all()
        
        org_summaries = []
        for org in orgs:
            owner = None
            if org.owner_user_id:
                owner = self.db.query(User).filter(User.id == org.owner_user_id).first()
            if not owner:
                owner = self.db.query(User).filter(and_(User.organization_id == org.id, User.role == UserRole.ORG_ADMIN)).first()
            total_users = self.db.query(User).filter(User.organization_id == org.id).count()
            total_accounts = self.db.query(Account).filter(Account.organization_id == org.id).count()
            total_clusters = self.db.query(Cluster).join(Account).filter(Account.organization_id == org.id).count()
            total_instances = self.db.query(Instance).join(Cluster).join(Account).filter(Account.organization_id == org.id).count()
            org_summaries.append(OrganizationSummary(
                id=org.id, name=org.name, slug=org.slug,
                owner_email=owner.email if owner else None,
                total_users=total_users, total_accounts=total_accounts, total_clusters=total_clusters,
                total_instances=total_instances, created_at=org.created_at,
                is_active=org.status == "active"
            ))
        return OrganizationList(organizations=org_summaries, total=total, page=filters.page, page_size=filters.page_size)

    def toggle_organization_status(self, requesting_user: User, org_id: str) -> OrganizationSummary:
        self.verify_super_admin(requesting_user)
        org = self.db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ResourceNotFoundError("Organization", org_id)
        
        org.status = "inactive" if org.status == "active" else "active"
        org.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(org)
        
        # Return summary
        owner = None
        if org.owner_user_id:
            owner = self.db.query(User).filter(User.id == org.owner_user_id).first()
        if not owner:
            owner = self.db.query(User).filter(and_(User.organization_id == org.id, User.role == UserRole.ORG_ADMIN)).first()
            
        total_users = self.db.query(User).filter(User.organization_id == org.id).count()
        total_accounts = self.db.query(Account).filter(Account.organization_id == org.id).count()
        total_clusters = self.db.query(Cluster).join(Account).filter(Account.organization_id == org.id).count()
        total_instances = self.db.query(Instance).join(Cluster).join(Account).filter(Account.organization_id == org.id).count()

        return OrganizationSummary(
            id=org.id, name=org.name, slug=org.slug,
            owner_email=owner.email if owner else None,
            total_users=total_users, total_accounts=total_accounts, total_clusters=total_clusters,
            total_instances=total_instances, created_at=org.created_at,
            is_active=org.status == "active"
        )

    def _get_client_stats(self, user_id: str) -> ClientStats:
        user = self.db.query(User).filter(User.id == user_id).first()
        org_id = user.organization_id if user else None
        if not org_id:
            return ClientStats(client_id=user_id, savings_trend=[], active_policies=0,
                             total_accounts=0, total_clusters=0, total_instances=0,
                             running_instances=0, total_cost=Decimal('0.0'))
        total_accounts = self.db.query(Account).filter(Account.organization_id == org_id).count()
        total_clusters = self.db.query(Cluster).join(Account).filter(Account.organization_id == org_id).count()
        total_instances = self.db.query(Instance).join(Cluster).join(Account).filter(Account.organization_id == org_id).count()
        running_instances = total_instances
        instances = self.db.query(Instance).join(Cluster).join(Account).filter(Account.organization_id == org_id).all()
        total_cost = Decimal('0.0')
        for instance in instances:
            if instance.price:
                total_cost += Decimal(str(instance.price)) * Decimal('720')
        return ClientStats(
            client_id=user_id, savings_trend=[], active_policies=0,
            total_accounts=total_accounts, total_clusters=total_clusters,
            total_instances=total_instances, running_instances=running_instances, total_cost=total_cost
        )

    def _calculate_platform_cost(self) -> Decimal:
        running_instances = self.db.query(Instance).all()
        total_cost = Decimal('0.0')
        for instance in running_instances:
            if instance.price:
                total_cost += Decimal(str(instance.price)) * Decimal('720')
        return total_cost

    def get_billing_info(self, requesting_user: User):
        self.verify_super_admin(requesting_user)
        return {
            "stats": {"mrr": "$48,250", "mrr_growth": "+12%", "active_subs": 842, "subs_growth": "+5%", "failed_charges": 3},
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

    def get_dashboard_stats(self, requesting_user: User):
        self.verify_super_admin(requesting_user)
        platform_stats = self.get_platform_stats(requesting_user)
        platform_stats.mrr = f"${platform_stats.total_cost:,.2f}"
        
        # Fetch real activity feed from AuditLog
        from backend.models.audit_log import AuditLog
        recent_logs = self.db.query(AuditLog).order_by(desc(AuditLog.timestamp)).limit(10).all()
        
        activity_feed = []
        for log in recent_logs:
            activity_feed.append({
                "id": log.id,
                "user": log.actor_name,
                "action": log.event,
                "detail": f"{log.resource_type}: {log.resource}",
                "time": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"), # Simple string format
                "type": "audit" # Marker
            })
            
        return {"stats": platform_stats, "savings_chart": [], "activity_feed": activity_feed}

    # ==============================================
    # Platform Identity Management
    # ==============================================

    def get_platform_connection(self, requesting_user: User) -> dict:
        self.verify_super_admin(requesting_user)
        from backend.models.system_config import SystemConfig
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        region = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        role_arn = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_ROLE_ARN").first()
        
        if access_key and access_key.value:
            key_value = access_key.value
            masked_key = f"{key_value[:4]}...{key_value[-4:]}" if len(key_value) > 8 else "****"
            return {"connected": True, "access_key_id": masked_key,
                    "region": region.value if region else "us-east-1",
                    "role_arn": role_arn.value if role_arn else None,
                    "message": "Platform AWS Identity is configured"}
        return {"connected": False, "access_key_id": None, "region": None, "role_arn": None,
                "message": "No platform credentials configured"}

    def update_platform_credentials(self, requesting_user: User, access_key_id: str,
                                   secret_access_key: str, region: str = "us-east-1",
                                   role_arn: str = None) -> dict:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
        from fastapi import HTTPException
        self.verify_super_admin(requesting_user)
        
        try:
            # STS is a global service, region is optional but we can use it for default
            sts = boto3.client('sts', aws_access_key_id=access_key_id,
                              aws_secret_access_key=secret_access_key,
                              region_name=region if region else 'us-east-1')
            identity = sts.get_caller_identity()
            verified_arn = identity.get('Arn', 'Unknown')
            account_id = identity.get('Account', 'Unknown')
            logger.info(f"Platform credentials verified: {verified_arn}")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', 'Invalid credentials')
            logger.error(f"AWS ClientError: {error_code} - {error_msg}")
            raise HTTPException(status_code=400, detail=f"AWS rejected credentials: {error_code} - {error_msg}")
        except NoCredentialsError:
            logger.error("No credentials provided")
            raise HTTPException(status_code=400, detail="AWS credentials are missing or invalid")
        except Exception as e:
            logger.error(f"Unexpected error verifying credentials: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to verify credentials: {str(e)}")
        
        from backend.models.system_config import SystemConfig
        config_items = {
            "PLATFORM_AWS_ACCESS_KEY": access_key_id,
            "PLATFORM_AWS_SECRET": secret_access_key,
            "PLATFORM_AWS_REGION": region,
            "PLATFORM_ROLE_ARN": role_arn or "",
            "PLATFORM_AWS_ACCOUNT_ID": account_id
        }
        for key, value in config_items.items():
            config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if config:
                config.value = value
            else:
                config = SystemConfig(key=key, value=value)
                self.db.add(config)
        self.db.commit()
        return {"connected": True, "account_id": account_id, "verified_arn": verified_arn,
                "region": region, "message": "Platform Identity verified and saved"}

    def disconnect_platform(self, requesting_user: User) -> dict:
        self.verify_super_admin(requesting_user)
        from backend.models.system_config import SystemConfig
        keys_to_remove = ["PLATFORM_AWS_ACCESS_KEY", "PLATFORM_AWS_SECRET", "PLATFORM_AWS_REGION",
                         "PLATFORM_ROLE_ARN", "PLATFORM_AWS_ACCOUNT_ID"]
        for key in keys_to_remove:
            config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if config:
                self.db.delete(config)
        self.db.commit()
        logger.info(f"Platform credentials removed by user {requesting_user.id}")
        return {"connected": False, "message": "Platform credentials removed successfully"}


def get_admin_service(db: Session) -> AdminService:
    return AdminService(db)
