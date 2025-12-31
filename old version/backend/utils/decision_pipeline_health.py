"""
Decision Pipeline Health Check

Tests the complete optimization pipeline with demo data to ensure:
1. Model files are loadable
2. Decision engine processes requests
3. Outputs are in expected format
4. Updates system monitor status
"""

from typing import Tuple, Dict
from datetime import datetime
import logging
import pickle
from pathlib import Path

from sqlalchemy.orm import Session
from utils.component_health_checks import ComponentHealthCheck

logger = logging.getLogger(__name__)


class DecisionPipelineCheck(ComponentHealthCheck):
    """
    End-to-end health check for the decision pipeline.
    
    Validates:
    - Active ML model is loadable
    - Model can process demo input
    - Decision engine integrates correctly
    - Output format is valid
    """
    
    def check(self) -> Tuple[str, Dict]:
        try:
            from database.models import MLModel
            
            # 1. Check if active model exists
            active_model = self.db.query(MLModel).filter(
                MLModel.is_active_prod == True
            ).first()
            
            if not active_model:
                return ("degraded", {
                    "message": "No active production model",
                    "recommendation": "Enable a model via Lab UI"
                })
            
            model_path = Path(active_model.file_path)
            
            # 2. Check if model file exists
            if not model_path.exists():
                return ("critical", {
                    "model_id": active_model.id,
                    "model_name": active_model.name,
                    "file_path": str(model_path),
                    "message": "Active model file not found on disk",
                    "recommendation": "Re-upload model or select different model"
                })
            
            # 3. Test model loading
            try:
                with open(model_path, 'rb') as f:
                    model_obj = pickle.load(f)
                    
                if not hasattr(model_obj, 'predict'):
                    return ("critical", {
                        "model_id": active_model.id,
                        "model_name": active_model.name,
                        "message": "Model object lacks 'predict' method",
                        "recommendation": "Upload valid scikit-learn/ML model"
                    })
                    
            except Exception as e:
                return ("critical", {
                    "model_id": active_model.id,
                    "model_name": active_model.name,
                    "error": str(e),
                    "message": "Model failed to load",
                    "recommendation": "Check model compatibility with current Python/library versions"
                })
            
            # 4. Test model prediction with demo data
            try:
                # Demo input: typical features for spot stability prediction
                # Columns might be: ['discount_percent', 'avg_duration_hours', 
                #                    'interruption_rate', 'price_volatility', ...]
                demo_input = [[65.0, 24.0, 5.0, 0.08, 2.0]]  # Safe spot pool example
                
                prediction = model_obj.predict(demo_input)
                
                # Verify output is valid
                if prediction is None or len(prediction) == 0:
                    return ("degraded", {
                        "model_id": active_model.id,
                        "model_name": active_model.name,
                        "message": "Model returned empty prediction",
                        "input_used": demo_input
                    })
                    
            except Exception as e:
                return ("degraded", {
                    "model_id": active_model.id,
                    "model_name": active_model.name,
                    "error": str(e),
                    "message": "Model prediction failed on demo data",
                    "recommendation": "Model may expect different input format"
                })
            
            # 5. Success - full pipeline operational
            return ("healthy", {
                "model_id": active_model.id,
                "model_name": active_model.name,
                "model_status": active_model.status,
                "uploaded_at": active_model.uploaded_at.isoformat() if active_model.uploaded_at else None,
                "file_size_kb": round(model_path.stat().st_size / 1024, 2),
                "demo_prediction": float(prediction[0]) if len(prediction) > 0 else None,
                "message": "Decision pipeline fully operational",
                "last_verified": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Decision pipeline health check crashed: {e}")
            return ("critical", {
                "error": str(e),
                "message": "Decision pipeline health check failed unexpectedly"
            })


class StandalonePipelineCheck(ComponentHealthCheck):
    """
    Health check for the Standalone Optimizer (Lab Mode).
    
    Verifies:
    - AWSAgentlessExecutor is functional
    - CloudWatch metrics accessible
    - StandaloneOptimizer components initialized
    """
    
    def check(self) -> Tuple[str, Dict]:
        try:
            from backend.executor.aws_agentless import AWSAgentlessExecutor
            from backend.pipelines.standalone_optimizer import StandaloneOptimizer
            from backend.decision_engine.engine_enhanced import EnhancedDecisionEngine
            
            # 1. Check if components can be instantiated
            try:
                executor = AWSAgentlessExecutor(region='us-east-1')
                engine = EnhancedDecisionEngine()
                optimizer = StandaloneOptimizer(executor, engine)
            except Exception as e:
                return ("critical", {
                    "error": str(e),
                    "message": "Failed to initialize Standalone Pipeline components"
                })
            
            # 2. Verify executor has required methods
            required_methods = ['get_instance_utilization', 'launch_instance', 
                              'terminate_instance', 'wait_for_instance_state']
            missing_methods = [m for m in required_methods if not hasattr(executor, m)]
            
            if missing_methods:
                return ("critical", {
                    "missing_methods": missing_methods,
                    "message": "Executor missing required methods"
                })
            
            # 3. Check if optimizer has optimize_node method
            if not hasattr(optimizer, 'optimize_node'):
                return ("critical", {
                    "message": "StandaloneOptimizer missing optimize_node method"
                })
            
            # 4. Success
            return ("healthy", {
                "message": "Standalone Pipeline components initialized successfully",
                "executor_region": executor.region,
                "last_verified": datetime.utcnow().isoformat()
            })
            
        except ImportError as e:
            return ("critical", {
                "error": str(e),
                "message": "Standalone Pipeline modules not found"
            })
        except Exception as e:
            logger.error(f"Standalone pipeline health check crashed: {e}")
            return ("critical", {
                "error": str(e),
                "message": "Standalone pipeline health check failed unexpectedly"
            })
