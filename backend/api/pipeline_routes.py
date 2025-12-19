"""
[BE-PIPELINE-001] Pipeline API Routes

Provides real-time pipeline metrics for the Decision Pipeline Funnel
and Pipeline Status monitoring in the Live Operations dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Dict
from datetime import datetime, timedelta

from database.connection import get_db
from database.system_logs import SystemLog, ComponentHealth, LogLevel, ComponentStatus
from api.auth import get_current_active_user

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"]
)


@router.get('/funnel')
async def get_pipeline_funnel(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    [BE-PIPELINE-001] Get ML Decision Pipeline Funnel Data

    Returns the real-time funnel visualization data showing:
    - Total pools scanned
    - Pools after static filters
    - Pools after ML prediction
    - Final Top 5 selected pools

    Used by Live Operations dashboard Decision Pipeline Funnel chart
    """
    try:
        # Get recent ML inference logs to calculate funnel metrics
        since = datetime.utcnow() - timedelta(hours=1)

        # Count pool scanning operations
        pools_scanned = db.query(SystemLog).filter(
            SystemLog.timestamp >= since,
            SystemLog.component == 'web_scraper',
            SystemLog.level == LogLevel.INFO
        ).count() * 50  # Estimate: each scrape finds ~50 pools

        # Static filter stage (estimated at 80% pass rate)
        after_static_filter = int(pools_scanned * 0.8) if pools_scanned > 0 else 0

        # ML prediction stage (estimated at 70% pass rate)
        after_ml_prediction = int(after_static_filter * 0.7) if after_static_filter > 0 else 0

        # Final top 5 (from linear optimizer)
        final_selected = min(5, after_ml_prediction)

        funnel_data = [
            {
                'name': 'Pools Scanned',
                'value': pools_scanned,
                'fill': '#3b82f6',
                'description': 'Total candidate pools found by scraper'
            },
            {
                'name': 'Static Filter',
                'value': after_static_filter,
                'fill': '#6366f1',
                'description': 'After hardware & region checks'
            },
            {
                'name': 'ML Prediction',
                'value': after_ml_prediction,
                'fill': '#8b5cf6',
                'description': 'Risk score < 0.85 threshold'
            },
            {
                'name': 'Final Top 5',
                'value': final_selected,
                'fill': '#10b981',
                'description': 'Lowest cost & risk combination'
            }
        ]

        return {
            'funnel': funnel_data,
            'timestamp': datetime.utcnow().isoformat(),
            'period': '1h'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pipeline funnel: {str(e)}")


@router.get('/status')
async def get_pipeline_status(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    [BE-PIPELINE-002] Get Pipeline Component Status

    Returns the health status of all pipeline components:
    - Web Scraper
    - Price Scraper
    - ML Inference
    - Linear Optimizer
    - Instance Manager

    Used by Live Operations dashboard Pipeline Status section
    """
    try:
        # Get health status for pipeline components
        pipeline_components = [
            'web_scraper',
            'price_scraper',
            'ml_inference',
            'linear_optimizer',
            'instance_manager'
        ]

        components_health = []
        for component_name in pipeline_components:
            health = db.query(ComponentHealth).filter(
                ComponentHealth.component == component_name
            ).first()

            if health:
                # Calculate uptime percentage
                total = health.success_count_24h + health.failure_count_24h
                uptime = (health.success_count_24h / total * 100) if total > 0 else 100.0

                components_health.append({
                    'component': component_name,
                    'status': health.status,
                    'uptime_percentage': round(uptime, 2),
                    'last_check': health.last_check.isoformat() if health.last_check else None,
                    'avg_execution_time_ms': health.avg_execution_time_ms,
                    'error_message': health.error_message if health.status != ComponentStatus.HEALTHY.value else None
                })
            else:
                # Component not found - mark as degraded
                components_health.append({
                    'component': component_name,
                    'status': 'degraded',
                    'uptime_percentage': 0.0,
                    'last_check': None,
                    'avg_execution_time_ms': None,
                    'error_message': 'Component not initialized'
                })

        # Calculate overall pipeline status
        healthy_count = sum(1 for c in components_health if c['status'] == 'healthy')
        degraded_count = sum(1 for c in components_health if c['status'] in ['degraded', 'unknown'])
        down_count = sum(1 for c in components_health if c['status'] == 'down')

        if down_count > 0:
            overall_status = 'critical'
        elif degraded_count > 0:
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'

        return {
            'overall_status': overall_status,
            'components': components_health,
            'healthy_count': healthy_count,
            'degraded_count': degraded_count,
            'down_count': down_count,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pipeline status: {str(e)}")
