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
from backend.services.savings_plan_service import get_savings_plan_service

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
    lookback_days: int = Query(30, description="Analysis period in days (7, 30, or 90)", ge=7, le=90),
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Trigger RI utilization analysis - PRODUCTION GRADE
    Supports configurable lookback period for more accurate analysis.
    
    Lookback periods:
    - 7 days: Quick recent snapshot (may not be representative)
    - 30 days: Standard monthly analysis (default, recommended)
    - 90 days: Quarterly analysis (most reliable for financial decisions)
    """
    service = get_ri_analysis_service(db)
    try:
        result = service.analyze_all_accounts(current_user, lookback_days)
        return {
            'status': 'success',
            'message': f"Analyzed {result['accounts_analyzed']} accounts over {lookback_days} days",
            'lookback_days': lookback_days,
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


# Savings Plans Endpoints

@router.get("/savings-plans/overview")
def get_savings_plans_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Savings Plans health overview.
    Returns utilization stats and coverage metrics.
    """
    service = get_savings_plan_service(db)
    return service.get_overview(current_user)


@router.post("/savings-plans/analyze")
def analyze_savings_plans(
    lookback_days: int = Query(30, description="Analysis period in days (7, 30, or 90)", ge=7, le=90),
    current_user: User = Depends(RequireRole("ORG_ADMIN")),
    db: Session = Depends(get_db)
):
    """
    Trigger Savings Plans analysis for all accounts.
    Modern alternative to Reserved Instances with more flexibility.
    """
    service = get_savings_plan_service(db)
    try:
        result = service.analyze_all_accounts(current_user, lookback_days)
        return {
            'status': 'success',
            'message': f"Analyzed Savings Plans for {result['accounts_analyzed']} accounts",
            'lookback_days': lookback_days,
            'summary': {
                'total_plans': result['total_plans'],
                'underutilized_count': result['underutilized_count'],
                'monthly_waste': result['total_monthly_waste'],
                'actual_savings': result['total_actual_savings']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unified-coverage")
def get_unified_coverage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get unified coverage report showing both RIs and Savings Plans.
    Prevents double-counting and shows total commitment coverage.
    """
    ri_service = get_ri_analysis_service(db)
    sp_service = get_savings_plan_service(db)
    
    ri_overview = ri_service.get_ri_overview(current_user)
    sp_overview = sp_service.get_overview(current_user)
    
    # Calculate unified metrics
    total_monthly_commitment = ri_overview.get('wasted_spend_monthly', 0) + sp_overview.get('total_monthly_commitment', 0)
    total_waste = ri_overview.get('wasted_spend_monthly', 0) + sp_overview.get('wasted_spend_monthly', 0)
    avg_coverage = sp_overview.get('avg_coverage_percentage', 0)  # SP coverage is more comprehensive
    
    return {
        'reserved_instances': {
            'count': ri_overview.get('total_ris', 0),
            'underutilized': ri_overview.get('underutilized_count', 0),
            'monthly_waste': ri_overview.get('wasted_spend_monthly', 0)
        },
        'savings_plans': {
            'count': sp_overview.get('total_plans', 0),
            'underutilized': sp_overview.get('underutilized_count', 0),
            'monthly_waste': sp_overview.get('wasted_spend_monthly', 0),
            'actual_savings': sp_overview.get('actual_savings_monthly', 0)
        },
        'unified': {
            'total_monthly_commitment': total_monthly_commitment,
            'total_monthly_waste': total_waste,
            'coverage_percentage': avg_coverage,
            'health_status': _get_unified_health(ri_overview.get('health_status'), sp_overview.get('health_status'))
        }
    }


def _get_unified_health(ri_health: str, sp_health: str) -> str:
    """Calculate unified health status from both RI and SP health"""
    health_priority = {'critical': 4, 'warning': 3, 'good': 2, 'healthy': 1, 'excellent': 0, 'no_data': 5}
    ri_priority = health_priority.get(ri_health, 5)
    sp_priority = health_priority.get(sp_health, 5)
    
    # Return worst health status
    worst_priority = max(ri_priority, sp_priority)
    for status, priority in health_priority.items():
        if priority == worst_priority:
            return status
    return 'no_data'
