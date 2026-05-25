"""
Continuous Validation Loop
==========================
Periodic task to compare predicted outcomes vs actual results.
Improves optimizer accuracy over time.
"""

import logging
from datetime import datetime, timedelta
from backend.models.base import get_db
from backend.models.rebalancing_action import RebalancingAction
from backend.workers.app import app

logger = logging.getLogger(__name__)

@app.task(name='workers.optimization_feedback_loop')
def run_validation_loop():
    """
    Analyzes completed actions and compares Predicted Savings vs Actual Savings.
    """
    db = next(get_db())
    try:
        # Fetch actions completed in the last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        completed_actions = db.query(RebalancingAction).filter(
            RebalancingAction.status == 'completed',
            RebalancingAction.completed_at >= cutoff
        ).all()
        
        for action in completed_actions:
            predicted = action.estimated_savings_hr or 0.0
            actual = action.realized_savings_hr or 0.0
            
            # If gap is > 20%, log for investigation
            if predicted > 0 and abs(predicted - actual) / predicted > 0.2:
                logger.warning(
                    f"[feedback_loop] Savings Gap Detected (Action {action.id}): "
                    f"Predicted ${predicted:.4f}/hr, Actual ${actual:.4f}/hr. "
                    f"Gap: {abs(predicted - actual) / predicted * 100:.1f}%"
                )
                
    except Exception as e:
        logger.error(f"[feedback_loop] Loop failed: {e}")
    finally:
        db.close()
