"""
Approval Workflow API Routes

Handles manual approval gates for optimization requests.
Provides endpoints for viewing pending requests and approving/rejecting them.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from database.connection import get_db
from database.models import Instance, Account
from utils.system_logger import logger
from api.auth import get_current_active_user as get_current_user

router = APIRouter(
    prefix="",
    tags=["approvals"]
)


class ApprovalAction(BaseModel):
    comment: Optional[str] = None


@router.get('/pending')
async def get_pending_approvals(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns list of optimization requests pending approval

    These are instances that have been evaluated and recommended for
    optimization, but require manual approval before execution.
    """
    try:
        # Query instances pending approval
        # Looking for instances with status 'pending_approval'
        pending = db.query(Instance).filter(
            Instance.status == 'pending_approval'
        ).order_by(Instance.last_seen.desc()).all()

        result = [
            {
                'id': str(req.id),
                'instance_id': req.instance_id,
                'instance_type_from': req.instance_type,
                'instance_type_to': req.metadata.get('recommended_type') if req.metadata else req.instance_type,
                'estimated_savings': float(req.metadata.get('estimated_savings', 0)) if req.metadata else 0.0,
                'risk_level': req.metadata.get('risk_level', 'medium') if req.metadata else 'medium',
                'requested_at': req.last_seen.isoformat() if req.last_seen else datetime.utcnow().isoformat(),
                'justification': req.metadata.get('justification', 'Cost optimization recommendation') if req.metadata else 'Cost optimization',
                'account_id': str(req.account_id),
                'region': req.account.region if req.account else 'unknown'
            }
            for req in pending
        ]

        logger.info(
            f'Pending approvals query returned {len(result)} items',
            extra={'component': 'ApprovalAPI', 'user_id': current_user.id}
        )

        return {
            'total_pending': len(result),
            'approval_requests': result
        }

    except Exception as e:
        logger.error(
            f'Failed to fetch pending approvals: {e}',
            extra={'component': 'ApprovalAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/{instance_id}/approve')
async def approve_request(
    instance_id: str,
    action: ApprovalAction,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Approves an optimization request

    Sets the instance status to 'approved' which allows the
    optimization pipeline to proceed with the switch.
    """
    try:
        # Find instance
        instance = db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()

        if not instance:
            raise HTTPException(status_code=404, detail='Instance not found')

        if instance.status != 'pending_approval':
            raise HTTPException(status_code=400, detail='Instance not pending approval')

        # Update instance status
        instance.status = 'approved'
        if not instance.metadata:
            instance.metadata = {}
        instance.metadata['approved_by'] = current_user.email
        instance.metadata['approved_at'] = datetime.utcnow().isoformat()
        instance.metadata['approval_comment'] = action.comment

        db.commit()

        logger.info(
            f'Instance {instance_id} approved for optimization',
            extra={
                'component': 'ApprovalAPI',
                'user_id': current_user.id,
                'instance_id': instance_id
            }
        )

        return {
            'status': 'approved',
            'instance_id': instance_id,
            'approved_by': current_user.email,
            'approved_at': datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f'Failed to approve instance {instance_id}: {e}',
            extra={'component': 'ApprovalAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/{instance_id}/reject')
async def reject_request(
    instance_id: str,
    action: ApprovalAction,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Rejects an optimization request

    Sets the instance status back to 'running' and blocks
    the optimization from proceeding.
    """
    try:
        # Find instance
        instance = db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()

        if not instance:
            raise HTTPException(status_code=404, detail='Instance not found')

        if instance.status != 'pending_approval':
            raise HTTPException(status_code=400, detail='Instance not pending approval')

        # Update instance status
        instance.status = 'running'  # Reset to running
        if not instance.metadata:
            instance.metadata = {}
        instance.metadata['rejected_by'] = current_user.email
        instance.metadata['rejected_at'] = datetime.utcnow().isoformat()
        instance.metadata['rejection_comment'] = action.comment
        instance.metadata['approval_blocked'] = True

        db.commit()

        logger.info(
            f'Instance {instance_id} optimization rejected',
            extra={
                'component': 'ApprovalAPI',
                'user_id': current_user.id,
                'instance_id': instance_id
            }
        )

        return {
            'status': 'rejected',
            'instance_id': instance_id,
            'rejected_by': current_user.email,
            'rejected_at': datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f'Failed to reject instance {instance_id}: {e}',
            extra={'component': 'ApprovalAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))
