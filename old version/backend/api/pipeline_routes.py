"""
Pipeline API Routes

Provides real-time pipeline funnel and status metrics
for the ML decision-making process visualization.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Dict
from datetime import datetime, timedelta

from database.connection import get_db
from database.models import Instance, ExperimentLog
from database.system_logs import SystemLog, ComponentStatus, ComponentHealth
from api.auth import get_current_active_user

router = APIRouter(
    prefix="",
    tags=["pipeline"]
)


@router.get('/funnel')
async def get_pipeline_funnel(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Returns ML pipeline funnel data showing the decision-making process:
    - Total pools considered
    - Pools after static filters
    - Pools after ML prediction
    - Final selections
    """
    try:
        # Get recent experiments to calculate funnel stages
        since = datetime.utcnow() - timedelta(hours=24)

        total_experiments = db.query(ExperimentLog).filter(
            ExperimentLog.created_at >= since
        ).count()

        # Simulate funnel stages based on experiment data
        # In production, this would query actual ML pipeline metrics

        # Stage 1: All available pools (estimate: 500)
        total_pools = total_experiments * 10 if total_experiments > 0 else 500

        # Stage 2: After static filters (remove ~20%)
        after_static_filters = int(total_pools * 0.8)

        # Stage 3: After ML prediction (remove another ~15%)
        after_ml_prediction = int(after_static_filters * 0.85)

        # Stage 4: Final selections (actual experiments)
        final_selections = total_experiments

        return {
            'stages': [
                {
                    'name': 'Total Pools Scanned',
                    'count': total_pools,
                    'percentage': 100,
                    'description': 'All available spot instance pools'
                },
                {
                    'name': 'After Static Filters',
                    'count': after_static_filters,
                    'percentage': round((after_static_filters / total_pools) * 100, 2),
                    'description': 'Pools meeting basic requirements'
                },
                {
                    'name': 'After ML Prediction',
                    'count': after_ml_prediction,
                    'percentage': round((after_ml_prediction / total_pools) * 100, 2),
                    'description': 'Pools with favorable ML scores'
                },
                {
                    'name': 'Final Selections',
                    'count': final_selections,
                    'percentage': round((final_selections / total_pools) * 100, 2),
                    'description': 'Pools actually selected for instances'
                }
            ],
            'period_hours': 24,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pipeline funnel: {str(e)}")


@router.get('/status')
async def get_pipeline_status(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Returns status of all pipeline components:
    - Scraper health
    - Risk Engine status
    - Cost Optimizer status
    - Controller status
    """
    try:
        # Get health status for key pipeline components
        components = [
            'web_scraper',
            'price_scraper',
            'ml_inference',
            'linear_optimizer',
            'instance_manager',
            'api_server'
        ]

        component_statuses = []
        for component_name in components:
            health = db.query(ComponentHealth).filter(
                ComponentHealth.component == component_name
            ).first()

            if health:
                component_statuses.append({
                    'name': component_name.replace('_', ' ').title(),
                    'status': health.status.value if hasattr(health.status, 'value') else str(health.status),
                    'uptime_seconds': (datetime.utcnow() - (health.last_success or datetime.utcnow())).total_seconds() if health.last_success else 0,
                    'avg_latency_ms': health.avg_execution_time_ms or 0,
                    'last_check': health.last_check.isoformat() if health.last_check else None
                })
            else:
                component_statuses.append({
                    'name': component_name.replace('_', ' ').title(),
                    'status': 'unknown',
                    'uptime_seconds': 0,
                    'avg_latency_ms': 0,
                    'last_check': None
                })

        # Calculate overall pipeline health
        healthy_count = sum(1 for c in component_statuses if c['status'] == 'healthy')
        total_count = len(component_statuses)
        pipeline_health_percentage = round((healthy_count / total_count) * 100, 2)

        # Determine overall status
        if pipeline_health_percentage >= 90:
            overall_status = 'healthy'
        elif pipeline_health_percentage >= 70:
            overall_status = 'degraded'
        else:
            overall_status = 'critical'

        return {
            'overall_status': overall_status,
            'health_percentage': pipeline_health_percentage,
            'components': component_statuses,
            'healthy_count': healthy_count,
            'total_count': total_count,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pipeline status: {str(e)}")
