"""
Metrics Collection Router

Handles incoming metrics from agent clusters.
Stores pod, node, and event metrics for analysis.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
import logging

from ..models.base import get_db
from ..models.cluster import Cluster
from ..models.cluster_metric import ClusterMetric
from ..models.pod_metric import PodMetric
from ..core.redis_client import get_redis_client

router = APIRouter(prefix="/api/v1/agent-metrics", tags=["agent-metrics"])
logger = logging.getLogger(__name__)


def _resolve_ec2_instance_ids(db: Session, cluster_id: str, region: str):
    """
    Resolve ip- placeholder instance IDs to real EC2 i- IDs via AWS DescribeInstances.
    Uses private IP address extracted from K8s hostname: ip-192-168-58-117 → 192.168.58.117.
    Cached in Redis for 10 minutes per cluster to avoid excessive AWS API calls.
    """
    from ..models.instance import Instance
    from ..core.redis_client import get_redis_client

    redis = get_redis_client()
    cache_key = f"ec2_id_resolve:{cluster_id}"

    # Skip if recently resolved (10 min cache)
    if redis and redis.get(cache_key):
        return

    # Find running instances with ip- placeholder IDs
    ip_instances = db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.state == 'running',
        Instance.instance_id.like('ip-%'),
    ).all()

    if not ip_instances:
        # All instances already have real IDs — cache and skip
        if redis:
            redis.setex(cache_key, 600, "resolved")
        return

    # Extract private IPs from hostnames: ip-192-168-58-117 → 192.168.58.117
    ip_map = {}  # private_ip → Instance ORM object
    for inst in ip_instances:
        parts = inst.instance_id.replace('ip-', '').split('-')
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            private_ip = '.'.join(parts)
            ip_map[private_ip] = inst

    if not ip_map:
        return

    # Load platform AWS credentials
    from ..models.system_config import SystemConfig
    pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
    ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
    plat_key = pk.value if pk and pk.value else None
    plat_secret = ps.value if ps and ps.value else None
    if not plat_key or not plat_secret:
        return

    # Try to assume role if configured, otherwise use platform creds directly
    from ..models.cluster import Cluster
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    role_arn = cluster.aws_role_arn if cluster else None
    ext_id = cluster.aws_external_id if cluster else None
    if not role_arn and cluster and cluster.account_id:
        try:
            from ..models.account import Account
            acct = db.query(Account).filter(Account.id == cluster.account_id).first()
            if acct:
                role_arn = acct.role_arn
                ext_id = acct.external_id
        except Exception:
            pass

    import boto3
    ec2_kwargs = {"region_name": region}
    if role_arn:
        try:
            sts = boto3.client(
                "sts",
                aws_access_key_id=plat_key,
                aws_secret_access_key=plat_secret,
                region_name=region,
            )
            assume_kw = {"RoleArn": role_arn, "RoleSessionName": "ec2-id-resolve"}
            if ext_id:
                assume_kw["ExternalId"] = ext_id
            creds = sts.assume_role(**assume_kw)["Credentials"]
            ec2_kwargs.update({
                "aws_access_key_id": creds["AccessKeyId"],
                "aws_secret_access_key": creds["SecretAccessKey"],
                "aws_session_token": creds["SessionToken"],
            })
        except Exception as e:
            logger.debug(f"[ec2_resolve] STS assume_role failed, using platform creds: {e}")
            ec2_kwargs.update({
                "aws_access_key_id": plat_key,
                "aws_secret_access_key": plat_secret,
            })
    else:
        ec2_kwargs.update({
            "aws_access_key_id": plat_key,
            "aws_secret_access_key": plat_secret,
        })

    ec2 = boto3.client("ec2", **ec2_kwargs)
    private_ips = list(ip_map.keys())

    try:
        resp = ec2.describe_instances(
            Filters=[
                {"Name": "private-ip-address", "Values": private_ips},
                {"Name": "instance-state-name", "Values": ["running", "pending"]},
            ]
        )
    except Exception as e:
        logger.warning(f"[ec2_resolve] DescribeInstances failed: {e}")
        # Cache failure to avoid retrying on every batch
        if redis:
            redis.setex(cache_key, 120, "failed")
        return

    resolved = 0
    for reservation in resp.get("Reservations", []):
        for ec2_inst in reservation.get("Instances", []):
            ec2_id = ec2_inst.get("InstanceId", "")
            priv_ip = ec2_inst.get("PrivateIpAddress", "")
            if ec2_id.startswith("i-") and priv_ip in ip_map:
                inst = ip_map[priv_ip]
                # Remove any stale/duplicate record that already has this EC2 ID
                # (e.g. terminated instances from previous discovery runs)
                stale = db.query(Instance).filter(
                    Instance.cluster_id == cluster_id,
                    Instance.instance_id == ec2_id,
                    Instance.id != inst.id,
                ).all()
                for s in stale:
                    logger.info(
                        f"[ec2_resolve] Removing stale record {s.instance_id} "
                        f"(state={s.state}) to make room for live node"
                    )
                    db.delete(s)
                if stale:
                    db.flush()  # Ensure deletes are visible before update

                logger.info(
                    f"[ec2_resolve] Resolved {inst.instance_id} → {ec2_id} "
                    f"(private IP {priv_ip}, node {inst.node_name})"
                )
                inst.instance_id = ec2_id
                # Also update architecture from EC2 metadata
                arch = ec2_inst.get("Architecture", "")
                if arch in ("x86_64", "arm64"):
                    inst.architecture = "arm64" if arch == "arm64" else "amd64"
                resolved += 1

    if resolved > 0:
        db.commit()
        logger.info(f"[ec2_resolve] Upgraded {resolved}/{len(ip_instances)} instance IDs for cluster {cluster_id}")

    if redis:
        redis.setex(cache_key, 600, f"resolved:{resolved}")


@router.post("/batch")
async def receive_metrics_batch(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Receive a batch of metrics from an agent.

    Metrics can be pod, node, or event metrics.
    This endpoint stores metrics in the database and caches recent values.
    """
    try:
        cluster_id = payload.get("cluster_id")
        metrics = payload.get("metrics", [])
        timestamp = payload.get("timestamp")

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Process metrics by type
        pod_metrics = []
        node_metrics = []
        event_metrics = []

        for metric in metrics:
            metric_type = metric.get("metric_type")

            if metric_type == "pod":
                pod_metrics.append(metric)
            elif metric_type == "node":
                node_metrics.append(metric)
            elif metric_type == "event":
                event_metrics.append(metric)

        # Calculate aggregated metrics from node data
        total_cpu_capacity = 0
        total_mem_capacity = 0
        total_cpu_usage = 0
        total_mem_usage = 0

        logger.debug(f"Processing {len(node_metrics)} node metrics for cluster {cluster_id}")

        for node in node_metrics:
            cpu_cap = node.get("cpu_capacity_millicores", 0)
            cpu_use = node.get("cpu_usage_millicores", 0)
            mem_cap = node.get("memory_capacity_bytes", 0)
            mem_use = node.get("memory_usage_bytes", 0)

            logger.debug(f"Node {node.get('node_name')}: CPU cap={cpu_cap}, usage={cpu_use}, Mem cap={mem_cap}, usage={mem_use}")

            # CPU in millicores (1000 millicores = 1 core)
            total_cpu_capacity += cpu_cap
            total_cpu_usage += cpu_use
            # Memory in bytes
            total_mem_capacity += mem_cap
            total_mem_usage += mem_use

        logger.debug(f"Totals - CPU cap={total_cpu_capacity}, usage={total_cpu_usage}, Mem cap={total_mem_capacity}, usage={total_mem_usage}")

        # Upsert Instance records from live node metrics.
        # This is the authoritative path: if the daemon set reports a node as
        # running, it IS running regardless of what the DB previously said.
        from datetime import timedelta
        from ..models.instance import Instance, InstanceLifecycle
        from ..models.base import generate_uuid

        for node in node_metrics:
            node_name = node.get("node_name")
            if not node_name:
                continue

            cpu_cap = node.get("cpu_capacity_millicores", 0)
            cpu_use = node.get("cpu_usage_millicores", 0)
            mem_cap = node.get("memory_capacity_bytes", 0)
            mem_use = node.get("memory_usage_bytes", 0)

            cpu_util_pct = round((cpu_use / cpu_cap) * 100, 2) if cpu_cap > 0 else 0
            mem_util_pct = round((mem_use / mem_cap) * 100, 2) if mem_cap > 0 else 0

            # Extract instance metadata from K8s node labels
            labels = node.get("labels", {})
            instance_type = (
                labels.get("node.kubernetes.io/instance-type")
                or labels.get("beta.kubernetes.io/instance-type")
                or "unknown"
            )
            az = (
                labels.get("topology.kubernetes.io/zone")
                or labels.get("failure-domain.beta.kubernetes.io/zone")
                or "unknown"
            )
            # Determine spot lifecycle from K8s node labels.
            # Sources checked in priority order:
            #   1. eks.amazonaws.com/capacityType   — EKS managed node groups (SPOT / ON_DEMAND)
            #   2. karpenter.sh/capacity-type        — Karpenter-provisioned nodes (spot / on-demand)
            #   3. node.kubernetes.io/lifecycle      — self-managed / legacy label (spot / normal)
            # If none of these are present (direct-launched non-Karpenter spot instances),
            # fall back to the existing DB value so the pre-registered SPOT record set by
            # _launch_spot_instance_direct is not overwritten with ON_DEMAND.
            lc_label = (
                labels.get("eks.amazonaws.com/capacityType")
                or labels.get("karpenter.sh/capacity-type")
                or labels.get("node.kubernetes.io/lifecycle")
                or ""
            ).lower()
            if "spot" in lc_label:
                lifecycle = InstanceLifecycle.SPOT
            elif lc_label == "":
                # No lifecycle label present — direct-launched non-Karpenter spot nodes
                # don't carry K8s lifecycle labels unless kubelet is explicitly configured.
                # Set to None so the existing DB value is preserved (see update logic below).
                lifecycle = None
            else:
                lifecycle = InstanceLifecycle.ON_DEMAND

            # Short ID: use first DNS label (e.g. "ip-192-168-3-201") to fit VARCHAR(20)
            short_id = node_name.split('.')[0][:20]

            # Extract real EC2 instance ID from provider_id if agent reported it
            ec2_instance_id = node.get("provider_id")  # e.g. "i-0abc123def456"

            # Try to match existing instance by node_name, short instance_id, or EC2 ID
            inst = None
            if ec2_instance_id:
                inst = db.query(Instance).filter(
                    Instance.cluster_id == cluster_id,
                    Instance.instance_id == ec2_instance_id,
                ).first()
            if not inst:
                inst = db.query(Instance).filter(
                    Instance.cluster_id == cluster_id,
                    (Instance.node_name == node_name) | (Instance.instance_id == short_id),
                ).first()

            if inst:
                # Mark as running (daemon set is reporting it — it's alive)
                inst.state = "running"
                inst.cpu_util = cpu_util_pct
                inst.memory_util = mem_util_pct
                if instance_type and instance_type != "unknown":
                    inst.instance_type = instance_type
                # Upgrade placeholder ip- instance_id to real EC2 i- ID when available
                if ec2_instance_id and not inst.instance_id.startswith('i-'):
                    logger.info(
                        f"[metrics] Upgrading instance_id {inst.instance_id} → "
                        f"{ec2_instance_id} for {node_name}"
                    )
                    inst.instance_id = ec2_instance_id
                if az and az != "unknown":
                    inst.az = az
                # RC3 guard: K8s label SPOT→OD must be observed 3× (~90s) before accepting.
                # After agent reinstall, labels may not propagate to the first few batch
                # payloads, causing a false ON_DEMAND report on a confirmed SPOT node.
                # lifecycle=None means no K8s label was present — preserve existing DB value.
                if lifecycle is None:
                    pass  # No label — keep existing DB lifecycle unchanged
                elif lifecycle == InstanceLifecycle.SPOT:
                    inst.lifecycle = InstanceLifecycle.SPOT
                    try:
                        from backend.core.redis_client import get_redis_client as _grc_m
                        _grc_m().delete(f"rc3:metrics_od_streak:{inst.instance_id}")
                    except Exception:
                        pass
                elif inst.lifecycle == InstanceLifecycle.SPOT:
                    # K8s says OD but DB has SPOT — guard against transient label absence
                    try:
                        from backend.core.redis_client import get_redis_client as _grc_m2
                        _rm2 = _grc_m2()
                        _sk_m = f"rc3:metrics_od_streak:{inst.instance_id}"
                        _streak_m = int(_rm2.incr(_sk_m) or 0)
                        _rm2.expire(_sk_m, 300)  # 5-min TTL (Issue 3c: was 1800s — streak window should match rebalancer cycle)
                        if _streak_m >= 3:
                            inst.lifecycle = lifecycle
                            _rm2.delete(_sk_m)
                        # else: keep SPOT (transient label absence after reinstall)
                    except Exception:
                        pass  # Redis unavailable — preserve current lifecycle
                else:
                    inst.lifecycle = lifecycle  # OD→OD: safe to update directly
                if not inst.node_name:
                    inst.node_name = node_name
                inst.updated_at = datetime.utcnow()
                logger.debug(f"Updated instance {inst.instance_id} ({node_name}): CPU={cpu_util_pct}%, Mem={mem_util_pct}%")
            else:
                # No record — create one. The daemon set is the source of truth.
                # Use short hostname as instance_id placeholder (VARCHAR(20) safe).
                # Real EC2 instance ID will be updated when register-node is called.
                # Skip creation if instance_type is unknown (no K8s labels yet) to
                # prevent ghost "unknown-node" records from appearing in the UI.
                if instance_type == 'unknown' or az == 'unknown':
                    logger.debug(
                        f"[metrics] Skipping Instance creation for {node_name}: "
                        f"instance_type or AZ not yet labelled (K8s labels pending). "
                        f"Will create on next metrics push once labels propagate."
                    )
                    continue
                # When no K8s lifecycle label is present (lifecycle=None), check whether
                # the cluster already has any known spot instances. If so, default to
                # SPOT (safer) rather than ON_DEMAND to avoid false rebalancing.
                # The aws_sync worker will correct the lifecycle within 15s if wrong.
                # Defaulting to ON_DEMAND caused cluster growth: spot nodes with missing
                # K8s labels were registered as OD, then the rebalancer launched
                # replacements thinking they needed to be converted to spot.
                _default_lc = InstanceLifecycle.ON_DEMAND  # safe fallback
                if lifecycle is None:
                    try:
                        _has_spot = db.query(Instance).filter(
                            Instance.cluster_id == cluster_id,
                            Instance.lifecycle == InstanceLifecycle.SPOT,
                            Instance.state == 'running',
                        ).first()
                        if _has_spot:
                            _default_lc = InstanceLifecycle.SPOT  # cluster is spot-heavy
                    except Exception:
                        pass
                new_inst = Instance(
                    id=generate_uuid(),
                    cluster_id=cluster_id,
                    instance_id=ec2_instance_id or short_id,  # prefer real EC2 ID
                    node_name=node_name,
                    instance_type=instance_type,
                    az=az,
                    lifecycle=lifecycle if lifecycle is not None else _default_lc,
                    state="running",
                    cpu_util=cpu_util_pct,
                    memory_util=mem_util_pct,
                )
                db.add(new_inst)
                db.flush()  # make record visible to subsequent iterations in same request
                _disp_id = ec2_instance_id or short_id
                logger.info(
                    f"[metrics] Created Instance record for {node_name} (id={_disp_id}) "
                    f"({instance_type}, {lifecycle}, {az}) — auto-registered from node metrics"
                )

        # Upsert NodeMetadata from node metrics so /optimize/nodes/bin-packing has data
        if node_metrics:
            try:
                from backend.models.node_metadata import NodeMetadata as _NM
                from sqlalchemy.dialects.postgresql import insert as _pg_insert
                _nm_rows = []
                for _n in node_metrics:
                    _nn = _n.get("node_name")
                    if not _nn:
                        continue
                    _lbs = _n.get("labels", {})
                    _cap_type = (
                        _lbs.get("eks.amazonaws.com/capacityType")
                        or _lbs.get("karpenter.sh/capacity-type")
                        or _lbs.get("node.kubernetes.io/lifecycle")
                        or None
                    )
                    _nm_rows.append({
                        "id": str(__import__("uuid").uuid4()),
                        "cluster_id": cluster_id,
                        "node_name": _nn,
                        "az": _lbs.get("topology.kubernetes.io/zone") or _lbs.get("failure-domain.beta.kubernetes.io/zone"),
                        "capacity_type": _cap_type,
                        "nodepool_name": _lbs.get("karpenter.sh/nodepool") or _lbs.get("eks.amazonaws.com/nodegroup"),
                        "instance_type": _lbs.get("node.kubernetes.io/instance-type") or _lbs.get("beta.kubernetes.io/instance-type"),
                        "do_not_disrupt": _lbs.get("karpenter.sh/do-not-disrupt") == "true",
                        "is_ready": True,
                        "allocatable_cpu_millicores": _n.get("allocatable_cpu_millicores") or _n.get("cpu_capacity_millicores"),
                        "allocatable_memory_bytes": _n.get("allocatable_memory_bytes") or _n.get("memory_capacity_bytes"),
                        "updated_at": datetime.utcnow(),
                    })
                # Deduplicate by node_name — same node can appear multiple times per batch
                _nm_dedup = {r["node_name"]: r for r in _nm_rows}
                _nm_rows = list(_nm_dedup.values())
                if _nm_rows:
                    _nm_stmt = _pg_insert(_NM).values(_nm_rows).on_conflict_do_update(
                        index_elements=["cluster_id", "node_name"],
                        set_={
                            "az": _pg_insert(_NM).excluded.az,
                            "capacity_type": _pg_insert(_NM).excluded.capacity_type,
                            "nodepool_name": _pg_insert(_NM).excluded.nodepool_name,
                            "instance_type": _pg_insert(_NM).excluded.instance_type,
                            "do_not_disrupt": _pg_insert(_NM).excluded.do_not_disrupt,
                            "is_ready": _pg_insert(_NM).excluded.is_ready,
                            "allocatable_cpu_millicores": _pg_insert(_NM).excluded.allocatable_cpu_millicores,
                            "allocatable_memory_bytes": _pg_insert(_NM).excluded.allocatable_memory_bytes,
                            "updated_at": _pg_insert(_NM).excluded.updated_at,
                        },
                    )
                    db.execute(_nm_stmt)
            except Exception as _nm_err:
                logger.warning(f"[metrics] NodeMetadata upsert failed (non-fatal): {_nm_err}")

        # Insert pod metrics into database
        for pod in pod_metrics:
            try:
                cpu_req = pod.get("cpu_request_millicores")
                cpu_use = pod.get("cpu_usage_millicores", 0)
                mem_req = pod.get("memory_request_bytes")
                mem_use = pod.get("memory_usage_bytes", 0)
                
                _pod_start_time = None
                _raw_start = pod.get("start_time")
                if _raw_start:
                    try:
                        _pod_start_time = datetime.fromisoformat(str(_raw_start).replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                pod_metric = PodMetric(
                    cluster_id=cluster_id,
                    namespace=pod.get("namespace", "default"),
                    pod_name=pod.get("pod_name", "unknown"),
                    node_name=pod.get("node_name", "unknown"),
                    controller_kind=pod.get("controller_kind"),
                    controller_name=pod.get("controller_name"),
                    cpu_usage_millicores=cpu_use,
                    cpu_request_millicores=cpu_req,
                    cpu_limit_millicores=pod.get("cpu_limit_millicores"),
                    memory_usage_bytes=mem_use,
                    memory_request_bytes=mem_req,
                    memory_limit_bytes=pod.get("memory_limit_bytes"),
                    cpu_utilization_pct=(cpu_use / cpu_req * 100) if cpu_req else None,
                    memory_utilization_pct=(mem_use / mem_req * 100) if mem_req else None,
                    container_count=pod.get("container_count", 1),
                    pod_metadata=pod.get("labels", {}),  # Map agent's labels to metadata for PVC detection
                    phase=pod.get("phase"),
                    start_time=_pod_start_time,
                    timestamp=datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow()
                )
                db.add(pod_metric)
            except Exception as e:
                logger.warning(f"Error structuring pod metric: {e}")

        # Query only running instances in the cluster to calculate true total capacity
        instances = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.state == 'running',
        ).all()

        total_nodes = len(instances)

        # If no instances found, fall back to current batch count
        if total_nodes == 0:
            total_nodes = len(node_metrics)

        logger.debug(f"Total nodes from instances table: {total_nodes}")

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

        true_cluster_cpu_cores = 0
        true_cluster_mem_gb = 0
        
        # Calculate cluster capacity by summing capacities of all member instances
        if instances:
            for inst in instances:
                true_cluster_cpu_cores += _VCPU_MAP.get(inst.instance_type or 't3.medium', 2)
                true_cluster_mem_gb += _MEM_MAP.get(inst.instance_type or 't3.medium', 4)
        else:
            true_cluster_cpu_cores = int(total_cpu_capacity / 1000)
            true_cluster_mem_gb = int(total_mem_capacity / (1024**3))

        # Update cluster with real-time aggregated data
        cluster.node_count = total_nodes
        cluster.cpu_total = true_cluster_cpu_cores
        cluster.mem_total = true_cluster_mem_gb

        # Self-heal cluster status: receiving a metrics batch proves the agent is alive.
        # The HTTP heartbeat may not reach the backend (e.g. agent behind NAT/firewall),
        # so upgrade status here to prevent the UI from showing "Install Agent" prompts.
        # ALWAYS update last_heartbeat so the Celery stale-agent task (5-min threshold)
        # doesn't reset the cluster back to DISCOVERED between metrics batches.
        from backend.models.cluster import ClusterStatus as _CS
        cluster.last_heartbeat = datetime.utcnow()
        if cluster.status != _CS.ACTIVE or cluster.agent_installed != 'Y':
            cluster.status = _CS.ACTIVE
            cluster.agent_installed = 'Y'

        logger.debug(f"Updated cluster: node_count={cluster.node_count}, cpu_total={cluster.cpu_total}, mem_total={cluster.mem_total}")

        # Calculate cluster usage percentages
        # Note: the total_cpu_usage / total_mem_usage from the agent batch is transient! 
        # Calculate an aggregate from the instances themselves to be completely accurate at the top level
        total_cluster_cpu_util_pct = 0
        total_cluster_mem_util_pct = 0
        
        if instances:
            used_cores = sum((_VCPU_MAP.get(inst.instance_type or 't3.medium', 2) * (inst.cpu_util or 0) / 100) for inst in instances)
            used_gb = sum((_MEM_MAP.get(inst.instance_type or 't3.medium', 4) * (inst.memory_util or 0) / 100) for inst in instances)
            
            if true_cluster_cpu_cores > 0:
                total_cluster_cpu_util_pct = round((used_cores / true_cluster_cpu_cores) * 100, 2)
            if true_cluster_mem_gb > 0:
                total_cluster_mem_util_pct = round((used_gb / true_cluster_mem_gb) * 100, 2)
        else:
             if total_cpu_capacity > 0:
                 total_cluster_cpu_util_pct = round((total_cpu_usage / total_cpu_capacity) * 100, 2)
             if total_mem_capacity > 0:
                 total_cluster_mem_util_pct = round((total_mem_usage / total_mem_capacity) * 100, 2)

        cluster.cpu_usage_pct = total_cluster_cpu_util_pct
        cluster.mem_usage_pct = total_cluster_mem_util_pct

        logger.debug(f"About to commit - cluster.cpu_usage_pct={cluster.cpu_usage_pct}, cluster.mem_usage_pct={cluster.mem_usage_pct}")

        # Calculate spot vs on-demand from node labels
        spot_count = sum(1 for node in node_metrics
                        if node.get("labels", {}).get("node.kubernetes.io/instance-type", "").startswith("spot"))
        cluster.spot_count = spot_count

        # Store aggregated metrics in database
        if (pod_metrics or node_metrics or event_metrics) and cluster_id:
            cluster_metric = ClusterMetric(
                cluster_id=cluster_id,
                metric_type="aggregated",
                metric_data={
                    "pod_count": len(pod_metrics),
                    "node_count": len(node_metrics),
                    "event_count": len(event_metrics),
                    "pod_metrics": pod_metrics[:10],  # Store sample
                    "node_metrics": node_metrics,     # Store all nodes
                    "event_metrics": event_metrics[:20],  # Store sample
                    "total_cpu_cores": cluster.cpu_total,
                    "total_mem_gib": cluster.mem_total,
                    "cpu_usage_millicores": total_cpu_usage,
                    "mem_usage_bytes": total_mem_usage,
                    "cpu_usage_pct": float(cluster.cpu_usage_pct) if cluster.cpu_usage_pct else 0,
                    "mem_usage_pct": float(cluster.mem_usage_pct) if cluster.mem_usage_pct else 0
                },
                timestamp=datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow()
            )
            db.add(cluster_metric)

        # Commit cluster updates (including usage percentages)
        db.commit()
        logger.debug(f"Committed - cluster.cpu_usage_pct={cluster.cpu_usage_pct}, cluster.mem_usage_pct={cluster.mem_usage_pct}")

        # ── Resolve ip- placeholder instance IDs to real EC2 i- IDs via AWS ──
        # The agent collector may only report K8s hostnames (ip-192-168-x-x).
        # The rebalancer requires real EC2 instance IDs (i-xxx) to operate.
        # This resolver uses DescribeInstances with private-IP filters to upgrade
        # placeholder IDs. Cached in Redis (10 min) to avoid hammering AWS.
        try:
            _resolve_ec2_instance_ids(db, cluster_id, cluster.region or 'ap-south-1')
        except Exception as _ec2_resolve_err:
            logger.debug(f"[metrics] EC2 ID resolution skipped: {_ec2_resolve_err}")

        # Cache latest metrics in Redis for fast access
        try:
            redis_client = get_redis_client()
            # Cache node metrics (latest state)
            for node_metric in node_metrics:
                cache_key = f"metrics:node:{cluster_id}:{node_metric.get('node_name')}"
                redis_client.setex(
                    cache_key,
                    900,  # 15 minute TTL — survives missed agent cycles
                    str(node_metric)
                )

            # Cache pod count and health summary
            running_pods = sum(1 for p in pod_metrics if p.get("phase") == "Running")
            cache_key = f"metrics:cluster:{cluster_id}:summary"
            redis_client.setex(
                cache_key,
                600,  # 10 minute TTL — prevents blank UI during transient agent gaps
                str({
                    "total_pods": len(pod_metrics),
                    "running_pods": running_pods,
                    "total_nodes": len(node_metrics),
                    "last_update": timestamp or datetime.utcnow().isoformat()
                })
            )
        except Exception as cache_error:
            logger.warning(f"Failed to cache metrics: {cache_error}")
            # Don't fail the request if caching fails

        logger.info(
            f"Received metrics batch from cluster {cluster_id}: "
            f"{len(pod_metrics)} pods, {len(node_metrics)} nodes, {len(event_metrics)} events"
        )

        return {
            "success": True,
            "cluster_id": cluster_id,
            "received": {
                "pods": len(pod_metrics),
                "nodes": len(node_metrics),
                "events": len(event_metrics)
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing metrics batch: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process metrics: {str(e)}"
        )


@router.get("/cluster/{cluster_id}/latest")
async def get_latest_metrics(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the latest metrics for a cluster.

    Returns cached metrics if available, otherwise queries database.
    """
    try:
        # Try cache first
        try:
            redis_client = get_redis_client()
            cache_key = f"metrics:cluster:{cluster_id}:summary"
            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Returning cached metrics for cluster {cluster_id}")
                return {
                    "cluster_id": cluster_id,
                    "metrics": eval(cached_data),
                    "source": "cache"
                }
        except Exception as cache_error:
            logger.warning(f"Cache read failed: {cache_error}")

        # Fall back to database
        latest_metric = db.query(ClusterMetric).filter(
            ClusterMetric.cluster_id == cluster_id
        ).order_by(ClusterMetric.timestamp.desc()).first()

        if not latest_metric:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No metrics found for cluster {cluster_id}"
            )

        return {
            "cluster_id": cluster_id,
            "metrics": latest_metric.metric_data,
            "timestamp": latest_metric.timestamp.isoformat(),
            "source": "database"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching latest metrics for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics: {str(e)}"
        )


@router.get("/cluster/{cluster_id}/history")
async def get_metrics_history(
    cluster_id: str,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """
    Get historical metrics for a cluster.

    Returns metrics from the past N hours.
    """
    try:
        from datetime import timedelta

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        metrics = db.query(ClusterMetric).filter(
            ClusterMetric.cluster_id == cluster_id,
            ClusterMetric.timestamp >= cutoff_time
        ).order_by(ClusterMetric.timestamp.desc()).all()

        return {
            "cluster_id": cluster_id,
            "hours": hours,
            "total_records": len(metrics),
            "metrics": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "data": m.metric_data
                }
                for m in metrics
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching metrics history for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics history: {str(e)}"
        )
