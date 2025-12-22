"""
Governance API Routes

Exposes security audit results and unauthorized instance detection.
Integrates with SecurityEnforcer to prevent Shadow IT.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime

from database.connection import get_db
from jobs.security_enforcer import SecurityEnforcer
from database.models import Instance, Account
from utils.system_logger import logger
from api.auth import get_current_active_user as get_current_user

router = APIRouter(
    prefix="",
    tags=["governance"]
)


@router.get('/audit')
async def get_security_audit(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns comprehensive security audit results

    Checks all instances for proper authorization tags:
    - ManagedBy: SpotOptimizer
    - aws:autoscaling:groupName (ASG membership)
    - eks:cluster-name (K8s cluster membership)
    """
    try:
        # Query instances flagged as unauthorized
        unauthorized_instances = db.query(Instance).filter(
            Instance.auth_status == 'unauthorized'
        ).all()

        # Query instances in grace period
        grace_period_instances = db.query(Instance).filter(
            Instance.auth_status == 'grace_period'
        ).all()

        # Group by severity
        critical = [i for i in unauthorized_instances if (i.instance_metadata or {}).get('grace_expired', False)]
        high = [i for i in unauthorized_instances if not (i.instance_metadata or {}).get('grace_expired', False)]
        medium = grace_period_instances

        result = {
            'total_violations': len(unauthorized_instances) + len(grace_period_instances),
            'by_severity': {
                'critical': len(critical),  # Grace period expired
                'high': len(high),  # Unauthorized, in grace period
                'medium': len(medium),  # Recently flagged
                'low': 0
            },
            'violations': [
                {
                    'id': str(i.id),
                    'instance_id': i.instance_id,
                    'instance_type': i.instance_type,
                    'account_id': str(i.account_id),
                    'region': i.account.region if i.account else 'unknown',
                    'severity': 'critical' if (i.instance_metadata or {}).get('grace_expired') else 'high',
                    'violation_type': 'unauthorized_instance',
                    'description': f'Instance {i.instance_id} running without proper authorization tags',
                    'detected_at': i.updated_at.isoformat() if i.updated_at else datetime.utcnow().isoformat()
                }
                for i in (unauthorized_instances + grace_period_instances)[:50]  # Limit to 50 most recent
            ]
        }

        logger.info(
            f'Security audit returned {result["total_violations"]} violations',
            extra={'component': 'GovernanceAPI', 'user_id': current_user.id}
        )

        return result

    except Exception as e:
        logger.error(
            f'Failed to fetch security audit: {e}',
            extra={'component': 'GovernanceAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/unauthorized')
async def get_unauthorized_instances(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns list of instances launched without proper authorization

    Instances are flagged if they lack:
    - ManagedBy tag
    - ASG membership
    - K8s cluster membership
    """
    try:
        # Query unauthorized instances
        unauthorized = db.query(Instance).filter(
            Instance.auth_status.in_(['unauthorized', 'grace_period'])
        ).order_by(Instance.updated_at.desc()).all()

        result = [
            {
                'id': str(item.id),
                'instance_id': item.instance_id,
                'instance_type': item.instance_type,
                'account_id': str(item.account_id),
                'region': item.account.region if item.account else 'unknown',
                'state': (item.instance_metadata or {}).get('state', 'unknown'),
                'launch_time': (item.instance_metadata or {}).get('launch_time'),
                'violation_reason': 'Missing authorization tags (ManagedBy, ASG, or EKS)',
                'auth_status': item.auth_status,
                'detected_at': item.updated_at.isoformat() if item.updated_at else datetime.utcnow().isoformat(),
                'grace_period_expires': (item.instance_metadata or {}).get('grace_expires_at')
            }
            for item in unauthorized
        ]

        logger.info(
            f'Unauthorized instances query returned {len(result)} items',
            extra={'component': 'GovernanceAPI', 'user_id': current_user.id}
        )

        return {
            'total_unauthorized': len(result),
            'instances': result
        }

    except Exception as e:
        logger.error(
            f'Failed to fetch unauthorized instances: {e}',
            extra={'component': 'GovernanceAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/scan')
async def trigger_security_scan(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Manually triggers a security audit across all accounts

    Scans all running instances for proper authorization tags.
    """
    try:
        logger.info(
            'Manual security scan triggered',
            extra={'component': 'GovernanceAPI', 'user_id': current_user.id}
        )

        # Initialize security enforcer
        enforcer = SecurityEnforcer(db)

        # Get all active accounts
        accounts = db.query(Account).filter(Account.status == 'active').all()

        total_scanned = 0
        total_violations = 0

        # Run scan for each account
        for account in accounts:
            try:
                scan_result = enforcer.audit_account(account)
                total_scanned += scan_result.get('instances_scanned', 0)
                total_violations += scan_result.get('violations_found', 0)
            except Exception as e:
                logger.warning(
                    f'Security scan failed for account {account.account_id}: {e}',
                    extra={'component': 'GovernanceAPI', 'account_id': account.account_id}
                )

        return {
            'status': 'completed',
            'scan_started_at': datetime.utcnow().isoformat(),
            'accounts_scanned': len(accounts),
            'instances_scanned': total_scanned,
            'violations_found': total_violations
        }

    except Exception as e:
        logger.error(
            f'Security scan failed: {e}',
            extra={'component': 'GovernanceAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=f'Scan failed: {str(e)}')


@router.post('/instances/apply')
async def apply_instance_actions(
    flagged_instances: List[Dict],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Apply flagged actions to instances (authorize or terminate)

    Expected format:
    [
        {"instance_id": "i-123", "action": "authorize"},
        {"instance_id": "i-456", "action": "terminate"}
    ]
    """
    try:
        logger.info(
            f'Applying actions to {len(flagged_instances)} instances',
            extra={'component': 'GovernanceAPI', 'user_id': current_user.id}
        )

        results = {
            'authorized': [],
            'terminated': [],
            'failed': []
        }

        for item in flagged_instances:
            instance_id = item.get('instance_id')
            action = item.get('action')

            try:
                # Find instance in database
                instance = db.query(Instance).filter(
                    Instance.instance_id == instance_id
                ).first()

                if not instance:
                    results['failed'].append({
                        'instance_id': instance_id,
                        'reason': 'Instance not found'
                    })
                    continue

                if action == 'authorize':
                    # Mark as authorized
                    instance.auth_status = 'authorized'
                    instance.updated_at = datetime.utcnow()

                    # Clear grace period metadata
                    if instance.instance_metadata:
                        instance.instance_metadata.pop('grace_expired', None)
                        instance.instance_metadata.pop('grace_expires_at', None)

                    db.commit()

                    results['authorized'].append({
                        'instance_id': instance_id,
                        'status': 'authorized'
                    })

                    logger.info(
                        f'Instance {instance_id} authorized',
                        extra={'component': 'GovernanceAPI', 'instance_id': instance_id}
                    )

                elif action == 'terminate':
                    # TODO: In production, call AWS API to terminate instance
                    # For now, mark as terminated in database
                    instance.is_active = False
                    instance.auth_status = 'terminated'
                    instance.updated_at = datetime.utcnow()

                    if not instance.instance_metadata:
                        instance.instance_metadata = {}
                    instance.instance_metadata['terminated_at'] = datetime.utcnow().isoformat()
                    instance.instance_metadata['terminated_by'] = str(current_user.id)

                    db.commit()

                    results['terminated'].append({
                        'instance_id': instance_id,
                        'status': 'terminated'
                    })

                    logger.info(
                        f'Instance {instance_id} terminated',
                        extra={'component': 'GovernanceAPI', 'instance_id': instance_id}
                    )

                else:
                    results['failed'].append({
                        'instance_id': instance_id,
                        'reason': f'Invalid action: {action}'
                    })

            except Exception as e:
                results['failed'].append({
                    'instance_id': instance_id,
                    'reason': str(e)
                })
                logger.error(
                    f'Failed to apply action for instance {instance_id}: {e}',
                    extra={'component': 'GovernanceAPI', 'instance_id': instance_id}
                )

        return {
            'status': 'completed',
            'results': results,
            'summary': {
                'total': len(flagged_instances),
                'authorized': len(results['authorized']),
                'terminated': len(results['terminated']),
                'failed': len(results['failed'])
            },
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(
            f'Failed to apply instance actions: {e}',
            extra={'component': 'GovernanceAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=f'Failed to apply actions: {str(e)}')
