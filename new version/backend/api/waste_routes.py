"""
Waste Scanner API Routes

Exposes waste detection results and manual scan triggers to the frontend.
Integrates with WasteScanner engine to identify unused AWS resources.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from database.connection import get_db
from jobs.waste_scanner import WasteScanner
from database.models import WasteResource, Account
from utils.system_logger import logger
from api.auth import get_current_active_user as get_current_user

router = APIRouter(
    prefix="",
    tags=["waste"]
)


@router.get('/')
async def get_waste(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns list of unused/underutilized resources detected by WasteScanner

    This endpoint queries the waste_resources table and returns all active
    waste items with their estimated monthly costs.
    """
    try:
        # Query waste resources from database
        waste_items = db.query(WasteResource).filter(
            WasteResource.status == 'active'
        ).order_by(WasteResource.detected_at.desc()).all()

        result = [
            {
                'id': str(item.id),
                'resource_type': item.resource_type,
                'resource_id': item.resource_id,
                'account_id': str(item.account_id),
                'region': item.region,
                'reason': item.reason,
                'monthly_cost': float(item.monthly_cost) if item.monthly_cost else 0.0,
                'detected_at': item.detected_at.isoformat(),
                'days_unused': item.days_unused or 0
            }
            for item in waste_items
        ]

        total_savings = sum(item['monthly_cost'] for item in result)

        logger.info(
            f'Waste query returned {len(result)} items, ${total_savings:.2f}/month potential savings',
            extra={'component': 'WasteAPI', 'user_id': current_user.id}
        )

        return {
            'total_waste_items': len(result),
            'total_monthly_savings': round(total_savings, 2),
            'waste_resources': result
        }

    except Exception as e:
        logger.error(
            f'Failed to fetch waste data: {e}',
            extra={'component': 'WasteAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/scan')
async def trigger_waste_scan(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Manually triggers a waste detection scan across all managed accounts

    This runs the WasteScanner engine which checks for:
    - Unattached Elastic IPs ($3.60/month each)
    - Detached EBS volumes (> 7 days)
    - Old EBS snapshots (> 30 days, not linked to AMI)
    """
    try:
        logger.info(
            'Manual waste scan triggered',
            extra={'component': 'WasteAPI', 'user_id': current_user.id}
        )

        # Initialize waste scanner
        scanner = WasteScanner(db)

        # Get all active accounts
        accounts = db.query(Account).filter(Account.status == 'active').all()

        total_new_items = 0
        total_potential_savings = 0.0

        # Run scan for each account
        for account in accounts:
            try:
                scan_result = scanner.scan_account(account)
                total_new_items += scan_result.get('new_items', 0)
                total_potential_savings += scan_result.get('savings', 0.0)
            except Exception as e:
                logger.warning(
                    f'Scan failed for account {account.account_id}: {e}',
                    extra={'component': 'WasteAPI', 'account_id': account.account_id}
                )

        return {
            'status': 'completed',
            'scan_started_at': datetime.utcnow().isoformat(),
            'accounts_scanned': len(accounts),
            'new_waste_detected': total_new_items,
            'potential_monthly_savings': round(total_potential_savings, 2)
        }

    except Exception as e:
        logger.error(
            f'Waste scan failed: {e}',
            extra={'component': 'WasteAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=f'Scan failed: {str(e)}')
