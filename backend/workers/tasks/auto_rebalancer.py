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
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import or_
import hashlib

import boto3
from botocore.exceptions import ClientError

from backend.core.logger import logger
from backend.models.base import get_db
from backend.models.rebalancing_action import (
    RebalancingAction,
    ACTION_STEP_INJECTED, ACTION_STEP_WAITING, ACTION_STEP_DRAINING,
    ACTION_STEP_TERMINATING, ACTION_STEP_CLEANUP, ACTION_STEP_DONE,
)
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

# ── apply_recommended_config stagger ──────────────────────────────────────────
# manual_apply actions are staggered by this interval (stored in action_metadata.scheduled_start_at).
STAGGER_DELAY_SECONDS = 30


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


def _advance_action_step(db: Session, action: RebalancingAction, step: str) -> None:
    """
    Persist the Karpenter-specific phase journal step to the DB immediately.

    Writes ``action.action_step = step`` and issues a targeted UPDATE so the
    value is committed even if the outer transaction later rolls back.  This
    gives crash-safe resume: on next Celery beat the worker reads ``action_step``
    and skips already-completed stages (e.g. skips re-creating the trigger pod
    if ``action_step == WAITING_SPOT`` and a trigger pod name is already stored
    in ``action_metadata``).

    Step ordering:
        INJECTED → WAITING_SPOT → DRAINING → TERMINATING → CLEANUP → DONE

    Safe to call multiple times for the same step — the DB write is idempotent.
    """
    try:
        from sqlalchemy import text as _sql_text
        action.action_step = step
        db.execute(
            _sql_text(
                "UPDATE rebalancing_actions SET action_step = :step WHERE id = :id"
            ),
            {"step": step, "id": action.id},
        )
        db.commit()
        logger.debug(f"[step_journal] action={action.id}: step → {step}")
    except Exception as _ase:
        logger.warning(f"[step_journal] action={action.id} advance to {step} failed: {_ase}")
        try:
            db.rollback()
        except Exception:
            pass


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

        # Also query Karpenter-managed nodes (tagged karpenter.sh/nodepool, same cluster tag)
        # Karpenter tags nodes with kubernetes.io/cluster/{name} but may use "" value
        # instead of "owned"/"shared", so query separately without value constraint.
        try:
            _karp_response = ec2.describe_instances(
                Filters=[
                    {'Name': 'tag:karpenter.sh/nodepool', 'Values': ['*']},
                    {'Name': f'tag:kubernetes.io/cluster/{cluster.name}', 'Values': ['*']},
                    {'Name': 'instance-state-name', 'Values': ['running']},
                ]
            )
            _karp_added = 0
            for _kr in _karp_response.get('Reservations', []):
                for _ki in _kr.get('Instances', []):
                    _kiid = _ki['InstanceId']
                    if _kiid not in aws_instance_map:
                        aws_instance_map[_kiid] = {
                            'lifecycle': _ki.get('InstanceLifecycle', 'on-demand'),
                            'instance_type': _ki.get('InstanceType', ''),
                            'az': (_ki.get('Placement') or {}).get('AvailabilityZone', ''),
                            'private_ip': _ki.get('PrivateIpAddress', ''),
                        }
                        _karp_added += 1
            if _karp_added:
                logger.info(
                    f"[aws_sync] Karpenter discovery: found {_karp_added} additional "
                    f"Karpenter-managed instances for cluster {cluster.name}"
                )
        except Exception as _karp_err:
            logger.debug(f"[aws_sync] Karpenter instance query failed: {_karp_err}")
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
                # Fix 14: Do NOT flip terminated→running if the rebalancer just
                # terminated this instance.  AWS propagates the state change with a
                # delay (1-10 s); during that window describe_instances still reports
                # "running", so aws_sync would undo the rebalancer's DB write,
                # causing the old OD node to re-enter the candidate list and trigger
                # a SECOND replacement launch → permanent cluster growth.
                # Guard: check Redis key set by the rebalancer immediately after
                # calling terminate_instances (TTL 120 s, covers the AWS propagation lag).
                _skip_state_reset = False
                if db_inst.state == 'terminated':
                    try:
                        from backend.core.redis_client import get_redis_client as _grc_f14
                        _r_f14 = _grc_f14()
                        if _r_f14 and _r_f14.exists(f"spot:recently_terminated:{db_inst.instance_id}"):
                            _skip_state_reset = True
                            logger.info(
                                f"[aws_sync] Fix14: {db_inst.instance_id} is terminated in DB "
                                f"and recently_terminated key exists — NOT resetting to running "
                                f"(AWS propagation delay)"
                            )
                    except Exception:
                        _skip_state_reset = True  # safe default: don't overwrite
                if not _skip_state_reset and db_inst.state != 'running':
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


def _sync_instance_state_from_k8s(db: Session, cluster: Cluster):
    """
    K8s-node-based fallback sync: mark DB instances as terminated when their
    registered node_name is no longer present in the live K8s cluster.

    This is called *after* _sync_instance_state_from_aws so that the AWS sync
    (when available) still takes precedence. When AWS credentials are NOT
    configured, this function ensures stale instance records accumulated from
    terminated Karpenter/spot nodes are cleaned up using only the K8s API.
    """
    try:
        from backend.services.karpenter_service import KarpenterService as _KS_k8ssync
        from kubernetes import client as _k8s_c_k8ssync
        _ks_k8ssync = _KS_k8ssync(db=db)
        _k8s_api_k8ssync = _ks_k8ssync._get_k8s_client(cluster)
        if _k8s_api_k8ssync is None:
            logger.debug(f"[k8s_sync] No K8s client for cluster {cluster.name}, skipping")
            return

        _core_v1_k8ssync = _k8s_c_k8ssync.CoreV1Api(_k8s_api_k8ssync)
        _live_nodes_resp = _core_v1_k8ssync.list_node()
        _live_node_names = {n.metadata.name for n in _live_nodes_resp.items}

        if not _live_node_names:
            # Empty node list is suspicious (API error / transient) — skip to avoid
            # falsely terminating all running instances.
            logger.debug(f"[k8s_sync] Empty node list for cluster {cluster.name}, skipping")
            return

        _db_instances = (
            db.query(Instance)
            .filter(
                Instance.cluster_id == cluster.id,
                Instance.state == 'running',
                Instance.node_name.isnot(None),
            )
            .all()
        )

        _k8s_terminated = 0
        for _inst in _db_instances:
            if _inst.node_name and _inst.node_name not in _live_node_names:
                _inst.state = 'terminated'
                _inst.status = 'terminated'
                _k8s_terminated += 1
                logger.info(
                    f"[k8s_sync] Marked {_inst.instance_id} (node={_inst.node_name}) as "
                    f"terminated — node absent from live K8s cluster {cluster.name} "
                    f"(live: {sorted(_live_node_names)})"
                )

        if _k8s_terminated:
            db.commit()
            logger.warning(
                f"[k8s_sync] Cluster {cluster.name}: {_k8s_terminated} stale instance(s) "
                f"marked terminated (node_name not in live K8s)"
            )
        else:
            logger.debug(
                f"[k8s_sync] Cluster {cluster.name}: all running DB instances have live K8s nodes"
            )
    except Exception as _k8s_sync_err:
        logger.debug(f"[k8s_sync] K8s sync skipped for cluster {cluster.name}: {_k8s_sync_err}")


# _launch_spot_instance_direct() removed — all node provisioning now goes through
# Karpenter NodePool updates. The auto-rebalancer patches the NodePool with the
# target instance type, and Karpenter provisions the replacement node.


def execute_rebalancing_action(db: Session, action: RebalancingAction, _batch_lock_held: bool = False):
        """Execute a single rebalancing action with full cross-system safety gates.
        
        Args:
            _batch_lock_held: When True, the caller already holds the per-cluster
                rebalance lock for a parallel batch. Skip lock acquisition/release
                so all batch actions execute concurrently without deferring each other.
        """
        from backend.core.redis_client import get_redis_client, key_cluster_cooldown, key_rebalance_lock
        from backend.services.cooldown_controller import CooldownController
        from backend.services.distributed_locks import distributed_lock

        # Track lock state outside try so finally can always release it
        _lock_key_release = None
        _redis_release = None

        try:
            logger.info(f"Executing rebalancing action {action.id}: {action.cluster_id} ({action.source_pool} → {action.target_pool})")

            # ── STAGGER GUARD ────────────────────────────────────────────────
            # apply_recommended_config stores a scheduled_start_at in action_metadata
            # so parallel migrations start 30 s apart.  Skip execution this cycle
            # if it is too early; the action stays in_progress and is retried.
            _action_meta_sg = action.action_metadata or {}
            _sched_start = _action_meta_sg.get("scheduled_start_at")
            if _sched_start:
                try:
                    _sched_dt = datetime.fromisoformat(_sched_start)
                    if datetime.utcnow() < _sched_dt:
                        logger.debug(
                            f"[auto_rebalancer] Action {action.id} stagger: scheduled at "
                            f"{_sched_start}, skipping until then."
                        )
                        return  # stay in_progress; executed next cycle
                except Exception:
                    pass  # malformed timestamp — proceed immediately

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

            # ── KARPENTER PAUSE GUARD ────────────────────────────────────────
            # If the agent saw a disruptive Karpenter event (Consolidated,
            # DisruptionLaunched, NodeClaimDeleted, TerminatingNodeClaim) recently,
            # a 120-second pause key is set in Redis.  Defer rather than fight
            # Karpenter while it is actively consolidating / disrupting.
            _karpenter_pause_key = f"spot:karpenter_pause:{action.cluster_id}"
            if _redis.exists(_karpenter_pause_key):
                _pause_reason = (_redis.get(_karpenter_pause_key) or b'').decode()
                _pause_ttl = _redis.ttl(_karpenter_pause_key)
                logger.info(
                    f"[auto_rebalancer] Karpenter pause active for cluster {action.cluster_id} "
                    f"(reason={_pause_reason!r}, {_pause_ttl}s remaining) — deferring action {action.id}"
                )
                action.status = 'deferred'
                action.error_message = f"Karpenter pause active ({_pause_reason}, {_pause_ttl}s remaining)"
                db.commit()
                return

            # ── CONCURRENCY LOCK GUARD ───────────────────────────────────────
            # Ensure only one rebalancing cycle runs at a time per cluster.
            # Problem #1/#7: Lock TTL was 600s but actions can take up to 30 min.
            # Fix: Set initial TTL to 2700s (45 min) and heartbeat every 60s.
            # NEW-3 fix: Exactly matches the 45-min stale action expiry — lock
            # cannot release before stale detection fires if heartbeat stops.
            #
            # BATCH FIX: When _batch_lock_held=True, the caller (batch execution
            # loop) already holds the cluster lock. Skip acquisition so all batch
            # actions run in parallel without deferring each other.
            if _batch_lock_held:
                _lock_acquired = True  # caller owns the lock
                _redis_release = _redis  # needed for cleanup helpers
                logger.debug(
                    f"[auto_rebalancer] Action {action.id}: batch lock held by caller — "
                    f"skipping lock acquisition"
                )
            else:
                _lock_key = key_rebalance_lock(action.cluster_id)
                _lock_acquired = _redis.set(_lock_key, str(action.id), nx=True, ex=2700)
            if _lock_acquired and not _batch_lock_held:
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

            # ── CRASH-SAFE RESUME GUARD ──────────────────────────────────────
            # If a previous worker crashed mid-Phase-1 (after NodePool was
            # patched but before the outer commit), action_step will already
            # be INJECTED or later.  Phase 1 was committed — skip it entirely
            # and let the waiting_agent loop handle Phase 2 onwards.
            _resume_step = action.action_step
            if _resume_step in (
                ACTION_STEP_INJECTED, ACTION_STEP_WAITING,
                ACTION_STEP_DRAINING, ACTION_STEP_TERMINATING,
                ACTION_STEP_CLEANUP,
            ):
                logger.info(
                    f"[auto_rebalancer] Crash-safe resume: action {action.id} "
                    f"step={_resume_step} — Phase 1 already committed, routing "
                    f"to waiting_agent loop"
                )
                if action.status != 'waiting_agent':
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
                                    # ── Direct K8s Karpenter pod check (fallback) ──
                                    # Agent heartbeats may not reach the backend, so the
                                    # Redis key never gets refreshed. Check directly.
                                    _k8s_karp_found = False
                                    try:
                                        from backend.services.karpenter_service import KarpenterService as _KS_kp
                                        from backend.core.redis_client import get_redis_client as _grc_kp
                                        _ks_kp = _KS_kp(db, _grc_kp())
                                        _det_result = _ks_kp.detect_karpenter_in_cluster(
                                            action.cluster_id, db
                                        )
                                        _k8s_karp_found = _det_result.get('detected', False)
                                    except Exception as _k8s_kp_err:
                                        logger.debug(
                                            f"[auto_rebalancer] Direct Karpenter detection "
                                            f"failed: {_k8s_kp_err}"
                                        )
                                    if not _k8s_karp_found:
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
                        action.completed_at = datetime.utcnow()
                        action.duration_seconds = int((action.completed_at - action.started_at).total_seconds()) if action.started_at else 0
                        # Clean up Redis locks so this instance isn't blocked for 24h
                        try:
                            _fail_meta_kp = dict(action.action_metadata or {})
                            _cleanup_rebalancing_resources(
                                action, _fail_meta_kp, _redis, db,
                                decr_semaphore=True,
                            )
                        except Exception:
                            pass
                        db.commit()
                        return

                    # ── PRE-FLIGHT: Ensure Karpenter node role has EKS cluster access ──
                    # Without this, Karpenter-provisioned nodes cannot join the K8s cluster
                    # (they boot but immediately fail the bootstrap handshake).
                    # The agent registers this during install_karpenter(), but it can fail
                    # silently or be deleted.  Verify + auto-fix every Phase 1 run.
                    _auth_check_key = f"spot:karpenter_auth_verified:{action.cluster_id}"
                    _auth_cached = _redis.get(_auth_check_key) if _redis else None
                    if not _auth_cached:
                        try:
                            import boto3 as _b3_auth
                            from backend.utils.aws.asg import get_assumed_credentials as _gac_auth
                            _auth_creds = _gac_auth(cluster, db)
                            _auth_region = cluster.region or 'ap-south-1'
                            _sts_auth = _b3_auth.client('sts', region_name=_auth_region, **_auth_creds)
                            _auth_account_id = _sts_auth.get_caller_identity()['Account']
                            _karp_role_arn = f"arn:aws:iam::{_auth_account_id}:role/KarpenterNodeRole-{cluster.name}"
                            _eks_auth = _b3_auth.client('eks', region_name=_auth_region, **_auth_creds)

                            # Check if EKS access entry exists for the Karpenter node role
                            _access_entry_ok = False
                            try:
                                _eks_auth.describe_access_entry(
                                    clusterName=cluster.name,
                                    principalArn=_karp_role_arn
                                )
                                _access_entry_ok = True
                                logger.debug(
                                    f"[auto_rebalancer] EKS access entry verified for "
                                    f"{_karp_role_arn}"
                                )
                            except _eks_auth.exceptions.ResourceNotFoundException:
                                pass
                            except Exception as _ae_desc_err:
                                logger.debug(
                                    f"[auto_rebalancer] EKS access entry check failed: "
                                    f"{_ae_desc_err}"
                                )

                            if not _access_entry_ok:
                                # Auto-fix: create EC2_LINUX access entry
                                try:
                                    _eks_auth.create_access_entry(
                                        clusterName=cluster.name,
                                        principalArn=_karp_role_arn,
                                        type='EC2_LINUX'
                                    )
                                    _access_entry_ok = True
                                    logger.info(
                                        f"[auto_rebalancer] AUTO-FIX: Created EC2_LINUX "
                                        f"access entry for {_karp_role_arn} — Karpenter "
                                        f"nodes can now join the cluster"
                                    )
                                except Exception as _ae_create_err:
                                    # Access entries API may be unavailable (older EKS or
                                    # cluster authentication mode = CONFIG_MAP only).
                                    # Fall back to checking/patching aws-auth ConfigMap.
                                    logger.warning(
                                        f"[auto_rebalancer] EKS access entry creation "
                                        f"failed ({_ae_create_err}). "
                                        f"Checking aws-auth ConfigMap fallback."
                                    )
                                    try:
                                        from backend.services.karpenter_service import KarpenterService as _KS_AUTH
                                        _ks_auth = _KS_AUTH(db, _redis)
                                        _k8s_api_auth = _ks_auth._get_k8s_client(cluster)
                                        from kubernetes import client as _k8s_auth_cl
                                        _core_auth = _k8s_auth_cl.CoreV1Api(_k8s_api_auth)
                                        _cm = _core_auth.read_namespaced_config_map(
                                            'aws-auth', 'kube-system'
                                        )
                                        import yaml as _yaml_auth
                                        _map_roles = _yaml_auth.safe_load(
                                            _cm.data.get('mapRoles', '[]')
                                        ) or []
                                        _role_present = any(
                                            _karp_role_arn in (r.get('rolearn', '') or '')
                                            for r in _map_roles
                                        )
                                        if not _role_present:
                                            _map_roles.append({
                                                'rolearn': _karp_role_arn,
                                                'username': 'system:node:{{EC2PrivateDNSName}}',
                                                'groups': [
                                                    'system:bootstrappers',
                                                    'system:nodes',
                                                ],
                                            })
                                            _cm.data['mapRoles'] = _yaml_auth.dump(
                                                _map_roles, default_flow_style=False
                                            )
                                            _core_auth.replace_namespaced_config_map(
                                                'aws-auth', 'kube-system', _cm
                                            )
                                            _access_entry_ok = True
                                            logger.info(
                                                f"[auto_rebalancer] AUTO-FIX: Patched "
                                                f"aws-auth ConfigMap with {_karp_role_arn}"
                                            )
                                        else:
                                            _access_entry_ok = True
                                            logger.debug(
                                                f"[auto_rebalancer] aws-auth ConfigMap "
                                                f"already has {_karp_role_arn}"
                                            )
                                    except Exception as _cm_err:
                                        logger.warning(
                                            f"[auto_rebalancer] aws-auth ConfigMap "
                                            f"fallback failed: {_cm_err}"
                                        )

                            if _access_entry_ok and _redis:
                                # Cache verification for 1 hour to avoid repeated API calls
                                _redis.setex(_auth_check_key, 3600, '1')
                            elif not _access_entry_ok:
                                logger.error(
                                    f"[auto_rebalancer] CRITICAL: Cannot verify Karpenter "
                                    f"node role access for {cluster.name}. Karpenter nodes "
                                    f"may fail to join the cluster. Proceeding with warning."
                                )
                        except Exception as _auth_err:
                            logger.warning(
                                f"[auto_rebalancer] Karpenter auth pre-flight check "
                                f"failed: {_auth_err}. Proceeding without verification."
                            )

                    # Validate capacity via dry-run before updating NodePool
                    # Enhancement 5: Parallel dry-runs — run uncached checks concurrently
                    try:
                        from backend.core.redis_client import get_redis_client as _grc_dr
                        from backend.utils.aws.dry_run import dry_run_pool as _dr_pool
                        _dr_redis = _grc_dr()
                        _verified_types = []
                        _dr_region = cluster.region or "ap-south-1"
                        _dr_max_checks = 5

                        # Separate cached hits from uncached types
                        _dr_uncached = []
                        for _lt in ml_instance_types:
                            _dr_key = f"dry_run:{_lt}:{target_az}"
                            _dr_cached = _dr_redis.get(_dr_key)
                            if _dr_cached:
                                _dr_val = _dr_cached.decode() if isinstance(_dr_cached, bytes) else _dr_cached
                                if _dr_val != "fail":
                                    _verified_types.append(_lt)
                            else:
                                _dr_uncached.append(_lt)

                        # Run uncached dry-runs in parallel (boto3 is thread-safe per-client)
                        if _dr_uncached:
                            _dr_uncached = _dr_uncached[:_dr_max_checks]
                            from concurrent.futures import ThreadPoolExecutor as _TPE_DR, as_completed as _as_completed_dr
                            def _dr_check(itype):
                                return itype, _dr_pool(region=_dr_region, instance_type=itype, az=target_az, redis=_dr_redis)
                            with _TPE_DR(max_workers=min(5, len(_dr_uncached))) as _dr_executor:
                                _dr_futures = [_dr_executor.submit(_dr_check, t) for t in _dr_uncached]
                                for _dr_f in _as_completed_dr(_dr_futures):
                                    try:
                                        _dr_t, _dr_ok = _dr_f.result()
                                        if _dr_ok:
                                            _verified_types.append(_dr_t)
                                    except Exception:
                                        pass
                            # Pass through any uncached types beyond _dr_max_checks (benefit of doubt)
                            _dr_checked_set = set(_dr_uncached)
                            for _lt in ml_instance_types:
                                if _lt not in _dr_checked_set:
                                    _dr_key2 = f"dry_run:{_lt}:{target_az}"
                                    _dr_cached2 = _dr_redis.get(_dr_key2)
                                    if _dr_cached2:
                                        _dr_val2 = _dr_cached2.decode() if isinstance(_dr_cached2, bytes) else _dr_cached2
                                        if _dr_val2 != "fail" and _lt not in _verified_types:
                                            _verified_types.append(_lt)
                                    elif _lt not in _verified_types:
                                        # Unchecked (beyond cap) — benefit of doubt
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
                    # Inject only the #1 ML-ranked type per action (not top-8) so the
                    # NodePool stays clean and doesn't drift toward a "allow everything" state.
                    # The target NodePool is resolved from the source node's
                    # karpenter.sh/nodepool label so secondary pools are never contaminated.
                    _nodepool_updated = False
                    _patched_nodepool_names = []
                    _added_types = []
                    try:
                        from backend.services.karpenter_service import KarpenterService
                        _karp_svc = KarpenterService(db, _redis)

                        # ── A6: Resolve target NodePool from source node label ─────────
                        # Read karpenter.sh/nodepool label from the EC2 instance's K8s node
                        # so we inject only into the pool actually managing this workload.
                        # K-5 fix: 3-tier NodePool resolution
                        # Tier 1: read karpenter.sh/nodepool label from source node
                        # Tier 2: try spot-general (created by NodePoolReconcilerService)
                        # Tier 3: fall back to default
                        # After resolution, verify the chosen NodePool actually exists.
                        _target_nodepool_name = None
                        try:
                            _nl_api_client = _karp_svc._get_k8s_client(cluster)
                            from kubernetes import client as _k8s_nl_cl
                            _nl_custom = _k8s_nl_cl.CustomObjectsApi(_nl_api_client)
                            _nl_core = _k8s_nl_cl.CoreV1Api(_nl_api_client)
                            _nl_nodes = _nl_core.list_node(
                                label_selector='karpenter.sh/nodepool'
                            ).items
                            _src_provider_id_suffix = (
                                f"/{instance_id_for_action}" if instance_id_for_action
                                else ''
                            )
                            # Tier 1 — source node label
                            for _nl_node in _nl_nodes:
                                _nl_pid = (_nl_node.spec.provider_id or '') if _nl_node.spec else ''
                                if _src_provider_id_suffix and _nl_pid.endswith(_src_provider_id_suffix):
                                    _nl_labels = (_nl_node.metadata.labels or {})
                                    _resolved_pool = _nl_labels.get('karpenter.sh/nodepool', '')
                                    if _resolved_pool:
                                        _target_nodepool_name = _resolved_pool
                                    break

                            # Tier 2 / 3 — spot-general → default (verify existence)
                            if not _target_nodepool_name:
                                for _candidate_pool in ('spot-general', 'default'):
                                    try:
                                        _nl_custom.get_cluster_custom_object(
                                            group='karpenter.sh', version='v1',
                                            plural='nodepools', name=_candidate_pool,
                                        )
                                        _target_nodepool_name = _candidate_pool
                                        logger.info(
                                            f"[auto_rebalancer] Phase 1 K-5: resolved NodePool "
                                            f"'{_candidate_pool}' for ASG source node {instance_id_for_action}"
                                        )
                                        break
                                    except Exception:
                                        continue

                            if not _target_nodepool_name:
                                logger.error(
                                    f"[auto_rebalancer] Phase 1 K-5: no spot NodePool found "
                                    f"(tried spot-general, default) for cluster {action.cluster_id} "
                                    f"— aborting Phase 1. Install Karpenter and bootstrap NodePool first."
                                )
                                action.status = 'failed'
                                action.error_message = 'no_spot_nodepool_exists'
                                db.commit()
                        except Exception as _nl_err:
                            _target_nodepool_name = _target_nodepool_name or 'default'
                            logger.warning(
                                f"[auto_rebalancer] Phase 1 K-5: NodePool resolution failed: {_nl_err} "
                                f"— using '{_target_nodepool_name}'"
                            )

                        # ── A5: Inject only the #1 ML-ranked type ────────────────────
                        # trust_ml_ranking: use target_instance_type (top-1 by ranking)
                        # and only fall back to ml_instance_types[0] when it is absent.
                        # Skip if no NodePool was resolved (action already marked failed above).
                        if _target_nodepool_name:
                            _types_to_patch = (
                                [target_instance_type] if target_instance_type
                                else ml_instance_types[:1]
                            )
                            for _kp_itype in _types_to_patch:
                                _kp_result = _karp_svc.add_allowed_instance_type(
                                    cluster_id=action.cluster_id,
                                    instance_type=_kp_itype,
                                    nodepool_name=_target_nodepool_name,
                                )
                                if _kp_result:
                                    _nodepool_updated = True
                                    if _target_nodepool_name not in _patched_nodepool_names:
                                        _patched_nodepool_names.append(_target_nodepool_name)
                                    _added_types.append(_kp_itype)
                                else:
                                    logger.warning(
                                        f"[auto_rebalancer] Phase 1: Failed to add {_kp_itype} to NodePool {_target_nodepool_name}"
                                    )
                            if _added_types:
                                logger.info(
                                    f"[auto_rebalancer] Phase 1: Added {len(_added_types)} ML-ranked types "
                                    f"{_added_types} to NodePool '{_target_nodepool_name}' "
                                    f"for cluster {cluster.name}"
                                )
                    except Exception as _kp_err:
                        logger.error(f"[auto_rebalancer] Phase 1: NodePool update failed: {_kp_err}")

                    if not _nodepool_updated:
                        # Enhancement 8: Non-blocking retry — defer instead of fail
                        # so the next Celery cycle retries the PATCH (max 3 attempts).
                        _np_retry = int((action.action_metadata or {}).get('nodepool_patch_retries', 0))
                        if _np_retry < 3:
                            _np_meta = dict(action.action_metadata or {})
                            _np_meta['nodepool_patch_retries'] = _np_retry + 1
                            action.action_metadata = _np_meta
                            action.status = 'deferred'
                            action.error_message = (
                                f"NodePool PATCH failed (attempt {_np_retry + 1}/3) — retrying next cycle"
                            )
                            logger.warning(
                                f"[auto_rebalancer] Phase 1: NodePool PATCH deferred "
                                f"(attempt {_np_retry + 1}/3) for action {action.id}"
                            )
                            db.commit()
                            return
                        action.status = 'failed'
                        action.error_message = (
                            f"Failed to update Karpenter NodePool with any of {ml_instance_types[:3]} "
                            f"after 3 attempts"
                        )
                        db.commit()
                        return

                    # Store metadata for Phase 2 tracking
                    _meta_update_p1 = dict(action.action_metadata or {})
                    _meta_update_p1.pop('nodepool_patch_retries', None)  # E8: clear retry counter
                    _meta_update_p1.pop('nodepool_patch_failed', None)   # E8: clear stale failed flag
                    _meta_update_p1['karpenter_nodepool_updated'] = True
                    _meta_update_p1['karpenter_target_types'] = ml_instance_types[:1]
                    _meta_update_p1['karpenter_nodepool_name'] = _patched_nodepool_names[0] if _patched_nodepool_names else "default"
                    _meta_update_p1['karpenter_patched_nodepools'] = _patched_nodepool_names
                    _meta_update_p1['phase1_completed_at'] = datetime.utcnow().isoformat()
                    _meta_update_p1['phase2_params'] = {
                        'instance_id': instance_id_for_action,
                        'instance_type': source_instance_type,
                        'az': target_az or source_az or '',
                    }
                    action.action_metadata = _meta_update_p1
                    action.current_state = 'WAITING_FOR_KARPENTER'
                    # ── Step journal: NodePool successfully patched ───────────────────
                    _advance_action_step(db, action, ACTION_STEP_INJECTED)

                    logger.info(
                        f"[auto_rebalancer] Phase 1 (Karpenter): NodePool updated with "
                        f"types {ml_instance_types[:3]} — awaiting Karpenter to provision spot node. "
                        f"Source: {source_instance_type}:{source_az}"
                    )

                    # NOTE: 24h cooldown key is now set at COMPLETION (Phase 2 done),
                    # not here at Phase 1.  Setting it early blocked other OD instances
                    # from being batched in the same cycle if the action was slow or failed.

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
                _baseline_spots = db.query(Instance).filter(
                    Instance.cluster_id == action.cluster_id,
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.state == 'running',
                ).all()
                _spot_baseline = len(_baseline_spots)
                _meta_update['spot_baseline_count'] = _spot_baseline
                # Fix #2: Store baseline spot instance IDs for set-diff detection
                # when baseline=0 the count-based gate is ambiguous.
                _meta_update['baseline_spot_instance_ids'] = [
                    s.instance_id for s in _baseline_spots if s.instance_id
                ]
            except Exception:
                _meta_update['spot_baseline_count'] = 0
                _meta_update['baseline_spot_instance_ids'] = []
            action.action_metadata = _meta_update

            # ── Enhancement 3: Create trigger pod at end of Phase 1 ────────
            # Instead of waiting for the next Celery cycle (15s) to create the trigger
            # pod in Step 0 of the wait loop, create it now — saves one Celery tick.
            # The 10s NodePool propagation delay (Enhancement 2) already elapsed:
            # NodePool PATCH + read-back verification + metadata save takes ~5-15s.
            try:
                from backend.services.karpenter_service import KarpenterService as _KS_P1TRIG
                _ks_p1 = _KS_P1TRIG(db, get_redis_client())
                _p1_trig_name = f"spot-trigger-{action.id}"
                _p1_trig_type = ""
                if action.target_pool and ':' in action.target_pool:
                    _p1_trig_type = action.target_pool.split(':')[0]
                elif action.target_pool:
                    _p1_trig_type = action.target_pool

                # Label existing nodes so trigger pod stays Pending
                _p1_existing = []
                try:
                    _p1_cluster = db.query(Cluster).filter(Cluster.id == action.cluster_id).first()
                    if _p1_cluster:
                        _p1_k8s = _ks_p1._get_k8s_client(_p1_cluster)
                        from kubernetes import client as _k8s_p1c
                        _p1_core = _k8s_p1c.CoreV1Api(_p1_k8s)
                        _p1_nodes = _p1_core.list_node().items
                        _p1_existing = [n.metadata.name for n in _p1_nodes]
                        _p1_label = {"metadata": {"labels": {"spot-optimizer.io/existing-node": "true"}}}
                        from concurrent.futures import ThreadPoolExecutor as _TPE_P1
                        def _label_node_p1(node_name):
                            try:
                                _p1_core.patch_node(node_name, _p1_label)
                            except Exception:
                                pass
                        with _TPE_P1(max_workers=10) as _pool_p1:
                            list(_pool_p1.map(_label_node_p1, _p1_existing))
                        logger.info(
                            f"[auto_rebalancer] Phase 1 trigger: labelled {len(_p1_existing)} "
                            f"existing nodes"
                        )
                except Exception as _p1_label_err:
                    logger.warning(f"[auto_rebalancer] Phase 1 trigger: node labelling error: {_p1_label_err}")

                # Workload-aware sizing (same as wait loop)
                _p1_cpu = "100m"
                _p1_mem = "128Mi"
                try:
                    _p1_src_id = _meta_update.get("instance_id", "") or (action.source_instance_id or "")
                    if _p1_src_id:
                        _p1_src = db.query(Instance).filter(Instance.instance_id == _p1_src_id).first()
                        _p1_node = _p1_src.node_name if _p1_src else None
                        if _p1_node:
                            from backend.models.pod_metric import PodMetric as _PM_P1
                            from sqlalchemy import func as _sqla_p1
                            _p1_ts = db.query(_sqla_p1.max(_PM_P1.timestamp)).filter(
                                _PM_P1.cluster_id == action.cluster_id,
                                _PM_P1.node_name == _p1_node,
                            ).scalar()
                            if _p1_ts:
                                _p1_pods = db.query(
                                    _sqla_p1.coalesce(_sqla_p1.sum(_PM_P1.cpu_request_millicores), 0),
                                    _sqla_p1.coalesce(_sqla_p1.sum(_PM_P1.memory_request_bytes), 0),
                                ).filter(
                                    _PM_P1.cluster_id == action.cluster_id,
                                    _PM_P1.node_name == _p1_node,
                                    _PM_P1.timestamp == _p1_ts,
                                    _sqla_p1.coalesce(_PM_P1.controller_kind, '') != 'DaemonSet',
                                ).first()
                                if _p1_pods:
                                    _cpu_m = max(int(int(_p1_pods[0] or 0) * 1.1), 100)
                                    _mem_mi = max(int((int(_p1_pods[1] or 0) * 1.1) / (1024 * 1024)), 128)
                                    _p1_cpu = f"{_cpu_m}m"
                                    _p1_mem = f"{_mem_mi}Mi"
                except Exception:
                    pass

                _p1_nodepool = _meta_update.get('karpenter_nodepool_name', 'default')
                _p1_result = _ks_p1.create_spot_trigger_pod(
                    cluster_id=action.cluster_id,
                    pod_name=_p1_trig_name,
                    target_instance_type=_p1_trig_type,
                    nodepool_name=_p1_nodepool,
                    exclude_nodes=_p1_existing,
                    cpu_request=_p1_cpu,
                    memory_request=_p1_mem,
                )
                if _p1_result:
                    _meta_update['trigger_pod_created'] = True
                    _meta_update['trigger_pod_name'] = _p1_trig_name
                    _meta_update['trigger_pod_instance_type'] = _p1_trig_type
                    _meta_update['trigger_cpu'] = _p1_cpu
                    _meta_update['trigger_mem'] = _p1_mem
                    action.action_metadata = _meta_update
                    logger.info(
                        f"[auto_rebalancer] Phase 1: Created trigger pod '{_p1_trig_name}' "
                        f"immediately (nodepool={_p1_nodepool}, type={_p1_trig_type})"
                    )
                else:
                    logger.warning(
                        f"[auto_rebalancer] Phase 1: Trigger pod creation failed — "
                        f"will retry in wait loop"
                    )
            except Exception as _p1_trig_err:
                logger.warning(f"[auto_rebalancer] Phase 1 trigger pod error: {_p1_trig_err}")

            # ── Step journal: trigger pod created / waiting for Karpenter provision ──
            _advance_action_step(db, action, ACTION_STEP_WAITING)
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
            # Fix: Full resource cleanup on Phase 1 exception — prevents stale Redis
            # keys (node_active_action, active_count) from blocking future actions.
            try:
                from backend.core.redis_client import get_redis_client as _grc_sem_fail
                _sem_fail_redis = _grc_sem_fail()
                _fail_meta_cleanup = dict(action.action_metadata or {})
                _cleanup_rebalancing_resources(
                    action, _fail_meta_cleanup, _sem_fail_redis, db,
                    decr_semaphore=True,
                )
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
            # Fix: On deferred/failed early exit, release node_active_action lock and
            # DECR semaphore so the instance isn't blocked for 24h. The except block
            # already handles crash failures; this covers deferred early returns.
            # _cleanup_rebalancing_resources is idempotent so double-call is safe.
            if action.status in ('deferred', 'failed'):
                try:
                    from backend.core.redis_client import get_redis_client as _grc_defer
                    _defer_redis = _redis_release or _grc_defer()
                    _defer_meta = dict(action.action_metadata or {})
                    _cleanup_rebalancing_resources(
                        action, _defer_meta, _defer_redis, db,
                        decr_semaphore=True,
                    )
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

            # ── P2 GUARD: reject Karpenter-managed nodes from OD seeding ────
            # If Redis telemetry carries karpenter labels (capacity-type=spot OR
            # nodepool tag present), this node is already Karpenter-managed spot.
            # Seeding it as ON_DEMAND would make the AR try to "migrate" it,
            # causing a redundant action on an already-spot node.
            _labels = _data.get('labels', {}) or {}
            _karp_capacity = _labels.get('karpenter.sh/capacity-type', '')
            _karp_nodepool = _labels.get('karpenter.sh/nodepool', '')
            if _karp_capacity == 'spot' or (
                _karp_nodepool and 'spot' in _karp_nodepool.lower()
            ):
                logger.debug(
                    f"[seed_redis] Skipping node {node_name} in cluster "
                    f"{cluster.id}: Karpenter spot node — not seeding as OD"
                )
                continue
            # Reject nodes with no cluster region: az would default to a wrong AZ
            # which bypasses the region-scoped stale-mark and creates immortal ghosts.
            if not getattr(cluster, 'region', None):
                logger.debug(
                    f"[seed_redis] Skipping node {node_name}: cluster has no region — "
                    f"cannot determine correct AZ for synthetic instance"
                )
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


# ── Idempotent cleanup for failed/completed rebalancing actions ───────────────
# Cleans ALL Redis keys, trigger pods, and cancels orphaned PENDING agent actions.
# Safe to call multiple times — every operation is idempotent.

def _cleanup_rebalancing_resources(wa, wa_meta, redis_client, db, *, decr_semaphore=True):
    """Clean up stale Redis keys, trigger pods, and PENDING agent actions.

    Must be called on EVERY exit path (fail or complete) to prevent:
      - spot:node_active_action stuck for 30 min (blocks next rebalancing)
      - rebalance:active_count stuck >0 (blocks concurrent actions)
      - Orphan trigger pods wasting cluster resources
      - Orphan PENDING agent actions never executed
    """
    # ── Step journal: entering cleanup (success or failure) ───────────────
    if getattr(wa, 'action_step', None) not in (ACTION_STEP_DONE, None):
        _advance_action_step(db, wa, ACTION_STEP_CLEANUP)

    _inst_id = wa_meta.get("instance_id", "") or (getattr(wa, 'source_instance_id', None) or "")

    # 1. Delete per-node active action lock (24h TTL safety net, but explicit is better)
    if _inst_id and redis_client:
        try:
            redis_client.delete(f"spot:node_active_action:{_inst_id}")
        except Exception:
            pass

    # Change 2: Clear draining key so PC can schedule pods on this node again
    _p2_node_cleanup = (wa_meta or {}).get('target_node_name') or (wa_meta or {}).get('target_node')
    if _p2_node_cleanup and redis_client:
        try:
            redis_client.delete(f"spot:node:draining:{wa.cluster_id}:{_p2_node_cleanup}")
        except Exception:
            pass

    # 2. DECR concurrent action semaphore (floor at 0)
    if decr_semaphore and redis_client:
        try:
            _sem_key = f"rebalance:active_count:{wa.cluster_id}"
            _new_val = redis_client.decr(_sem_key)
            if _new_val < 0:
                redis_client.set(_sem_key, 0, ex=300)
        except Exception:
            pass

    # 3. Clean up trigger pod if one was created (Karpenter mode)
    # Always try to delete the trigger pod — derive name from action ID as fallback
    # to prevent orphaned pending pods that Karpenter may later satisfy with random types.
    _trig_name = wa_meta.get('trigger_pod_name') or f"spot-trigger-{wa.id}"
    try:
        from backend.services.karpenter_service import KarpenterService as _KS_CLN
        _ks = _KS_CLN(db, redis_client)
        _ks.delete_spot_trigger_pod(cluster_id=wa.cluster_id, pod_name=_trig_name)
        logger.info(f"[cleanup] Deleted trigger pod '{_trig_name}' for action {wa.id}")
    except Exception:
        pass

    # 4. Cancel any remaining PENDING agent actions for this rebalancing action
    try:
        from backend.models.agent_action import AgentAction as _AA_CLN, AgentActionStatus as _AAS_CLN
        from sqlalchemy import or_ as _or_cln
        _cancelled = db.query(_AA_CLN).filter(
            _or_cln(
                _AA_CLN.payload.contains({"rebalancing_action_id": wa.id}),
                _AA_CLN.payload.contains({"rebalancing_action_id": str(wa.id)}),
            ),
            _AA_CLN.status == _AAS_CLN.PENDING,
        ).update(
            {"status": "FAILED", "error_message": f"Cancelled: parent action {wa.id} {wa.status}"},
            synchronize_session=False,
        )
        if _cancelled:
            logger.info(f"[cleanup] Cancelled {_cancelled} PENDING agent actions for action {wa.id}")
    except Exception:
        pass

    # 5. KEEP replacement-instance claim alive (do NOT delete) so other actions in the
    #    same batch cannot reuse the same physical spot via time-based/stagnation fallback.
    #    The Redis key (TTL 1h) expires naturally long after the batch finishes.
    _repl_inst = wa_meta.get('replacement_spot_instance_id')
    if _repl_inst and redis_client:
        try:
            _claim_key = f"spot:replacement_claimed:{_repl_inst}"
            _owner = redis_client.get(_claim_key)
            _owner_str = _owner.decode() if isinstance(_owner, bytes) else str(_owner) if _owner else ""
            if _owner_str == str(wa.id):
                logger.info(f"[cleanup] Retained replacement claim on {_repl_inst} for action {wa.id} (prevents reuse by concurrent actions)")
        except Exception:
            pass

    # 6. Immediate NodePool rollback: proactively remove the instance types that
    #    Phase 1 injected into the NodePool, then clear the 30-min sync cooldown.
    #    Without this, Karpenter can see the orphan types in the NodePool and
    #    provision unintended instances for normal scaling events during the
    #    window before the next background sync beat.
    _kp_target_types = wa_meta.get('karpenter_target_types', [])
    _kp_patched_nps = wa_meta.get('karpenter_patched_nodepools', []) or [wa_meta.get('karpenter_nodepool_name', 'default')]
    if _kp_target_types and db:
        try:
            from backend.services.karpenter_service import KarpenterService as _KS_ROLL
            _ks_roll = _KS_ROLL(db, redis_client)
            for _rm_type in _kp_target_types:
                for _rm_np in _kp_patched_nps:
                    try:
                        _ks_roll.remove_allowed_instance_type(
                            cluster_id=wa.cluster_id,
                            instance_type=_rm_type,
                            nodepool_name=_rm_np,
                        )
                    except Exception:
                        pass  # best-effort per type per nodepool
            logger.info(
                f"[cleanup] Removed {len(_kp_target_types)} Phase-1 injected types "
                f"from NodePool(s) {_kp_patched_nps} for action {wa.id}: {_kp_target_types[:3]}"
            )
        except Exception as _roll_err:
            logger.warning(f"[cleanup] NodePool type removal failed for action {wa.id}: {_roll_err}")
    if redis_client:
        try:
            _np_cooldown_key = f"spot:karpenter:nodepool_updated:{wa.cluster_id}"
            redis_client.delete(_np_cooldown_key)
            logger.info(
                f"[cleanup] Cleared NodePool sync cooldown for cluster {wa.cluster_id} "
                f"— background sync will restore ML-ranked types on next beat"
            )
        except Exception:
            pass

    # Change 12: Clear takeover_active guard if this was a takeover action
    _wa_meta_cleanup = wa_meta or {}
    if _wa_meta_cleanup.get('mng_node'):
        try:
            redis_client.delete(f"spot:takeover_active:{wa.cluster_id}")
        except Exception:
            pass
        # ADJ-5: Increment per-node retry counter on failure
        _tko_node_name = _wa_meta_cleanup.get('target_node_name')
        if getattr(wa, 'status', '') in ('failed',) and _tko_node_name and redis_client:
            try:
                import json as _json_cleanup
                _attempt_key = f"spot:takeover_attempts:{wa.cluster_id}:{_tko_node_name}"
                redis_client.incr(_attempt_key)
                redis_client.expire(_attempt_key, 86400)
                _attempts = int(redis_client.get(_attempt_key) or 1)
                if _attempts >= 3:
                    logger.error(
                        f"[takeover] Node {_tko_node_name} failed {_attempts} times "
                        f"— marking blocked. Manual intervention required."
                    )
                    redis_client.setex(
                        f"spot:takeover_blocked_node:{wa.cluster_id}:{_tko_node_name}",
                        86400,
                        _json_cleanup.dumps({
                            "attempts": _attempts,
                            "reason": getattr(wa, 'error_message', None),
                        }),
                    )
            except Exception:
                pass


# ── Onboarding / Takeover helpers ────────────────────────────────────────────


def _derive_node_owner_type(node_labels: dict) -> str:
    """
    Classify a node's ownership type from its K8s labels.
    Returns one of: bootstrap | legacy_mng | karpenter_dynamic | unknown

    ADJ-1: Returns 'unknown' (not 'bootstrap') when classification fails.
    'unknown' is treated as no-drain but is visible in logs/dashboards.
    'bootstrap' is ONLY set when optimization-exempt=true is explicit.
    """
    if not node_labels:
        return "unknown"
    if node_labels.get("optimization-exempt") == "true":
        return "bootstrap"
    if "karpenter.sh/nodepool" in node_labels:
        return "karpenter_dynamic"
    if "eks.amazonaws.com/nodegroup" in node_labels:
        return "legacy_mng"
    return "unknown"


def _takeover_should_skip_node(node, cluster_id: str, redis, db) -> Optional[str]:
    """
    Returns a skip reason string if the node should NOT be takeover-drained.
    Returns None if the node is safe to proceed with takeover.

    Checks (in order):
      1. kube-system critical pods
      2. Singleton StatefulSets with no PDB
      3. Max takeover retry counter exceeded (ADJ-5)
    """
    import json as _json
    node_name = getattr(node, 'node_name', '') or ''

    if not node_name:
        return "missing_node_name"

    # 1. kube-system critical pods
    try:
        _pod_raw = redis.get(f"spot:node:pods:{cluster_id}:{node_name}") if redis else None
        if _pod_raw:
            _pods = _json.loads(_pod_raw)
            _system_pods = [
                p for p in _pods
                if p.get("namespace") == "kube-system"
                and p.get("priority_class") in (
                    "system-cluster-critical", "system-node-critical"
                )
            ]
            if _system_pods:
                return f"kube_system_critical_pods:{len(_system_pods)}"
    except Exception:
        pass

    # 2. Singleton StatefulSets with no PDB
    try:
        _wl_raw = redis.get(f"spot:node:workloads:{cluster_id}:{node_name}") if redis else None
        if _wl_raw:
            _workloads = _json.loads(_wl_raw)
            for _wl in _workloads:
                if (
                    _wl.get("controller_kind") in ("StatefulSet",)
                    and int(_wl.get("replicas", 2)) == 1
                    and not _wl.get("has_pdb")
                ):
                    return f"singleton_statefulset_no_pdb:{_wl.get('workload_id')}"
    except Exception:
        pass

    # 3. Max retry counter — ADJ-5
    try:
        _attempt_key = f"spot:takeover_attempts:{cluster_id}:{node_name}"
        _attempts = int(redis.get(_attempt_key) or 0) if redis else 0
        if _attempts >= 3:
            return f"max_takeover_retries_exceeded:{_attempts}"
    except Exception:
        pass

    return None


def _run_takeover_step(cluster_id: str, db, redis) -> None:
    """
    Execute one step of the MNG→Karpenter OD takeover flow.
    Enforces single-node-at-a-time via spot:takeover_active:{cluster_id}.

    Flow:
      T-0: Check active takeover guard — exit if one is already running.
      T-1: Query all legacy_mng nodes still running.
      T-2: If none left — transition onboarding_phase → managed.
      T-3: Filter safe nodes via _takeover_should_skip_node().
      T-4: Create RebalancingAction targeting od-general.
      T-5: Set takeover active guard.
    """
    from backend.models.instance import Instance
    from backend.models.cluster import Cluster
    from backend.models.rebalancing_action import RebalancingAction

    # T-0: One node at a time
    _takeover_active_key = f"spot:takeover_active:{cluster_id}"
    if redis and redis.exists(_takeover_active_key):
        logger.debug(f"[takeover] Cluster {cluster_id}: takeover already active — waiting")
        return

    # T-1: Find remaining MNG nodes
    mng_nodes = (
        db.query(Instance)
        .filter(
            Instance.cluster_id == cluster_id,
            Instance.node_owner_type == 'legacy_mng',
            Instance.state == 'running',
        )
        .all()
    )

    # T-2: All MNG nodes gone — advance to managed
    if not mng_nodes:
        try:
            db.query(Cluster).filter(Cluster.id == cluster_id).update(
                {"onboarding_phase": "managed"}
            )
            db.commit()
            if redis:
                redis.setex(
                    f"spot:takeover_completed_at:{cluster_id}",
                    604800,  # 7 days
                    str(int(datetime.utcnow().timestamp())),
                )
            logger.info(
                f"[takeover] Cluster {cluster_id}: all MNG nodes migrated → onboarding_phase=managed"
            )
        except Exception as _adv_exc:
            logger.error(f"[takeover] Phase advance failed cluster={cluster_id}: {_adv_exc}")
        return

    # T-3: Skip anchor/singleton nodes
    _safe_nodes = []
    for _cand in mng_nodes:
        _skip_reason = _takeover_should_skip_node(_cand, cluster_id, redis, db)
        if _skip_reason:
            logger.warning(
                f"[takeover] Skipping node {_cand.node_name} cluster={cluster_id}: {_skip_reason}"
            )
        else:
            _safe_nodes.append(_cand)

    if not _safe_nodes:
        logger.warning(
            f"[takeover] Cluster {cluster_id}: all {len(mng_nodes)} MNG nodes are anchor-blocked. "
            f"Manual intervention required. Nodes: {[n.node_name for n in mng_nodes]}"
        )
        return

    # T-4: Pick node with the fewest pods (least disruptive first)
    target_node = _safe_nodes[0]

    # T-5: Create RebalancingAction targeting od-general
    try:
        action = RebalancingAction(
            cluster_id=cluster_id,
            trigger="takeover",
            source_pool=f"{target_node.instance_id}:{getattr(target_node, 'az', 'unknown')}",
            target_pool="od-general",
            status="in_progress",
            migration_type="mng_takeover",
            source="auto_rebalancer",
            started_at=datetime.utcnow(),
            action_metadata={
                "trigger": "mng_takeover",
                "target_node_name": target_node.node_name,
                "mng_node": True,
                "instance_id": target_node.instance_id,
                "target_nodepool_name": "od-general",
            },
        )
        db.add(action)
        db.commit()

        if redis:
            redis.setex(_takeover_active_key, 2700, str(action.id))

        logger.info(
            f"[takeover] Cluster {cluster_id}: queued takeover for node "
            f"{target_node.node_name} ({target_node.instance_id}) → od-general. "
            f"Remaining MNG nodes: {len(mng_nodes)}"
        )
    except Exception as _act_exc:
        logger.error(f"[takeover] Failed to create RebalancingAction cluster={cluster_id}: {_act_exc}")


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


@app.task(name='workers.rebalancer_reconciliation')
def reconcile_stuck_actions():
    """Fix 16: Periodic reconciliation task (runs every 5 min via Celery beat).

    Detects and resolves actions stuck in intermediate states:
    - waiting_for_spot_node > 35 min with no spot detected → fail
    - cordoning_node/draining_pods > 25 min with no agent heartbeat → fail
    - Actions where source EC2 is already terminated → auto-complete
    """
    db = next(get_db())
    try:
        from backend.core.redis_client import get_redis_client as _grc_rec
        _redis = _grc_rec()

        # Find actions in intermediate states that might be stuck
        _stuck_cutoff = datetime.utcnow() - timedelta(minutes=35)
        _stuck_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
            RebalancingAction.started_at < _stuck_cutoff,
        ).all()

        _resolved = 0
        for _action in _stuck_actions:
            _meta = dict(_action.action_metadata or {})
            _inst_id = _meta.get('instance_id', '') or (_action.source_instance_id or '')
            _cur_step = _meta.get('current_step', '')

            # Check if source EC2 is already terminated in DB
            if _inst_id:
                _src = db.query(Instance).filter(
                    Instance.instance_id == _inst_id
                ).first()
                if _src and _src.state == 'terminated':
                    logger.info(
                        f"[reconciliation] Action {_action.id}: source {_inst_id[:12]} "
                        f"already terminated in DB — auto-completing"
                    )
                    _action.status = 'completed'
                    _action.completed_at = datetime.utcnow()
                    _action.duration_seconds = int(
                        (_action.completed_at - _action.started_at).total_seconds()
                    ) if _action.started_at else 0
                    _meta['current_step'] = 'completed'
                    _meta['reconciliation_auto_completed'] = True
                    _action.action_metadata = _meta
                    # Clean up resources
                    try:
                        _cleanup_rebalancing_resources(_action, _meta, _redis, db)
                    except Exception:
                        pass
                    _resolved += 1
                    continue

            # Clear stale locks for truly stuck actions (>45 min)
            _elapsed_min = int(
                (datetime.utcnow() - _action.started_at).total_seconds() / 60
            ) if _action.started_at else 0
            if _elapsed_min > 45 and _inst_id and _redis:
                try:
                    _redis.delete(f"spot:node_active_action:{_inst_id}")
                    logger.info(
                        f"[reconciliation] Cleared stale node_active_action lock "
                        f"for {_inst_id[:12]} (action {_action.id}, stuck {_elapsed_min}min)"
                    )
                except Exception:
                    pass

        if _resolved:
            db.commit()
            logger.info(f"[reconciliation] Resolved {_resolved} stuck action(s)")

        # ── ORPHAN TRIGGER POD SWEEP ──────────────────────────────────────
        # Find failed/completed/deferred actions whose trigger pods were never
        # cleaned up (e.g. because AGENT_WENT_OFFLINE path skipped cleanup).
        # Uses action ID naming convention: trigger pod = spot-trigger-{action_id}.
        try:
            _orphan_cutoff = datetime.utcnow() - timedelta(minutes=10)
            _terminal_with_pods = db.query(RebalancingAction).filter(
                RebalancingAction.status.in_(['failed', 'completed', 'deferred']),
                RebalancingAction.started_at >= datetime.utcnow() - timedelta(hours=24),
            ).all()
            _cleaned_pods = 0
            for _oa in _terminal_with_pods:
                _oa_meta = dict(_oa.action_metadata or {})
                _pod_name = _oa_meta.get('trigger_pod_name') or f"spot-trigger-{_oa.id}"
                try:
                    from backend.services.karpenter_service import KarpenterService as _KS_SWEEP
                    _ks_sweep = _KS_SWEEP(db, _redis)
                    _deleted = _ks_sweep.delete_spot_trigger_pod(
                        cluster_id=_oa.cluster_id, pod_name=_pod_name
                    )
                    if _deleted:
                        _cleaned_pods += 1
                except Exception:
                    pass
            if _cleaned_pods:
                logger.info(
                    f"[reconciliation] Cleaned up {_cleaned_pods} orphan trigger pod(s)"
                )
        except Exception as _sweep_pod_err:
            logger.debug(f"[reconciliation] Trigger pod sweep failed: {_sweep_pod_err}")
    except Exception as e:
        logger.warning(f"[reconciliation] Reconciliation task failed: {e}")
    finally:
        db.close()

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
        # ── MANIFEST-DRIVEN EXECUTION PATH (ExecutionEngine) ─────────────────
        # For each cluster that has a READY manifest written by DistributionEngine,
        # hand off to ExecutionEngine. EE handles all 10 layers (gate, race, provision,
        # stateful, stateless, drain, verify). The legacy path below runs only for
        # clusters NOT handled by EE this cycle (no manifest or manifest expired).
        _ee_clusters_handled: set = set()
        try:
            from backend.pipeline.stage5_execution.engine import ExecutionEngine, ManifestStore
            from backend.models.cluster import Cluster as _EECluster
            _ee_active_clusters = db.query(_EECluster).filter(_EECluster.status == "active").all()
            for _ee_cluster in _ee_active_clusters:
                _cid = str(_ee_cluster.id)
                _manifest = ManifestStore.read(_cid)
                if _manifest and _manifest.get("status") == "READY":
                    try:
                        logger.info(f"[auto_rebalancer] Handing off cluster {_cid} to ExecutionEngine")
                        ExecutionEngine.run(_cid, _manifest, db)
                        _ee_clusters_handled.add(_cid)
                    except Exception as _ee_err:
                        logger.error(f"[auto_rebalancer] EE failed for cluster {_cid}: {_ee_err}")
        except ImportError:
            pass  # EE not yet deployed — fall through to legacy path for all clusters
        except Exception as _ee_outer_err:
            logger.error(f"[auto_rebalancer] EE outer loop failed: {_ee_outer_err}")

        # ── K-1 / K-2: KARPENTER NODEPOOL BOOTSTRAP ──────────────────────────
        # After Karpenter install completes, the first cycle must create the default
        # spot NodePool before any Phase 1 injection attempt. install_karpenter() sets
        # spot:karpenter_nodepool_bootstrap_needed:{cluster_id} (TTL 2h). We call
        # bootstrap_default_nodepool() which is idempotent — skips if pool already exists.
        if _redis:
            try:
                from backend.services.karpenter_service import KarpenterService as _KSBoot
                from backend.models.cluster import Cluster as _BootCluster
                _boot_clusters = db.query(_BootCluster).filter(_BootCluster.status == "active").all()
                for _boot_c in _boot_clusters:
                    _boot_flag = f"spot:karpenter_nodepool_bootstrap_needed:{_boot_c.id}"
                    if _redis.exists(_boot_flag):
                        try:
                            _ks_boot = _KSBoot(db, _redis)
                            _boot_result = _ks_boot.bootstrap_default_nodepool(str(_boot_c.id))
                            logger.info(
                                f"[auto_rebalancer] K-1 bootstrap cluster={_boot_c.id} result={_boot_result}"
                            )
                        except Exception as _boot_err:
                            logger.warning(
                                f"[auto_rebalancer] K-1 bootstrap failed cluster={_boot_c.id}: {_boot_err}"
                            )
            except Exception as _boot_outer_err:
                logger.error(f"[auto_rebalancer] K-1 bootstrap loop failed: {_boot_outer_err}")

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
            # K-6 fix: Restore NodePool consolidateAfter if action timed out mid-Phase-1.
            # add_allowed_instance_type() sets consolidateAfter=Never during migration and
            # saves the original value. On timeout the cleanup path may not have run.
            _stale_nodepool = _stale_meta.get('patched_nodepool_name') or _stale_meta.get('target_nodepool_name')
            _stale_cluster_id = _stale.cluster_id
            if _stale_nodepool and _stale_cluster_id:
                try:
                    from backend.services.karpenter_service import KarpenterService as _KSStale
                    _ks_stale = _KSStale(db, _redis)
                    _baseline_key = f"karpenter:nodepool_consolidate_after_baseline:{_stale_cluster_id}:{_stale_nodepool}"
                    _orig_after = None
                    if _redis:
                        _raw_orig = _redis.get(_baseline_key)
                        _orig_after = _raw_orig.decode() if _raw_orig else None
                    _ks_stale.remove_allowed_instance_type(
                        cluster_id=_stale_cluster_id,
                        instance_type=_stale_meta.get('target_instance_type', ''),
                        nodepool_name=_stale_nodepool,
                    )
                    logger.info(
                        f"[auto_rebalancer] K-6: restored consolidateAfter for NodePool "
                        f"'{_stale_nodepool}' cluster={_stale_cluster_id} orig={_orig_after}"
                    )
                except Exception as _k6_err:
                    logger.warning(
                        f"[auto_rebalancer] K-6: failed to restore consolidateAfter for "
                        f"NodePool '{_stale_nodepool}': {_k6_err}"
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
        from backend.models.agent_action import AgentAction as _AA0, AgentActionStatus as _AAS0, AgentActionType as _AAT0

        # ── Stale-resource sweeper ──────────────────────────────────────────
        # Safety net: Find actions that reached a terminal state (failed/completed/
        # deferred) but still have spot:node_active_action locks in Redis.
        # This catches leaks from OOM kills, signal-9, or code paths added later
        # that forget to call _cleanup_rebalancing_resources().
        try:
            _terminal_recent = db.query(RebalancingAction).filter(
                RebalancingAction.status.in_(['failed', 'deferred']),
                RebalancingAction.completed_at >= (datetime.utcnow() - timedelta(hours=24)),
            ).all()
            for _tr in _terminal_recent:
                _tr_inst = _tr.source_instance_id or ((_tr.action_metadata or {}).get("instance_id", ""))
                if _tr_inst and _redis:
                    _tr_lock = _redis.get(f"spot:node_active_action:{_tr_inst}")
                    if _tr_lock:
                        _redis.delete(f"spot:node_active_action:{_tr_inst}")
                        logger.info(
                            f"[sweeper] Cleared stale node_active_action lock for "
                            f"{_tr_inst} (action {_tr.id} is {_tr.status})"
                        )
        except Exception as _sweep_err:
            logger.debug(f"[sweeper] Stale lock sweep failed: {_sweep_err}")

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
                    _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                    _AA0.status.in_([_AAS0.PENDING, _AAS0.PICKED_UP])
                ).count()
                if _still_pending > 0:
                    # ── STEP TRACKING: record step timestamps while agent is still working ──
                    _wa_meta_live = dict(_wa.action_metadata or {})
                    from backend.models.agent_action import AgentActionType as _AAT0
                    # step_1 (Karpenter NodePool update) is done directly in Phase 1,
                    # not via agent action — timestamp stored in action_metadata.
                    # Verification: add_allowed_instance_type now does read-back check.
                    if 'karpenter_nodepool_updated' in _wa_meta_live and 'step_1_spot_provisioning' not in _wa_meta_live:
                        _wa_meta_live['step_1_spot_provisioning'] = _wa_meta_live.get('phase1_completed_at', _wa.started_at.isoformat() if _wa.started_at else datetime.utcnow().isoformat())
                    for _sname, _stype in [
                        ('step_2_cordon', _AAT0.CORDON_NODE),
                        ('step_3_draining_pods', _AAT0.DRAIN_NODE),
                    ]:
                        if _sname not in _wa_meta_live:
                            _sa = db.query(_AA0).filter(
                                _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                                _AA0.action_type == _stype,
                                _AA0.status == _AAS0.COMPLETED,
                            ).first()
                            if _sa and _sa.completed_at:
                                # Only set step timestamp if agent verified the action
                                _sa_result = _sa.result or {}
                                _sa_verified = _sa_result.get('verified', False)
                                if _sa_verified:
                                    _wa_meta_live[_sname] = _sa.completed_at.isoformat()
                                    _wa_meta_live[f'{_sname}_verified'] = True
                                else:
                                    # Agent completed but didn't verify — still mark but flag
                                    _wa_meta_live[_sname] = _sa.completed_at.isoformat()
                                    _wa_meta_live[f'{_sname}_verified'] = False
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: {_sname} completed "
                                        f"but agent verification={_sa_verified} (result={_sa_result})"
                                    )
                    # Determine current_step from what's done so far
                    if 'step_3_draining_pods' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'waiting_for_spot_node'
                        # ── Step journal: drain done, terminate in flight ──────
                        if _wa.action_step not in (ACTION_STEP_TERMINATING, ACTION_STEP_CLEANUP, ACTION_STEP_DONE):
                            _advance_action_step(db, _wa, ACTION_STEP_TERMINATING)
                    elif 'step_2_cordon' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'draining_pods'
                    elif 'step_1_spot_provisioning' in _wa_meta_live:
                        _wa_meta_live['current_step'] = 'cordoning_node'
                    else:
                        _wa_meta_live['current_step'] = 'provisioning_spot_pool'
                    _wa.action_metadata = _wa_meta_live
                    db.commit()

                    # ── BACKEND-SIDE CORDON/DRAIN BYPASS ──────────────────────
                    # Safety-net fallback: if inline CORDON+DRAIN at Phase 2
                    # creation failed and the agent hasn't picked up after 15s,
                    # execute directly from backend K8s API.
                    _AGENT_TIMEOUT_S = 15
                    _pending_cordon = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status == _AAS0.PENDING,
                    ).first()
                    _pending_drain = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status == _AAS0.PENDING,
                    ).first()
                    # Use the CORDON action's created_at as the reference timestamp
                    _oldest_pending = _pending_cordon or _pending_drain
                    _p2_elapsed = 0
                    if _oldest_pending and _oldest_pending.created_at:
                        _p2_elapsed = (datetime.utcnow() - _oldest_pending.created_at).total_seconds()
                    if _p2_elapsed >= _AGENT_TIMEOUT_S and (_pending_cordon or _pending_drain):
                                logger.warning(
                                    f"[auto_rebalancer] Action {_wa.id}: Agent actions PENDING "
                                    f"for {int(_p2_elapsed)}s — executing cordon/drain directly "
                                    f"from backend via K8s API"
                                )
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_CD
                                    from kubernetes import client as _k8s_cd
                                    _ks_cd = _KS_CD(db, _redis)
                                    _wa_cluster_cd = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                                    if _wa_cluster_cd:
                                        _k8s_api_cd = _ks_cd._get_k8s_client(_wa_cluster_cd)
                                        _core_cd = _k8s_cd.CoreV1Api(_k8s_api_cd)

                                        _cd_node_name = None
                                        if _pending_cordon:
                                            _cd_node_name = (_pending_cordon.payload or {}).get('node_name')
                                        elif _pending_drain:
                                            _cd_node_name = (_pending_drain.payload or {}).get('node_name')

                                        if _cd_node_name:
                                            # ── CORDON: mark node unschedulable ──
                                            if _pending_cordon:
                                                try:
                                                    _core_cd.patch_node(_cd_node_name, {"spec": {"unschedulable": True}})
                                                    _pending_cordon.status = _AAS0.COMPLETED
                                                    _pending_cordon.completed_at = datetime.utcnow()
                                                    _pending_cordon.result = {"backend_executed": True, "verified": True}
                                                    db.flush()
                                                    logger.info(
                                                        f"[auto_rebalancer] Action {_wa.id}: Backend cordon "
                                                        f"of {_cd_node_name} succeeded"
                                                    )
                                                except Exception as _cordon_err:
                                                    logger.error(
                                                        f"[auto_rebalancer] Action {_wa.id}: Backend cordon "
                                                        f"failed for {_cd_node_name}: {_cordon_err}"
                                                    )
                                                    _pending_cordon.status = _AAS0.FAILED
                                                    _pending_cordon.error_message = str(_cordon_err)
                                                    db.flush()

                                            # ── DRAIN: evict non-DaemonSet pods ──
                                            if _pending_drain and (not _pending_cordon or _pending_cordon.status == _AAS0.COMPLETED):
                                                try:
                                                    _drain_force = (_pending_drain.payload or {}).get('force', True)
                                                    _drain_grace = (_pending_drain.payload or {}).get('grace_period_seconds', 60)
                                                    _drain_ignore_ds = (_pending_drain.payload or {}).get('ignore_daemonsets', True)

                                                    _pods_on_node = _core_cd.list_namespaced_pod(
                                                        namespace="",
                                                        field_selector=f"spec.nodeName={_cd_node_name}"
                                                    ).items
                                                    # Filter: skip DaemonSet pods and mirror pods
                                                    _evictable = []
                                                    for _pod in _pods_on_node:
                                                        _owner_refs = _pod.metadata.owner_references or []
                                                        _is_ds = any(o.kind == 'DaemonSet' for o in _owner_refs)
                                                        _is_mirror = bool((_pod.metadata.annotations or {}).get('kubernetes.io/config.mirror'))
                                                        if _drain_ignore_ds and _is_ds:
                                                            continue
                                                        if _is_mirror:
                                                            continue
                                                        _evictable.append(_pod)

                                                    logger.info(
                                                        f"[auto_rebalancer] Action {_wa.id}: Backend drain — "
                                                        f"evicting {len(_evictable)} pods from {_cd_node_name}"
                                                    )
                                                    _evict_errors = []
                                                    for _epod in _evictable:
                                                        try:
                                                            _eviction = _k8s_cd.V1Eviction(
                                                                metadata=_k8s_cd.V1ObjectMeta(
                                                                    name=_epod.metadata.name,
                                                                    namespace=_epod.metadata.namespace,
                                                                ),
                                                                delete_options=_k8s_cd.V1DeleteOptions(
                                                                    grace_period_seconds=_drain_grace,
                                                                ),
                                                            )
                                                            _core_cd.create_namespaced_pod_eviction(
                                                                name=_epod.metadata.name,
                                                                namespace=_epod.metadata.namespace,
                                                                body=_eviction,
                                                            )
                                                        except _k8s_cd.ApiException as _evict_exc:
                                                            if _evict_exc.status == 404:
                                                                pass  # Pod already gone
                                                            elif _evict_exc.status == 429 and not _drain_force:
                                                                _evict_errors.append(f"{_epod.metadata.namespace}/{_epod.metadata.name}: PDB blocked")
                                                            else:
                                                                _evict_errors.append(f"{_epod.metadata.namespace}/{_epod.metadata.name}: {_evict_exc.reason}")
                                                        except Exception as _evict_gen:
                                                            _evict_errors.append(f"{_epod.metadata.namespace}/{_epod.metadata.name}: {_evict_gen}")

                                                    if _evict_errors and not _drain_force:
                                                        _pending_drain.status = _AAS0.FAILED
                                                        _pending_drain.error_message = f"PDB/eviction blocked: {_evict_errors[:5]}"
                                                    else:
                                                        _pending_drain.status = _AAS0.COMPLETED
                                                        _pending_drain.completed_at = datetime.utcnow()
                                                        _pending_drain.result = {
                                                            "backend_executed": True,
                                                            "verified": True,
                                                            "pods_evicted": len(_evictable),
                                                            "evict_errors": _evict_errors[:5] if _evict_errors else [],
                                                        }
                                                    db.flush()
                                                    logger.info(
                                                        f"[auto_rebalancer] Action {_wa.id}: Backend drain "
                                                        f"of {_cd_node_name} done — {len(_evictable)} pods evicted, "
                                                        f"{len(_evict_errors)} errors"
                                                    )
                                                except Exception as _drain_err:
                                                    logger.error(
                                                        f"[auto_rebalancer] Action {_wa.id}: Backend drain "
                                                        f"failed for {_cd_node_name}: {_drain_err}"
                                                    )
                                                    _pending_drain.status = _AAS0.FAILED
                                                    _pending_drain.error_message = str(_drain_err)
                                                    db.flush()

                                            # Also mark TERMINATE_NODE as COMPLETED — backend
                                            # handles termination directly via AWS API below
                                            _pending_term = db.query(_AA0).filter(
                                                _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                                                _AA0.action_type == _AAT0.TERMINATE_NODE,
                                                _AA0.status == _AAS0.PENDING,
                                            ).first()
                                            if _pending_term:
                                                _pending_term.status = _AAS0.COMPLETED
                                                _pending_term.completed_at = datetime.utcnow()
                                                _pending_term.result = {"backend_will_terminate": True}
                                                db.flush()

                                            db.commit()
                                            # Don't continue — fall through to let the
                                            # readiness + AWS terminate logic execute
                                        else:
                                            logger.warning(
                                                f"[auto_rebalancer] Action {_wa.id}: No node_name in "
                                                f"CORDON/DRAIN payload — cannot execute backend-side"
                                            )
                                            continue
                                    else:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: Cluster not found "
                                            f"for backend-side cordon/drain"
                                        )
                                        continue
                                except Exception as _cd_err:
                                    logger.error(
                                        f"[auto_rebalancer] Action {_wa.id}: Backend cordon/drain "
                                        f"error: {_cd_err}"
                                    )
                                    continue
                    else:
                        continue  # Agent still working or no PENDING actions — leave as waiting_agent

                _failed = db.query(_AA0).filter(
                    _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                    _AA0.status == _AAS0.FAILED,
                    _AA0.action_type != _AAT0.LABEL_NODE,  # LABEL_NODE (do-not-disrupt annotation) is non-critical; exclude from failure count
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
                            _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                            _AA0.action_type == _stype,
                        ).first()
                        if _sa:
                            ts = (_sa.completed_at or _sa.created_at)
                            if ts:
                                _sa_result = _sa.result or {}
                                _sa_verified = _sa_result.get('verified', False)
                                _wa_meta[_sname] = ts.isoformat()
                                _wa_meta[f'{_sname}_verified'] = _sa_verified
                                if not _sa_verified:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: {_sname} completed "
                                        f"but agent verification={_sa_verified}"
                                    )

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
                    _direct_launch = bool(_wa_meta.get('replacement_spot_instance_id')) and not _wa_karpenter_active

                    # Extract expected target instance type (Fix #4, must be before E9 arch
                    # check — _expected_instance_type is derived from _wa.target_pool).
                    _expected_instance_type = None
                    if _wa.target_pool and ':' in _wa.target_pool:
                        _expected_instance_type = _wa.target_pool.split(':')[0]
                    elif _wa.target_pool:
                        _expected_instance_type = _wa.target_pool

                    # Fix 1: After escalation, the trigger pod instance type changes
                    # but _expected_instance_type still points to the original target.
                    # Count-based detection then filters out the new spot node because
                    # its type doesn't match. Update _expected_instance_type to match
                    # the current trigger pod type (set by escalation logic).
                    _esc_trigger_type = _wa_meta.get('trigger_pod_instance_type')
                    if _esc_trigger_type and _esc_trigger_type != _expected_instance_type:
                        logger.debug(
                            f"[auto_rebalancer] Action {_wa.id}: Fix1 — updating "
                            f"_expected_instance_type from {_expected_instance_type} "
                            f"to {_esc_trigger_type} (escalation active)"
                        )
                        _expected_instance_type = _esc_trigger_type
                    # If broad escalation removed the type constraint, accept any spot type
                    if _wa_meta.get('esc_broad_done'):
                        _expected_instance_type = None

                    # ── Early compute _spot_wait_elapsed ──────────────────────
                    # Needed by Fix9 safety fallback (L3282) which runs inside the
                    # readiness gate block, BEFORE the main spot-wait section where
                    # it was originally defined.
                    _phase1_ts_early = _wa_meta.get('phase1_completed_at')
                    if _phase1_ts_early:
                        try:
                            _patch_completed_early = datetime.fromisoformat(_phase1_ts_early)
                        except (ValueError, TypeError):
                            _patch_completed_early = _wa.started_at
                    else:
                        _patch_completed_early = _wa.started_at
                    _spot_wait_elapsed = (
                        (datetime.utcnow() - _patch_completed_early).total_seconds()
                        if _patch_completed_early else 9999
                    )

                    # ── Enhancement 9: Standby fast-path ──────────────────────
                    # If a ready standby exists, find_ready_standby() now atomically
                    # claims it (Redis NX) and checks architecture inside the function.
                    # On success: pin the replacement ID in metadata and `continue` to
                    # skip the count-based detection.  The pinned-ID path handles Phase 2
                    # on the next Celery cycle (15 s later).
                    if not _wa_meta.get('standby_claimed') and not _wa_meta.get('replacement_spot_instance_id'):
                        try:
                            from backend.workers.tasks.standby import find_ready_standby
                            _standby = find_ready_standby(
                                db,
                                _wa.cluster_id,
                                redis_client=_redis,
                                source_instance_type=_expected_instance_type,
                                action_id=str(_wa.id),
                            )
                            if _standby and _standby.node_name and _standby.instance_id:
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: STANDBY FAST-PATH — "
                                    f"using pre-warmed standby {_standby.instance_id[:12]} "
                                    f"(node={_standby.node_name}, type={_standby.instance_type})"
                                )
                                # Uncordon the standby node so pods can schedule on it
                                try:
                                    if _wa_cluster_obj:
                                        from backend.services.karpenter_service import KarpenterService as _KS_SB
                                        _ks_sb = _KS_SB(db, _redis)
                                        _sb_api = _ks_sb._get_k8s_client(_wa_cluster_obj)
                                        from kubernetes import client as _k8s_sb_c
                                        _sb_v1 = _k8s_sb_c.CoreV1Api(_sb_api)
                                        _sb_v1.patch_node(_standby.node_name, {
                                            "spec": {"unschedulable": None}
                                        })
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: Uncordoned standby "
                                            f"node {_standby.node_name}"
                                        )
                                except Exception as _sb_uncordon_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Failed to uncordon "
                                        f"standby: {_sb_uncordon_err}"
                                    )

                                # Record the standby as this action's replacement.
                                # Set status=READY explicitly so the readiness gate in the
                                # count/pinned-ID detection below passes on this same cycle
                                # without needing a K8s live round-trip (standby was already
                                # running and cordoned — it IS Ready).
                                _standby.standby = False
                                _standby.status = 'READY'
                                _wa_meta['replacement_spot_instance_id'] = _standby.instance_id
                                _wa_meta['replacement_spot_node_name'] = _standby.node_name
                                _wa_meta['standby_claimed'] = True
                                _wa_meta['used_standby'] = True
                                _wa_meta['standby_claimed_at'] = datetime.utcnow().isoformat()
                                _wa.action_metadata = _wa_meta
                                _wa.actual_instance_type = _standby.instance_type
                                _wa.actual_az = getattr(_standby, 'az', None) or ''
                                db.commit()

                                # Trigger new standby provisioning to replace the one we used
                                try:
                                    from backend.workers.tasks.standby import launch_standby_node
                                    launch_standby_node.delay(_wa.cluster_id)
                                except Exception:
                                    pass

                                # Fall through to the count/pinned-ID detection below so Phase 2
                                # is created in THIS cycle (zero-lag).  replacement_spot_instance_id
                                # is already set in _wa_meta so the pinned-ID path picks it up and
                                # the readiness gate passes because we set status=READY above.
                        except Exception as _sb_err:
                            logger.debug(f"[auto_rebalancer] Standby check: {_sb_err}")

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
                    _SPOT_STABILIZE_S = 30
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
                                # Safety: if the instance is terminated/shutting-down, do NOT
                                # treat it as joined — another action's rollback may have killed it.
                                if _p12_inst.state in ('terminated', 'shutting-down', 'stopped'):
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: pinned replacement "
                                        f"{_replacement_id_pinned[:12]} has node_name={_p12_inst.node_name} "
                                        f"but state={_p12_inst.state} — NOT treating as joined"
                                    )
                                    # Clear stale pin so the rebalancer can look for a new
                                    # spot node or create a fresh trigger pod instead of
                                    # looping on a terminated instance forever.
                                    _wa_meta.pop('replacement_spot_instance_id', None)
                                    _wa_meta.pop('replacement_spot_node_name', None)
                                    _wa_meta['trigger_pod_created'] = False
                                    _wa_meta.pop('esc_alt1_done', None)
                                    _wa_meta.pop('esc_alt2_done', None)
                                    _wa_meta.pop('esc_broad_done', None)
                                    _wa_meta.pop('step_entered_waiting_for_spot_node', None)
                                    _wa.action_metadata = _wa_meta
                                    db.commit()
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: cleared stale pin "
                                        f"{_replacement_id_pinned[:12]} — will create fresh trigger pod"
                                    )
                                    # Do NOT set _p12_joined or _newest_spot
                                else:
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
                        logger.warning(
                            f"[auto_rebalancer] Action {_wa.id}: Phase 2 count-fallback "
                            f"(spot_count={_spot_count} > baseline={_spot_baseline}) — "
                            f"no replacement_spot_instance_id in metadata (Phase 1 may be old)"
                        )
                        # Fix #2: ID-set-diff detection — find spots NOT in baseline snapshot.
                        # More reliable than pure count comparison, especially when baseline=0.
                        _baseline_ids = set(_wa_meta.get('baseline_spot_instance_ids', []))
                        _count_fb_query = db.query(Instance).filter(
                            Instance.cluster_id == _wa.cluster_id,
                            Instance.lifecycle == InstanceLifecycle.SPOT,
                            Instance.state == 'running',
                        )
                        if _expected_instance_type:
                            _count_fb_query = _count_fb_query.filter(
                                Instance.instance_type == _expected_instance_type,
                            )
                        if _baseline_ids:
                            _count_fb_query = _count_fb_query.filter(
                                Instance.instance_id.notin_(_baseline_ids),
                            )
                        # Fix: Batch-parallel claim — find first UNCLAIMED spot among all
                        # candidates, not just .first().  When 3 actions run concurrently,
                        # each must pick a different replacement.
                        _count_fb_candidates = _count_fb_query.order_by(Instance.created_at.desc()).all()
                        _newest_spot = None
                        for _cfb_candidate in _count_fb_candidates:
                            _cfb_claim_key = f"spot:replacement_claimed:{_cfb_candidate.instance_id}"
                            if _redis and _redis.exists(_cfb_claim_key):
                                _cfb_owner = _redis.get(_cfb_claim_key)
                                _cfb_owner_str = _cfb_owner.decode() if isinstance(_cfb_owner, bytes) else str(_cfb_owner)
                                if _cfb_owner_str != str(_wa.id):
                                    logger.debug(
                                        f"[auto_rebalancer] Action {_wa.id}: skipping "
                                        f"{_cfb_candidate.instance_id[:12]} — already claimed "
                                        f"by action {_cfb_owner_str}"
                                    )
                                    continue
                            _newest_spot = _cfb_candidate
                            break
                        if _newest_spot:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: ID-set-diff found unclaimed spot "
                                f"{_newest_spot.instance_id[:12]} (type={_newest_spot.instance_type}) "
                                f"not in baseline set of {len(_baseline_ids)} IDs "
                                f"(checked {len(_count_fb_candidates)} candidates)"
                            )
                        elif not _newest_spot and _expected_instance_type:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: count-fallback found no "
                                f"{_expected_instance_type} spot — ignoring non-matching spot nodes"
                            )
                    elif _spot_count >= 1 and _spot_count <= _spot_baseline and _wa.started_at:
                        # Bug #12b: Count stagnation fallback — a new spot was provisioned
                        # but an old spot died simultaneously, so net count didn't increase.
                        # Detect by finding a spot created AFTER the action started.
                        _stag_fb_query = db.query(Instance).filter(
                            Instance.cluster_id == _wa.cluster_id,
                            Instance.lifecycle == InstanceLifecycle.SPOT,
                            Instance.state == 'running',
                            Instance.created_at > _wa.started_at,
                        )
                        # Fix #4: Also filter by expected type in stagnation fallback
                        if _expected_instance_type:
                            _stag_fb_query = _stag_fb_query.filter(
                                Instance.instance_type == _expected_instance_type,
                            )
                        _post_action_spot = None
                        _stag_candidates = _stag_fb_query.order_by(Instance.created_at.desc()).all()
                        for _stag_cand in _stag_candidates:
                            _stag_claim_key = f"spot:replacement_claimed:{_stag_cand.instance_id}"
                            if _redis and _redis.exists(_stag_claim_key):
                                _stag_owner = _redis.get(_stag_claim_key)
                                _stag_owner_str = _stag_owner.decode() if isinstance(_stag_owner, bytes) else str(_stag_owner)
                                if _stag_owner_str != str(_wa.id):
                                    continue
                            _post_action_spot = _stag_cand
                            break
                        if _post_action_spot:
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: time-based fallback — "
                                f"spot {_post_action_spot.instance_id[:12]} created after action start "
                                f"(type={_post_action_spot.instance_type}, "
                                f"count={_spot_count} <= baseline={_spot_baseline} due to churn)"
                            )
                            _newest_spot = _post_action_spot

                    if _newest_spot:
                        # Fix #4: Instance type validation — reject nodes whose instance_type
                        # doesn't match the action's target.  This prevents accepting a
                        # random Karpenter-provisioned node (e.g. c5a.large from normal
                        # workload scaling) as the rebalancing replacement for c7g.medium.
                        # Only applies to unpinned paths (count/time fallbacks); the pinned
                        # path already resolves by exact instance ID.
                        if (
                            _expected_instance_type
                            and not _replacement_id_pinned
                            and _newest_spot.instance_type
                            and _newest_spot.instance_type != _expected_instance_type
                        ):
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: candidate spot "
                                f"{_newest_spot.instance_id[:12]} is {_newest_spot.instance_type} "
                                f"but action targets {_expected_instance_type} — ignoring "
                                f"(likely a normal scaling event, not our replacement)"
                            )
                            _newest_spot = None

                    # ── Enhancement 1: K8s direct node detection (bypass aws_sync) ──
                    # If DB-based detection found nothing, query K8s API directly.
                    # aws_sync runs every 5 min — this live query saves up to 300s.
                    if not _newest_spot and not _replacement_id_pinned and _wa_karpenter_active:
                        try:
                            _k8s_detect_cluster = _wa_cluster_obj
                            if _k8s_detect_cluster:
                                from backend.services.karpenter_service import KarpenterService as _KS_DETECT
                                _ks_detect = _KS_DETECT(db, _redis)
                                _k8s_detect_api = _ks_detect._get_k8s_client(_k8s_detect_cluster)
                                from kubernetes import client as _k8s_detect_c
                                _core_detect = _k8s_detect_c.CoreV1Api(_k8s_detect_api)

                                # Determine target AZ
                                _detect_az = ''
                                if _wa.target_pool and ':' in _wa.target_pool:
                                    _detect_az = _wa.target_pool.split(':')[1]

                                # Phase 1 completion time for filtering
                                _detect_p1_ts = _wa_meta.get('phase1_completed_at')
                                _detect_p1_dt = None
                                if _detect_p1_ts:
                                    try:
                                        _detect_p1_dt = datetime.fromisoformat(_detect_p1_ts)
                                    except (ValueError, TypeError):
                                        pass

                                # Query K8s nodes filtered by labels
                                _k8s_nodes = _core_detect.list_node().items
                                for _k8s_node in _k8s_nodes:
                                    _k8s_labels = _k8s_node.metadata.labels or {}
                                    _k8s_node_type = _k8s_labels.get('node.kubernetes.io/instance-type', '')
                                    _k8s_node_az = _k8s_labels.get('topology.kubernetes.io/zone', '')
                                    _k8s_cap_type = _k8s_labels.get('karpenter.sh/capacity-type', '')
                                    _k8s_created = _k8s_node.metadata.creation_timestamp

                                    # Filter: must be spot, correct type, correct AZ (if known),
                                    # created after Phase 1
                                    if _k8s_cap_type != 'spot':
                                        continue
                                    if _expected_instance_type and _k8s_node_type != _expected_instance_type:
                                        # Also accept the current escalation target type
                                        _esc_trig_type = _wa_meta.get('trigger_pod_instance_type', '')
                                        if _esc_trig_type and _k8s_node_type != _esc_trig_type:
                                            continue
                                        elif not _esc_trig_type:
                                            continue
                                    if _detect_az and _k8s_node_az != _detect_az:
                                        continue
                                    if _detect_p1_dt and _k8s_created:
                                        # Strip timezone from K8s timestamp to match
                                        # naive _detect_p1_dt (both are UTC)
                                        _k8s_ts = _k8s_created.replace(tzinfo=None) if hasattr(_k8s_created, 'tzinfo') and _k8s_created.tzinfo else _k8s_created
                                        if _k8s_ts < _detect_p1_dt:
                                            continue

                                    # Check Ready condition
                                    _k8s_ready = False
                                    for _cond in (_k8s_node.status.conditions or []):
                                        if _cond.type == 'Ready' and _cond.status == 'True':
                                            _k8s_ready = True
                                            break
                                    if not _k8s_ready:
                                        continue

                                    # Skip nodes already labelled as existing
                                    if _k8s_labels.get('spot-optimizer.io/existing-node') == 'true':
                                        continue

                                    _k8s_node_name = _k8s_node.metadata.name
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: K8s DIRECT detection — "
                                        f"node {_k8s_node_name} ({_k8s_node_type}, {_k8s_node_az}) "
                                        f"is Ready, bypassing aws_sync wait"
                                    )

                                    # Try to find or create matching Instance in DB
                                    # Look up by node_name first (agent collector may have it)
                                    _k8s_inst = db.query(Instance).filter(
                                        Instance.cluster_id == _wa.cluster_id,
                                        Instance.node_name == _k8s_node_name,
                                        Instance.state == 'running',
                                    ).first()
                                    if not _k8s_inst:
                                        # Also try by provider ID label
                                        _provider_id = (_k8s_node.spec.provider_id or '') if _k8s_node.spec else ''
                                        _ec2_id = ''
                                        if _provider_id and '/' in _provider_id:
                                            _ec2_id = _provider_id.rsplit('/', 1)[-1]
                                        if _ec2_id:
                                            _k8s_inst = db.query(Instance).filter(
                                                Instance.instance_id == _ec2_id,
                                            ).first()
                                    if _k8s_inst:
                                        # Claim-aware check: skip spots already claimed by other actions
                                        _k8s_claim_key = f"spot:replacement_claimed:{_k8s_inst.instance_id}"
                                        if _redis and _redis.exists(_k8s_claim_key):
                                            _k8s_owner = _redis.get(_k8s_claim_key)
                                            _k8s_owner_str = _k8s_owner.decode() if isinstance(_k8s_owner, bytes) else str(_k8s_owner)
                                            if _k8s_owner_str != str(_wa.id):
                                                logger.info(
                                                    f"[auto_rebalancer] Action {_wa.id}: K8s detected "
                                                    f"{_k8s_node_name} ({_k8s_inst.instance_id[:12]}) "
                                                    f"already claimed by action {_k8s_owner_str} — skipping"
                                                )
                                                continue  # Try next K8s node
                                        _newest_spot = _k8s_inst
                                        # Ensure it has node_name set
                                        if not _k8s_inst.node_name:
                                            _k8s_inst.node_name = _k8s_node_name
                                        # Override status to allow stabilization gate
                                        if _k8s_inst.status not in ('READY', 'CALIBRATING'):
                                            _k8s_inst.status = 'READY'
                                        db.commit()
                                        break  # Found an unclaimed matching node
                                    else:
                                        # aws_sync hasn't created the record yet.
                                        # Don't create one — just record in metadata so
                                        # the next cycle can match via node_name.
                                        _wa_meta['k8s_detected_node'] = _k8s_node_name
                                        _wa_meta['k8s_detected_type'] = _k8s_node_type
                                        _wa_meta['k8s_detected_az'] = _k8s_node_az
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: K8s detected "
                                            f"{_k8s_node_name} but no DB record yet — "
                                            f"waiting for aws_sync or collector"
                                        )
                                        break  # No DB record yet, wait for next cycle
                        except Exception as _k8s_detect_err:
                            logger.debug(
                                f"[auto_rebalancer] Action {_wa.id}: K8s direct detection failed: "
                                f"{_k8s_detect_err}"
                            )

                    if _newest_spot:
                        _spot_age_s = (
                            (datetime.utcnow() - _newest_spot.created_at).total_seconds()
                            if _newest_spot.created_at else 0
                        )
                        # Enhancement 4: Readiness gate — replaces flat 30s timer.
                        # Proceed to Phase 2 when ALL conditions met:
                        # 1. node_name is set (kubelet joined K8s)
                        # 2. At least 10s elapsed since node appeared (hard floor)
                        # 3. Node status = READY or CALIBRATING (collector confirmed)
                        # 4. For K8s-detected nodes, also verify DaemonSets are running
                        _SPOT_STABILIZE_FLOOR_S = 10  # Hard minimum, non-negotiable
                        if _spot_age_s >= _SPOT_STABILIZE_FLOOR_S and _newest_spot.node_name:
                            _repl_status = getattr(_newest_spot, 'status', None) or ''
                            if _repl_status not in ('READY', 'CALIBRATING'):
                                # Try live K8s check if collector hasn't confirmed yet
                                _k8s_ready_live = False
                                try:
                                    if _wa_cluster_obj:
                                        from backend.services.karpenter_service import KarpenterService as _KS_READY
                                        _ks_ready = _KS_READY(db, _redis)
                                        _ready_api = _ks_ready._get_k8s_client(_wa_cluster_obj)
                                        from kubernetes import client as _k8s_ready_c
                                        _ready_v1 = _k8s_ready_c.CoreV1Api(_ready_api)
                                        _ready_node = _ready_v1.read_node(_newest_spot.node_name)
                                        for _cond in (_ready_node.status.conditions or []):
                                            if _cond.type == 'Ready' and _cond.status == 'True':
                                                _k8s_ready_live = True
                                                break
                                        if _k8s_ready_live:
                                            # Update DB status so next cycle doesn't re-check
                                            _newest_spot.status = 'READY'
                                            db.commit()
                                            _repl_status = 'READY'
                                except Exception:
                                    pass

                            if _repl_status not in ('READY', 'CALIBRATING'):
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: replacement "
                                    f"{_newest_spot.instance_id[:12]} node_name={_newest_spot.node_name} "
                                    f"status={_repl_status or 'UNKNOWN'} — waiting for K8s Ready condition"
                                )
                            else:
                                _new_spot_joined = True
                                # Pin replacement ID for rollback reliability
                                if _newest_spot.instance_id and not _wa_meta.get('replacement_spot_instance_id'):
                                    _wa_meta['replacement_spot_instance_id'] = _newest_spot.instance_id
                                    _wa.action_metadata = _wa_meta
                                    flag_modified(_wa, 'action_metadata')
                                # Pin node_name so it survives loop iterations
                                if _newest_spot.node_name and not _wa_meta.get('replacement_spot_node_name'):
                                    _wa_meta['replacement_spot_node_name'] = _newest_spot.node_name
                                    _wa.action_metadata = _wa_meta
                                    flag_modified(_wa, 'action_metadata')
                                # Populate actual_instance_type/az on the rebalancing_action row
                                if _newest_spot.instance_type and not _wa.actual_instance_type:
                                    _wa.actual_instance_type = _newest_spot.instance_type
                                    _wa.actual_az = getattr(_newest_spot, 'az', None) or ''

                                # Fix 3: Architecture validation — ensure replacement spot
                                # matches the source OD node architecture (arm64 vs amd64).
                                # Detect from K8s label 'kubernetes.io/arch' if available,
                                # otherwise from instance type family naming convention.
                                _src_arch = _wa_meta.get('source_architecture', '')
                                _repl_arch = getattr(_newest_spot, 'architecture', '') or ''
                                if _src_arch and _repl_arch and _src_arch != _repl_arch:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Fix3 ARCH MISMATCH — "
                                        f"source={_src_arch}, replacement={_repl_arch} "
                                        f"({_newest_spot.instance_type}). Replacement may fail "
                                        f"to schedule pods built for {_src_arch}. Proceeding anyway "
                                        f"(operator should verify workload compatibility)."
                                    )
                                    _wa_meta['arch_mismatch_warning'] = (
                                        f"source={_src_arch}, replacement={_repl_arch}"
                                    )
                        elif _spot_age_s >= _SPOT_STABILIZE_FLOOR_S and not _newest_spot.node_name:
                            logger.debug(
                                f"[auto_rebalancer] Action {_wa.id}: new spot EC2 up "
                                f"{int(_spot_age_s)}s but node_name not set yet (kubelet not joined k8s) — waiting"
                            )
                        else:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: new spot appeared but "
                                f"only {int(_spot_age_s)}s old (need {_SPOT_STABILIZE_FLOOR_S}s) — "
                                f"waiting for readiness gate"
                            )

                    # Fix 9: Safety fallback — if _newest_spot exists, is READY,
                    # has a node_name, and the spot wait has been going for >60s,
                    # force _new_spot_joined = True.  This catches edge cases where
                    # the readiness gate's status check failed due to stale DB status
                    # but K8s live check wasn't attempted (e.g., K8s API unavailable
                    # on that cycle).  The 60s floor prevents premature triggers.
                    # FIX: Always verify node ACTUALLY exists in K8s before proceeding.
                    # DB node_name can be set (from EC2 private DNS) before the kubelet
                    # has registered the node in the K8s API server → 404 on LABEL_NODE.
                    if (
                        not _new_spot_joined
                        and _newest_spot
                        and _newest_spot.node_name
                        and _newest_spot.status in ('READY', 'CALIBRATING')
                        and _spot_wait_elapsed > 60
                    ):
                        # Verify node is LIVE in K8s before proceeding
                        _fix9_node_live = False
                        try:
                            if _wa_cluster_obj:
                                from backend.services.karpenter_service import KarpenterService as _KS_F9
                                _ks_f9 = _KS_F9(db, _redis)
                                _f9_api = _ks_f9._get_k8s_client(_wa_cluster_obj)
                                from kubernetes import client as _k8s_f9
                                _f9_v1 = _k8s_f9.CoreV1Api(_f9_api)
                                _f9_v1.read_node(_newest_spot.node_name)
                                _fix9_node_live = True
                        except Exception as _f9_err:
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Fix9 — node "
                                f"{_newest_spot.node_name} NOT in K8s yet ({_f9_err}), "
                                f"deferring _new_spot_joined"
                            )

                        if _fix9_node_live:
                            _new_spot_joined = True
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Fix9 safety fallback — "
                                f"_newest_spot {_newest_spot.instance_id[:12]} is "
                                f"{_newest_spot.status} with node_name={_newest_spot.node_name} "
                                f"and wait={int(_spot_wait_elapsed)}s > 60s — forcing _new_spot_joined=True"
                            )
                            # Pin replacement ID
                            if _newest_spot.instance_id and not _wa_meta.get('replacement_spot_instance_id'):
                                _wa_meta['replacement_spot_instance_id'] = _newest_spot.instance_id
                                _wa.action_metadata = _wa_meta
                            if _newest_spot.node_name and not _wa_meta.get('replacement_spot_node_name'):
                                _wa_meta['replacement_spot_node_name'] = _newest_spot.node_name
                                _wa.action_metadata = _wa_meta

                    # Check if Phase 2 actions exist yet.
                    # EXPIRED and FAILED actions don't count — they were never successfully
                    # executed. Fix 4: previously FAILED CORDON actions counted as "existing",
                    # preventing Phase 2 re-creation after a transient K8s API failure.
                    _phase2_any = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status.notin_([_AAS0.EXPIRED, _AAS0.FAILED]),
                    ).count() > 0
                    _phase2_active = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status.notin_([_AAS0.EXPIRED, _AAS0.FAILED]),
                    ).count() > 0

                    # ── FAST-RECOVERY: Phase 2 expired while agent was down ──────────────
                    # If CORDON/DRAIN/TERMINATE all expired (agent pod restarted mid-action),
                    # check the source EC2 state in AWS:
                    #   • Already terminated → auto-complete (replacement succeeded in real world)
                    #   • Still running → delete expired actions and re-queue Phase 2 fresh
                    # Fix 4: Use a separate query that includes expired/failed to detect
                    # whether Phase 2 was EVER created (even if all actions are now terminal).
                    _phase2_ever_existed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                    ).count() > 0
                    if _phase2_ever_existed and not _phase2_active:
                        _expired_count = db.query(_AA0).filter(
                            _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
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
                                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
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
                                    _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                                    _AA0.status == _AAS0.EXPIRED,
                                    _AA0.action_type.in_([_AAT0.CORDON_NODE, _AAT0.DRAIN_NODE, _AAT0.TERMINATE_NODE]),
                                ).delete(synchronize_session=False)
                                db.commit()
                                _phase2_any = False
                                _phase2_active = False

                    _phase2_exists = _phase2_any
                    # Ghost terminate has no CORDON action (TERMINATE-only path) —
                    # treat as Phase 2 existing so we skip the spot-wait block and
                    # route through the ghost_terminate bypass below.
                    if _wa_meta.get('ghost_terminate'):
                        _phase2_exists = True

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
                    _SPOT_WAIT_TIMEOUT_S = 30 * 60  # 30 minutes default
                    # Fix 2: Configurable Phase 1 hard timeout from cluster settings.
                    # spot_join_timeout_minutes overrides the default 30-min timeout.
                    if _wa_opt and getattr(_wa_opt, 'spot_join_timeout_minutes', None):
                        _SPOT_WAIT_TIMEOUT_S = int(_wa_opt.spot_join_timeout_minutes) * 60

                    # ── GHOST NODE EARLY FAST-PATH ──────────────────────────────
                    # If the target is ASG-backed but not in K8s (ghost node), skip
                    # Phase 1 spot-wait entirely — no pods to drain, no replacement
                    # spot node needed. Detect here so we never create a trigger pod.
                    if (
                        _wa_meta.get('asg_name_used')
                        and not _wa_meta.get('ghost_terminate')
                        and not _wa_meta.get('phase2_created_at')
                    ):
                        _ghfp_node = _wa_meta.get('target_node_name', '')
                        _ghfp_inst = _wa_instance_id
                        _ghfp_is_ghost = False
                        try:
                            if _wa_cluster_obj:
                                from backend.services.karpenter_service import KarpenterService as _KS_GHFP
                                _ks_ghfp = _KS_GHFP(db, _redis)
                                _ghfp_api = _ks_ghfp._get_k8s_client(_wa_cluster_obj)
                                from kubernetes import client as _k8s_ghfp
                                _ghfp_names = {n.metadata.name for n in _k8s_ghfp.CoreV1Api(_ghfp_api).list_node().items}
                                if _ghfp_node and _ghfp_node not in _ghfp_names:
                                    _ghfp_is_ghost = True
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: Ghost fast-path "
                                        f"— {_ghfp_node} ({_ghfp_inst[:12]}) not in K8s, "
                                        f"ASG={_wa_meta['asg_name_used'][:25]}. Skipping Phase 1."
                                    )
                        except Exception as _ghfp_err:
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: Ghost fast-path K8s check failed: {_ghfp_err}"
                            )
                        if _ghfp_is_ghost:
                            # Delete trigger pod if already created (not needed for ghost)
                            _ghfp_trig = _wa_meta.get('trigger_pod_name', f"spot-trigger-{_wa.id}")
                            if _wa_meta.get('trigger_pod_created') and _wa_cluster_obj:
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_GHFP2
                                    _KS_GHFP2(db, _redis).delete_spot_trigger_pod(
                                        cluster_id=_wa.cluster_id, pod_name=_ghfp_trig,
                                    )
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: Deleted trigger pod "
                                        f"'{_ghfp_trig}' (ghost fast-path, not needed)"
                                    )
                                except Exception:
                                    pass
                            # Create TERMINATE-only agent action — no cordon/drain needed
                            from backend.models.agent_action import AgentAction as _AA_GHFP
                            from backend.models.agent_action import AgentActionType as _AAT_GHFP
                            _ghfp_term_action = _AA_GHFP(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT_GHFP.TERMINATE_NODE,
                                payload={
                                    "instance_id": _ghfp_inst,
                                    "node_name": None,
                                    "rebalancing_action_id": str(_wa.id),
                                    "zero_downtime_step": 4,
                                    "termination_mode": "scaledown",
                                    "asg_name": _wa_meta.get("asg_name_used"),
                                    "asg_min_at_start": _wa_meta.get("asg_min_at_start"),
                                    "asg_desired_at_start": _wa_meta.get("asg_desired_at_start"),
                                    "ghost_node": True,
                                },
                            )
                            db.add(_ghfp_term_action)
                            db.flush()
                            _wa_meta['ghost_terminate'] = True
                            _wa_meta['termination_mode'] = 'scaledown'
                            _wa_meta['phase2_created_at'] = datetime.utcnow().isoformat()
                            _wa_meta['current_step'] = 'ghost_terminate_pending'
                            _wa.action_metadata = _wa_meta
                            db.commit()
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Ghost fast-path — "
                                f"TERMINATE-only action created for {_ghfp_inst[:12]}, "
                                f"skipping spot wait"
                            )
                            continue  # Next cycle: TERMINATE pending → agent picks up

                    # ── Phase 2 creation: NEW spot joined OR timeout ───────────
                    if not _phase2_exists:
                        if _wa_karpenter_active and not _new_spot_joined and _spot_wait_elapsed < _SPOT_WAIT_TIMEOUT_S:
                            # Karpenter only provisions nodes when there are pending pods.
                            # EKS managed node group nodes are NOT managed by Karpenter, so
                            # consolidation won't trigger.  After 10s of 0 spot nodes, create
                            # a lightweight "trigger" pod that requests spot capacity.  Karpenter
                            # sees the pending pod and provisions a spot node.  The trigger pod
                            # is cleaned up once a spot node joins.
                            # Enhancement 2: Cut from 60s → 10s (NodePool propagation to Karpenter
                            # controller cache is 5-10s; 10s is a safe floor).
                            if _spot_count <= _spot_baseline and _spot_wait_elapsed >= 10 and not _wa_meta.get('trigger_pod_created'):
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_TRIG
                                    _ks_trig = _KS_TRIG(db, _redis)
                                    _trig_name = f"spot-trigger-{_wa.id}"
                                    # Extract target instance type from action's target_pool
                                    # (format: "instance_type:az", e.g. "c7g.medium:ap-south-1a")
                                    _trig_instance_type = ""
                                    if _wa.target_pool and ':' in _wa.target_pool:
                                        _trig_instance_type = _wa.target_pool.split(':')[0]
                                    elif _wa.target_pool:
                                        _trig_instance_type = _wa.target_pool
                                    # Label every existing node with
                                    # 'spot-optimizer.io/existing-node=true' so
                                    # the trigger pod's DoesNotExist nodeAffinity
                                    # keeps it Pending, forcing Karpenter to
                                    # provision a brand-new spot node.
                                    # (kubernetes.io/hostname is a restricted label
                                    #  in Karpenter and cannot be used.)
                                    _existing_nodes = []
                                    try:
                                        _ks_cluster = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                                        if _ks_cluster:
                                            _k8s_api = _ks_trig._get_k8s_client(_ks_cluster)
                                            from kubernetes import client as _k8s_c
                                            _core_v1 = _k8s_c.CoreV1Api(_k8s_api)
                                            _all_nodes = _core_v1.list_node().items
                                            _existing_nodes = [n.metadata.name for n in _all_nodes]
                                            # Enhancement 6: Parallel node labelling + Redis cache
                                            _label_body = {"metadata": {"labels": {"spot-optimizer.io/existing-node": "true"}}}
                                            _label_cache_key = f"spot:nodes_labelled:{_wa.cluster_id}"
                                            _already_labelled = set()
                                            try:
                                                _cached_labels = _redis.smembers(_label_cache_key)
                                                _already_labelled = {
                                                    (v.decode() if isinstance(v, bytes) else v) for v in _cached_labels
                                                } if _cached_labels else set()
                                            except Exception:
                                                pass
                                            _to_label = [n for n in _existing_nodes if n not in _already_labelled]
                                            if _to_label:
                                                from concurrent.futures import ThreadPoolExecutor as _TPE_LBL
                                                def _label_node(_n):
                                                    try:
                                                        _core_v1.patch_node(_n, _label_body)
                                                        return _n
                                                    except Exception:
                                                        return None
                                                with _TPE_LBL(max_workers=min(10, len(_to_label))) as _lbl_pool:
                                                    _labelled = list(_lbl_pool.map(_label_node, _to_label))
                                                _newly_labelled = [n for n in _labelled if n]
                                                if _newly_labelled:
                                                    try:
                                                        _redis.sadd(_label_cache_key, *_newly_labelled)
                                                        _redis.expire(_label_cache_key, 3600)
                                                    except Exception:
                                                        pass
                                            logger.info(
                                                f"[auto_rebalancer] Action {_wa.id}: Labelled {len(_to_label)} "
                                                f"nodes ({len(_already_labelled)} cached) with spot-optimizer.io/existing-node=true"
                                            )
                                    except Exception as _node_err:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: Could not list nodes "
                                            f"for exclusion: {_node_err}"
                                        )
                                    # ── Workload-aware trigger pod sizing ──
                                    # Query the source OD node's aggregate pod requests so the
                                    # trigger pod reserves enough capacity for Karpenter to pick
                                    # an instance size that can actually host the drained workloads.
                                    _trig_cpu = "100m"
                                    _trig_mem = "128Mi"
                                    try:
                                        _src_inst_id = _wa_meta.get("instance_id", "") or (_wa.source_instance_id or "")
                                        if _src_inst_id:
                                            _src_inst = db.query(Instance).filter(
                                                Instance.instance_id == _src_inst_id
                                            ).first()
                                            _src_node = _src_inst.node_name if _src_inst else None
                                            if _src_node:
                                                from backend.models.pod_metric import PodMetric as _PM
                                                from sqlalchemy import func as _sqla_func
                                                # Latest metric snapshot per pod on this node
                                                # (exclude DaemonSet pods — they exist on every node)
                                                _latest_ts = db.query(
                                                    _sqla_func.max(_PM.timestamp)
                                                ).filter(
                                                    _PM.cluster_id == _wa.cluster_id,
                                                    _PM.node_name == _src_node,
                                                ).scalar()
                                                if _latest_ts:
                                                    _node_pods = db.query(
                                                        _sqla_func.coalesce(_sqla_func.sum(_PM.cpu_request_millicores), 0),
                                                        _sqla_func.coalesce(_sqla_func.sum(_PM.memory_request_bytes), 0),
                                                    ).filter(
                                                        _PM.cluster_id == _wa.cluster_id,
                                                        _PM.node_name == _src_node,
                                                        _PM.timestamp == _latest_ts,
                                                        _sqla_func.coalesce(_PM.controller_kind, '') != 'DaemonSet',
                                                    ).first()
                                                    if _node_pods:
                                                        _total_cpu_m = int(_node_pods[0] or 0)
                                                        _total_mem_b = int(_node_pods[1] or 0)
                                                        # Apply 10% safety margin, enforce minimums
                                                        _total_cpu_m = max(int(_total_cpu_m * 1.1), 100)
                                                        _total_mem_mi = max(int((_total_mem_b * 1.1) / (1024 * 1024)), 128)
                                                        _trig_cpu = f"{_total_cpu_m}m"
                                                        _trig_mem = f"{_total_mem_mi}Mi"
                                                        logger.info(
                                                            f"[auto_rebalancer] Action {_wa.id}: Trigger pod sized "
                                                            f"from node {_src_node} workload: cpu={_trig_cpu}, mem={_trig_mem}"
                                                        )
                                    except Exception as _sizing_err:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: Workload sizing failed, "
                                            f"using defaults: {_sizing_err}"
                                        )
                                    _trig_nodepool = _wa_meta.get('karpenter_nodepool_name', 'default')
                                    _trig_result = _ks_trig.create_spot_trigger_pod(
                                        cluster_id=_wa.cluster_id,
                                        pod_name=_trig_name,
                                        target_instance_type=_trig_instance_type,
                                        nodepool_name=_trig_nodepool,
                                        exclude_nodes=_existing_nodes,
                                        cpu_request=_trig_cpu,
                                        memory_request=_trig_mem,
                                    )
                                    if _trig_result:
                                        _wa_meta['trigger_pod_created'] = True
                                        _wa_meta['trigger_pod_name'] = _trig_name
                                        _wa_meta['trigger_pod_instance_type'] = _trig_instance_type
                                        _wa_meta['trigger_cpu'] = _trig_cpu
                                        _wa_meta['trigger_mem'] = _trig_mem
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: Created spot trigger pod "
                                            f"'{_trig_name}' (nodepool={_trig_nodepool}, type={_trig_instance_type}) "
                                            f"to force Karpenter provisioning"
                                        )
                                    else:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: Failed to create trigger pod"
                                        )
                                except Exception as _trig_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Trigger pod error: {_trig_err}"
                                    )

                            # Enhancement 7: Active trigger pod verification EVERY CYCLE.
                            # Check if trigger pod still exists, is Pending (normal), Failed,
                            # or vanished. Recreate immediately instead of waiting 120s.
                            elif _spot_count <= _spot_baseline and _wa_meta.get('trigger_pod_created'):
                                _trig_name_check = _wa_meta.get('trigger_pod_name', f"spot-trigger-{_wa.id}")
                                _trig_state = 'unknown'  # unknown|pending|failed|missing
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_TRIG2
                                    _ks_trig2 = _KS_TRIG2(db, _redis)
                                    _wa_cluster_trig = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                                    if _wa_cluster_trig:
                                        _k8s_api_trig = _ks_trig2._get_k8s_client(_wa_cluster_trig)
                                        from kubernetes import client as _k8s_trig
                                        _core_trig = _k8s_trig.CoreV1Api(_k8s_api_trig)
                                        try:
                                            _trig_pod = _core_trig.read_namespaced_pod(_trig_name_check, 'default')
                                            _trig_phase = (_trig_pod.status.phase or '').lower()
                                            if _trig_phase == 'pending':
                                                _trig_state = 'pending'
                                            elif _trig_phase == 'failed':
                                                _trig_state = 'failed'
                                            elif _trig_phase == 'running':
                                                _trig_state = 'running'
                                            elif _trig_phase == 'succeeded':
                                                _trig_state = 'succeeded'
                                            else:
                                                _trig_state = 'pending'
                                        except Exception:
                                            _trig_state = 'missing'
                                except Exception:
                                    _trig_state = 'unknown'  # K8s API error, don't spam recreate

                                if _trig_state == 'missing':
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Trigger pod "
                                        f"'{_trig_name_check}' vanished — recreating immediately"
                                    )
                                    _wa_meta['trigger_pod_created'] = False
                                    # Will be re-created on next cycle (trigger_pod_created=False)
                                elif _trig_state == 'failed':
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Trigger pod "
                                        f"'{_trig_name_check}' in Failed state — deleting and recreating"
                                    )
                                    try:
                                        _core_trig.delete_namespaced_pod(_trig_name_check, 'default')
                                    except Exception:
                                        pass
                                    _wa_meta['trigger_pod_created'] = False
                                elif _trig_state == 'pending' and _spot_wait_elapsed >= 300:
                                    # Pending for > 5 min — suspect wrong NodePool or stale config.
                                    # Re-verify NodePool has the target type and recreate.
                                    if not _wa_meta.get('trig_np_reverified'):
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: Trigger pod Pending "
                                            f"for {int(_spot_wait_elapsed)}s — re-verifying NodePool"
                                        )
                                        try:
                                            from backend.services.karpenter_service import KarpenterService as _KS_VERIFY
                                            _ks_verify = _KS_VERIFY(db, _redis)
                                            _trig_type_v = _wa_meta.get('trigger_pod_instance_type', '')
                                            if _trig_type_v:
                                                _ks_verify.add_allowed_instance_type_all_spot(
                                                    cluster_id=_wa.cluster_id,
                                                    instance_type=_trig_type_v,
                                                )
                                            _wa_meta['trig_np_reverified'] = True
                                        except Exception as _np_rev_err:
                                            logger.debug(f"[auto_rebalancer] NodePool re-verify failed: {_np_rev_err}")

                            # ── Escalation logic for baseline=0 stalls ──────────────
                            # When spot_count=0 and baseline=0, the trigger pod may be
                            # Pending because Karpenter can't get capacity for the target
                            # type. Progressively try alternative instance types.
                            # DISABLED: User requires strict ML-recommended type only.
                            # The rebalancer will wait for the ML-recommended type or
                            # timeout — no fallback to alternative instance types.
                            _ESC_ALT1_S = 300   # 5 min — try 2nd alternative type
                            _ESC_ALT2_S = 600   # 10 min — try 3rd alternative type
                            _ESC_BROAD_S = 900  # 15 min — broaden to any NodePool type
                            _ranked_alts = _wa_meta.get('ranked_alternatives', [])
                            _current_trig_type = _wa_meta.get('trigger_pod_instance_type') or _expected_instance_type or ''

                            if False and (
                                _spot_count == 0
                                and _spot_baseline == 0
                                and _wa_meta.get('trigger_pod_created')
                                and _ranked_alts
                            ):
                                _esc_action_needed = None
                                if _spot_wait_elapsed >= _ESC_BROAD_S and not _wa_meta.get('esc_broad_done'):
                                    _esc_action_needed = 'broad'
                                elif _spot_wait_elapsed >= _ESC_ALT2_S and not _wa_meta.get('esc_alt2_done'):
                                    # Pick 3rd alternative (index 2) or fall through
                                    if len(_ranked_alts) > 2 and _ranked_alts[2] != _current_trig_type:
                                        _esc_action_needed = 'alt2'
                                elif _spot_wait_elapsed >= _ESC_ALT1_S and not _wa_meta.get('esc_alt1_done'):
                                    # Pick 2nd alternative (index 1) or fall through
                                    if len(_ranked_alts) > 1 and _ranked_alts[1] != _current_trig_type:
                                        _esc_action_needed = 'alt1'

                                if _esc_action_needed:
                                    try:
                                        from backend.services.karpenter_service import KarpenterService as _KS_ESC
                                        _ks_esc = _KS_ESC(db, _redis)
                                        _esc_cluster = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                                        if _esc_cluster:
                                            _k8s_esc = _ks_esc._get_k8s_client(_esc_cluster)
                                            from kubernetes import client as _k8s_esc_c
                                            _core_esc = _k8s_esc_c.CoreV1Api(_k8s_esc)
                                            # Delete current trigger pod
                                            _trig_del_name = _wa_meta.get('trigger_pod_name', f"spot-trigger-{_wa.id}")
                                            try:
                                                _core_esc.delete_namespaced_pod(_trig_del_name, 'default')
                                            except Exception:
                                                pass  # may already be gone

                                            if _esc_action_needed == 'broad':
                                                # Broaden: don't constrain instance type — let Karpenter choose
                                                _esc_type = ''
                                                _wa_meta['esc_broad_done'] = True
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: ESCALATION 15min — "
                                                    f"recreating trigger pod with NO instance-type constraint "
                                                    f"(letting Karpenter choose from entire NodePool)"
                                                )
                                            elif _esc_action_needed == 'alt2':
                                                _esc_type = _ranked_alts[2]
                                                _wa_meta['esc_alt2_done'] = True
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: ESCALATION 10min — "
                                                    f"switching trigger pod from {_current_trig_type} to "
                                                    f"alternative type {_esc_type}"
                                                )
                                            else:  # alt1
                                                _esc_type = _ranked_alts[1]
                                                _wa_meta['esc_alt1_done'] = True
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: ESCALATION 5min — "
                                                    f"switching trigger pod from {_current_trig_type} to "
                                                    f"alternative type {_esc_type}"
                                                )

                                            # Re-label existing nodes for new trigger pod (parallel)
                                            _label_body_esc = {"metadata": {"labels": {"spot-optimizer.io/existing-node": "true"}}}
                                            _existing_esc = []
                                            try:
                                                _all_esc = _core_esc.list_node().items
                                                _existing_esc = [n.metadata.name for n in _all_esc]
                                                from concurrent.futures import ThreadPoolExecutor as _TPE_ESC
                                                def _label_esc_node(_n):
                                                    try:
                                                        _core_esc.patch_node(_n, _label_body_esc)
                                                    except Exception:
                                                        pass
                                                with _TPE_ESC(max_workers=min(10, max(1, len(_existing_esc)))) as _esc_pool:
                                                    list(_esc_pool.map(_label_esc_node, _existing_esc))
                                            except Exception:
                                                pass

                                            _trig_nodepool_esc = _wa_meta.get('karpenter_nodepool_name', 'default')

                                            # Add the escalation instance type to the
                                            # NodePool BEFORE creating the trigger pod
                                            # so Karpenter can actually provision it.
                                            if _esc_type:
                                                try:
                                                    _ks_esc.add_allowed_instance_type_all_spot(
                                                        cluster_id=_wa.cluster_id,
                                                        instance_type=_esc_type,
                                                    )
                                                    logger.info(
                                                        f"[auto_rebalancer] Action {_wa.id}: Added {_esc_type} "
                                                        f"to spot NodePool(s) for escalation"
                                                    )
                                                except Exception as _np_esc_err:
                                                    logger.warning(
                                                        f"[auto_rebalancer] Action {_wa.id}: Failed to add "
                                                        f"{_esc_type} to NodePool: {_np_esc_err}"
                                                    )

                                            _trig_result_esc = _ks_esc.create_spot_trigger_pod(
                                                cluster_id=_wa.cluster_id,
                                                pod_name=_trig_del_name,
                                                target_instance_type=_esc_type,
                                                nodepool_name=_trig_nodepool_esc,
                                                exclude_nodes=_existing_esc,
                                                cpu_request=_wa_meta.get('trigger_cpu', '100m'),
                                                memory_request=_wa_meta.get('trigger_mem', '128Mi'),
                                            )
                                            if _trig_result_esc:
                                                _wa_meta['trigger_pod_instance_type'] = _esc_type
                                                logger.info(
                                                    f"[auto_rebalancer] Action {_wa.id}: Escalation trigger pod "
                                                    f"created (type={'ANY' if not _esc_type else _esc_type})"
                                                )
                                            else:
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: Escalation trigger pod "
                                                    f"creation failed"
                                                )
                                    except Exception as _esc_err:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: Escalation error: {_esc_err}"
                                        )

                            # Still waiting for THIS action's spot replacement — do NOT create drain actions yet
                            # Fix 5: Safety escape — if a spot node exists with a node_name
                            # and we've been waiting >5 min, force Phase 2 creation.
                            # This catches cases where the readiness gate can't pass
                            # (status=UNKNOWN, K8s API unreachable) but the node is actually
                            # running and Ready in K8s.
                            if (
                                _newest_spot
                                and _newest_spot.node_name
                                and _newest_spot.instance_id
                                and _spot_wait_elapsed > 300
                            ):
                                # FIX: Verify node actually exists in K8s before forcing Phase 2.
                                # DB node_name may be set from EC2 private DNS before kubelet
                                # registers → LABEL_NODE will 404 if we proceed prematurely.
                                _fix5_node_live = False
                                try:
                                    if _wa_cluster_obj:
                                        from backend.services.karpenter_service import KarpenterService as _KS_F5
                                        _ks_f5 = _KS_F5(db, _redis)
                                        _f5_api = _ks_f5._get_k8s_client(_wa_cluster_obj)
                                        from kubernetes import client as _k8s_f5
                                        _f5_v1 = _k8s_f5.CoreV1Api(_f5_api)
                                        _f5_v1.read_node(_newest_spot.node_name)
                                        _fix5_node_live = True
                                except Exception as _f5_err:
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: Fix5 — node "
                                        f"{_newest_spot.node_name} NOT in K8s yet ({_f5_err}), "
                                        f"deferring _new_spot_joined"
                                    )

                                if _fix5_node_live:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Fix5 safety escape — "
                                        f"spot {_newest_spot.instance_id[:12]} has node_name="
                                        f"{_newest_spot.node_name} but readiness gate stuck for "
                                        f"{int(_spot_wait_elapsed)}s. Forcing _new_spot_joined=True."
                                    )
                                    _new_spot_joined = True
                                    # Pin replacement ID
                                    if not _wa_meta.get('replacement_spot_instance_id'):
                                        _wa_meta['replacement_spot_instance_id'] = _newest_spot.instance_id
                                    if not _wa_meta.get('replacement_spot_node_name'):
                                        _wa_meta['replacement_spot_node_name'] = _newest_spot.node_name
                                    _wa.action_metadata = _wa_meta
                                    # Don't continue — fall through to Phase 2 creation below
                            else:
                                _wa_meta['current_step'] = 'waiting_for_spot_node'
                                # Fix 15: Set step_entered timestamp for per-state timeout tracking
                                if 'step_entered_waiting_for_spot_node' not in _wa_meta:
                                    _wa_meta['step_entered_waiting_for_spot_node'] = datetime.utcnow().isoformat()
                                _wa_meta['spot_wait_elapsed_s'] = int(_spot_wait_elapsed)
                                _wa_meta['spot_count_current'] = _spot_count
                                _wa_meta['spot_count_baseline'] = _spot_baseline
                                _wa_meta['provisioner_type'] = 'karpenter'
                                _wa.action_metadata = _wa_meta
                                # Progressive log severity: INFO < 5min, WARNING 5-20min, ERROR > 20min
                                _wait_msg = (
                                    f"[auto_rebalancer] Action {_wa.id}: Phase 1 done, "
                                    f"waiting for NEW spot node (current={_spot_count}, baseline={_spot_baseline}, "
                                    f"{int(_spot_wait_elapsed)}s elapsed, timeout {_SPOT_WAIT_TIMEOUT_S}s)"
                                )
                                if _spot_wait_elapsed >= 1200:
                                    logger.error(_wait_msg)
                                elif _spot_wait_elapsed >= 300:
                                    logger.warning(_wait_msg)
                                else:
                                    logger.info(_wait_msg)
                                db.commit()
                                continue  # Re-check next cycle (outer for _wa loop)

                        if _new_spot_joined:
                            # ── ATOMIC CLAIM: Prevent two actions from sharing one replacement ──
                            # Use Redis SET NX to atomically claim this replacement instance.
                            # If another action already claimed it, this action must wait for
                            # a new spot node instead of proceeding with Phase 2.
                            _claim_inst_id = _newest_spot.instance_id if _newest_spot else None
                            if _claim_inst_id and _redis:
                                _claim_key = f"spot:replacement_claimed:{_claim_inst_id}"
                                _claimed = _redis.set(_claim_key, str(_wa.id), nx=True, ex=3600)
                                if not _claimed:
                                    _existing_claim = _redis.get(_claim_key)
                                    _existing_claim_str = _existing_claim.decode() if isinstance(_existing_claim, bytes) else str(_existing_claim)
                                    if _existing_claim_str != str(_wa.id):
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: replacement "
                                            f"{_claim_inst_id[:12]} already claimed by action "
                                            f"{_existing_claim_str} — waiting for a new spot node"
                                        )
                                        _new_spot_joined = False
                                        # Reset and wait for next cycle
                                        _wa_meta['current_step'] = 'waiting_for_spot_node'
                                        _wa_meta['spot_wait_elapsed_s'] = int(_spot_wait_elapsed)
                                        _wa.action_metadata = _wa_meta
                                        db.commit()
                                        continue

                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: NEW spot node joined! "
                                f"(count {_spot_baseline} → {_spot_count}) "
                                f"Creating Phase 2 actions (CORDON→DRAIN→TERMINATE)"
                            )
                            _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()

                            # ── TAG SPOT INSTANCE: Copy Name tag from source OD instance ──
                            # Karpenter-provisioned spots don't inherit the ASG Name tag.
                            # Copy it from the original OD instance so the spot shows a
                            # proper Name in the AWS console instead of blank.
                            _tag_src_id = _wa_meta.get("instance_id", "") or (_wa.source_instance_id or "")
                            _tag_repl_id = _wa_meta.get('replacement_spot_instance_id', '')
                            if _tag_src_id and _tag_repl_id and _tag_src_id.startswith("i-") and _tag_repl_id.startswith("i-"):
                                try:
                                    import boto3 as _b3tag
                                    from backend.models.system_config import SystemConfig as _SC_TAG
                                    _tag_cluster = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                                    _tag_region = (_tag_cluster.region if _tag_cluster else None) or "ap-south-1"

                                    _pk_t = db.query(_SC_TAG).filter(_SC_TAG.key == "PLATFORM_AWS_ACCESS_KEY").first()
                                    _ps_t = db.query(_SC_TAG).filter(_SC_TAG.key == "PLATFORM_AWS_SECRET").first()
                                    _plat_key_t = (_pk_t.value if _pk_t and _pk_t.value else None)
                                    _plat_secret_t = (_ps_t.value if _ps_t and _ps_t.value else None)

                                    _tag_creds = {}
                                    _tag_role = (_tag_cluster.aws_role_arn if _tag_cluster else None)
                                    _tag_ext = (_tag_cluster.aws_external_id if _tag_cluster else None)
                                    if not _tag_role and _tag_cluster and _tag_cluster.account_id:
                                        try:
                                            from backend.models.account import Account as _Acct_TAG
                                            _acct_t = db.query(_Acct_TAG).filter(_Acct_TAG.id == _tag_cluster.account_id).first()
                                            if _acct_t:
                                                _tag_role = _acct_t.role_arn
                                                _tag_ext = _acct_t.external_id
                                        except Exception:
                                            pass

                                    if _tag_role and _plat_key_t and _plat_secret_t:
                                        _sts_t = _b3tag.client("sts", aws_access_key_id=_plat_key_t,
                                                               aws_secret_access_key=_plat_secret_t, region_name=_tag_region)
                                        _assume_kw = {"RoleArn": _tag_role, "RoleSessionName": "spot-rebalancer-tag"}
                                        if _tag_ext:
                                            _assume_kw["ExternalId"] = _tag_ext
                                        _assumed_t = _sts_t.assume_role(**_assume_kw)
                                        _ct = _assumed_t["Credentials"]
                                        _tag_creds = {
                                            "aws_access_key_id": _ct["AccessKeyId"],
                                            "aws_secret_access_key": _ct["SecretAccessKey"],
                                            "aws_session_token": _ct["SessionToken"],
                                        }
                                    elif _plat_key_t and _plat_secret_t:
                                        _tag_creds = {"aws_access_key_id": _plat_key_t,
                                                      "aws_secret_access_key": _plat_secret_t}

                                    if _tag_creds:
                                        _ec2_tag = _b3tag.client("ec2", region_name=_tag_region, **_tag_creds)

                                        # Read Name tag from source OD instance
                                        _src_tags_resp = _ec2_tag.describe_tags(Filters=[
                                            {"Name": "resource-id", "Values": [_tag_src_id]},
                                            {"Name": "key", "Values": ["Name"]},
                                        ])
                                        _src_name = ""
                                        for _t in _src_tags_resp.get("Tags", []):
                                            if _t.get("Key") == "Name":
                                                _src_name = _t.get("Value", "")
                                                break

                                        if not _src_name:
                                            _src_name = f"{_tag_cluster.name}-spot-node" if _tag_cluster else "spot-node"

                                        # Apply Name tag + cluster Name tag to the replacement spot
                                        _new_tags = [
                                            {"Key": "Name", "Value": _src_name},
                                        ]
                                        _ec2_tag.create_tags(Resources=[_tag_repl_id], Tags=_new_tags)
                                        _wa_meta['spot_name_tag_applied'] = _src_name
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: Tagged spot "
                                            f"{_tag_repl_id[:12]} with Name='{_src_name}'"
                                        )
                                except Exception as _tag_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Failed to tag "
                                        f"spot instance: {_tag_err}"
                                    )

                            # Clean up trigger pod if one was created
                            _trig_pod_name = _wa_meta.get('trigger_pod_name')
                            if _trig_pod_name:
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_CLEAN
                                    _ks_clean = _KS_CLEAN(db, _redis)
                                    _ks_clean.delete_spot_trigger_pod(
                                        cluster_id=_wa.cluster_id,
                                        pod_name=_trig_pod_name,
                                    )
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: Cleaned up trigger pod '{_trig_pod_name}'"
                                    )
                                except Exception as _trig_clean_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Trigger pod cleanup failed: {_trig_clean_err}"
                                    )

                            # Apply karpenter.sh/do-not-disrupt=true to the new spot node.
                            # This prevents Karpenter's consolidation/expiry loop from
                            # terminating the replacement node while pods are still draining
                            # onto it.  The annotation is removed after Phase 2 completes.
                            if _newest_spot and _newest_spot.node_name:
                                # CRITICAL: Apply annotation DIRECTLY via backend K8s API
                                # instead of (or in addition to) an agent action, because
                                # the agent may be unreachable and the LABEL_NODE action
                                # stays PENDING → Karpenter kills the unprotected spot.
                                _dnd_applied = False
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_DND
                                    _ks_dnd = _KS_DND(db=db)
                                    _wa_cluster_dnd = db.query(Cluster).filter(
                                        Cluster.id == _wa.cluster_id
                                    ).first()
                                    if _wa_cluster_dnd:
                                        _k8s_api_dnd = _ks_dnd._get_k8s_client(_wa_cluster_dnd)
                                        from kubernetes import client as _k8s_dnd
                                        _core_dnd = _k8s_dnd.CoreV1Api(_k8s_api_dnd)
                                        # Retry with backoff: node may still be registering
                                        # in K8s after EC2 launch (404 = not found yet).
                                        import time as _time_dnd
                                        _DND_MAX_RETRIES = 6
                                        _DND_RETRY_INTERVAL_S = 5  # 6 x 5s = 30s max wait
                                        for _dnd_attempt in range(1, _DND_MAX_RETRIES + 1):
                                            try:
                                                _core_dnd.patch_node(
                                                    _newest_spot.node_name,
                                                    {"metadata": {"annotations": {
                                                        "karpenter.sh/do-not-disrupt": "true"
                                                    }}}
                                                )
                                                _dnd_applied = True
                                                logger.info(
                                                    f"[auto_rebalancer] Action {_wa.id}: Applied "
                                                    f"karpenter.sh/do-not-disrupt=true DIRECTLY on "
                                                    f"{_newest_spot.node_name} via backend K8s API"
                                                    f" (attempt {_dnd_attempt}/{_DND_MAX_RETRIES})"
                                                )
                                                break  # success
                                            except _k8s_dnd.ApiException as _dnd_api_err:
                                                if _dnd_api_err.status == 404 and _dnd_attempt < _DND_MAX_RETRIES:
                                                    logger.info(
                                                        f"[auto_rebalancer] Action {_wa.id}: Node "
                                                        f"{_newest_spot.node_name} not found in K8s yet "
                                                        f"(attempt {_dnd_attempt}/{_DND_MAX_RETRIES}), "
                                                        f"retrying in {_DND_RETRY_INTERVAL_S}s..."
                                                    )
                                                    _time_dnd.sleep(_DND_RETRY_INTERVAL_S)
                                                else:
                                                    raise  # non-404 or last attempt → bubble up
                                except Exception as _dnd_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Direct do-not-disrupt "
                                        f"annotation failed: {_dnd_err} — falling back to agent action"
                                    )

                                # Also queue the agent action as a backup (agent may apply it
                                # if the direct path failed or when it eventually reconnects)
                                if not _dnd_applied:
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
                                                "zero_downtime_step": 1,
                                            },
                                        )
                                        db.add(_kp_annotate)
                                        db.flush()
                                        logger.info(
                                            f"[auto_rebalancer] Queued karpenter.sh/do-not-disrupt=true "
                                            f"on {_newest_spot.node_name} (action {_wa.id}) [fallback]"
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
                                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
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
                                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
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
                            _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
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
                            _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                            db.commit()
                            continue  # outer for _wa loop

                        # ── CREATE PHASE 2 ACTIONS ────────────────────────────
                        # Retrieve instance params from action metadata (set in Phase 1)
                        _p2 = _wa_meta.get("phase2_params", {})
                        # Fix 12: Instance ID fallback chain — phase2_params → metadata → model field
                        _p2_instance_id = (
                            _p2.get("instance_id")
                            or _wa_meta.get("instance_id", "")
                            or (_wa.source_instance_id or "")
                        )
                        _p2_instance_type = _p2.get("instance_type", "")
                        _p2_az = _p2.get("az", "")

                        # ── Source-alive gate: abort if the OD instance was already
                        #    terminated (e.g. by ASG AZ-rebalancing) while we waited ──
                        if _p2_instance_id:
                            from backend.models.instance import Instance as _InstAlive
                            _src_alive = db.query(_InstAlive).filter(
                                _InstAlive.instance_id == _p2_instance_id,
                                _InstAlive.state == 'running',
                            ).first()
                            if not _src_alive:
                                logger.warning(
                                    f"[auto_rebalancer] Action {_wa.id}: source OD "
                                    f"{_p2_instance_id} is no longer running (terminated by "
                                    f"ASG or externally). Aborting — no node to replace."
                                )
                                _wa.status = 'cancelled'
                                _wa.error_message = (
                                    f"Source instance {_p2_instance_id} terminated externally "
                                    f"before Phase 2 could start."
                                )
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                                db.commit()
                                continue  # outer for _wa loop

                        # Karpenter manages node lifecycle — no ASG attach needed.
                        # Fix #6: If the source OD node belongs to an ASG (detected in
                        # Phase 1 and stored in metadata), use "scaledown" mode so the
                        # agent calls terminate_instance_in_auto_scaling_group with
                        # ShouldDecrementDesiredCapacity=True.  This prevents the ASG
                        # from auto-healing by launching a new OD instance to replace
                        # the one we just terminated.
                        _p2_asg_name = _wa_meta.get("asg_name_used")
                        if _p2_asg_name:
                            _p2_term_mode = "scaledown"
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: source OD node is ASG-backed "
                                f"(asg={_p2_asg_name}) — using termination_mode='scaledown' "
                                f"(ShouldDecrementDesiredCapacity=True)"
                            )
                        else:
                            _p2_term_mode = "karpenter"
                        _wa_meta['termination_mode'] = _p2_term_mode

                        # Bug #8 fix: Resolve node_name from DB and verify the
                        # target OD instance is actually registered in K8s before
                        # creating CORDON/DRAIN actions.  Without this, the agent
                        # may resolve the wrong node via type+AZ fallback.
                        _p2_node_name = None
                        if _p2_instance_id:
                            from backend.models.instance import Instance as _InstP2
                            _p2_inst_obj = db.query(_InstP2).filter(
                                _InstP2.cluster_id == _wa.cluster_id,
                                _InstP2.instance_id == _p2_instance_id,
                            ).first()
                            _p2_node_name = getattr(_p2_inst_obj, 'node_name', None) if _p2_inst_obj else None
                            # Fix 6: providerID fallback — if DB node_name is empty,
                            # query K8s nodes by spec.providerID to find the node name.
                            # This handles nodes where aws_sync or collector hasn't
                            # populated node_name yet but the node IS in K8s.
                            if not _p2_node_name and _wa_cluster_obj and _p2_instance_id:
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_F6
                                    _ks_f6 = _KS_F6(db, _redis)
                                    _f6_api = _ks_f6._get_k8s_client(_wa_cluster_obj)
                                    from kubernetes import client as _k8s_f6
                                    _f6_v1 = _k8s_f6.CoreV1Api(_f6_api)
                                    for _f6_node in _f6_v1.list_node().items:
                                        _f6_pid = (_f6_node.spec.provider_id or '') if _f6_node.spec else ''
                                        if _p2_instance_id in _f6_pid:
                                            _p2_node_name = _f6_node.metadata.name
                                            # Update DB so we don't have to do this again
                                            if _p2_inst_obj:
                                                _p2_inst_obj.node_name = _p2_node_name
                                                db.flush()
                                            logger.info(
                                                f"[auto_rebalancer] Action {_wa.id}: Fix6 — "
                                                f"resolved node_name={_p2_node_name} via "
                                                f"providerID for {_p2_instance_id[:12]}"
                                            )
                                            break
                                except Exception as _f6_err:
                                    logger.debug(
                                        f"[auto_rebalancer] Action {_wa.id}: Fix6 providerID "
                                        f"lookup failed: {_f6_err}"
                                    )
                            # Also check action metadata for target_node_name
                            if not _p2_node_name:
                                _p2_node_name = _wa_meta.get('target_node_name')
                            # Verify the node actually exists in K8s via the backend K8s client.
                            # If the node is MISSING from K8s but the instance is ASG-backed,
                            # skip cordon/drain (no pods to drain) and go straight to ASG
                            # terminate+decrement.  This handles the common case where the
                            # kubelet crashed or the node was removed but EC2 is still running.
                            _p2_skip_cordon_drain = False
                            if _p2_node_name:
                                try:
                                    from backend.services.karpenter_service import KarpenterService as _KS_p2v
                                    from kubernetes import client as _k8s_client_p2v
                                    _ks_p2v = _KS_p2v(db=db)
                                    _wa_cluster_obj = db.query(Cluster).filter(Cluster.id == _wa.cluster_id).first()
                                    if _wa_cluster_obj:
                                        _k8s_api = _ks_p2v._get_k8s_client(_wa_cluster_obj)
                                        _core_v1 = _k8s_client_p2v.CoreV1Api(_k8s_api)
                                        _k8s_nodes_p2v = _core_v1.list_node()
                                        _p2v_names = {n.metadata.name for n in _k8s_nodes_p2v.items}
                                        if _p2_node_name not in _p2v_names:
                                            _p2_asg_for_ghost = _wa_meta.get("asg_name_used")
                                            if _p2_asg_for_ghost:
                                                # Node gone from K8s but EC2 still in ASG —
                                                # skip cordon/drain, go straight to terminate+decrement.
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: target node "
                                                    f"{_p2_node_name} ({_p2_instance_id}) NOT in K8s "
                                                    f"(known: {_p2v_names}) but instance is ASG-backed "
                                                    f"(asg={_p2_asg_for_ghost}). Skipping cordon/drain, "
                                                    f"will terminate+decrement ASG directly."
                                                )
                                                _p2_skip_cordon_drain = True
                                            else:
                                                # Not ASG-backed and not in K8s — nothing to do.
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: target node "
                                                    f"{_p2_node_name} ({_p2_instance_id}) NOT registered in K8s "
                                                    f"(known: {_p2v_names}) and not ASG-backed. Marking failed."
                                                )
                                                _wa.status = 'failed'
                                                _wa.error_message = (
                                                    f"Target instance {_p2_instance_id} node {_p2_node_name} "
                                                    f"is not registered in Kubernetes. Cannot cordon/drain."
                                                )
                                                _wa.completed_at = datetime.utcnow()
                                                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                                                db.commit()
                                                continue
                                except Exception as _p2v_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: K8s node verification "
                                        f"failed: {_p2v_err} — proceeding with node_name from DB"
                                    )

                        if _p2_instance_id and _p2_skip_cordon_drain:
                            # Node not in K8s but instance in ASG — skip cordon/drain (no pods
                            # to drain) and create ONLY the TERMINATE agent action so the
                            # existing backend-side terminate logic (with full credential
                            # resolution and ASG decrement) handles it.
                            from backend.models.agent_action import AgentAction as _AA_P2G
                            from backend.models.agent_action import AgentActionType as _AAT0G
                            terminate_ghost = _AA_P2G(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0G.TERMINATE_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "node_name": None,
                                    "rebalancing_action_id": str(_wa.id),
                                    "zero_downtime_step": 4,
                                    "termination_mode": "scaledown",
                                    "asg_name": _wa_meta.get("asg_name_used"),
                                    "asg_min_at_start": _wa_meta.get("asg_min_at_start"),
                                    "asg_desired_at_start": _wa_meta.get("asg_desired_at_start"),
                                    "ghost_node": True,
                                }
                            )
                            db.add(terminate_ghost)
                            db.flush()
                            _wa_meta['current_step'] = 'ghost_terminate_pending'
                            _wa_meta['ghost_terminate'] = True
                            _wa_meta['termination_mode'] = 'scaledown'
                            _wa_meta['phase2_created_at'] = datetime.utcnow().isoformat()
                            _wa.action_metadata = _wa_meta
                            flag_modified(_wa, 'action_metadata')
                            db.commit()
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Created TERMINATE-only action "
                                f"for ghost OD node {_p2_instance_id} (skipping cordon/drain — "
                                f"node not in K8s)"
                            )
                        elif _p2_instance_id:
                            # ── E2: PRE-CORDON ENDPOINT CONVERGENCE GATE ────────────
                            # Problem 2: Verify pods on the new spot node are routable
                            # (IPs in EndpointSlice, kube-proxy propagated) before
                            # cordoning the old node. Without this, there is a 30-60s
                            # window where old pods are being drained and replacements
                            # are not yet serving traffic.
                            _e2_passed = True  # default: pass (fail-open)
                            _repl_node_name = _wa_meta.get('replacement_spot_node_name', '')
                            if _repl_node_name and _wa_cluster_obj:
                                try:
                                    from backend.pipeline.stage4_decision.eviction_safety import check_endpoints_for_node_pods, KUBE_PROXY_SOAK_BY_TIER as _E2_SOAK_MAP
                                    from backend.services.karpenter_service import KarpenterService as _KS_E2
                                    from kubernetes import client as _k8s_e2
                                    _ks_e2 = _KS_E2(db, _redis)
                                    _e2_api = _ks_e2._get_k8s_client(_wa_cluster_obj)
                                    _e2_core = _k8s_e2.CoreV1Api(_e2_api)
                                    _e2_discovery = _k8s_e2.DiscoveryV1Api(_e2_api)
                                    # W6.5: use tier-based soak if drain_tier was stored on a previous iteration
                                    _e2_soak_s = _E2_SOAK_MAP.get(_wa_meta.get("drain_tier", 4), 10)
                                    _e2_all_routable, _e2_unroutable = check_endpoints_for_node_pods(
                                        core_v1=_e2_core,
                                        discovery_v1=_e2_discovery,
                                        namespace_filter=None,
                                        new_node_name=_repl_node_name,
                                        min_ready_seconds=_e2_soak_s,
                                        timeout_seconds=120,
                                    )
                                    if not _e2_all_routable:
                                        # Check if we've been waiting too long (5 min max)
                                        _e2_start = _wa_meta.get('e2_gate_started_at')
                                        if not _e2_start:
                                            _wa_meta['e2_gate_started_at'] = datetime.utcnow().isoformat()
                                            _wa_meta['current_step'] = 'endpoint_convergence'
                                            _wa.action_metadata = _wa_meta
                                            flag_modified(_wa, 'action_metadata')
                                            db.commit()
                                            logger.info(
                                                f"[auto_rebalancer] Action {_wa.id}: E2 gate — "
                                                f"{len(_e2_unroutable)} pod(s) on {_repl_node_name} not "
                                                f"yet routable. Waiting for endpoint convergence."
                                            )
                                            continue
                                        _e2_elapsed = (
                                            datetime.utcnow() - datetime.fromisoformat(_e2_start)
                                        ).total_seconds()
                                        if _e2_elapsed < 300:  # 5 min max wait
                                            _wa_meta['current_step'] = 'endpoint_convergence'
                                            _wa_meta['e2_elapsed_s'] = int(_e2_elapsed)
                                            _wa.action_metadata = _wa_meta
                                            flag_modified(_wa, 'action_metadata')
                                            db.commit()
                                            continue
                                        else:
                                            logger.warning(
                                                f"[auto_rebalancer] Action {_wa.id}: E2 gate timeout "
                                                f"({int(_e2_elapsed)}s) — proceeding with cordon despite "
                                                f"unroutable pods: {_e2_unroutable[:3]}"
                                            )
                                    else:
                                        _wa_meta['e2_endpoints_verified'] = True
                                        _wa_meta['e2_endpoints_verified_at'] = datetime.utcnow().isoformat()
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: E2 gate PASSED — "
                                            f"all pods on {_repl_node_name} confirmed routable"
                                        )
                                except Exception as _e2_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: E2 endpoint check "
                                        f"failed ({_e2_err}) — proceeding (fail-open)"
                                    )

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
                                    "node_name": _p2_node_name,
                                    "instance_type": _p2_instance_type,
                                    "az": _p2_az,
                                    "rebalancing_action_id": str(_wa.id),
                                    "zero_downtime_step": 2,
                                }
                            )
                            drain_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.DRAIN_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "node_name": _p2_node_name,
                                    "instance_type": _p2_instance_type,
                                    "az": _p2_az,
                                    "ignore_daemonsets": True,
                                    "grace_period_seconds": 60,
                                    "force": _n1_force_drain,
                                    "rebalancing_action_id": str(_wa.id),
                                    "zero_downtime_step": 3,
                                }
                            )
                            terminate_p2 = _AA_P2(
                                cluster_id=_wa.cluster_id,
                                action_type=_AAT0.TERMINATE_NODE,
                                payload={
                                    "instance_id": _p2_instance_id,
                                    "node_name": None,
                                    "rebalancing_action_id": str(_wa.id),
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
                            _wa_meta['step_entered_cordoning_node'] = datetime.utcnow().isoformat()
                            _wa_meta['phase2_created_at'] = datetime.utcnow().isoformat()
                            _wa.action_metadata = _wa_meta
                            flag_modified(_wa, 'action_metadata')
                            # ── Step journal: CORDON+DRAIN+TERMINATE dispatched ────
                            _advance_action_step(db, _wa, ACTION_STEP_DRAINING)
                            db.commit()
                            logger.info(
                                f"[auto_rebalancer] Action {_wa.id}: Phase 2 created "
                                f"(CORDON→DRAIN→TERMINATE for {_p2_instance_id})"
                            )

                            # ── INLINE CORDON+DRAIN: execute immediately from backend ──
                            # The agent often takes 90+ seconds to pick up actions due to
                            # step-gating and polling intervals.  Backend has direct K8s API
                            # access and can complete CORDON+DRAIN in 1-3 seconds.
                            _inline_ok = False
                            _inline_t0 = datetime.utcnow()
                            try:
                                from backend.services.karpenter_service import KarpenterService as _KS_INL
                                from kubernetes import client as _k8s_inl
                                _ks_inl = _KS_INL(db, _redis)
                                _wa_cluster_inl = db.query(Cluster).filter(
                                    Cluster.id == _wa.cluster_id
                                ).first()
                                if _wa_cluster_inl and _p2_node_name:
                                    _k8s_api_inl = _ks_inl._get_k8s_client(_wa_cluster_inl)
                                    _core_inl = _k8s_inl.CoreV1Api(_k8s_api_inl)

                                    # ── CORDON + draining label (Change 2) ──
                                    # Label is read by PC._select_burst_pods to skip pods on this node.
                                    _core_inl.patch_node(
                                        _p2_node_name,
                                        {
                                            "spec": {"unschedulable": True},
                                            "metadata": {"labels": {"spot-optimizer/draining": "true"}},
                                        }
                                    )
                                    cordon_p2.status = _AAS0.COMPLETED
                                    cordon_p2.completed_at = datetime.utcnow()
                                    cordon_p2.result = {
                                        "backend_executed": True,
                                        "inline": True,
                                        "verified": True,
                                    }
                                    db.flush()
                                    # Change 2: Set draining key so PC._select_burst_pods skips this node
                                    try:
                                        if _redis:
                                            _redis.setex(
                                                f"spot:node:draining:{_wa.cluster_id}:{_p2_node_name}",
                                                3600,  # 1h — cleared by _cleanup_rebalancing_resources
                                                "1",
                                            )
                                    except Exception:
                                        pass
                                    _wa_meta['step_2_cordon'] = datetime.utcnow().isoformat()
                                    _wa_meta['step_2_cordon_verified'] = True
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: "
                                        f"Inline CORDON of {_p2_node_name} succeeded"
                                    )

                                    # ── DRAIN ──
                                    _pods_on_node = _core_inl.list_namespaced_pod(
                                        namespace="",
                                        field_selector=f"spec.nodeName={_p2_node_name}",
                                    ).items
                                    _evictable_inl = []
                                    for _pod_inl in _pods_on_node:
                                        _owner_refs_inl = _pod_inl.metadata.owner_references or []
                                        _is_ds_inl = any(
                                            o.kind == 'DaemonSet' for o in _owner_refs_inl
                                        )
                                        _is_mirror_inl = bool(
                                            (_pod_inl.metadata.annotations or {}).get(
                                                'kubernetes.io/config.mirror'
                                            )
                                        )
                                        if _is_ds_inl or _is_mirror_inl:
                                            continue
                                        _evictable_inl.append(_pod_inl)

                                    _evict_errs_inl = []
                                    _scaled_controllers = []  # P4: track controllers scaled up
                                    _drained_controllers = []  # P6: track controllers with active drains
                                    _frozen_controllers = []   # W7.6: track controllers with frozen HPA/KEDA

                                    # ── P4: Single-replica protective scale-out ────────
                                    # Before evicting, check each controller: if single-replica
                                    # with no PDB, scale up to 2 temporarily.
                                    _p4_apps_v1 = None
                                    try:
                                        _p4_apps_v1 = _k8s_inl.AppsV1Api(_k8s_api_inl)
                                    except Exception:
                                        pass

                                    # Group evictable pods by controller
                                    _ctrl_pods_map = {}
                                    for _ep_inl in _evictable_inl:
                                        _ep_owners = _ep_inl.metadata.owner_references or []
                                        _ep_kind = _ep_owners[0].kind if _ep_owners else ""
                                        _ep_ctrl_name = _ep_owners[0].name if _ep_owners else ""
                                        if _ep_kind == "ReplicaSet":
                                            parts = _ep_ctrl_name.rsplit("-", 1)
                                            if len(parts) == 2 and len(parts[1]) >= 6:
                                                _ep_ctrl_name = parts[0]
                                                _ep_kind = "Deployment"
                                        _ep_ctrl_key = f"{_ep_inl.metadata.namespace}/{_ep_ctrl_name}"
                                        _ctrl_pods_map.setdefault(_ep_ctrl_key, {
                                            "pods": [], "kind": _ep_kind, "name": _ep_ctrl_name,
                                            "namespace": _ep_inl.metadata.namespace,
                                            "tier": 4,  # W6.5: default TIER_4, updated by tier gate
                                        })["pods"].append(_ep_inl)

                                    # P4 + P6 pre-flight per controller
                                    _eviction_blocked_pods = set()
                                    for _ck, _cv in _ctrl_pods_map.items():
                                        # W3.3/W3.4 — Tier gate: read workload tier
                                        # from Redis and skip TIER_0 (system/DaemonSet)
                                        # and TIER_1 (stateful databases) workloads to
                                        # prevent accidental eviction of anchored work.
                                        try:
                                            _tier_key = (
                                                f"spot:workload_tier:{_wa.cluster_id}:{_ck}"
                                            )
                                            _tier_raw = _redis.get(_tier_key)
                                            if _tier_raw:
                                                _tier_data = json.loads(_tier_raw)
                                                _wl_tier = _tier_data.get("tier", 4)
                                                _cv["tier"] = _wl_tier  # W6.5: propagate to drain-min-tier calc
                                                if _wl_tier == 0:
                                                    logger.info(
                                                        f"[auto_rebalancer] Action {_wa.id}: "
                                                        f"TIER_0 gate — skipping {_ck} "
                                                        f"(NEVER_MIGRATE)"
                                                    )
                                                    for _bp in _cv["pods"]:
                                                        _eviction_blocked_pods.add(
                                                            f"{_bp.metadata.namespace}/{_bp.metadata.name}"
                                                        )
                                                    continue
                                                if _wl_tier == 1:
                                                    _policy = _tier_data.get("policy", "")
                                                    logger.warning(
                                                        f"[auto_rebalancer] Action {_wa.id}: "
                                                        f"TIER_1 gate — skipping {_ck} "
                                                        f"(ANCHORED_MANUAL, policy={_policy}). "
                                                        f"Use migrate_to_anchored() instead."
                                                    )
                                                    for _bp in _cv["pods"]:
                                                        _eviction_blocked_pods.add(
                                                            f"{_bp.metadata.namespace}/{_bp.metadata.name}"
                                                        )
                                                    continue
                                                # Low-confidence TIER_4 → treat as TIER_3
                                                if _wl_tier == 4:
                                                    _conf = _tier_data.get("confidence", 1.0)
                                                    if _conf < 0.3:
                                                        logger.debug(
                                                            f"[auto_rebalancer] Action {_wa.id}: "
                                                            f"Low-confidence TIER_4 for {_ck} "
                                                            f"(conf={_conf:.2f}) — treating as TIER_3"
                                                        )
                                                        # Continue but flag for extra caution
                                        except Exception as _tier_err:
                                            logger.debug(
                                                f"[auto_rebalancer] Tier check skipped for "
                                                f"{_ck}: {_tier_err}"
                                            )

                                        # P6: Per-controller concurrent drain check
                                        try:
                                            from backend.pipeline.stage4_decision.eviction_safety import eviction_gate, release_active_drain
                                            _gate_ok, _gate_reason = eviction_gate(
                                                cluster_id=_wa.cluster_id,
                                                namespace=_cv["namespace"],
                                                controller_name=_cv["name"],
                                                redis_client=_redis,
                                            )
                                            if not _gate_ok:
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: Eviction gate "
                                                    f"BLOCKED for {_ck}: {_gate_reason}"
                                                )
                                                for _bp in _cv["pods"]:
                                                    _eviction_blocked_pods.add(
                                                        f"{_bp.metadata.namespace}/{_bp.metadata.name}"
                                                    )
                                                continue
                                            _drained_controllers.append(_ck)
                                        except Exception as _gate_err:
                                            logger.warning(
                                                f"[auto_rebalancer] Action {_wa.id}: Eviction gate "
                                                f"error for {_ck}: {_gate_err} — proceeding (fail-open)"
                                            )

                                        # P4: Single-replica protection
                                        if _p4_apps_v1 and _cv["kind"] == "Deployment":
                                            try:
                                                _p4_profile_key = f"spot:workload_profile:{_wa.cluster_id}:{_ck}"
                                                _p4_raw = _redis.get(_p4_profile_key)
                                                _p4_profile = json.loads(_p4_raw) if _p4_raw else None
                                                if (
                                                    _p4_profile
                                                    and _p4_profile.get("replica_count") == 1
                                                    and not _p4_profile.get("pdb_defined")
                                                ):
                                                    from backend.pipeline.stage4_decision.eviction_safety import protect_single_replica
                                                    _p4_result = protect_single_replica(
                                                        apps_v1=_p4_apps_v1,
                                                        core_v1=_core_inl,
                                                        namespace=_cv["namespace"],
                                                        controller_name=_cv["name"],
                                                        controller_kind=_cv["kind"],
                                                        timeout=120,
                                                    )
                                                    if _p4_result["eviction_blocked"]:
                                                        logger.warning(
                                                            f"[auto_rebalancer] Action {_wa.id}: P4 — "
                                                            f"eviction BLOCKED for {_ck}: {_p4_result['reason']}. "
                                                            f"Marking EVICTION_BLOCKED_NO_CAPACITY."
                                                        )
                                                        _wa_meta.setdefault('eviction_blocked', []).append({
                                                            "controller": _ck,
                                                            "reason": _p4_result["reason"],
                                                        })
                                                        for _bp in _cv["pods"]:
                                                            _eviction_blocked_pods.add(
                                                                f"{_bp.metadata.namespace}/{_bp.metadata.name}"
                                                            )
                                                        continue
                                                    elif _p4_result["scaled"]:
                                                        _scaled_controllers.append({
                                                            "namespace": _cv["namespace"],
                                                            "name": _cv["name"],
                                                            "original_replicas": _p4_result["original_replicas"],
                                                        })
                                            except Exception as _p4_err:
                                                logger.warning(
                                                    f"[auto_rebalancer] Action {_wa.id}: P4 error "
                                                    f"for {_ck}: {_p4_err} — proceeding without protection"
                                                )

                                        # W7.6: Freeze HPA/KEDA autoscaler before evicting this controller.
                                        # Called AFTER P4 protect_single_replica so we freeze at the
                                        # post-scale-out replica count, never at a stale single-replica count.
                                        _w7_post_p4_replicas = max(len(_cv.get("pods", [])), 1)
                                        if any(
                                            f"{_s['namespace']}/{_s['name']}" == _ck
                                            for _s in _scaled_controllers
                                        ):
                                            _w7_post_p4_replicas = 2
                                        try:
                                            from backend.pipeline.stage4_decision.eviction_safety import (
                                                freeze_autoscaler as _w7_freeze,
                                            )
                                            from backend.services.keda_service import (
                                                KedaService as _KS_W7,
                                            )
                                            _ks_w7 = _KS_W7(db, _redis)
                                            _fstate_w7 = _w7_freeze(
                                                apps_v1=_p4_apps_v1,
                                                keda_service=_ks_w7,
                                                namespace=_cv["namespace"],
                                                controller_name=_cv["name"],
                                                controller_kind=_cv["kind"],
                                                current_replicas=_w7_post_p4_replicas,
                                                redis_client=_redis,
                                                cluster_id=_wa.cluster_id,
                                            )
                                            if (
                                                _fstate_w7.get("hpa_frozen")
                                                or _fstate_w7.get("keda_frozen")
                                            ):
                                                _frozen_controllers.append({
                                                    "namespace": _cv["namespace"],
                                                    "name": _cv["name"],
                                                })
                                                logger.info(
                                                    f"[auto_rebalancer] Action {_wa.id}: "
                                                    f"W7.6 froze autoscaler for {_ck}"
                                                )
                                        except Exception as _w7_err:
                                            logger.debug(
                                                f"[auto_rebalancer] Action {_wa.id}: "
                                                f"W7.6 freeze skipped for {_ck}: {_w7_err}"
                                            )

                                    # W6.5: Compute worst (most critical) tier so the post-drain
                                    # readiness grace uses the correct tier-aware soak time.
                                    _drain_min_tier = min(
                                        (v.get("tier", 4) for v in _ctrl_pods_map.values()),
                                        default=4,
                                    )
                                    _wa_meta["drain_tier"] = _drain_min_tier

                                    for _ep_inl in _evictable_inl:
                                        _ep_id = f"{_ep_inl.metadata.namespace}/{_ep_inl.metadata.name}"
                                        if _ep_id in _eviction_blocked_pods:
                                            _evict_errs_inl.append(f"{_ep_id}: EVICTION_BLOCKED")
                                            continue

                                        # P3: Read actual grace period from pod spec
                                        _pod_grace = 60  # default
                                        try:
                                            _pod_spec_grace = _ep_inl.spec.termination_grace_period_seconds
                                            if _pod_spec_grace is not None:
                                                _pod_grace = _pod_spec_grace
                                        except Exception:
                                            pass

                                        # P1: Pre-eviction delay (2s) for kube-proxy propagation
                                        import time as _time_p1
                                        _time_p1.sleep(2)

                                        # W7.9: Annotate pod with karpenter.sh/do-not-disrupt=true
                                        # while it is being migrated (EC-9 mitigation — prevents
                                        # Karpenter node consolidation from racing with the eviction).
                                        if _frozen_controllers:
                                            _ep_owners_w79 = _ep_inl.metadata.owner_references or []
                                            _ep_ctrl_w79 = (
                                                _ep_owners_w79[0].name if _ep_owners_w79 else ""
                                            )
                                            _ep_kind_w79 = (
                                                _ep_owners_w79[0].kind if _ep_owners_w79 else ""
                                            )
                                            if _ep_kind_w79 == "ReplicaSet":
                                                _rs_parts_w79 = _ep_ctrl_w79.rsplit("-", 1)
                                                if (
                                                    len(_rs_parts_w79) == 2
                                                    and len(_rs_parts_w79[1]) >= 6
                                                ):
                                                    _ep_ctrl_w79 = _rs_parts_w79[0]
                                            _ep_ck_w79 = (
                                                f"{_ep_inl.metadata.namespace}/{_ep_ctrl_w79}"
                                            )
                                            if any(
                                                f"{_fc['namespace']}/{_fc['name']}" == _ep_ck_w79
                                                for _fc in _frozen_controllers
                                            ):
                                                try:
                                                    _core_inl.patch_namespaced_pod(
                                                        name=_ep_inl.metadata.name,
                                                        namespace=_ep_inl.metadata.namespace,
                                                        body={"metadata": {"annotations": {
                                                            "karpenter.sh/do-not-disrupt": "true",
                                                        }}},
                                                    )
                                                except Exception:
                                                    pass  # W7.9 annotation is best-effort

                                        try:
                                            _core_inl.create_namespaced_pod_eviction(
                                                name=_ep_inl.metadata.name,
                                                namespace=_ep_inl.metadata.namespace,
                                                body=_k8s_inl.V1Eviction(
                                                    metadata=_k8s_inl.V1ObjectMeta(
                                                        name=_ep_inl.metadata.name,
                                                        namespace=_ep_inl.metadata.namespace,
                                                    ),
                                                    delete_options=_k8s_inl.V1DeleteOptions(
                                                        grace_period_seconds=_pod_grace,
                                                    ),
                                                ),
                                            )
                                        except _k8s_inl.ApiException as _ev_exc:
                                            if _ev_exc.status == 404:
                                                pass  # Pod already gone
                                            else:
                                                _evict_errs_inl.append(
                                                    f"{_ep_inl.metadata.namespace}/"
                                                    f"{_ep_inl.metadata.name}: {_ev_exc.reason}"
                                                )
                                        except Exception as _ev_gen:
                                            _evict_errs_inl.append(str(_ev_gen)[:100])

                                    # P6: Release active drain counters
                                    for _dc in _drained_controllers:
                                        try:
                                            _dc_parts = _dc.split("/", 1)
                                            if len(_dc_parts) == 2:
                                                from backend.pipeline.stage4_decision.eviction_safety import release_active_drain
                                                release_active_drain(
                                                    _wa.cluster_id, _dc_parts[0], _dc_parts[1], _redis
                                                )
                                        except Exception:
                                            pass

                                    # P4: Restore scaled-up controllers back to original replicas
                                    for _sc in _scaled_controllers:
                                        try:
                                            from backend.pipeline.stage4_decision.eviction_safety import restore_single_replica
                                            restore_single_replica(
                                                _p4_apps_v1, _sc["namespace"],
                                                _sc["name"], _sc["original_replicas"],
                                            )
                                        except Exception as _sc_err:
                                            logger.warning(
                                                f"[auto_rebalancer] Action {_wa.id}: P4 restore "
                                                f"failed for {_sc['namespace']}/{_sc['name']}: {_sc_err}"
                                            )

                                    # W7.6: Restore HPA/KEDA autoscalers after drain completes
                                    for _fc in _frozen_controllers:
                                        try:
                                            from backend.pipeline.stage4_decision.eviction_safety import (
                                                restore_autoscaler as _w7_restore,
                                            )
                                            from backend.services.keda_service import (
                                                KedaService as _KS_W7R,
                                            )
                                            _ks_w7r = _KS_W7R(db, _redis)
                                            _w7_restore(
                                                apps_v1=_p4_apps_v1,
                                                keda_service=_ks_w7r,
                                                namespace=_fc["namespace"],
                                                controller_name=_fc["name"],
                                                redis_client=_redis,
                                                cluster_id=_wa.cluster_id,
                                            )
                                            logger.info(
                                                f"[auto_rebalancer] Action {_wa.id}: W7.6 restored "
                                                f"autoscaler for {_fc['namespace']}/{_fc['name']}"
                                            )
                                        except Exception as _w7r_err:
                                            logger.warning(
                                                f"[auto_rebalancer] Action {_wa.id}: W7.6 restore "
                                                f"failed for {_fc['namespace']}/{_fc['name']}: {_w7r_err}"
                                            )

                                    drain_p2.status = _AAS0.COMPLETED
                                    drain_p2.completed_at = datetime.utcnow()
                                    drain_p2.result = {
                                        "backend_executed": True,
                                        "inline": True,
                                        "verified": True,
                                        "pods_evicted": len(_evictable_inl),
                                        "evict_errors": _evict_errs_inl[:5],
                                    }
                                    _wa_meta['step_3_draining_pods'] = datetime.utcnow().isoformat()
                                    _wa_meta['step_3_draining_pods_verified'] = True

                                    # Mark TERMINATE as backend-will-handle
                                    terminate_p2.status = _AAS0.COMPLETED
                                    terminate_p2.completed_at = datetime.utcnow()
                                    terminate_p2.result = {
                                        "backend_will_terminate": True,
                                        "inline": True,
                                    }
                                    db.flush()

                                    _inl_elapsed = (
                                        datetime.utcnow() - _inline_t0
                                    ).total_seconds()
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: "
                                        f"Inline CORDON+DRAIN completed in {_inl_elapsed:.1f}s "
                                        f"({len(_evictable_inl)} pods evicted, "
                                        f"{len(_evict_errs_inl)} errors)"
                                    )
                                    if _evict_errs_inl:
                                        logger.warning(
                                            f"[auto_rebalancer] Action {_wa.id}: "
                                            f"Eviction errors: {_evict_errs_inl[:3]}"
                                        )

                                    _wa_meta['current_step'] = 'draining_pods'
                                    _wa_meta['inline_cordon_drain'] = True
                                    _wa.action_metadata = _wa_meta
                                    flag_modified(_wa, 'action_metadata')
                                    db.commit()
                                    _inline_ok = True
                                else:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: "
                                        f"Inline CORDON+DRAIN skipped — "
                                        f"cluster={'found' if _wa_cluster_inl else 'missing'}, "
                                        f"node_name={_p2_node_name or 'missing'}"
                                    )
                            except Exception as _inl_err:
                                logger.warning(
                                    f"[auto_rebalancer] Action {_wa.id}: "
                                    f"Inline CORDON+DRAIN failed ({type(_inl_err).__name__}: "
                                    f"{_inl_err}) — agent/fallback will handle"
                                )
                            if not _inline_ok:
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: "
                                    f"Waiting for agent fallback (timeout=15s)"
                                )
                        continue  # Proceed to readiness check on next cycle (or wait for agent fallback)

                    # Ghost terminate: node is not in K8s, only TERMINATE action was
                    # created (no CORDON/DRAIN). Skip drain check and readiness wait,
                    # mark readiness as verified so we proceed straight to backend EC2
                    # terminate+decrement.
                    if _wa_meta.get('ghost_terminate'):
                        _wa_meta['readiness_verified'] = True
                        _wa_meta['step_3_draining_pods'] = datetime.utcnow().isoformat()
                        if not _wa_meta.get('post_drain_readiness_started_at'):
                            _wa_meta['post_drain_readiness_started_at'] = datetime.utcnow().isoformat()
                        logger.info(
                            f"[auto_rebalancer] Action {_wa.id}: Ghost terminate — "
                            f"skipping drain/readiness wait, proceeding to EC2 terminate"
                        )

                    # Phase 2 exists — check if drain is done, wait for completion
                    _drain_sa = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
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
                        # W6.5: Tier-aware readiness grace — TIER_1 waits 45s, TIER_4 waits 10s
                        # (90s spot-stabilisation wait already happened before Phase 2)
                        try:
                            from backend.pipeline.stage4_decision.eviction_safety import KUBE_PROXY_SOAK_BY_TIER as _W6_SOAK
                            _READINESS_GRACE_S = _W6_SOAK.get(_wa_meta.get("drain_tier", 4), 20)
                        except Exception:
                            _READINESS_GRACE_S = 20
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

                        # Grace period passed: verify pods actually moved off the drained node
                        # PRIMARY: K8s API direct check (real-time, no stale data)
                        # FALLBACK: PodMetric DB check (if K8s API unavailable)
                        _drained_node_name = _wa_meta.get('target_node_name', '')
                        _drained_inst_rd = _wa_meta.get('instance_id', '')
                        _pods_stuck = False
                        _pods_stuck_count = 0
                        _k8s_check_done = False

                        # Primary: K8s API live pod check on the drained node
                        if _drained_node_name:
                            try:
                                from backend.services.karpenter_service import KarpenterService as _KS_RD
                                from kubernetes import client as _k8s_rd
                                _ks_rd = _KS_RD(db, _redis)
                                _wa_cluster_rd = db.query(Cluster).filter(
                                    Cluster.id == _wa.cluster_id
                                ).first()
                                if _wa_cluster_rd:
                                    _k8s_api_rd = _ks_rd._get_k8s_client(_wa_cluster_rd)
                                    _core_rd = _k8s_rd.CoreV1Api(_k8s_api_rd)
                                    try:
                                        _live_pods = _core_rd.list_pod_for_all_namespaces(
                                            field_selector=f"spec.nodeName={_drained_node_name},status.phase=Running",
                                        ).items
                                        # Exclude DaemonSet pods (they stay on drained nodes)
                                        _non_ds_pods = [
                                            p for p in _live_pods
                                            if not any(
                                                o.kind == 'DaemonSet'
                                                for o in (p.metadata.owner_references or [])
                                            )
                                        ]
                                        _pods_stuck_count = len(_non_ds_pods)
                                        _pods_stuck = _pods_stuck_count > 0
                                        _k8s_check_done = True
                                        if _pods_stuck:
                                            _stuck_names = [
                                                f"{p.metadata.namespace}/{p.metadata.name}"
                                                for p in _non_ds_pods[:5]
                                            ]
                                            logger.info(
                                                f"[auto_rebalancer] Action {_wa.id}: "
                                                f"{_pods_stuck_count} non-DaemonSet pod(s) "
                                                f"still on {_drained_node_name}: {_stuck_names}"
                                            )
                                        else:
                                            logger.info(
                                                f"[auto_rebalancer] Action {_wa.id}: "
                                                f"K8s API confirms 0 workload pods on "
                                                f"{_drained_node_name} — drain verified"
                                            )
                                    except _k8s_rd.ApiException as _k8s_404:
                                        if _k8s_404.status == 404:
                                            # Node already gone from K8s — drain is complete
                                            _pods_stuck = False
                                            _k8s_check_done = True
                                        else:
                                            raise
                            except Exception as _k8s_rd_err:
                                logger.debug(
                                    f"[auto_rebalancer] Action {_wa.id}: K8s pod check "
                                    f"failed ({_k8s_rd_err}), falling back to PodMetric"
                                )

                        # Fallback: PodMetric DB check (stale but better than nothing)
                        if not _k8s_check_done and _drained_inst_rd:
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
                            # Problem 5: Assess WHY pods are stuck before deciding
                            # whether to terminate. Blindly terminating can cause outages
                            # if the cluster lacks capacity to reschedule.
                            _p5_safe_to_terminate = True
                            _p5_reason = "timeout — proceeding"
                            if _k8s_check_done and _drained_node_name:
                                try:
                                    from backend.pipeline.stage4_decision.eviction_safety import (
                                        assess_stuck_pods as _assess_stuck,
                                        should_terminate_with_stuck_pods as _should_term,
                                    )
                                    # Re-fetch stuck pods for assessment
                                    _stuck_pod_objs = [
                                        p for p in _core_rd.list_pod_for_all_namespaces(
                                            field_selector=f"spec.nodeName={_drained_node_name},status.phase=Running",
                                        ).items
                                        if not any(
                                            o.kind == 'DaemonSet'
                                            for o in (p.metadata.owner_references or [])
                                        )
                                    ]
                                    _assessments = _assess_stuck(
                                        _core_rd, _stuck_pod_objs, _wa.cluster_id
                                    )
                                    _p5_safe_to_terminate, _p5_reason = _should_term(_assessments)
                                    _wa_meta['stuck_pod_assessment'] = _assessments[:5]
                                except Exception as _p5_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: P5 stuck pod "
                                        f"assessment failed: {_p5_err} — proceeding with terminate"
                                    )

                            if not _p5_safe_to_terminate:
                                # ABORT: Uncordon old node and fail the action
                                logger.error(
                                    f"[auto_rebalancer] Action {_wa.id}: P5 — {_p5_reason}"
                                )
                                _wa.status = 'failed'
                                _wa.error_message = f"Stuck pods: {_p5_reason}"
                                _wa.completed_at = datetime.utcnow()
                                _wa.duration_seconds = int(
                                    (_wa.completed_at - _wa.started_at).total_seconds()
                                ) if _wa.started_at else 0
                                _wa_meta['current_step'] = 'failed_stuck_pods'
                                _wa_meta['p5_abort_reason'] = _p5_reason
                                # Attempt to uncordon the old node
                                try:
                                    if _wa_cluster_rd and _drained_node_name:
                                        _core_rd.patch_node(
                                            _drained_node_name,
                                            {"spec": {"unschedulable": False}},
                                        )
                                        logger.info(
                                            f"[auto_rebalancer] Action {_wa.id}: Uncordoned "
                                            f"{_drained_node_name} after stuck pod abort"
                                        )
                                except Exception as _uncord_err:
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Uncordon failed: {_uncord_err}"
                                    )
                                _wa.action_metadata = _wa_meta
                                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                                db.commit()
                                continue
                            else:
                                logger.warning(
                                    f"[auto_rebalancer] Action {_wa.id}: pod readiness timeout "
                                    f"({int(_post_drain_elapsed)}s) — P5 assessment: {_p5_reason}. "
                                    f"Proceeding to EC2 terminate."
                                )

                        # Readiness verified (grace period elapsed, no stuck pods or timeout)
                        _wa_meta['readiness_verified'] = True
                        _wa_meta['readiness_verified_at'] = datetime.utcnow().isoformat()
                        _wa.action_metadata = _wa_meta
                        db.commit()

                    # Spot appeared — record and proceed to terminate
                    if _spot_count > 0:
                        _wa_meta['step_4_new_node_joined'] = datetime.utcnow().isoformat()
                        _wa_meta['current_step'] = 'old_node_terminating'
                    else:
                        # CRITICAL FIX: Replacement spot is GONE (Karpenter consolidation
                        # killed it, or it was never provisioned).  DO NOT terminate the
                        # OD node — that would shrink the cluster permanently.
                        # Instead: FAIL the action, attempt to uncordon the OD node
                        # (if it was cordoned), and clean up resources.
                        logger.error(
                            f"[auto_rebalancer] Action {_wa.id}: ABORT — replacement spot "
                            f"node is gone (_spot_count=0) after Phase 2 drain. "
                            f"Refusing to terminate OD node {_wa_instance_id} without "
                            f"a live replacement. Failing action and uncordoning."
                        )
                        _wa.status = 'failed'
                        _wa.error_message = (
                            f"Replacement spot node disappeared (Karpenter consolidation?) "
                            f"after drain completed. OD node {_wa_instance_id} preserved "
                            f"to maintain cluster capacity. Will retry next cycle."
                        )
                        _wa.completed_at = datetime.utcnow()
                        _wa.duration_seconds = int(
                            (_wa.completed_at - _wa.started_at).total_seconds()
                        ) if _wa.started_at else 0
                        _wa_meta['current_step'] = 'failed_spot_gone_before_terminate'
                        _wa.action_metadata = _wa_meta

                        # N7 fix: Block the pool for the full join timeout duration
                        try:
                            _timeout_itype = _wa_meta.get("target_instance_type", "")
                            _timeout_az = _wa_meta.get("target_az", "")
                            if _timeout_itype and _timeout_az and _redis:
                                _block_key = f"spot:launch_blocked:{_wa.cluster_id}:{_timeout_itype}:{_timeout_az}"
                                _block_ttl = _SPOT_WAIT_TIMEOUT_S if _SPOT_WAIT_TIMEOUT_S > 0 else 1800
                                _redis.setex(_block_key, _block_ttl, '1')
                        except Exception:
                            pass

                        # Attempt to uncordon the OD node directly via K8s API
                        # (agent is unreachable so we can't rely on UNCORDON_NODE action)
                        try:
                            _unc_node_name = _wa_meta.get('target_node_name', '')
                            if not _unc_node_name and _wa_instance_id:
                                _unc_inst = db.query(Instance).filter(
                                    Instance.instance_id == _wa_instance_id
                                ).first()
                                if _unc_inst:
                                    _unc_node_name = _unc_inst.node_name or ''
                            if _unc_node_name:
                                from backend.services.karpenter_service import KarpenterService as _KS_UNC
                                _ks_unc = _KS_UNC(db=db)
                                _wa_cluster_unc = db.query(Cluster).filter(
                                    Cluster.id == _wa.cluster_id
                                ).first()
                                if _wa_cluster_unc:
                                    _k8s_api_unc = _ks_unc._get_k8s_client(_wa_cluster_unc)
                                    from kubernetes import client as _k8s_unc
                                    _core_unc = _k8s_unc.CoreV1Api(_k8s_api_unc)
                                    _core_unc.patch_node(
                                        _unc_node_name,
                                        {"spec": {"unschedulable": None}}
                                    )
                                    logger.info(
                                        f"[auto_rebalancer] Action {_wa.id}: UNCORDONED "
                                        f"{_unc_node_name} via backend K8s API (spot gone rollback)"
                                    )
                        except Exception as _unc_err:
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: backend-side uncordon "
                                f"failed: {_unc_err}"
                            )

                        _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                        db.commit()
                        continue

                # Fix 2 + CORDON guard: if ANY Phase 2 action failed, determine which
                # stage failed and execute the appropriate rollback.
                if _failed > 0:
                    # Bug #11 guard (top-level): If TERMINATE_NODE already completed
                    # despite other step failures (parallel agent execution), the OD
                    # node is gone.  Skip destructive rollback (orphan spot terminate).
                    _term_already_done_top = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.TERMINATE_NODE,
                        _AA0.status == _AAS0.COMPLETED,
                    ).count() > 0
                    if _term_already_done_top:
                        logger.warning(
                            f"[auto_rebalancer] Action {_wa.id}: {_failed} steps failed but "
                            f"TERMINATE already completed (parallel agent). "
                            f"Marking partial success — skipping rollback."
                        )
                        _wa.status = 'completed'
                        _wa.error_message = (
                            f"{_failed} Phase 2 step(s) failed but TERMINATE_NODE succeeded. "
                            f"OD node {_wa_instance_id} terminated. Spot replacement active."
                        )
                        _wa.completed_at = datetime.utcnow()
                        _wa.duration_seconds = int(
                            (_wa.completed_at - _wa.started_at).total_seconds()
                        ) if _wa.started_at else 0
                        _wa_meta['current_step'] = 'completed_partial_steps_failed'
                        _wa.action_metadata = _wa_meta
                        _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                        db.commit()
                        continue

                    # ── CORDON failure: drain never ran — full clean rollback ────────
                    _cordon_node_failed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.CORDON_NODE,
                        _AA0.status == _AAS0.FAILED,
                    ).first()
                    # Check whether drain *actually executed* (COMPLETED or FAILED).
                    # EXPIRED/PICKED_UP actions mean the agent died before running drain
                    # (e.g. SELF_CORDON on agent node → agent evicted mid-drain →
                    # DRAIN stays PICKED_UP then EXPIRED). These must NOT block the
                    # cordon-only rollback path — treat them as "drain never ran".
                    _drain_attempted = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
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
                            _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
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
                        _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                        continue

                    # ── DRAIN failure: workloads still on old node — safe rollback ──
                    _drain_node_failed = db.query(_AA0).filter(
                        _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                        _AA0.action_type == _AAT0.DRAIN_NODE,
                        _AA0.status == _AAS0.FAILED,
                    ).first()
                    if _drain_node_failed:
                        # Bug #11 guard: If TERMINATE_NODE already completed (agent ran
                        # steps in parallel before the ordering fix), the OD node is already
                        # gone.  Do NOT rollback — mark action as completed instead.
                        _term_already_done = db.query(_AA0).filter(
                            _AA0.payload.contains({"rebalancing_action_id": str(_wa.id)}),
                            _AA0.action_type == _AAT0.TERMINATE_NODE,
                            _AA0.status == _AAS0.COMPLETED,
                        ).count() > 0
                        if _term_already_done:
                            logger.warning(
                                f"[auto_rebalancer] Action {_wa.id}: DRAIN failed but "
                                f"TERMINATE already completed (parallel execution). "
                                f"Treating as partial success — OD node already gone."
                            )
                            _wa.status = 'completed'
                            _wa.error_message = (
                                f"DRAIN_NODE failed but TERMINATE_NODE succeeded (parallel agent). "
                                f"OD node {_wa_instance_id} terminated. Spot replacement active."
                            )
                            _wa.completed_at = datetime.utcnow()
                            _wa.duration_seconds = int(
                                (_wa.completed_at - _wa.started_at).total_seconds()
                            ) if _wa.started_at else 0
                            _wa_meta['current_step'] = 'completed_partial_drain_skip'
                            _wa.action_metadata = _wa_meta
                            _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                            db.commit()
                            continue

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
                        _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                        continue

                # ── Backend EC2 terminate: drain is done, now kill the instance ──
                # Agent's kubectl delete node removes the K8s object but leaves EC2
                # running. We must terminate via backend's assumed IAM role to ensure
                # the instance is actually gone so Karpenter provisions a spot replacement.
                if _wa_instance_id and _wa_instance_id.startswith("i-") and _failed == 0:
                    # ── SAFETY GATE: Verify replacement spot instance is still alive ──
                    # Another action's rollback may have terminated our shared replacement.
                    # If the replacement is dead, ABORT and rollback instead of orphaning workloads.
                    _pre_term_replacement_id = _wa_meta.get('replacement_spot_instance_id')
                    if _pre_term_replacement_id:
                        _pre_term_inst = db.query(Instance).filter(
                            Instance.instance_id == _pre_term_replacement_id[:20],
                        ).first()
                        _pre_term_dead = False
                        if _pre_term_inst and _pre_term_inst.state in ('terminated', 'shutting-down', 'stopped'):
                            _pre_term_dead = True
                        elif not _pre_term_inst:
                            _pre_term_dead = True  # Instance disappeared from DB
                        if _pre_term_dead:
                            logger.error(
                                f"[auto_rebalancer] Action {_wa.id}: ABORT TERMINATE — "
                                f"replacement spot {_pre_term_replacement_id[:12]} is "
                                f"{'gone from DB' if not _pre_term_inst else _pre_term_inst.state}. "
                                f"Cannot terminate OD node {_wa_instance_id} without a live replacement. "
                                f"Rolling back."
                            )
                            _wa.status = 'failed'
                            _wa.error_message = (
                                f"Replacement spot {_pre_term_replacement_id[:12]} terminated before "
                                f"OD node could be removed. Rolled back to preserve cluster capacity."
                            )
                            _wa.completed_at = datetime.utcnow()
                            _wa.duration_seconds = int(
                                (_wa.completed_at - _wa.started_at).total_seconds()
                            ) if _wa.started_at else 0
                            _wa_meta['current_step'] = 'failed_replacement_dead'
                            _wa.action_metadata = _wa_meta
                            # Queue UNCORDON for the OD node (it was cordoned in Phase 2)
                            try:
                                from backend.models.agent_action import AgentAction as _AA_UNC2, AgentActionType as _AAT_UNC2, AgentActionStatus as _AAS_UNC2
                                _src_node_name = ''
                                _src_inst_db = db.query(Instance).filter(
                                    Instance.instance_id == _wa_instance_id
                                ).first()
                                if _src_inst_db:
                                    _src_node_name = _src_inst_db.node_name or ''
                                if _src_node_name:
                                    _unc_action = _AA_UNC2(
                                        cluster_id=_wa.cluster_id,
                                        action_type=_AAT_UNC2.UNCORDON_NODE,
                                        status=_AAS_UNC2.PENDING,
                                        payload={
                                            "node_name": _src_node_name,
                                            "rebalancing_action_id": str(_wa.id),
                                            "reason": "replacement_spot_terminated_rollback",
                                        },
                                    )
                                    db.add(_unc_action)
                            except Exception as _unc_err:
                                logger.warning(f"[auto_rebalancer] UNCORDON rollback failed: {_unc_err}")
                            _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)
                            db.commit()
                            continue  # Skip to next action

                    try:
                        # Fix 13: Idempotency guard — prevent double-terminate.
                        # If another rebalancer cycle or concurrent worker already
                        # terminated this instance, skip the AWS API call.
                        _idem_key = f"spot:terminating:{_wa_instance_id}"
                        if _redis:
                            _idem_set = _redis.set(_idem_key, str(_wa.id), nx=True, ex=300)
                            if not _idem_set:
                                _idem_owner = _redis.get(_idem_key)
                                _idem_owner_str = (_idem_owner.decode() if isinstance(_idem_owner, bytes) else str(_idem_owner)) if _idem_owner else '?'
                                if _idem_owner_str != str(_wa.id):
                                    logger.warning(
                                        f"[auto_rebalancer] Action {_wa.id}: Fix13 — "
                                        f"{_wa_instance_id} already being terminated by "
                                        f"action {_idem_owner_str} — skipping duplicate terminate"
                                    )
                                    _wa_meta['step_5_old_node_terminated'] = datetime.utcnow().isoformat()
                                    _wa_meta['ec2_terminate_skipped_duplicate'] = True
                                    _wa.action_metadata = _wa_meta
                                    db.commit()
                                    # Fall through to STATUS DECISION below

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
                                getattr(_wa_cluster, 'optimization_settings', None),
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
                                            # FLOOR: Never decrement MinSize below 1 when
                                            # Karpenter is active. Karpenter pods have
                                            # nodeAffinity "karpenter.sh/nodepool DoesNotExist"
                                            # so they MUST run on ASG-managed (non-Karpenter)
                                            # nodes. If MinSize hits 0, ASG scales to 0 OD
                                            # nodes → Karpenter pods go Pending → no more
                                            # spot provisioning.
                                            _min_floor = 1 if _wa_karpenter_active else 0
                                            if _cur_min > _min_floor:
                                                # Set MinSize to anchor floor directly
                                                # (not -1 per action). For a batch of N
                                                # terminates, the first call drops MinSize
                                                # to anchor_count and subsequent calls
                                                # are no-ops.  Example: 6-node cluster,
                                                # 1 anchor, batch of 3:
                                                #   Old: Min 6→5→4→3 (too high)
                                                #   New: Min 6→1 on first terminate
                                                _asg_wa.update_auto_scaling_group(
                                                    AutoScalingGroupName=_stored_asg_for_term,
                                                    MinSize=_min_floor,
                                                )
                                                logger.info(
                                                    f"[auto_rebalancer] Pre-set ASG "
                                                    f"'{_stored_asg_for_term}' MinSize "
                                                    f"{_cur_min} → {_min_floor} (anchor floor) "
                                                    f"before terminate"
                                                )
                                            elif _cur_min <= _min_floor:
                                                logger.info(
                                                    f"[auto_rebalancer] ASG '{_stored_asg_for_term}' "
                                                    f"MinSize={_cur_min} already at floor "
                                                    f"({_min_floor}) — skipping pre-decrement "
                                                    f"(Karpenter needs ≥1 ASG node)"
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
                                        elif _asg_err_code in ('ExpiredTokenException', 'ExpiredToken'):
                                            # Fix 10: STS token expired during long-running action.
                                            # Re-assume role and rebuild ASG client.
                                            logger.warning(
                                                f"[auto_rebalancer] ASG terminate: STS token expired "
                                                f"for {_wa_instance_id} (attempt {_asg_term_attempt + 1}/"
                                                f"{_asg_term_max_retries}) — refreshing credentials"
                                            )
                                            try:
                                                _sts_refresh = _b3wa.client(
                                                    "sts",
                                                    aws_access_key_id=_plat_key,
                                                    aws_secret_access_key=_plat_secret,
                                                    region_name=_plat_region,
                                                )
                                                _refresh_kwargs = {"RoleArn": _wa_role_arn,
                                                                   "RoleSessionName": "spot-rebalancer-terminate-refresh"}
                                                if _wa_ext_id:
                                                    _refresh_kwargs["ExternalId"] = _wa_ext_id
                                                _refresh_creds = _sts_refresh.assume_role(**_refresh_kwargs)['Credentials']
                                                _wa_creds = {
                                                    "aws_access_key_id":     _refresh_creds["AccessKeyId"],
                                                    "aws_secret_access_key": _refresh_creds["SecretAccessKey"],
                                                    "aws_session_token":     _refresh_creds["SessionToken"],
                                                }
                                                _asg_wa = _b3wa.client("autoscaling",
                                                                       region_name=_term_region, **_wa_creds)
                                            except Exception as _refresh_err:
                                                logger.error(
                                                    f"[auto_rebalancer] STS refresh failed: {_refresh_err}"
                                                )
                                            import time as _t_asg_exp
                                            _t_asg_exp.sleep(1)
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

                                # FLOOR GUARD: After terminate+decrement, ensure ASG
                                # DesiredCapacity never drops below 1 when Karpenter is
                                # active.  Karpenter pods have nodeAffinity requiring
                                # non-Karpenter nodes (karpenter.sh/nodepool DoesNotExist),
                                # so at least 1 ASG node must always exist.
                                if _should_decrement and _wa_karpenter_active:
                                    try:
                                        _post_desc = _asg_wa.describe_auto_scaling_groups(
                                            AutoScalingGroupNames=[_stored_asg_for_term]
                                        )['AutoScalingGroups']
                                        if _post_desc:
                                            _post_desired = _post_desc[0].get('DesiredCapacity', 0)
                                            _post_min = _post_desc[0].get('MinSize', 0)
                                            if _post_desired < 1 or _post_min < 1:
                                                _new_min = max(_post_min, 1)
                                                _new_desired = max(_post_desired, 1)
                                                _asg_wa.update_auto_scaling_group(
                                                    AutoScalingGroupName=_stored_asg_for_term,
                                                    MinSize=_new_min,
                                                    DesiredCapacity=_new_desired,
                                                )
                                                logger.warning(
                                                    f"[auto_rebalancer] ASG floor guard: restored "
                                                    f"'{_stored_asg_for_term}' Min={_new_min} "
                                                    f"Desired={_new_desired} (was Min={_post_min} "
                                                    f"Desired={_post_desired}) — Karpenter needs "
                                                    f"≥1 ASG node"
                                                )
                                    except Exception as _floor_err:
                                        logger.warning(
                                            f"[auto_rebalancer] ASG floor guard check failed: {_floor_err}"
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

                            # ── Verification: confirm EC2 instance is actually terminated/shutting-down ──
                            _term_verified = False
                            try:
                                import time as _time_verify
                                _time_verify.sleep(2)  # Brief pause for AWS state propagation
                                _verify_ec2 = _b3wa.client("ec2", region_name=_term_region, **_wa_creds)
                                _verify_resp = _verify_ec2.describe_instances(InstanceIds=[_wa_instance_id])
                                for _vr in _verify_resp.get("Reservations", []):
                                    for _vi in _vr.get("Instances", []):
                                        _vi_state = _vi.get("State", {}).get("Name", "")
                                        if _vi_state in ("terminated", "shutting-down"):
                                            _term_verified = True
                                        else:
                                            logger.warning(
                                                f"[auto_rebalancer] EC2 terminate verification: "
                                                f"{_wa_instance_id} state={_vi_state} (expected terminated/shutting-down)"
                                            )
                                _wa_meta['step_5_verified'] = _term_verified
                                if _term_verified:
                                    logger.info(
                                        f"[auto_rebalancer] VERIFIED: {_wa_instance_id} is terminated/shutting-down"
                                    )
                            except Exception as _verify_err:
                                logger.warning(f"[auto_rebalancer] EC2 terminate verification failed: {_verify_err}")
                                _wa_meta['step_5_verified'] = False

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
                                # Fix 14: Set recently_terminated key so aws_sync does
                                # NOT flip this instance back to 'running' during the
                                # 1-10 s AWS state propagation window.
                                try:
                                    _redis.setex(
                                        f"spot:recently_terminated:{_wa_instance_id}",
                                        120,  # 2 min TTL — covers AWS propagation
                                        "1"
                                    )
                                except Exception:
                                    pass
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
                    # ── Step journal: all Phase 2 steps succeeded ─────────────
                    _advance_action_step(db, _wa, ACTION_STEP_DONE)
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

                    # Set 24h cooldown NOW (on success) — prevents the terminated
                    # instance ID from being retried while it lingers in the DB.
                    _wa_inst_id_success = _wa_meta.get("instance_id", "") or (_wa.source_instance_id or "")
                    if _wa_inst_id_success and _redis:
                        try:
                            _redis.setex(f"spot:rebalanced:instance:{_wa_inst_id_success}", 86400, "1")
                        except Exception:
                            pass

                    # Fix #14 (success path): reset failure counter so the next OD→spot
                    # migration on this instance starts from 5-min backoff, not escalated.
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
                        # Remove annotation directly via backend K8s API (agent may be unreachable)
                        try:
                            from backend.services.karpenter_service import KarpenterService as _KS_DNDREM
                            _ks_dndrem = _KS_DNDREM(db=db)
                            _wa_cluster_rem = db.query(Cluster).filter(
                                Cluster.id == _wa.cluster_id
                            ).first()
                            if _wa_cluster_rem:
                                _k8s_api_rem = _ks_dndrem._get_k8s_client(_wa_cluster_rem)
                                from kubernetes import client as _k8s_rem
                                _core_rem = _k8s_rem.CoreV1Api(_k8s_api_rem)
                                import json as _json_rem
                                _core_rem.patch_node(
                                    _replacement_node_name,
                                    [{"op": "remove", "path": "/metadata/annotations/karpenter.sh~1do-not-disrupt"}],
                                    _content_type='application/json-patch+json'
                                )
                                logger.info(
                                    f"[auto_rebalancer] Action {_wa.id}: Removed do-not-disrupt "
                                    f"from {_replacement_node_name} via backend K8s API"
                                )
                        except Exception as _deann_err:
                            logger.warning(
                                f"[auto_rebalancer] Failed to remove do-not-disrupt: {_deann_err}"
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
                            _region = (_wa_cluster.region if _wa_cluster else None) or "ap-south-1"
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

                # Full resource cleanup: semaphore DECR, node lock, trigger pod, PENDING actions.
                # Replaces the inline BUG-7 DECR — now covers all resources in one call.
                _cleanup_rebalancing_resources(_wa, _wa_meta, _redis, db)

                # ── CRITICAL: Commit action status + cleanup NOW, before any
                # non-essential post-processing (pool reputation, etc.) that may
                # corrupt the DB session via missing tables / schema errors.
                try:
                    db.commit()
                    logger.info(f"[auto_rebalancer] Action {_wa.id} status committed to DB")
                except Exception as _commit_err:
                    logger.error(f"[auto_rebalancer] Failed to commit action {_wa.id}: {_commit_err}")
                    try:
                        db.rollback()
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
                        from backend.pipeline.stage4_decision.engine import DecisionEngineService
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
                                    _rlf_region = (_wa_cluster.region if _wa_cluster else None) or "ap-south-1"
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
                        _rep_region = (_wa_cluster.region if _wa_cluster else None) or "ap-south-1"
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
                    # Recover the DB session if the error invalidated it
                    # (e.g. psycopg2.errors.UndefinedTable corrupts the session)
                    try:
                        db.rollback()
                    except Exception:
                        pass

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

            # ── AGENT DISCONNECTED GATE ──────────────────────────────────────
            # Phase 2 (CORDON→DRAIN→TERMINATE) requires the in-cluster agent.
            # If the agent has been offline for >5 min, skip the cluster entirely
            # to avoid creating actions that immediately fail with AGENT_WENT_OFFLINE,
            # which then trigger 2h cooldowns and permanently block all nodes.
            try:
                from backend.models.cluster import ClusterStatus as _CS_agent_gate
                if (cluster.status == _CS_agent_gate.DISCONNECTED
                    and getattr(cluster, 'is_agentless', 'N') != 'Y'):
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name} agent DISCONNECTED "
                        f"(last heartbeat: {cluster.last_heartbeat}) — skipping until agent reconnects"
                    )
                    # P5: surface agent-disconnected as degraded health state
                    try:
                        if _redis:
                            import json as _hj_ag
                            _redis.setex(
                                f"spot:cluster_health:{cluster.id}",
                                300,
                                _hj_ag.dumps({
                                    "state": "degraded",
                                    "reason": "agent_disconnected",
                                    "detail": (
                                        f"Agent DISCONNECTED since {cluster.last_heartbeat}. "
                                        f"No rebalancing until agent reconnects."
                                    ),
                                    "cluster_name": cluster.name,
                                })
                            )
                    except Exception:
                        pass
                    continue
            except Exception:
                pass

            # ── ONBOARDING PHASE GATE ─────────────────────────────────────────
            # shadow   → no optimization at all
            # takeover → _run_takeover_step() runs; normal rebalancing skipped
            # managed  → full optimization loop (fall through)
            try:
                _ob_phase = getattr(cluster, 'onboarding_phase', 'managed') or 'managed'
                if _ob_phase == 'shadow':
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name} onboarding_phase=shadow "
                        f"— skipping optimization"
                    )
                    if _redis:
                        _record_skip(_redis, cluster.id, "onboarding_shadow")
                    continue
                if _ob_phase == 'takeover':
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name} onboarding_phase=takeover "
                        f"— running takeover step only"
                    )
                    try:
                        _run_takeover_step(cluster.id, db, _redis)
                    except Exception as _tko_exc:
                        logger.warning(
                            f"[auto_rebalancer] _run_takeover_step failed cluster={cluster.name}: {_tko_exc}"
                        )
                    continue
            except Exception:
                pass  # fail open — unknown phase does not block AR

            # ── KARPENTER INSTALLED GATE ─────────────────────────────────────
            # karpenter_mode=None → Karpenter not installed → view-only mode.
            # AR must not create rebalancing actions until Karpenter is detected,
            # because CORDON/DRAIN/TERMINATE assumes Karpenter-managed nodes.
            try:
                if getattr(cluster, 'karpenter_mode', None) is None:
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name} karpenter_mode=None "
                        f"— view-only mode, skipping rebalancing"
                    )
                    if _redis:
                        _record_skip(_redis, cluster.id, "karpenter_not_installed")
                    continue
            except Exception:
                pass  # fail open

            # ── CROSS-ENGINE CLUSTER MUTEX ───────────────────────────────────
            # PlacementController acquires spot:cluster_mutex:{cluster_id} (a
            # HeartbeatLock, TTL 60 s) when running its 5-minute cycle.
            # auto_rebalancer must NOT acquire the same mutex — it only performs a
            # read-only GET to detect whether PC is holding it.  If held, skip this
            # cluster for the current 15-second beat; PC will release within 60 s.
            try:
                _mutex_key = f"spot:cluster_mutex:{cluster.id}"
                _mutex_holder = _redis.get(_mutex_key) if _redis else None
                if _mutex_holder:
                    logger.info(
                        f"[auto_rebalancer] Cluster {cluster.name}: cluster mutex held by "
                        f"{_mutex_holder.decode() if isinstance(_mutex_holder, bytes) else _mutex_holder}"
                        f" — skipping this cycle to avoid race condition"
                    )
                    if _redis:
                        _record_skip(_redis, cluster.id, "cluster_mutex_contention")
                    continue
            except Exception:
                pass

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
                # Always record the last-run timestamp so the frontend countdown
                # endpoint can compute an accurate `next_check_at`.
                if _redis:
                    _redis.set(
                        f"spot:last_run_ts:{cluster.id}",
                        str(int(datetime.utcnow().timestamp())),
                        ex=_check_interval * 3,  # auto-cleanup
                    )
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

            # ── STALE POOL RANKINGS WARNING + SELF-HEAL (Issue 9 + P-M4) ────
            # If global_pool_rankings:{region} is absent from Redis (cold cache,
            # Redis restart, or TTL expiry between hourly rebuilds), trigger an
            # immediate async rebuild rather than blocking the entire region for
            # up to 1 hour. Skip this cluster THIS CYCLE only (cache will be
            # available within ~5-10s on next cycle). This replaces the old
            # approach that blocked all clusters region-wide for 1 hour.
            _pm4_skip_cluster = False
            try:
                if _redis:
                    _rank_region = cluster.region or 'us-east-1'
                    _rank_key = f'global_pool_rankings:{_rank_region}'
                    _rank_ttl = _redis.ttl(_rank_key)
                    if _rank_ttl is None or _rank_ttl == -2:  # key does not exist
                        _stale_warn_key = f'ranking_stale_warned:{_rank_region}'
                        # BUG-3 fix: atomic set — only one worker logs the CRITICAL
                        if _redis.set(_stale_warn_key, '1', nx=True, ex=60):
                            logger.warning(
                                '[auto_rebalancer] Pool rankings cache absent for region %s. '
                                'Triggering immediate rebuild. Skipping THIS cycle only.',
                                _rank_region
                            )
                            # Self-heal: trigger immediate cache rebuild instead of
                            # waiting up to 1 hour for the scheduled task.
                            try:
                                from backend.workers.app import app as _celery_rebuild
                                _celery_rebuild.send_task(
                                    'build_global_pool_cache',
                                    args=[_rank_region],
                                    countdown=0,
                                    queue='celery',
                                )
                                logger.info(
                                    '[auto_rebalancer] Triggered immediate pool rankings '
                                    'rebuild for region %s', _rank_region
                                )
                            except Exception as _rebuild_err:
                                logger.warning(
                                    '[auto_rebalancer] Failed to trigger pool rankings '
                                    'rebuild: %s', _rebuild_err
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

            # K8s-node fallback: clean up stale records when AWS credentials are absent
            try:
                _sync_instance_state_from_k8s(db, cluster)
            except Exception as _k8s_sync_err:
                logger.debug(f"[auto_rebalancer] K8s sync skipped for {cluster.name}: {_k8s_sync_err}")

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
            # During initial OD→Spot batch rebalance, multiple agent actions are
            # expected to be in-flight simultaneously (one per batch node). Only
            # block for post-migration (S2S) sequential mode where one-at-a-time
            # is correct.
            # Early OD count for the gate check (full _od_count computed later
            # for the last-node guard — this is a lightweight pre-check).
            try:
                _od_count_for_gate = int(db.execute(
                    "SELECT COUNT(*) FROM instances "
                    "WHERE cluster_id = :cid AND state = 'running' "
                    "AND instance_id LIKE 'i-%%' "
                    "AND lifecycle NOT IN ('spot', 'SPOT')",
                    {"cid": cluster.id}
                ).scalar() or 0)
            except Exception:
                _od_count_for_gate = 0
            _is_initial_for_gate = (
                _od_count_for_gate > 0
                and not getattr(cluster, 'managed_node_group_deleted', False)
            )
            if active_agent_actions > 0 and not _is_initial_for_gate:
                logger.info(
                    f"[auto_rebalancer] Skipping cluster {cluster.name}: "
                    f"{active_agent_actions} AgentAction(s) still in-flight — waiting for completion (S2S sequential mode)"
                )
                try:
                    if _redis:
                        _record_skip(_redis, cluster.id, f'agent_actions_in_flight:{active_agent_actions}')
                except Exception:
                    pass
                continue
            elif active_agent_actions > 0:
                logger.info(
                    f"[auto_rebalancer] Cluster {cluster.name}: {active_agent_actions} AgentAction(s) "
                    f"in-flight — allowed (initial OD→Spot batch mode, {_od_count_for_gate} OD nodes)"
                )

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
                    # Karpenter path: continue is NOT called — fall through to
                    # normal rebalancing so new actions can be created once a
                    # spot node appears.  The old unconditional `continue` blocked
                    # single-node Karpenter clusters permanently.

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
                        from sqlalchemy import text as _sa_text
                        _cd_od = db.execute(
                            _sa_text("SELECT COUNT(*) FROM instances WHERE cluster_id = :cid "
                            "AND state = 'running' AND lifecycle::text NOT IN ('spot', 'SPOT')"),
                            {"cid": str(cluster.id)}
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
                            # P5: surface degraded state — dashboard can read this key
                            try:
                                import json as _hj
                                _redis.setex(
                                    f"spot:cluster_health:{cluster.id}",
                                    300,  # 5-min TTL — clears automatically on recovery
                                    _hj.dumps({
                                        "state": "degraded",
                                        "reason": "classification_stalled",
                                        "detail": (
                                            f"WorkloadInspector cache absent for {_miss_streak} cycles "
                                            f"(>{_miss_streak * 15}s). APScheduler job may be stalled."
                                        ),
                                        "since": _miss_streak,
                                        "cluster_name": cluster.name,
                                    })
                                )
                            except Exception:
                                pass
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
                        # Fix #10: Obtain K8s client via KarpenterService (STS AssumeRole path)
                        # so WorkloadInspector can actually query K8s API from the celery worker.
                        _wi_k8s = None
                        try:
                            from backend.services.karpenter_service import KarpenterService as _KS_WI
                            _ks_wi = _KS_WI(db, _redis)
                            _wi_k8s = _ks_wi._get_k8s_client(cluster)
                        except Exception as _wi_k8s_err:
                            logger.warning(
                                f"[auto_rebalancer] WorkloadInspector K8s client failed for "
                                f"{cluster.name}: {_wi_k8s_err}"
                            )
                        _wi_svc = _WI(_redis, k8s_client=_wi_k8s)
                        _wi_result = _wi_svc.scan_cluster(cluster.id)
                        if _wi_result:
                            # E1: Also build workload profiles inline so the
                            # drain step can read per-controller fragility.
                            try:
                                _wi_svc.build_all_profiles_for_cluster(cluster.id)
                            except Exception as _wp_err:
                                logger.warning(
                                    f"[auto_rebalancer] Inline workload profile build "
                                    f"failed for {cluster.name}: {_wp_err}"
                                )
                            _wi_raw = _redis.get(_wi_cache_key)  # re-read after scan
                            logger.info(
                                f"[auto_rebalancer] WorkloadInspector inline classification "
                                f"complete for {cluster.name}: {len(_wi_result)} nodes classified."
                            )
                        else:
                            raise ValueError("scan_cluster returned empty result")
                    except Exception as _wi_inline_err:
                        # K8s unreachable or scan failed.
                        #
                        # For INITIAL OD→Spot migration: default to STATELESS_ELIGIBLE.
                        # OD→Spot replaces the node with an identical workload on spot —
                        # even stateful workloads are safe because Karpenter provisions
                        # a replacement BEFORE we drain the source. Blocking here would
                        # permanently prevent rebalancing whenever K8s API is flaky.
                        #
                        # For S2S (post-migration): default to STATEFUL (safe).
                        # S2S migrations between spot pools are optional optimizations
                        # and shouldn't risk stateful workloads.
                        _is_initial_for_wi = (
                            len(on_demand_instances) > 0
                            and not getattr(cluster, 'managed_node_group_deleted', False)
                        )
                        if _is_initial_for_wi:
                            logger.warning(
                                f"[auto_rebalancer] Inline WorkloadInspector failed for "
                                f"{cluster.name}: {_wi_inline_err}. "
                                f"Initial OD→Spot migration — defaulting to STATELESS_ELIGIBLE "
                                f"(safe: replacement provisioned before drain)."
                            )
                            import json as _json_wi_fb
                            _default_classification = {
                                inst.node_name: "STATELESS_ELIGIBLE"
                                for inst in on_demand_instances if inst.node_name
                            }
                        else:
                            logger.warning(
                                f"[auto_rebalancer] Inline WorkloadInspector failed for "
                                f"{cluster.name}: {_wi_inline_err}. "
                                f"S2S mode — defaulting all nodes to STATEFUL (safe). "
                                f"Rebalancing paused until WorkloadInspector recovers."
                            )
                            import json as _json_wi_fb
                            _default_classification = {
                                inst.node_name: "STATEFUL"
                                for inst in on_demand_instances if inst.node_name
                            }
                        # Short cache (60s) so we retry quickly once K8s is reachable
                        _redis.setex(_wi_cache_key, 60, _json_wi_fb.dumps(_default_classification))
                        _wi_raw = _redis.get(_wi_cache_key)
                else:
                    # Issue 7: Cache hit — reset miss streak counter and health state.
                    try:
                        if _redis:
                            _redis.delete(f'class_miss_streak:{cluster.id}')
                            # P5: clear degraded state if it was set for classification_stalled
                            try:
                                import json as _hj_clr
                                _cur_health_raw = _redis.get(f"spot:cluster_health:{cluster.id}")
                                if _cur_health_raw:
                                    _cur_health = _hj_clr.loads(_cur_health_raw)
                                    if _cur_health.get('reason') == 'classification_stalled':
                                        _redis.delete(f"spot:cluster_health:{cluster.id}")
                            except Exception:
                                pass
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

            # ── WIE v4.3 ENRICHMENT — TIERED ENFORCEMENT ────────────────────────
            # Phase 1 (HARD BLOCK — always active):
            #   TIER_0 workloads, singleton stateful (replica=1 + no PDB),
            #   and PVC-bound workloads are ALWAYS blocked regardless of flag.
            #   These represent data-loss risk if migrated to spot.
            # Phase 2 (SOFT ENFORCEMENT — observation only for now):
            #   Silver/Bronze workloads log disagreements but do not block.
            #   Enable _WIE_ENFORCEMENT_ENABLED after ≥14 days of observation
            #   with disagreement rate < 10%.
            _WIE_ENFORCEMENT_ENABLED = False  # Set True after ≥14 days observation + disagreement rate <10%

            # Tiers that are ALWAYS hard-blocked regardless of _WIE_ENFORCEMENT_ENABLED
            _WIE_HARD_BLOCK_TIERS = {"Tier0", "TIER_0", "tier0", "Platinum"}
            # Signals that indicate data-loss risk even without tier classification
            _WIE_HARD_BLOCK_SIGNALS = {"singleton_stateful", "pvc_bound", "has_pvc"}

            try:
                _wie_json = None
                import json as _wie_json_mod
                for _od_inst in list(on_demand_instances):
                    if not _od_inst.node_name:
                        continue
                    # Get pods on this node from workload inspector cache
                    _node_pods_key = f"spot:wie:node_pods:{cluster.id}:{_od_inst.node_name}"
                    # WIE enrichment: check each workload on this node
                    # We query the WIE classification cache per known namespace/controller combos
                    # from the workload tier cache (same tier key pattern)
                    _wie_blocks = []
                    _wie_hard_blocks = []
                    _wie_disagreements = []
                    _tier_prefix = f"spot:workload_tier:{cluster.id}:"
                    # Use the WIE classification cache if available for known workloads
                    # (best-effort — we only check workloads already in the tier cache)
                    for _cached_key in (_redis.scan_iter(f"spot:wie:classification:{cluster.id}:*", count=50) if _redis else []):
                        try:
                            _wie_raw_item = _redis.get(_cached_key)
                            if not _wie_raw_item:
                                continue
                            _wie_item = _wie_json_mod.loads(_wie_raw_item)
                            _wie_ns = _wie_item.get("namespace", "")
                            _wie_ctrl = _wie_item.get("name", "")
                            _wie_confidence = _wie_item.get("confidence_state", "")
                            _wie_spot_friendly = _wie_item.get("spot_friendly", True)
                            _wie_tier = _wie_item.get("tier", "Bronze")
                            _wie_signals = set(_wie_item.get("risk_signals", []) or [])

                            # Check disagreement with old classifier
                            _old_tier_key = f"spot:workload_tier:{cluster.id}:{_wie_ns}/{_wie_ctrl}"
                            _old_tier_raw = _redis.get(_old_tier_key) if _redis else None
                            if _old_tier_raw:
                                try:
                                    _old_tier_data = _wie_json_mod.loads(_old_tier_raw)
                                    _old_spot_eligible = _old_tier_data.get("tier", 99) >= 2
                                    if _old_spot_eligible != _wie_spot_friendly and _wie_confidence == "CONFIRMED":
                                        _wie_disagreements.append(
                                            f"{_wie_ns}/{_wie_ctrl}: old_spot={_old_spot_eligible} "
                                            f"wie_spot={_wie_spot_friendly} tier={_wie_tier}"
                                        )
                                except Exception:
                                    pass

                            # ── HARD BLOCK: TIER_0 / singleton stateful / PVC ──────────
                            # These are always enforced — data-loss risk regardless of flag.
                            _is_hard_block = (
                                _wie_tier in _WIE_HARD_BLOCK_TIERS
                                or bool(_wie_signals & _WIE_HARD_BLOCK_SIGNALS)
                                or (
                                    _wie_confidence == "CONFIRMED"
                                    and not _wie_spot_friendly
                                    and _wie_tier in _WIE_HARD_BLOCK_TIERS
                                )
                            )
                            if _is_hard_block:
                                _wie_hard_blocks.append(
                                    f"{_wie_ns}/{_wie_ctrl} (tier={_wie_tier}, signals={list(_wie_signals)[:2]})"
                                )
                            # Soft block check (only for CONFIRMED + not spot_friendly)
                            elif _wie_confidence == "CONFIRMED" and not _wie_spot_friendly:
                                _wie_blocks.append(f"{_wie_ns}/{_wie_ctrl} (tier={_wie_tier})")
                        except Exception:
                            continue

                    if _wie_disagreements:
                        logger.warning(
                            f"[auto_rebalancer] WIE DISAGREEMENTS for cluster {cluster.name} "
                            f"({len(_wie_disagreements)} workloads): " + "; ".join(_wie_disagreements[:5])
                        )

                    if _wie_hard_blocks:
                        # Always enforce — TIER_0/singleton/PVC regardless of observation flag
                        logger.warning(
                            f"[auto_rebalancer] WIE HARD BLOCK (data-loss risk) for node "
                            f"{_od_inst.node_name} in {cluster.name}: {'; '.join(_wie_hard_blocks[:3])}"
                        )
                        on_demand_instances = [
                            i for i in on_demand_instances if i.node_name != _od_inst.node_name
                        ]
                    elif _wie_blocks:
                        if _WIE_ENFORCEMENT_ENABLED:
                            logger.info(
                                f"[auto_rebalancer] WIE blocks spot migration for node "
                                f"{_od_inst.node_name} in {cluster.name}: {'; '.join(_wie_blocks[:3])}"
                            )
                            on_demand_instances = [
                                i for i in on_demand_instances if i.node_name != _od_inst.node_name
                            ]
                        else:
                            logger.info(
                                f"[auto_rebalancer] WIE (observation): would block {_od_inst.node_name} "
                                f"in {cluster.name} for: {'; '.join(_wie_blocks[:3])} "
                                f"[enforcement disabled]"
                            )
            except Exception as _wie_err:
                logger.debug(f"[auto_rebalancer] WIE enrichment skipped: {_wie_err}")

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

            # ── STABLE NODE EXCLUSION ──────────────────────────────────────────
            # When Karpenter is active, one ASG-managed OD node MUST remain for
            # Karpenter system pods (nodeAffinity: karpenter.sh/nodepool DoesNotExist).
            # The ASG floor guard (Phase 14) prevents Min<1, but the rebalancer
            # still sees the floor node as eligible and creates actions for it in
            # an infinite loop.  Remove it from candidates entirely.
            if _karpenter_active and on_demand_instances:
                import json as _json_sn
                _stable_node_key = f"spot:stable_node:{cluster.id}"
                _stable_node = None

                # 1. Re-use previously designated stable node if still present
                try:
                    _cached_sn = _redis.get(_stable_node_key) if _redis else None
                    if _cached_sn:
                        _cached_sn_data = _json_sn.loads(_cached_sn)
                        _cached_sn_id = _cached_sn_data.get('instance_id')
                        for _sn_inst in on_demand_instances:
                            if _sn_inst.instance_id == _cached_sn_id:
                                _stable_node = _sn_inst
                                break
                except Exception:
                    pass

                # 2. Pick a new stable node — prefer the one hosting Karpenter pods
                if not _stable_node:
                    try:
                        from backend.services.karpenter_service import KarpenterService as _KS_SN
                        _ks_sn = _KS_SN(db, _redis)
                        _sn_k8s = _ks_sn._get_k8s_client(cluster)
                        from kubernetes import client as _k8s_sn
                        _sn_v1 = _k8s_sn.CoreV1Api(_sn_k8s)
                        _karp_pods = _sn_v1.list_namespaced_pod('karpenter')
                        _karp_node_names = set()
                        for _kp in _karp_pods.items:
                            if _kp.spec.node_name:
                                _karp_node_names.add(_kp.spec.node_name)
                        for _sn_inst in on_demand_instances:
                            if _sn_inst.node_name in _karp_node_names:
                                _stable_node = _sn_inst
                                break
                    except Exception as _sn_err:
                        logger.debug(
                            f"[auto_rebalancer] Karpenter pod lookup for stable node: {_sn_err}"
                        )

                # 3. Fallback: first OD instance (oldest)
                if not _stable_node:
                    _stable_node = on_demand_instances[0]

                # Cache selection (10 min TTL)
                try:
                    _redis.setex(_stable_node_key, 600, _json_sn.dumps({
                        "instance_id": _stable_node.instance_id,
                        "node_name": _stable_node.node_name,
                        "instance_type": _stable_node.instance_type,
                    }))
                except Exception:
                    pass

                # Remove from candidates
                on_demand_instances = [
                    inst for inst in on_demand_instances
                    if inst.instance_id != _stable_node.instance_id
                ]
                logger.info(
                    f"[auto_rebalancer] Stable node for {cluster.name}: "
                    f"{_stable_node.instance_id} ({_stable_node.node_name}) — "
                    f"excluded from rebalancing. {len(on_demand_instances)} OD nodes remain"
                )

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
                # trigger S2S only on risk-threshold breaches — UNLESS
                # diversify_pools is enabled, in which case diversify and
                # opportunistic S2S checks must also run.
                _s2s_risk_only_mode = not _diversify_s2s
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

                    # B12: Check 0 settle guard — skip nodes that recently completed an S2S move.
                    # Check 2 (risk_threshold) bypasses this — real risk still acts immediately.
                    _s2s_settled_key = f"s2s_settled:{_sp_inst.instance_id}"
                    try:
                        if _redis and _redis.exists(_s2s_settled_key):
                            logger.debug(
                                f"[auto_rebalancer] S2S Check 0 skipped: "
                                f"{_sp_inst.instance_id} is in 4h settle window after recent S2S"
                            )
                            # Note: only Check 0 (opportunistic) is blocked here.
                            # Check 1 (diversify) and Check 2 (risk) proceed normally below.
                            _skip_check0 = True
                        else:
                            _skip_check0 = False
                    except Exception:
                        _skip_check0 = False

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
                    if not _s2s_trigger_reason and _sp_inst.instance_type and not _s2s_risk_only_mode and not _skip_check0:
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
                                        # B11: minimum tenure check — target pool must have been
                                        # at current risk level for ≥ 2 scoring cycles (~1 h).
                                        _tenure_ok = False
                                        try:
                                            _tgt_pk = f"{_opp_better.pool.instance_type}:{_opp_better.pool.az}"
                                            _ps_raw = _redis.get(f"pool_stable_since:{_tgt_pk}")
                                            if _ps_raw:
                                                from datetime import datetime as _dt_b11, timezone as _tz_b11
                                                _stable_since = _dt_b11.fromisoformat(
                                                    _ps_raw.decode() if isinstance(_ps_raw, bytes) else _ps_raw
                                                )
                                                _stable_since = _stable_since.replace(
                                                    tzinfo=_tz_b11.utc
                                                ) if _stable_since.tzinfo is None else _stable_since
                                                _age_s = (_dt_b11.now(_tz_b11.utc) - _stable_since).total_seconds()
                                                _tenure_ok = _age_s >= 3600
                                        except Exception:
                                            pass
                                        if not _tenure_ok:
                                            logger.debug(
                                                f"[auto_rebalancer] S2S Check 0 skipped: "
                                                f"{_opp_better.pool.instance_type}:{_opp_better.pool.az} "
                                                f"has not held stable risk for ≥1 h (tenure guard)"
                                            )
                                        else:
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
                        # B12: write settle key on source node so Check 0 backs off for 4 h
                        try:
                            if _redis:
                                _redis.setex(f"s2s_settled:{_sp_inst.instance_id}", 14400, "1")
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
                # AR's in-flight RebalancingActions
                _ar_active = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cluster.id,
                    RebalancingAction.status.in_(['pending', 'in_progress', 'waiting_agent']),
                ).count()
                # PC's in-flight EVICT_POD AgentActions (cross-engine batch visibility)
                try:
                    from backend.models.agent_action import AgentAction as _AA, AgentActionStatus as _AAS
                    _pc_active = db.query(_AA).filter(
                        _AA.cluster_id == cluster.id,
                        _AA.status.in_([_AAS.PENDING, _AAS.PICKED_UP]),
                    ).count()
                except Exception:
                    _pc_active = 0
                _actual_active = _ar_active + _pc_active
                _sem_stale = int(_redis.get(_sem_reconcile_key) or 0)
                if _sem_stale != _actual_active:
                    logger.info(
                        f"[auto_rebalancer] Semaphore reconciliation: {cluster.name} "
                        f"redis={_sem_stale} actual={_actual_active} "
                        f"(ar={_ar_active} pc={_pc_active}) — correcting"
                    )
                    _redis.set(_sem_reconcile_key, _actual_active, ex=300)
            except Exception:
                pass

            # ── BATCH SIZE LIMITING (PDB-aware) ─────────────────────────────
            # Determine how many nodes we can target this cycle based on
            # rebalance_batch_percent and PDB safety. This caps the iteration
            # list so we don't create more actions than the batch allows.
            _batch_percent = 60  # default: 60% of target nodes
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

            import math as _math_batch
            # Pre-filter: remove nodes with recent failed/completed actions (< 2h cooldown)
            # BEFORE computing batch size. Otherwise the batch picks cooled-down nodes,
            # skips them in the loop, and never reaches eligible nodes beyond the batch window.
            # EXCEPTION: Infrastructure-level failures (AGENT_WENT_OFFLINE, Karpenter not
            # installed) don't count — the node was never touched, so cooldown is pointless
            # and causes infinite blocking loops.
            _INFRA_FAILURES = (
                'AGENT_WENT_OFFLINE',
                'Karpenter not installed',
                'Dry run:',
                'No compatible spot pool',
                'Action timed out',
                'name \'cluster\' is not defined',  # bug guard: missing cluster query
                'Cluster ',  # "Cluster <id> not found" — node was never touched
            )
            _total_od_for_batch = len(on_demand_instances)
            _eligible_od = []
            _cooled_down_ids = set()
            for _od_inst in on_demand_instances:
                try:
                    _cd_recent = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(['completed', 'failed']),
                        RebalancingAction.completed_at >= datetime.utcnow() - timedelta(hours=2),
                    ).filter(
                        (RebalancingAction.source_instance_id == _od_inst.instance_id)
                        | (RebalancingAction.action_metadata.op('->>')('instance_id') == _od_inst.instance_id)
                    ).first()
                    if _cd_recent:
                        # Don't cooldown for infrastructure-level failures
                        if _cd_recent.status == 'failed' and _cd_recent.error_message and any(
                            _cd_recent.error_message.startswith(inf) for inf in _INFRA_FAILURES
                        ):
                            pass  # fall through to eligible
                        else:
                            _cooled_down_ids.add(_od_inst.instance_id)
                            continue
                except Exception:
                    pass
                _eligible_od.append(_od_inst)
            if _cooled_down_ids:
                logger.info(
                    f"[auto_rebalancer] Pre-filter: {len(_cooled_down_ids)} OD nodes in cooldown "
                    f"({', '.join(iid[:12] for iid in _cooled_down_ids)}), "
                    f"{len(_eligible_od)} eligible"
                )
            # Batch size is based on TOTAL OD count (not just eligible), so the
            # batch % reflects the cluster's intended migration pace.
            _batch_size = max(1, _math_batch.ceil(_total_od_for_batch * _batch_percent / 100))
            _batch_candidates = _eligible_od[:_batch_size]

            # ── INITIAL vs POST-MIGRATION CONCURRENCY ───────────────────────
            # Initial OD→Spot rebalance (managed node group not yet deleted):
            #   Run the full batch concurrently — the batch slider controls how
            #   many nodes are replaced at once (e.g. 3 nodes × 60% = ceil(1.8)
            #   = 2 nodes concurrently in batch 1, then 1 in batch 2).
            # Post-migration S2S: sequential (max_concurrent stays 1) — Karpenter
            #   handles risk/emergency ordering.
            _is_initial_rebalance = (
                len(on_demand_instances) > 0
                and not getattr(cluster, 'managed_node_group_deleted', False)
            )
            if _is_initial_rebalance:
                _initial_max_concurrent = _batch_size
            else:
                _initial_max_concurrent = None  # use default from settings (1)

            logger.info(
                f"[auto_rebalancer] Batch sizing: {cluster.name} "
                f"total_od={_total_od_for_batch} eligible={len(_eligible_od)} "
                f"batch_pct={_batch_percent}% batch_size={_batch_size} "
                f"initial_rebalance={_is_initial_rebalance} "
                f"concurrent={_initial_max_concurrent or 'default(1)'}"
            )

            # ── BATCH-LEVEL ASG MinSize PRE-SET ────────────────────────────
            # Before creating actions, lower ASG MinSize to anchor count (1)
            # so terminate+decrement calls can proceed without MinSize blocking.
            # Example: 6-node cluster, 1 anchor, batch of 3:
            #   MinSize 6 → 1 (anchor only), Desired stays 6 until terminates
            #   Batch 1 terminates: Desired 6→5→4→3, Min=1
            #   Batch 2 terminates: Desired 3→2→1, Min=1
            if _is_initial_rebalance and _batch_candidates and _karpenter_active:
                try:
                    _bm_first = _batch_candidates[0]
                    if _bm_first.instance_id and _bm_first.instance_id.startswith('i-'):
                        from backend.utils.aws.asg import (
                            get_assumed_credentials as _get_creds_bm,
                            get_asg_for_instance as _get_asg_bm,
                        )
                        _bm_region = cluster.region or "ap-south-1"
                        _bm_creds = _get_creds_bm(cluster, db)
                        _bm_asg_name = _get_asg_bm(
                            _bm_first.instance_id, _bm_region, _bm_creds
                        )
                        if _bm_asg_name:
                            import boto3 as _b3_bm
                            _bm_asg_client = _b3_bm.client(
                                "autoscaling", region_name=_bm_region, **_bm_creds
                            ) if _bm_creds else _b3_bm.client(
                                "autoscaling", region_name=_bm_region
                            )
                            _bm_desc = _bm_asg_client.describe_auto_scaling_groups(
                                AutoScalingGroupNames=[_bm_asg_name]
                            )['AutoScalingGroups']
                            if _bm_desc:
                                _bm_cur_min = _bm_desc[0].get('MinSize', 0)
                                _bm_cur_desired = _bm_desc[0].get('DesiredCapacity', 0)
                                # Anchor count = 1 (stable node excluded above)
                                _bm_target_min = 1
                                if _bm_cur_min > _bm_target_min:
                                    _bm_asg_client.update_auto_scaling_group(
                                        AutoScalingGroupName=_bm_asg_name,
                                        MinSize=_bm_target_min,
                                    )
                                    logger.info(
                                        f"[auto_rebalancer] Batch ASG pre-set: "
                                        f"'{_bm_asg_name}' MinSize {_bm_cur_min} → "
                                        f"{_bm_target_min} (anchor_count=1, "
                                        f"batch={_batch_size}, "
                                        f"Desired={_bm_cur_desired} unchanged)"
                                    )
                                else:
                                    logger.info(
                                        f"[auto_rebalancer] Batch ASG pre-set: "
                                        f"'{_bm_asg_name}' MinSize={_bm_cur_min} "
                                        f"already ≤ target {_bm_target_min}"
                                    )
                except Exception as _bm_err:
                    logger.warning(
                        f"[auto_rebalancer] Batch ASG MinSize pre-set failed: "
                        f"{_bm_err} — per-action decrement will handle it"
                    )

            for instance in _batch_candidates:
                logger.info(
                    f"[auto_rebalancer] BATCH-LOOP instance={instance.instance_id} "
                    f"lifecycle={instance.lifecycle} state={instance.state} "
                    f"type={instance.instance_type}"
                )
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
                # EXCEPTION: Infrastructure-level failures (AGENT_WENT_OFFLINE, Karpenter
                # not installed) bypass cooldown — the node was never touched.
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
                        # Infrastructure failures don't count as cooldown
                        _is_infra_fail = (
                            _recent_completed.status == 'failed'
                            and _recent_completed.error_message
                            and any(_recent_completed.error_message.startswith(inf) for inf in _INFRA_FAILURES)
                        )
                        if _is_infra_fail:
                            # Bypass cooldown — node was never touched, proceed with rebalancing
                            logger.info(
                                f"[auto_rebalancer] Bypassing cooldown for {instance.instance_id}: "
                                f"recent action {_recent_completed.id} was infra failure "
                                f"({_recent_completed.error_message[:60]})"
                            )
                        elif _recent_completed.status == 'completed':
                            logger.info(
                                f"[auto_rebalancer] Skipping {instance.instance_id}: "
                                f"recent completed action {_recent_completed.id} "
                                f"exists (< 2h) — marking DB instance as terminated to stop growth"
                            )
                            # Source should already be gone — force DB state to terminated
                            instance.state = 'terminated'
                            db.commit()
                            continue
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
                # Lock is set when an action is created (30-min TTL, 1800s) and cleared
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
                #
                # Initial OD→Spot rebalance: override to batch_size so the full
                # batch runs concurrently. After initial migration, fall back to
                # the user setting (default 1) for sequential S2S.
                if _is_initial_rebalance and _initial_max_concurrent:
                    _max_concurrent = _initial_max_concurrent
                else:
                    _max_concurrent = (
                        _opt_settings.max_concurrent_rebalance_actions
                        if _opt_settings and getattr(_opt_settings, 'max_concurrent_rebalance_actions', None)
                        else 1
                    )

                # ── CROSS-ENGINE DB COUNT GATE (authoritative) ─────────────
                # Single AgentAction DB query covers both engines:
                #   • PlacementController  → EVICT_POD AgentActions
                #   • auto_rebalancer      → CORDON/DRAIN/UNCORDON AgentActions
                # This is the canonical fix for the cross-engine batch limit race;
                # the Redis semaphore below is kept as a soft in-process guard.
                try:
                    from backend.models.agent_action import AgentAction as _AA_xeng, AgentActionStatus as _AAS_xeng
                    _xeng_active = (
                        db.query(_AA_xeng)
                        .filter(
                            _AA_xeng.cluster_id == cluster.id,
                            _AA_xeng.status.in_([_AAS_xeng.PENDING, _AAS_xeng.PICKED_UP]),
                        )
                        .count()
                    )
                    if _xeng_active >= _max_concurrent:
                        logger.debug(
                            f'[auto_rebalancer] Cluster {cluster.name} cross-engine batch gate: '
                            f'{_xeng_active}/{_max_concurrent} AgentActions in-flight — skipping (DB COUNT)'
                        )
                        break
                except Exception as _xeng_err:
                    logger.debug(f'[auto_rebalancer] Cross-engine DB gate failed ({_xeng_err}), falling back to semaphore')

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
                        if _cur_specs is None:
                            # P5: instance type missing from catalog dict — bin-pack silently
                            # degrades to same-type migration. Surface as degraded health state.
                            logger.warning(
                                f"[auto_rebalancer] Bin-pack: {instance.instance_type} not in "
                                f"instance catalog for cluster {cluster.name} — "
                                f"rightsizing disabled, falling back to same-type spot migration. "
                                f"Run instance catalog refresh for region {cluster.region}."
                            )
                            try:
                                if _redis:
                                    import json as _hj_cat
                                    _redis.setex(
                                        f"spot:cluster_health:{cluster.id}",
                                        3600,  # 1h TTL — will refresh on next catalog run
                                        _hj_cat.dumps({
                                            "state": "degraded",
                                            "reason": "catalog_missing",
                                            "detail": (
                                                f"Instance type {instance.instance_type} not found "
                                                f"in catalog for region {cluster.region}. "
                                                f"Rightsizing disabled — run catalog refresh."
                                            ),
                                            "cluster_name": cluster.name,
                                            "missing_type": instance.instance_type,
                                            "region": cluster.region,
                                        })
                                    )
                            except Exception:
                                pass
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
                        logger.info(
                            f"[auto_rebalancer] No qualifying spot pool for {instance.instance_id} "
                            f"({instance.instance_type}) — skipping this cycle"
                        )
                except Exception as _pool_sel_err:
                    logger.warning(
                        f"[auto_rebalancer] Pool selection exception for {instance.instance_id}: "
                        f"{type(_pool_sel_err).__name__}: {_pool_sel_err}"
                    )
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

                # ── TARGET POOL DEDUP ───────────────────────────────────────────
                # For S2S (post-migration) only: prevent two actions from targeting
                # the same spot pool simultaneously — two S2S migrations to the same
                # pool would waste a provision.
                #
                # For initial OD→Spot batch: SKIP this check. Multiple OD nodes
                # SHOULD target the same best pool (e.g. c7g.medium:az). Each gets
                # its own separate spot EC2 instance. Dedup was incorrectly forcing
                # different instance types (e.g. c5.large) for parallel batch nodes.
                # The only real guard needed: source_instance_id != target (can't
                # replace a node with itself), which is already enforced above.
                if not _is_initial_rebalance:
                    try:
                        _active_target_pools = set()
                        _active_for_dedup = db.query(RebalancingAction.target_pool).filter(
                            RebalancingAction.cluster_id == cluster.id,
                            RebalancingAction.status.in_(['in_progress', 'waiting_agent', 'pending_approval']),
                        ).all()
                        for (_atp,) in _active_for_dedup:
                            if _atp:
                                _active_target_pools.add(_atp)
                        if target_pool in _active_target_pools:
                            logger.info(
                                f"[auto_rebalancer] Skipping {instance.instance_id} — "
                                f"target pool {target_pool} already claimed by active action (S2S dedup)"
                            )
                            continue
                    except Exception as _dedup_err:
                        logger.debug(f"[auto_rebalancer] Target pool dedup check failed: {_dedup_err}")

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
                        'is_initial_batch': _is_initial_rebalance,
                        'batch_size': _batch_size if _is_initial_rebalance else 1,
                        'total_od_nodes': len(on_demand_instances),
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

                # Z6 fix: Set per-node active action lock with 30-min safety-net TTL.
                # Cleared explicitly by completion/failure handlers; TTL is a fallback
                # to prevent permanent lockout if explicit cleanup is missed.
                # Reduced from 24h to 30min — typical action completes in <20min;
                # 24h TTL caused day-long blockouts when cleanup was missed.
                try:
                    if _redis:
                        _redis.setex(
                            f"spot:node_active_action:{instance.instance_id}",
                            1800,
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

                # Initial OD→Spot rebalance: create ALL batch actions in one cycle.
                # Post-migration (S2S): only 1 action per cluster per cycle.
                if not _is_initial_rebalance:
                    break  # sequential: 1 action per cluster per cycle

        db.commit()

        # Step 2: Execute in_progress actions.
        # Initial OD→Spot rebalance (MNG not deleted): execute the full batch
        # concurrently — all in_progress actions for that cluster run in one cycle.
        # Post-migration S2S: execute 1 per cluster (sequential).
        from sqlalchemy import func as _sqlfunc
        clusters_with_actions = db.query(RebalancingAction.cluster_id).filter(
            RebalancingAction.status == 'in_progress'
        ).distinct().all()

        executed = 0
        for (cid,) in clusters_with_actions:
            _exec_cluster = db.query(Cluster).filter(Cluster.id == cid).first()
            _is_initial = (
                _exec_cluster
                and not getattr(_exec_cluster, 'managed_node_group_deleted', False)
            )

            if _is_initial:
                # Initial rebalance: execute ALL in_progress actions (batch)
                # Acquire the cluster lock ONCE, then pass _batch_lock_held=True
                # so all batch actions execute in parallel without deferring.
                _batch_actions = db.query(RebalancingAction).filter(
                    RebalancingAction.cluster_id == cid,
                    RebalancingAction.status == 'in_progress'
                ).order_by(RebalancingAction.started_at).all()
                if _batch_actions:
                    from backend.core.redis_client import get_redis_client as _grc_batch, key_rebalance_lock as _krl_batch
                    _batch_redis = _grc_batch()
                    _batch_lock_key = _krl_batch(cid)
                    # Use first action's ID as lock owner for the entire batch
                    _batch_lock_ok = _batch_redis.set(
                        _batch_lock_key, f"batch:{_batch_actions[0].id}",
                        nx=True, ex=2700
                    )
                    if not _batch_lock_ok:
                        logger.info(
                            f"[auto_rebalancer] Cluster {_exec_cluster.name}: "
                            f"rebalance lock held — deferring {len(_batch_actions)} batch actions"
                        )
                        for action in _batch_actions:
                            action.status = 'deferred'
                            action.error_message = 'Batch lock held by concurrent operation'
                        db.commit()
                    else:
                        try:
                            for action in _batch_actions:
                                execute_rebalancing_action(db, action, _batch_lock_held=True)
                                executed += 1
                            logger.info(
                                f"[auto_rebalancer] Initial batch: executed {len(_batch_actions)} "
                                f"parallel action(s) for {_exec_cluster.name}"
                            )
                        finally:
                            # Release batch lock after all actions complete
                            try:
                                _batch_redis.delete(_batch_lock_key)
                            except Exception:
                                pass
            else:
                # Post-migration: 1 action at a time (sequential S2S)
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
            logger.info(f"Executed {executed} rebalancing action(s)")

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
