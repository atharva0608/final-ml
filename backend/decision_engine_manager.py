"""
AWS Spot Optimizer - Decision Engine Manager
=============================================
Manages ML decision engine lifecycle and model registry
"""

import json
import logging
import importlib
from datetime import datetime

from backend.config import config
from backend.database_manager import execute_query, get_db_connection
from backend.utils import generate_uuid, log_system_event

logger = logging.getLogger(__name__)


class DecisionEngineManager:
    """Manages decision engine lifecycle and model registry"""

    def __init__(self):
        self.engine = None
        self.engine_type = None
        self.engine_version = None
        self.models_loaded = False

    def load_engine(self):
        """Load decision engine dynamically"""
        try:
            logger.info(f"Loading decision engine: {config.DECISION_ENGINE_MODULE}.{config.DECISION_ENGINE_CLASS}")

            # Import module dynamically
            module = importlib.import_module(config.DECISION_ENGINE_MODULE)
            engine_class = getattr(module, config.DECISION_ENGINE_CLASS)

            # Initialize engine
            self.engine = engine_class(
                model_dir=config.MODEL_DIR,
                db_connection_func=get_db_connection
            )

            # Load models
            self.engine.load()

            self.engine_type = config.DECISION_ENGINE_CLASS
            self.engine_version = getattr(self.engine, 'version', 'unknown')
            self.models_loaded = True

            logger.info(f"✓ Decision engine loaded: {self.engine_type} v{self.engine_version}")
            log_system_event('decision_engine_loaded', 'info',
                           f'Decision engine {self.engine_type} loaded successfully')

            # Register models in database
            self._register_models()

            return True

        except Exception as e:
            logger.warning(f"Decision engine not loaded: {e}")
            self.models_loaded = False
            return False

    def _register_models(self):
        """Register loaded models in the database"""
        if not hasattr(self.engine, 'get_model_info'):
            return

        try:
            models_info = self.engine.get_model_info()

            for model_info in models_info:
                execute_query("""
                    INSERT INTO model_registry
                    (id, model_name, model_type, version, file_path, is_active,
                     performance_metrics, config, loaded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        is_active = VALUES(is_active),
                        loaded_at = NOW()
                """, (
                    model_info.get('id', generate_uuid()),
                    model_info.get('name'),
                    model_info.get('type'),
                    model_info.get('version'),
                    model_info.get('file_path'),
                    model_info.get('is_active', True),
                    json.dumps(model_info.get('metrics', {})),
                    json.dumps(model_info.get('config', {}))
                ))

            logger.info(f"✓ Registered {len(models_info)} models in database")

        except Exception as e:
            logger.error(f"Failed to register models: {e}")

    def make_decision(self, instance: dict, pricing: dict, config_data: dict,
                     recent_switches_count: int, last_switch_time: datetime) -> dict:
        """Make switching decision using loaded engine"""
        if not self.engine or not self.models_loaded:
            return self._get_default_decision(instance)

        try:
            start_time = datetime.utcnow()

            decision = self.engine.make_decision(
                instance=instance,
                pricing=pricing,
                config=config_data,
                recent_switches_count=recent_switches_count,
                last_switch_time=last_switch_time
            )

            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Log decision
            self._log_decision(instance, decision, execution_time)

            return decision

        except Exception as e:
            logger.error(f"Decision engine error: {e}", exc_info=True)
            log_system_event('decision_error', 'error', str(e),
                           instance_id=instance.get('instance_id'))
            return self._get_default_decision(instance)

    def _get_default_decision(self, instance: dict) -> dict:
        """Return safe default decision when engine fails"""
        return {
            'instance_id': instance.get('instance_id'),
            'risk_score': 0.0,
            'recommended_action': 'stay',
            'recommended_mode': instance.get('current_mode'),
            'recommended_pool_id': instance.get('current_pool_id'),
            'expected_savings_per_hour': 0.0,
            'allowed': False,
            'reason': 'Decision engine unavailable - staying in current mode for safety'
        }

    def _log_decision(self, instance: dict, decision: dict, execution_time_ms: int):
        """Log decision to database"""
        try:
            models_used = []
            if hasattr(self.engine, 'get_models_used'):
                models_used = self.engine.get_models_used()

            execute_query("""
                INSERT INTO decision_engine_log
                (engine_type, engine_version, instance_id, input_data, output_decision,
                 execution_time_ms, models_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                self.engine_type,
                self.engine_version,
                instance.get('instance_id'),
                json.dumps(instance),
                json.dumps(decision),
                execution_time_ms,
                json.dumps(models_used)
            ))
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")


# Initialize global decision engine manager
decision_engine_manager = DecisionEngineManager()
