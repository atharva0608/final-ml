"""
Cluster Service

Business logic for cluster discovery, registration, and management
"""
import boto3
import threading
import json
from typing import List, Optional, Dict, Any

import uuid
import logging
import secrets
import string
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from backend.models.account import Account, AccountStatus
from backend.models.cluster import Cluster, ClusterStatus
from backend.models.user import User
from backend.models.instance import Instance, InstanceLifecycle
from backend.schemas.cluster_schemas import (
    ClusterCreate, ClusterUpdate, ClusterResponse, ClusterList,
    AWSConnectRequest, AgentInstallCommand, ClusterFilter,
    InstallScriptRequest, InstallScriptResponse
)
from backend.core.exceptions import (
    ResourceNotFoundError, ResourceAlreadyExistsError, ValidationError
)
from backend.models.cluster import ClusterType, ClusterStatus
from backend.core.validators import validate_cluster_name, validate_aws_region
from backend.schemas.cluster_schemas import ClusterListItem
from backend.core.config import CREDENTIAL_CACHE_TTL_BUFFER_SECS, MAX_CONCURRENT_ASSUME_ROLE

logger = logging.getLogger(__name__)

# Module-level semaphore — lazy init
_assume_role_semaphore = None


def _get_assume_role_semaphore():
    global _assume_role_semaphore
    if _assume_role_semaphore is None:
        _assume_role_semaphore = threading.Semaphore(MAX_CONCURRENT_ASSUME_ROLE)
    return _assume_role_semaphore


def get_client_credentials(account_id: str, role_arn: str) -> dict:
    """
    Assume IAM role and return credentials, using Redis cache to avoid redundant STS calls.
    Cache key: credential_cache:{account_id}, TTL = expiry - CREDENTIAL_CACHE_TTL_BUFFER_SECS.
    """
    from backend.core.redis_client import get_redis_client, key_credential_cache
    redis_client = get_redis_client()
    cache_key = key_credential_cache(account_id)

    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    semaphore = _get_assume_role_semaphore()
    with semaphore:
        # Double-check after acquiring semaphore
        cached = redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        sts = boto3.client('sts')
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f'spot-optimizer-{account_id[:8]}',
        )
        creds = assumed['Credentials']
        result = {
            'aws_access_key_id': creds['AccessKeyId'],
            'aws_secret_access_key': creds['SecretAccessKey'],
            'aws_session_token': creds['SessionToken'],
        }

        # Calculate TTL with buffer
        expiry = creds['Expiration']
        if hasattr(expiry, 'timestamp'):
            ttl = int(expiry.timestamp() - datetime.utcnow().timestamp()) - CREDENTIAL_CACHE_TTL_BUFFER_SECS
        else:
            ttl = 3600 - CREDENTIAL_CACHE_TTL_BUFFER_SECS
        if ttl > 0:
            redis_client.setex(cache_key, ttl, json.dumps(result))

        return result


def _get_wie_enrichment(redis_client, json_mod, cluster_id: str, namespace: str, owner_kind: str) -> dict:
    """
    Read v4.3 WIE classification from Redis and return enrichment fields.
    Returns all None values if engine hasn't run yet (backward compatible).
    """
    empty = {"wie_tier": None, "wie_confidence": None, "wie_spot_score": None, "wie_spot_friendly": None}
    if not redis_client or not owner_kind or owner_kind in ('', 'Pod'):
        return empty
    try:
        key = f"spot:wie:classification:{cluster_id}:{namespace}/{owner_kind}"
        raw = redis_client.get(key)
        if not raw:
            return empty
        data = json_mod.loads(raw)
        return {
            "wie_tier": data.get("tier"),
            "wie_confidence": data.get("confidence_state"),
            "wie_spot_score": data.get("spot_score"),
            "wie_spot_friendly": data.get("spot_friendly"),
        }
    except Exception:
        return empty


class ClusterService:
    def __init__(self, db: Session):
        self.db = db

    def _get_cluster_with_access(self, cluster_id: str, user_id: str) -> Cluster:
        """
        Helper to get cluster and verify user has access
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)
        
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)
        
        # Check organization access
        account = self.db.query(Account).filter(Account.id == cluster.account_id).first()
        if not account or account.organization_id != user.organization_id:
            raise ResourceNotFoundError("Cluster", cluster_id)  # Hide unauthorized
        
        return cluster

    def verify_connection(self, cluster_id: str, user_id: str) -> dict:
        """
        Verify cluster connection status (agent is connected)
        Only returns connected=True if agent has sent a heartbeat
        """
        cluster = self._get_cluster_with_access(cluster_id, user_id)
        
        # Check if agent has sent heartbeat (real connection)
        is_connected = cluster.status == ClusterStatus.ACTIVE and cluster.last_heartbeat is not None
        
        # Also check if heartbeat is recent (within 2 minutes)
        if is_connected and cluster.last_heartbeat:
            from datetime import timedelta
            threshold = datetime.utcnow() - timedelta(minutes=2)
            is_connected = cluster.last_heartbeat > threshold
        
        return {
            "status": "connected" if is_connected else "pending",
            "cluster_id": cluster.id,
            "cluster_name": cluster.name,
            "last_heartbeat": (cluster.last_heartbeat.isoformat() + 'Z') if cluster.last_heartbeat else None
        }

    def update_resource_costs(self, cluster_id: str, user_id: str, costs: dict) -> dict:
        """
        Update resource costs for a cluster
        """
        cluster = self._get_cluster_with_access(cluster_id, user_id)
        
        # Store costs in cluster tags (or could use a separate table)
        if not cluster.tags:
            cluster.tags = {}
        
        cluster.tags['resource_costs'] = {
            'cpu_cost': costs.get('cpu_cost', '0'),
            'memory_cost': costs.get('memory_cost', '0'),
            'storage_cost': costs.get('storage_cost', '0'),
            'ingress_cost': costs.get('ingress_cost', '0'),
            'egress_cost': costs.get('egress_cost', '0'),
        }
        cluster.updated_at = datetime.utcnow()
        self.db.commit()
        
        return {
            "status": "success",
            "cluster_id": cluster.id,
            "costs": cluster.tags['resource_costs']
        }

    def discover_clusters(self, account_id: str, user_id: str) -> List[Dict[str, Any]]:
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account: return []

        # Scan these regions — covers all common EKS regions
        # Always includes the account's configured region plus all major regions
        SCAN_REGIONS = [
            "ap-south-1", "ap-southeast-1", "ap-southeast-2",
            "ap-northeast-1", "ap-northeast-2",
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "eu-west-1", "eu-west-2", "eu-central-1",
            "ca-central-1", "sa-east-1",
        ]
        # Put the account's own region first so it's found fast
        account_region = account.region or "us-east-1"
        regions_to_scan = [account_region] + [r for r in SCAN_REGIONS if r != account_region]

        discovered = []
        try:
            # Assume Role
            sts = boto3.client('sts')
            assumed = sts.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName="Discovery",
                ExternalId=account.external_id
            )
            creds = assumed['Credentials']

            for region in regions_to_scan:
                try:
                    eks = boto3.client(
                        'eks',
                        aws_access_key_id=creds['AccessKeyId'],
                        aws_secret_access_key=creds['SecretAccessKey'],
                        aws_session_token=creds['SessionToken'],
                        region_name=region
                    )
                    cluster_names = []
                    paginator = eks.get_paginator('list_clusters')
                    for page in paginator.paginate():
                        cluster_names.extend(page.get('clusters', []))
                except Exception:
                    continue  # Region not accessible — skip silently

                for cluster_name in cluster_names:
                    try:
                        details = eks.describe_cluster(name=cluster_name)['cluster']
                    except Exception:
                        continue

                    cluster = self.db.query(Cluster).filter(
                        Cluster.name == cluster_name,
                        Cluster.account_id == account.id,
                        Cluster.is_dismissed == False,
                    ).first()

                    new_arn = details.get('arn', '')

                    if not cluster:
                        cluster = Cluster(
                            id=str(uuid.uuid4()),
                            name=cluster_name,
                            account_id=account.id,
                            region=region,
                            arn=new_arn,
                            status=ClusterStatus.DISCOVERED,
                            version=details.get('version'),
                            endpoint=details.get('endpoint'),
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        self.db.add(cluster)
                        logger.info(f"Discovered new cluster: {cluster_name} in {region}")
                    else:
                        # Detect if the physical cluster was recreated
                        # Case 1: ARN changed (different physical cluster)
                        # Case 2: Old record had no ARN but was stale/disconnected
                        arn_changed = (new_arn and cluster.arn and cluster.arn != new_arn)
                        stale_without_arn = (
                            new_arn
                            and not cluster.arn
                            and cluster.status in (
                                ClusterStatus.DISCONNECTED,
                                ClusterStatus.TERMINATED,
                                ClusterStatus.INACTIVE,
                            )
                            and cluster.agent_installed == "Y"
                        )
                        is_recreated = arn_changed or stale_without_arn
                        if is_recreated:
                            logger.info(
                                f"Cluster {cluster_name} was recreated or stale "
                                f"(old_arn={cluster.arn}, new_arn={new_arn}, "
                                f"old_status={cluster.status}). "
                                f"Resetting agent data."
                            )
                            cluster.arn = new_arn
                            cluster.cluster_uid = uuid.uuid4().hex[:8]
                            cluster.agent_installed = "N"
                            cluster.is_agentless = "N"
                            cluster.last_heartbeat = None
                            cluster.node_count = 0
                            cluster.spot_count = 0
                            cluster.cpu_total = 0
                            cluster.mem_total = 0
                            cluster.cpu_usage_pct = 0
                            cluster.mem_usage_pct = 0
                            cluster.monthly_cost = 0
                            cluster.estimated_savings = 0
                            cluster.potential_savings_monthly = 0
                            cluster.realized_savings_monthly = 0
                            cluster.on_demand_node_count = 0
                            cluster.inventory_summary = None
                            cluster.version = details.get('version')
                            cluster.karpenter_mode = None
                            cluster.auto_rebalance_enabled = False
                            cluster.rightsizing_enabled = False
                        elif not cluster.arn and new_arn:
                            # Backfill ARN if it was missing
                            cluster.arn = new_arn

                        cluster.status = ClusterStatus.DISCOVERED
                        if not is_recreated:
                            cluster.version = details.get('version')
                        cluster.endpoint = details.get('endpoint')
                        cluster.region = region  # Update region in case it changed
                        cluster.updated_at = datetime.utcnow()

                    discovered.append({
                        "name": cluster.name,
                        "region": region,
                        "status": "active",
                        "version": cluster.version
                    })

            self.db.commit()

            # Invalidate cluster list cache so the UI shows results immediately
            try:
                import redis as _redis_lib
                _r = _redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
                for key in _r.scan_iter("clusters:*"):
                    _r.delete(key)
            except Exception:
                pass

            return discovered

        except Exception as e:
            logger.error(f"Discovery failed for account {account.id}: {e}")
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

        # Check for duplicate cluster name in account (exclude dismissed/deleted clusters)
        existing = self.db.query(Cluster).filter(
            and_(
                Cluster.account_id == cluster_data.account_id,
                Cluster.name == cluster_data.name,
                Cluster.is_dismissed == False,
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
            f"Cluster registered: id={new_cluster.id} name={new_cluster.name} region={new_cluster.region} user_id={user_id}"
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

        # Check for existing cluster with same name within org (exclude dismissed/deleted)
        existing = self.db.query(Cluster).join(Account).filter(
            and_(
                Account.organization_id == user.organization_id,
                Cluster.name == connect_data.name,
                Cluster.is_dismissed == False,
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
                aws_account_id=(connect_data.role_arn or '').split(':')[4] if len((connect_data.role_arn or '').split(':')) > 4 else '',
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
            f"Cluster connected via AWS STS: id={new_cluster.id} name={new_cluster.name} role_arn={new_cluster.aws_role_arn}"
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
        import redis
        import json
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             # Return empty if no org
             return ClusterList(clusters=[], total=0, page=filters.page, page_size=filters.page_size)

        # Try Redis cache for fast UX (5 second TTL for real-time status)
        cache_key = f"clusters:{user.organization_id}:{filters.page}:{filters.page_size}:{filters.status}:{filters.search or ''}"
        try:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            r = redis.from_url(redis_url)
            cached = r.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return ClusterList(**cached_data)
        except Exception as e:
            logger.debug(f"Redis cache miss or error: {e}")

        # SUPER_ADMIN can see all clusters across all organizations
        if user.role == "SUPER_ADMIN":
            query = self.db.query(Cluster).join(Account).filter(
                Cluster.status != ClusterStatus.PENDING,
                Cluster.is_dismissed == False,
            )
        else:
            query = self.db.query(Cluster).join(Account).filter(
                Account.organization_id == user.organization_id,
                Cluster.status != ClusterStatus.PENDING,  # Exclude PENDING (unverified) clusters
                Cluster.is_dismissed == False,             # Exclude dismissed clusters
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
                    Cluster.arn.ilike(search_pattern),
                    Cluster.cluster_uid.ilike(search_pattern)
                )
            )

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        clusters = query.order_by(desc(Cluster.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()
        
        # Convert to ClusterListItem schemas
        # Batch-fetch all instance counts for this page in ONE aggregated query
        # instead of 3 COUNT queries per cluster (N+1 → 1 query total).
        from sqlalchemy import func
        cluster_ids_page = [c.id for c in clusters]
        _count_rows = self.db.query(
            Instance.cluster_id,
            Instance.lifecycle,
            func.count(Instance.id).label('cnt')
        ).filter(
            Instance.cluster_id.in_(cluster_ids_page),
            Instance.state == 'running',
            Instance.instance_type.isnot(None),
            Instance.instance_type != '',
            Instance.instance_type != 'unknown',
        ).group_by(Instance.cluster_id, Instance.lifecycle).all()

        _counts_map: dict = {}  # {cluster_id: {total, spot, on_demand}}
        for _row in _count_rows:
            _cid = _row.cluster_id
            if _cid not in _counts_map:
                _counts_map[_cid] = {'total': 0, 'spot': 0, 'on_demand': 0}
            _counts_map[_cid]['total'] += _row.cnt
            if _row.lifecycle == InstanceLifecycle.SPOT:
                _counts_map[_cid]['spot'] += _row.cnt
            elif _row.lifecycle == InstanceLifecycle.ON_DEMAND:
                _counts_map[_cid]['on_demand'] += _row.cnt

        cluster_list_items = []
        for cluster in clusters:
            _cluster_counts = _counts_map.get(cluster.id, {'total': 0, 'spot': 0, 'on_demand': 0})
            total_instances = _cluster_counts['total']
            spot_instances = _cluster_counts['spot']
            on_demand_instances = _cluster_counts['on_demand']

            cluster_list_items.append(ClusterListItem(
                id=cluster.id,
                cluster_uid=cluster.cluster_uid,
                name=cluster.name,
                region=cluster.region,
                status=cluster.status.value,
                # RC7 fix: avoid stale fallback when DB clearly has data.
                # `or` treats 0 as falsy so "0 spot instances" incorrectly fell back to
                # the stale discovery teaser count.  Only fall back if DB found nothing at all.
                node_count=total_instances if total_instances > 0 else (cluster.node_count or 0),
                spot_count=spot_instances if total_instances > 0 else (cluster.spot_count or 0),
                # RC7b: use same guard as above — `or` treats 0 as falsy, causing stale fallback
                # when all instances are spot (on_demand_instances == 0).
                on_demand_node_count=on_demand_instances if total_instances > 0 else (cluster.on_demand_node_count or 0),
                monthly_cost=float(cluster.monthly_cost or 0),
                agent_installed=cluster.agent_installed == 'Y',
                last_heartbeat=cluster.last_heartbeat,
                # Include savings fields for frontend
                estimated_savings=float(cluster.estimated_savings or 0),
                potential_savings_monthly=float(cluster.potential_savings_monthly or 0),
                realized_savings_monthly=float(getattr(cluster, 'realized_savings_monthly', 0) or 0),
                cpu_total=cluster.cpu_total or 0,
                mem_total=cluster.mem_total or 0,
                cpu_usage_pct=float(cluster.cpu_usage_pct or 0),
                mem_usage_pct=float(cluster.mem_usage_pct or 0),
                auto_rebalance_enabled=bool(cluster.auto_rebalance_enabled),
                rightsizing_enabled=bool(getattr(cluster, 'rightsizing_enabled', False)),
            ))

        # Batch-read health scores (one pipeline round-trip for the whole page).
        # Key written by health_monitor every 5 min: cluster_health:{cluster_id}
        # overall_health is 0-100; map to letter grades matching monitor thresholds.
        try:
            _hr = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
            _pipe = _hr.pipeline(transaction=False)
            for _ci in cluster_list_items:
                _pipe.get(f"cluster_health:{_ci.id}")
            _health_raws = _pipe.execute()

            def _grade(score_raw) -> Optional[str]:
                if score_raw is None:
                    return None
                try:
                    _s = json.loads(score_raw).get("overall_health", None)
                    if _s is None:
                        return None
                    _s = float(_s)
                    if _s >= 85:
                        return "A"
                    if _s >= 70:
                        return "B"
                    if _s >= 50:
                        return "C"
                    return "D"
                except Exception:
                    return None

            for _ci, _raw in zip(cluster_list_items, _health_raws):
                _ci.health_score = _grade(_raw)
        except Exception as _he:
            logger.debug(f"Health score enrichment failed (non-blocking): {_he}")

        result = ClusterList(
            clusters=cluster_list_items,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )
        
        # Cache result in Redis for 30 seconds.
        # 5s was too short — it expired mid-discovery, returning empty/partial lists and
        # causing the UI "blank screen" flicker. 30s is safe: discovery runs every 5 min
        # so at worst the list is 30s behind a node join event (well within tolerance).
        try:
            r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
            r.setex(cache_key, 30, result.model_dump_json())
        except Exception as e:
            logger.debug(f"Failed to cache cluster list: {e}")
        
        return result

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
            f"Cluster updated: id={cluster_id} fields={list(update_dict.keys())} user_id={user_id}"
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

        # ── Cascade-delete all related records before deleting the cluster ──
        # (FK constraints prevent cluster deletion if child rows exist)

        # Instances
        self.db.query(Instance).filter(Instance.cluster_id == cluster_id).delete(synchronize_session=False)

        # Cluster metrics
        try:
            from backend.models.cluster_metric import ClusterMetric
            self.db.query(ClusterMetric).filter(ClusterMetric.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Rebalancing actions
        try:
            from backend.models.rebalancing_action import RebalancingAction
            self.db.query(RebalancingAction).filter(RebalancingAction.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Optimizer state
        try:
            from backend.models.optimizer_state import OptimizerState
            self.db.query(OptimizerState).filter(OptimizerState.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Cluster cooldowns
        try:
            from backend.models.cluster_cooldown import ClusterCooldown
            self.db.query(ClusterCooldown).filter(ClusterCooldown.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Pool cooldowns
        try:
            from backend.models.pool_cooldown import PoolCooldown
            self.db.query(PoolCooldown).filter(PoolCooldown.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Substitute states
        try:
            from backend.models.substitute_state import SubstituteState
            self.db.query(SubstituteState).filter(SubstituteState.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Optimization settings
        try:
            from backend.models.cluster import ClusterOptimizationSettings, StatelessRuntimeRules
            self.db.query(ClusterOptimizationSettings).filter(ClusterOptimizationSettings.cluster_id == cluster_id).delete(synchronize_session=False)
            self.db.query(StatelessRuntimeRules).filter(StatelessRuntimeRules.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Pod metrics
        try:
            from backend.models.pod_metric import PodMetric
            self.db.query(PodMetric).filter(PodMetric.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Agent actions (has FK ondelete=CASCADE but must be explicit to avoid
        # SQLAlchemy identity-map conflicts when passive_deletes=True is set)
        try:
            from backend.models.agent_action import AgentAction
            self.db.query(AgentAction).filter(AgentAction.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Daily cluster stats
        try:
            from backend.models.daily_cluster_stats import DailyClusterStat
            self.db.query(DailyClusterStat).filter(DailyClusterStat.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Cluster template mappings
        try:
            from backend.models.node_template import ClusterTemplateMapping
            self.db.query(ClusterTemplateMapping).filter(ClusterTemplateMapping.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Rightsizing proposals (no ondelete=CASCADE — must delete explicitly)
        try:
            from backend.models.rightsizing_proposal import RightsizingProposal
            self.db.query(RightsizingProposal).filter(RightsizingProposal.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Hibernation schedule ↔ cluster join table (no CASCADE on FK)
        try:
            from backend.models.hibernation_schedule_clusters import hibernation_schedule_clusters as _hsc
            self.db.execute(_hsc.delete().where(_hsc.c.cluster_id == cluster_id))
        except Exception:
            pass

        # Cluster cooldown states (Redis-restart resilience table added 2026-03-25)
        try:
            from backend.models.cluster import ClusterCooldownState
            self.db.query(ClusterCooldownState).filter(ClusterCooldownState.cluster_id == cluster_id).delete(synchronize_session=False)
        except Exception:
            pass

        # Clear Redis warm spare & substitute state for this cluster
        try:
            from backend.core.redis_client import get_redis_client
            _redis = get_redis_client()
            for key in [
                f"spot:substitute:state:{cluster_id}",
                f"spot:substitute:meta:{cluster_id}",
                f"spot:substitute:next_spare:{cluster_id}",
                f"spot:cooldown:cluster:{cluster_id}",
                f"karpenter_config:{cluster_id}",
                f"clusters:org:{getattr(cluster, 'account', None) and cluster.account.organization_id}",
            ]:
                try:
                    _redis.delete(key)
                except Exception:
                    pass
        except Exception:
            pass


        account = getattr(cluster, 'account', None)

        # ── AWS CLEANUP: delete all Karpenter resources the platform created ─
        # Runs regardless of whether agent/Karpenter are currently installed.
        # Idempotent — already-deleted resources are silently skipped.
        if account and (account.role_arn or cluster.aws_role_arn):
            try:
                from backend.services.agent_injector import AgentInjectorService as _Inj
                _inj = _Inj(self.db)
                _role_arn = cluster.aws_role_arn or account.role_arn
                _ext_id = cluster.aws_external_id or account.external_id
                _region = cluster.region or "ap-south-1"
                _creds = _inj._assume_role(
                    role_arn=_role_arn, external_id=_ext_id or "", region=_region)
                if _creds:
                    _result = _inj.delete_all_cluster_karpenter_resources(
                        cluster_name=cluster.name, region=_region, credentials=_creds)
                    logger.info(
                        f"AWS Karpenter cleanup for {cluster.name}: "
                        f"{len(_result.get('deleted', []))} deleted, "
                        f"{len(_result.get('errors', []))} warnings"
                    )
            except Exception as _aws_err:
                logger.warning(
                    f"AWS Karpenter cleanup failed for {cluster.name} (non-fatal): {_aws_err}")
                # Proceed with DB deletion anyway

        # Uninstall Agent from Kubernetes if installed
        if cluster.agent_installed == 'Y' and account and account.role_arn:
            try:
                from backend.services.agent_injector import AgentInjectorService
                injector = AgentInjectorService(self.db)

                logger.info(f"Uninstalling agent from cluster {cluster.name} before deletion...")
                injector.uninstall_agent(
                    cluster_name=cluster.name,
                    cluster_endpoint=cluster.endpoint,
                    cluster_ca_data=cluster.ca_data,
                    role_arn=account.role_arn,
                    external_id=cluster.aws_external_id or account.external_id,
                    region=cluster.region
                )
            except Exception as e:
                logger.warning(f"Failed to uninstall agent during cluster deletion: {e}")
                # Proceed with deletion anyway

        self.db.delete(cluster)
        self.db.commit()

        logger.info(
            f"Cluster deleted: id={cluster_id} name={cluster.name} user_id={user_id}"
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
            f"Agent install command generated: cluster_id={cluster_id} user_id={user_id}"
        )

        return AgentInstallCommand(
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            install_command=install_command,
            yaml_manifest=install_command,  # Reusing for simplicity as per requirements
            instructions=["Run the command in your terminal", "Monitor the connection status in dashboard"]
        )

    def generate_helm_install_script(self, cluster_id: str, user_id: str) -> str:
        """
        Generate a shell script to install the agent via Helm
        One-click experience: curl | bash
        """
        cluster = self._get_cluster_with_access(cluster_id, user_id)
        
        from backend.core.redis_client import get_backend_public_url
        backend_url = get_backend_public_url()
        ws_url = backend_url.replace('https://', 'wss://').replace('http://', 'ws://')

        script = f"""#!/bin/bash
set -e

echo "🚀 Starting Spot Optimizer Agent Installation (Helm)..."
echo "📍 Cluster: {cluster.name}"

# 1. Dependency Checks
if ! command -v helm &> /dev/null; then
    echo "⚙️  Helm not found. Installing Helm..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# 2. Chart Location
CHART_URI="oci://public.ecr.aws/spot-optimizer/spot-optimizer-agent" # Example Placeholder

echo "📦 Installing Chart from $CHART_URI..."

# 3. Construct Helm Command
HELM_CMD="helm upgrade --install spot-optimizer-agent $CHART_URI \\
  --namespace spot-optimizer \\
  --create-namespace \\
  --set config.apiKey='{cluster.api_key}' \\
  --set config.backendUrl='{ws_url}/ws/cluster/{cluster.id}' \\
  --set config.clusterId='{cluster.id}' \\
  --wait"

# Execute
eval "$HELM_CMD"

echo ""
echo "✅ Agent successfully deployed!"
"""
        return script

    def generate_install_script_provider(
        self,
        user_id: str,
        request: InstallScriptRequest
    ) -> InstallScriptResponse:
        """
        Generate install script for a new cluster based on provider
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user or not user.organization_id:
             raise ResourceNotFoundError("User or Organization", user_id)

        # 1. Get or Create Default Account for Org
        account = self.db.query(Account).filter(Account.organization_id == user.organization_id).first()
        if not account:
            account = Account(
                id=str(uuid.uuid4()),
                organization_id=user.organization_id,
                aws_account_id="000000000000", # Placeholder
                role_arn="", 
                status=AccountStatus.ACTIVE,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(account)
            self.db.flush()

        # 2. Check if cluster exists
        cluster = self.db.query(Cluster).filter(
            and_(
                Cluster.account_id == account.id,
                Cluster.name == request.cluster_name
            )
        ).first()

        if not cluster:
            # Create new
            cluster = Cluster(
                id=str(uuid.uuid4()),
                name=request.cluster_name,
                account_id=account.id,
                region=request.region or 'us-east-1',
                status=ClusterStatus.PENDING,
                api_key=os.getenv("AGENT_API_KEY") or secrets.token_urlsafe(32)
            )
            self.db.add(cluster)
            self.db.commit()
            self.db.refresh(cluster)
        
        # 2. Get Configuration
        from backend.core.redis_client import get_backend_public_url
        backend_url = get_backend_public_url()
        ws_url = backend_url.replace('https://', 'wss://').replace('http://', 'ws://')
        
        # Placeholder - updated by publish_to_dockerhub.sh
        CHART_URI="oci://public.ecr.aws/spot-optimizer/spot-optimizer-agent" # Updated via script

        # 3. Return Data (Script field used for command template or left empty)
        # We reuse the existing response model to assume 'script' might hold the URI or we assume frontend doesn't need 'script'
        
        return InstallScriptResponse(
            cluster_id=cluster.id,
            api_key=cluster.api_key,
            script=CHART_URI # Hijacking script field to pass Chart URI to frontend
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

        # ── COORDINATOR INIT (GAP 2 FIX) ──────────────────────────────
        try:
            from backend.services.optimizer_coordinator import OptimizerCoordinator
            from backend.core.redis_client import get_redis_client
            coordinator = OptimizerCoordinator(self.db, get_redis_client())
            coordinator.initialize_cluster_state(cluster_id)
            logger.info(f"Initialized optimizer state for cluster {cluster_id}")
        except Exception as e:
            logger.error(f"Failed to init optimizer state: {e}")

        logger.debug(
            f"Cluster heartbeat updated: id={cluster_id} name={cluster.name}"
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
            cluster_uid=cluster.cluster_uid,
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
            updated_at=cluster.updated_at,
            auto_rebalance_enabled=cluster.auto_rebalance_enabled or False,
            monthly_cost=float(cluster.monthly_cost or 0),
            estimated_savings=float(cluster.estimated_savings or 0),
            realized_savings_monthly=float(getattr(cluster, 'realized_savings_monthly', 0) or 0),
            node_count=cluster.node_count or 0,
            spot_count=cluster.spot_count or 0,
            on_demand_node_count=cluster.on_demand_node_count or 0,
            agent_installed=cluster.agent_installed,
            is_agentless=cluster.is_agentless,
            potential_savings_monthly=float(cluster.potential_savings_monthly or 0),
            inventory_summary=cluster.inventory_summary or {},
            rightsizing_enabled=cluster.rightsizing_enabled or False,
            managed_node_group_deleted=cluster.managed_node_group_deleted or False,
        )

    def get_cluster_nodes(self, cluster_id: str, user_id: str) -> dict:
        """
        Get nodes/instances for a cluster
        """
        cluster = self._get_cluster_with_access(cluster_id, user_id)

        # Build set of replacement spot instance IDs with active optimization
        # so we can hide them from the fleet view until optimization completes.
        from backend.models.rebalancing_action import RebalancingAction as _RA_FV
        _active_replacements = set()
        _active_ras = self.db.query(_RA_FV).filter(
            _RA_FV.cluster_id == cluster_id,
            _RA_FV.status.in_(['in_progress', 'waiting_agent']),
        ).all()
        for _ra in _active_ras:
            _ra_meta = _ra.action_metadata or {}
            _repl_id = _ra_meta.get('replacement_spot_instance_id')
            if _repl_id:
                _active_replacements.add(_repl_id)

        # Query ONLY active instances — terminated records must never appear in node lists.
        # Exclude ghost placeholder instances (instance_id not like 'i-%' or 'ip-%').
        instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state.in_(['running', 'pending']),
            Instance.instance_id.like('i-%') | Instance.instance_id.like('ip-%'),
        ).all()

        nodes = []
        for inst in instances:
            # Hide replacement spot nodes whose optimization is still in progress
            if inst.instance_id in _active_replacements:
                continue
            nodes.append({
                "id": inst.id,
                "type": inst.instance_type,
                "lifecycle": inst.lifecycle.value if hasattr(inst.lifecycle, 'value') else str(inst.lifecycle),
                "cpu_util": inst.cpu_util or 0,
                "memory_util": inst.memory_util or 0,
                "az": inst.az,
                "state": inst.state if hasattr(inst, 'state') else "running"
            })

        return {"nodes": nodes, "total": len(nodes)}

    def get_cluster_utilization(self, cluster_id: str, user_id: str) -> dict:
        """
        Get cluster utilization metrics

        Returns:
            dict with CPU %, Memory %, Pod count, Node count, and average usage
        """
        from backend.models.pod_metric import PodMetric
        from sqlalchemy import func

        cluster = self._get_cluster_with_access(cluster_id, user_id)

        # Get node count from instances table
        node_count = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state.in_(['running', 'pending'])
        ).count()

        # Get latest pod metrics for this cluster (last 5 minutes)
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)

        # Get unique pod count
        pod_count = self.db.query(func.count(func.distinct(PodMetric.pod_name))).filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp >= five_minutes_ago
        ).scalar() or 0

        # Calculate average utilization from pod metrics
        pod_stats = self.db.query(
            func.avg(PodMetric.cpu_utilization_pct).label('avg_cpu'),
            func.avg(PodMetric.memory_utilization_pct).label('avg_mem'),
            func.sum(PodMetric.cpu_usage_millicores).label('total_cpu_millicores'),
            func.sum(PodMetric.memory_usage_bytes).label('total_mem_bytes'),
            func.sum(PodMetric.cpu_request_millicores).label('total_cpu_request'),
            func.sum(PodMetric.memory_request_bytes).label('total_mem_request')
        ).filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp >= five_minutes_ago
        ).first()

        # Calculate cluster-level utilization percentage
        cpu_utilization_pct = 0.0
        memory_utilization_pct = 0.0

        if pod_stats:
            # If we have request data, calculate utilization as usage/request
            if pod_stats.total_cpu_request and pod_stats.total_cpu_request > 0:
                cpu_utilization_pct = (pod_stats.total_cpu_millicores / pod_stats.total_cpu_request) * 100
            elif pod_stats.avg_cpu:
                cpu_utilization_pct = pod_stats.avg_cpu

            if pod_stats.total_mem_request and pod_stats.total_mem_request > 0:
                memory_utilization_pct = (pod_stats.total_mem_bytes / pod_stats.total_mem_request) * 100
            elif pod_stats.avg_mem:
                memory_utilization_pct = pod_stats.avg_mem

        # Fallback to cluster table values if no recent pod metrics
        if cpu_utilization_pct == 0.0 and cluster.cpu_usage_pct:
            cpu_utilization_pct = float(cluster.cpu_usage_pct)
        if memory_utilization_pct == 0.0 and cluster.mem_usage_pct:
            memory_utilization_pct = float(cluster.mem_usage_pct)

        # Calculate average resource usage (cores and GB)
        avg_cpu_cores = (pod_stats.total_cpu_millicores / 1000.0 / pod_count) if pod_count > 0 and pod_stats.total_cpu_millicores else 0
        avg_memory_gb = (pod_stats.total_mem_bytes / (1024**3) / pod_count) if pod_count > 0 and pod_stats.total_mem_bytes else 0

        return {
            "cpu_utilization_pct": round(cpu_utilization_pct, 2),
            "memory_utilization_pct": round(memory_utilization_pct, 2),
            "pod_count": pod_count,
            "node_count": node_count,
            "avg_cpu_cores": round(avg_cpu_cores, 3),
            "avg_memory_gb": round(avg_memory_gb, 3),
            "total_cpu_millicores": pod_stats.total_cpu_millicores if pod_stats else 0,
            "total_memory_bytes": pod_stats.total_mem_bytes if pod_stats else 0
        }

    def get_cluster_workload_type(self, cluster_id: str, user_id: str) -> dict:
        """
        Detect cluster workload type based on PVC usage

        Detection logic:
        - Checks pod_metrics for pods with PVCs (via pod_metadata)
        - STATELESS: No PVCs found
        - STATEFUL: One or more pods have PVCs
        - MIXED: Some pods with PVCs, some without
        - UNKNOWN: Unable to determine (no pod data)

        Returns:
            dict with workload_type, pvc_count, total_pod_count, and details
        """
        from backend.models.pod_metric import PodMetric
        from sqlalchemy import func
        import os
        import redis as redis_lib
        import json

        cluster = self._get_cluster_with_access(cluster_id, user_id)

        # Check Redis cache first (10-minute TTL from workload_inspector)
        try:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            r = redis_lib.from_url(redis_url)

            # Check for cached workload classification
            workload_cache_key = f"spot:workload_type:{cluster_id}"
            cached_type = r.get(workload_cache_key)
            if cached_type:
                cached_type = cached_type.decode('utf-8') if isinstance(cached_type, bytes) else cached_type
                logger.info(f"Using cached workload type for cluster {cluster_id}: {cached_type}")
                return {
                    "workload_type": cached_type,
                    "cached": True,
                    "description": self._get_workload_description(cached_type)
                }
        except Exception as e:
            logger.debug(f"Redis cache check failed: {e}")

        # Fallback: Analyze pod metrics for PVC detection
        # Get recent pod metrics (last 10 minutes)
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)

        # Get unique pods with their metadata
        recent_pods = self.db.query(
            PodMetric.pod_name,
            PodMetric.namespace,
            PodMetric.pod_metadata,
            PodMetric.controller_kind
        ).filter(
            PodMetric.cluster_id == cluster_id,
            PodMetric.timestamp >= ten_minutes_ago
        ).distinct(PodMetric.pod_name, PodMetric.namespace).all()

        total_pod_count = len(recent_pods)
        pvc_pod_count = 0
        statefulset_pod_count = 0

        # Analyze each pod's metadata for PVCs
        for pod in recent_pods:
            pod_metadata = pod.pod_metadata or {}

            # Check for PVC volumes in metadata.
            # agent v1.1.7+ sets 'has_pvc' directly; older agents/fallback: volumes list.
            has_pvc = pod_metadata.get('has_pvc', False)
            if not has_pvc:
                volumes = pod_metadata.get('volumes', [])
                has_pvc = any('persistentVolumeClaim' in vol for vol in volumes) if isinstance(volumes, list) else False

            if has_pvc:
                pvc_pod_count += 1

            # Use the dedicated controller_kind DB column (populated by agent directly).
            # pod_metadata['owner_kind'] was never set by the agent — always fell back to ''.
            owner_kind = pod.controller_kind or pod_metadata.get('owner_kind', '')
            if owner_kind == 'StatefulSet':
                statefulset_pod_count += 1

        # Determine workload type
        if total_pod_count == 0:
            workload_type = "UNKNOWN"
        elif pvc_pod_count == 0 and statefulset_pod_count == 0:
            workload_type = "STATELESS"
        elif pvc_pod_count == total_pod_count or statefulset_pod_count == total_pod_count:
            workload_type = "STATEFUL"
        else:
            workload_type = "MIXED"

        logger.info(
            f"Workload detection for cluster {cluster_id}: {workload_type} "
            f"(PVCs: {pvc_pod_count}/{total_pod_count}, StatefulSets: {statefulset_pod_count}/{total_pod_count})"
        )

        return {
            "workload_type": workload_type,
            "total_pod_count": total_pod_count,
            "pvc_pod_count": pvc_pod_count,
            "statefulset_pod_count": statefulset_pod_count,
            "cached": False,
            "description": self._get_workload_description(workload_type),
            "can_optimize_spot": workload_type in ["STATELESS", "MIXED"]
        }

    def get_cluster_nodes_detailed(self, cluster_id: str, user_id: str) -> dict:
        """
        Get detailed node information with pod-level details and PVC detection.
        Returns node-by-node breakdown with pods, utilization, and classification.

        Prioritizes the `instances` table to guarantee we return all nodes even if they
        don't have user workloads/pods running on them. Pod metrics are attached to matching nodes.
        """
        from backend.models.instance import Instance
        from backend.models.pod_metric import PodMetric
        from sqlalchemy import func
        from datetime import datetime, timedelta

        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        # If the EKS cluster was deleted, return empty immediately — no ghost nodes in the UI.
        _dead_statuses = {'DEGRADED', 'DISCONNECTED'}
        _cluster_status = cluster.status.value if hasattr(cluster.status, 'value') else str(cluster.status)
        if _cluster_status in _dead_statuses:
            # Also clear any leftover instances so future calls are fast
            from backend.models.instance import Instance as _Inst_dd
            _leftover = self.db.query(_Inst_dd).filter(_Inst_dd.cluster_id == cluster_id).count()
            if _leftover > 0:
                self.db.query(_Inst_dd).filter(_Inst_dd.cluster_id == cluster_id).delete(synchronize_session=False)
                self.db.commit()
            return {
                "cluster_id": cluster_id,
                "cluster_name": cluster.name,
                "total_nodes": 0,
                "total_pods": 0,
                "spot_friendly_pods": 0,
                "non_spot_friendly_pods": 0,
                "stable_node": None,
                "nodes": [],
                "timestamp": datetime.utcnow().isoformat(),
                "warning": f"Cluster is {_cluster_status}. No live node data available."
            }

        # Only show RUNNING instances — terminated/shutting-down nodes must not appear in the UI
        _all_instances = self.db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state == 'running',
        ).all()

        # Build set of replacement spot instance IDs with active optimization
        # so we can hide them from the fleet view until optimization completes.
        from backend.models.rebalancing_action import RebalancingAction as _RA_FVD
        _active_replacements_d = set()
        _active_ras_d = self.db.query(_RA_FVD).filter(
            _RA_FVD.cluster_id == cluster_id,
            _RA_FVD.status.in_(['in_progress', 'waiting_agent']),
        ).all()
        for _ra_d in _active_ras_d:
            _ra_d_meta = _ra_d.action_metadata or {}
            _repl_id_d = _ra_d_meta.get('replacement_spot_instance_id')
            if _repl_id_d:
                _active_replacements_d.add(_repl_id_d)

        # Filter out replacement spot instances with active optimization
        _all_instances = [
            i for i in _all_instances
            if i.instance_id not in _active_replacements_d
        ]

        # Deduplicate: prefer real EC2 instances (instance_id starts with 'i-') over
        # daemon-set placeholder records (instance_id starts with 'ip-').
        # Key by the short hostname prefix so ip-x-y-z-w maps to the same slot as
        # the real instance whose node_name = ip-x-y-z-w.region.internal.
        _seen: dict = {}
        for _inst in _all_instances:
            _key = (_inst.node_name or '').split('.')[0] or _inst.instance_id
            _existing = _seen.get(_key)
            if _existing is None:
                _seen[_key] = _inst
            else:
                _is_real = _inst.instance_id and _inst.instance_id.startswith('i-')
                _ex_real = _existing.instance_id and _existing.instance_id.startswith('i-')
                if _is_real and not _ex_real:
                    # Transfer utilisation from placeholder before discarding it
                    if _existing.cpu_util is not None and _inst.cpu_util is None:
                        _inst.cpu_util = _existing.cpu_util
                        _inst.memory_util = _existing.memory_util
                    # RC6 fix: also transfer lifecycle when real instance has no lifecycle set
                    # (agent-registered placeholder may have lifecycle from heartbeat data)
                    if _existing.lifecycle is not None and _inst.lifecycle is None:
                        _inst.lifecycle = _existing.lifecycle
                    _seen[_key] = _inst
        instances = list(_seen.values())

        # Strip ghost placeholder instances (instance_id not matching a real EC2 ID
        # and not an ip-hostname placeholder). These show as "unknown" rows in the UI.
        instances = [
            i for i in instances
            if (i.instance_id or '').startswith('i-')
            or (i.instance_id or '').startswith('ip-')
        ]

        # Agent reports pod metrics every ~1 minute. Use a 5-minute window:
        # fresh enough to exclude stale pods from terminated/replaced nodes,
        # while tolerating brief agent restarts or tunnel hiccups.
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)

        # Use PostgreSQL DISTINCT ON (pod_name) to get exactly one row per pod —
        # the most recent report. This is immune to timestamp ties (multiple agents
        # on different nodes can insert the same pod at the same second) and to
        # cancelled/rescheduled pods that left stale rows in the window.
        from sqlalchemy import text as _sa_text
        _raw_pods = self.db.execute(
            _sa_text("""
                SELECT DISTINCT ON (pod_name)
                    id, cluster_id, pod_name, node_name, namespace,
                    cpu_usage_millicores, cpu_request_millicores,
                    memory_usage_bytes, memory_request_bytes,
                    controller_kind, pod_metadata, timestamp
                FROM pod_metrics
                WHERE cluster_id = :cluster_id
                  AND timestamp >= :cutoff
                ORDER BY pod_name, timestamp DESC
            """),
            {"cluster_id": cluster_id, "cutoff": cutoff_time}
        ).fetchall()

        # Re-query full ORM objects for the deduplicated set so downstream code
        # can use ORM attributes (pod.pod_metadata, pod.controller_kind, etc.)
        _dedup_ids = [r[0] for r in _raw_pods]
        recent_pods = (
            self.db.query(PodMetric).filter(PodMetric.id.in_(_dedup_ids)).all()
            if _dedup_ids else []
        )


        # Load node-level classification from Redis (WorkloadInspector scan, 9-min TTL).
        # Keys: node_name → "STATELESS_ELIGIBLE" | "STATEFUL_PROTECTED" | "DRAIN_UNSAFE" | "SYSTEM_PROTECTED"
        _node_classification: dict = {}
        _workload_tier_cache: dict = {}
        try:
            from backend.core.redis_client import get_redis_client as _grc_pod
            import json as _json_pod
            _redis_pod = _grc_pod()
            _raw_nc = _redis_pod.get(f"spot:node_classification:{cluster_id}")
            if _raw_nc:
                _node_classification = _json_pod.loads(_raw_nc)
        except Exception:
            pass  # best-effort; falls back to simple checks below

        # System namespaces whose pods are never spot-migratable
        _SYSTEM_NS = frozenset({
            "kube-system", "kube-public", "kube-node-lease",
            "karpenter", "spot-optimizer", "cert-manager", "monitoring",
            "istio-system", "linkerd",
        })

        # Pod-name patterns for known stateful workloads (fallback when agent
        # doesn't report PVC metadata or workload tier isn't cached in Redis).
        # Matches: postgres-0, redis-master-xyz, my-mongodb-5f8b, etc.
        import re as _re_cls
        _STATEFUL_POD_NAME_RE = _re_cls.compile(
            r"(?:postgres|postgresql|pgbouncer|patroni|spilo|"
            r"redis|keydb|dragonfly|"
            r"mongo|mysql|mariadb|percona|"
            r"elasticsearch|opensearch|"
            r"cassandra|scylladb|"
            r"kafka|zookeeper|"
            r"rabbitmq|nats|activemq|"
            r"etcd|consul|memcached|"
            r"minio|cockroachdb|clickhouse|influxdb|neo4j|couchdb)",
            _re_cls.IGNORECASE,
        )

        # Control-plane pod names that must be SPREAD, not packed onto one node.
        # These are Deployments in kube-system / argocd / karpenter that provide
        # cluster services. They should land on OD but be distributed.
        _CONTROL_PLANE_POD_RE = _re_cls.compile(
            r"^(?:coredns|karpenter|metrics-server|"
            r"argocd-(?:server|controller|repo|application|redis|dex|notifications)|"
            r"cluster-autoscaler|aws-load-balancer-controller|"
            r"ebs-csi-controller|efs-csi-controller|"
            r"cert-manager|external-dns|ingress-nginx-controller)",
            _re_cls.IGNORECASE,
        )

        pods_by_node: dict = {}
        for pod in recent_pods:
            node_name = pod.node_name
            if node_name not in pods_by_node:
                pods_by_node[node_name] = []

            pod_metadata = pod.pod_metadata or {}
            # agent v1.1.7+ sets 'has_pvc' directly; older agents/fallback: volumes list.
            has_pvc = pod_metadata.get('has_pvc', False)
            if not has_pvc:
                volumes = pod_metadata.get('volumes', [])
                has_pvc = any('persistentVolumeClaim' in vol for vol in volumes) if isinstance(volumes, list) else False
            # Use the dedicated controller_kind DB column; pod_metadata['owner_kind'] was never set by the agent.
            owner_kind = pod.controller_kind or pod_metadata.get('owner_kind', 'Pod')
            namespace = pod.namespace or ''

            # ── Determine is_stateful using all classification signals ──────
            # Factor 1: PVC or StatefulSet (always stateful by nature)
            _stateful_by_nature = has_pvc or owner_kind == 'StatefulSet'

            # Factor 3: System namespace pods are never spot-migratable (by nature)
            if not _stateful_by_nature and namespace in _SYSTEM_NS:
                _stateful_by_nature = True

            # Factor 4: DaemonSet — runs on every node (by nature, not migratable)
            _is_daemonset = owner_kind == 'DaemonSet'
            if not _stateful_by_nature and _is_daemonset:
                _stateful_by_nature = True

            # Factor 5: Smart classifier tier from Redis (TIER_0 / TIER_1 = not spot-friendly)
            if not _stateful_by_nature and owner_kind not in ('', 'Pod'):
                _tier_key = f"spot:workload_tier:{cluster_id}:{namespace}/{owner_kind}"
                if _tier_key not in _workload_tier_cache:
                    try:
                        _raw_tier = _redis_pod.get(_tier_key)
                        _workload_tier_cache[_tier_key] = _json_pod.loads(_raw_tier) if _raw_tier else None
                    except Exception:
                        _workload_tier_cache[_tier_key] = None
                _tier_data = _workload_tier_cache.get(_tier_key)
                if _tier_data and _tier_data.get('tier', 4) <= 1:
                    _stateful_by_nature = True

            # Factor 6: Pod name matches known stateful image patterns (fallback
            # for when agent doesn't send PVC metadata or tier isn't cached yet)
            if not _stateful_by_nature:
                _pod_nm = pod.pod_name or ''
                if _STATEFUL_POD_NAME_RE.search(_pod_nm):
                    _stateful_by_nature = True

            # ── Determine control-plane vs DaemonSet sub-type ────────────────
            # DaemonSets: scheduled on every node automatically, skip in placement
            # Control-plane: must SPREAD across nodes (not pack into one)
            _is_control_plane = False
            _pod_nm_cp = pod.pod_name or ''
            if namespace in _SYSTEM_NS and not _is_daemonset:
                if _CONTROL_PLANE_POD_RE.search(_pod_nm_cp):
                    _is_control_plane = True

            # Factor 2: Node-level WorkloadInspector result (STATEFUL_PROTECTED/DRAIN_UNSAFE)
            # A spot-friendly pod found on a stateful-classified node = misplaced
            _stateful_by_placement = False
            if not _stateful_by_nature:
                _nstatus = _node_classification.get(node_name, '')
                if _nstatus in ('STATEFUL_PROTECTED', 'DRAIN_UNSAFE'):
                    _stateful_by_placement = True

            _stateful = _stateful_by_nature or _stateful_by_placement
            _stateful_reason = (
                "by_nature" if _stateful_by_nature
                else ("by_placement" if _stateful_by_placement else None)
            )

            pods_by_node[node_name].append({
                "pod_name": pod.pod_name,
                "namespace": namespace,
                "cpu_usage_millicores": pod.cpu_usage_millicores,
                "cpu_request_millicores": pod.cpu_request_millicores,
                "memory_usage_bytes": pod.memory_usage_bytes,
                "memory_request_bytes": pod.memory_request_bytes,
                "memory_usage_mb": round(
                    pod.memory_usage_bytes / (1024 * 1024), 2
                ) if pod.memory_usage_bytes else 0,
                "memory_request_mb": round(
                    pod.memory_request_bytes / (1024 * 1024), 2
                ) if pod.memory_request_bytes else 0,
                "has_pvc": has_pvc,
                "controller_type": owner_kind,
                "is_stateful": _stateful,
                "stateful_reason": _stateful_reason,
                "is_daemonset": _is_daemonset,
                "is_control_plane": _is_control_plane,
                "status": pod_metadata.get('status', 'Unknown'),
                # v4.3 WIE enrichment — additive, does NOT change is_stateful logic
                # Defaults to None when engine hasn't run yet for this workload (backward compatible)
                **_get_wie_enrichment(_redis_pod, _json_pod, cluster_id, namespace, owner_kind),
            })

        # Drop pods from dead/replaced nodes — only keep pods whose node_name
        # matches a currently-running instance. This prevents stale pod_metrics
        # rows (within the 5-min window) from terminated nodes inflating counts.
        _live_node_names = {i.node_name for i in instances if i.node_name}
        pods_by_node = {
            node: pods
            for node, pods in pods_by_node.items()
            if node in _live_node_names
        }

        _VCPU_MAP = {
            "t3.nano": 2, "t3.micro": 2, "t3.small": 2, "t3.medium": 2, "t3.large": 2, "t3.xlarge": 4, "t3.2xlarge": 8,
            "t3a.nano": 2, "t3a.micro": 2, "t3a.small": 2, "t3a.medium": 2, "t3a.large": 2, "t3a.xlarge": 4, "t3a.2xlarge": 8,
            "m5.large": 2, "m5.xlarge": 4, "m5.2xlarge": 8, "m5.4xlarge": 16, "m5.8xlarge": 32, "m5.12xlarge": 48, "m5.16xlarge": 64, "m5.24xlarge": 96,
            "m6i.large": 2, "m6i.xlarge": 4, "m6i.2xlarge": 8, "m6i.4xlarge": 16, "m6i.8xlarge": 32, "m6i.12xlarge": 48, "m6i.16xlarge": 64, "m6i.24xlarge": 96,
            "c5.large": 2, "c5.xlarge": 4, "c5.2xlarge": 8, "c5.4xlarge": 16, "c5.9xlarge": 36, "c5.12xlarge": 48, "c5.18xlarge": 72, "c5.24xlarge": 96,
            "c6i.large": 2, "c6i.xlarge": 4, "c6i.2xlarge": 8, "c6i.4xlarge": 16, "c6i.8xlarge": 32, "c6i.12xlarge": 48, "c6i.16xlarge": 64, "c6i.24xlarge": 96,
            "r5.large": 2, "r5.xlarge": 4, "r5.2xlarge": 8, "r5.4xlarge": 16, "r5.8xlarge": 32, "r5.12xlarge": 48, "r5.16xlarge": 64, "r5.24xlarge": 96,
            "r6i.large": 2, "r6i.xlarge": 4, "r6i.2xlarge": 8, "r6i.4xlarge": 16,
        }
        _MEM_MAP = {
            "t3.nano": 0.5, "t3.micro": 1, "t3.small": 2, "t3.medium": 4, "t3.large": 8, "t3.xlarge": 16, "t3.2xlarge": 32,
            "t3a.nano": 0.5, "t3a.micro": 1, "t3a.small": 2, "t3a.medium": 4, "t3a.large": 8, "t3a.xlarge": 16, "t3a.2xlarge": 32,
            "m5.large": 8, "m5.xlarge": 16, "m5.2xlarge": 32, "m5.4xlarge": 64, "m5.8xlarge": 128, "m5.12xlarge": 192, "m5.16xlarge": 256, "m5.24xlarge": 384,
            "m6i.large": 8, "m6i.xlarge": 16, "m6i.2xlarge": 32, "m6i.4xlarge": 64,
            "c5.large": 4, "c5.xlarge": 8, "c5.2xlarge": 16, "c5.4xlarge": 32,
            "c6i.large": 4, "c6i.xlarge": 8, "c6i.2xlarge": 16, "c6i.4xlarge": 32,
            "r5.large": 16, "r5.xlarge": 32, "r5.2xlarge": 64, "r5.4xlarge": 128,
            "r6i.large": 16, "r6i.xlarge": 32, "r6i.2xlarge": 64, "r6i.4xlarge": 128,
        }

        nodes_detailed = []
        pod_nodes_items = list(pods_by_node.items())

        # Pre-fetch latest NodeMetric per instance/node to avoid N+1 queries.
        # Two lookups: by instance_id (preferred) and by node_name (fallback).
        if instances:
            from backend.models.node_metrics import NodeMetric as _NM_pre
            from sqlalchemy import func as _func_pre
            _nm_cutoff_pre = datetime.utcnow() - timedelta(minutes=5)
            _all_inst_ids = [i.instance_id for i in instances if i.instance_id]
            _all_node_names_pre = [i.node_name for i in instances if i.node_name]

            _nm_by_inst_id: dict = {}
            if _all_inst_ids:
                _nm_id_subq = self.db.query(
                    _NM_pre.instance_id,
                    _func_pre.max(_NM_pre.timestamp).label('max_ts')
                ).filter(
                    _NM_pre.cluster_id == cluster_id,
                    _NM_pre.timestamp >= _nm_cutoff_pre,
                    _NM_pre.instance_id.in_(_all_inst_ids),
                ).group_by(_NM_pre.instance_id).subquery()
                for _nm_row in self.db.query(_NM_pre).join(
                    _nm_id_subq,
                    (_NM_pre.instance_id == _nm_id_subq.c.instance_id) &
                    (_NM_pre.timestamp == _nm_id_subq.c.max_ts)
                ).all():
                    _nm_by_inst_id[_nm_row.instance_id] = _nm_row

            _nm_by_node_name: dict = {}
            if _all_node_names_pre:
                _nm_name_subq = self.db.query(
                    _NM_pre.node_name,
                    _func_pre.max(_NM_pre.timestamp).label('max_ts')
                ).filter(
                    _NM_pre.cluster_id == cluster_id,
                    _NM_pre.timestamp >= _nm_cutoff_pre,
                    _NM_pre.node_name.in_(_all_node_names_pre),
                ).group_by(_NM_pre.node_name).subquery()
                for _nm_row in self.db.query(_NM_pre).join(
                    _nm_name_subq,
                    (_NM_pre.node_name == _nm_name_subq.c.node_name) &
                    (_NM_pre.timestamp == _nm_name_subq.c.max_ts)
                ).all():
                    _nm_by_node_name[_nm_row.node_name] = _nm_row

            # Pre-fetch OptimizationStrategy once (it's the same per cluster, not per node).
            from backend.models.cluster import OptimizationStrategy as _OS_nd
            _strat_nd_prefetched = self.db.query(_OS_nd).filter_by(cluster_id=cluster_id).first()

        if instances:
            for idx, inst in enumerate(instances):
                instance_type = inst.instance_type or "Unknown"
                lc_raw = inst.lifecycle
                if lc_raw is None:
                    lifecycle = "on-demand"
                elif hasattr(lc_raw, 'value'):
                    lifecycle = lc_raw.value.lower()
                else:
                    lc_str = str(lc_raw).lower()
                    lifecycle = "on-demand" if lc_str in ('none', 'null', '') else lc_str
                availability_zone = inst.az or "unknown"
                node_cpu_capacity_cores = _VCPU_MAP.get(instance_type, 4)
                node_memory_capacity_gb = _MEM_MAP.get(instance_type, 16)

                node_cpu_util_pct = float(inst.cpu_util) if inst.cpu_util is not None and inst.cpu_util > 0 else 0
                node_mem_util_pct = float(inst.memory_util) if inst.memory_util is not None and inst.memory_util > 0 else 0

                # Override with fresher data from pre-fetched node_metrics dict (no N+1).
                try:
                    _nm = (
                        _nm_by_inst_id.get(inst.instance_id) if inst.instance_id
                        else _nm_by_node_name.get(inst.node_name) if inst.node_name
                        else None
                    )
                    if _nm:
                        if _nm.cpu_usage_millicores and _nm.cpu_capacity_millicores and _nm.cpu_capacity_millicores > 0:
                            node_cpu_util_pct = round((_nm.cpu_usage_millicores / _nm.cpu_capacity_millicores) * 100, 2)
                        if _nm.memory_usage_bytes and _nm.memory_capacity_bytes and _nm.memory_capacity_bytes > 0:
                            node_mem_util_pct = round((_nm.memory_usage_bytes / _nm.memory_capacity_bytes) * 100, 2)
                except Exception:
                    pass

                # Match pods by actual node_name, not by position index
                node_name = inst.node_name or f"node-{idx}"
                node_pods = pods_by_node.get(node_name, [])

                if node_cpu_util_pct == 0 and node_pods:
                    total_cpu_millicores = sum(p['cpu_usage_millicores'] for p in node_pods if p['cpu_usage_millicores'])
                    node_cpu_util_pct = ((total_cpu_millicores / (node_cpu_capacity_cores * 1000)) * 100) if total_cpu_millicores else 0
                
                if node_mem_util_pct == 0 and node_pods:
                    total_memory_mb = sum(p['memory_usage_mb'] for p in node_pods)
                    node_mem_util_pct = ((total_memory_mb / (node_memory_capacity_gb * 1024)) * 100) if total_memory_mb else 0

                stateful_pods = [p for p in node_pods if p['is_stateful']]
                if not node_pods:
                    node_classification = "EMPTY"
                elif not stateful_pods:
                    node_classification = "STATELESS"
                elif len(stateful_pods) == len(node_pods):
                    node_classification = "STATEFUL"
                else:
                    node_classification = "MIXED"

                # ── Node condition: risk score + rebalance trigger ───────────
                _node_risk_score = None
                _node_best_pool = None
                _node_condition = "STABLE"
                try:
                    from backend.core.redis_client import get_redis_client as _grc_nd
                    import json as _jnd
                    _r_nd = _grc_nd()
                    _raw_nd = _r_nd.get(f"global_pool_rankings:{cluster.region or 'ap-south-1'}")
                    if _raw_nd:
                        _rankings_nd = _jnd.loads(_raw_nd).get("data", [])
                        _this_pool_key = f"{instance_type}:{availability_zone}"
                        _cur_nd = next(
                            (p for p in _rankings_nd
                             if f"{p['instance_type']}:{p['az']}" == _this_pool_key), None
                        )
                        if _cur_nd:
                            _node_risk_score = round(_cur_nd.get('risk_probability', 0), 3)
                            _cur_sav_nd = _cur_nd.get('predicted_savings', 0)
                            _better_nd = [
                                p for p in _rankings_nd
                                if (p.get('risk_probability', 1) < _node_risk_score and
                                    p.get('predicted_savings', 0) >= _cur_sav_nd and
                                    f"{p['instance_type']}:{p['az']}" != _this_pool_key)
                            ]
                            if _better_nd:
                                _node_best_pool = f"{_better_nd[0]['instance_type']}:{_better_nd[0]['az']}"
                        # Determine condition using cluster's risk ceiling (pre-fetched before loop)
                        _ceil_nd = (getattr(_strat_nd_prefetched, 'risk_ceiling_percent', 25) or 25) / 100.0
                        if lifecycle == "on-demand":
                            _node_condition = "AWAITING_SPOT"
                        elif _node_risk_score is not None and _node_risk_score > _ceil_nd:
                            _node_condition = "REBALANCE:RISK_HIGH"
                        elif _node_best_pool:
                            _node_condition = "REBALANCE:BETTER_POOL"
                        else:
                            _node_condition = "STABLE"
                except Exception:
                    pass  # condition enrichment is best-effort; never blocks node display

                # Compute request-based allocation % (CPU/MEM reserved by pod requests vs capacity)
                # This matches what AWS EKS console shows and is useful for over-provisioning analysis
                _total_cpu_req_m = sum(p.get('cpu_request_millicores') or 0 for p in node_pods) if node_pods else 0
                _total_mem_req_mb = sum(p.get('memory_request_mb') or 0 for p in node_pods) if node_pods else 0
                _cpu_alloc_pct = round((_total_cpu_req_m / (node_cpu_capacity_cores * 1000)) * 100, 2) if node_cpu_capacity_cores > 0 else 0
                _mem_alloc_pct = round((_total_mem_req_mb / (node_memory_capacity_gb * 1024)) * 100, 2) if node_memory_capacity_gb > 0 else 0

                nodes_detailed.append({
                    "instance_id": inst.instance_id,
                    "node_name": node_name,
                    "instance_type": instance_type,
                    "lifecycle": lifecycle,
                    "availability_zone": availability_zone,
                    "status": "running",
                    "classification": node_classification,
                    "cpu_utilization_pct": round(node_cpu_util_pct, 2),
                    "memory_utilization_pct": round(node_mem_util_pct, 2),
                    "cpu_request_pct": _cpu_alloc_pct,
                    "memory_request_pct": _mem_alloc_pct,
                    "cpu_capacity_cores": node_cpu_capacity_cores,
                    "memory_capacity_gb": node_memory_capacity_gb,
                    "total_cpu_usage_millicores": sum(p['cpu_usage_millicores'] for p in node_pods if p['cpu_usage_millicores']) if node_pods else 0,
                    "total_cpu_request_millicores": _total_cpu_req_m,
                    "total_memory_usage_mb": round(sum(p['memory_usage_mb'] for p in node_pods), 2) if node_pods else 0,
                    "total_memory_request_mb": round(_total_mem_req_mb, 2),
                    "pod_count": len(node_pods),
                    "stateful_pod_count": len(stateful_pods),
                    "pods": node_pods,
                    "current_risk_score": _node_risk_score,
                    "best_available_pool": _node_best_pool,
                    "rebalance_condition": _node_condition,
                })
        # No else branch — if no running instances are in the DB we return an empty list.
        # Fake "Unknown" nodes must not appear; only daemon-set-reported data is shown.

        if not nodes_detailed:
            return {
                "cluster_id": cluster_id,
                "cluster_name": cluster.name,
                "total_nodes": 0,
                "nodes": [],
                "timestamp": datetime.utcnow().isoformat(),
                "warning": "No node data available. Please ensure the agent is installed and running on your cluster."
            }

        logger.info(
            f"Nodes detailed for cluster {cluster_id}: {len(nodes_detailed)} nodes "
            f"from pod_metrics ({'enriched with instances' if instances else 'pod_metrics_only'})"
        )

        _total_pods = sum(n["pod_count"] for n in nodes_detailed)

        # ── STABLE / ANCHOR NODE DETECTION ─────────────────────────────────
        # The auto-rebalancer designates one OD node as "stable" (hosts Karpenter
        # system pods). Its pods must NOT count as spot-friendly in the UI card.
        # Strategy:
        #   1. Try Redis cache first (set by the rebalancer, 10 min TTL).
        #   2. If Redis miss, detect anchor from node data (node with karpenter-
        #      namespace pods that is lifecycle=on-demand).
        _stable_node_info = None
        _stable_node_name = None
        try:
            import os as _os_sn
            import redis as _redis_sn
            import json as _json_sn
            _r_sn = _redis_sn.from_url(_os_sn.getenv("REDIS_URL", "redis://redis:6379/0"))
            _sn_raw = _r_sn.get(f"spot:stable_node:{cluster_id}")
            if _sn_raw:
                _stable_node_info = _json_sn.loads(_sn_raw)
                _stable_node_name = _stable_node_info.get('node_name')
        except Exception:
            pass

        # Fallback: detect from pod data — find an OD node hosting karpenter pods
        if not _stable_node_name:
            for n in nodes_detailed:
                if n.get("lifecycle") == "on-demand":
                    karp_pods = [p for p in n.get("pods", []) if p.get("namespace") == "karpenter"]
                    if karp_pods:
                        _stable_node_name = n.get("node_name")
                        _stable_node_info = {
                            "node_name": _stable_node_name,
                            "instance_type": n.get("instance_type"),
                            "detected_via": "pod_data_fallback",
                        }
                        break

        # Tag nodes and compute spot-friendly pods.
        # Karpenter pods (namespace=karpenter) are non-spot-friendly on ANY node
        # because Karpenter must run on OD nodes and can never be migrated to spot.
        # DaemonSet pods (aws-node, kube-proxy, spot-agent) run on ALL nodes
        # including spot, so they remain spot-friendly.
        _non_spot_friendly_count = 0
        _NON_SPOT_NAMESPACES = {"karpenter"}
        for n in nodes_detailed:
            if _stable_node_name and n.get("node_name") == _stable_node_name:
                n["is_stable_node"] = True
                n["classification"] = "ANCHOR"
            else:
                n["is_stable_node"] = False

            # Count karpenter-namespace pods as non-spot-friendly on every node
            for p in n["pods"]:
                if p.get("namespace") in _NON_SPOT_NAMESPACES:
                    _non_spot_friendly_count += 1

        _spot_friendly_pods = sum(
            len([p for p in n["pods"] if not p.get("is_stateful", False)])
            for n in nodes_detailed
        ) - _non_spot_friendly_count

        # Count misplaced pods: spot-friendly pods currently on stateful-classified nodes
        _misplaced_pods = sum(
            len([p for p in n["pods"] if p.get("stateful_reason") == "by_placement"])
            for n in nodes_detailed
        )

        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster.name,
            "total_nodes": len(nodes_detailed),
            "total_pods": _total_pods,
            "spot_friendly_pods": _spot_friendly_pods,
            "non_spot_friendly_pods": _total_pods - _spot_friendly_pods,
            "misplaced_pods": _misplaced_pods,
            "stable_node": _stable_node_info,
            "nodes": nodes_detailed,
            "timestamp": datetime.utcnow().isoformat(),
            "data_source": "instances_primary" if instances else "pod_metrics_only"
        }

    def _get_workload_description(self, workload_type: str) -> str:
        """Get human-readable description for workload type"""
        descriptions = {
            "STATELESS": "All workloads are stateless - safe for aggressive spot optimization",
            "STATEFUL": "Cluster has stateful workloads (PVCs/StatefulSets) - use caution with spot instances",
            "MIXED": "Cluster has both stateful and stateless workloads - selective optimization recommended",
            "UNKNOWN": "Unable to determine workload type - no pod data available",
            "SYSTEM_PROTECTED": "System/control plane nodes - protected from optimization"
        }
        return descriptions.get(workload_type, "Unknown workload type")


def get_cluster_service(db: Session) -> ClusterService:
    """Get cluster service instance"""
    return ClusterService(db)


def create_agent_action(
    node_name: str,
    action_type,
    payload: dict,
    cluster_id: str,
    db: Session,
) -> 'AgentAction':
    """
    Create an AgentAction record with status=PENDING.

    Args:
        node_name: Kubernetes node name (stored in payload)
        action_type: AgentActionType enum value
        payload: Action-specific payload dict
        cluster_id: Cluster ID
        db: Database session

    Returns:
        Created AgentAction instance
    """
    from backend.models.agent_action import AgentAction, AgentActionStatus
    from backend.models.base import generate_uuid

    action = AgentAction(
        id=generate_uuid(),
        cluster_id=cluster_id,
        action_type=action_type,
        payload={**(payload or {}), "node_name": node_name},
        status=AgentActionStatus.PENDING,
    )
    db.add(action)
    db.commit()
    return action
