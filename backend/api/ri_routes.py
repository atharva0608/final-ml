"""
Reserved Instance Analysis API Routes
Endpoints for RI waste detection and recommendations
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user, RequireRole
from backend.services.ri_analysis_service import get_ri_analysis_service, RIAnalysisService

router = APIRouter(prefix="/ri", tags=["Reserved Instances"])


@router.get("/overview")
def get_ri_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get RI health overview for dashboard.
    Returns total RIs, underutilization stats, and waste metrics.
    """
    service = get_ri_analysis_service(db)
    return service.get_ri_overview(current_user)


@router.get("/list")
def list_ris(
    underutilized_only: bool = Query(False, description="Filter to underutilized RIs only"),
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all Reserved Instances with utilization data.
    Supports filtering by underutilization status and account.
    """
    service = get_ri_analysis_service(db)
    filters = {
        'underutilized_only': underutilized_only,
        'account_id': account_id
    }
    return {
        'ris': service.get_ri_list(current_user, filters)
    }


@router.get("/{ri_id}/recommendations")
def get_ri_recommendations(
    ri_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed recommendations for a specific Reserved Instance.
    Includes alternative actions and estimated savings.
    """
    service = get_ri_analysis_service(db)
    return service.get_ri_recommendations(current_user, ri_id)


@router.post("/analyze")
def analyze_ri_utilization(
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Trigger RI utilization analysis for all accounts.
    Requires ORG_ADMIN role. This may take a few minutes.
    """
    service = get_ri_analysis_service(db)
    try:
        result = service.analyze_all_accounts(current_user)
        return {
            'status': 'success',
            'message': f"Analyzed {result['accounts_analyzed']} accounts",
            'summary': {
                'total_ris': result['total_ris'],
                'underutilized_count': result['underutilized_count'],
                'monthly_waste': result['total_monthly_waste'],
                'annual_waste': result['total_annual_waste']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{ri_id}/action/{action_type}")
def execute_ri_action(
    ri_id: str,
    action_type: str,
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Execute an action on a Reserved Instance.
    Actions: sell_marketplace, modify, convert, monitor
    """
    valid_actions = ['sell_marketplace', 'modify', 'convert', 'monitor', 'analyze_workload']
    
    if action_type not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Valid actions: {valid_actions}")
    
    # For now, return a mock response indicating the action would be taken
    # In production, this would integrate with AWS SDK to perform the action
    return {
        'status': 'pending',
        'message': f"Action '{action_type}' scheduled for RI {ri_id}",
        'next_steps': get_action_next_steps(action_type)
    }


def get_action_next_steps(action_type: str) -> list:
    """Get next steps guidance for each action type"""
    steps = {
        'sell_marketplace': [
            'Navigate to AWS Console → EC2 → Reserved Instances',
            'Select the RI and click "Sell Reserved Instance"',
            'Set your asking price (we recommend 60-70% of remaining value)',
            'Review and confirm the listing'
        ],
        'modify': [
            'Navigate to AWS Console → EC2 → Reserved Instances',
            'Select the RI and click "Modify Reserved Instances"',
            'Choose new instance type or availability zone',
            'Confirm the modification (note: some modifications have restrictions)'
        ],
        'convert': [
            'Consider converting to Compute Savings Plan for more flexibility',
            'Navigate to AWS Cost Explorer → Savings Plans',
            'Use the RI purchase amount as your commitment',
            'Review coverage estimate before purchasing'
        ],
        'monitor': [
            'RI will be monitored for the next 30 days',
            'You will receive alerts if utilization changes significantly',
            'Review the situation next month'
        ],
        'analyze_workload': [
            'Review which EC2 instances are using this RI',
            'Identify why utilization is low (scaled down? migrated?)',
            'Determine if workload will increase or if RI is no longer needed'
        ]
    }
    return steps.get(action_type, [])
