import uuid
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.account import Account, AccountStatus
from backend.models.user import User, UserRole
from backend.schemas.account_schemas import AccountCreate, AccountResponse

logger = logging.getLogger(__name__)

class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def _get_platform_client(self, service_name: str):
        """Get an AWS client using platform credentials from SystemConfig"""
        from backend.models.system_config import SystemConfig
        
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        region = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        
        region_name = region.value if region and region.value else 'us-east-1'
        
        if access_key and secret_key and access_key.value and secret_key.value:
            return boto3.client(
                service_name,
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value,
                region_name=region_name
            )
        else:
            # Check if we have env vars as fallback, otherwise raise friendly error
            import os
            if not os.getenv("AWS_ACCESS_KEY_ID"):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400, 
                    detail="Platform AWS Identity is not configured. Please set up Platform Credentials in Admin Settings first."
                )
            
            # Fallback to environment variables
            return boto3.client(service_name, region_name=region_name)

    def verify_connection(self, role_arn: str, external_id: str) -> bool:
        """
        Verify AWS connection by attempting to assume role.
        The external_id MUST match the Trust Policy condition on the target role.
        """
        try:
            sts = self._get_platform_client('sts')
            sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="SpotOptimizerVerify",
                ExternalId=external_id
            )
            return True
        except ClientError as e:
            # Check for AccessDenied which likely means ExternalID mismatch
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDenied':
                raise HTTPException(400, "Access Denied: Please ensure the External ID in your Role Trust Policy matches exactly.")
            raise HTTPException(400, f"AWS Connection Failed: {str(e)}")

    def list_accounts(self, user: "User") -> List[Account]:
        """
        List accounts based on RBAC:
        - Org Admin: All accounts in organization
        - Team Lead: All accounts owned by team members
        - Member: Only their own accounts
        """
        query = self.db.query(Account).filter(Account.organization_id == user.organization_id)
        
        if user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT:
            return query.all()
        
        elif user.role == UserRole.TEAM_LEAD:
            if not user.team_id:
                return query.filter(Account.user_id == user.id).all() # Fallback to own
            
            # Get all user IDs in the team
            team_members = self.db.query(User.id).filter(User.team_id == user.team_id).all()
            member_ids = [m.id for m in team_members]
            return query.filter(Account.user_id.in_(member_ids)).all()
            
        elif user.role == UserRole.MEMBER:
            return query.filter(Account.user_id == user.id).all()
            
        return []

    def get_account(self, account_id: str, organization_id: str) -> Account:
        """Get a specific account by ID"""
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == organization_id
        ).first()
        if not account:
            raise HTTPException(404, "Account not found")
        return account

    def link_aws_account(
        self,
        organization_id: str,
        aws_account_id: str,
        role_arn: str,
        external_id: str, # Kept for API compatibility, but we overwrite it with Org's ID
        requester
    ) -> dict:
        """Link a new AWS account after verifying credentials"""
        from backend.models.user import UserRole
        from backend.models.approval import Approval, ApprovalType, ApprovalStatus, JITScope
        from backend.models.organization import Organization
        
        # SECURITY: Always enforce the Organization's unique External ID
        # Accessing Organization directly here to avoid circular imports with OrgService
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org or not org.external_id:
            raise HTTPException(500, "Organization configuration error: Missing External ID")
            
        secure_external_id = org.external_id
        
        # Verify using the SECURE ID
        self.verify_connection(role_arn, secure_external_id)
        
        # ... rest ...
        
        # Check if account already exists
        existing = self.db.query(Account).filter(
            Account.aws_account_id == aws_account_id,
            Account.organization_id == organization_id
        ).first()
        if existing:
            raise HTTPException(400, "Account already linked")

        # Determine Status - Check Team-Specific Governance
        status = AccountStatus.ACTIVE
        needs_approval = False
        
        if requester.role == UserRole.MEMBER:
            # Check team-specific governance config first
            if requester.team and requester.team.governance_config:
                # If team has CONNECT_ACCOUNT rule enabled, require approval
                needs_approval = requester.team.governance_config.get("CONNECT_ACCOUNT", False)
            else:
                # Fallback to system default: Members always need approval
                needs_approval = True
                
            if needs_approval:
                status = AccountStatus.PENDING_APPROVAL

        account = Account(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            aws_account_id=aws_account_id,
            role_arn=role_arn,
            external_id=secure_external_id, # Persist the ID that was actually used
            status=status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(account)
        self.db.commit()
        
        if needs_approval:
            approval_req = Approval(
                organization_id=organization_id,
                user_id=requester.id,
                type=ApprovalType.ACTION,
                action_type="CONNECT_ACCOUNT",
                resource_id=account.id,
                status=ApprovalStatus.PENDING,
                jit_scope=JITScope.ORGANIZATION,
                jit_metadata={"aws_account_id": aws_account_id}
            )
            self.db.add(approval_req)
            self.db.commit()
            self.db.refresh(account)
            # Return account regardless - status indicates pending
            return account

        self.db.refresh(account)
        return account
    def delete_account(self, account_id: str, organization_id: str) -> bool:
        """Delete/unlink an AWS account and all its child data in safe dependency order."""
        from backend.models.cluster import Cluster
        from sqlalchemy import text

        account = self.get_account(account_id, organization_id)

        # Collect all cluster IDs for this account so we can delete children first
        cluster_ids = [c.id for c in self.db.query(Cluster.id).filter(
            Cluster.account_id == account_id
        ).all()]

        try:
            if cluster_ids:
                placeholders = ", ".join(f"'{cid}'" for cid in cluster_ids)

                # CRITICAL: When a Postgres DELETE fails (e.g. table doesn't exist,
                # FK violation), Python catching the exception is NOT enough — Postgres
                # marks the entire connection transaction as aborted.  All subsequent
                # SQL on the same session is then rejected with InFailedSqlTransaction.
                #
                # Fix: wrap each table delete in a SAVEPOINT. On failure, roll back to
                # the savepoint so the outer transaction stays alive.
                tables_with_cluster_fk = [
                    "pod_metrics",
                    "cluster_metrics",
                    "agent_actions",
                    "execution_states",
                    "rightsizing_proposals",
                    "optimizer_states",
                    "optimization_jobs",
                    "rebalancing_actions",
                    "substitute_states",
                    "cluster_optimization_settings",
                    "optimization_strategy",
                    "stateless_runtime_rules",
                    "stateful_rules",
                    "cluster_template_mappings",
                    "cluster_policies",
                    "chaos_experiments",
                    "api_keys",
                    "instances",
                ]

                for table in tables_with_cluster_fk:
                    sp_name = f"sp_{table}"
                    try:
                        self.db.execute(text(f"SAVEPOINT {sp_name}"))
                        self.db.execute(
                            text(f"DELETE FROM {table} WHERE cluster_id IN ({placeholders})")
                        )
                        self.db.execute(text(f"RELEASE SAVEPOINT {sp_name}"))
                    except Exception as table_err:
                        try:
                            self.db.execute(text(f"ROLLBACK TO SAVEPOINT {sp_name}"))
                        except Exception:
                            pass
                        logger.warning(
                            "Skipped delete from '%s' (table may not exist yet): %s",
                            table, table_err
                        )

                # Delete account-level FK rows
                try:
                    self.db.execute(text("SAVEPOINT sp_authorized_resources"))
                    self.db.execute(
                        text(f"DELETE FROM authorized_resources WHERE account_id = '{account_id}'")
                    )
                    self.db.execute(text("RELEASE SAVEPOINT sp_authorized_resources"))
                except Exception:
                    try:
                        self.db.execute(text("ROLLBACK TO SAVEPOINT sp_authorized_resources"))
                    except Exception:
                        pass

                # Delete the clusters themselves
                self.db.execute(
                    text(f"DELETE FROM clusters WHERE id IN ({placeholders})")
                )

            self.db.delete(account)
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.exception("Failed to delete account %s: %s", account_id, e)
            raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")



    def validate_account(self, account_id: str, organization_id: str) -> Account:
        """Validate account credentials are still working"""
        account = self.get_account(account_id, organization_id)
        
        try:
            self.verify_connection(account.role_arn, account.external_id)
            account.status = AccountStatus.ACTIVE
            account.last_validated = datetime.utcnow()
            account.updated_at = datetime.utcnow()
            
            # Trigger discovery
            try:
                from backend.services.cluster_service import ClusterService
                cluster_service = ClusterService(self.db)
                # Pass organization_id as user_id for context, though currently unused
                cluster_service.discover_clusters(account.id, organization_id)
            except Exception as e:
                # Log but don't fail validation
                print(f"Discovery trigger failed: {e}")
                
        except HTTPException:
            account.status = AccountStatus.ERROR
            account.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(account)
        return account

    def set_default_account(self, account_id: str, organization_id: str) -> Account:
        """Set an account as the default for the organization"""
        # First, unset any existing default
        self.db.query(Account).filter(
            Account.organization_id == organization_id,
            Account.is_default == True
        ).update({"is_default": False})
        
        # Set this account as default
        account = self.get_account(account_id, organization_id)
        account.is_default = True
        account.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(account)
        return account

    def disconnect_account(self, account_id: str, organization_id: str) -> Account:
        """
        Disconnect AWS account - strips credentials but keeps historical data.
        This is safer than delete as it preserves cost/usage history.
        """
        account = self.get_account(account_id, organization_id)
        
        # Strip credentials (don't delete the record)
        account.role_arn = None
        account.external_id = None
        account.status = AccountStatus.DISCONNECTED
        account.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(account)
        return account

    # Legacy method for backwards compatibility
    def link_account(self, user_id: int, data: AccountCreate) -> Account:
        """Legacy link account method"""
        return self.link_aws_account(
            organization_id=str(user_id),  # Map user_id to org_id (simplified)
            aws_account_id=data.account_id,
            role_arn=data.role_arn,
            external_id=data.external_id
        )

def get_account_service(db: Session) -> AccountService:
    return AccountService(db)

