"""Auto-Rebalancing Worker - System B: Automatic Node Migration

Executes auto-rebalancing actions created by termination_monitor.py:
1. Emergency Rebalancing (90 seconds): Triggered on termination notice
2. Graceful Rebalancing (10 minutes): Proactive migration to safer pools

Process:
- Query rebalancing_actions table for 'in_progress' actions
- Drain nodes on source pool
- Provision new nodes on target pool (via Karpenter)
- Update action status to 'completed' or 'failed'
- Calculate duration

Celery Task: Runs every 15 seconds checking for active rebalancing actions
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
import hashlib

import boto3
from botocore.exceptions import ClientError

from backend.core.logger import logger
from backend.models.base import get_db
from backend.models.rebalancing_action import RebalancingAction
from backend.models.cluster import Cluster
from backend.models.instance import Instance, InstanceLifecycle


# ── Pillar 1: State Machine States ────────────────────────────────────────────
SM_CREATED              = 'CREATED'
SM_POOL_SELECTED        = 'POOL_SELECTED'
SM_SOURCE_CORDONED      = 'SOURCE_CORDONED'
SM_SOURCE_DRAINED       = 'SOURCE_DRAINED'
SM_REPLACEMENT_LAUNCHING = 'REPLACEMENT_LAUNCHING'
SM_REPLACEMENT_READY    = 'REPLACEMENT_READY'
SM_SOURCE_TERMINATING   = 'SOURCE_TERMINATING'
SM_COMPLETED            = 'COMPLETED'
SM_FAILED               = 'FAILED'
SM_DRAIN_TIMEOUT        = 'DRAIN_TIMEOUT'


def _sm_transition(db: Session, action_id: int, from_state: str, to_state: str, max_retries: int = 2) -> bool:
    """
    Pillar 1 — Atomic state machine transition using optimistic locking.

    Executes: UPDATE rebalancing_actions SET current_state = to_state
              WHERE id = action_id AND current_state = from_state

    Returns True if transition succeeded (exactly 1 row updated).
    Returns False if another worker already advanced past from_state.

    BUG-8 fix: Retries up to max_retries times with 100ms/200ms backoff.
    Re-reads current state before each retry to detect if another worker won.
    """
    import time as _time_sm
    for _attempt in range(max_retries + 1):
        try:
            from sqlalchemy import text
            result = db.execute(
                text(
                    "UPDATE rebalancing_actions "
                    "SET current_state = :to_state "
                    "WHERE id = :action_id AND (current_state = :from_state OR current_state IS NULL AND :from_state = 'CREATED') "
                ),
                {"to_state": to_state, "action_id": action_id, "from_state": from_state},
            )
            db.commit()
            if result.rowcount == 1:
                logger.info(f"[state_machine] action={action_id}: {from_state} → {to_state}")
                return True
            # Transition failed — check if retry is worthwhile
            if _attempt < max_retries:
                _time_sm.sleep(0.1 * (_attempt + 1))  # 100ms, 200ms
                # Re-read current state to decide whether to retry or abort
                try:
                    _current_row = db.execute(
                        text("SELECT current_state FROM rebalancing_actions WHERE id = :aid"),
                        {"aid": action_id}
                    ).fetchone()
                    if _current_row and _current_row[0] != from_state:
                        logger.warning(
                            f"[state_machine] action={action_id}: transition {from_state}→{to_state} "
                            f"aborted — current state is {_current_row[0]} (another worker won)"
                        )
                        return False
                except Exception:
                    pass
                continue
            logger.warning(f"[state_machine] action={action_id}: transition {from_state}→{to_state} lost after {max_retries + 1} attempts")
            return False
        except Exception as e:
            logger.error(f"[state_machine] action={action_id} transition failed: {e}")
            db.rollback()
            return False
    return False


def _sm_set_state(db: Session, action_id: int, state: str):
    """Force-set state without optimistic check (use for initial CREATED and FAILED/COMPLETED)."""
    try:
        from sqlalchemy import text
        db.execute(
            text("UPDATE rebalancing_actions SET current_state = :state WHERE id = :id"),
            {"state": state, "id": action_id},
        )
        db.commit()
    except Exception as e:
        logger.error(f"[state_machine] _sm_set_state action={action_id} state={state} failed: {e}")
        db.rollback()


def _get_instance_arch(ec2_client, instance_type: str, fallback_arm_families: set, region: str) -> str:
    """
    Problem #10 — Determine architecture for an instance type using the
    DescribeInstanceTypes API with a 7-day Redis cache.  Falls back to the
    static ARM family set when the API is unavailable.

    Returns 'arm64' or 'x86_64'.
    """
    if not instance_type:
        return "x86_64"
    cache_key = f"instance_type_arch:{instance_type}"
    try:
        from backend.core.redis_client import get_redis_client as _grc_arch_helper
        _r = _grc_arch_helper()
        cached = _r.get(cache_key)
        if cached:
            return cached.decode() if isinstance(cached, bytes) else cached
    except Exception:
        _r = None

    # Call DescribeInstanceTypes API
    try:
        resp = ec2_client.describe_instance_types(InstanceTypes=[instance_type])
        if resp.get("InstanceTypes"):
            supported = resp["InstanceTypes"][0].get("ProcessorInfo", {}).get("SupportedArchitectures", [])
            arch = "arm64" if "arm64" in supported else "x86_64"
            try:
                if _r:
                    _r.setex(cache_key, 7 * 86400, arch)  # 7-day TTL
            except Exception:
                pass
            return arch
    except Exception as _e:
        logger.debug(f"[arch_detect] DescribeInstanceTypes failed for {instance_type}: {_e}")

    # Fallback: static family set
    family = instance_type.split('.')[0] if '.' in instance_type else instance_type
    return "arm64" if family in fallback_arm_families else "x86_64"


def _extract_k8s_minor_version(cluster, source_ami_name: str) -> Optional[str]:
    """Best-effort extraction of the EKS minor version used by this cluster/AMI."""
    import re as _re_k8s

    _cluster_version = getattr(cluster, 'k8s_version', None) or ''
    _cluster_match = _re_k8s.search(r'(\d+\.\d+)', str(_cluster_version))
    if _cluster_match:
        return _cluster_match.group(1)

    _ami_match = _re_k8s.search(r'(\d+\.\d+)', source_ami_name or '')
    if _ami_match:
        return _ami_match.group(1)

    return None


def _resolve_arch_compatible_ami(ec2_client, cluster, source_ami_name: str, target_arch: str) -> Optional[str]:
    """
    Resolve an EKS-compatible AMI for the requested architecture.

    Strategy:
    1. Exact source-name architecture swap for classic EKS AMIs.
    2. Version-aware wildcard search across common EKS naming schemes.
    3. Generic architecture wildcard search as a last resort.

    Returns an AMI ID or None if no compatible AMI could be found.
    """
    _name_candidates = []
    _version = _extract_k8s_minor_version(cluster, source_ami_name)
    _is_arm = target_arch == 'arm64'

    if source_ami_name and 'amazon-eks' in source_ami_name:
        if _is_arm and 'amazon-eks-node' in source_ami_name and 'arm64' not in source_ami_name:
            _name_candidates.append(source_ami_name.replace('amazon-eks-node', 'amazon-eks-arm64-node'))
        elif not _is_arm and 'amazon-eks-arm64-node' in source_ami_name:
            _name_candidates.append(source_ami_name.replace('amazon-eks-arm64-node', 'amazon-eks-node'))

    if _version:
        if _is_arm:
            _name_candidates.extend([
                f'amazon-eks-arm64-node-{_version}*',
                f'amazon-eks-node-al2023-arm64-standard-{_version}*',
            ])
        else:
            _name_candidates.extend([
                f'amazon-eks-node-{_version}*',
                f'amazon-eks-node-al2023-x86_64-standard-{_version}*',
            ])

    if _is_arm:
        _name_candidates.extend([
            'amazon-eks-arm64-node-*',
            'amazon-eks-node-al2023-arm64-standard-*',
        ])
    else:
        _name_candidates.extend([
            'amazon-eks-node-*',
            'amazon-eks-node-al2023-x86_64-standard-*',
        ])

    _seen = set()
    _name_candidates = [n for n in _name_candidates if n and not (n in _seen or _seen.add(n))]

    for _name_filter in _name_candidates:
        try:
            _resp = ec2_client.describe_images(
                Owners=['602401143452', 'amazon'],
                Filters=[
                    {'Name': 'name', 'Values': [_name_filter]},
                    {'Name': 'state', 'Values': ['available']},
                    {'Name': 'architecture', 'Values': [target_arch]},
                ],
            )
            _images = sorted(
                _resp.get('Images', []),
                key=lambda _img: _img.get('CreationDate', ''),
                reverse=True,
            )
            if _images:
                _selected = _images[0]
                logger.info(
                    f"[auto_rebalancer] Resolved {target_arch} AMI: "
                    f"{_selected['ImageId']} (filter={_name_filter}, name={_selected.get('Name', '')})"
                )
                return _selected['ImageId']
        except Exception as _ami_resolve_err:
            logger.warning(
                f"[auto_rebalancer] Could not resolve {target_arch} AMI with filter "
                f"{_name_filter}: {_ami_resolve_err}"
            )

    return None


def _validate_rebalancing_action_schema(
    cluster_id: str,
    source_pool: str,
    target_pool: str,
    source_od_price_hr: float = None,
    target_spot_price_hr: float = None,
    estimated_savings_hr: float = None,
) -> None:
    """
    Pillar 6 — Data contract validation for RebalancingAction creation.

    Raises ValueError with a clear message if any contract is violated.
    Called before DB insert so invalid actions are never silently stored.

    Rules:
      - source_pool must match 'instance_type:az' format
      - target_pool must match 'instance_type:az' format
      - source_od_price_hr must be >= 0 when provided (0 is allowed for unknown)
      - estimated_savings_hr must approximately equal source_od_price_hr - target_spot_price_hr
        (within 5% tolerance) when all three values are provided
    """
    import re
    pool_pattern = re.compile(r'^[a-z][a-z0-9.]+:[a-z]{2}-[a-z]+-\d[a-z]$')

    # Contract 1: Pool format validation (warn-only if region AZ suffix missing)
    if source_pool and ':' not in source_pool:
        raise ValueError(
            f"[schema_validation] source_pool='{source_pool}' must be 'instance_type:az' format"
        )
    if target_pool and ':' not in target_pool:
        raise ValueError(
            f"[schema_validation] target_pool='{target_pool}' must be 'instance_type:az' format"
        )

    # Contract 2: Price non-negative
    if source_od_price_hr is not None and source_od_price_hr < 0:
        raise ValueError(
            f"[schema_validation] source_od_price_hr={source_od_price_hr} must be >= 0"
        )
    if target_spot_price_hr is not None and target_spot_price_hr < 0:
        raise ValueError(
            f"[schema_validation] target_spot_price_hr={target_spot_price_hr} must be >= 0"
        )

    # Contract 3: estimated_savings_hr consistency check (when all three are known)
    if (source_od_price_hr is not None
            and target_spot_price_hr is not None
            and estimated_savings_hr is not None
            and source_od_price_hr > 0):
        expected = source_od_price_hr - target_spot_price_hr
        tolerance = max(0.001, abs(expected) * 0.05)  # 5% tolerance
        if abs(estimated_savings_hr - expected) > tolerance:
            raise ValueError(
                f"[schema_validation] estimated_savings_hr={estimated_savings_hr:.4f} does not match "
                f"source_od_price_hr ({source_od_price_hr:.4f}) - target_spot_price_hr ({target_spot_price_hr:.4f}) "
                f"= {expected:.4f} (tolerance ±{tolerance:.4f})"
            )


def _sync_instance_state_from_aws(db: Session, cluster: Cluster):
    """
    Pull real EC2 instance lifecycle from AWS and sync to the DB.
    This ensures the platform's source of truth is AWS, not assumed DB state.
    Requires cluster.aws_role_arn to be configured.
    """
    # Resolve role ARN: prefer cluster-level, fall back to linked account
    role_arn = cluster.aws_role_arn
    external_id = cluster.aws_external_id
    if not role_arn and cluster.account_id:
        try:
            from backend.models.account import Account
            acct = db.query(Account).filter(Account.id == cluster.account_id).first()
            if acct:
                role_arn = acct.role_arn
                external_id = acct.external_id
        except Exception:
            pass

    if not role_arn:
        logger.debug(f"[aws_sync] Cluster {cluster.name}: no role ARN configured, skipping sync")
        return

    try:
        # Use stored platform credentials from the system_configs table
        # (same pattern as AccountService._get_platform_client — no hardcoded keys)
        from backend.models.system_config import SystemConfig

        _key_row = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        _sec_row = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        _reg_row = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()

        platform_key    = _key_row.value if _key_row and _key_row.value else None
        platform_secret = _sec_row.value if _sec_row and _sec_row.value else None
        platform_region = (_reg_row.value if _reg_row and _reg_row.value else None) or cluster.region or 'ap-south-1'

        if not platform_key or not platform_secret:
            logger.debug(
                f"[aws_sync] Platform AWS credentials not configured in Admin Settings; "
                f"skipping real-time sync for cluster {cluster.name}"
            )
            return

        # Step 1: Build STS client with platform credentials
        # Use regional STS endpoint to avoid global endpoint connectivity issues
        sts = boto3.client(
            'sts',
            aws_access_key_id=platform_key,
            aws_secret_access_key=platform_secret,
            region_name=platform_region,
            endpoint_url=f"https://sts.{platform_region}.amazonaws.com",
        )

        # Step 2: Assume the client account's role via STS
        assume_kwargs = {
            'RoleArn': role_arn,
            'RoleSessionName': 'SpotOptimizerStateSync',
        }
        if external_id:
            assume_kwargs['ExternalId'] = external_id

        creds = sts.assume_role(**assume_kwargs)['Credentials']
        ec2 = boto3.client(
            'ec2',
            region_name=cluster.region or 'ap-south-1',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )

        # Describe running instances tagged for this cluster (EKS standard tag)
        response = ec2.describe_instances(
            Filters=[
                {'Name': f'tag:kubernetes.io/cluster/{cluster.name}', 'Values': ['owned', 'shared']},
                {'Name': 'instance-state-name', 'Values': ['running']},
            ]
        )

        # Build map: EC2 instance_id → (lifecycle, instance_type, az, private_ip) from AWS
        aws_instance_map = {}
        for reservation in response.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                iid = inst['InstanceId']
                # EC2 DescribeInstances: InstanceLifecycle = 'spot' | 'scheduled' | absent (on-demand)
                raw_lc = inst.get('InstanceLifecycle', 'on-demand')
                itype = inst.get('InstanceType', '')
                az = (inst.get('Placement') or {}).get('AvailabilityZone', '')
                private_ip = inst.get('PrivateIpAddress', '')
                aws_instance_map[iid] = {
                    'lifecycle': raw_lc, 'instance_type': itype, 'az': az,
                    'private_ip': private_ip,
                }
        aws_lifecycle_map = aws_instance_map  # keep name for backward compat check below

        # Build set of instance_ids already in DB for this cluster (needed for both paths below)
        db_instances = db.query(Instance).filter(Instance.cluster_id == cluster.id).all()
        db_id_map = {inst.instance_id: inst for inst in db_instances}

        if not aws_lifecycle_map:
            # Empty result may be transient (EKS tag not yet propagated, API hiccup, wrong tag).
            # Require 3 consecutive empty responses before marking instances terminated.
            # This prevents all nodes from being falsely evicted on a single bad AWS call.
            _empty_streak_key = f"aws_sync:empty_streak:{cluster.id}"
            try:
                from backend.core.redis_client import get_redis_client as _grc_es
                _r_es = _grc_es()
                _empty_streak = int(_r_es.incr(_empty_streak_key) or 0)
                _r_es.expire(_empty_streak_key, 600)  # 10-min TTL (3 × ~3-min cycles)
                logger.warning(
                    f"[aws_sync] No running instances found in AWS for cluster {cluster.name} "
                    f"(check tag kubernetes.io/cluster/{cluster.name}) "
                    f"— empty streak {_empty_streak}/3"
                )
                if _empty_streak < 3:
                    return  # Transient — don't touch DB yet
                # 3 consecutive empty responses: likely scaled to 0 or tag removed
                _r_es.delete(_empty_streak_key)
            except Exception:
                # Redis unavailable — use conservative single-observation guard:
                # never mass-terminate on a single empty result
                logger.warning(
                    f"[aws_sync] No running instances found in AWS for cluster {cluster.name} "
                    f"(Redis unavailable for streak guard) — skipping to avoid false termination"
                )
                return
            # Confirmed 3× empty: cluster likely scaled to 0 or misconfigured
            logger.warning(
                f"[aws_sync] Confirmed 3 consecutive empty AWS responses for {cluster.name} "
                f"— marking all DB instances as terminated"
            )
            for db_inst in db_instances:
                if db_inst.state == 'running':
                    db_inst.state = 'terminated'
                    db_inst.status = 'terminated'
            cluster.spot_count = 0
            cluster.on_demand_node_count = 0
            db.commit()
            return

        spot_count = 0
        od_count = 0
        corrected = 0
        created = 0

        for aws_iid, aws_data in aws_instance_map.items():
            aws_raw_lc   = aws_data['lifecycle']
            aws_itype    = aws_data['instance_type']
            aws_az       = aws_data['az']
            aws_priv_ip  = aws_data.get('private_ip', '')
            real_lifecycle = InstanceLifecycle.SPOT if aws_raw_lc == 'spot' else InstanceLifecycle.ON_DEMAND

            # Derive the K8s node hostname from the private IP (EKS convention)
            # e.g. 192.168.3.201 → ip-192-168-3-201.ap-south-1.compute.internal
            derived_node_name = None
            if aws_priv_ip:
                _region = cluster.region or 'ap-south-1'
                derived_node_name = f"ip-{aws_priv_ip.replace('.', '-')}.{_region}.compute.internal"

            db_inst = db_id_map.get(aws_iid)
            if db_inst is None:
                # ── NEW: create a DB record for every AWS instance we discover ──
                # Truncate instance_id to 20 chars (VARCHAR(20) constraint).
                safe_iid = aws_iid[:20]
                # Check again with the (possibly truncated) id to avoid duplicate
                if not db.query(Instance).filter(Instance.instance_id == safe_iid).first():
                    new_inst = Instance(
                        cluster_id=cluster.id,
                        instance_id=safe_iid,
                        instance_type=aws_itype or "t3.medium",
                        lifecycle=real_lifecycle,
                        az=aws_az or f"{cluster.region or 'ap-south-1'}a",
                        price=0.0,  # real price populated by pricing_collector worker
                        state='running',
                        status='READY',
                        architecture='amd64',
                        node_name=derived_node_name,  # EKS K8s node hostname
                    )
                    db.add(new_inst)
                    db.flush()  # get the id so we can use it below
                    created += 1
                    logger.info(
                        f"[aws_sync] Created instance record {safe_iid} "
                        f"(node={derived_node_name}, {aws_itype}, {real_lifecycle.value}) for cluster {cluster.name}"
                    )
                    db_inst = new_inst
            else:
                # Update existing record to match AWS truth
                changed = False
                if db_inst.lifecycle != real_lifecycle:
                    if (db_inst.lifecycle == InstanceLifecycle.SPOT and
                            real_lifecycle == InstanceLifecycle.ON_DEMAND):
                        # SPOT→OD downgrade: require 3 consecutive AWS observations
                        # to avoid flipping on transient DescribeInstances gaps
                        try:
                            from backend.core.redis_client import get_redis_client as _grc_rc3s
                            _r3s = _grc_rc3s()
                            _sk3s = f"rc3:sync_od_streak:{aws_iid}"
                            _streak3s = int(_r3s.incr(_sk3s) or 0)
                            # P-M3 fix: increase TTL from 300s (5 min) to 600s (10 min).
                            # With 5-min discovery cycles, a 300s TTL expires exactly at the
                            # boundary — Celery beat jitter of even 1s resets the streak.
                            # 600s gives 2× the cycle window, eliminating boundary expiry races.
                            _r3s.expire(_sk3s, 600)  # 10-min TTL (was 300s — boundary race)
                            if _streak3s >= 3:
                                db_inst.lifecycle = real_lifecycle
                                _r3s.delete(_sk3s)
                                changed = True
                                logger.info(f"[aws_sync] RC3: confirmed SPOT→OD for {aws_iid} after 3 consecutive OD observations")
                            # else: keep SPOT (transient absence)
                        except Exception as _rc3_err:
                            # Redis unavailable — keep current SPOT lifecycle.
                            # Downgrading on a transient Redis error would cause false OD
                            # classification and trigger unnecessary rebalancing.
                            logger.warning(
                                f"[aws_sync] RC3 guard Redis error for {aws_iid}: {_rc3_err} "
                                f"— keeping current lifecycle {db_inst.lifecycle} (no change)"
                            )
                    else:
                        db_inst.lifecycle = real_lifecycle
                        changed = True
                        # Clear any stale RC3 streak when confirmed non-SPOT
                        try:
                            from backend.core.redis_client import get_redis_client as _grc_rc3c
                            _grc_rc3c().delete(f"rc3:sync_od_streak:{aws_iid}")
                        except Exception:
                            pass
                if aws_itype and db_inst.instance_type != aws_itype:
                    db_inst.instance_type = aws_itype
                    changed = True
                if aws_az and db_inst.az != aws_az:
                    db_inst.az = aws_az
                    changed = True
                # Set node_name if not already stored
                if not db_inst.node_name and derived_node_name:
                    db_inst.node_name = derived_node_name
                    changed = True
                if changed:
                    logger.warning(
                        f"[aws_sync] Corrected {db_inst.instance_id}: "
                        f"lifecycle={real_lifecycle.value}, type={aws_itype}, az={aws_az}, node={derived_node_name}"
                    )
                    corrected += 1

            # Delete any ip- placeholder record that corresponds to this real instance.
            # These are created by the daemon-set metrics batch before aws_sync runs.
            if derived_node_name:
                placeholder_short = derived_node_name.split('.')[0]  # e.g. 'ip-192-168-3-201'
                dup = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.instance_id == placeholder_short,
                ).first()
                if dup:
                    # Transfer fresh utilisation data to the real instance before deleting
                    if db_inst and dup.cpu_util is not None:
                        if db_inst.cpu_util is None or dup.cpu_util > 0:
                            db_inst.cpu_util = dup.cpu_util
                            db_inst.memory_util = dup.memory_util
                    db.delete(dup)
                    logger.info(f"[aws_sync] Deleted placeholder {placeholder_short} (merged into {aws_iid[:20]})")

            if real_lifecycle == InstanceLifecycle.SPOT:
                spot_count += 1
            else:
                od_count += 1

        # Mark DB instances NOT found in AWS running set as terminated.
        # This cleans up stale records left by terminated/replaced EC2 instances.
        # SKIP placeholder records whose instance_id is a K8s hostname (e.g. ip-192-168-3-201)
        # rather than a real EC2 instance ID (always starts with "i-").
        aws_running_truncated = {aws_iid[:20] for aws_iid in aws_instance_map.keys()}
        terminated_count = 0
        for db_inst in db_instances:
            if not db_inst.instance_id or not db_inst.instance_id.startswith('i-'):
                # Placeholder record auto-created from daemon-set metrics — leave alone
                continue
            if db_inst.instance_id not in aws_running_truncated and db_inst.state == 'running':
                db_inst.state = 'terminated'
                db_inst.status = 'terminated'
                terminated_count += 1
                logger.info(
                    f"[aws_sync] Marked {db_inst.instance_id} as terminated "
                    f"(not found in AWS running instances for cluster {cluster.name})"
                )
            elif db_inst.instance_id in aws_running_truncated:
                # EC2 is running in AWS — sync state.
                if db_inst.state != 'running':
                    db_inst.state = 'running'
                # Only reset UNKNOWN→READY if the K8s collector has recently confirmed
                # this node is in the cluster (fresh last_heartbeat within 10 min).
                # Without this guard, aws_sync would override the UNKNOWN marker set by
                # cleanup_zombie_nodes for nodes whose EC2 is running but K8s node is gone
                # (i.e. failed-terminate orphans) — allowing them to re-enter rebalancing.
                _hb_fresh = (
                    db_inst.last_heartbeat is not None
                    and (datetime.utcnow() - db_inst.last_heartbeat).total_seconds() < 600
                )
                if _hb_fresh:
                    if db_inst.status not in ('READY', 'CALIBRATING'):
                        db_inst.status = 'READY'
                elif db_inst.status not in ('READY', 'CALIBRATING', 'UNKNOWN', 'terminated'):
                    # No recent K8s heartbeat — mark UNKNOWN so it's excluded from rebalancing
                    db_inst.status = 'UNKNOWN'

        # P-M1 fix: also update node_count so API consumers see correct total
        # during active rebalancing (discovery worker only updates node_count every 5 min)
        cluster.spot_count = spot_count
        cluster.on_demand_node_count = od_count
        cluster.node_count = spot_count + od_count
        db.commit()

        logger.warning(
            f"[aws_sync] Cluster {cluster.name}: {spot_count} SPOT, {od_count} ON_DEMAND "
            f"({corrected} updated, {created} created, {terminated_count} terminated, "
            f"{len(aws_lifecycle_map)} instances found in AWS)"
        )

    except ClientError as e:
        logger.warning(f"[aws_sync] AWS API error syncing cluster {cluster.name}: {e}")
    except Exception as e:
        logger.warning(f"[aws_sync] Sync failed for cluster {cluster.name}: {e}")


# _launch_spot_instance_direct() removed — all node provisioning now goes through
# Karpenter NodePool updates. The auto-rebalancer patches the NodePool with the
# target instance type, and Karpenter provisions the replacement node.


def execute_rebalancing_action(db: Session, action: RebalancingAction):
        """Execute a single rebalancing action with full cross-system safety gates."""
        from backend.core.redis_client import get_redis_client, key_cluster_cooldown, key_rebalance_lock
        from backend.services.cooldown_controller import CooldownController
        from backend.services.distributed_locks import distributed_lock

        # Track lock state outside try so finally can always release it
        _lock_key_release = None
        _redis_release = None

        try:
            logger.info(f"Executing rebalancing action {action.id}: {action.cluster_id} ({action.source_pool} → {action.target_pool})")

            cluster = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {action.cluster_id} not found")

            _redis = get_redis_client()

            # ── CLUSTER COOLDOWN GUARD ───────────────────────────────────────
            # Check if cluster-level cooldown is active (set by emergency or recent rebalance)
            _cooldown_key = key_cluster_cooldown(action.cluster_id)
            if _redis.exists(_cooldown_key):
                ttl = _redis.ttl(_cooldown_key)
                logger.info(
                    f"[auto_rebalancer] Cluster {action.cluster_id} cooldown active "
                    f"({ttl}s remaining) — deferring action {action.id}"
                )
                action.status = 'deferred'
                action.error_message = f"Cluster cooldown active ({ttl}s remaining)"
                db.commit()
                return

            # ── CONCURRENCY LOCK GUARD ───────────────────────────────────────
            # Ensure only one rebalancing cycle runs at a time per cluster.
            # Problem #1/#7: Lock TTL was 600s but actions can take up to 30 min.
            # Fix: Set initial TTL to 2700s (45 min) and heartbeat every 60s.
            # NEW-3 fix: Exactly matches the 45-min stale action expiry — lock
            # cannot release before stale detection fires if heartbeat stops.
            _lock_key = key_rebalance_lock(action.cluster_id)
            _lock_acquired = _redis.set(_lock_key, str(action.id), nx=True, ex=2700)
            if _lock_acquired:
                # Store refs so finally block can always release the lock
                _lock_key_release = _lock_key
                _redis_release = _redis
                # Start a background thread that heartbeats the per-cluster lock
                import threading as _thr_lock
                _lock_hb_stop = _thr_lock.Event()
                def _heartbeat_cluster_lock(_r, _k, _stop, _aid):
                    """Renew per-cluster rebalance lock TTL every 60s."""
                    while not _stop.wait(60):
                        try:
                            # Only renew if we still own the lock
                            _cur = _r.get(_k)
                            if _cur and (_cur.decode() if isinstance(_cur, bytes) else str(_cur)) == str(_aid):
                                _r.expire(_k, 2700)
                            else:
                                break  # Lock taken by another action
                        except Exception:
                            break
                _lock_hb_thread = _thr_lock.Thread(
                    target=_heartbeat_cluster_lock,
                    args=(_redis, _lock_key, _lock_hb_stop, action.id),
                    daemon=True,
                )
                _lock_hb_thread.start()
            if not _lock_acquired:
                logger.info(
                    f"[auto_rebalancer] Rebalance already in progress for cluster "
                    f"{action.cluster_id} — deferring action {action.id}"
                )
                action.status = 'deferred'
                action.error_message = "Rebalance lock held by concurrent action"
                db.commit()
                return

            _cooldown = CooldownController(_redis)

            # ── CROSS-SYSTEM SAFETY GATE 1: Stabilization lock ──────────────
            # Another system acted recently — wait for the cluster to reach steady state
            is_locked, remaining = _cooldown.is_stabilization_locked(action.cluster_id)
            if is_locked:
                logger.info(
                    f"[auto_rebalancer] Deferring action {action.id}: stabilization lock active "
                    f"({remaining}s remaining) — cluster not yet stable after last operation"
                )
                action.status = 'deferred'
                action.error_message = f"Stabilization lock active ({remaining}s remaining)"
                db.commit()
                return

            # ── CROSS-SYSTEM SAFETY GATE 2: Substitute mutual exclusion ─────
            # SubstituteManager is in mid-flight — do NOT drain the node it is prewarming
            sub_state_raw = _redis.get(f"spot:substitute:state:{action.cluster_id}")
            sub_state = (sub_state_raw.decode('utf-8') if isinstance(sub_state_raw, bytes) else sub_state_raw) or "IDLE"
            # READY = warm spare is standing by (good! use it). Only block PREWARMING/RELEASING.
            if sub_state in ("PREWARMING", "RELEASING"):
                logger.info(
                    f"[auto_rebalancer] Deferring action {action.id}: substitute is {sub_state} "
                    f"— draining would kill the substitute node mid-flight"
                )
                action.status = 'deferred'
                action.error_message = f"Substitute in state {sub_state} — deferred to avoid conflict"
                db.commit()
                return

            # ── CROSS-SYSTEM SAFETY GATE 3: Resize cooldown ─────────────────
            # Right-sizing just executed for this cluster — give it time before rebalancing
            if _redis.exists(f"spot:cooldown:action:resize:{action.cluster_id}"):
                logger.info(
                    f"[auto_rebalancer] Deferring action {action.id}: resize cooldown active "
                    f"— right-sizing is mid-execution for cluster {action.cluster_id}"
                )
                action.status = 'deferred'
                action.error_message = "Resize cooldown active — deferred"
                db.commit()
                return

            # ── DOUBLE-LAUNCH GUARD ───────────────────────────────────────────
            # If replacement_spot_instance_id is already set in metadata, Phase 1
            # (spot launch) already ran. Transitioning to waiting_agent at line 1241
            # should prevent re-entry, but this explicit guard protects against race
            # conditions where the action is still in_progress when the next cycle runs.
            _existing_replacement = (action.action_metadata or {}).get('replacement_spot_instance_id')
            if _existing_replacement:
                logger.info(
                    f"[auto_rebalancer] Action {action.id}: spot {_existing_replacement} already launched "
                    f"— skipping Phase 1, transitioning to waiting_agent"
                )
                action.status = 'waiting_agent'
                db.commit()
                return

            source_instance_type, source_az = action.source_pool.split(':') if ':' in action.source_pool else (action.source_pool, '')
            target_instance_type, target_az = action.target_pool.split(':') if ':' in action.target_pool else (action.target_pool, '')

            nodes_cordoned = 0
            pods_migrated = 0

            # ── DISTRIBUTED LOCK: one system drains this cluster at a time ───
            # Z10 fix: TTL increased from 180s→1200s (20 min) to cover slow EC2
            # API calls and max drain timeout. Lock auto-releases via context manager.
            lock_key = f"lock:node_action:{action.cluster_id}"
            try:
                with distributed_lock(lock_key, timeout=1200):
                    from backend.models.agent_action import AgentAction, AgentActionType

                    metadata = action.action_metadata or {}
                    instance_id_for_action = metadata.get('instance_id', '')

                    # Guard: if instance_id is a K8s hostname placeholder (not a real EC2 ID),
                    # try to resolve the real EC2 ID from the DB before proceeding.
                    if instance_id_for_action and not instance_id_for_action.startswith('i-'):
                        from backend.models.instance import Instance as _InstModel
                        _real = db.query(_InstModel).filter(
                            _InstModel.cluster_id == action.cluster_id,
                            _InstModel.node_name.like(f"{instance_id_for_action}%"),
                            _InstModel.instance_id.like('i-%'),
                        ).first()
                        if _real:
                            logger.info(
                                f"[auto_rebalancer] Resolved placeholder {instance_id_for_action} "
                                f"→ real EC2 ID {_real.instance_id}"
                            )
                            instance_id_for_action = _real.instance_id
                        else:
                            logger.error(
                                f"[auto_rebalancer] Action {action.id}: instance_id "
                                f"{instance_id_for_action} is not a real EC2 ID and no real "
                                f"record found — marking action as failed"
                            )
                            action.status = 'failed'
                            action.error_message = f"Placeholder instance_id {instance_id_for_action} has no real EC2 record"
                            db.commit()
                            return

                    # ── PRE-COMPUTE: karpenter_installed needed before ASG decrement ──
                    # Must determine Karpenter status early so the ASG pre-step can be
                    # gated on it.  The full NodePool-existence check happens later (line ~645)
                    # but we need a quick flag now.
                    _karpenter_precheck = getattr(cluster, 'karpenter_mode', None) is not None
                    if _karpenter_precheck:
                        try:
                            from backend.models.agent_action import AgentAction as _AA_PC, AgentActionType as _AAT_PC, AgentActionStatus as _AAS_PC
                            _karpenter_precheck = db.query(_AA_PC).filter(
                                _AA_PC.cluster_id == action.cluster_id,
                                _AA_PC.action_type == _AAT_PC.INSTALL_KARPENTER,
                                _AA_PC.status == _AAS_PC.COMPLETED,
                            ).first() is not None
                        except Exception:
                            pass

                    # ── PRE-STEP: ASG detection via helper module ────────────────────
                    # Before launching the spot instance, detect whether the source OD
                    # node belongs to an ASG so Phase 2 can use the atomic
                    # terminate_instance_in_auto_scaling_group API.
                    #
                    # No ASG process suspension is performed here. The atomic API call
                    # in Phase 2 handles termination + desired capacity decrement in a
                    # single step, eliminating the need for suspend/resume.
                    #
                    # When karpenter_only_mode is True, skip ASG detection entirely —
                    # all nodes are assumed Karpenter-managed.
                    _asg_reduced = False
                    _asg_name_used = None
                    _karpenter_only = getattr(
                        getattr(cluster, 'optimization_settings', None),
                        'karpenter_only_mode', False
                    )
                    if _karpenter_only:
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name} is karpenter_only_mode "
                            f"— skipping ASG detection for {instance_id_for_action}"
                        )
                    elif instance_id_for_action and instance_id_for_action.startswith('i-'):
                        try:
                            from backend.utils.aws.asg import (
                                get_assumed_credentials,
                                get_asg_for_instance,
                                describe_auto_scaling_group,
                            )
                            _region = cluster.region or "ap-south-1"
                            _asg_creds = get_assumed_credentials(cluster, db)

                            _asg_name = get_asg_for_instance(
                                instance_id_for_action, _region, _asg_creds
                            )

                            if _asg_name:
                                _asg_name_used = _asg_name

                                # Store ASG name in metadata so Phase 2 knows to use
                                # terminate_instance_in_auto_scaling_group instead of
                                # direct EC2 terminate.
                                try:
                                    _early_meta = dict(action.action_metadata or {})
                                    _early_meta['asg_name_used'] = _asg_name
                                    action.action_metadata = _early_meta
                                    db.commit()
                                    logger.debug(
                                        f"[auto_rebalancer] ASG name '{_asg_name}' persisted to DB "
                                        f"for action {action.id} (cluster {action.cluster_id})"
                                    )
                                except Exception as _asg_commit_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Failed to persist ASG name "
                                        f"to DB for action {action.id}: {_asg_commit_err}"
                                    )

                                # Store current ASG config in metadata so Phase 2
                                # can log the baseline for reference.
                                try:
                                    _asg_info = describe_auto_scaling_group(
                                        _asg_name, _region, _asg_creds
                                    )
                                    if _asg_info:
                                        metadata.setdefault('asg_desired_at_start',
                                                            _asg_info["DesiredCapacity"])
                                        metadata.setdefault('asg_min_at_start',
                                                            _asg_info["MinSize"])
                                except Exception:
                                    pass
                            else:
                                logger.info(
                                    f"[auto_rebalancer] Instance {instance_id_for_action} not in any ASG "
                                    f"(may be Karpenter-managed) — skipping ASG handling"
                                )
                        except Exception as _asg_err:
                            logger.warning(
                                f"[auto_rebalancer] ASG pre-step failed for "
                                f"{instance_id_for_action}: {_asg_err} — continuing anyway"
                            )

                    # ── 2-PHASE PROVISION-AND-WAIT ─────────────────────────────────────
                    # Phase 1: Update Karpenter NodePool directly via K8s API to add
                    #          target instance types. Karpenter provisions a new spot node.
                    #          Action resolution (below) waits for spot to be Ready.
                    # Phase 2: Once spot node is Ready, action resolution creates
                    #          CORDON → DRAIN → TERMINATE.
                    #
                    # This prevents the blast-radius problem where we drain a node
                    # BEFORE confirming a replacement exists.

                    # ── USE PRE-COMPUTED RANKED ALTERNATIVES ──────────────────
                    # The per-node alternative list is the final list after all
                    # filter/compatibility/dry-run checks. Use it directly for
                    # launching instead of re-ranking every time.
                    _pre_ranked = metadata.get('ranked_alternatives', [])
                    if _pre_ranked and isinstance(_pre_ranked, list) and len(_pre_ranked) > 0:
                        # Use the pre-computed list from action creation.
                        # Source type already excluded at creation time.
                        ml_instance_types = list(_pre_ranked)[:8]
                        # Prepend target if it's a legitimate different type
                        if target_instance_type and target_instance_type != source_instance_type:
                            ml_instance_types = list(dict.fromkeys(
                                [target_instance_type] + ml_instance_types
                            ))
                        logger.info(
                            f"[auto_rebalancer] Using pre-computed ranked_alternatives: "
                            f"{ml_instance_types[:4]} (from action metadata)"
                        )
                    else:
                        # Fallback: old actions without ranked_alternatives — re-rank
                        logger.info(
                            f"[auto_rebalancer] No ranked_alternatives in metadata — "
                            f"falling back to re-ranking for action {action.id}"
                        )
                        # Fallback init
                        if target_instance_type and target_instance_type != source_instance_type:
                            ml_instance_types = [target_instance_type]
                        else:
                            ml_instance_types = [target_instance_type] if target_instance_type else ["t3.medium"]
                        try:
                            import re as _re_arch_rb
                            _src_fam_rb = source_instance_type.split('.')[0]
                            _src_arch_rb = 'arm64' if (
                                bool(_re_arch_rb.search(r'\dg', _src_fam_rb)) or _src_fam_rb == 'a1'
                            ) else 'amd64'
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            from backend.core.redis_client import get_redis_client as _grc_ml
                            _specs_rb = _INSTANCE_VCPU_MEM.get(source_instance_type, (2, 8))
                            _od_price_rb = 0.0
                            try:
                                _pricing_region_rb = cluster.region or 'ap-south-1'
                                _od_redis_rb = _grc_ml()
                                for _od_fmt in [f"pricing:od:{_pricing_region_rb}:{source_instance_type}",
                                                f"od_price:{_pricing_region_rb}:{source_instance_type}",
                                                f"ondemand_price:{_pricing_region_rb}:{source_instance_type}"]:
                                    _od_val = _od_redis_rb.get(_od_fmt)
                                    if _od_val:
                                        _od_price_rb = float(_od_val.decode() if isinstance(_od_val, bytes) else _od_val)
                                        break
                            except Exception:
                                pass
                            _ranked_ml = PoolRankingService(db, _grc_ml()).rank_pools_for_node(
                                node_info={
                                    'instance_type': source_instance_type,
                                    'az': target_az or '',
                                    'od_price': _od_price_rb,
                                    'resource_profile': {
                                        'min_vcpu_required': _specs_rb[0],
                                        'min_memory_required': float(_specs_rb[1]),
                                        'architecture': _src_arch_rb,
                                    },
                                },
                                cluster_id=action.cluster_id,
                                region=cluster.region or 'ap-south-1',
                                include_dynamic_filters=True,
                            )
                            if _ranked_ml:
                                _ranked_only = [p['instance_type'] for p in _ranked_ml]
                                if target_instance_type and target_instance_type != source_instance_type:
                                    _candidate_types = list(dict.fromkeys(
                                        [target_instance_type] + _ranked_only
                                    ))
                                else:
                                    _candidate_types = list(dict.fromkeys(_ranked_only))
                                _candidate_types = [t for t in _candidate_types if t != source_instance_type]
                                if _candidate_types:
                                    ml_instance_types = _candidate_types[:8]
                                logger.info(
                                    f"[auto_rebalancer] Fallback re-ranked ml_instance_types: "
                                    f"{ml_instance_types[:4]}"
                                )
                        except Exception:
                            pass

                    # ── NO-JOIN BLOCK FILTER (always applied — capacity is ephemeral) ──
                    try:
                        from backend.core.redis_client import get_redis_client as _grc_blk
                        _blk_redis = _grc_blk()
                        _pre_block = len(ml_instance_types)
                        ml_instance_types = [
                            t for t in ml_instance_types
                            if not _blk_redis.get(f"spot:launch_blocked:{action.cluster_id}:{t}:{target_az}")
                        ]
                        if _pre_block != len(ml_instance_types):
                            logger.info(
                                f"[auto_rebalancer] No-join block removed {_pre_block - len(ml_instance_types)} "
                                f"types — {len(ml_instance_types)} remaining"
                            )
                    except Exception:
                        pass
                    if not ml_instance_types:
                        logger.info(
                            f"[auto_rebalancer] All candidate pools blocked — deferring "
                            f"action {action.id} to next cycle"
                        )
                        action.status = 'deferred'
                        action.error_message = (
                            f"All candidate spot pools for {target_az} are currently blocked "
                            f"(no-join timeout). Will retry next cycle."
                        )
                        db.commit()
                        return

                    logger.info(
                        f"[auto_rebalancer] Exec ml_instance_types (final): "
                        f"{ml_instance_types[:4]}"
                    )

                    # Determine required architectures from WorkloadInspector cache
                    _arch_values = ["amd64", "arm64"]  # default: allow both
                    try:
                        import json as _json_arch
                        from backend.core.redis_client import get_redis_client as _grc_arch
                        _arch_redis = _grc_arch()
                        _arch_raw = _arch_redis.get(f"spot:node_arch_constraints:{cluster.id}")
                        if _arch_raw:
                            _arch_map = _json_arch.loads(_arch_raw)
                            _node_archs = _arch_map.get(instance_id_for_action, [])
                            if _node_archs:
                                _arch_values = _node_archs
                    except Exception:
                        pass

                    # ── ARCHITECTURE FILTER ────────────────────────────────────────
                    # Karpenter NodePool must only include instance types matching the
                    # cluster's architecture. An amd64 NodePool cannot run ARM64 types
                    # (c6g, m6g, t4g, etc.) and vice-versa. Filter ml_instance_types
                    # to the source arch to prevent provisioning failures.
                    #
                    # Fix 2: Also respect the cluster's architecture_preference setting.
                    # If the cluster is configured for arm64-only or amd64-only, enforce
                    # that; otherwise fall back to source-node-based detection.
                    # Problem #10: Use API-backed arch detection with expanded fallback set
                    _ARM64_FAMILIES = {'t4g', 'c6g', 'c7g', 'c8g', 'm6g', 'm7g', 'm8g', 'r6g', 'r7g', 'r8g',
                                       'c6gn', 'c6gd', 'm6gd', 'r6gd', 'a1', 'hpc7g', 'x2gd', 'im4gn', 'is4gen'}
                    _arch_region = cluster.region or "ap-south-1"
                    _ec2 = None
                    try:
                        import boto3 as _b3_arch
                        from backend.utils.aws.asg import get_assumed_credentials as _gac_arch
                        _arch_creds = _gac_arch(cluster, db)
                        _ec2 = _b3_arch.client("ec2", region_name=_arch_region, **_arch_creds)
                    except Exception as _ec2_err:
                        logger.debug(f"[auto_rebalancer] EC2 client for arch detection failed: {_ec2_err}")
                    _source_arch = _get_instance_arch(_ec2, source_instance_type or '', _ARM64_FAMILIES, _arch_region)
                    _source_is_arm = (_source_arch == 'arm64')

                    # Load architecture_preference from ClusterOptimizationSettings
                    _arch_pref = 'both'
                    try:
                        _arch_opt = db.query(ClusterOptimizationSettings).filter(
                            ClusterOptimizationSettings.cluster_id == action.cluster_id
                        ).first()
                        if _arch_opt and getattr(_arch_opt, 'architecture_preference', None):
                            _arch_pref = _arch_opt.architecture_preference
                    except Exception:
                        pass

                    # Fix 4: Intersect with node template's allowed architectures
                    _template_archs = None
                    try:
                        from backend.models.node_template import ClusterTemplateMapping
                        _ctm = db.query(ClusterTemplateMapping).filter(
                            ClusterTemplateMapping.cluster_id == action.cluster_id,
                            ClusterTemplateMapping.is_default == True
                        ).first()
                        if _ctm and _ctm.version and _ctm.version.constraints_json:
                            _tc = _ctm.version.constraints_json
                            if isinstance(_tc, dict) and 'architecture' in _tc:
                                _template_archs = set(_tc['architecture'])
                    except Exception:
                        pass

                    # Determine effective architecture filter
                    if _arch_pref == 'arm64':
                        _want_arm = True
                        _want_both = False
                    elif _arch_pref == 'amd64':
                        _want_arm = False
                        _want_both = False
                    else:
                        # 'both' / 'auto' — check template, then allow both arches
                        _want_both = True
                        _want_arm = False  # unused when _want_both=True
                        if _template_archs:
                            _has_arm = bool(_template_archs & {'arm64'})
                            _has_amd = bool(_template_archs & {'amd64', 'x86_64'})
                            if _has_arm and not _has_amd:
                                _want_arm = True
                                _want_both = False
                            elif _has_amd and not _has_arm:
                                _want_arm = False
                                _want_both = False

                    _pre_filter_count = len(ml_instance_types)
                    if not _want_both:
                        if _want_arm:
                            ml_instance_types = [
                                t for t in ml_instance_types
                                if t.split('.')[0] in _ARM64_FAMILIES
                            ]
                        else:
                            ml_instance_types = [
                                t for t in ml_instance_types
                                if t.split('.')[0] not in _ARM64_FAMILIES
                            ]
                    if not ml_instance_types:
                        # Architecture filter removed all candidates — use source type
                        ml_instance_types = [source_instance_type or 't3.medium']
                    if len(ml_instance_types) != _pre_filter_count:
                        logger.info(
                            f"[auto_rebalancer] Filtered ml_instance_types by arch "
                            f"({'arm64' if _want_arm else 'amd64'}, pref={_arch_pref}): "
                            f"{_pre_filter_count} → {len(ml_instance_types)} types: "
                            f"{ml_instance_types[:5]}"
                        )

                    # ── PHASE 1: Provision spot node via Karpenter ─────────────
                    # Karpenter-only path: directly update the NodePool via K8s API
                    # to include the target instance type. Karpenter provisions the
                    # replacement node automatically. No direct EC2 launch.
                    #
                    # If Karpenter is not installed, the rebalancer skips this cluster.

                    _karpenter_installed = getattr(cluster, 'karpenter_mode', None) is not None

                    # Verify Karpenter is actually available.
                    # Accepts ANY of:
                    #   (a) a completed INSTALL_KARPENTER AgentAction, OR
                    #   (b) the Redis live-detection key set by detect_karpenter_in_cluster(), OR
                    #   (c) karpenter_mode is set AND an install action is in-flight
                    if _karpenter_installed:
                        try:
                            from backend.models.agent_action import AgentActionStatus as _AAS_P1
                            _install_completed = db.query(AgentAction).filter(
                                AgentAction.cluster_id == action.cluster_id,
                                AgentAction.action_type == AgentActionType.INSTALL_KARPENTER,
                                AgentAction.status == _AAS_P1.COMPLETED,
                            ).first()
                            if not _install_completed:
                                _redis_kp_key = f"spot:karpenter:installed:{action.cluster_id}"
                                _redis_kp_val = _redis.get(_redis_kp_key) if _redis else None
                                if not _redis_kp_val:
                                    _install_inflight = db.query(AgentAction).filter(
                                        AgentAction.cluster_id == action.cluster_id,
                                        AgentAction.action_type == AgentActionType.INSTALL_KARPENTER,
                                        AgentAction.status.in_([_AAS_P1.PICKED_UP, _AAS_P1.PENDING]),
                                    ).first()
                                    if not _install_inflight:
                                        _karpenter_installed = False
                        except Exception as _kp_check_err:
                            logger.warning(
                                f"[auto_rebalancer] Phase 1: NodePool pre-check failed "
                                f"({_kp_check_err}) — proceeding with Karpenter path"
                            )

                    if not _karpenter_installed:
                        logger.warning(
                            f"[auto_rebalancer] Karpenter not installed on cluster {cluster.name} "
                            f"(id={cluster.id}), cannot rebalance. Install Karpenter first."
                        )
                        action.status = 'failed'
                        action.error_message = "Karpenter not installed — install Karpenter before rebalancing"
                        db.commit()
                        return

                    # Validate capacity via dry-run before updating NodePool
                    try:
                        from backend.core.redis_client import get_redis_client as _grc_dr
                        from backend.utils.aws.dry_run import dry_run_pool as _dr_pool
                        _dr_redis = _grc_dr()
                        _verified_types = []
                        _dr_region = cluster.region or "ap-south-1"
                        _dr_max_checks = 5
                        _dr_api_calls = 0
                        for _lt in ml_instance_types:
                            _dr_key = f"dry_run:{_lt}:{target_az}"
                            _dr_cached = _dr_redis.get(_dr_key)
                            if _dr_cached:
                                _dr_val = _dr_cached.decode() if isinstance(_dr_cached, bytes) else _dr_cached
                                if _dr_val == "fail":
                                    continue
                                _verified_types.append(_lt)
                            else:
                                if _dr_api_calls >= _dr_max_checks:
                                    _verified_types.append(_lt)
                                    continue
                                _dr_api_calls += 1
                                if _dr_pool(region=_dr_region, instance_type=_lt, az=target_az, redis=_dr_redis):
                                    _verified_types.append(_lt)
                        if _verified_types:
                            ml_instance_types = _verified_types
                        else:
                            action.status = 'failed'
                            action.error_message = f"Dry run: no capacity in {target_az} for any of {ml_instance_types[:3]}"
                            db.commit()
                            return
                    except Exception as _dr_err:
                        logger.warning(f"[auto_rebalancer] Dry run pre-check failed ({_dr_err}) — proceeding")

                    # Update Karpenter NodePool directly via K8s API
                    _nodepool_updated = False
                    try:
                        from backend.services.karpenter_service import KarpenterService
                        _karp_svc = KarpenterService(db, _redis)
                        for _kp_itype in ml_instance_types[:8]:
                            _kp_result = _karp_svc.add_allowed_instance_type(
                                cluster_id=action.cluster_id,
                                instance_type=_kp_itype,
                            )
                            if _kp_result:
                                _nodepool_updated = True
                                logger.info(
                                    f"[auto_rebalancer] Phase 1: Updated NodePool with {_kp_itype} "
                                    f"for cluster {cluster.name}"
                                )
                                break
                            else:
                                logger.warning(
                                    f"[auto_rebalancer] Phase 1: Failed to add {_kp_itype} to NodePool, "
                                    f"trying next candidate"
                                )
                    except Exception as _kp_err:
                        logger.error(f"[auto_rebalancer] Phase 1: NodePool update failed: {_kp_err}")

                    if not _nodepool_updated:
                        action.status = 'failed'
                        action.error_message = (
                            f"Failed to update Karpenter NodePool with any of {ml_instance_types[:3]}"
                        )
                        db.commit()
                        return

                    # Store metadata for Phase 2 tracking
                    _meta_update_p1 = dict(action.action_metadata or {})
                    _meta_update_p1['karpenter_nodepool_updated'] = True
                    _meta_update_p1['karpenter_target_types'] = ml_instance_types[:8]
                    _meta_update_p1['phase1_completed_at'] = datetime.utcnow().isoformat()
                    _meta_update_p1['phase2_params'] = {
                        'instance_id': instance_id_for_action,
                        'instance_type': source_instance_type,
                        'az': target_az or source_az or '',
                    }
                    action.action_metadata = _meta_update_p1
                    action.current_state = 'WAITING_FOR_KARPENTER'

                    logger.info(
                        f"[auto_rebalancer] Phase 1 (Karpenter): NodePool updated with "
                        f"types {ml_instance_types[:3]} — awaiting Karpenter to provision spot node. "
                        f"Source: {source_instance_type}:{source_az}"
                    )

                    # Set 24h cooldown on this instance
                    if instance_id_for_action:
                        try:
                            _cooldown_key = f"spot:rebalanced:instance:{instance_id_for_action}"
                            _redis.setex(_cooldown_key, 86400, "1")
                        except Exception as _cd_err:
                            logger.warning(f"[auto_rebalancer] Failed to set instance cooldown: {_cd_err}")

            except RuntimeError as lock_err:
                logger.warning(f"[auto_rebalancer] Action {action.id} deferred: lock contention — {lock_err}")
                action.status = 'deferred'
                action.error_message = f"Lock contention: {lock_err}"
                db.commit()
                return

            # Mark as waiting_agent — actual completion tracked in Step 0 of main task loop
            # when all 4 associated AgentActions reach COMPLETED/FAILED status.
            action.status = 'waiting_agent'
            action.nodes_affected = 1
            # Issue 4 fix: count real pods from pod_metrics instead of hardcoded 3.
            # Phase 2 hasn't run yet so this is a pre-drain estimate; updated to 0 if no data.
            try:
                from backend.models.pod_metric import PodMetric
                _target_node_inst = db.query(Instance).filter(
                    Instance.instance_id == instance_id_for_action
                ).first()
                _target_node_name = _target_node_inst.node_name if _target_node_inst else None
                if _target_node_name:
                    _recent_cutoff = datetime.utcnow() - timedelta(minutes=10)
                    action.pods_migrated = db.query(PodMetric.pod_name).filter(
                        PodMetric.node_name == _target_node_name,
                        PodMetric.timestamp >= _recent_cutoff,
                    ).distinct().count()
                else:
                    action.pods_migrated = 0
            except Exception:
                action.pods_migrated = 0
            # Persist ASG name for Phase 2 atomic terminate
            _meta_update = dict(action.action_metadata or {})
            if _asg_name_used:
                _meta_update['asg_name_used'] = _asg_name_used
            # Record spot baseline BEFORE Phase 1 launched.
            # Phase 2 trigger uses this to detect that a NEW spot node joined —
            # not just any pre-existing spot instance from a concurrent rebalance.
            try:
                _spot_baseline = db.query(Instance).filter(
                    Instance.cluster_id == action.cluster_id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state == 'running',
                ).count()
                _meta_update['spot_baseline_count'] = _spot_baseline
            except Exception:
                _meta_update['spot_baseline_count'] = 0
            action.action_metadata = _meta_update
            db.commit()

            logger.info(
                f"[auto_rebalancer] Action {action.id} — Karpenter NodePool updated — "
                f"status=waiting_agent until Karpenter provisions spot node, then CORDON→DRAIN→TERMINATE"
            )

        except Exception as e:
            logger.error(f"Failed to execute rebalancing action {action.id}: {e}")
            action.status = 'failed'
            action.completed_at = datetime.utcnow()
            action.duration_seconds = int((action.completed_at - action.started_at).total_seconds()) if action.started_at else 0
            action.error_message = str(e)
            # Release semaphore on failure — prevent stale counter from blocking future actions
            try:
                from backend.core.redis_client import get_redis_client as _grc_sem_fail
                _sem_fail_redis = _grc_sem_fail()
                _sem_fail_key = f"rebalance:active_count:{action.cluster_id}"
                _sem_new = _sem_fail_redis.decr(_sem_fail_key)
                if _sem_new < 0:
                    _sem_fail_redis.set(_sem_fail_key, 0, ex=300)
            except Exception:
                pass
            # Problem #3/#9: On generic failure, terminate any orphaned replacement spot
            _fail_meta = dict(action.action_metadata or {})
            _fail_spot_id = _fail_meta.get('replacement_spot_instance_id')
            if _fail_spot_id:
                try:
                    _do_rollback_terminate_orphan_spot(action, _fail_meta, db)
                    logger.warning(
                        f"[auto_rebalancer] Generic failure — terminated orphan spot "
                        f"{_fail_spot_id} for action {action.id}"
                    )
                except Exception as _fail_cleanup_err:
                    logger.error(
                        f"[auto_rebalancer] Failed to cleanup orphan spot "
                        f"{_fail_spot_id}: {_fail_cleanup_err}"
                    )
                # Clear replacement_spot_instance_id so action can be retried
                _fail_meta.pop('replacement_spot_instance_id', None)
                action.action_metadata = _fail_meta
            db.commit()
        finally:
            # Stop the per-cluster lock heartbeat thread
            try:
                _lock_hb_stop.set()
            except Exception:
                pass
            # Release the rebalance lock — verify ownership before deleting
            if _lock_key_release and _redis_release:
                try:
                    _cur_val = _redis_release.get(_lock_key_release)
                    _cur_str = _cur_val.decode() if isinstance(_cur_val, bytes) else str(_cur_val or "")
                    if _cur_str == str(action.id):
                        _redis_release.delete(_lock_key_release)
                except Exception:
                    pass


def trigger_graceful_rebalancing(
    cluster_id: str,
    source_pool: str,
    target_pool: str,
    reason: str = "proactive_optimization",
    instance_id: str = None,
) -> Dict:
    """
    Triggers graceful rebalancing (10 minutes) for a cluster.

    This is called by:
    - Scheduled optimization checks
    - Manual user action via UI
    - Pool risk score increase

    Args:
        cluster_id: Cluster to rebalance
        source_pool: Current pool (e.g., 'm5.xlarge:aps1-az1')
        target_pool: Target safer/cheaper pool
        reason: Reason for rebalancing

    Returns:
        Dict with rebalancing action details
    """
    db = next(get_db())

    try:
        # Create rebalancing action record
        rebalancing_action = RebalancingAction(
            cluster_id=cluster_id,
            trigger='graceful',
            source_pool=source_pool,
            target_pool=target_pool,
            source_instance_id=instance_id,
            status='in_progress',
            started_at=datetime.utcnow(),
            action_metadata={
                'reason': reason,
                'initiated_by': 'system',
                **({"instance_id": instance_id} if instance_id else {}),
            }
        )

        db.add(rebalancing_action)
        db.commit()

        logger.info(f"Graceful rebalancing triggered: {cluster_id} ({source_pool} → {target_pool})")

        return {
            'status': 'success',
            'action_id': rebalancing_action.id,
            'cluster_id': cluster_id,
            'source_pool': source_pool,
            'target_pool': target_pool,
            'trigger': 'graceful',
            'started_at': rebalancing_action.started_at.isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to trigger graceful rebalancing: {e}")
        db.rollback()
        return {
            'status': 'error',
            'error': str(e)
        }
    finally:
        db.close()


def _seed_instances_from_redis(db: Session, cluster) -> list:
    """
    When the `instances` table has no records for this cluster (agent-reported nodes
    haven't been persisted yet), seed synthetic Instance rows from Redis node telemetry
    so the auto-rebalancer has something to work with.

    Uses capacity data to infer instance type.  Synthetic instance_ids are derived from
    the node hostname's IP component (e.g. 'ip-192-168-14-254'), which fits VARCHAR(20).
    Lifecycle is assumed ON_DEMAND (the rebalancer will migrate them to spot).
    """
    from backend.core.redis_client import get_redis_client as _grc
    from backend.models.instance import Instance
    import ast as _ast
    import json as _json

    _TYPE_MAP = [
        (2, 0.5, "t3.nano"), (2, 1.0, "t3.micro"), (2, 2.0, "t3.small"),
        (2, 4.0, "t3.medium"), (2, 8.0, "t3.large"), (4, 16.0, "t3.xlarge"),
        (8, 32.0, "t3.2xlarge"),
        (2, 8.0, "m5.large"), (4, 16.0, "m5.xlarge"), (8, 32.0, "m5.2xlarge"),
        (2, 4.0, "c5.large"), (4, 8.0, "c5.xlarge"),
        (2, 16.0, "r5.large"), (4, 32.0, "r5.xlarge"),
    ]

    def _infer_type(vcpu, mem_gb):
        best, best_dist = "t3.medium", 1e9
        for v, m, name in _TYPE_MAP:
            dist = abs(v - vcpu) * 8 + abs(m - mem_gb)
            if dist < best_dist:
                best_dist, best = dist, name
        return best

    _redis = _grc()

    # Guard: if the cluster already has any running instances in the DB (even ip- placeholders),
    # don't create NEW synthetic instances. Discovery will eventually link ip- records to i- IDs.
    # Seeding is only for clusters with ZERO instance records.
    # Also: if ANY spot instances exist in the cluster (running OR terminated recently),
    # never seed with ON_DEMAND defaults — this would cause false OD detection and
    # trigger unnecessary spot launches, growing the cluster.
    try:
        _existing_count = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running',
        ).count()
        if _existing_count > 0:
            return []
    except Exception:
        pass

    # Secondary guard: if cluster has ANY spot instances (even recently terminated),
    # don't seed. A cluster with known spot history should not get fake OD seeds.
    try:
        _spot_exists = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.lifecycle == InstanceLifecycle.SPOT,
        ).first()
        if _spot_exists:
            logger.debug(
                f"[seed_redis] Cluster {cluster.id} has spot instance history — "
                f"skipping ON_DEMAND seed to prevent false rebalancing"
            )
            return []
    except Exception:
        pass

    _pattern = f"metrics:node:{cluster.id}:*"
    try:
        # Issue 13 fix: use scan_iter instead of keys() — avoids O(N) blocking scan
        _keys = list(_redis.scan_iter(_pattern))
    except Exception:
        return []

    seeded = []
    for _key in _keys:
        try:
            _raw = _redis.get(_key)
            if not _raw:
                continue
            _raw_str = _raw.decode('utf-8') if isinstance(_raw, bytes) else str(_raw)
            try:
                _data = _json.loads(_raw_str)
            except Exception:
                try:
                    _data = _ast.literal_eval(_raw_str)
                except Exception:
                    continue

            node_name = _data.get('node_name', '')
            # Extract ip-xxx-xxx-xxx-xxx from hostname (fits VARCHAR(20))
            _short_id = node_name.split('.')[0] if node_name else ''
            if not _short_id or len(_short_id) > 20:
                _short_id = node_name[:20]
            if not _short_id:
                continue

            # Skip if already exists in DB.
            # Do NOT re-add existing ip- placeholder records to the seeded list —
            # they may be stale (spot nodes whose EC2 'i-' ID was later discovered),
            # and targeting them for rebalancing causes launch failures because
            # 'ip-xxx' is not a valid EC2 instance ID.
            existing = db.query(Instance).filter(Instance.instance_id == _short_id).first()
            if existing:
                continue

            cpu_mc = _data.get('cpu_capacity_millicores', 2000)
            mem_bytes = _data.get('memory_capacity_bytes', 4026089472)
            vcpu = max(1, round(cpu_mc / 1000))
            mem_gb = round(mem_bytes / (1024 ** 3), 1)
            itype = _infer_type(vcpu, mem_gb)

            new_inst = Instance(
                cluster_id=cluster.id,
                instance_id=_short_id,
                instance_type=itype,
                lifecycle=InstanceLifecycle.ON_DEMAND,
                az=f"{cluster.region or 'ap-south-1'}a",
                price=0.0,  # real price populated by pricing_collector worker
                cpu_util=round(
                    _data.get('cpu_usage_millicores', 0) / max(cpu_mc, 1) * 100, 1
                ),
                memory_util=round(
                    _data.get('memory_usage_bytes', 0) / max(mem_bytes, 1) * 100, 1
                ),
                state='running',
                status='READY',
                architecture='amd64',
            )
            db.add(new_inst)
            seeded.append(new_inst)
            logger.info(
                f"[auto_rebalancer] Seeded instance {_short_id} ({itype}) "
                f"for cluster {cluster.name} from Redis telemetry"
            )
        except Exception as _e:
            logger.warning(f"[auto_rebalancer] Failed to seed node from Redis key {_key}: {_e}")

    if seeded:
        try:
            db.commit()
        except Exception as _ce:
            db.rollback()
            logger.warning(f"[auto_rebalancer] Failed to commit seeded instances: {_ce}")
            seeded = []

    return seeded


# ── Rollback helpers ─────────────────────────────────────────────────────────
# Shared by CORDON failure, DRAIN failure, and EC2-terminate failure paths.

def _do_rollback_uncordon_and_terminate(wa, wa_meta, db):
    """
    Full rollback after a pre-drain failure (CORDON failed or similar):
      1. Queue UNCORDON_NODE so the old OD node is schedulable again.
      2. Terminate the orphan spot instance that was launched for this cycle.

    No ASG resume needed — we no longer suspend ASG processes during Phase 1.
    Never raises — all steps wrapped in try/except.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus

    # 1. Queue UNCORDON_NODE
    _rb_node = wa_meta.get('target_node_name') or wa_meta.get('node_name')
    if _rb_node:
        try:
            _unc = AgentAction(
                cluster_id=wa.cluster_id,
                action_type=AgentActionType.UNCORDON_NODE,
                status=AgentActionStatus.PENDING,
                payload={"node_name": _rb_node},
                action_metadata={"rollback_for_action_id": str(wa.id)},
            )
            db.add(_unc)
            db.commit()
            logger.info(f"[rollback] Queued UNCORDON_NODE for {_rb_node} (action {wa.id})")
        except Exception as _e:
            logger.error(f"[rollback] UNCORDON_NODE queue failed: {_e}")

    # 3. Terminate orphan spot
    _do_rollback_terminate_orphan_spot(wa, wa_meta, db)


def _do_rollback_terminate_orphan_spot(wa, wa_meta, db):
    """
    Terminate the replacement spot instance launched for a failed rebalancing cycle.
    Prefers wa_meta['replacement_spot_instance_id'] (stored at Phase 1 launch);
    falls back to timestamp query (latest SPOT created after action start).

    Never raises — wrapped in try/except.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    try:
        _rb_cluster = db.query(Cluster).filter(Cluster.id == wa.cluster_id).first()
        if not _rb_cluster:
            return

        # Prefer explicit instance_id stored at launch time
        _orphan_id = wa_meta.get('replacement_spot_instance_id')
        _orphan_inst = None

        if _orphan_id:
            _orphan_inst = db.query(Instance).filter(
                Instance.cluster_id == _rb_cluster.id,
                Instance.instance_id == _orphan_id,
            ).first()

        if not _orphan_inst:
            # Fallback: newest SPOT created since this action started
            _orphan_inst = (
                db.query(Instance)
                .filter(
                    Instance.cluster_id == _rb_cluster.id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.created_at >= wa.created_at,
                )
                .order_by(Instance.created_at.desc())
                .first()
            )

        # Resolve the EC2 instance ID to terminate (DB record OR direct from metadata)
        _terminate_id = None
        if _orphan_inst and _orphan_inst.instance_id:
            _terminate_id = _orphan_inst.instance_id
        elif _orphan_id and _orphan_id.startswith('i-'):
            # DB record doesn't exist yet (discovery hasn't synced), but we know
            # the exact instance_id from Phase 1 metadata → terminate directly.
            _terminate_id = _orphan_id
            logger.info(
                f"[rollback] Orphan {_orphan_id} not in DB yet (discovery lag) "
                f"— terminating directly via EC2 API (action {wa.id})"
            )

        if _terminate_id:
            from backend.utils.aws.asg import get_assumed_credentials as _gac_spot
            import boto3 as _b3spot
            _spot_creds = _gac_spot(_rb_cluster, db)
            _spot_ec2 = _b3spot.Session(
                aws_access_key_id=_spot_creds.get('aws_access_key_id') or _spot_creds.get('AccessKeyId'),
                aws_secret_access_key=_spot_creds.get('aws_secret_access_key') or _spot_creds.get('SecretAccessKey'),
                aws_session_token=_spot_creds.get('aws_session_token') or _spot_creds.get('SessionToken'),
            ).client("ec2", region_name=_rb_cluster.region or "ap-south-1")
            _spot_ec2.terminate_instances(InstanceIds=[_terminate_id])
            logger.info(
                f"[rollback] Terminated orphan spot {_terminate_id} "
                f"(action {wa.id})"
            )
            wa_meta['rollback_terminated_spot'] = _terminate_id
            # Problem #9: Clear replacement_spot_instance_id so the action
            # doesn't block new attempts for 45 minutes via stale metadata.
            wa_meta.pop('replacement_spot_instance_id', None)
            wa.action_metadata = wa_meta
            # Clean up associated Redis keys for the terminated spot
            try:
                from backend.core.redis_client import get_redis_client as _grc_rb
                _rb_redis = _grc_rb()
                _rb_redis.delete(f"spot:asserted_spot:{_terminate_id}")
                # Z12 fix: Don't delete node_joined if the spot instance is < 3 min old.
                # created_at is the DB insert time (not EC2 launch), so 180s covers
                # the lag between EC2 launch and actual K8s join.
                _skip_node_joined_delete = False
                if _orphan_inst and hasattr(_orphan_inst, 'created_at') and _orphan_inst.created_at:
                    _spot_age_s = (datetime.utcnow() - _orphan_inst.created_at).total_seconds()
                    if _spot_age_s < 180:
                        logger.info(
                            f"[rollback] Skipping node_joined deletion for {_terminate_id} "
                            f"— launched {_spot_age_s:.0f}s ago (< 180s)"
                        )
                        _skip_node_joined_delete = True
                if not _skip_node_joined_delete:
                    _rb_redis.delete(f"node_joined:{_terminate_id}")
                _rb_redis.delete(f"spot:node_active_action:{_terminate_id}")
            except Exception:
                pass
            db.commit()
        else:
            logger.info(f"[rollback] No orphan spot instance found for action {wa.id}")
    except Exception as _e:
        logger.warning(f"[rollback] Orphan spot terminate failed (action {wa.id}): {_e}")


# ── Issue 6: Skip streak helpers ─────────────────────────────────────────────
# Track consecutive skips per cluster within a 5-minute window. Emits a warning
# if a cluster is skipped 20+ times (≈5 min) to detect stalled system states.

def _record_skip(redis, cluster_id: str, reason: str):
    """Increment skip streak counter and emit warning at thresholds."""
    try:
        skip_key = f'spot:skip_streak:{cluster_id}'
        skip_streak = int(redis.incr(skip_key))
        redis.expire(skip_key, 300)
        if skip_streak == 20:
            logger.warning(
                'Cluster %s has been skipped %d times in 5 min (latest reason: %s). '
                'System may be stalled.',
                cluster_id, skip_streak, reason
            )
        elif skip_streak > 20 and skip_streak % 20 == 0:
            logger.warning(
                'Cluster %s still skipping — %d total skips (reason: %s)',
                cluster_id, skip_streak, reason
            )
    except Exception:
        pass


def _record_active(redis, cluster_id: str):
    """Clear skip streak when a cluster proceeds to actual evaluation."""
    try:
        redis.delete(f'spot:skip_streak:{cluster_id}')
    except Exception:
        pass


# Celery task registration
from backend.workers.app import app

@app.task(name='workers.auto_rebalancer')
def execute_rebalancing():
    """Celery task entry point for auto-rebalancing."""
    logger.info("Auto-rebalancer task started")

    db = next(get_db())

    _heartbeat_lock = None
    _hb_stop_event = None
    try:
        from backend.core.redis_client import get_redis_client as _get_redis_outer
        _redis = _get_redis_outer()
        if _redis:
            # Use HeartbeatLock so the lock TTL is extended while the task runs.
            # Previously: fixed 300s NX lock. If task ran >5 min, a second worker
            # could start simultaneously (lock expired silently → race condition).
            # Fix: heartbeat thread renews TTL every 150s (300/2). If Redis drops,
            # stop_event is set and the main loop aborts cleanly.
            import threading as _threading_reb
            from backend.services.distributed_locks import HeartbeatLock as _HBLock
            _hb_stop_event = _threading_reb.Event()
            _heartbeat_lock = _HBLock(
                _redis,
                "lock:workers.auto_rebalancer",
                timeout=300,
                stop_event=_hb_stop_event,
            )
            if not _heartbeat_lock.acquire(blocking=False):
                logger.info("Auto-rebalancer already running, skipping this scheduled run.")
                db.close()
                return
    except Exception:
        _redis = None
        _heartbeat_lock = None
        _hb_stop_event = None

    try:
        # ── STALE ACTION EXPIRY ───────────────────────────────────────────────
        # Actions stuck in in_progress or waiting_agent for >45 min are orphaned:
        # spot node never joined K8s, agent restarted, EC2 launch failed silently,
        # or drain timed out.  Expire them so they don't block new migrations
        # forever and so the history card shows an honest 'failed' entry instead
        # of a ghost 'In Progress' badge.
        #
        # Problem #19: Per-state timeouts — check action_heartbeat for long-running
        # states. If heartbeat stopped for >2 min, fail the action early.
        _STATE_TIMEOUTS_MIN = {
            'in_progress': 45,
            'waiting_agent': 10,  # Fast fallback: EC2 check + re-queue runs in <1 rebalancer cycle
            'waiting_for_spot_node': 28,  # Must be ≤ spot_join_timeout_minutes default (30 min)
            'cordoning_node': 10,
            'draining_pods': 20,
            'verifying_pod_readiness': 20,
            'terminating_source': 10,
        }
        _stale_cutoff = datetime.utcnow() - timedelta(minutes=45)
        _stale_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
            RebalancingAction.started_at < _stale_cutoff,
        ).all()
        # Also check per-state timeouts for actions within the 45-min window
        _recent_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
            RebalancingAction.started_at >= _stale_cutoff,
        ).all()
        for _ra_check in _recent_actions:
            _ra_meta = dict(_ra_check.action_metadata or {})
            _cur_step = _ra_meta.get('current_step', '')
            _step_timeout = _STATE_TIMEOUTS_MIN.get(_cur_step, 45)
            # Check action heartbeat — if worker is alive it updates this every ~15s (rebalancer cycle)
            _hb_key = f"action_heartbeat:{_ra_check.id}"
            try:
                _hb_val = _redis.get(_hb_key)
                if _hb_val:
                    _hb_ts = float(_hb_val.decode() if isinstance(_hb_val, bytes) else _hb_val)
                    _hb_age = datetime.utcnow().timestamp() - _hb_ts
                    if _hb_age > 120:  # heartbeat stopped >2 min ago
                        logger.warning(
                            f"[auto_rebalancer] Action {_ra_check.id} heartbeat stopped "
                            f"{_hb_age:.0f}s ago in step '{_cur_step}' — marking stale"
                        )
                        _stale_actions.append(_ra_check)
                        continue
            except Exception:
                pass
            # Check per-state timeout
            _step_start = _ra_meta.get(f'step_entered_{_cur_step}')
            if _step_start:
                try:
                    _step_elapsed = (datetime.utcnow() - datetime.fromisoformat(_step_start)).total_seconds()
                    if _step_elapsed > _step_timeout * 60:
                        logger.warning(
                            f"[auto_rebalancer] Action {_ra_check.id} exceeded per-state timeout: "
                            f"step='{_cur_step}' elapsed={_step_elapsed:.0f}s limit={_step_timeout * 60}s"
                        )
                        _stale_actions.append(_ra_check)
                except (ValueError, TypeError):
                    pass
        for _stale in _stale_actions:
            _stuck_min = int((datetime.utcnow() - _stale.started_at).total_seconds() / 60) if _stale.started_at else 0
            _stale_prev_status = _stale.status
            _stale.status = 'failed'
            _stale.error_message = (
                f"Action timed out after {_stuck_min} min in state '{_stale_prev_status}'. "
                f"Possible causes: spot node never joined (InsufficientInstanceCapacity), "
                f"K8s agent disconnected, EC2 launch failed silently, or drain blocked by PDB. "
                f"Rebalancer will retry on next eligible cycle."
            )
            _stale.completed_at = datetime.utcnow()
            if _stale.started_at:
                _stale.duration_seconds = int(
                    (datetime.utcnow() - _stale.started_at).total_seconds()
                )
            logger.warning(
                f"[auto_rebalancer] Expired stale action {_stale.id} "
                f"({_stale.source_pool} → {_stale.target_pool}) — "
                f"stuck {_stuck_min} min in status that was '{_stale_prev_status}' "
                f"(started {_stale.started_at})"
            )
            # P-C2 fix: terminate orphan spot EC2 if Phase 1 already launched one.
            # action_metadata['replacement_spot_instance_id'] is set at Phase 1 launch time.
            # If the action timed out (agent crash, network split), the spot EC2 is still
            # running and must be terminated to prevent cluster growing by 1 permanently.
            _stale_meta = dict(_stale.action_metadata or {})
            _orphan_ec2 = _stale_meta.get('replacement_spot_instance_id')
            if _orphan_ec2:
                try:
                    _do_rollback_terminate_orphan_spot(_stale, _stale_meta, db)
                    logger.warning(
                        f"[auto_rebalancer] Stale action {_stale.id}: terminated orphan spot "
                        f"EC2 {_orphan_ec2} during stale expiry cleanup"
                    )
                except Exception as _stale_rb_err:
                    logger.error(
                        f"[auto_rebalancer] Stale action {_stale.id}: orphan spot EC2 "
                        f"{_orphan_ec2} termination failed: {_stale_rb_err}"
                    )
            # Z6 fix: Clear spot:node_active_action for the source instance so the
            # node is not permanently excluded from future rebalancing attempts.
            _stale_source_id = _stale_meta.get('instance_id', '')
            if _stale_source_id and _redis:
                try:
                    _redis.delete(f"spot:node_active_action:{_stale_source_id}")
                except Exception:
                    pass
        if _stale_actions:
            db.commit()
            logger.warning(
                f"[auto_rebalancer] Expired {len(_stale_actions)} stale RebalancingAction(s) "
                f"that exceeded the 45-min timeout."
            )

        # Step 0: Resolve waiting_agent actions whose AgentActions have all finished.
        # An action stays 'waiting_agent' until PATCH_NODEPOOL → CORDON → DRAIN → TERMINATE
        # all complete on the agent. This prevents UI showing "completed" prematurely.
        from backend.models.agent_action import AgentAction as _AA0, AgentActionStatus as _AAS0
        waiting_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status == 'waiting_agent'
        ).all()
        for _wa in waiting_actions:
            try:
                # Problem #19: Update action heartbeat so stale monitor knows we're alive
                try:
                    _redis.setex(f"action_heartbeat:{_wa.id}", 120, str(datetime.utcnow().timestamp()))
                except Exception:
                    pass
                _still_pending = db.query(_AA0).filter(
                    _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                    _AA0.status.in_([_AAS0.PENDING, _AAS0.PICKED_UP])
                ).count()
                if _still_pending > 0:
                    # ── STEP TRACKING: record step timestamps while agent is still working ──
                    _wa_meta_live = dict(_wa.action_metadata or {})
                    from backend.models.agent_action import AgentActionType as _AAT0
                    # step_1 (Karpenter NodePool update) is done directly in Phase 1,
                    # not via agent action — timestamp stored in action_metadata.
                    if 'karpenter_nodepool_updated' in _wa_meta_live and 'step_1_spot_provisioning' not in _wa_meta_live:
                        _wa_meta_live['step_1_spot_provisioning'] = _wa_meta_live.get('phase1_completed_at', _wa.started_at.isoformat() if _wa.started_at else datetime.utcnow().isoformat())
                    for _sname, _stype in [
                        ('step_2_cordon', _AAT0.CORDON_NODE),
                        ('step_3_draining_pods', _AAT0.DRAIN_NODE),
                    ]:
                        if _sname not in _wa_meta_live:
                            _sa = db.query(_AA0).filter(
                                _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                                _AA0.action_type == _stype,
                                _AA0.status == _AAS0.COMPLETED,
                            ).first()
                            if _sa and _sa.completed_at:
                                _wa_meta_live[_sname] = _sa.completed_at.isoformat()
                    # Determine current_step from what's done so far
                    if 'step_3_draining_pods' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'waiting_for_spot_node'
                    elif 'step_2_cordon' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'draining_pods'
                    elif 'step_1_spot_provisioning' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'cordoning_node'
                    else:
                        _wa_meta_live['current_step'] = 'provisioning_spot_pool'
                    _wa.action_metadata = _wa_meta_live
                    db.commit()
                    continue  # Agent still working — leave as waiting_agent

                _failed = db.query(_AA0).filter(
                    _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                    _AA0.status == _AAS0.FAILED
                ).count()

                _wa_meta = dict(_wa.action_metadata or {})
                _wa_instance_id = _wa_meta.get("instance_id", "") or (_wa.source_instance_id or "")

                # ── Record step timestamps for completed agent actions ────────
                from backend.models.agent_action import AgentActionType as _AAT0
                # step_1 (Karpenter NodePool update) is done directly — not an agent action.
                if 'karpenter_nodepool_updated' in _wa_meta and 'step_1_spot_provisioning' not in _wa_meta:
                    _wa_meta['step_1_spot_provisioning'] = _wa_meta.get('phase1_completed_at', _wa.started_at.isoformat() if _wa.started_at else datetime.utcnow().isoformat())
                for _sname, _stype in [
                    ('step_2_cordon', _AAT0.CORDON_NODE),
                    ('step_3_draining_pods', _AAT0.DRAIN_NODE),
                ]:
                    if _sname not in _wa_meta:
                        _sa = db.query(_AA0).filter(
                            _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                            _AA0.action_type == _stype,
                        ).first()
                        if _sa:
                            ts = (_sa.completed_at or _sa.created_at)
                            if ts:
                                _wa_meta[_sname] = ts.isoformat()

                # ── 2-PHASE: WAIT FOR SPOT NODE → CREATE PHASE 2 ACTIONS ──────
                # After Phase 1 completes (NodePool update via K8s API), wait for a
                # spot node to be Ready BEFORE creating CORDON/DRAIN/TERMINATE (Phase 2).
                # This prevents draining when no replacement exists.
                # NOTE: This block is intentionally OUTSIDE the 'for _sname, _stype' loop
                # above. Previously it was incorrectly indented inside the loop, causing
                # `continue` to only advance the inner loop instead of the outer `for _wa`
                # loop — all 3 iterations completed with `continue`, then execution fell
                # through to the EC2 terminate block, immediately killing the OD node
                # without waiting for the spot replacement to join.
                if _failed == 0:
                    _wa_cluster_obj = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                    # Load opt_settings once for this action's cluster (used for join timeout)
                    try:
                        from backend.models.cluster import ClusterOptimizationSettings as _COSS
                        _wa_opt = db.query(_COSS).filter(_COSS.cluster_id == _wa.cluster_id).first()
                    except Exception:
                        _wa_opt = None
                    # Karpenter detection: Phase 1 now updates NodePool directly via K8s API
                    # and stores 'karpenter_nodepool_updated' in action_metadata. Use this stable
                    # metadata flag instead of querying for agent actions.
                    _wa_karpenter_active = bool(_wa_meta.get('karpenter_nodepool_updated'))

                    _spot_count = db.query(Instance).filter(
                        Instance.cluster_id == _wa.cluster_id,
                        Instance.lifecycle == InstanceLifecycle.SPOT,
                        Instance.state == 'running',
                    ).count()

                    # Issue #13 fix: ID-first Phase 2 gate — use pinned replacement_spot_instance_id
                    # when available, fall back to count comparison ONLY if no ID is recorded.
                    # This prevents count-based false triggers when concurrent actions add/remove
                    # spot nodes, changing the baseline independently of this action's replacement.
                    _spot_baseline = int(_wa_meta.get('spot_baseline_count', 0))
                    _new_spot_joined = False
                    _SPOT_STABILIZE_S = 90
                    _replacement_id_pinned = _wa_meta.get('replacement_spot_instance_id')
                    _newest_spot = None

                    if _replacement_id_pinned:
                        # Primary path: look up the SPECIFIC replacement instance by ID.
                        # Bypass count gate — count can be wrong when concurrent actions run.
                        _newest_spot = db.query(Instance).filter(
                            Instance.cluster_id == _wa.cluster_id,
                            Instance.lifecycle == InstanceLifecycle.SPOT,
                            Instance.state == 'running',
                            Instance.instance_id == _replacement_id_pinned[:20],
                        ).first()
                        if not _newest_spot:
                            # Problem #12: Proactive polling fallback — check if the instance
                            # has joined via node_joined Redis key or has a node_name in DB
                            # (agent heartbeat may have set it) even if state isn't 'running' yet.
                            _p12_inst = db.query(Instance).filter(
                                Instance.instance_id == _replacement_id_pinned[:20],
                            ).first()
                            _p12_joined = False
                            if _p12_inst and _p12_inst.node_name:
                                # Agent reported a node_name — consider it joined
                                _p12_joined = True
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: pinned replacement "
                                    f"{_replacement_id_pinned[:12]} has node_name={_p12_inst.node_name} "
                                    f"(state={_p12_inst.state}) — proactive join detection"
                                )
                                # Update state to running if needed
                                if _p12_inst.state != 'running':
                                    _p12_inst.state = 'running'
                                    db.commit()
                                _newest_spot = _p12_inst
                            if not _p12_joined:
                                try:
                                    _p12_nj_key = f"node_joined:{_replacement_id_pinned}"
                                    if _redis.exists(_p12_nj_key):
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: node_joined key exists "
                                            f"for {_replacement_id_pinned[:12]} — proactive join detection"
                                        )
                                        _p12_joined = True
                                        if _p12_inst:
                                            _newest_spot = _p12_inst
                                except Exception:
                                    pass
                            if not _p12_joined:
                                logger.debug(
                                    f"[auto_rebalancer] Action {_wa.id}: pinned replacement "
                                    f"{_replacement_id_pinned[:12]} not yet running — waiting"
                                )
                                continue
                    elif _spot_count > _spot_baseline:
                        # Fallback: count-based trigger (legacy path when Phase 1 did not pin an ID).
                        # Log a warning so we can track how often this happens.
                        logger.warning(
                            f"[auto_rebalancer] Action {_wa.id}: Phase 2 count-fallback "
                            f"(spot_count={_spot_count} > baseline={_spot_baseline}) — "
                            f"no replacement_spot_instance_id in metadata (Phase 1 may be old)"
                        )
                        _newest_spot = db.query(Instance).filter(
                            Instance.cluster_id == _wa.cluster_id,
                            Instance.lifecycle == InstanceLifecycle.SPOT,
                            Instance.state == 'running',
                        ).order_by(Instance.created_at.desc()).first()

                    if _newest_spot:
                        _spot_age_s = (
                            (datetime.utcnow() - _newest_spot.created_at).total_seconds()
                            if _newest_spot.created_at else 0
                        )
                        if _spot_age_s >= _SPOT_STABILIZE_S and _newest_spot.node_name:
                            # Safety gate: only proceed to Phase 2 (CORDON→DRAIN→TERMINATE) once
                            # the collector has confirmed the new spot node is Ready in K8s.
                            # status='READY' is set by the agent collector when K8s Ready condition
                            # is True. This prevents draining the old node when the new node is
                            # still initializing (Not-Ready) and cannot accept evicted pods.
                            _repl_status = getattr(_newest_spot, 'status', None) or 'READY'
                            if _repl_status not in ('READY', 'CALIBRATING'):
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: replacement "
                                    f"{_newest_spot.instance_id[:12]} node_name={_newest_spot.node_name} "
                                    f"status={_repl_status} — waiting for K8s Ready condition"
                                )
                                # Don't set _new_spot_joined — wait for collector to confirm Ready
                            else:
                                _new_spot_joined = True
                                # Pin replacement ID for rollback reliability
                                if _newest_spot.instance_id and not _wa_meta.get('replacement_spot_instance_id'):
                                    _wa_meta['replacement_spot_instance_id'] = _newest_spot.instance_id
                                    _wa.action_metadata = _wa_meta
                                # Pin node_name so it survives loop iterations
                                if _newest_spot.node_name and not _wa_meta.get('replacement_spot_node_name'):
                                    _wa_meta['replacement_spot_node_name'] = _newest_spot.node_name
                                    _wa.action_metadata = _wa_meta
                        elif _spot_age_s >= _SPOT_STABILIZE_S and not _newest_spot.node_name:
                            logger.debug(
                                f"[auto_rebalancer] Action {_wa.id}: new spot EC2 up "
                                f"{int(_spot_age_s)}s but node_name not set yet (kubelet not joined k8s) — waiting"
                            )
                        else:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: new spot appeared but "
                                f"only {int(_spot_age_s)}s old (need {_SPOT_STABILIZE_S}s) — "
                                f"waiting for node to stabilize before Phase 2"
                            )

                    # Check if Phase 2 actions exist yet.
                    # EXPIRED actions don't count — they were never executed (agent restarted).
                    # If Phase 2 existed but all expired, we need to either auto-complete
                    # (source EC2 already terminated) or re-queue them fresh.
                    _phase2_any = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                    ).count() > 0
                    _phase2_active = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status.notin_([_AAS0.EXPIRED, _AAS0.FAILED]),
                    ).count() > 0

                    # ── FAST-RECOVERY: Phase 2 expired while agent was down ──────────────
                    # If CORDON/DRAIN/TERMINATE all expired (agent pod restarted mid-action),
                    # check the source EC2 state in AWS:
                    #   • Already terminated → auto-complete (replacement succeeded in real world)
                    #   • Still running → delete expired actions and re-queue Phase 2 fresh
                    if _phase2_any and not _phase2_active:
                        _expired_count = db.query(_AA0).filter(
                            _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                            _AA0.status == _AAS0.EXPIRED,
                            _AA0.action_type.in_([_AAT0.CORDON_NODE, _AAT0.DRAIN_NODE, _AAT0.TERMINATE_NODE]),
                        ).count()
                        if _expired_count > 0:
                            _src_terminated = False
                            try:
                                import boto3 as _b3_rec
                                from backend.utils.aws.asg import get_assumed_credentials as _gac_rec
                                _rec_cluster_obj = db.query(Cluster).filter_by(id=_wa.cluster_id).first()
                                _rec_creds = _gac_rec(_rec_cluster_obj, db) if _rec_cluster_obj else {}
                                _rec_region = (_rec_cluster_obj.region if _rec_cluster_obj else None) or "ap-south-1"
                                _rec_ec2 = _b3_rec.client("ec2", region_name=_rec_region, **_rec_creds)
                                _rec_resp = _rec_ec2.describe_instances(InstanceIds=[_wa_instance_id]) if _wa_instance_id else {"Reservations": []}
                                for _rec_r in _rec_resp.get("Reservations", []):
                                    for _rec_i in _rec_r.get("Instances", []):
                                        if _rec_i.get("State", {}).get("Name") in ("terminated", "shutting-down"):
                                            _src_terminated = True
                            except Exception as _rec_ec2_err:
                                logger.warning(
                                    f"[auto_rebalancer] Action {_wa.id}: EC2 recovery check failed: "
                                    f"{_rec_ec2_err} — will re-queue expired Phase 2 actions"
                                )

                            if _src_terminated:
                                # Source already gone — the replacement succeeded in the real world.
                                # Auto-complete the rebalancing action to clear the stuck state.
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: Phase 2 actions expired "
                                    f"but source EC2 {_wa_instance_id} is already terminated — "
                                    f"auto-completing (replacement succeeded)"
                                )
                                _wa.status = 'completed'
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                _wa_meta['current_step'] = 'completed'
                                _wa_meta['auto_completed_reason'] = (
                                    f"Phase2 AgentActions expired (agent restarted) but source "
                                    f"EC2 {_wa_instance_id} was already terminated — auto-completed"
                                )
                                _wa.action_metadata = _wa_meta
                                if _wa_instance_id and _redis:
                                    try:
                                        _redis.delete(f"spot:node_active_action:{_wa_instance_id}")
                                    except Exception:
                                        pass
                                db.commit()
                                continue
                            else:
                                # Source still running — delete expired actions so _phase2_any
                                # becomes False and Phase 2 re-creation runs below normally.
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: Phase 2 actions expired, "
                                    f"source EC2 {_wa_instance_id} still running — re-queuing Phase 2"
                                )
                                db.query(_AA0).filter(
                                    _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                                    _AA0.status == _AAS0.EXPIRED,
                                    _AA0.action_type.in_([_AAT0.CORDON_NODE, _AAT0.DRAIN_NODE, _AAT0.TERMINATE_NODE]),
                                ).delete(synchronize_session=False)
                                db.commit()
                                _phase2_any = False
                                _phase2_active = False

                    _phase2_exists = _phase2_any

                    # Measure elapsed since Phase 1 (NodePool update) completed
                    _phase1_ts = _wa_meta.get('phase1_completed_at')
                    if _phase1_ts:
                        try:
                            _patch_completed_at = datetime.fromisoformat(_phase1_ts)
                        except (ValueError, TypeError):
                            _patch_completed_at = _wa.started_at
                    else:
                        _patch_completed_at = _wa.started_at
                    _spot_wait_elapsed = (
                        (datetime.utcnow() - _patch_completed_at).total_seconds()
                        if _patch_completed_at else 9999
                    )
                    _SPOT_WAIT_TIMEOUT_S = 30 * 60  # 30 minutes

                    # ── Phase 2 creation: NEW spot joined OR timeout ───────────
                    if not _phase2_exists:
                        if _wa_karpenter_active and not _new_spot_joined and _spot_wait_elapsed < _SPOT_WAIT_TIMEOUT_S:
                            # Still waiting for THIS action's spot replacement — do NOT create drain actions yet
                            _wa_meta['current_step'] = 'waiting_for_spot_node'
                            _wa_meta['spot_wait_elapsed_s'] = int(_spot_wait_elapsed)
                            _wa_meta['spot_count_current'] = _spot_count
                            _wa_meta['spot_count_baseline'] = _spot_baseline
                            _wa_meta['provisioner_type'] = 'karpenter'
                            _wa.action_metadata = _wa_meta
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Phase 1 done, "
                                f"waiting for NEW spot node (current={_spot_count}, baseline={_spot_baseline}, "
                                f"{int(_spot_wait_elapsed)}s elapsed, timeout {_SPOT_WAIT_TIMEOUT_S}s)"
                            )
                            db.commit()
                            continue  # Re-check next cycle (outer for _wa loop)

                        if _new_spot_joined:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: NEW spot node joined! "
                                f"(count {_spot_baseline} → {_spot_count}) "
                                f"Creating Phase 2 actions (CORDON→DRAIN→TERMINATE)"
                            )
                            _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()

                            # Apply karpenter.sh/do-not-disrupt=true to the new spot node.
                            # This prevents Karpenter's consolidation/expiry loop from
                            # terminating the replacement node while pods are still draining
                            # onto it.  The annotation is removed after Phase 2 completes.
                            if _newest_spot and _newest_spot.node_name:
                                try:
                                    from backend.models.agent_action import AgentAction as _AA_ANN, AgentActionType as _AAT_ANN, AgentActionStatus as _AAS_ANN
                                    _kp_annotate = _AA_ANN(
                                        cluster_id=_wa.cluster_id,
                                        action_type=_AAT_ANN.LABEL_NODE,
                                        status=_AAS_ANN.PENDING,
                                        payload={
                                            "node_name": _newest_spot.node_name,
                                            "labels": {},
                                            "annotations": {
                                                "karpenter.sh/do-not-disrupt": "true"
                                            },
                                            "rebalancing_action_id": str(_wa.id),
                                            "purpose": "protect_replacement_node",
                                        },
                                    )
                                    db.add(_kp_annotate)
                                    db.flush()
                                    logger.info(
                                        f"[auto_rebalancer] Queued karpenter.sh/do-not-disrupt=true "
                                        f"on {_newest_spot.node_name} (action {_wa.id})"
                                    )
                                except Exception as _ann_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Failed to queue do-not-disrupt annotation: {_ann_err}"
                                    )
                        elif _spot_wait_elapsed >= _SPOT_WAIT_TIMEOUT_S and _wa_karpenter_active:
                            # Timeout: spot replacement did not join K8s in time.
                            # For direct EC2 launch (non-Karpenter S2S): the replacement EC2
                            # is running in AWS but kubelet never started (likely missing user-data /
                            # IAM issue). Terminate the orphan EC2 and FAIL the action — do NOT
                            # drain the source node without a working replacement.
                            if _direct_launch:
                                _orphan_id = _wa_meta.get('replacement_spot_instance_id')
                                if _orphan_id:
                                    try:
                                        _do_rollback_terminate_orphan_spot(
                                            _wa, _wa_meta, db
                                        )
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: direct-launch "
                                            f"orphan {_orphan_id} terminated (kubelet never joined K8s)"
                                        )
                                    except Exception as _orp_err:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: orphan termination "
                                            f"failed: {_orp_err} — manual cleanup of {_orphan_id} required"
                                        )
                                logger.error(
                                    f"[auto_rebalancer] Action {_wa.id}: direct spot node "
                                    f"did not join cluster after {int(_spot_wait_elapsed)}s — "
                                    f"failing action. Likely cause: missing user-data (grant "
                                    f"ec2:DescribeInstanceAttribute + ec2:DescribeLaunchTemplateVersions)"
                                )
                                _wa.status = 'failed'
                                _wa.error_message = (
                                    f"Spot node did not join cluster after {int(_spot_wait_elapsed)}s. "
                                    f"Likely cause: EKS bootstrap script not copied to new node. "
                                    f"Grant ec2:DescribeInstanceAttribute and ec2:DescribeLaunchTemplateVersions "
                                    f"to the cross-account IAM role and retry."
                                )
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                db.commit()
                                continue

                            # Karpenter (non-direct) timeout: check if other nodes exist
                            # to absorb workloads before proceeding.
                            _other_running = db.query(Instance).filter(
                                Instance.cluster_id == _wa.cluster_id,
                                Instance.state == 'running',
                                Instance.instance_id != _wa_instance_id,
                            ).count()
                            if _other_running == 0:
                                logger.error(
                                    f"[auto_rebalancer] Action {_wa.id}: Karpenter timeout AND "
                                    f"no other nodes in cluster — refusing to drain last node "
                                    f"without a replacement."
                                )
                                _wa.status = 'failed'
                                _wa.error_message = (
                                    "Karpenter spot provisioning timed out and no other cluster "
                                    "nodes exist. Drain aborted to prevent workload downtime. "
                                    "Check Karpenter logs and EC2 spot capacity for this region."
                                )
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                db.commit()
                                continue
                            # P-H1 fix: other nodes exist but Karpenter never provisioned a
                            # replacement. Proceeding to drain without a confirmed spot node
                            # causes a permanent cluster shrink if Karpenter's NodeClaim is
                            # stuck. FAIL the action instead — operator must investigate
                            # Karpenter logs and NodeClaim status.
                            logger.error(
                                f"[auto_rebalancer] Action {_wa.id}: Karpenter spot wait timeout "
                                f"({int(_spot_wait_elapsed)}s) — no spot node provisioned. "
                                f"{_other_running} other node(s) exist but proceeding to drain "
                                f"without confirmed replacement risks permanent cluster shrink. "
                                f"Failing action — check Karpenter NodeClaim status."
                            )
                            _wa.status = 'failed'
                            _wa.error_message = (
                                f"Karpenter spot provisioning timed out ({int(_spot_wait_elapsed)}s) "
                                f"with no replacement node joining. Drain aborted to prevent "
                                f"cluster shrink. Investigate Karpenter NodeClaim status and spot "
                                f"capacity for this region/AZ. Rebalancer will retry when "
                                f"Karpenter recovers."
                            )
                            _wa.completed_at = datetime.utcnow()
                            _wa.duration_seconds = int(
                                (_wa.completed_at - _wa.started_at).total_seconds()
                            ) if _wa.started_at else 0
                            db.commit()
                            continue
                        elif _spot_wait_elapsed >= _SPOT_WAIT_TIMEOUT_S and not _wa_karpenter_active:
                            # No Karpenter + no spot node = nothing will ever provision a replacement.
                            # FAIL the action cleanly. Do not drain or terminate the OD node.
                            logger.error(
                                f"[auto_rebalancer] Action {_wa.id}: no spot node joined after "
                                f"{int(_spot_wait_elapsed)}s and Karpenter is not installed. "
                                f"Failing action — cannot replace OD node without a replacement."
                            )
                            _wa.status = 'failed'
                            _wa.error_message = (
                                "Spot wait timeout: no replacement spot node joined the cluster. "
                                "Check spot capacity availability in this region/AZ, or enable "
                                "Karpenter for automatic spot provisioning with fallback logic."
                            )
                            _wa.completed_at = datetime.utcnow()
                            _wa.duration_seconds = int(
                                (_wa.completed_at - _wa.started_at).total_seconds()
                            ) if _wa.started_at else 0
                            db.commit()
                            continue  # outer for _wa loop

                        # ── CREATE PHASE 2 ACTIONS ────────────────────────────
                        # Retrieve instance params from action metadata (set in Phase 1)
                        _p2 = _wa_meta.get("phase2_params", {})
                        _p2_instance_id = _p2.get("instance_id") or _wa_meta.get("instance_id", "")
                        _p2_instance_type = _p2.get("instance_type", "")
                        _p2_az = _p2.get("az", "")

                        # Karpenter manages node lifecycle — no ASG attach needed.
                        _p2_term_mode = "karpenter"
                        _wa_meta['termination_mode'] = _p2_term_mode

                        if _p2_instance_id:
                            from backend.models.agent_action import AgentAction as _AA_P2
                            # N1 fix: Read respect_pdb_enabled from cluster settings.
                            # force=True means ignore PDB; respect_pdb_enabled=True means obey PDB → force=False
                            _n1_force_drain = True  # default: force drain (legacy behaviour)
                            try:
                                from backend.models.cluster import StatelessRuntimeRules as _SRR_N1
                                _srr_n1 = db.query(_SRR_N1).filter(_SRR_N1.cluster_id == _wa.cluster_id).first()
                                if _srr_n1 and getattr(_srr_n1, 'respect_pdb_enabled', False):
                                    _n1_force_drain = False  # respect PDB → do NOT force
                            except Exception:
                                pass

                            cordon_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.CORDON_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "instance_type": _p2_instance_type,
                                    "az": _p2_az,
                                    "rebalancing_action_id": _wa.id,
                                    "zero_downtime_step": 2,
                                }
                            )
                            drain_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.DRAIN_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "instance_type": _p2_instance_type,
                                    "az": _p2_az,
                                    "ignore_daemonsets": True,
                                    "grace_period_seconds": 60,
                                    "force": _n1_force_drain,
                                    "rebalancing_action_id": _wa.id,
                                    "zero_downtime_step": 3,
                                }
                            )
                            terminate_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.TERMINATE_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "node_name": None,
                                    "rebalancing_action_id": _wa.id,
                                    "zero_downtime_step": 4,
                                    # termination_mode routing:
                                    # "asg_no_decrement" → attach mode: terminate_instance_in_auto_scaling_group(ShouldDecrementDesiredCapacity=False)
                                    # "replacement"      → standard: detach-not-decrement + EC2 terminate
                                    "termination_mode": _p2_term_mode,
                                    "asg_name": _wa_meta.get("asg_name_used"),
                                    "asg_min_at_start": _wa_meta.get("asg_min_at_start"),
                                    "asg_desired_at_start": _wa_meta.get("asg_desired_at_start"),
                                }
                            )
                            db.add(cordon_p2)
                            db.add(drain_p2)
                            db.add(terminate_p2)
                            db.flush()
                            _wa_meta['current_step'] = 'cordoning_node'
                            _wa_meta['phase2_created_at'] = datetime.utcnow().isoformat()
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Phase 2 created "
                                f"(CORDON→DRAIN→TERMINATE for {_p2_instance_id})"
                            )
                        continue  # Wait for Phase 2 to complete (outer for _wa loop)

                    # Phase 2 exists — check if drain is done, wait for completion
                    _drain_sa = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status == _AAS0.COMPLETED,
                    ).first()
                    if 'step_3_draining_pods' not in _wa_meta and _drain_sa and _drain_sa.completed_at:
                        _wa_meta['step_3_draining_pods'] = _drain_sa.completed_at.isoformat()

                    # ── READINESS-AWARE VERIFICATION ────────────────────────────────────
                    # After all K8s steps complete (CORDON → DRAIN → kubectl delete node),
                    # enforce a 90-second grace period before EC2 termination.
                    # This gives evicted pods time to reschedule on the replacement spot node.
                    # Max wait: 5 minutes. Pods stuck after 5 min → log warning and proceed
                    # (K8s node is already deleted; uncordon is not possible at this stage).
                    if not _wa_meta.get('readiness_verified'):
                        _post_drain_ts = _wa_meta.get('post_drain_readiness_started_at')
                        if not _post_drain_ts:
                            # First cycle after K8s actions complete: start readiness timer
                            _wa_meta['post_drain_readiness_started_at'] = datetime.utcnow().isoformat()
                            _wa_meta['current_step'] = 'verifying_pod_readiness'
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            continue

                        _post_drain_elapsed = (
                            datetime.utcnow() - datetime.fromisoformat(_post_drain_ts)
                        ).total_seconds()
                        _READINESS_GRACE_S = 20   # 20 seconds minimum after kubectl delete node (90s spot-stabilisation wait already happened before Phase 2)
                        # Problem #11: Configurable drain timeout per cluster (default 15 min)
                        _drain_timeout_min = 15
                        try:
                            from backend.models.cluster import ClusterOptimizationSettings as _COS_dt
                            _cos_dt = db.query(_COS_dt).filter(
                                _COS_dt.cluster_id == _wa.cluster_id
                            ).first()
                            if _cos_dt and getattr(_cos_dt, 'drain_timeout_minutes', None):
                                _drain_timeout_min = _cos_dt.drain_timeout_minutes
                        except Exception:
                            pass
                        _READINESS_MAX_S = _drain_timeout_min * 60  # configurable drain timeout

                        if _post_drain_elapsed < _READINESS_GRACE_S:
                            # Still in grace period — wait for next cycle
                            _wa_meta['current_step'] = 'verifying_pod_readiness'
                            _wa_meta['post_drain_elapsed_s'] = int(_post_drain_elapsed)
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            continue

                        # Grace period passed: check pod_metrics for pods still on old node
                        _drained_inst_rd = _wa_meta.get('instance_id', '')
                        _pods_stuck = False
                        if _drained_inst_rd:
                            try:
                                from backend.models.pod_metric import PodMetric as _PM_RD
                                _pods_stuck = db.query(_PM_RD).filter(
                                    _PM_RD.cluster_id == _wa.cluster_id,
                                    _PM_RD.node_name == _drained_inst_rd,
                                    _PM_RD.timestamp >= datetime.utcnow() - timedelta(minutes=2),
                                ).count() > 0
                            except Exception:
                                pass  # pod_metrics unavailable — proceed optimistically

                        if _pods_stuck and _post_drain_elapsed < _READINESS_MAX_S:
                            # Pods still migrating — wait up to 5 min total
                            _wa_meta['current_step'] = 'verifying_pod_readiness'
                            _wa_meta['post_drain_elapsed_s'] = int(_post_drain_elapsed)
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            continue

                        if _pods_stuck and _post_drain_elapsed >= _READINESS_MAX_S:
                            # 5-min timeout: pods may still be stuck but the K8s node object
                            # was already deleted by the drain sequence — uncordon is not
                            # meaningful at this point (there is nothing to uncordon).
                            # Log the anomaly and proceed to EC2 terminate.
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: pod readiness timeout "
                                f"({int(_post_drain_elapsed)}s) — pods may still be on "
                                f"{_drained_inst_rd}. K8s node already deleted; "
                                f"proceeding to EC2 terminate."
                            )

                        # Readiness verified (grace period elapsed, no stuck pods or timeout)
                        _wa_meta['readiness_verified'] = True
                        _wa_meta['readiness_verified_at'] = datetime.utcnow().isoformat()
                        _wa.action_metadata = _wa_meta
                        db.commit()

                    # Spot appeared or timeout reached — record and proceed to terminate
                    if _spot_count > 0:
                        _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()
                        _wa_meta['current_step'] = 'old_node_terminating'
                    else:
                        _wa_meta['current_step'] = 'old_node_terminating_timeout'
                        logger.warning(
                            f"[auto_rebalancer] Action {_wa.id}: spot node wait timeout "
                            f"({int(_spot_wait_elapsed)}s) — proceeding to terminate old OD node anyway"
                        )
                        # N7 fix: Block the pool for the full join timeout duration
                        # instead of hardcoded 300s. Prevents double-launch when
                        # launch_blocked expires before the 30-min join timeout.
                        try:
                            _timeout_itype = _wa_meta.get("target_instance_type", "")
                            _timeout_az = _wa_meta.get("target_az", "")
                            if _timeout_itype and _timeout_az and _redis:
                                _block_key = f"spot:launch_blocked:{_wa.cluster_id}:{_timeout_itype}:{_timeout_az}"
                                _block_ttl = _SPOT_WAIT_TIMEOUT_S if _SPOT_WAIT_TIMEOUT_S > 0 else 1800
                                _redis.setex(_block_key, _block_ttl, '1')
                                logger.warning(
                                    '[auto_rebalancer] No-join timeout for action %s — '
                                    'blocking pool %s:%s in cluster %s for %ds',
                                    _wa.id, _timeout_itype, _timeout_az, _wa.cluster_id, _block_ttl
                                )
                        except Exception:
                            pass

                # Fix 2 + CORDON guard: if ANY Phase 2 action failed, determine which
                # stage failed and execute the appropriate rollback.
                if _failed > 0:
                    # ── CORDON failure: drain never ran — full clean rollback ────────
                    _cordon_node_failed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status == _AAS0.FAILED,
                    ).first()
                    # Check whether drain *actually executed* (COMPLETED or FAILED).
                    # EXPIRED/PICKED_UP actions mean the agent died before running drain
                    # (e.g. SELF_CORDON on agent node → agent evicted mid-drain →
                    # DRAIN stays PICKED_UP then EXPIRED). These must NOT block the
                    # cordon-only rollback path — treat them as "drain never ran".
                    _drain_attempted = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status.in_([_AAS0.COMPLETED, _AAS0.FAILED]),
                    ).count() > 0

                    # Z5 fix: SELF_CORDON_ATTEMPT — agent is on the node being drained.
                    # Force-treat as cordon-only failure regardless of drain existence.
                    _cordon_err_raw = (_cordon_node_failed.error_message or '') if _cordon_node_failed else ''
                    _is_self_cordon = 'SELF_CORDON_ATTEMPT' in _cordon_err_raw
                    if _is_self_cordon:
                        logger.error(
                            f"[auto_rebalancer] Action {_wa.id}: SELF_CORDON_ATTEMPT — "
                            f"agent is running on the node being drained. "
                            f"Forcing cordon-only rollback path."
                        )
                        _drain_attempted = False  # override: treat as cordon-only failure

                    if _cordon_node_failed and not _drain_attempted:
                        # Z4 fix: If CORDON failed because the K8s node is gone (404/NOT_FOUND),
                        # the source EC2 is a zombie — terminate it directly and clean up.
                        _cordon_err = (_cordon_node_failed.error_message or '').lower()
                        _cordon_result = _cordon_node_failed.result or {}
                        _cordon_err_detail = str(_cordon_result.get('error', '')).lower()
                        _is_node_gone = (
                            'not found' in _cordon_err or '404' in _cordon_err
                            or 'not found' in _cordon_err_detail or '404' in _cordon_err_detail
                        )
                        if _is_node_gone and _wa_instance_id:
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: CORDON_NODE failed with "
                                f"NOT_FOUND — K8s node gone, EC2 {_wa_instance_id} is a zombie. "
                                f"Terminating zombie EC2."
                            )
                            try:
                                import boto3 as _b3_z4
                                _z4_region = _wa_meta.get('target_region', 'us-east-1')
                                _z4_creds = {}
                                try:
                                    _z4_acct = db.query(Cluster).filter_by(id=_wa.cluster_id).first()
                                    if _z4_acct:
                                        from backend.workers.tasks.reconciliation_worker import _get_platform_sts_client, _assume_role_for_account
                                        _z4_sts = _get_platform_sts_client(db)
                                        _z4_aws_acct = db.query(AWSAccount).filter_by(id=_z4_acct.account_id).first()
                                        if _z4_aws_acct:
                                            _z4_creds = _assume_role_for_account(_z4_sts, _z4_aws_acct)
                                            _z4_region = _z4_acct.region or _z4_region
                                except Exception:
                                    pass
                                _z4_ec2 = _b3_z4.client("ec2", region_name=_z4_region, **_z4_creds)
                                _z4_ec2.terminate_instances(InstanceIds=[_wa_instance_id])
                                logger.info(
                                    f"[auto_rebalancer] Terminated zombie EC2 {_wa_instance_id} "
                                    f"(K8s node missing)"
                                )
                            except Exception as _z4_err:
                                logger.error(
                                    f"[auto_rebalancer] Failed to terminate zombie EC2 "
                                    f"{_wa_instance_id}: {_z4_err}"
                                )
                            # Clear both keys — Z4 and Z6 are coupled
                            if _redis:
                                try:
                                    _redis.delete(f"rebalance_failures:{_wa_instance_id}")
                                    _redis.delete(f"spot:node_active_action:{_wa_instance_id}")
                                except Exception:
                                    pass
                            _wa.status = 'failed'
                            _wa.error_message = "ZOMBIE_EC2_TERMINATED"
                            _wa.completed_at = datetime.utcnow()
                            _wa.duration_seconds = int(
                                (_wa.completed_at - _wa.started_at).total_seconds()
                            ) if _wa.started_at else 0
                            _wa_meta['current_step'] = 'zombie_ec2_terminated'
                            _wa.action_metadata = _wa_meta
                            _do_rollback_terminate_orphan_spot(_wa, _wa_meta, db)
                            db.commit()
                            continue

                        logger.error(
                            f"[auto_rebalancer] Action {_wa.id}: CORDON_NODE failed — "
                            f"rolling back (uncordon + terminate orphan spot). "
                            f"Clearing cooldown for retry."
                        )
                        _wa.status = 'failed'
                        _wa.error_message = (
                            f"CORDON_NODE failed. Node {_wa_instance_id} unchanged. "
                            f"Orphan spot instance terminated. Will retry next cycle."
                        )
                        _wa.completed_at = datetime.utcnow()
                        _wa.duration_seconds = int(
                            (_wa.completed_at - _wa.started_at).total_seconds()
                        ) if _wa.started_at else 0
                        _wa_meta['current_step'] = 'failed_cordon_rollback'
                        _wa.action_metadata = _wa_meta
                        if _wa_instance_id and _redis:
                            try:
                                # P-H3 fix: set backoff key IMMEDIATELY instead of deleting it.
                                # Deleting leaves a ~15-30s window with no protection.
                                # Setting a short backoff prevents a new action being created
                                # in the next Celery beat while rollback is still in-flight.
                                _fkey_h3c = f"rebalance_failures:{_wa_instance_id}"
                                # Problem #16: Sliding window — reset if no failure in 24h
                                _lf_h3c = _redis.get(f"rebalance_last_failure:{_wa_instance_id}")
                                if _lf_h3c:
                                    try:
                                        if (datetime.utcnow().timestamp() - float(_lf_h3c.decode() if isinstance(_lf_h3c, bytes) else _lf_h3c)) > 86400:
                                            _redis.delete(_fkey_h3c)
                                    except (ValueError, TypeError):
                                        pass
                                _fcnt_h3c = int(_redis.incr(_fkey_h3c) or 1)
                                _redis.expire(_fkey_h3c, 86400)
                                _redis.setex(f"rebalance_last_failure:{_wa_instance_id}", 86400, str(datetime.utcnow().timestamp()))
                                _boff_h3c = min(300 * (2 ** (_fcnt_h3c - 1)), 3600)
                                _redis.setex(
                                    f"spot:rebalanced:instance:{_wa_instance_id}",
                                    max(_boff_h3c, 60),
                                    "failure_backoff_cordon"
                                )
                            except Exception:
                                pass
                        db.commit()
                        # P-H2 fix: set stabilization lock after CORDON failure so the next
                        # 15s beat does not immediately re-attempt the same cluster while
                        # UNCORDON rollback is still in-flight.
                        if _redis:
                            try:
                                from backend.services.cooldown_controller import CooldownController
                                from backend.core.redis_client import get_redis_client as _grc_h2a
                                CooldownController(_grc_h2a()).acquire_stabilization_lock(
                                    _wa.cluster_id, reason="phase2_cordon_failure_rollback"
                                )
                            except Exception:
                                pass
                        _do_rollback_uncordon_and_terminate(_wa, _wa_meta, db)
                        continue

                    # ── DRAIN failure: workloads still on old node — safe rollback ──
                    _drain_node_failed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": _wa.id}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status == _AAS0.FAILED,
                    ).first()
                    if _drain_node_failed:
                        _drain_fail_err = (_drain_node_failed.error_message or '').strip()
                        _drain_fail_detail = _drain_fail_err[:200] if _drain_fail_err else 'conflict or pod disruption budget'
                        logger.error(
                            f"[auto_rebalancer] Action {_wa.id}: DRAIN_NODE failed — "
                            f"EC2 terminate SKIPPED to protect workloads on {_wa_instance_id}. "
                            f"Node will be uncordoned. Orphan spot terminated. Retrying after backoff."
                        )
                        _wa.status = 'failed'
                        _wa.error_message = (
                            f"DRAIN_NODE failed ({_drain_fail_detail}). "
                            f"EC2 terminate skipped — {_wa_instance_id} still running. "
                            f"Source node uncordoned; orphan spot terminated. "
                            f"Rebalancer will retry after backoff."
                        )
                        _wa.completed_at = datetime.utcnow()
                        _wa.duration_seconds = int(
                            (_wa.completed_at - _wa.started_at).total_seconds()
                        ) if _wa.started_at else 0
                        _wa_meta['current_step'] = 'failed_drain_ec2_protected'
                        _wa.action_metadata = _wa_meta
                        if _wa_instance_id and _redis:
                            try:
                                # P-H3 fix: set backoff key immediately (same logic as CORDON path)
                                _fkey_h3d = f"rebalance_failures:{_wa_instance_id}"
                                # Problem #16: Sliding window — reset if no failure in 24h
                                _lf_h3d = _redis.get(f"rebalance_last_failure:{_wa_instance_id}")
                                if _lf_h3d:
                                    try:
                                        if (datetime.utcnow().timestamp() - float(_lf_h3d.decode() if isinstance(_lf_h3d, bytes) else _lf_h3d)) > 86400:
                                            _redis.delete(_fkey_h3d)
                                    except (ValueError, TypeError):
                                        pass
                                _fcnt_h3d = int(_redis.incr(_fkey_h3d) or 1)
                                _redis.expire(_fkey_h3d, 86400)
                                _redis.setex(f"rebalance_last_failure:{_wa_instance_id}", 86400, str(datetime.utcnow().timestamp()))
                                _boff_h3d = min(300 * (2 ** (_fcnt_h3d - 1)), 3600)
                                _redis.setex(
                                    f"spot:rebalanced:instance:{_wa_instance_id}",
                                    max(_boff_h3d, 60),
                                    "failure_backoff_drain"
                                )
                            except Exception:
                                pass
                        db.commit()
                        # P-H2 fix: set stabilization lock after DRAIN failure so the next
                        # 15s beat does not immediately re-attempt the same cluster while
                        # UNCORDON rollback is still in-flight.
                        if _redis:
                            try:
                                from backend.services.cooldown_controller import CooldownController
                                from backend.core.redis_client import get_redis_client as _grc_h2b
                                CooldownController(_grc_h2b()).acquire_stabilization_lock(
                                    _wa.cluster_id, reason="phase2_drain_failure_rollback"
                                )
                            except Exception:
                                pass
                        # Full rollback via shared helper:
                        # 1. Queue UNCORDON_NODE (undo cordon on old OD node)
                        # 2. Terminate orphan spot instance
                        _do_rollback_uncordon_and_terminate(_wa, _wa_meta, db)
                        continue

                # ── Backend EC2 terminate: drain is done, now kill the instance ──
                # Agent's kubectl delete node removes the K8s object but leaves EC2
                # running. We must terminate via backend's assumed IAM role to ensure
                # the instance is actually gone so Karpenter provisions a spot replacement.
                if _wa_instance_id and _wa_instance_id.startswith("i-") and _failed == 0:
                    try:
                        import boto3 as _b3wa
                        from backend.models.system_config import SystemConfig as _SC
                        _wa_cluster = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                        _wa_region  = (_wa_cluster.region if _wa_cluster else None) or "ap-south-1"

                        # Load stored platform credentials (same pattern as _sync_instance_state_from_aws)
                        _pk_row  = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_ACCESS_KEY").first()
                        _ps_row  = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_SECRET").first()
                        _pr_row  = db.query(_SC).filter(_SC.key == "PLATFORM_AWS_REGION").first()
                        _plat_key    = (_pk_row.value if _pk_row and _pk_row.value else None)
                        _plat_secret = (_ps_row.value if _ps_row and _ps_row.value else None)
                        _plat_region = (_pr_row.value if _pr_row and _pr_row.value else None) or _wa_region

                        _wa_creds = {}
                        # Resolve IAM role ARN: cluster-level → account-level → no assumption
                        _wa_role_arn = (_wa_cluster.aws_role_arn if _wa_cluster else None)
                        _wa_ext_id   = (_wa_cluster.aws_external_id if _wa_cluster else None)
                        if not _wa_role_arn and _wa_cluster and _wa_cluster.account_id:
                            try:
                                from backend.models.account import Account as _Acct
                                _acct = db.query(_Acct).filter(_Acct.id == _wa_cluster.account_id).first()
                                if _acct:
                                    _wa_role_arn = _acct.role_arn
                                    _wa_ext_id   = _acct.external_id
                            except Exception:
                                pass

                        if _wa_role_arn and _plat_key and _plat_secret:
                            # Use stored platform credentials to build the STS client, then assume role.
                            # Do NOT set endpoint_url — boto3 uses the correct regional endpoint via
                            # region_name automatically. Forcing a regional URL caused "Could not connect"
                            # when Docker's DNS had a transient blip for that specific hostname.
                            import time as _t_sts_wa
                            _wa_creds = {}
                            _sts_last_err = None
                            for _sts_att in range(5):
                                try:
                                    _sts_wa = _b3wa.client(
                                        "sts",
                                        aws_access_key_id=_plat_key,
                                        aws_secret_access_key=_plat_secret,
                                        region_name=_plat_region,
                                    )
                                    _assume_kwargs = {"RoleArn": _wa_role_arn,
                                                      "RoleSessionName": "spot-rebalancer-terminate"}
                                    if _wa_ext_id:
                                        _assume_kwargs["ExternalId"] = _wa_ext_id
                                    _assumed_wa = _sts_wa.assume_role(**_assume_kwargs)
                                    _cwa = _assumed_wa["Credentials"]
                                    _wa_creds = {
                                        "aws_access_key_id":     _cwa["AccessKeyId"],
                                        "aws_secret_access_key": _cwa["SecretAccessKey"],
                                        "aws_session_token":     _cwa["SessionToken"],
                                    }
                                    _sts_last_err = None
                                    break
                                except Exception as _sts_e:
                                    _sts_last_err = _sts_e
                                    if "Could not connect" in str(_sts_e) or "EndpointConnectionError" in str(_sts_e):
                                        _sts_wait = 2 ** _sts_att  # 1, 2, 4, 8, 16s
                                        logger.warning(
                                            f"[auto_rebalancer] STS terminate attempt {_sts_att + 1}/5 "
                                            f"failed: {_sts_e} — retrying in {_sts_wait}s"
                                        )
                                        _t_sts_wa.sleep(_sts_wait)
                                        continue
                                    raise
                            if _sts_last_err:
                                # All STS retries exhausted — fall back to direct platform creds
                                # (no role assumption). Requires the platform IAM user to have
                                # direct EC2/ASG permissions on the target account. If not, the
                                # outer try/except will catch the subsequent API error.
                                logger.warning(
                                    f"[auto_rebalancer] STS assume_role exhausted all retries for "
                                    f"action {_wa.id} — falling back to direct platform credentials. "
                                    f"Last error: {_sts_last_err}"
                                )
                                _wa_creds = {
                                    "aws_access_key_id":     _plat_key,
                                    "aws_secret_access_key": _plat_secret,
                                }
                        elif _plat_key and _plat_secret:
                            # No role ARN — use platform credentials directly
                            _wa_creds = {
                                "aws_access_key_id":     _plat_key,
                                "aws_secret_access_key": _plat_secret,
                            }

                        _terminated = False
                        _term_region = _wa_region

                        # Single-path terminate — no fallbacks.
                        # Rule: if the node is in an ASG, use terminate_instance_in_auto_scaling_group ONLY.
                        #       if the node is NOT in an ASG (Karpenter-managed), use direct EC2 ONLY.
                        # On ANY failure — log the error, mark ec2_terminate_failed, do NOT retry
                        # (except transient throttling which gets up to 3 retries).
                        try:
                            _stored_asg_for_term = _wa_meta.get('asg_name_used')
                            _term_mode = str(_wa_meta.get('termination_mode') or 'replacement')
                            # Backward compatibility for in-flight actions created before
                            # termination_mode was persisted in metadata.
                            if _term_mode == 'replacement' and _wa_meta.get('attached_to_asg'):
                                _term_mode = 'asg_no_decrement'
                            _should_decrement = _term_mode != 'asg_no_decrement'

                            # karpenter_only_mode: skip ASG path entirely, use direct EC2
                            _karpenter_only_term = getattr(
                                getattr(cluster, 'optimization_settings', None),
                                'karpenter_only_mode', False
                            )
                            if _karpenter_only_term:
                                _stored_asg_for_term = None  # Force direct EC2 path

                            if _stored_asg_for_term:
                                # ── ASG-managed node: terminate via ASG API ───────────────
                                # replacement mode       -> decrement desired capacity (legacy)
                                # asg_no_decrement mode -> keep desired capacity unchanged
                                _asg_wa = _b3wa.client("autoscaling",
                                                       region_name=_term_region, **_wa_creds)
                                from botocore.exceptions import ClientError as _CE_asg_term

                                # Pre-decrement MinSize only when we are decrementing desired
                                # capacity as part of replacement mode.
                                if _should_decrement:
                                    try:
                                        _asg_desc = _asg_wa.describe_auto_scaling_groups(
                                            AutoScalingGroupNames=[_stored_asg_for_term]
                                        )['AutoScalingGroups']
                                        if _asg_desc:
                                            _cur_min = _asg_desc[0].get('MinSize', 0)
                                            if _cur_min > 0:
                                                _asg_wa.update_auto_scaling_group(
                                                    AutoScalingGroupName=_stored_asg_for_term,
                                                    MinSize=_cur_min - 1,
                                                )
                                                logger.info(
                                                    f"[auto_rebalancer] Pre-decremented ASG "
                                                    f"'{_stored_asg_for_term}' MinSize "
                                                    f"{_cur_min} → {_cur_min - 1} before terminate"
                                                )
                                    except Exception as _pre_dec_err:
                                        logger.warning(
                                            f"[auto_rebalancer] Failed to pre-decrement MinSize for "
                                            f"ASG '{_stored_asg_for_term}': {_pre_dec_err} — "
                                            f"proceeding with terminate anyway"
                                        )

                                _asg_term_max_retries = 3
                                _asg_term_success = False
                                for _asg_term_attempt in range(_asg_term_max_retries):
                                    try:
                                        _asg_wa.terminate_instance_in_auto_scaling_group(
                                            InstanceId=_wa_instance_id,
                                            ShouldDecrementDesiredCapacity=_should_decrement,
                                        )
                                        _asg_term_success = True
                                        break
                                    except _CE_asg_term as _asg_ce:
                                        _asg_err_code = _asg_ce.response.get('Error', {}).get('Code', '')
                                        if _asg_err_code in ('Throttling', 'RequestLimitExceeded'):
                                            import time as _t_asg
                                            _asg_wait = 2 ** _asg_term_attempt
                                            logger.warning(
                                                f"[auto_rebalancer] ASG terminate throttled for "
                                                f"{_wa_instance_id} (attempt {_asg_term_attempt + 1}/"
                                                f"{_asg_term_max_retries}), retrying in {_asg_wait}s"
                                            )
                                            _t_asg.sleep(_asg_wait)
                                            continue
                                        elif _asg_err_code == 'ValidationError':
                                            # Instance already removed from ASG (EKS MNG auto-terminated
                                            # after kubectl delete node). Fall back to direct EC2 terminate.
                                            logger.warning(
                                                f"[auto_rebalancer] Instance {_wa_instance_id} not in ASG "
                                                f"'{_stored_asg_for_term}' (already detached/terminated by "
                                                f"EKS MNG): {_asg_ce} — falling back to direct EC2 terminate"
                                            )
                                            _ec2_wa_fallback = _b3wa.client(
                                                "ec2", region_name=_term_region, **_wa_creds
                                            )
                                            _ec2_wa_fallback.terminate_instances(InstanceIds=[_wa_instance_id])
                                            _asg_term_success = True
                                            break
                                        else:
                                            raise
                                if not _asg_term_success:
                                    raise RuntimeError(
                                        f"ASG terminate exhausted {_asg_term_max_retries} retries "
                                        f"for {_wa_instance_id}"
                                    )
                                _terminated = True
                                logger.info(
                                    f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                                    f"via terminate_instance_in_auto_scaling_group "
                                    f"(mode={_term_mode}, "
                                    f"ShouldDecrementDesiredCapacity={_should_decrement}, "
                                    f"action {_wa.id} post-drain)"
                                )
                            else:
                                # ── Non-ASG node (Karpenter-managed): direct EC2 ONLY ─────
                                _ec2_wa = _b3wa.client("ec2",
                                                       region_name=_term_region, **_wa_creds)
                                _ec2_wa.terminate_instances(InstanceIds=[_wa_instance_id])
                                _terminated = True
                                logger.info(
                                    f"[auto_rebalancer] Backend terminated EC2 {_wa_instance_id} "
                                    f"via direct EC2 API (non-ASG node, action {_wa.id} post-drain)"
                                )

                            _wa_meta['step_5_old_node_terminated'] = datetime.utcnow().isoformat()
                            # ── Immediately mark source instance as terminated in DB ──
                            # Without this, the rebalancer sees it as ON_DEMAND on the
                            # next 15s cycle and launches ANOTHER replacement → cluster growth.
                            try:
                                # Issue #11: with_for_update — lock row before state write
                                _src_db_inst = db.query(Instance).filter(
                                    Instance.instance_id == _wa_instance_id
                                ).with_for_update().first()
                                if _src_db_inst:
                                    _src_db_inst.state = 'terminated'
                                    _src_db_inst.status = 'terminated'
                                    db.flush()
                                    logger.info(
                                        f"[auto_rebalancer] Marked {_wa_instance_id} as "
                                        f"terminated in DB (prevents cluster growth)"
                                    )
                            except Exception as _term_db_err:
                                logger.warning(
                                    f"[auto_rebalancer] Failed to mark source instance "
                                    f"terminated in DB: {_term_db_err}"
                                )
                            # Also clear the per-instance rebalancing cooldown key so discovery
                            # can re-register this instance if it somehow reappears (unlikely).
                            try:
                                _redis.delete(f"spot:rebalanced:instance:{_wa_instance_id}")
                            except Exception:
                                pass

                        except Exception as _term_err:
                            _wa_meta['ec2_terminate_failed'] = True
                            logger.error(
                                f"[auto_rebalancer] EC2 terminate FAILED for {_wa_instance_id}: "
                                f"{_term_err} — no fallback applied, cluster state unchanged. "
                                f"Manual intervention required."
                            )
                            # P-M2 fix: increase cooldown from 90 min (5400s) to 4 hours (14400s).
                            # 90 min is insufficient for operator review — after expiry the
                            # rebalancer retries with both OD + orphan spot still running (N+1).
                            # 4 hours gives operators time to investigate and manually terminate
                            # before the next automatic retry attempt.
                            try:
                                _redis.set(
                                    f"spot:term_failed:{_wa_instance_id}", "1", ex=14400
                                )
                            except Exception:
                                pass
                    except Exception as _term_err:
                        _terminated = False
                        _wa_meta['ec2_terminate_failed'] = True
                        logger.error(
                            f"[auto_rebalancer] Backend EC2 terminate block failed for "
                            f"{_wa_instance_id}: {_term_err} — instance still running!"
                        )


                # ── STATUS DECISION: fail if EC2 terminate failed ────────────────
                _ec2_terminate_failed = _wa_meta.get('ec2_terminate_failed', False)
                if _failed > 0:
                    _wa.status = 'failed'
                elif _ec2_terminate_failed and _wa_instance_id:
                    _wa.status = 'failed'
                    _wa.error_message = (
                        "Agent K8s actions succeeded but EC2 terminate failed — "
                        f"instance {_wa_instance_id} may still be running on AWS"
                    )
                    # Fix 3: drain completed but old OD couldn't die — the replacement
                    # spot instance is now running but receiving no workloads (drain
                    # evacuated the old node). Terminate it to avoid orphan billing.
                    # Note: K8s node object already deleted — uncordon is not possible.
                    _do_rollback_terminate_orphan_spot(_wa, _wa_meta, db)
                else:
                    _wa.status = 'completed'
                _wa.completed_at = datetime.utcnow()
                _wa.duration_seconds = (
                    int((_wa.completed_at - _wa.started_at).total_seconds())
                    if _wa.started_at else 0
                )
                if _failed > 0:
                    _wa_meta['current_step'] = 'failed'
                    # Issue 8b fix: always set step_6 timestamp so UI timeline shows final marker
                    # even for failed actions (prevents incomplete/empty timeline dots)
                    _wa_meta['step_6_optimization_complete'] = datetime.utcnow().isoformat()
                    _wa.error_message = f"{_failed} agent action(s) failed"
                    # Fix #14: On action failure, apply exponential backoff instead of
                    # deleting the cooldown (which allowed immediate retry → rapid-fire loop).
                    # Track failure count: rebalance_failures:{instance_id}
                    # Backoff = min(300 × 2^failures, 3600) seconds.
                    # Min 5 min, max 1 hour. Reset counter on success.
                    _wa_inst_id_clear = _wa_meta.get("instance_id", "") or (_wa.source_instance_id or "")
                    if _wa_inst_id_clear and _redis:
                        try:
                            _failure_key = f"rebalance_failures:{_wa_inst_id_clear}"
                            _last_fail_key = f"rebalance_last_failure:{_wa_inst_id_clear}"
                            # Problem #16: Sliding window — reset counter if no failure in 24h
                            _last_fail_ts = _redis.get(_last_fail_key)
                            if _last_fail_ts:
                                try:
                                    _lf_val = float(_last_fail_ts.decode() if isinstance(_last_fail_ts, bytes) else _last_fail_ts)
                                    if (datetime.utcnow().timestamp() - _lf_val) > 86400:
                                        _redis.delete(_failure_key)
                                        logger.info(f"[auto_rebalancer] Reset backoff for {_wa_inst_id_clear} — no failure in 24h")
                                except (ValueError, TypeError):
                                    pass
                            _failure_count = int(_redis.incr(_failure_key) or 1)
                            _redis.expire(_failure_key, 86400)  # 24h failure counter TTL
                            _redis.setex(_last_fail_key, 86400, str(datetime.utcnow().timestamp()))
                            _backoff_s = min(300 * (2 ** (_failure_count - 1)), 3600)
                            # Replace the 24h cooldown with the shorter backoff key
                            _cd_key_fail = f"spot:rebalanced:instance:{_wa_inst_id_clear}"
                            _redis.setex(_cd_key_fail, _backoff_s, "failure_backoff")
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id} failed — "
                                f"set {_backoff_s}s backoff for {_wa_inst_id_clear} "
                                f"(failure #{_failure_count}, max 3600s)"
                            )
                        except Exception:
                            pass
                    # Clear per-node active action lock so next cycle can re-target
                    if _wa_inst_id_clear and _redis:
                        try:
                            _redis.delete(f"spot:node_active_action:{_wa_inst_id_clear}")
                        except Exception:
                            pass
                else:
                    _wa_meta['current_step'] = 'optimization_complete'
                    _wa_meta['step_6_optimization_complete'] = datetime.utcnow().isoformat()

                    # Fix #14 (success path): reset failure counter so the next OD→spot
                    # migration on this instance starts from 5-min backoff, not escalated.
                    _wa_inst_id_success = _wa_meta.get("instance_id", "") or (_wa.source_instance_id or "")
                    if _wa_inst_id_success and _redis:
                        try:
                            _redis.delete(f"rebalance_failures:{_wa_inst_id_success}")
                            _redis.delete(f"rebalance_last_failure:{_wa_inst_id_success}")
                        except Exception:
                            pass
                    # Clear per-node active action lock on success
                    if _wa_inst_id_success and _redis:
                        try:
                            _redis.delete(f"spot:node_active_action:{_wa_inst_id_success}")
                        except Exception:
                            pass

                    # ── POST-SUCCESS: Remove do-not-disrupt from replacement node ──
                    # The replacement node is now the primary; it should participate
                    # in Karpenter consolidation normally going forward.
                    # Issue 3 fix: read from metadata (set when spot joined) instead of
                    # _newest_spot variable which is unreliable across loop iterations.
                    _replacement_node_name = (
                        _wa_meta.get('replacement_node_name') or
                        _wa_meta.get('replacement_spot_node_name')
                    )
                    if _replacement_node_name:
                        try:
                            from backend.models.agent_action import AgentAction as _AA_DP, AgentActionType as _AAT_DP, AgentActionStatus as _AAS_DP
                            _kp_deprotect = _AA_DP(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT_DP.LABEL_NODE,
                                status=_AAS_DP.PENDING,
                                payload={
                                    "node_name": _replacement_node_name,
                                    "labels": {},
                                    "annotations": {"karpenter.sh/do-not-disrupt": "true"},
                                    "remove": True,
                                },
                                action_metadata={"rebalancing_action_id": str(_wa.id),
                                                 "purpose": "release_replacement_node"},
                            )
                            db.add(_kp_deprotect)
                            db.flush()
                        except Exception as _deann_err:
                            logger.warning(
                                f"[auto_rebalancer] Failed to queue do-not-disrupt removal: {_deann_err}"
                            )

                    # ── POST-SUCCESS: Trigger standby node launch ──────────────
                    # If cluster has maintain_standby enabled, launch a new standby
                    try:
                        from backend.models.cluster import ClusterOptimizationSettings
                        _settings = db.query(ClusterOptimizationSettings).filter(
                            ClusterOptimizationSettings.cluster_id == _wa.cluster_id
                        ).first()
                        # Read maintain_standby from the dedicated column (not the JSON blob)
                        if _settings and getattr(_settings, "maintain_standby", False):
                            from backend.workers.tasks.standby import launch_standby_node
                            launch_standby_node.delay(_wa.cluster_id)
                            logger.info(
                                f"[auto_rebalancer] Triggered standby launch for "
                                f"cluster {_wa.cluster_id} after successful rebalance"
                            )
                    except Exception as _standby_err:
                        logger.warning(
                            f"[auto_rebalancer] Standby launch trigger failed: {_standby_err}"
                        )

                    # ── POST-SUCCESS: Recalculate realized savings immediately ──
                    try:
                        from backend.workers.tasks.savings_calculator import calculate_real_savings
                        calculate_real_savings.delay()
                        logger.info(
                            f"[auto_rebalancer] Triggered savings recalculation after "
                            f"completed rebalance action {_wa.id}"
                        )
                    except Exception as _savings_err:
                        logger.warning(
                            f"[auto_rebalancer] Savings recalculation trigger failed: {_savings_err}"
                        )

                    # ── POST-SUCCESS: Invalidate coverage cache so UI refreshes ──
                    # The 30s frontend polling will pick up the fresh coverage data
                    # (source node removed, replacement node visible).
                    try:
                        if _redis:
                            _redis.delete(f"cluster_coverage:{_wa.cluster_id}")
                            logger.info(
                                f"[auto_rebalancer] Invalidated coverage cache for "
                                f"cluster {_wa.cluster_id} after successful rebalance"
                            )
                    except Exception as _cov_err:
                        logger.debug(f"[auto_rebalancer] Coverage cache invalidation failed: {_cov_err}")

                    # ── POST-SUCCESS: Write realized savings to action row (Issue #25) ──
                    # realized = ondemand_price(source_type) - actual_spot_price(target_pool)
                    try:
                        _src_itype = (
                            _wa.source_pool.split(':')[0] if _wa.source_pool and ':' in _wa.source_pool
                            else _wa.source_pool or ""
                        )
                        _tgt_itype = _wa_meta.get("target_instance_type") or (
                            _wa.target_pool.split(':')[0] if _wa.target_pool and ':' in _wa.target_pool
                            else ""
                        )
                        _tgt_az = _wa_meta.get("target_az") or (
                            _wa.target_pool.split(':')[1] if _wa.target_pool and ':' in _wa.target_pool
                            else ""
                        )
                        if _src_itype and _tgt_itype and _tgt_az:
                            from backend.utils.pricing_helper import get_pricing_helper as _gph
                            _ph = _gph()
                            _region = cluster.region or "ap-south-1"
                            _od_price = _ph.get_ec2_price(_region, _src_itype) or 0.0
                            _spot_price = _ph.get_spot_price(_region, _tgt_itype, _tgt_az) or 0.0
                            _hourly_saved = max(_od_price - _spot_price, 0.0)
                            _wa.realized_savings_hourly_usd = round(_hourly_saved, 6)
                            _wa.realized_savings_monthly_usd = round(_hourly_saved * 730, 4)
                            logger.info(
                                f"[auto_rebalancer] Realized savings for action {_wa.id}: "
                                f"${_hourly_saved:.4f}/hr (${_wa.realized_savings_monthly_usd:.2f}/mo) "
                                f"[{_src_itype} OD → {_tgt_itype} spot]"
                            )
                    except Exception as _rs_err:
                        logger.warning(
                            f"[auto_rebalancer] Realized savings write failed for action {_wa.id}: {_rs_err}"
                        )

                _wa.action_metadata = _wa_meta
                logger.info(
                    f"[auto_rebalancer] Action {_wa.id} resolved to {_wa.status} "
                    f"(all AgentActions done, steps: {list(_wa_meta.keys())})"
                )

                # BUG-7 fix: Release the concurrent-action semaphore on completion/failure.
                try:
                    if _redis:
                        _sem_release_key = f"rebalance:active_count:{_wa.cluster_id}"
                        _new_sem = _redis.decr(_sem_release_key)
                        if _new_sem < 0:
                            _redis.set(_sem_release_key, 0, ex=300)
                except Exception:
                    pass

                # Issue 2: Increment Redis daily count on completion so subsequent
                # cluster loop cycles read from the counter instead of hitting DB.
                if _wa.status == 'completed':
                    try:
                        if _redis:
                            _incr_count_key = f'spot:daily_count:{_wa.cluster_id}'
                            _new_count = _redis.incr(_incr_count_key)
                            _current_ttl = _redis.ttl(_incr_count_key)
                            if _current_ttl < 0 or _current_ttl > 86400:
                                _redis.expire(_incr_count_key, 86400)
                    except Exception:
                        pass

                # ── POST-FAILURE: Report to Decision Engine ────────────────
                if _wa.status == 'failed':
                    try:
                        from backend.services.decision_engine_service import DecisionEngineService
                        from backend.core.redis_client import get_redis_client as _grc_de
                        _de_svc = DecisionEngineService(db, _grc_de())
                        _target_type = _wa_meta.get("target_instance_type", "")
                        # Fallback: parse from target_pool string for old actions that
                        # pre-date the 'target_az' metadata key being stored at creation.
                        _target_az = _wa_meta.get("target_az") or (
                            _wa.target_pool.split(':')[1]
                            if _wa.target_pool and ':' in _wa.target_pool else ""
                        )
                        if _target_type and _target_az:
                            _de_svc.report_launch_failure(
                                cluster_id=_wa.cluster_id,
                                pool_key=f"{_target_type}:{_target_az}",
                                reason="rebalance_failure",
                            )
                            logger.info(
                                f"[auto_rebalancer] Reported launch failure "
                                f"{_target_type}:{_target_az} to DE"
                            )

                            # Issue 14: Event-driven pool ranking refresh after launch failure.
                            # Debounced to at most 1 refresh per region per 60s so repeated
                            # failures don't hammer the cache builder.
                            try:
                                if _redis:
                                    _rlf_region = cluster.region or "ap-south-1"
                                    _rlf_debounce_key = f'ranking_refresh_pending:{_rlf_region}'
                                    # BUG-3 fix: atomic set — only one worker triggers refresh
                                    if _redis.set(_rlf_debounce_key, '1', nx=True, ex=60):
                                        from backend.workers.app import app as _celery_rlf
                                        _celery_rlf.send_task(
                                            'build_global_pool_cache',
                                            args=[_rlf_region],
                                            countdown=5,
                                            queue='celery',
                                        )
                                        logger.debug(
                                            '[auto_rebalancer] Triggered pool ranking refresh '
                                            'for region %s after launch failure on %s:%s',
                                            _rlf_region, _target_type, _target_az
                                        )
                            except Exception as _rlf_err:
                                logger.debug(
                                    '[auto_rebalancer] Ranking refresh trigger failed (non-fatal): %s',
                                    _rlf_err
                                )
                    except Exception as _de_err:
                        logger.warning(
                            f"[auto_rebalancer] DE failure report failed: {_de_err}"
                        )

                # ── POST-RESOLUTION: Record pool reputation outcome ─────────
                try:
                    from backend.services.pool_reputation_service import PoolReputationService as _PRS
                    from backend.core.redis_client import get_redis_client as _grc_rep
                    _rep_svc = _PRS(db, _grc_rep())
                    _rep_target_pool = _wa.target_pool or ""
                    if ':' in _rep_target_pool:
                        _rep_itype, _rep_az = _rep_target_pool.split(':', 1)
                        _rep_outcome = 'success' if _wa.status == 'completed' else 'failed'
                        _rep_region = cluster.region or "ap-south-1"
                        _rep_spot_price = _wa_meta.get("actual_spot_price_hr") or _wa.actual_spot_price_hr
                        _rep_svc.record_launch_outcome(
                            pool_key=_rep_target_pool,
                            cluster_id=_wa.cluster_id,
                            instance_type=_rep_itype,
                            az=_rep_az,
                            region=_rep_region,
                            outcome=_rep_outcome,
                            actual_spot_price_hr=_rep_spot_price,
                            launched_at=_wa.started_at,
                            resolved_at=_wa.completed_at,
                            failure_reason=_wa.error_message if _rep_outcome == 'failed' else None,
                            rebalancing_action_id=_wa.id,
                        )
                        logger.info(
                            f"[auto_rebalancer] Pool reputation recorded: "
                            f"{_rep_target_pool} → {_rep_outcome}"
                        )
                except Exception as _rep_err:
                    logger.warning(
                        f"[auto_rebalancer] Pool reputation recording failed for action "
                        f"{_wa.id}: {_rep_err}"
                    )

                # Acquire stabilization lock now that the drain+terminate cycle is truly done
                try:
                    from backend.services.cooldown_controller import CooldownController
                    from backend.core.redis_client import get_redis_client as _grc0
                    CooldownController(_grc0()).acquire_stabilization_lock(
                        _wa.cluster_id, reason="auto_rebalancer_complete"
                    )
                except Exception:
                    pass
            except Exception as _wa_err:
                logger.warning(f"[auto_rebalancer] Error resolving waiting_agent action {_wa.id}: {_wa_err}")
        db.commit()

        # Step 1: Check clusters with auto-rebalancing enabled and create actions for on-demand instances
        from backend.models.cluster import ClusterOptimizationSettings, StatelessRuntimeRules

        # Find clusters with unified auto-rebalance enabled
        active_settings = db.query(ClusterOptimizationSettings).filter(
            ClusterOptimizationSettings.auto_rebalance_enabled == True
        ).all()
        
        cluster_ids = [s.cluster_id for s in active_settings]
        auto_rebalance_clusters = db.query(Cluster).filter(Cluster.id.in_(cluster_ids)).all()

        for cluster in auto_rebalance_clusters:
            # Load optimization settings once per cluster (used for cooldown + other logic)
            _opt_settings = db.query(ClusterOptimizationSettings).filter(
                ClusterOptimizationSettings.cluster_id == cluster.id
            ).first()

            logger.debug(f"[auto_rebalancer] >>> Processing cluster {cluster.name} (id={cluster.id})")

            # ── HIBERNATION EARLY GATE ────────────────────────────────────────
            # Skip hibernating clusters completely — no rebalancing, no AWS calls.
            if getattr(cluster, 'is_hibernating', False):
                logger.info(f"[auto_rebalancer] Cluster {cluster.name} is hibernating — skipping")
                try:
                    if _redis:
                        _record_skip(_redis, cluster.id, 'hibernating')
                except Exception:
                    pass
                continue

            # ── PER-CLUSTER INTERVAL GATE ────────────────────────────────────
            # Each cluster can configure its own check frequency (default 15s).
            # The Celery beat fires every 15s; this gate prevents re-processing
            # clusters more frequently than their configured interval.
            # Gate only engages for custom intervals > 15s — at default 15s every
            # beat should process (1:1 ratio). TTL is set to `_check_interval - 14`
            # so the key expires ~1s before the next eligible beat, preventing the
            # double-skip bug where TTL == beat_interval causes every-other skipping.
            _check_interval = max(15, int(getattr(_opt_settings, 'check_interval_seconds', 15) or 15))
            _last_check_key = f"spot:last_check:{cluster.id}"
            # BUG-3 fix: atomic check-and-set using NX to prevent race between
            # concurrent workers both passing the exists() check.
            try:
                if _redis and _check_interval > 15:
                    _gate_acquired = _redis.set(
                        _last_check_key, "1",
                        nx=True, ex=max(1, _check_interval - 14)
                    )
                    if not _gate_acquired:
                        continue  # another worker already claimed this interval
            except Exception:
                pass

            # ── STABILIZATION LOCK GATE ──────────────────────────────────────
            # After any execution action, a 60-second stabilization lock is set.
            # Skip this cluster until the lock expires so the cluster can reach
            # a new steady state before the next optimization cycle.
            # Issue 13: On Redis miss (restart), re-hydrate from DB ClusterCooldownState
            # so the stabilization guarantee survives Redis restarts.
            try:
                if _redis:
                    _stab_key = f'spot:stabilization_lock:{cluster.id}'
                    _stab_ttl = _redis.ttl(_stab_key)
                    # Issue 13: re-hydrate from DB if Redis key is absent
                    if not _stab_ttl or _stab_ttl <= 0:
                        try:
                            from backend.models.cluster import ClusterCooldownState as _CCS
                            _ccs_row = db.query(_CCS).filter_by(cluster_id=cluster.id).first()
                            if _ccs_row and _ccs_row.stabilization_until and _ccs_row.stabilization_until > datetime.utcnow():
                                _remaining = int((_ccs_row.stabilization_until - datetime.utcnow()).total_seconds())
                                _redis.setex(_stab_key, _remaining, '1')
                                _stab_ttl = _remaining
                                logger.debug(
                                    '[auto_rebalancer] Cluster %s: stabilization lock re-hydrated from DB (%ds remaining)',
                                    cluster.id, _remaining
                                )
                        except Exception:
                            pass
                    if _stab_ttl and _stab_ttl > 0:
                        logger.debug(
                            '[auto_rebalancer] Cluster %s in stabilization lock (%ds remaining), deferring',
                            cluster.id, _stab_ttl
                        )
                        _record_skip(_redis, cluster.id, f'stabilization_lock:{_stab_ttl}s')
                        continue
            except Exception:
                pass

            # ── STALE POOL RANKINGS WARNING + ABORT (Issue 9 + P-M4) ─────────
            # If global_pool_rankings:{region} is absent from Redis (cold cache,
            # Redis restart, or TTL expiry between hourly rebuilds), skip this
            # cluster entirely rather than falling through to the full DB pipeline.
            # With 15s cycles and many clusters, a cache miss → 240+ heavy DB calls
            # per hour → DB connection pool exhaustion. Warn once per hour.
            _pm4_skip_cluster = False
            try:
                if _redis:
                    _rank_region = cluster.region or 'us-east-1'
                    _rank_key = f'global_pool_rankings:{_rank_region}'
                    _rank_ttl = _redis.ttl(_rank_key)
                    if _rank_ttl is None or _rank_ttl == -2:  # key does not exist
                        _stale_warn_key = f'ranking_stale_warned:{_rank_region}'
                        # BUG-3 fix: atomic set — only one worker logs the CRITICAL
                        if _redis.set(_stale_warn_key, '1', nx=True, ex=3600):
                            logger.critical(
                                '[auto_rebalancer] CRITICAL: global_pool_rankings:%s is absent from Redis. '
                                'Skipping all clusters in this region until cache warms up. '
                                'Check build_global_pool_cache task and Redis health.',
                                _rank_region
                            )
                        _pm4_skip_cluster = True
            except Exception:
                pass
            # ── STEP 0: Sync real AWS instance state before any decisions ────
            # This ensures DB reflects actual AWS lifecycle, not assumed state.
            # Must run BEFORE the P-M4 rankings-absent skip so instance states stay
            # fresh even when the pool rankings cache is cold (Redis restart, etc.).
            try:
                _sync_instance_state_from_aws(db, cluster)
            except Exception as _sync_err:
                logger.warning(f"[auto_rebalancer] AWS sync failed for {cluster.name}: {_sync_err}")

            if _pm4_skip_cluster:
                # P-M4 fix: abort cluster cycle to prevent expensive DB pipeline on every beat
                # AWS sync above still runs so instance states remain fresh.
                _record_skip(_redis, cluster.id, 'pool_rankings_cache_absent') if _redis else None
                continue

            # ── KARPENTER NODEPOOL REFRESH ────────────────────────────────────
            # When Karpenter is installed, keep its NodePool updated with ML-ranked
            # spot pools every 30 min. Then fall through to cordon/drain/terminate
            # so managed-node-group (ASG) on-demand nodes are actually replaced.
            # The agent's TERMINATE_NODE uses ShouldDecrementDesiredCapacity=True so
            # the ASG won't relaunch a replacement — Karpenter provisions spot instead.
            _karpenter_mode = getattr(cluster, 'karpenter_mode', None)
            _karpenter_active = _karpenter_mode is not None  # any mode (AUTO or DRY_RUN)

            # Also check Redis heartbeat written by agent (set when Karpenter pods detected)
            try:
                _k_key = f"spot:karpenter:installed:{cluster.id}"
                if not _karpenter_active and _redis and _redis.exists(_k_key):
                    _karpenter_active = True
            except Exception:
                pass

            if _karpenter_active:
                # Update NodePool with current ML-ranked spot pools (30-min cooldown).
                # Use the backend's KarpenterService directly (requires no in-cluster agent)
                # so this works even when there are no running nodes.
                _nodepool_cooldown_key = f"spot:karpenter:nodepool_updated:{cluster.id}"
                try:
                    if _redis and not _redis.exists(_nodepool_cooldown_key):
                        try:
                            from backend.services.karpenter_service import KarpenterService
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            from backend.models.instance import Instance as _Inst
                            _od_inst = db.query(_Inst).filter(
                                _Inst.cluster_id == cluster.id,
                                _Inst.lifecycle == InstanceLifecycle.ON_DEMAND,
                                _Inst.instance_id.like('i-%')
                            ).first()
                            _src_type_np = _od_inst.instance_type if _od_inst else "t3.medium"
                            _specs_np = _INSTANCE_VCPU_MEM.get(_src_type_np, (2, 8))
                            _ranked_np = PoolRankingService(db, _redis).rank_pools_for_size(
                                vcpu=_specs_np[0], memory_gb=float(_specs_np[1]),
                                region=cluster.region or "ap-south-1", limit=10
                            )
                            if _ranked_np:
                                _top_pools = [
                                    {"instance_type": p.pool.instance_type,
                                     "az": p.pool.az,
                                     "ml_score": float(p.ml_score)}
                                    for p in _ranked_np
                                ]
                                _ksvc = KarpenterService(db, _redis)
                                _sync_result = _ksvc.sync_ml_rankings_to_nodepool(
                                    cluster_id=cluster.id,
                                    top_pools=_top_pools,
                                    nodepool_name="default"
                                )
                                if _sync_result.get("status") == "success":
                                    if _redis:
                                        _redis.setex(_nodepool_cooldown_key, 1800, "1")
                                    logger.info(
                                        f"[auto_rebalancer] Karpenter cluster {cluster.name}: "
                                        f"NodePool updated with {len(_top_pools)} ML-ranked pools "
                                        f"(direct backend call — no agent required)"
                                    )
                        except Exception as _ksvc_err:
                            logger.warning(
                                f"[auto_rebalancer] NodePool direct sync failed for "
                                f"{cluster.name}: {_ksvc_err}"
                            )
                except Exception as _kp_err:
                    logger.warning(
                        f"[auto_rebalancer] NodePool ML update failed for Karpenter "
                        f"cluster {cluster.name}: {_kp_err}"
                    )
                # NOTE: Do NOT continue here. Fall through to the cordon/drain/terminate
                # logic below so managed-node-group on-demand nodes are actually replaced.

            logger.info(f"[auto_rebalancer] CHECKPOINT-A cluster={cluster.name}")
            # ── GHOST INSTANCE CLEANUP ──────────────────────────────────────
            # Remove placeholder records (instance_id NOT like 'i-%') that were
            # created before the metrics.py guard was added. These ghost instances
            # pollute OD queries (blocking S2S) and show "unknown" in the UI.
            try:
                _ghost_updated = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    ~Instance.instance_id.like('i-%'),
                    ~Instance.instance_id.like('ip-%'),
                ).update({'state': 'terminated'}, synchronize_session=False)
                if _ghost_updated:
                    db.flush()
                    logger.info(
                        f"[auto_rebalancer] Cleaned up {_ghost_updated} ghost placeholder "
                        f"instance(s) for cluster {cluster.name}"
                    )
            except Exception as _ghost_err:
                logger.warning(f"[auto_rebalancer] Ghost cleanup failed for {cluster.name}: {_ghost_err}")
            # ── STALE ip- PLACEHOLDER CLEANUP ──────────────────────────────
            # ip- records (K8s hostname-style IDs) are stale when no running i-
            # instance has a matching node_name. Without this cleanup, stale OD
            # placeholders (e.g. ip-192-168-70-251) inflate _od_count and block S2S.
            try:
                _ip_placeholders = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    Instance.instance_id.like('ip-%'),
                ).all()
                if _ip_placeholders:
                    _real_node_names = set(
                        r[0] for r in db.query(Instance.node_name).filter(
                            Instance.cluster_id == cluster.id,
                            Instance.state == 'running',
                            Instance.instance_id.like('i-%'),
                            Instance.node_name.isnot(None),
                        ).all()
                    )
                    # If there are zero running i-* instances, skip cleanup entirely.
                    # Without any i-* records to compare against, ALL ip- placeholders
                    # would be marked stale — which is wrong when the cluster only has
                    # ip- records (e.g. agent reports K8s hostnames only, or all i-*
                    # records were terminated by failed rebalancing actions).
                    if not _real_node_names:
                        logger.debug(
                            f"[auto_rebalancer] Skipping stale ip- cleanup for "
                            f"{cluster.name}: no running i-* instances to compare"
                        )
                    else:
                        _stale_ip_count = 0
                        for _ip_rec in _ip_placeholders:
                            _ip_prefix = _ip_rec.instance_id  # e.g. 'ip-192-168-70-251'
                            _matched = any(
                                nm and (nm == _ip_prefix or nm.startswith(_ip_prefix + '.'))
                                for nm in _real_node_names
                            )
                            if not _matched:
                                _ip_rec.state = 'terminated'
                                _stale_ip_count += 1
                        if _stale_ip_count:
                            db.flush()
                            logger.info(
                                f"[auto_rebalancer] Cleaned up {_stale_ip_count} stale ip- "
                                f"placeholder(s) for cluster {cluster.name} "
                                f"(no matching running i- node_name)"
                            )
            except Exception as _ip_err:
                logger.warning(f"[auto_rebalancer] Stale ip- cleanup failed for {cluster.name}: {_ip_err}")
            # ── SAFETY GATE: OptimizerCoordinator phase (RC-5) ──────────────
            # Don't create new rebalancing actions while right-sizing is mid-execution
            try:
                from backend.models.optimizer_state import OptimizerState
                _opt = db.query(OptimizerState).filter(
                    OptimizerState.cluster_id == cluster.id
                ).first()
                if _opt and _opt.current_phase in ("RIGHTSIZING_EVALUATION", "COMBINED_EXECUTION"):
                    logger.info(
                        f"[auto_rebalancer] Skipping cluster {cluster.name}: "
                        f"optimizer in phase {_opt.current_phase} — would corrupt combined EV calculation"
                    )
                    try:
                        if _redis:
                            _record_skip(_redis, cluster.id, f'optimizer_phase:{_opt.current_phase}')
                    except Exception:
                        pass
                    continue
            except Exception:
                pass  # OptimizerState table may not exist; proceed safely

            # Enforce stateless runtime limits (max rebalances per 24h)
            stateless_rules = db.query(StatelessRuntimeRules).filter(StatelessRuntimeRules.cluster_id == cluster.id).first()
            max_rebalances = stateless_rules.max_rebalances_per_24h if stateless_rules else 5

            # Issue 2: Use Redis counter to avoid DB query every 15s.
            # Fall back to DB on Redis miss (cold start / eviction) and seed the counter.
            _count_key = f'spot:daily_count:{cluster.id}'
            try:
                _daily_count_raw = _redis.get(_count_key) if _redis else None
            except Exception:
                _daily_count_raw = None
            if _daily_count_raw is None:
                recent_rebalances = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cluster.id,
                    RebalancingAction.trigger == 'auto_rebalance',
                    RebalancingAction.status == 'completed',
                    RebalancingAction.started_at >= datetime.utcnow() - timedelta(hours=24)
                ).count()
                try:
                    if _redis:
                        _redis.setex(_count_key, 86400, recent_rebalances)
                except Exception:
                    pass
            else:
                recent_rebalances = int(_daily_count_raw)

            if recent_rebalances >= max_rebalances:
                # Daily limit is designed to prevent excessive SPOT→SPOT churn.
                # OD→SPOT conversions are always allowed — that's the core purpose
                # of the platform and should never be blocked by the churn limiter.
                # Use raw SQL to ensure fresh read (bypasses ORM identity cache).
                try:
                    _od_row = db.execute(
                        "SELECT COUNT(*) FROM instances "
                        "WHERE cluster_id = :cid AND state = 'running' "
                        "AND instance_id LIKE 'i-%' "
                        "AND lifecycle NOT IN ('spot', 'SPOT')",
                        {"cid": cluster.id}
                    ).scalar()
                    _pre_od_count = int(_od_row or 0)
                except Exception:
                    _pre_od_count = 0
                if _pre_od_count == 0:
                    # No OD nodes — only S2S work remains. S2S has its own per-node
                    # daily limit check (line ~3044) so do NOT continue here.
                    # Log the state for observability but fall through to S2S section.
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name}: daily limit reached "
                        f"({recent_rebalances}/{max_rebalances}) — no OD nodes, S2S will "
                        f"apply its own limit check"
                    )
                logger.info(
                    f"[auto_rebalancer] Daily limit reached ({recent_rebalances}/{max_rebalances}) "
                    f"but cluster {cluster.name} has {_pre_od_count} OD node(s) — "
                    f"bypassing limit for OD→spot conversion"
                )

            logger.info(f"[auto_rebalancer] CHECKPOINT-B cluster={cluster.name} recent={recent_rebalances}/{max_rebalances}")
            # ── ONE-AT-A-TIME GUARDRAIL ──────────────────────────────────────
            # Check if an AgentAction (cordon/drain/patch) is still in flight
            # for this cluster. If so, skip until it completes.
            # Auto-expire stale PENDING/PICKED_UP actions (> 5 min) — these are orphaned by
            # agent restarts and would block the rebalancer indefinitely otherwise.
            # PICKED_UP actions >5 min old: the agent that picked them up likely died
            # (e.g. the node being drained was terminated before the agent could execute).
            # PENDING actions >5 min old were never picked up and are effectively dead.
            from backend.models.agent_action import AgentAction, AgentActionStatus
            _expire_cutoff = datetime.utcnow() - timedelta(minutes=5)
            stale_count = db.query(AgentAction).filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP]),
                AgentAction.created_at < _expire_cutoff,
            ).update({"status": AgentActionStatus.EXPIRED}, synchronize_session=False)
            if stale_count:
                db.flush()
                logger.warning(
                    f"[auto_rebalancer] Expired {stale_count} stale PENDING/PICKED_UP AgentAction(s) "
                    f"for cluster {cluster.name} (>5 min old — agent not processing)"
                )
            active_agent_actions = db.query(AgentAction).filter(
                AgentAction.cluster_id == cluster.id,
                AgentAction.status.in_([AgentActionStatus.PENDING, AgentActionStatus.PICKED_UP])
            ).count()
            if active_agent_actions > 0:
                logger.info(
                    f"[auto_rebalancer] Skipping cluster {cluster.name}: "
                    f"{active_agent_actions} AgentAction(s) still in-flight — waiting for completion"
                )
                try:
                    if _redis:
                        _record_skip(_redis, cluster.id, f'agent_actions_in_flight:{active_agent_actions}')
                except Exception:
                    pass
                continue

            # ── PROACTIVE WARM STANDBY ────────────────────────────────────────
            # If maintain_standby=True and no standby node exists, launch one now.
            # This ensures a pre-warmed node is always available for fast failover.
            try:
                _sb_settings = db.query(ClusterOptimizationSettings).filter(
                    ClusterOptimizationSettings.cluster_id == cluster.id
                ).first()
                if _sb_settings and getattr(_sb_settings, "maintain_standby", False):
                    from backend.services.substitute_manager import SubstituteManager
                    _sb_mgr = SubstituteManager(db, _redis)
                    _sb_status = _sb_mgr.get_substitute_status(cluster.id)
                    _sb_active = (
                        _sb_status.get("is_warm_spare") or
                        _sb_status.get("state") in ("PREWARMING", "ACTIVE")
                    ) if _sb_status else False
                    if not _sb_active:
                        from backend.workers.tasks.standby import launch_standby_node
                        launch_standby_node.delay(cluster.id)
                        logger.info(
                            f"[auto_rebalancer] Proactive standby launch triggered for "
                            f"cluster {cluster.name} (maintain_standby=True, no standby found)"
                        )
            except Exception as _sb_err:
                logger.warning(f"[auto_rebalancer] Proactive standby check failed for {cluster.name}: {_sb_err}")

            # ── LAST-NODE SAFETY GUARD ────────────────────────────────────────
            # Never drain the very last running node — pods would have nowhere to go.
            # Correct logic: check TOTAL running nodes (OD + spot), not just OD count.
            # Example: 1 OD + 1 spot = 2 total → safe to drain the OD (spot absorbs pods).
            # Example: 1 OD + 0 spot = 1 total → unsafe, pods would have nowhere to go.
            _total_nodes = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.state == 'running',
                Instance.instance_id.like('i-%'),  # exclude ghost placeholders
            ).count()
            _od_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',
                Instance.instance_id.like('i-%'),  # exclude ghost placeholders
            ).count()
            if _total_nodes == 0:
                # Completely empty cluster — nothing to rebalance
                logger.info(f"[auto_rebalancer] Cluster {cluster.name}: no running instances — skipping")
                continue

            if _total_nodes == 1 and _od_count == 0:
                # Single SPOT node — cluster is already optimized.
                # Fall through to S2S risk checks only.
                logger.info(
                    f"[auto_rebalancer] Cluster {cluster.name}: 1 spot node, 0 OD nodes "
                    f"— skipping last-node guard, proceeding to S2S risk-threshold checks"
                )

            elif _total_nodes <= 1:
                if _karpenter_active:
                    # Karpenter is present — update NodePool via direct backend call
                    # (no in-cluster agent required) to signal spot provisioning.
                    # Do NOT cordon/drain yet; wait for spot node to appear.
                    _provision_key = f"spot:karpenter:provision_requested:{cluster.id}"
                    if _redis and not _redis.exists(_provision_key):
                        try:
                            from backend.services.karpenter_service import KarpenterService
                            from backend.services.pool_ranking_service import PoolRankingService
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                            _any_od = db.query(Instance).filter(
                                Instance.cluster_id == cluster.id,
                                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                                Instance.instance_id.like('i-%')
                            ).first()
                            _src_type = _any_od.instance_type if _any_od else "t3.medium"
                            _specs = _INSTANCE_VCPU_MEM.get(_src_type, (2, 8))
                            _ranked_np = PoolRankingService(db, _redis).rank_pools_for_size(
                                vcpu=_specs[0], memory_gb=float(_specs[1]),
                                region=cluster.region or "ap-south-1", limit=5
                            )
                            _top_np = [
                                {"instance_type": p.pool.instance_type, "az": p.pool.az, "ml_score": float(p.ml_score)}
                                for p in (_ranked_np or [])
                            ]
                            if _top_np:
                                _ksvc2 = KarpenterService(db, _redis)
                                _ksvc2.sync_ml_rankings_to_nodepool(
                                    cluster_id=cluster.id,
                                    top_pools=_top_np,
                                    nodepool_name="default"
                                )
                            if _redis:
                                _redis.setex(_provision_key, 900, "1")  # 15-min cooldown
                            logger.info(
                                f"[auto_rebalancer] Cluster {cluster.name}: only {_od_count} OD node(s) "
                                f"— updated Karpenter NodePool directly (cordon/drain deferred until spot appears)"
                            )
                        except Exception as _np_err:
                            logger.warning(
                                f"[auto_rebalancer] Last-node Karpenter NodePool update failed "
                                f"for {cluster.name}: {_np_err}"
                            )
                    else:
                        # Non-Karpenter clusters: skip — Karpenter must be installed first.
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: only {_total_nodes} total / "
                            f"{_od_count} OD node(s) — Karpenter not active, skipping last-node guard. "
                            f"Install Karpenter to enable spot provisioning."
                        )
                continue

            # Spot recovery for direct-EC2 launches removed — Karpenter handles
            # spot interruption recovery automatically via NodePool reconciliation.

            logger.info(f"[auto_rebalancer] CHECKPOINT-C cluster={cluster.name}")
            # ── KARPENTER PROVISIONING COOLDOWN ──────────────────────────────
            # After draining a node, wait 20 min AND check if Karpenter provisioned
            # a spot node. Only proceed if either a spot node exists OR 20 min elapsed.
            # This prevents cascade-draining all nodes before Karpenter provisions spot.
            last_completed_action = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status == 'completed',
                RebalancingAction.trigger == 'auto_rebalance',
                RebalancingAction.completed_at.isnot(None),
            ).order_by(RebalancingAction.completed_at.desc()).first()
            if last_completed_action and last_completed_action.completed_at:
                elapsed = (datetime.utcnow() - last_completed_action.completed_at).total_seconds()
                # Cooldown: user-configured (cooldown_override_minutes), default 60 min
                _cooldown_cfg = getattr(_opt_settings, 'cooldown_override_minutes', None) if _opt_settings else None
                _COOLDOWN = (_cooldown_cfg * 60) if (_cooldown_cfg and _cooldown_cfg > 0) else 3600
                if elapsed < _COOLDOWN:
                    # Cooldown prevents excessive S2S churn. OD→SPOT conversions always
                    # bypass it — converting OD to spot is the platform's primary purpose.
                    try:
                        _cd_od = db.execute(
                            "SELECT COUNT(*) FROM instances WHERE cluster_id = :cid "
                            "AND state = 'running' AND lifecycle NOT IN ('spot', 'SPOT')",
                            {"cid": cluster.id}
                        ).scalar()
                        _cd_od = int(_cd_od or 0)
                    except Exception:
                        _cd_od = 0
                    if _cd_od == 0:
                        # No OD nodes — check for diversification violations that also bypass
                        _cd_diversify_bypass = False
                        try:
                            _cd_opt_div = db.query(ClusterOptimizationSettings).filter_by(
                                cluster_id=cluster.id
                            ).first()
                            if getattr(_cd_opt_div, 'diversify_pools', False):
                                _cd_running = db.query(Instance).filter(
                                    Instance.cluster_id == cluster.id,
                                    Instance.state == 'running',
                                ).all()
                                _cd_pool_dist: dict = {}
                                for _cdr in _cd_running:
                                    if _cdr.instance_type and _cdr.az:
                                        _k = (_cdr.instance_type, _cdr.az)
                                        _cd_pool_dist[_k] = _cd_pool_dist.get(_k, 0) + 1
                                _cd_diversify_bypass = any(v > 1 for v in _cd_pool_dist.values())
                        except Exception:
                            pass
                        if not _cd_diversify_bypass:
                            logger.info(
                                f"[auto_rebalancer] Cluster {cluster.name}: strict {_COOLDOWN}s cooldown "
                                f"({int(_COOLDOWN - elapsed)}s remaining)"
                            )
                            continue
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: cooldown active "
                            f"({int(_COOLDOWN - elapsed)}s remaining) but diversify violation detected "
                            f"— bypassing cooldown for S2S diversification fix"
                        )
                    else:
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: cooldown active "
                            f"({int(_COOLDOWN - elapsed)}s remaining) but {_cd_od} OD node(s) "
                            f"— bypassing cooldown for OD→SPOT conversion"
                        )

            # Re-queue only the OLDEST deferred action (1 at a time per cluster)
            oldest_deferred = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status == 'deferred'
            ).order_by(RebalancingAction.started_at).first()
            if oldest_deferred:
                # OD nodes take priority over deferred S2S actions — check first.
                try:
                    _def_od = db.execute(
                        "SELECT COUNT(*) FROM instances WHERE cluster_id = :cid "
                        "AND state = 'running' AND lifecycle NOT IN ('spot', 'SPOT')",
                        {"cid": cluster.id}
                    ).scalar()
                    _def_od = int(_def_od or 0)
                except Exception:
                    _def_od = 0
                if _def_od > 0:
                    logger.info(
                        f"[auto_rebalancer] Skipping deferred action {oldest_deferred.id} re-queue: "
                        f"{_def_od} OD node(s) take priority for cluster {cluster.name}"
                    )
                    # Fall through to OD instance processing below
                else:
                    oldest_deferred.status = 'in_progress'
                    oldest_deferred.started_at = datetime.utcnow()
                    logger.info(f"Re-queuing deferred action {oldest_deferred.id} for cluster {cluster.name}")
                    # Don't create new actions this cycle — retry the deferred one first
                    continue

            logger.info(f"[auto_rebalancer] CHECKPOINT-D cluster={cluster.name}")
            # Issue 6: Cluster passed all gates — clear skip streak so stall detection resets.
            try:
                if _redis:
                    _record_active(_redis, cluster.id)
            except Exception:
                pass
            # Find on-demand instances that should be migrated to spot
            # IMPORTANT: state='running' filter prevents terminated OD instances
            # (instances already replaced in a previous cycle whose DB record hasn't
            # been cleaned up yet) from being retargeted — which caused an infinite loop
            # where the same "dead" OD node was queued for rebalancing over and over.
            on_demand_instances = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                Instance.state == 'running',   # Only target running OD nodes
                Instance.instance_id.like('i-%'),  # exclude ghost placeholder instances
                # notin_() excludes NULL rows in SQL — use or_() to include instances
                # whose status hasn't been set yet (nullable column, defaults to READY).
                or_(Instance.status.notin_(['UNKNOWN']), Instance.status.is_(None)),
            ).all()

            # ── REDIS FALLBACK: seed instances from agent telemetry if DB is empty ──
            # This handles the common case where the agent is running and sending
            # pod/node metrics but the instances table hasn't been populated yet
            # (no AWS discovery configured, or discovery hasn't run).
            if not on_demand_instances:
                _seeded = _seed_instances_from_redis(db, cluster)
                if _seeded:
                    logger.info(
                        f"[auto_rebalancer] Seeded {len(_seeded)} instance(s) from Redis "
                        f"for cluster {cluster.name} — proceeding with rebalancing"
                    )
                    on_demand_instances = _seeded
                else:
                    # No OD instances found — but SPOT instances may still need S2S
                    # diversification or risk-based migration. Only truly skip if there
                    # are no running instances at all (empty cluster).
                    _any_running = db.query(Instance).filter(
                        Instance.cluster_id == cluster.id,
                        Instance.state == 'running',
                    ).count()
                    if _any_running == 0:
                        logger.info(
                            f"[auto_rebalancer] No running instances for cluster {cluster.name} "
                            f"— skipping rebalancing this cycle"
                        )
                        continue
                    # else: fall through — S2S checks will run on spot instances below

            # ── PER-INSTANCE COOLDOWN: skip instances already rebalanced recently ──
            # After a successful rebalancing, a 24h Redis key is set for the instance.
            # This prevents the infinite loop where AWS sync resets lifecycle to ON_DEMAND
            # and the auto-rebalancer keeps re-targeting the same node.
            try:
                from backend.core.redis_client import get_redis_client as _grc_cd
                _redis_cd = _grc_cd()
                filtered_instances = []
                for inst in on_demand_instances:
                    _cd_key = f"spot:rebalanced:instance:{inst.instance_id}"
                    if _redis_cd.exists(_cd_key):
                        logger.debug(
                            f"[auto_rebalancer] Skipping instance {inst.instance_id}: "
                            f"recently rebalanced (24h cooldown active)"
                        )
                    else:
                        filtered_instances.append(inst)
                on_demand_instances = filtered_instances
            except Exception as _cd_err:
                logger.warning(f"[auto_rebalancer] Instance cooldown check failed: {_cd_err}")

            # ── CLASSIFICATION GUARD: skip nodes that WorkloadInspector hasn't classified yet ──
            # New nodes joining the cluster have a ~10-min window before classification runs.
            # If we try to replace a STATEFUL node mistakenly during that window we could lose
            # persistent data.
            #
            # Cache ABSENT (TTL expired or worker restart): skip the ENTIRE cluster this cycle
            # and trigger a fresh WorkloadInspector run. This prevents stateful nodes from
            # becoming eligible when their classification has expired.
            #
            # Cache PRESENT: filter out any individual nodes not yet classified.
            try:
                _wi_cache_key = f"spot:node_classification:{cluster.id}"
                _wi_raw = _redis.get(_wi_cache_key) if _redis else None
                if _wi_raw is None:
                    # Issue 7: Escalating logs for consecutive cache misses.
                    _miss_key = f'class_miss_streak:{cluster.id}'
                    try:
                        _miss_streak = int(_redis.incr(_miss_key)) if _redis else 1
                        if _redis:
                            _redis.expire(_miss_key, 90)
                        if _miss_streak == 1:
                            logger.debug(
                                '[auto_rebalancer] Cluster %s: classification cache absent, '
                                'running inline classification.',
                                cluster.name
                            )
                        elif 2 <= _miss_streak < 4:
                            logger.info(
                                '[auto_rebalancer] Cluster %s: classification cache absent for '
                                '%d consecutive cycles.',
                                cluster.name, _miss_streak
                            )
                        elif _miss_streak >= 4:
                            logger.warning(
                                '[auto_rebalancer] Cluster %s: classification cache absent for '
                                '%d cycles (>%ds). WorkloadInspector APScheduler job may be stalled.',
                                cluster.name, _miss_streak, _miss_streak * 15
                            )
                    except Exception:
                        pass
                    # Cache absent — run WorkloadInspector inline to build classification now.
                    # This keeps the rebalancer unblocked on first run or after cache expiry.
                    logger.info(
                        f"[auto_rebalancer] WorkloadInspector cache absent for {cluster.name} "
                        f"— running inline classification now."
                    )
                    try:
                        from backend.services.workload_inspector import WorkloadInspector as _WI
                        _wi_svc = _WI(_redis)
                        _wi_result = _wi_svc.scan_cluster(cluster.id)
                        if _wi_result:
                            _wi_raw = _redis.get(_wi_cache_key)  # re-read after scan
                            logger.info(
                                f"[auto_rebalancer] WorkloadInspector inline classification "
                                f"complete for {cluster.name}: {len(_wi_result)} nodes classified."
                            )
                        else:
                            raise ValueError("scan_cluster returned empty result")
                    except Exception as _wi_inline_err:
                        # K8s unreachable or scan failed — fall through with all-stateless default
                        # so the rebalancer is not permanently blocked by a missing K8s connection.
                        logger.warning(
                            f"[auto_rebalancer] Inline WorkloadInspector failed for "
                            f"{cluster.name}: {_wi_inline_err}. "
                            f"Treating all OD nodes as STATELESS_ELIGIBLE (safe default)."
                        )
                        import json as _json_wi_fb
                        _default_classification = {
                            inst.node_name: "STATELESS_ELIGIBLE"
                            for inst in on_demand_instances if inst.node_name
                        }
                        _redis.setex(_wi_cache_key, 300, _json_wi_fb.dumps(_default_classification))
                        _wi_raw = _redis.get(_wi_cache_key)
                else:
                    # Issue 7: Cache hit — reset miss streak counter.
                    try:
                        if _redis:
                            _redis.delete(f'class_miss_streak:{cluster.id}')
                    except Exception:
                        pass
                    import json as _json_wi
                    _wi_cache = _json_wi.loads(_wi_raw)
                    _unclassified = [
                        inst for inst in on_demand_instances
                        if inst.node_name and inst.node_name not in _wi_cache
                    ]
                    if _unclassified:
                        logger.info(
                            f"[auto_rebalancer] {len(_unclassified)} OD node(s) in {cluster.name} "
                            f"not yet classified by WorkloadInspector — skipping unclassified nodes"
                        )
                        on_demand_instances = [
                            inst for inst in on_demand_instances
                            if not inst.node_name or inst.node_name in _wi_cache
                        ]
            except Exception as _wi_err:
                logger.debug(f"[auto_rebalancer] Classification guard skipped: {_wi_err}")

            # ── TARGET SPOT EXPOSURE ENFORCEMENT ────────────────────────────────
            # Compute current spot ratio and limit the OD→Spot batch to only what
            # is needed to reach the configured target_spot_exposure_pct.
            # When target is already met, skip OD→Spot rebalancing entirely.
            _target_spot_pct = (getattr(_opt_settings, 'target_spot_exposure_pct', 100) or 100) if _opt_settings else 100
            if _target_spot_pct < 100 and on_demand_instances:
                _total_running = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).count()
                _spot_running = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                ).count()
                _current_spot_pct = (_spot_running / _total_running * 100) if _total_running > 0 else 0
                if _current_spot_pct >= _target_spot_pct:
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name}: spot ratio "
                        f"{_current_spot_pct:.0f}% already meets target {_target_spot_pct}% "
                        f"— skipping OD→Spot rebalancing"
                    )
                    on_demand_instances = []
                else:
                    # Only convert enough OD nodes to reach the target
                    _od_to_convert = max(1, int(
                        (_target_spot_pct - _current_spot_pct) / 100 * _total_running
                    ))
                    if _od_to_convert < len(on_demand_instances):
                        logger.info(
                            f"[auto_rebalancer] Cluster {cluster.name}: limiting OD batch from "
                            f"{len(on_demand_instances)} to {_od_to_convert} to reach "
                            f"target {_target_spot_pct}% (current {_current_spot_pct:.0f}%)"
                        )
                        on_demand_instances = on_demand_instances[:_od_to_convert]

            logger.info(f"[auto_rebalancer] CHECKPOINT-E cluster={cluster.name} od={len(on_demand_instances)}")
            if not on_demand_instances:
                # ── MIGRATION COMPLETION CHECK ──────────────────────────────────────
                # If all OD nodes are gone and managed node group hasn't been deleted
                # yet, trigger the cleanup task to finalize migration.
                if not getattr(cluster, 'managed_node_group_deleted', False):
                    _real_od_count = db.query(Instance).filter(
                        Instance.cluster_id == cluster.id,
                        Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
                        Instance.state == 'running',
                    ).count()
                    if _real_od_count == 0:
                        try:
                            from backend.workers.tasks.cleanup_tasks import cleanup_managed_node_group
                            cleanup_managed_node_group.delay(cluster.id)
                            logger.info(
                                f"[auto_rebalancer] Cluster {cluster.name}: zero OD instances — "
                                f"triggered cleanup_managed_node_group task"
                            )
                        except Exception as _cleanup_err:
                            logger.warning(
                                f"[auto_rebalancer] Failed to trigger cleanup task "
                                f"for {cluster.name}: {_cleanup_err}"
                            )

                # ── SPOT-TO-SPOT REBALANCING ────────────────────────────────────────
                # All ON_DEMAND nodes are migrated or in cooldown.
                # Now check SPOT nodes for:
                #   1. Diversify violations  — a family exceeds the 40% cap
                #   2. Risk-based migration  — current pool risk > 0.4 AND a
                #      significantly better alternative exists (Δrisk ≥ 0.15)
                # ───────────────────────────────────────────────────────────────────
                _spot_candidates = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state == 'running',
                ).all()

                if not _spot_candidates:
                    logger.info(
                        f"[auto_rebalancer] No ON_DEMAND or SPOT instances for cluster "
                        f"{cluster.name} — skipping cycle"
                    )
                    continue

                # Load opt settings for S2S checks
                _opt_s2s = db.query(ClusterOptimizationSettings).filter(
                    ClusterOptimizationSettings.cluster_id == cluster.id
                ).first()
                _diversify_s2s = getattr(_opt_s2s, 'diversify_pools', False)
                # When the cluster is already fully spot (optimized state),
                # trigger S2S only on risk-threshold breaches.
                _s2s_risk_only_mode = True
                logger.info(f"[auto_rebalancer] CHECKPOINT-F S2S diversify_s2s={_diversify_s2s} cluster={cluster.name}")
                _diversify_fam_cap_pct = getattr(_opt_s2s, 'max_family_diversification_cap_pct', 40) or 40
                _diversify_fam_cap_ratio = _diversify_fam_cap_pct / 100.0
                import math as _math_s2s

                # Load risk strategy (risk ceiling + tradeoff %) for S2S decisions
                try:
                    from backend.models.cluster import OptimizationStrategy as _OptS_s2s
                    _opt_strat_s2s = db.query(_OptS_s2s).filter_by(cluster_id=cluster.id).first()
                    _risk_ceil_s2s = (getattr(_opt_strat_s2s, 'risk_ceiling_percent', 25) or 25) / 100.0
                    _tradeoff_pct_s2s = (getattr(_opt_strat_s2s, 'risk_savings_tradeoff_pct', 20) or 20) / 100.0
                except Exception:
                    _risk_ceil_s2s = 0.25
                    _tradeoff_pct_s2s = 0.20
                # Apply regional market factor to S2S risk ceiling (clamped 0.8–1.2)
                try:
                    _mf_raw_s2s = _redis.get(f"market_factor:{cluster.region or 'ap-south-1'}")
                    _risk_ceil_s2s *= float(_mf_raw_s2s) if _mf_raw_s2s else 1.0
                except Exception:
                    pass

                # Pool distribution across ALL currently running nodes
                _all_running_s2s = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                ).all()
                # pool_counts_s2s: (instance_type, az) → count for pool-level uniqueness
                _pool_counts_s2s: dict = {}
                _fam_counts_s2s: dict = {}  # kept for legacy risk-check pass
                for _sri in _all_running_s2s:
                    if _sri.instance_type and _sri.az:
                        _spk = (_sri.instance_type, _sri.az)
                        _pool_counts_s2s[_spk] = _pool_counts_s2s.get(_spk, 0) + 1
                    if _sri.instance_type:
                        _f = _sri.instance_type.split('.')[0]
                        _fam_counts_s2s[_f] = _fam_counts_s2s.get(_f, 0) + 1
                _total_running_s2s = max(1, len(_all_running_s2s))

                _s2s_created = False
                for _sp_inst in _spot_candidates:
                    if not _sp_inst.instance_id or not _sp_inst.instance_id.startswith('i-'):
                        continue

                    # Per-instance cooldown
                    try:
                        if _redis_cd.exists(f"spot:rebalanced:instance:{_sp_inst.instance_id}"):
                            continue
                    except Exception:
                        pass

                    # S2S suppression after fallback (set when capacity caused fallback)
                    try:
                        if _redis_cd.exists(f"spot:s2s_suppressed:{_sp_inst.instance_id}"):
                            continue
                    except Exception:
                        pass

                    # Post-launch cooldown — skip S2S for 60s after a spot was just launched
                    # to let AWS metadata propagate and the node settle in K8s
                    try:
                        if _redis_cd.exists(f"spot:post_launch_cooldown:{_sp_inst.instance_id}"):
                            continue
                    except Exception:
                        pass

                    # Active-action guard: only 1 migration at a time per cluster
                    _active_s2s = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent'])
                    ).first()
                    if _active_s2s:
                        break
                    # Daily limit guard: diversify violations always bypass (correctness,
                    # not churn); risk-based S2S is subject to the per-cluster limit.
                    _s2s_is_diversify = False
                    if (not _s2s_risk_only_mode) and _diversify_s2s and _sp_inst.instance_type and _sp_inst.az:
                        _sp_pool_key_s2s_pre = (_sp_inst.instance_type, _sp_inst.az)
                        _s2s_is_diversify = _pool_counts_s2s.get(_sp_pool_key_s2s_pre, 0) > 1
                    if recent_rebalances >= max_rebalances and not _s2s_is_diversify:
                        break  # over limit + no diversify violation → skip

                    _s2s_trigger_reason = None
                    _cur_risk_s2s = None  # may remain None if Check 2 is skipped (diversify trigger)

                    # ── Check 0: Opportunistic better-pool trigger ────────────────
                    # If a pool exists that is BOTH cheaper (higher savings) AND safer
                    # (lower risk) than the current pool, always migrate — no other
                    # condition required. Dynamic thresholds adapt to node risk and
                    # market volatility (changes.md §7).
                    _S2S_OPP_RISK_DELTA  = 0.05   # base: pool must be ≥5pp lower risk
                    _S2S_OPP_SAV_DELTA   = 0.01   # base: pool must be ≥1pp higher savings
                    # Dynamic: widen thresholds when market is volatile, tighten when node is risky
                    try:
                        _vol_key = f"volatility_regime:{cluster.region or 'ap-south-1'}"
                        _vol_regime = (_redis.get(_vol_key) or b"NORMAL").decode()
                        _vol_boost = 0.02 if _vol_regime == "HIGH" else (0.04 if _vol_regime == "CRITICAL" else 0.0)
                        _S2S_OPP_RISK_DELTA += _vol_boost
                        _S2S_OPP_SAV_DELTA  += _vol_boost * 0.5
                    except Exception:
                        pass
                    if not _s2s_trigger_reason and _sp_inst.instance_type and not _s2s_risk_only_mode:
                        try:
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM_opp
                            from backend.services.pool_ranking_service import PoolRankingService as _PRS_opp
                            _opp_specs = _IVM_opp.get(_sp_inst.instance_type, (2, 8))
                            _opp_ranked = _PRS_opp(db, _redis).rank_pools_for_size(
                                vcpu=_opp_specs[0], memory_gb=float(_opp_specs[1]),
                                region=cluster.region or 'ap-south-1', limit=10
                            )
                            if _opp_ranked:
                                _opp_cur = next(
                                    (_rp for _rp in _opp_ranked
                                     if _rp.pool.instance_type == _sp_inst.instance_type and
                                     (_rp.pool.az or "") == (_sp_inst.az or "")),
                                    None
                                )
                                if _opp_cur:
                                    _opp_cur_risk = _opp_cur.risk_probability
                                    _opp_cur_sav  = _opp_cur.predicted_savings
                                    _opp_better = next(
                                        (_rp for _rp in _opp_ranked
                                         if (_rp.pool.instance_type, _rp.pool.az or "") !=
                                            (_sp_inst.instance_type, _sp_inst.az or "")
                                         and _rp.risk_probability <= _opp_cur_risk - _S2S_OPP_RISK_DELTA
                                         and _rp.predicted_savings >= _opp_cur_sav + _S2S_OPP_SAV_DELTA),
                                        None
                                    )
                                    if _opp_better:
                                        _cur_risk_s2s = _opp_cur_risk
                                        _s2s_trigger_reason = (
                                            f'opportunistic: {_opp_better.pool.instance_type}:{_opp_better.pool.az} '
                                            f'risk {_opp_cur_risk:.2f}→{_opp_better.risk_probability:.2f} '
                                            f'sav {_opp_cur_sav:.2f}→{_opp_better.predicted_savings:.2f}'
                                        )
                                        logger.info(
                                            f"[auto_rebalancer] S2S opportunistic trigger: "
                                            f"{_sp_inst.instance_id} ({_sp_inst.instance_type}:{_sp_inst.az}) "
                                            f"— {_s2s_trigger_reason}"
                                        )
                        except Exception as _opp_err:
                            logger.debug(f'[auto_rebalancer] S2S opportunistic check: {_opp_err}')

                    # ── Check 1: Diversify violation (pool-level) ─────────────────
                    # Pool = (instance_type, az). If >1 node shares the same pool, trigger S2S.
                    if (not _s2s_risk_only_mode) and _diversify_s2s and _sp_inst.instance_type and _sp_inst.az:
                        _sp_pool_key_s2s = (_sp_inst.instance_type, _sp_inst.az)
                        _sp_pool_count = _pool_counts_s2s.get(_sp_pool_key_s2s, 0)
                        if _sp_pool_count > 1:
                            _s2s_trigger_reason = (
                                f'diversify_pools: duplicate pool '
                                f'{_sp_inst.instance_type}:{_sp_inst.az} '
                                f'({_sp_pool_count} nodes)'
                            )
                            logger.info(
                                f"[auto_rebalancer] S2S diversify trigger: "
                                f"{_sp_inst.instance_id} ({_sp_inst.instance_type}:{_sp_inst.az}) "
                                f"— {_s2s_trigger_reason}"
                            )
                            
                        # ── Check 1.5: Diversify violation (family-level) ─────────────
                        if not _s2s_trigger_reason and _sp_inst.instance_type:
                            _f = _sp_inst.instance_type.split('.')[0]
                            _f_count = _fam_counts_s2s.get(_f, 0)
                            # Use ceiling so small clusters are handled correctly:
                            # ceil(0.40 * 3) = 2 — a family is only "over cap" when it
                            # holds strictly MORE than the ceiling limit.
                            _fam_cap_nodes = max(1, _math_s2s.ceil(_diversify_fam_cap_ratio * _total_running_s2s))
                            if _total_running_s2s > 0 and _f_count > _fam_cap_nodes:
                                _s2s_trigger_reason = (
                                    f'diversify_family: family {_f} exceeds cap '
                                    f'({_f_count}/{_total_running_s2s} > {_diversify_fam_cap_pct}%)'
                                )
                                logger.info(
                                    f"[auto_rebalancer] S2S diversify trigger: "
                                    f"{_sp_inst.instance_id} ({_sp_inst.instance_type}:{_sp_inst.az}) "
                                    f"— {_s2s_trigger_reason}"
                                )

                    # ── Check 2: Risk-threshold trigger (uses OptimizationStrategy) ──
                    # Fires when the node's pool risk > risk_ceiling_percent.
                    # Uses the user-configured risk ceiling (default 25%).
                    if not _s2s_trigger_reason and _sp_inst.instance_type:
                        try:
                            from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM2
                            from backend.services.pool_ranking_service import PoolRankingService as _PRS2
                            _sp_specs = _IVM2.get(_sp_inst.instance_type, (2, 8))
                            _sp_ranked = _PRS2(db, _redis).rank_pools_for_size(
                                vcpu=_sp_specs[0], memory_gb=float(_sp_specs[1]),
                                region=cluster.region or 'ap-south-1', limit=10
                            )
                            if _sp_ranked:
                                _cur_risk_s2s = next(
                                    (_rp.risk_probability for _rp in _sp_ranked
                                     if _rp.pool.instance_type == _sp_inst.instance_type and
                                     (_rp.pool.az or "") == (_sp_inst.az or "")),
                                    next(
                                        (_rp.risk_probability for _rp in _sp_ranked
                                         if _rp.pool.instance_type == _sp_inst.instance_type),
                                        None
                                    )
                                )
                                if _cur_risk_s2s is not None and _cur_risk_s2s > _risk_ceil_s2s:
                                    _s2s_trigger_reason = (
                                        f'risk_threshold: {_sp_inst.instance_type}:{_sp_inst.az} '
                                        f'risk={_cur_risk_s2s:.2f} > ceil={_risk_ceil_s2s:.2f}'
                                    )
                        except Exception as _rck_err:
                            logger.debug(f'[auto_rebalancer] S2S risk check: {_rck_err}')

                    if not _s2s_trigger_reason:
                        continue  # this SPOT node is fine, check the next one

                    # ── Find best target pool (pool-level uniqueness + tradeoff) ──
                    try:
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM as _IVM3
                        from backend.services.pool_ranking_service import PoolRankingService as _PRS3
                        _sp_specs3 = _IVM3.get(_sp_inst.instance_type, (2, 8))
                        _sp_ranked3 = _PRS3(db, _redis).rank_pools_for_size(
                            vcpu=_sp_specs3[0], memory_gb=float(_sp_specs3[1]),
                            region=cluster.region or 'ap-south-1', limit=10
                        )
                        # Current node's savings baseline (for tradeoff calc)
                        _sp_cur_savings = next(
                            (_rp.predicted_savings for _rp in _sp_ranked3
                             if _rp.pool.instance_type == _sp_inst.instance_type and
                             (_rp.pool.az or "") == (_sp_inst.az or "")),
                            0.5  # assume moderate savings if not found
                        )
                        _best_s2s_pool = None
                        # Is this a diversification-triggered S2S?
                        _is_diversify_trigger = 'diversify' in (_s2s_trigger_reason or '')
                        # Pass 1: better risk AND equal/higher savings
                        for _rp3 in _sp_ranked3:
                            _t3_pk = (_rp3.pool.instance_type, _rp3.pool.az or "")
                            _t3_f = _rp3.pool.instance_type.split('.')[0]
                            if _t3_pk == (_sp_inst.instance_type, _sp_inst.az or ""):
                                continue  # never re-migrate to same pool

                            # Ceiling-based family cap: ceil(cap% × total) → each family
                            # may hold at most that many nodes. This prevents the raw-ratio
                            # check from blocking all alternatives on small clusters.
                            # e.g. 3 nodes, 40% cap → ceil(1.2)=2; adding 1 to empty family
                            # gives count=1 ≤ 2 → PASSES (was 33% > 40% raw → would block).
                            _fam_cap_nodes_tgt = max(1, _math_s2s.ceil(_diversify_fam_cap_ratio * _total_running_s2s))
                            if _diversify_s2s:
                                if _pool_counts_s2s.get(_t3_pk, 0) > 0:
                                    continue  # target pool already occupied
                                _cur_t3_f_count = _fam_counts_s2s.get(_t3_f, 0)
                                if _cur_t3_f_count + 1 > _fam_cap_nodes_tgt:
                                    continue  # family would exceed ceiling cap

                            if (_rp3.risk_probability < (_cur_risk_s2s or 1.0) and
                                    _rp3.predicted_savings >= _sp_cur_savings):
                                _best_s2s_pool = _rp3
                                break
                        # Pass 2 (tradeoff): better risk, accept up to tradeoff% less savings.
                        # ONLY for risk-threshold trigger — opportunistic/diversify must not
                        # sacrifice savings (user condition: must be BOTH cheaper AND safer).
                        if not _best_s2s_pool and 'risk_threshold' in (_s2s_trigger_reason or ''):
                            _min_sav = _sp_cur_savings * (1 - _tradeoff_pct_s2s)
                            for _rp3 in _sp_ranked3:
                                _t3_pk = (_rp3.pool.instance_type, _rp3.pool.az or "")
                                _t3_f = _rp3.pool.instance_type.split('.')[0]
                                if _t3_pk == (_sp_inst.instance_type, _sp_inst.az or ""):
                                    continue

                                if _diversify_s2s:
                                    if _pool_counts_s2s.get(_t3_pk, 0) > 0:
                                        continue
                                    _cur_t3_f_count = _fam_counts_s2s.get(_t3_f, 0)
                                    if _cur_t3_f_count + 1 > _fam_cap_nodes_tgt:
                                        continue

                                if (_rp3.risk_probability < (_cur_risk_s2s or 1.0) and
                                        _rp3.predicted_savings >= _min_sav):
                                    _best_s2s_pool = _rp3
                                    break
                        # Pass 3 (diversify any-pool): for diversification triggers, accept
                        # ANY unoccupied pool from a different family — correctness over optimality.
                        if not _best_s2s_pool and _is_diversify_trigger and _diversify_s2s:
                            for _rp3 in _sp_ranked3:
                                _t3_pk = (_rp3.pool.instance_type, _rp3.pool.az or "")
                                _t3_f = _rp3.pool.instance_type.split('.')[0]
                                if _t3_pk == (_sp_inst.instance_type, _sp_inst.az or ""):
                                    continue
                                _cur_t3_f_count = _fam_counts_s2s.get(_t3_f, 0)
                                # Don't migrate to a DIFFERENT node in the SAME over-represented family
                                if _cur_t3_f_count + 1 > _fam_cap_nodes_tgt:
                                    continue
                                if _pool_counts_s2s.get(_t3_pk, 0) == 0:
                                    _best_s2s_pool = _rp3
                                    break

                        if not _best_s2s_pool:
                            # Pass 3 (OD fallback): if risk is the trigger and no spot pool
                            # qualifies, fall back to same-type on-demand to maintain capacity.
                            # Diversification violations just retry next cycle (no OD needed).
                            if 'risk_threshold' in (_s2s_trigger_reason or ''):
                                _s2s_od_src = f"{_sp_inst.instance_type}:{_sp_inst.az or cluster.region + 'a'}"
                                _s2s_od_action = RebalancingAction(
                                    cluster_id=cluster.id,
                                    trigger='auto_rebalance',
                                    source_pool=_s2s_od_src,
                                    target_pool=_s2s_od_src,  # same type, OD lifecycle
                                    source_instance_id=_sp_inst.instance_id,
                                    status='in_progress',
                                    started_at=datetime.utcnow(),
                                    action_metadata={
                                        'reason': f'{_s2s_trigger_reason} (od_fallback)',
                                        'initiated_by': 'auto_rebalancer',
                                        'instance_id': _sp_inst.instance_id,
                                        'spot_to_spot': False,
                                        'is_od_fallback': True,
                                        'target_instance_type': _sp_inst.instance_type,
                                        'bin_packed': False,
                                    }
                                )
                                db.add(_s2s_od_action)
                                _s2s_created = True
                                logger.info(
                                    f'[auto_rebalancer] S2S OD fallback: no safer spot pool for '
                                    f'{_sp_inst.instance_id} ({_sp_inst.instance_type}) — '
                                    f'replacing with on-demand (reason={_s2s_trigger_reason})'
                                )
                            else:
                                logger.info(
                                    f'[auto_rebalancer] S2S: no qualifying target pool for '
                                    f'{_sp_inst.instance_id} (risk={_cur_risk_s2s}, '
                                    f'tradeoff={_tradeoff_pct_s2s:.0%}) — will retry next cycle'
                                )
                            continue

                        _s2s_src = f"{_sp_inst.instance_type}:{_sp_inst.az or cluster.region + 'a'}"
                        _s2s_tgt = f"{_best_s2s_pool.pool.instance_type}:{_best_s2s_pool.pool.az}"

                        # Fix #10: S2S infinite migration loop prevention.
                        # Check if this source→target pair was migrated in the last 2 hours.
                        # Without this, the same pair can be re-triggered every 15s cycle.
                        _s2s_dedup_key = f"s2s_migration:{cluster.id}:{_s2s_src}:{_s2s_tgt}"
                        try:
                            if _redis and _redis.exists(_s2s_dedup_key):
                                logger.info(
                                    f"[auto_rebalancer] S2S dedup: {_s2s_src}→{_s2s_tgt} "
                                    f"migrated recently (2h window) — skipping to prevent loop"
                                )
                                continue
                        except Exception:
                            pass

                        _s2s_action = RebalancingAction(
                            cluster_id=cluster.id,
                            trigger='auto_rebalance',
                            source_pool=_s2s_src,
                            target_pool=_s2s_tgt,
                            source_instance_id=_sp_inst.instance_id,
                            status='in_progress',
                            started_at=datetime.utcnow(),
                            action_metadata={
                                'reason': _s2s_trigger_reason,
                                'initiated_by': 'auto_rebalancer',
                                'instance_id': _sp_inst.instance_id,
                                'spot_to_spot': True,
                                'target_instance_type': _best_s2s_pool.pool.instance_type,
                                'bin_packed': False,
                            }
                        )
                        db.add(_s2s_action)
                        _s2s_created = True
                        # Write dedup key so same pair is not re-triggered for 2 hours
                        try:
                            if _redis:
                                _redis.setex(_s2s_dedup_key, 7200, "1")
                        except Exception:
                            pass
                        logger.info(
                            f'[auto_rebalancer] SPOT→SPOT action created: '
                            f'{_sp_inst.instance_id} ({_s2s_src} → {_s2s_tgt}) '
                            f'reason={_s2s_trigger_reason} (2h dedup key set)'
                        )
                        break
                    except Exception as _s2s_err:
                        logger.error(f'[auto_rebalancer] S2S action creation error: {_s2s_err}')

                if not _s2s_created:
                    logger.debug(
                        f'[auto_rebalancer] No SPOT→SPOT migration needed for '
                        f'cluster {cluster.name} this cycle'
                    )
                continue  # done with this cluster for this cycle

            # ── SPOT INFO ─────────────────────────────────────────────────────────
            _running_spot_count = db.query(Instance).filter(
                Instance.cluster_id == cluster.id,
                Instance.lifecycle == InstanceLifecycle.SPOT,
                Instance.state == 'running',
            ).count()
            _total_running = _running_spot_count + len(on_demand_instances)
            logger.debug(
                f"[auto_rebalancer] Cluster {cluster.name}: "
                f"{_running_spot_count} running spot, {len(on_demand_instances)} remaining OD"
            )

            # ── DYNAMIC AUTOSCALER (delegated to auto_scaler.py) ──────────────
            # Capacity management is handled by backend/workers/tasks/auto_scaler.py.
            # That task runs every 30 seconds and is enabled per-cluster via the
            # `enable_ascp_auto_scaler` toggle in ClusterOptimizationSettings.
            # When the toggle is OFF (default) no automatic scaling occurs here.

            # ── SEMAPHORE RECONCILIATION ─────────────────────────────────
            # Self-heal: sync the Redis semaphore with actual active action count.
            # Without this, a crash or error path that skips DECR leaves the
            # semaphore stuck, permanently blocking new actions for this cluster.
            try:
                _sem_reconcile_key = f"rebalance:active_count:{cluster.id}"
                _actual_active = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cluster.id,
                    RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent']),
                ).count()
                _sem_stale = int(_redis.get(_sem_reconcile_key) or 0)
                if _sem_stale != _actual_active:
                    logger.info(
                        f"[auto_rebalancer] Semaphore reconciliation: {cluster.name} "
                        f"redis={_sem_stale} actual={_actual_active} — correcting"
                    )
                    _redis.set(_sem_reconcile_key, _actual_active, ex=300)
            except Exception:
                pass

            # ── BATCH SIZE LIMITING (PDB-aware) ─────────────────────────────
            # Determine how many nodes we can target this cycle based on
            # rebalance_batch_percent and PDB safety. This caps the iteration
            # list so we don't create more actions than the batch allows.
            _batch_percent = 15  # default: 15% of target nodes
            if _opt_settings and getattr(_opt_settings, 'rebalance_batch_percent', None) is not None:
                _batch_percent = _opt_settings.rebalance_batch_percent
                if _batch_percent == 0:
                    logger.info(f"[auto_rebalancer] Batch percent is 0% for {cluster.name} — skipping rebalance cycle")
                    continue
            else:
                # No user override — use PDB-safe value if respect_pdb_enabled
                _stateless_rules = getattr(cluster, 'stateless_rules', None)
                if _stateless_rules and getattr(_stateless_rules, 'respect_pdb_enabled', True):
                    try:
                        from backend.services.pdb_service import get_pdb_safe_percent_for_cluster
                        _pdb_safe = get_pdb_safe_percent_for_cluster(cluster, db)
                        if _pdb_safe is not None:
                            _batch_percent = _pdb_safe
                    except Exception:
                        pass  # Fall back to default 15%

            # If respect_pdb_enabled, always cap to PDB-safe limit
            _stateless_rules = getattr(cluster, 'stateless_rules', None)
            if _stateless_rules and getattr(_stateless_rules, 'respect_pdb_enabled', True):
                try:
                    from backend.services.pdb_service import get_pdb_safe_percent_for_cluster
                    _pdb_cap = get_pdb_safe_percent_for_cluster(cluster, db)
                    if _pdb_cap is not None:
                        _batch_percent = min(_batch_percent, _pdb_cap)
                except Exception:
                    pass

            _batch_size = max(1, int(len(on_demand_instances) * _batch_percent / 100))
            _batch_candidates = on_demand_instances[:_batch_size]
            logger.debug(
                f"[auto_rebalancer] Batch sizing: {cluster.name} "
                f"total_od={len(on_demand_instances)} batch_pct={_batch_percent}% "
                f"batch_size={_batch_size}"
            )

            for instance in _batch_candidates:
                # Skip placeholder instances (daemon-set auto-created with ip- hostname as ID).
                # They don't have real EC2 IDs and can't be used for spot launch.
                if not instance.instance_id or not instance.instance_id.startswith('i-'):
                    logger.debug(
                        f"[auto_rebalancer] Skipping placeholder instance {instance.instance_id} "
                        f"(not a real EC2 ID) for cluster {cluster.name}"
                    )
                    continue

                # ── LIVE AWS LIFECYCLE VERIFICATION ─────────────────────────────
                # Confirm from AWS that this instance is really ON_DEMAND before
                # targeting it. Karpenter-provisioned spot nodes can briefly appear
                # as ON_DEMAND in the DB due to discovery race conditions.
                #
                # Credential availability: try assumed-role first, then platform creds.
                # If NO credentials are available (dev/demo env), TRUST the DB and proceed.
                # The discovery worker keeps lifecycle in sync; skipping all instances
                # every cycle because credentials aren't configured defeats the purpose.
                try:
                    _lv_creds = {}
                    try:
                        from backend.utils.aws.asg import get_assumed_credentials as _get_creds_lv
                        _lv_creds = _get_creds_lv(cluster, db)
                    except Exception:
                        pass  # STS/assume-role failed — fall through to platform creds

                    if not _lv_creds:
                        # No cross-account role — try platform credentials
                        try:
                            from backend.models.system_config import SystemConfig as _SC_lv
                            _pk_lv = db.query(_SC_lv).filter(_SC_lv.key == "PLATFORM_AWS_ACCESS_KEY").first()
                            _ps_lv = db.query(_SC_lv).filter(_SC_lv.key == "PLATFORM_AWS_SECRET").first()
                            if _pk_lv and _ps_lv and _pk_lv.value and _ps_lv.value:
                                _lv_creds = {
                                    'access_key': _pk_lv.value,
                                    'secret_key': _ps_lv.value,
                                }
                                logger.info(
                                    f"[auto_rebalancer] Using platform credentials for live lifecycle check "
                                    f"on {cluster.name}"
                                )
                        except Exception as _plat_cred_err:
                            logger.debug(f"[auto_rebalancer] Platform creds unavailable: {_plat_cred_err}")

                    # Only attempt live check for real EC2 instance IDs (i-xxx)
                    if not instance.instance_id or not instance.instance_id.startswith('i-'):
                        logger.info(
                            f"[auto_rebalancer] Live check skipped: {instance.instance_id} is not "
                            f"a real EC2 ID — marking terminated"
                        )
                        instance.state = 'terminated'
                        db.commit()
                        continue

                    if not _lv_creds:
                        # No credentials available — trust DB lifecycle and proceed
                        logger.info(
                            f"[auto_rebalancer] No AWS credentials for live check on "
                            f"{instance.instance_id} — trusting DB (lifecycle={instance.lifecycle})"
                        )
                        # Fall through: proceed with rebalancing based on DB data
                    else:
                        import boto3 as _boto3_lv
                        _ec2_lv = _boto3_lv.client(
                            'ec2',
                            region_name=cluster.region or 'ap-south-1',
                            aws_access_key_id=_lv_creds.get('aws_access_key_id') or _lv_creds.get('access_key'),
                            aws_secret_access_key=_lv_creds.get('aws_secret_access_key') or _lv_creds.get('secret_key'),
                            aws_session_token=_lv_creds.get('aws_session_token') or _lv_creds.get('session_token'),
                        )
                        _resp_lv = _ec2_lv.describe_instances(InstanceIds=[instance.instance_id])
                        _aws_inst_lv = None
                        for _r in _resp_lv.get('Reservations', []):
                            for _i in _r.get('Instances', []):
                                if _i.get('InstanceId') == instance.instance_id:
                                    _aws_inst_lv = _i
                                    break
                        if _aws_inst_lv:
                            _aws_lc = _aws_inst_lv.get('InstanceLifecycle', 'on-demand')
                            if _aws_lc == 'spot':
                                # AWS says SPOT — correct the DB and skip this instance
                                instance.lifecycle = InstanceLifecycle.SPOT
                                db.commit()
                                _cd_key_lv = f"spot:rebalanced:instance:{instance.instance_id}"
                                try:
                                    get_redis_client().set(_cd_key_lv, '1', ex=86400)
                                except Exception:
                                    pass
                                logger.info(
                                    f"[auto_rebalancer] Live AWS check: {instance.instance_id} is SPOT "
                                    f"(DB was stale ON_DEMAND). Corrected + set 24h cooldown."
                                )
                                continue
                            # AWS confirmed ON_DEMAND — safe to proceed with rebalancing
                        else:
                            # Instance not found in AWS → already terminated, skip
                            logger.info(
                                f"[auto_rebalancer] Live AWS check: {instance.instance_id} not found "
                                f"in AWS — likely already terminated, skipping."
                            )
                            instance.state = 'terminated'
                            db.commit()
                            continue
                except Exception as _lv_err:
                    # Unexpected error — log and proceed (don't block rebalancing)
                    logger.warning(
                        f"[auto_rebalancer] Live lifecycle check error for {instance.instance_id}: "
                        f"{_lv_err} — trusting DB and proceeding"
                    )

                # Check daily limit — OD→spot conversions always bypass (see cluster-level check above)
                if (recent_rebalances) >= max_rebalances:
                    # instance here is always OD (we're in on_demand_instances loop)
                    # so we allow it through. Only break if this instance is somehow spot.
                    if instance.lifecycle != InstanceLifecycle.ON_DEMAND:
                        logger.info(f"Hit daily limit for cluster {cluster.name}")
                        break

                # ── CLUSTER GROWTH GUARD #1: termination-failed cooldown ───────
                # If we previously tried to terminate this instance and it failed,
                # don't immediately create another action → cluster would grow.
                try:
                    if _redis.get(f"spot:term_failed:{instance.instance_id}"):
                        logger.info(
                            f"[auto_rebalancer] Skipping {instance.instance_id}: "
                            f"termination recently failed (cooldown active). "
                            f"Mark instance as orphan for manual cleanup."
                        )
                        # Mark the stuck instance as orphan so UI can surface it
                        instance.state = 'orphan'
                        db.commit()
                        continue
                except Exception:
                    pass

                # ── FIX #15: Per-instance daily cap (10 attempts/day) ────────────────
                # Prevents unbounded retry loop for a persistently failing cluster.
                # Tracked in Redis: rebalance_daily_count:{instance_id}:{date_utc}
                # Key expires at end of UTC day.
                try:
                    import time as _time_dlc
                    _dlc_date = datetime.utcnow().strftime('%Y-%m-%d')
                    _dlc_key = f"rebalance_daily_count:{instance.instance_id}:{_dlc_date}"
                    _dlc_count = int(_redis.get(_dlc_key) or 0)
                    _MAX_PER_INSTANCE_DAILY = 10
                    if _dlc_count >= _MAX_PER_INSTANCE_DAILY:
                        logger.info(
                            f"[auto_rebalancer] Per-instance daily cap hit for "
                            f"{instance.instance_id} ({_dlc_count}/{_MAX_PER_INSTANCE_DAILY}) "
                            f"— skipping until tomorrow UTC"
                        )
                        continue
                except Exception:
                    pass

                # ── CLUSTER GROWTH GUARD #2: recent completed action for this instance ──
                # If a completed action already ran for this source instance in the last
                # 2 hours (e.g. terminate succeeded but DB state wasn't updated yet),
                # skip it to prevent duplicate replacements.
                # For failed actions, only skip (cooldown) — do NOT mark terminated
                # because the source node was never touched.
                try:
                    _recent_completed = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(['completed', 'failed']),
                        RebalancingAction.completed_at >= datetime.utcnow() - timedelta(hours=2),
                    ).filter(
                        (RebalancingAction.source_instance_id == instance.instance_id)
                        | (RebalancingAction.action_metadata.op('->>')('instance_id') == instance.instance_id)
                    ).first()
                    if _recent_completed:
                        if _recent_completed.status == 'completed':
                            logger.info(
                                f"[auto_rebalancer] Skipping {instance.instance_id}: "
                                f"recent completed action {_recent_completed.id} "
                                f"exists (< 2h) — marking DB instance as terminated to stop growth"
                            )
                            # Source should already be gone — force DB state to terminated
                            instance.state = 'terminated'
                            db.commit()
                        else:
                            # Failed action — source node is still alive, just skip for cooldown
                            logger.info(
                                f"[auto_rebalancer] Skipping {instance.instance_id}: "
                                f"recent failed action {_recent_completed.id} "
                                f"exists (< 2h) — cooling down before retry"
                            )
                        continue
                except Exception as _rcq_err:
                    logger.debug(f"[auto_rebalancer] Recent action check failed: {_rcq_err}")

                # ── PER-NODE ACTIVE ACTION LOCK (changes.md §2.2) ──────────────
                # Prevent overlapping drains/migrations for the same source node.
                # Lock is set when an action is created (10-min TTL) and cleared
                # on completion or failure so the next cycle can re-target freely.
                try:
                    _na_lock_key = f"spot:node_active_action:{instance.instance_id}"
                    if _redis and _redis.exists(_na_lock_key):
                        logger.debug(
                            "[auto_rebalancer] Skipping %s: per-node active action lock held "
                            "(node is already being migrated, waiting for completion)",
                            instance.instance_id,
                        )
                        continue
                except Exception:
                    pass

                # Issue 12 + BUG-7 fix: Configurable concurrent action limit.
                # max_concurrent_rebalance_actions=NULL → 1 (preserve existing behavior).
                # BUG-7: Use Redis atomic INCR/DECR as distributed semaphore instead
                # of DB query (two workers can read same count and both proceed).
                _max_concurrent = (
                    _opt_settings.max_concurrent_rebalance_actions
                    if _opt_settings and getattr(_opt_settings, 'max_concurrent_rebalance_actions', None)
                    else 1
                )
                _sem_key = f"rebalance:active_count:{cluster.id}"
                _sem_acquired = False
                try:
                    if _redis:
                        _sem_current = _redis.incr(_sem_key)
                        _redis.expire(_sem_key, 300)  # safety TTL: auto-expire if worker dies
                        if _sem_current > _max_concurrent:
                            _redis.decr(_sem_key)
                            logger.debug(
                                f'[auto_rebalancer] Cluster {cluster.name} at concurrent action limit '
                                f'({_sem_current - 1}/{_max_concurrent}) — skipping new creation (semaphore)'
                            )
                            break
                        _sem_acquired = True
                    else:
                        # Fallback to DB check when Redis unavailable
                        _active_rebalancing = db.query(RebalancingAction).filter(
                            RebalancingAction.cluster_id == cluster.id,
                            RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent', 'pending_approval'])
                        ).all()
                        if len(_active_rebalancing) >= _max_concurrent:
                            if _active_rebalancing:
                                logger.debug(
                                    f'[auto_rebalancer] Cluster {cluster.name} at concurrent action limit '
                                    f'({len(_active_rebalancing)}/{_max_concurrent}) — skipping new creation'
                                )
                            break
                except Exception as _sem_err:
                    logger.warning(f"[auto_rebalancer] Semaphore check failed: {_sem_err}")

                # Create new rebalancing action: on-demand → ML-selected spot pool
                source_az = instance.az or f"{cluster.region}a"
                source_pool = f"{instance.instance_type}:{source_az}"

                # ── TOGGLE LOGIC ────────────────────────────────────────────────
                # auto_rebalance only  → ML-rank spot pools at the SAME instance size
                # auto_rebalance+rightsizing → BIN-PACK first (find smaller type based on
                #                              actual CPU/memory usage), then ML-rank for
                #                              the bin-packed size → cheapest + smallest spot
                # _opt_settings already loaded at top of cluster loop
                _auto_rightsizing_on = _opt_settings.auto_rightsizing_enabled if _opt_settings else False

                target_instance_type = instance.instance_type  # default: same size
                bin_packed = False
                _reason = 'automatic_spot_migration'

                if _auto_rightsizing_on:
                    # Bin-pack: find smallest instance type that fits actual usage + 30% buffer
                    _cpu_pct = float(instance.cpu_util or 0.0)
                    _mem_pct = float(instance.memory_util or 0.0)
                    if _cpu_pct > 0 and _mem_pct > 0:
                        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                        _cur_specs = _INSTANCE_VCPU_MEM.get(instance.instance_type)
                        if _cur_specs:
                            _BUF = 1.30  # 30% safety headroom above P95 usage
                            _req_vcpu = max(0.25, (_cur_specs[0] * _cpu_pct / 100) * _BUF)
                            _req_mem  = max(0.5,  (_cur_specs[1] * _mem_pct / 100) * _BUF)
                            # Fix #24: bin-pack uses hardcoded VCPU/mem/price dict as fallback only.
                            # Try AWSPricingService cache first for current-type OD price.
                            _PRICES = {
                                "t3.nano":(2,0.5,0.0058),"t3.micro":(2,1.0,0.0116),
                                "t3.small":(2,2.0,0.0232),"t3.medium":(2,4.0,0.0464),
                                "t3.large":(2,8.0,0.0928),"t3.xlarge":(4,16.0,0.1856),
                                "t3.2xlarge":(8,32.0,0.3712),
                                "t3a.micro":(2,1.0,0.0104),"t3a.small":(2,2.0,0.0209),
                                "t3a.medium":(2,4.0,0.0418),"t3a.large":(2,8.0,0.0836),
                                "m5.large":(2,8.0,0.096),"m5.xlarge":(4,16.0,0.192),
                                "m6i.large":(2,8.0,0.096),"m6i.xlarge":(4,16.0,0.192),
                                "c5.large":(2,4.0,0.085),"c5.xlarge":(4,8.0,0.17),
                                "c6i.large":(2,4.0,0.085),"c6g.large":(2,4.0,0.068),
                                "m6g.medium":(1,4.0,0.038),"m6g.large":(2,8.0,0.077),
                                "t4g.micro":(2,1.0,0.0092),"t4g.small":(2,2.0,0.0184),
                                "t4g.medium":(2,4.0,0.0368),"t4g.large":(2,8.0,0.0736),
                            }
                            # Try pricing cache to get live OD price for current instance type
                            _bp_region = cluster.region or 'ap-south-1'
                            _bp_cached = None
                            try:
                                _bp_cached_raw = _redis.get(f"pricing:od:{_bp_region}:{instance.instance_type}")
                                if _bp_cached_raw:
                                    _bp_cached = float(_bp_cached_raw)
                            except Exception:
                                pass
                            # Override the hardcoded price for current instance type if cached
                            if _bp_cached and instance.instance_type in _PRICES:
                                _bp_entry = _PRICES[instance.instance_type]
                                _PRICES[instance.instance_type] = (_bp_entry[0], _bp_entry[1], _bp_cached)
                            _cur_hourly = _PRICES.get(instance.instance_type, (None,None,_cur_specs[0]*0.05))[2]
                            # Sort by price ascending; only consider cheaper options
                            _candidates = sorted(
                                [(t,v,m,h) for t,(v,m,h) in _PRICES.items() if h < _cur_hourly],
                                key=lambda x: x[3]
                            )
                            for _t, _v, _m, _h in _candidates:
                                if _v >= _req_vcpu and _m >= _req_mem:
                                    target_instance_type = _t
                                    bin_packed = True
                                    _reason = 'bin_pack_and_spot_migration'
                                    logger.info(
                                        f"[auto_rebalancer] Bin-packed {instance.instance_type} "
                                        f"({_cpu_pct:.0f}%cpu/{_mem_pct:.0f}%mem) → {_t}"
                                    )
                                    break

                # ML-rank: find the best spot pool for the target instance size
                # Initialize to None — only set after double-gate succeeds.
                # If exception occurs or no pool qualifies, target_pool stays None
                # and the deferred-action path fires (skips action creation).
                target_pool = None
                target_instance_type_final = target_instance_type
                # Determine source architecture (available to both double-gate and ranked_alternatives)
                _src_arch_label = 'amd64'  # default
                _ARM_FAMS_RANK = {'t4g','c6g','c7g','c8g','m6g','m7g','m8g','r6g','r7g','r8g',
                                  'c6gn','c6gd','m6gd','r6gd','a1','hpc7g','x2gd','im4gn','is4gen'}
                _src_fam_rank = instance.instance_type.split('.')[0] if '.' in instance.instance_type else ''
                if _src_fam_rank in _ARM_FAMS_RANK:
                    _src_arch_label = 'arm64'
                try:
                    from backend.core.redis_client import get_redis_client as _grc
                    from backend.services.pool_ranking_service import PoolRankingService
                    from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
                    _specs = _INSTANCE_VCPU_MEM.get(target_instance_type, (2, 8))
                    # Check architecture_preference setting
                    _arch_pref_rank = getattr(_opt_settings, 'architecture_preference', 'both') or 'both'
                    if _arch_pref_rank == 'both':
                        _rank_arch = ['amd64', 'arm64']
                    elif _arch_pref_rank == 'arm64':
                        _rank_arch = ['arm64']
                    else:
                        _rank_arch = ['amd64']
                    _redis = _grc()
                    _prs = PoolRankingService(db, _redis)
                    _fb_result = []
                    _per_node_primary_pool = None
                    _per_node_primary_type = None

                    # Primary target selection source: per-node alternatives
                    # (same method as /alternatives API).
                    try:
                        from backend.workers.tasks.cache_builder import (
                            _lookup_specs as _cb_lookup_specs_primary,
                        )
                        _pn_vcpu, _pn_mem, _pn_arch, _ = _cb_lookup_specs_primary(instance.instance_type)
                        _pn_vcpu = _pn_vcpu or 2
                        _pn_mem = _pn_mem or 4.0
                        _pn_arch = getattr(instance, 'architecture', None) or _pn_arch or _src_arch_label
                        _pn_od_price = float(getattr(instance, 'current_price', 0) or 0)
                        _fb_result = _prs.rank_pools_for_node(
                            node_info={
                                'instance_type': instance.instance_type,
                                'az': source_az,
                                'od_price': _pn_od_price,
                                'risk_score': float(getattr(instance, 'risk_score', 0) or 0),
                                'resource_profile': {
                                    'min_vcpu_required': float(_pn_vcpu),
                                    'min_memory_required': float(_pn_mem),
                                    'architecture': _pn_arch,
                                },
                            },
                            cluster_id=str(cluster.id),
                            region=cluster.region or 'ap-south-1',
                            include_dynamic_filters=True,
                        )
                        _launched_primary = next(
                            (p for p in _fb_result if p.get('would_be_launched')), None
                        ) or next(
                            (p for p in _fb_result if p.get('rebalancer_eligible')), None
                        )
                        if _launched_primary:
                            _pn_type = _launched_primary.get('instance_type', '')
                            _pn_az = _launched_primary.get('az', source_az)
                            if _pn_type and _pn_type != instance.instance_type:
                                _per_node_primary_pool = f"{_pn_type}:{_pn_az}"
                                _per_node_primary_type = _pn_type
                                target_pool = _per_node_primary_pool
                                target_instance_type_final = _pn_type
                                logger.info(
                                    f"[auto_rebalancer] rank_pools_for_node primary selected "
                                    f"{target_pool} for {instance.instance_id} "
                                    f"(pass={_launched_primary.get('rebalancer_pass')}, "
                                    f"savings={_launched_primary.get('savings_pct', 0):.1f}%)"
                                )
                    except Exception as _pn_pick_err:
                        logger.warning(
                            f"[auto_rebalancer] rank_pools_for_node primary selection failed: "
                            f"{_pn_pick_err}"
                        )

                    _ranked = _prs.rank_pools_for_size(
                        vcpu=_specs[0], memory_gb=float(_specs[1]),
                        region=cluster.region or "ap-south-1", limit=10,
                        architecture=_rank_arch,
                    )

                    # ── DIVERSIFY POOLS: pool-level uniqueness + 50% AZ cap ─────────
                    # Pool = (instance_type, az). Max 1 node per identical pool.
                    # c5.large:ap-south-1a and c5.large:ap-south-1b are DIFFERENT pools.
                    # AZ cap (50%) is kept to prevent all nodes concentrating in one AZ.
                    #
                    # Always active — pool uniqueness is a correctness constraint, not a
                    # setting. The `diversify_pools` flag now only controls the *strict*
                    # family cap (40% default). Pool-level and AZ-level checks always run.
                    if _ranked:
                        from backend.models.instance import Instance as _DivInst
                        _running_insts = db.query(_DivInst).filter(
                            _DivInst.cluster_id == cluster.id,
                            _DivInst.state == 'running',
                        ).all()
                        # Build pool-count dict: (instance_type, az) → count
                        _pool_counts: dict = {}
                        _az_counts: dict = {}
                        _fam_counts: dict = {}
                        _diversify_fam_cap_pct = getattr(_opt_settings, 'max_family_diversification_cap_pct', 40) or 40
                        _diversify_fam_cap_ratio = _diversify_fam_cap_pct / 100.0
                        import math as _math_div

                        for _ri in _running_insts:
                            if _ri.instance_type and _ri.az:
                                _pk = (_ri.instance_type, _ri.az)
                                _pool_counts[_pk] = _pool_counts.get(_pk, 0) + 1
                            if _ri.az:
                                _az_counts[_ri.az] = _az_counts.get(_ri.az, 0) + 1
                            if _ri.instance_type:
                                _f = _ri.instance_type.split('.')[0]
                                _fam_counts[_f] = _fam_counts.get(_f, 0) + 1

                        # Include in-flight AND recently-completed actions to prevent duplicate pools.
                        # "Recently completed" = completed in last 10 min — new replacement EC2s
                        # may not yet appear in the Instance table (collector lag), so we read
                        # the target_pool from the action itself to block duplicate selection.
                        _inflight_actions_div = []
                        try:
                            _div_recent_cutoff = datetime.utcnow() - timedelta(minutes=10)
                            _inflight_actions_div = db.query(RebalancingAction).filter(
                                RebalancingAction.cluster_id == cluster.id,
                            ).filter(
                                (RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent'])) |
                                (
                                    (RebalancingAction.status == 'completed') &
                                    (RebalancingAction.completed_at >= _div_recent_cutoff)
                                )
                            ).all()
                        except Exception as _div_ia_err:
                            logger.debug(f"[auto_rebalancer] In-flight action count failed: {_div_ia_err}")
                        for _ia in _inflight_actions_div:
                            # target_pool is stored as "instance_type:az" string
                            _ia_tpool = getattr(_ia, 'target_pool', None) or ''
                            if _ia_tpool and ':' in _ia_tpool:
                                _ia_type, _ia_az = _ia_tpool.split(':', 1)
                                _pk = (_ia_type, _ia_az)
                                _pool_counts[_pk] = _pool_counts.get(_pk, 0) + 1
                                _az_counts[_ia_az] = _az_counts.get(_ia_az, 0) + 1
                                _fam_counts[_ia_type.split('.')[0]] = _fam_counts.get(_ia_type.split('.')[0], 0) + 1

                        _total_nodes_div = len(_running_insts) + len(_inflight_actions_div) + 1
                        _MAX_AZ_SHARE = 0.50
                        # Family cap: only enforced when diversify_pools=True (strict mode).
                        # When the setting is off, family cap = total_nodes (effectively unlimited),
                        # so pool-uniqueness and AZ cap still block duplicates but won't reject
                        # a family that was legitimately chosen as the best option.
                        _strict_diversify = getattr(_opt_settings, 'diversify_pools', False)
                        if _strict_diversify:
                            # Ceiling-based family cap: max nodes per family = ceil(cap% × total).
                            # Prevents raw-ratio math from blocking all new families on small clusters.
                            # Example: 3 nodes, 40% cap → ceil(1.2)=2; adding 1 to empty family
                            # gives count=1 ≤ 2 → PASSES (raw 33% < 40% also passes, consistent).
                            _fam_cap_nodes_div = max(1, _math_div.ceil(_diversify_fam_cap_ratio * _total_nodes_div))
                        else:
                            _fam_cap_nodes_div = _total_nodes_div  # unlimited — family cap disabled

                        _diversified = []
                        for _rp in _ranked:
                            _pk = (_rp.pool.instance_type, _rp.pool.az or "")
                            _f = _rp.pool.instance_type.split('.')[0]
                            _az_ok = (_az_counts.get(_rp.pool.az or "", 0) + 1) / _total_nodes_div <= _MAX_AZ_SHARE
                            _fam_ok = (_fam_counts.get(_f, 0) + 1) <= _fam_cap_nodes_div

                            # Pool-level & Family-level: skip if occupied or family cap exceeded
                            if _pool_counts.get(_pk, 0) == 0 and _az_ok and _fam_ok:
                                _diversified.append(_rp)
                                if len(_diversified) >= 3:
                                    break
                        # Fallback 1: relax AZ cap, still enforce pool uniqueness & family cap
                        if not _diversified:
                            for _rp in _ranked:
                                _pk = (_rp.pool.instance_type, _rp.pool.az or "")
                                _f = _rp.pool.instance_type.split('.')[0]
                                _fam_ok = (_fam_counts.get(_f, 0) + 1) <= _fam_cap_nodes_div
                                if _pool_counts.get(_pk, 0) == 0 and _fam_ok:
                                    _diversified.append(_rp)
                                    if len(_diversified) >= 3:
                                        break
                        # Fallback 2: relax family cap too, only enforce pool uniqueness
                        if not _diversified:
                            for _rp in _ranked:
                                _pk = (_rp.pool.instance_type, _rp.pool.az or "")
                                if _pool_counts.get(_pk, 0) == 0:
                                    _diversified.append(_rp)
                                    if len(_diversified) >= 3:
                                        break
                        # Last resort: use top-3 as-is
                        _ranked = _diversified if _diversified else _ranked[:3]
                        logger.info(
                            f"[auto_rebalancer] Diversify active (pool-level, strict={_strict_diversify}): "
                            f"pool_counts={_pool_counts} az_counts={_az_counts} "
                            f"→ selected {len(_ranked)} pool(s) after pool-uniqueness+AZ cap"
                        )
                    # NOTE: 'else: _ranked = _ranked[:3]' removed — diversification always runs above

                    # ── SIZE CAP: prevent upsizing during pure spot migration ────
                    # When NOT bin-packing, do not pick a pool whose instance type
                    # is larger than the current node (avoids paying more for
                    # a bigger instance just because it has lower risk).
                    # Allow up to 1.25x vCPU/memory headroom for equivalent tiers.
                    if not bin_packed:
                        _cur_specs_cap = _INSTANCE_VCPU_MEM.get(instance.instance_type)
                        if _cur_specs_cap:
                            _max_vcpu_cap = _cur_specs_cap[0] * 1.25
                            _max_mem_cap = _cur_specs_cap[1] * 1.25
                            _size_capped = [
                                _r for _r in _ranked
                                if (
                                    _INSTANCE_VCPU_MEM.get(_r.pool.instance_type, (0, 0))[0] <= _max_vcpu_cap
                                    and
                                    _INSTANCE_VCPU_MEM.get(_r.pool.instance_type, (0, 0))[1] <= _max_mem_cap
                                )
                            ]
                            if _size_capped:
                                logger.debug(
                                    f"[auto_rebalancer] Size cap: {len(_ranked)} → {len(_size_capped)} "
                                    f"pools (max {_max_vcpu_cap:.1f}vCPU/{_max_mem_cap:.1f}GB)"
                                )
                                _ranked = _size_capped

                    # ── DOUBLE GATE: 3-step selection hierarchy ──────────────────
                    # OD on-demand reference price — try AWSPricingService cache first.
                    # Fix #24: hardcoded dict was causing wrong savings comparisons when
                    # real OD prices differed (different region/pricing tier).
                    # Fallback to hardcoded dict with warning if cache miss.
                    _OD_PRICES_FALLBACK = {
                        "t3.nano":0.0052,"t3.micro":0.0104,"t3.small":0.0208,
                        "t3.medium":0.0416,"t3.large":0.0832,"t3.xlarge":0.1664,
                        "t3.2xlarge":0.3328,"t3a.medium":0.0376,"t3a.large":0.0752,
                        "m5.large":0.096,"m5.xlarge":0.192,"m5.2xlarge":0.384,
                        "m6i.large":0.096,"m6i.xlarge":0.192,"c5.large":0.085,
                        "c5.xlarge":0.17,"c6i.large":0.085,"c6g.large":0.077,
                        "r5.large":0.126,"r5.xlarge":0.252,"m6g.large":0.077,
                    }
                    _od_price_g = None
                    try:
                        # AWSPricingService caches OD prices as pricing:od:{region}:{instance_type}
                        _pricing_region = cluster.region or 'ap-south-1'
                        _pricing_key = f"pricing:od:{_pricing_region}:{instance.instance_type}"
                        _cached_price = _redis.get(_pricing_key) if _redis else None
                        if _cached_price:
                            _od_price_g = float(_cached_price)
                    except Exception:
                        pass
                    if _od_price_g is None:
                        _od_price_g = _OD_PRICES_FALLBACK.get(instance.instance_type)
                        if _od_price_g is None:
                            logger.warning(
                                f"[auto_rebalancer] OD price not found in cache or fallback "
                                f"for {instance.instance_type} in {cluster.region}. "
                                f"Using 0.10/hr default. Run pricing collector to populate cache."
                            )
                            _od_price_g = 0.10
                        else:
                            logger.debug(
                                f"[auto_rebalancer] Using hardcoded OD price for "
                                f"{instance.instance_type}: ${_od_price_g}/hr "
                                f"(pricing cache miss for {_pricing_region})"
                            )
                    try:
                        from backend.models.cluster import OptimizationStrategy as _OS_g
                        _os_g = db.query(_OS_g).filter_by(cluster_id=cluster.id).first()
                        _tradeoff_g = (getattr(_os_g, 'risk_savings_tradeoff_pct', 20) or 20) / 100.0
                        _rceil_g = (getattr(_os_g, 'risk_ceiling_percent', 25) or 25) / 100.0
                    except Exception:
                        _tradeoff_g = 0.20
                        _rceil_g = 0.25
                    # Apply regional market factor to risk ceiling (clamped 0.8–1.2)
                    try:
                        _mf_raw_g = _redis.get(f"market_factor:{cluster.region or 'ap-south-1'}")
                        _rceil_g *= float(_mf_raw_g) if _mf_raw_g else 1.0
                    except Exception:
                        pass

                    _chosen_g = None
                    # Find cheapest valid spot price to calculate realistic tradeoff bounds
                    _valid_spots = [r for r in _ranked if r.pool.spot_price > 0]
                    _cheapest_spot = min(
                        _valid_spots, key=lambda x: x.pool.spot_price
                    ).pool.spot_price if _valid_spots else _od_price_g * 0.3

                    # Pass 1: cheaper (spot < OD price) AND risk below ceiling
                    for _rg in _ranked:
                        _cheaper_g = (
                            (_rg.pool.spot_price > 0 and _rg.pool.spot_price < _od_price_g) or
                            (_rg.pool.spot_price == 0 and _rg.predicted_savings > 0.05)
                        )
                        if _cheaper_g and _rg.risk_probability < _rceil_g:
                            _chosen_g = _rg
                            break
                            
                    # Pass 2 (tradeoff): allow giving up to tradeoff% of the OD savings
                    if not _chosen_g:
                        _max_g = _cheapest_spot + (_od_price_g - _cheapest_spot) * _tradeoff_g
                        _p2_g = [
                            _rg for _rg in _ranked
                            if ((_rg.pool.spot_price > 0 and _rg.pool.spot_price <= _max_g)
                                or _rg.pool.spot_price == 0)
                            and _rg.risk_probability < _rceil_g
                        ]
                        if _p2_g:
                            _chosen_g = min(_p2_g, key=lambda r: r.risk_probability)
                    # Risk override: node itself is dangerously risky → any safer pool, price ignored
                    if not _chosen_g:
                        _node_risk_g = float(instance.risk_score or 0.0)
                        if _node_risk_g > _rceil_g:
                            _safer_g = [_rg for _rg in _ranked if _rg.risk_probability < _node_risk_g]
                            if _safer_g:
                                _chosen_g = min(_safer_g, key=lambda r: r.risk_probability)

                    # OD→SPOT final fallback: any spot pool is still better than staying on OD.
                    # Spot is almost always cheaper than OD even at "high risk". Pick the
                    # lowest-risk pool that is at least cheaper than OD price.
                    if not _chosen_g and instance.lifecycle == InstanceLifecycle.ON_DEMAND:
                        _cheaper_any = [
                            r for r in _ranked
                            if r.pool.spot_price == 0 or r.pool.spot_price < _od_price_g
                        ]
                        if _cheaper_any:
                            _chosen_g = min(_cheaper_any, key=lambda r: r.risk_probability)
                            logger.info(
                                f"[auto_rebalancer] OD→SPOT fallback for {instance.instance_id}: "
                                f"using lowest-risk pool {_chosen_g.pool.instance_type}:{_chosen_g.pool.az} "
                                f"(risk={_chosen_g.risk_probability:.2f}, ceiling exceeded but still cheaper than OD)"
                            )
                        elif _ranked:
                            _chosen_g = _ranked[0]
                            logger.info(
                                f"[auto_rebalancer] OD→SPOT last-resort for {instance.instance_id}: "
                                f"using top-ranked pool {_ranked[0].pool.instance_type}:{_ranked[0].pool.az}"
                            )

                    if _chosen_g:
                        _p = _chosen_g.pool
                        _chosen_pool_str = f"{_p.instance_type}:{_p.az}"
                        # Guard: same pool as source means no real improvement.
                        # OD→Spot in exact same type+AZ is technically cheaper but
                        # creates confusing same-type migrations that look like bugs.
                        # Skip and let the rebalancer try again next cycle with better data.
                        if _chosen_pool_str == source_pool or _p.instance_type == instance.instance_type:
                            logger.warning(
                                f"[auto_rebalancer] Double-gate picked same instance type as source "
                                f"({instance.instance_type}) pool={_chosen_pool_str} vs source={source_pool} "
                                f"— no better alternative found this cycle. "
                                f"Trying rank_pools_for_node fallback."
                            )
                            target_pool = None  # try rank_pools_for_node fallback below
                        else:
                            target_pool = _chosen_pool_str
                            target_instance_type_final = _p.instance_type
                    else:
                        # No suitable spot pool from rank_pools_for_size double-gate
                        logger.info(
                            f"[auto_rebalancer] Double-gate found no qualifying pool for "
                            f"{instance.instance_id} ({instance.instance_type}, "
                            f"od_price={_od_price_g:.4f}, risk_ceil={_rceil_g:.2f}) — "
                            f"trying rank_pools_for_node fallback"
                        )
                        target_pool = None  # try fallback

                    # If per-node alternatives already picked a launchable pool, keep it
                    # as the final execution target (source of truth).
                    if _per_node_primary_pool:
                        if target_pool != _per_node_primary_pool:
                            logger.info(
                                f"[auto_rebalancer] Using per-node primary target "
                                f"{_per_node_primary_pool} instead of double-gate "
                                f"result for {instance.instance_id}"
                            )
                        target_pool = _per_node_primary_pool
                        target_instance_type_final = _per_node_primary_type or target_instance_type_final

                    # ── FALLBACK: Use rank_pools_for_node() when double-gate fails ──
                    # rank_pools_for_node() is the SAME method the /alternatives UI uses.
                    # It has its own built-in rebalancer gate evaluation. The pool marked
                    # would_be_launched=True is the one the rebalancer should pick.
                    # This ensures UI alternatives = execution target — no disconnect.
                    if target_pool is None:
                        try:
                            from backend.workers.tasks.cache_builder import (
                                _lookup_specs as _cb_lookup_specs_fb,
                            )
                            _fb_vcpu, _fb_mem, _fb_arch, _ = _cb_lookup_specs_fb(instance.instance_type)
                            _fb_vcpu = _fb_vcpu or 2
                            _fb_mem = _fb_mem or 4.0
                            _fb_arch = getattr(instance, 'architecture', None) or _fb_arch or _src_arch_label
                            _fb_od_price = _od_price_g or 0.0
                            if not _fb_result:
                                _fb_result = _prs.rank_pools_for_node(
                                    node_info={
                                        'instance_type': instance.instance_type,
                                        'az': source_az,
                                        'od_price': _fb_od_price,
                                        'risk_score': float(getattr(instance, 'risk_score', 0) or 0),
                                        'resource_profile': {
                                            'min_vcpu_required': float(_fb_vcpu),
                                            'min_memory_required': float(_fb_mem),
                                            'architecture': _fb_arch,
                                        },
                                    },
                                    cluster_id=str(cluster.id),
                                    region=cluster.region or 'ap-south-1',
                                    include_dynamic_filters=True,
                                )
                            # Find the would_be_launched pool (rebalancer's top pick)
                            _launched_fb = next(
                                (p for p in _fb_result if p.get('would_be_launched')), None
                            )
                            if not _launched_fb and _fb_result:
                                # No would_be_launched flag — use first rebalancer_eligible
                                _launched_fb = next(
                                    (p for p in _fb_result if p.get('rebalancer_eligible')), None
                                )
                            if _launched_fb:
                                _fb_type = _launched_fb.get('instance_type', '')
                                _fb_az = _launched_fb.get('az', source_az)
                                if _fb_type and _fb_type != instance.instance_type:
                                    target_pool = f"{_fb_type}:{_fb_az}"
                                    target_instance_type_final = _fb_type
                                    logger.info(
                                        f"[auto_rebalancer] rank_pools_for_node fallback "
                                        f"selected {target_pool} for {instance.instance_id} "
                                        f"(pass={_launched_fb.get('rebalancer_pass')}, "
                                        f"savings={_launched_fb.get('savings_pct', 0):.1f}%)"
                                    )
                                else:
                                    logger.warning(
                                        f"[auto_rebalancer] rank_pools_for_node fallback: "
                                        f"would_be_launched is same type {_fb_type} — skipping"
                                    )
                            else:
                                logger.info(
                                    f"[auto_rebalancer] rank_pools_for_node fallback: "
                                    f"no rebalancer_eligible pool for {instance.instance_id} "
                                    f"(total pools: {len(_fb_result)})"
                                )
                        except Exception as _fb_err:
                            logger.warning(
                                f"[auto_rebalancer] rank_pools_for_node fallback failed: {_fb_err}"
                            )

                    if target_pool is None:
                        # Neither double-gate nor rank_pools_for_node found a pool
                        logger.debug(
                            f"[auto_rebalancer] No qualifying spot pool for {instance.instance_id} "
                            f"({instance.instance_type}) — skipping this cycle"
                        )
                except Exception:
                    # Sync target_instance_type_final from target_pool if it was already
                    # set (e.g. by _per_node_primary_pool before the exception occurred).
                    # Avoids the UI showing "→ t3.medium" when target_pool is correctly
                    # set to c7g.medium:ap-south-1b but the except resets to source type.
                    if target_pool and ':' in target_pool:
                        _exc_type = target_pool.split(':')[0]
                        target_instance_type_final = _exc_type if _exc_type else target_instance_type
                    else:
                        target_instance_type_final = target_instance_type

                # Build ranked alternatives using rank_pools_for_node() — the SAME
                # method the /alternatives endpoint uses. This ensures the per-node
                # alternatives the UI shows = the list execution uses. No disconnect.
                # Reuse _fb_result if already computed during the fallback above.
                _ranked_alternatives = []
                try:
                    _src_itype = instance.instance_type
                    try:
                        _per_node_result = _fb_result  # reuse from fallback
                    except NameError:
                        # _fb_result wasn't computed (double-gate succeeded first try)
                        _node_od_price_ra = 0.0
                        try:
                            _node_od_price_ra = _od_price_g or 0.0
                        except NameError:
                            pass
                        from backend.workers.tasks.cache_builder import (
                            _lookup_specs as _cb_lookup_specs_ra,
                        )
                        _ra_vcpu, _ra_mem, _ra_arch_det, _ = _cb_lookup_specs_ra(instance.instance_type)
                        _ra_vcpu = _ra_vcpu or 2
                        _ra_mem = _ra_mem or 4.0
                        _node_arch_ra = getattr(instance, 'architecture', None) or _ra_arch_det or _src_arch_label
                        _per_node_result = _prs.rank_pools_for_node(
                            node_info={
                                'instance_type': instance.instance_type,
                                'az': source_az,
                                'od_price': _node_od_price_ra,
                                'risk_score': float(getattr(instance, 'risk_score', 0) or 0),
                                'resource_profile': {
                                    'min_vcpu_required': float(_ra_vcpu),
                                    'min_memory_required': float(_ra_mem),
                                    'architecture': _node_arch_ra,
                                },
                            },
                            cluster_id=str(cluster.id),
                            region=cluster.region or 'ap-south-1',
                            include_dynamic_filters=True,
                        )
                    # Apply no-join block + dry-run filters (same as /alternatives)
                    for _pnr in _per_node_result:
                        _pnr_type = _pnr.get('instance_type', '')
                        if _pnr_type == _src_itype or _pnr_type in _ranked_alternatives:
                            continue
                        _blk_key = f"spot:launch_blocked:{cluster.id}:{_pnr_type}:{source_az}"
                        if _redis.get(_blk_key):
                            continue
                        _dr_key = f"dry_run:{_pnr_type}:{source_az}"
                        _dr_cached = _redis.get(_dr_key)
                        if _dr_cached:
                            _dr_val = _dr_cached.decode() if isinstance(_dr_cached, bytes) else _dr_cached
                            if _dr_val == 'fail':
                                continue
                        _ranked_alternatives.append(_pnr_type)
                    logger.info(
                        f"[auto_rebalancer] rank_pools_for_node alternatives for "
                        f"{instance.instance_id}: {_ranked_alternatives[:8]} "
                        f"(total={len(_ranked_alternatives)})"
                    )
                except Exception as _ra_err:
                    logger.warning(
                        f"[auto_rebalancer] rank_pools_for_node ranked_alternatives: {_ra_err} — "
                        f"using double-gate ranked list"
                    )
                    # Fallback: use double-gate ranked list if rank_pools_for_node fails
                    _ranked_alternatives = []
                    try:
                        _src_itype_fb = instance.instance_type
                        for _rp in _ranked:
                            _rit = _rp.pool.instance_type
                            if _rit != _src_itype_fb and _rit not in _ranked_alternatives:
                                _ranked_alternatives.append(_rit)
                    except Exception:
                        pass

                if target_pool is None:
                    # No qualifying spot pool — create a deferred action so the UI
                    # can surface this as a visible event rather than a silent skip.
                    try:
                        _deferred_action = RebalancingAction(
                            cluster_id=cluster.id,
                            trigger='auto_rebalance',
                            source_pool=source_pool,
                            target_pool=source_pool,  # same as source — no better pool found; NOT NULL constraint requires a value
                            source_instance_id=instance.instance_id,
                            status='deferred',
                            started_at=datetime.utcnow(),
                            completed_at=datetime.utcnow(),
                            duration_seconds=0,
                            error_message=(
                                f"No compatible spot pool found for {instance.instance_type} "
                                f"(risk_ceil={_rceil_g:.0%}, tradeoff={_tradeoff_g:.0%}). "
                                f"Will retry next cycle."
                            ),
                            action_metadata={
                                'reason': 'no_pool_found',
                                'initiated_by': 'auto_rebalancer',
                                'instance_id': instance.instance_id,
                                'instance_type': instance.instance_type,
                                'risk_ceiling': round(_rceil_g, 3),
                                'tradeoff_pct': round(_tradeoff_g, 3),
                            },
                        )
                        db.add(_deferred_action)
                        db.commit()
                        logger.info(
                            f"[auto_rebalancer] Deferred action created for {instance.instance_id} "
                            f"— no qualifying spot pool (risk_ceil={_rceil_g:.0%})"
                        )
                    except Exception as _def_err:
                        logger.warning(f"[auto_rebalancer] Failed to create deferred action: {_def_err}")
                    continue  # try next OD instance

                _needs_approval = getattr(_opt_settings, 'manual_approval_required', False)
                _action_status = 'pending_approval' if _needs_approval else 'in_progress'

                # Pillar 6 — schema validation before DB insert
                try:
                    _src_od_price = getattr(instance, 'current_price', None) or 0.0
                    _validate_rebalancing_action_schema(
                        cluster_id=str(cluster.id),
                        source_pool=source_pool,
                        target_pool=target_pool,
                        source_od_price_hr=_src_od_price if _src_od_price > 0 else None,
                    )
                except ValueError as _schema_err:
                    logger.warning(f"[auto_rebalancer] Schema validation failed: {_schema_err}")
                    # Schema violation is logged but does NOT block action creation —
                    # availability > perfect data during live rebalancing.

                rebalancing_action = RebalancingAction(
                    cluster_id=cluster.id,
                    trigger='auto_rebalance',
                    source_pool=source_pool,
                    target_pool=target_pool,
                    source_instance_id=instance.instance_id,
                    status=_action_status,
                    started_at=datetime.utcnow(),
                    action_metadata={
                        'reason': _reason,
                        'initiated_by': 'auto_rebalancer',
                        'instance_id': instance.instance_id,
                        'bin_packed': bin_packed,
                        # Use target_instance_type_final (post-double-gate actual choice)
                        # NOT pre-gate target_instance_type which may still equal source type.
                        'target_instance_type': target_instance_type_final,
                        # AZs stored at creation so Decision Engine failure reporting
                        # and Phase-2 AZ fallback never rely on empty-string guards.
                        'target_az': target_pool.split(':')[1] if ':' in (target_pool or '') else (instance.az or ''),
                        'source_az': instance.az or '',
                        # Pre-computed ranked alternatives (source type excluded).
                        # Execution path uses this directly instead of re-ranking.
                        'ranked_alternatives': _ranked_alternatives[:8],
                    }
                )

                db.add(rebalancing_action)
                if _needs_approval:
                    logger.info(
                        f"[auto_rebalancer] manual_approval_required=True — created "
                        f"pending_approval action for {instance.instance_id} in cluster "
                        f"{cluster.name}. Approve via POST /api/v1/ascpai/rebalancing-actions/{{id}}/approve"
                    )
                else:
                    logger.info(f"Created auto-rebalance action for {instance.instance_id} in cluster {cluster.name}")

                # Z6 fix: Set per-node active action lock with 24h safety-net TTL.
                # Cleared explicitly by completion/failure handlers; TTL is a fallback
                # to prevent permanent lockout if explicit cleanup is missed.
                try:
                    if _redis:
                        _redis.setex(
                            f"spot:node_active_action:{instance.instance_id}",
                            86400,
                            instance.instance_id,
                        )
                except Exception:
                    pass

                # Fix #15: increment per-instance daily counter
                try:
                    _dlc_date2 = datetime.utcnow().strftime('%Y-%m-%d')
                    _dlc_key2 = f"rebalance_daily_count:{instance.instance_id}:{_dlc_date2}"
                    _dlc_new_val = _redis.incr(_dlc_key2)
                    # Expire at end of the UTC day
                    import time as _time_dlc2
                    _dlc_now = datetime.utcnow()
                    _dlc_seconds_left = int(
                        ((_dlc_now.replace(hour=23, minute=59, second=59) - _dlc_now).total_seconds()) + 1
                    )
                    _redis.expire(_dlc_key2, max(1, _dlc_seconds_left))
                    logger.debug(
                        f"[auto_rebalancer] Per-instance daily count: "
                        f"{instance.instance_id} = {_dlc_new_val}/10 today"
                    )
                except Exception:
                    pass

                break  # Only create 1 action per cluster per cycle

        db.commit()

        # Step 2: Execute 1 in_progress action per cluster (never all at once)
        # Group by cluster_id and pick the oldest in_progress action per cluster.
        from sqlalchemy import func as _sqlfunc
        clusters_with_actions = db.query(RebalancingAction.cluster_id).filter(
            RebalancingAction.status == 'in_progress'
        ).distinct().all()

        executed = 0
        for (cid,) in clusters_with_actions:
            action = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cid,
                RebalancingAction.status == 'in_progress'
            ).order_by(RebalancingAction.started_at).first()
            if action:
                execute_rebalancing_action(db, action)
                executed += 1

        if executed == 0:
            logger.debug("No in_progress rebalancing actions to execute")
        else:
            logger.info(f"Executed {executed} rebalancing action(s) (1 per cluster)")

        logger.info("Auto-rebalancer task completed successfully")

        # ── AUTO-STATEFUL RIGHTSIZING PHASE ──────────────────────────────────────
        # Runs every cycle. When auto_stateful_rightsizing_enabled=True AND
        # StatefulRules.require_approval=False, finds the most over-provisioned
        # ON_DEMAND stateful node and queues CORDON→DRAIN→TERMINATE for OD replacement.
        # Conservative: max 1 node per cluster per cycle, 48h per-node cooldown.
        try:
            from backend.models.cluster import (
                ClusterOptimizationSettings as _COS,
                StatefulRules as _SFRules,
            )
            from backend.models.instance import Instance as _SFInst
            from backend.models.agent_action import AgentAction as _SFAA, AgentActionType as _SFAAType
            from backend.api.karpenter_routes import INSTANCE_SPECS as _SF_SPECS

            _sf_settings = db.query(_COS).filter(
                _COS.auto_stateful_rightsizing_enabled == True
            ).all()

            for _sf_opt in _sf_settings:
                _sf_cid = _sf_opt.cluster_id
                try:
                    # Gate 1: StatefulRules.require_approval must be False
                    _sf_rules = db.query(_SFRules).filter(
                        _SFRules.cluster_id == _sf_cid
                    ).first()
                    if _sf_rules and _sf_rules.require_approval:
                        continue

                    # Gate 2: 48h per-cluster cooldown
                    _sf_cluster_key = f"spot:stateful:resize:cluster:{_sf_cid}"
                    if _redis and _redis.exists(_sf_cluster_key):
                        continue

                    # Find ON_DEMAND instances in this cluster
                    # lifecycle is stored as "on-demand" or "spot" string in DB
                    from backend.models.instance import InstanceLifecycle as _ILC
                    _od_instances = db.query(_SFInst).filter(
                        _SFInst.cluster_id == _sf_cid,
                        _SFInst.lifecycle != _ILC.SPOT,
                        _SFInst.state == "running",
                    ).all()

                    _max_downscale_pct = int(
                        (_sf_rules.max_downscale_percent if _sf_rules else None) or 25
                    )

                    for _sf_inst in _od_instances:
                        _itype = _sf_inst.instance_type
                        _cpu   = float(_sf_inst.cpu_util or 0.0)
                        _mem   = float(_sf_inst.memory_util or 0.0)

                        if _itype not in _SF_SPECS:
                            continue

                        # Per-instance 48h cooldown
                        _sf_inst_key = f"spot:stateful:resize:instance:{_sf_inst.instance_id}"
                        if _redis and _redis.exists(_sf_inst_key):
                            continue

                        # Bin-pack to find recommended type
                        from backend.api.karpenter_routes import _bin_pack_instance as _sf_bpi
                        _rec_type, _resize_savings = _sf_bpi(_itype, _cpu, _mem, buffer_pct=30.0)

                        if _rec_type == _itype or _resize_savings <= 0:
                            continue  # No downsize possible

                        # Validate downscale doesn't exceed max_downscale_pct
                        _cur_hr = _SF_SPECS[_itype][2]
                        _rec_hr = _SF_SPECS.get(_rec_type, (None, None, _cur_hr))[2]
                        _downscale_pct = round((_cur_hr - _rec_hr) / _cur_hr * 100)
                        if _downscale_pct > _max_downscale_pct:
                            logger.debug(
                                f"[auto_rebalancer] Stateful resize skipped: {_sf_inst.instance_id} "
                                f"{_itype}→{_rec_type} would downscale {_downscale_pct}% "
                                f"(max allowed: {_max_downscale_pct}%)"
                            )
                            continue

                        # N1 fix: Read respect_pdb_enabled for stateful resize drains too
                        _sf_force_drain = True
                        try:
                            from backend.models.cluster import StatelessRuntimeRules as _SRR_SF
                            _srr_sf = db.query(_SRR_SF).filter(_SRR_SF.cluster_id == _sf_cid).first()
                            if _srr_sf and getattr(_srr_sf, 'respect_pdb_enabled', False):
                                _sf_force_drain = False
                        except Exception:
                            pass

                        # Queue CORDON → DRAIN (120s) → TERMINATE
                        db.add(_SFAA(
                            cluster_id=_sf_cid,
                            action_type=_SFAAType.CORDON_NODE,
                            payload={
                                "instance_id": _sf_inst.instance_id,
                                "node_name": _sf_inst.node_name,
                                "stateful_resize": True,
                                "reason": f"auto_stateful_rightsizing: {_itype}→{_rec_type}",
                            },
                        ))
                        db.add(_SFAA(
                            cluster_id=_sf_cid,
                            action_type=_SFAAType.DRAIN_NODE,
                            payload={
                                "instance_id": _sf_inst.instance_id,
                                "node_name": _sf_inst.node_name,
                                "ignore_daemonsets": True,
                                "grace_period_seconds": 120,
                                "force": _sf_force_drain,
                                "stateful_resize": True,
                            },
                        ))
                        db.add(_SFAA(
                            cluster_id=_sf_cid,
                            action_type=_SFAAType.TERMINATE_NODE,
                            payload={
                                "instance_id": _sf_inst.instance_id,
                                "node_name": _sf_inst.node_name,
                                "recommended_type": _rec_type,
                                "stateful_resize": True,
                                # TASK-1.1: termination_mode replaces decrement_asg boolean.
                                # stateful resize is a replacement-style operation — ASG DesiredCapacity stays.
                                "termination_mode": "replacement",
                                "reason": f"auto_stateful_rightsizing: {_itype}→{_rec_type}",
                            },
                        ))

                        # Set 48h cooldowns
                        if _redis:
                            _redis.setex(_sf_inst_key, 172800, "1")
                            _redis.setex(_sf_cluster_key, 172800, "1")

                        db.commit()
                        logger.info(
                            f"[auto_rebalancer] Auto-stateful rightsizing: queued CORDON→DRAIN→TERMINATE "
                            f"for {_sf_inst.instance_id} ({_itype}→{_rec_type}, "
                            f"saves ${_resize_savings}/mo) on cluster {_sf_cid}"
                        )
                        break  # MAX 1 stateful node per cluster per Celery cycle

                except Exception as _sf_err:
                    logger.warning(
                        f"[auto_rebalancer] Auto-stateful rightsizing error for cluster {_sf_cid}: {_sf_err}"
                    )

        except Exception as _sf_outer:
            logger.warning(f"[auto_rebalancer] Auto-stateful rightsizing phase failed: {_sf_outer}")

    except Exception as e:
        logger.error(f"Auto-rebalancer task failed: {e}")
        raise
    finally:
        db.close()
        # Release HeartbeatLock (stops heartbeat thread + deletes Redis key)
        if _heartbeat_lock:
            try:
                _heartbeat_lock.release()
            except Exception:
                pass
        elif _redis:
            # Fallback: direct delete if HeartbeatLock was not acquired
            try:
                _redis.delete("lock:workers.auto_rebalancer")
            except Exception:
                pass
