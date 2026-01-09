"""
Cluster Service

Business logic for cluster discovery, registration, and management
"""
import boto3
from typing import List, Optional, Dict, Any

import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from backend.models.account import Account, AccountStatus
from backend.models.cluster import Cluster, ClusterStatus
from backend.models.user import User
from backend.models.instance import Instance
from backend.schemas.cluster_schemas import (
    ClusterCreate, ClusterUpdate, ClusterResponse, ClusterList, 
    AWSConnectRequest, AgentInstallCommand, ClusterFilter
)
from backend.core.exceptions import (
    ResourceNotFoundError, ResourceAlreadyExistsError, ValidationError
)

logger = logging.getLogger(__name__)


class ClusterService:
    def __init__(self, db: Session):
        self.db = db

    def discover_clusters(self, account_id: str, user_id: str) -> List[Dict[str, Any]]:
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account: return []

        try:
            # Assume Role
            sts = boto3.client('sts')
            assumed = sts.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName="Discovery",
                ExternalId=account.external_id
            )
            creds = assumed['Credentials']
            
            # List Clusters
            eks = boto3.client(
                'eks',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name='us-east-1' # Make dynamic in future
            )
            
            clusters = eks.list_clusters()['clusters']
            results = []
            for name in clusters:
                # Save to DB logic here (simplified)
                results.append({"name": name, "status": "discovered"})
            
            return results
        except Exception as e:
            print(f"Error: {e}")
            return []

    def register_cluster(
        self,
        user_id: str,
        cluster_data: ClusterCreate
    ) -> ClusterResponse:
        """
        Register a new cluster manually

        Args:
            user_id: User UUID
            cluster_data: Cluster creation data

        Returns:
            ClusterResponse with registered cluster

        Raises:
            ResourceAlreadyExistsError: If cluster already exists
            ResourceNotFoundError: If account not found
            ValidationError: If validation fails
        """
        # Validate cluster name
        is_valid, error_msg = validate_cluster_name(cluster_data.name)
        if not is_valid:
            raise ValidationError(error_msg)

        # Validate region
        if not validate_aws_region(cluster_data.region):
            raise ValidationError(f"Invalid AWS region: {cluster_data.region}")

        # Get user
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        # Check if account exists and belongs to user's org
        account = self.db.query(Account).filter(
            and_(
                Account.id == cluster_data.account_id,
                Account.organization_id == user.organization_id
            )
        ).first()

        if not account:
            raise ResourceNotFoundError("Account", cluster_data.account_id)

        # Check for duplicate cluster name in account
        existing = self.db.query(Cluster).filter(
            and_(
                Cluster.account_id == cluster_data.account_id,
                Cluster.name == cluster_data.name
            )
        ).first()

        if existing:
            raise ResourceAlreadyExistsError("Cluster", cluster_data.name)

        # Create cluster
        new_cluster = Cluster(
            id=str(uuid.uuid4()),
            account_id=cluster_data.account_id,
            name=cluster_data.name,
            arn=cluster_data.arn,
            region=cluster_data.region,
            cluster_type=cluster_data.cluster_type,
            version=cluster_data.version,
            endpoint=cluster_data.endpoint,
            status=ClusterStatus.DISCOVERED,
            tags=cluster_data.tags or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_cluster)
        self.db.commit()
        self.db.refresh(new_cluster)

        logger.info(
            "Cluster registered",
            cluster_id=new_cluster.id,
            cluster_name=new_cluster.name,
            region=new_cluster.region,
            user_id=user_id
        )

        return self._to_response(new_cluster)

    def connect_aws_cluster(
        self,
        user_id: str,
        connect_data: AWSConnectRequest
    ) -> ClusterResponse:
        """
        Connect cluster via AWS STS (Agentless)

        Args:
            user_id: User UUID
            connect_data: Connection details

        Returns:
            ClusterResponse

        Raises:
            ResourceAlreadyExistsError: If cluster name already exists
            ValidationError: If validation fails
        """
        # Validate inputs
        if not validate_aws_region(connect_data.region):
            raise ValidationError(f"Invalid AWS region: {connect_data.region}")

        # Get user
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        # Check for existing cluster with same name within org
        existing = self.db.query(Cluster).join(Account).filter(
            and_(
                Account.organization_id == user.organization_id,
                Cluster.name == connect_data.name
            )
        ).first()

        if existing:
            raise ResourceAlreadyExistsError("Cluster", connect_data.name)

        # Get or create placeholder account for this org
        account = self.db.query(Account).filter(Account.organization_id == user.organization_id).first()
        
        if not account:
            # Create a default account if none exists
            account = Account(
                id=str(uuid.uuid4()),
                organization_id=user.organization_id,
                aws_account_id=connect_data.role_arn.split(':')[4],
                role_arn="", 
                status=AccountStatus.ACTIVE,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(account)
            self.db.flush()

        # Create cluster record
        new_cluster = Cluster(
            id=str(uuid.uuid4()),
            account_id=account.id,
            name=connect_data.name,
            arn=f"arn:aws:eks:{connect_data.region}:{account.aws_account_id}:cluster/{connect_data.name}", # Constructed ARN
            region=connect_data.region,
            cluster_type="EKS", # Default to EKS for AWS connections
            status=ClusterStatus.ACTIVE, # Assume active if we have role
            agent_installed="N",
            is_agentless="Y",
            aws_role_arn=connect_data.role_arn,
            aws_external_id=connect_data.external_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_cluster)
        self.db.commit()
        self.db.refresh(new_cluster)

        logger.info(
            "Cluster connected via AWS STS",
            cluster_id=new_cluster.id,
            name=new_cluster.name,
            role_arn=new_cluster.aws_role_arn
        )

        return self._to_response(new_cluster)

    def get_cluster(self, cluster_id: str, user_id: str) -> ClusterResponse:
        """
        Get cluster by ID

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID

        Returns:
            ClusterResponse

        Raises:
            ResourceNotFoundError: If cluster not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.organization_id == user.organization_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        return self._to_response(cluster)

    def list_clusters(
        self,
        user_id: str,
        filters: ClusterFilter
    ) -> ClusterList:
        """
        List clusters with filters and pagination

        Args:
            user_id: User UUID
            filters: Filter criteria

        Returns:
            ClusterList with paginated results
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             # Return empty if no org
             return ClusterList(clusters=[], total=0, page=filters.page, page_size=filters.page_size)

        query = self.db.query(Cluster).join(Account).filter(
            Account.organization_id == user.organization_id
        )

        # Apply filters
        if filters.account_id:
            query = query.filter(Cluster.account_id == filters.account_id)
        if filters.region:
            query = query.filter(Cluster.region == filters.region)
        if filters.cluster_type:
            query = query.filter(Cluster.cluster_type == filters.cluster_type)
        if filters.status:
            query = query.filter(Cluster.status == filters.status)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(
                or_(
                    Cluster.name.ilike(search_pattern),
                    Cluster.arn.ilike(search_pattern)
                )
            )

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        clusters = query.order_by(desc(Cluster.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        # Convert to response schemas
        cluster_responses = [self._to_response(cluster) for cluster in clusters]

        return ClusterList(
            clusters=cluster_responses,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def update_cluster(
        self,
        cluster_id: str,
        user_id: str,
        update_data: ClusterUpdate
    ) -> ClusterResponse:
        """
        Update cluster details

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID
            update_data: Update data

        Returns:
            Updated ClusterResponse

        Raises:
            ResourceNotFoundError: If cluster not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.organization_id == user.organization_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(cluster, field, value)

        cluster.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(cluster)

        logger.info(
            "Cluster updated",
            cluster_id=cluster_id,
            updated_fields=list(update_dict.keys()),
            user_id=user_id
        )

        return self._to_response(cluster)

    def delete_cluster(self, cluster_id: str, user_id: str) -> bool:
        """
        Delete cluster

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID

        Returns:
            True if deleted

        Raises:
            ResourceNotFoundError: If cluster not found
            ValidationError: If cluster has active instances
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.organization_id == user.organization_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        # Check for active instances
        active_instances = self.db.query(Instance).filter(
            and_(
                Instance.cluster_id == cluster_id,
                Instance.state.in_(['running', 'pending'])
            )
        ).count()

        if active_instances > 0:
            raise ValidationError(
                f"Cannot delete cluster with {active_instances} active instances"
            )

        self.db.delete(cluster)
        self.db.commit()

        logger.info(
            "Cluster deleted",
            cluster_id=cluster_id,
            cluster_name=cluster.name,
            user_id=user_id
        )

        return True

    def generate_agent_install_command(
        self,
        cluster_id: str,
        user_id: str
    ) -> AgentInstallCommand:
        """
        Generate Kubernetes Agent installation command

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID

        Returns:
            AgentInstallCommand with installation script

        Raises:
            ResourceNotFoundError: If cluster not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.organization_id == user.organization_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        # Generate installation command
        # This would typically include cluster-specific API key
        install_command = f"""# Spot Optimizer Agent Installation
# Cluster: {cluster.name}
# Region: {cluster.region}

kubectl create namespace spot-optimizer

kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: spot-optimizer-config
  namespace: spot-optimizer
data:
  CLUSTER_ID: "{cluster.id}"
  API_ENDPOINT: "https://api.spotoptimizer.com"
  REGION: "{cluster.region}"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spot-optimizer-agent
  namespace: spot-optimizer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spot-optimizer-agent
  template:
    metadata:
      labels:
        app: spot-optimizer-agent
    spec:
      serviceAccountName: spot-optimizer-agent
      containers:
      - name: agent
        image: spotoptimizer/agent:latest
        envFrom:
        - configMapRef:
            name: spot-optimizer-config
        - secretRef:
            name: spot-optimizer-secret
EOF

# Note: Create secret with your API key
# kubectl create secret generic spot-optimizer-secret \\
#   --from-literal=API_KEY=your-api-key-here \\
#   -n spot-optimizer
"""

        logger.info(
            "Agent install command generated",
            cluster_id=cluster_id,
            user_id=user_id
        )

        return AgentInstallCommand(
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            install_command=install_command,
            namespace="spot-optimizer"
        )

    def update_heartbeat(self, cluster_id: str) -> bool:
        """
        Update cluster heartbeat timestamp

        Args:
            cluster_id: Cluster UUID

        Returns:
            True if updated

        Raises:
            ResourceNotFoundError: If cluster not found
        """
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        cluster.last_heartbeat = datetime.utcnow()
        cluster.status = ClusterStatus.ACTIVE
        cluster.updated_at = datetime.utcnow()

        self.db.commit()

        logger.debug(
            "Cluster heartbeat updated",
            cluster_id=cluster_id,
            cluster_name=cluster.name
        )

        return True

    def get_inactive_clusters(self, minutes: int = 10) -> List[Cluster]:
        """
        Get clusters with no heartbeat in specified minutes

        Args:
            minutes: Heartbeat timeout in minutes

        Returns:
            List of inactive clusters
        """
        threshold = datetime.utcnow() - timedelta(minutes=minutes)

        inactive_clusters = self.db.query(Cluster).filter(
            or_(
                Cluster.last_heartbeat < threshold,
                Cluster.last_heartbeat.is_(None)
            )
        ).filter(
            Cluster.status == ClusterStatus.ACTIVE
        ).all()

        return inactive_clusters

    def _to_response(self, cluster: Cluster) -> ClusterResponse:
        """
        Convert Cluster model to ClusterResponse schema

        Args:
            cluster: Cluster model

        Returns:
            ClusterResponse schema
        """
        return ClusterResponse(
            id=cluster.id,
            account_id=cluster.account_id,
            name=cluster.name,
            arn=cluster.arn,
            region=cluster.region,
            cluster_type=cluster.cluster_type.value,
            version=cluster.version,
            endpoint=cluster.endpoint,
            status=cluster.status.value,
            last_heartbeat=cluster.last_heartbeat,
            tags=cluster.tags,
            created_at=cluster.created_at,
            updated_at=cluster.updated_at
        )


def get_cluster_service(db: Session) -> ClusterService:
    """Get cluster service instance"""
    return ClusterService(db)
