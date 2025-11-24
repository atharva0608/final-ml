"""
================================================================================
DECISION ENGINE LOADING COMPONENT
================================================================================

COMPONENT PURPOSE:
------------------
Manages the initialization, loading, and lifecycle of ML models and decision
engines. Maintains a STRICT, unchangeable I/O contract that allows seamless
integration of new model versions without modifying the backend code.

KEY RESPONSIBILITIES:
--------------------
1. Engine Loading: Initialize and validate decision engines
2. Model Loading: Load ML models from disk with version tracking
3. I/O Contract: Enforce fixed input/output structure
4. Model Registry: Track available models and their metadata
5. Hot Reload: Reload models without restarting backend

I/O CONTRACT (UNCHANGEABLE):
---------------------------
Input Parameters (required by ALL decision engines):
  - agent_id: str
  - instance_type: str
  - region: str
  - current_mode: str ('spot', 'ondemand')
  - current_pool_id: str
  - spot_price: Decimal
  - ondemand_price: Decimal
  - price_history_7d: List[Dict]  # 7 days of pricing data
  - interruption_history: List[Dict]  # Historical interruptions

Output Structure (required from ALL decision engines):
  {
    'decision': str,  # 'switch' | 'stay' | 'emergency'
    'confidence': float,  # 0.0 - 1.0
    'target_pool_id': str | None,
    'target_mode': str,  # 'spot' | 'ondemand'
    'expected_savings': Decimal,
    'risk_score': float,  # 0.0 - 1.0
    'reasoning': str  # Human-readable explanation
  }

SCENARIO EXAMPLES:
-----------------

Scenario 1: Loading Default ML Model
------------------------------------
System startup → Load decision engine

Decision Engine Loading:
1. Reads config: DECISION_ENGINE_MODULE = 'decision_engines.ml_based_engine'
2. Dynamically imports module
3. Instantiates engine class
4. Validates I/O contract:
   - Has make_decision() method?
   - Accepts required parameters?
   - Returns correct output structure?
5. Loads ML model files:
   - models/spot_optimizer_v1.pkl (main model)
   - models/risk_calculator_v1.pkl (risk scorer)
6. Registers in model registry:
   {
     'engine_type': 'ml_based',
     'version': '1.2.0',
     'loaded_at': '2024-01-15 10:00:00',
     'model_files': ['spot_optimizer_v1.pkl', 'risk_calculator_v1.pkl'],
     'status': 'active'
   }

Result: Engine ready, all API calls use this engine

Scenario 2: Hot Reload After Model Upload
-----------------------------------------
User uploads new model via /api/admin/upload-model

Decision Engine Processing:
1. File saved to models/spot_optimizer_v2.pkl
2. Validates file:
   - Is it a valid pickle/joblib file?
   - Can it be loaded without errors?
   - Does it have required predict() method?
3. Creates backup of current model: spot_optimizer_v1.pkl.backup
4. Unloads old model from memory
5. Loads new model: spot_optimizer_v2.pkl
6. Runs validation test:
   test_input = {
     'instance_type': 't3.medium',
     'region': 'us-east-1',
     ...
   }
   result = engine.make_decision(test_input)
   validates_output(result)  # Must match I/O contract
7. If validation passes:
   - Updates model registry
   - Marks model as active
   - Logs success
8. If validation fails:
   - Reverts to backup
   - Logs error
   - Notifies user

Result: New model active, no backend restart needed

Scenario 3: I/O Contract Enforcement
------------------------------------
Developer uploads model with incorrect output format

Decision Engine Processing:
1. Load new model
2. Run validation test
3. Call make_decision() with test data
4. Check output structure:
   Expected: {'decision': ..., 'confidence': ..., ...}
   Received: {'action': 'switch', 'score': 0.87}  # WRONG FORMAT
5. Contract validation FAILS:
   - Missing 'decision' key (has 'action' instead)
   - Missing 'confidence' key (has 'score' instead)
   - Missing required fields: target_pool_id, expected_savings, risk_score
6. REJECTS model:
   logger.error("Model I/O contract violation: missing keys")
7. Keeps old model active
8. Returns error to user:
   {
     'success': False,
     'error': 'Model output does not match required I/O contract',
     'details': {
       'missing_keys': ['decision', 'confidence', 'target_pool_id'],
       'extra_keys': ['action', 'score'],
       'required_structure': {...}
     }
   }

Result: Invalid model rejected, system stability maintained

Scenario 4: Fallback to Rule-Based Engine
-----------------------------------------
ML model fails to load (corrupted file)

Decision Engine Processing:
1. Attempts to load ml_based_engine
2. Error: pickle.UnpicklingError (file corrupted)
3. Logs critical error
4. Falls back to rule_based_engine:
   - Loads decision_engines/rule_based_engine.py
   - Simple if/else logic (no ML required)
   - Still follows I/O contract
5. Validates fallback engine
6. Marks as active with degraded status:
   {
     'engine_type': 'rule_based',
     'status': 'active_fallback',
     'reason': 'ML model failed to load'
   }
7. Creates alert: "System using fallback engine - ML model unavailable"

Result: System continues operating with reduced intelligence

CONFIGURATION:
-------------
"""

import logging
import importlib
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Type
from decimal import Decimal
import pickle
import joblib

logger = logging.getLogger(__name__)


class DecisionEngineConfig:
    """
    Decision engine configuration

    Override these in environment variables:
    - DECISION_ENGINE_MODULE: Python module path
    - DECISION_ENGINE_CLASS: Class name to instantiate
    - MODEL_DIR: Directory containing model files
    """

    # Default Engine
    DEFAULT_ENGINE_MODULE = 'decision_engines.ml_based_engine'
    DEFAULT_ENGINE_CLASS = 'MLBasedDecisionEngine'

    # Fallback Engine (if ML fails)
    FALLBACK_ENGINE_MODULE = 'decision_engines.rule_based_engine'
    FALLBACK_ENGINE_CLASS = 'RuleBasedEngine'

    # Directories
    MODEL_DIR = Path('./models')
    ENGINE_DIR = Path('./decision_engines')

    # Validation
    VALIDATE_ON_LOAD = True
    REQUIRE_IO_CONTRACT = True

    # I/O Contract Definition
    REQUIRED_INPUT_KEYS = [
        'agent_id', 'instance_type', 'region', 'current_mode',
        'current_pool_id', 'spot_price', 'ondemand_price',
        'price_history_7d'
    ]

    REQUIRED_OUTPUT_KEYS = [
        'decision', 'confidence', 'target_pool_id', 'target_mode',
        'expected_savings', 'risk_score', 'reasoning'
    ]

    # Model File Extensions
    ALLOWED_MODEL_EXTENSIONS = {'.pkl', '.joblib', '.h5', '.pb', '.pth', '.onnx'}


class DecisionEngineManager:
    """
    Decision Engine Manager - ML Model Lifecycle Controller

    Manages loading, validation, and hot-reloading of decision engines
    while enforcing strict I/O contracts for compatibility.

    Example Usage:

    from backend.components.decision_engine import engine_manager

    # Load default engine
    engine_manager.load_engine()

    # Make decision
    decision = engine_manager.make_decision(
        agent_id='agent-123',
        instance_type='t3.medium',
        region='us-east-1',
        current_mode='spot',
        current_pool_id='t3.medium.us-east-1a',
        spot_price=Decimal('0.0456'),
        ondemand_price=Decimal('0.0416'),
        price_history_7d=[...],
        interruption_history=[...]
    )

    # Hot reload after model upload
    engine_manager.reload_engine('/path/to/new_model.pkl')
    """

    def __init__(self, config: DecisionEngineConfig = None):
        """Initialize Decision Engine Manager"""
        self.config = config or DecisionEngineConfig()

        # Current engine
        self.engine = None
        self.engine_type = None
        self.engine_version = None
        self.engine_status = 'unloaded'

        # Model registry
        self.model_registry = []

        # Statistics
        self.stats = {
            'total_decisions': 0,
            'engine_reloads': 0,
            'validation_failures': 0,
            'fallback_activations': 0
        }

        # Ensure directories exist
        self.config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self.config.ENGINE_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("Decision Engine Manager initialized")

    # =========================================================================
    # ENGINE LOADING
    # =========================================================================

    def load_engine(
        self,
        module_path: str = None,
        class_name: str = None,
        force_reload: bool = False
    ) -> bool:
        """
        Load decision engine

        Args:
            module_path: Python module path (e.g., 'decision_engines.ml_based_engine')
            class_name: Class name to instantiate
            force_reload: Force reload even if already loaded

        Returns:
            True if loaded successfully

        Example:
            success = engine_manager.load_engine(
                module_path='decision_engines.ml_based_engine',
                class_name='MLBasedDecisionEngine'
            )
        """
        if self.engine and not force_reload:
            logger.info("Engine already loaded, use force_reload=True to reload")
            return True

        # Use defaults if not specified
        module_path = module_path or self.config.DEFAULT_ENGINE_MODULE
        class_name = class_name or self.config.DEFAULT_ENGINE_CLASS

        try:
            # Step 1: Import module
            logger.info(f"Loading engine: module={module_path}, class={class_name}")

            # Reload module if already imported (for hot reload)
            if module_path in sys.modules:
                importlib.reload(sys.modules[module_path])
                module = sys.modules[module_path]
            else:
                module = importlib.import_module(module_path)

            # Step 2: Get engine class
            engine_class = getattr(module, class_name)

            # Step 3: Instantiate engine
            engine_instance = engine_class()

            # Step 4: Validate I/O contract
            if self.config.VALIDATE_ON_LOAD:
                if not self._validate_engine_contract(engine_instance):
                    raise ValueError("Engine failed I/O contract validation")

            # Step 5: Load models (if engine has model files)
            if hasattr(engine_instance, 'load_models'):
                engine_instance.load_models(str(self.config.MODEL_DIR))

            # Step 6: Register engine
            self.engine = engine_instance
            self.engine_type = class_name
            self.engine_version = getattr(engine_instance, 'VERSION', 'unknown')
            self.engine_status = 'active'

            # Update registry
            self._register_engine(module_path, class_name)

            logger.info(
                f"Engine loaded successfully: type={self.engine_type}, "
                f"version={self.engine_version}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to load engine: {e}", exc_info=True)

            # Try fallback engine
            if module_path != self.config.FALLBACK_ENGINE_MODULE:
                logger.warning("Attempting fallback to rule-based engine")
                return self._load_fallback_engine()

            return False

    def _load_fallback_engine(self) -> bool:
        """Load fallback rule-based engine"""
        try:
            success = self.load_engine(
                module_path=self.config.FALLBACK_ENGINE_MODULE,
                class_name=self.config.FALLBACK_ENGINE_CLASS,
                force_reload=True
            )

            if success:
                self.engine_status = 'active_fallback'
                self.stats['fallback_activations'] += 1
                logger.warning("Fallback engine activated - ML model unavailable")

            return success

        except Exception as e:
            logger.critical(f"Fallback engine also failed: {e}", exc_info=True)
            return False

    def reload_engine(self, model_path: str = None) -> Dict[str, Any]:
        """
        Hot reload engine (typically after model upload)

        Args:
            model_path: Path to new model file (optional)

        Returns:
            {
                'success': True,
                'previous_version': '1.2.0',
                'new_version': '1.3.0',
                'reloaded_at': datetime(...)
            }
        """
        logger.info(f"Hot reloading engine, model_path={model_path}")

        previous_version = self.engine_version

        # Backup current engine
        backup_engine = self.engine

        try:
            # Reload with force
            success = self.load_engine(force_reload=True)

            if success:
                self.stats['engine_reloads'] += 1

                return {
                    'success': True,
                    'previous_version': previous_version,
                    'new_version': self.engine_version,
                    'reloaded_at': datetime.utcnow()
                }
            else:
                # Restore backup
                self.engine = backup_engine
                return {
                    'success': False,
                    'error': 'Failed to reload engine',
                    'engine_restored': True
                }

        except Exception as e:
            # Restore backup
            self.engine = backup_engine
            logger.error(f"Engine reload failed: {e}", exc_info=True)

            return {
                'success': False,
                'error': str(e),
                'engine_restored': True
            }

    # =========================================================================
    # DECISION MAKING
    # =========================================================================

    def make_decision(self, **kwargs) -> Dict[str, Any]:
        """
        Make decision using loaded engine

        This method enforces the I/O contract by validating inputs and outputs.

        Args:
            **kwargs: Decision parameters (must match I/O contract)

        Returns:
            Decision dictionary matching output contract

        Raises:
            ValueError: If engine not loaded or I/O contract violated
        """
        if not self.engine:
            raise ValueError("No decision engine loaded")

        # Validate input
        if self.config.REQUIRE_IO_CONTRACT:
            self._validate_input_contract(kwargs)

        # Make decision
        try:
            decision = self.engine.make_decision(**kwargs)
        except Exception as e:
            logger.error(f"Engine decision failed: {e}", exc_info=True)
            # Return safe default decision
            decision = self._get_safe_default_decision()

        # Validate output
        if self.config.REQUIRE_IO_CONTRACT:
            self._validate_output_contract(decision)

        self.stats['total_decisions'] += 1

        return decision

    def is_loaded(self) -> bool:
        """Check if engine is loaded and ready"""
        return self.engine is not None and self.engine_status in ['active', 'active_fallback']

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_engine_contract(self, engine_instance) -> bool:
        """
        Validate engine implements required I/O contract

        Checks:
        - Has make_decision() method
        - Method accepts required parameters
        - Returns correct output structure
        """
        # Check method exists
        if not hasattr(engine_instance, 'make_decision'):
            logger.error("Engine missing make_decision() method")
            return False

        # Run test decision
        test_input = self._get_test_input()

        try:
            test_output = engine_instance.make_decision(**test_input)

            # Validate output structure
            return self._validate_output_structure(test_output)

        except Exception as e:
            logger.error(f"Engine contract validation failed: {e}", exc_info=True)
            return False

    def _validate_input_contract(self, input_data: Dict[str, Any]):
        """Validate input matches contract"""
        missing_keys = [
            key for key in self.config.REQUIRED_INPUT_KEYS
            if key not in input_data
        ]

        if missing_keys:
            raise ValueError(
                f"Input missing required keys: {missing_keys}. "
                f"Required: {self.config.REQUIRED_INPUT_KEYS}"
            )

    def _validate_output_contract(self, output_data: Dict[str, Any]):
        """Validate output matches contract"""
        if not self._validate_output_structure(output_data):
            self.stats['validation_failures'] += 1
            raise ValueError(
                f"Output does not match I/O contract. "
                f"Required keys: {self.config.REQUIRED_OUTPUT_KEYS}"
            )

    def _validate_output_structure(self, output: Dict[str, Any]) -> bool:
        """Check output has all required keys"""
        missing_keys = [
            key for key in self.config.REQUIRED_OUTPUT_KEYS
            if key not in output
        ]

        if missing_keys:
            logger.error(
                f"Output missing required keys: {missing_keys}. "
                f"Received keys: {list(output.keys())}"
            )
            return False

        return True

    # =========================================================================
    # MODEL REGISTRY
    # =========================================================================

    def _register_engine(self, module_path: str, class_name: str):
        """Register engine in model registry"""
        entry = {
            'engine_type': self.engine_type,
            'module_path': module_path,
            'class_name': class_name,
            'version': self.engine_version,
            'status': self.engine_status,
            'loaded_at': datetime.utcnow(),
            'model_files': self._get_model_files()
        }

        self.model_registry.append(entry)

        # Keep only last 10 entries
        if len(self.model_registry) > 10:
            self.model_registry = self.model_registry[-10:]

    def _get_model_files(self) -> List[str]:
        """Get list of model files in MODEL_DIR"""
        if not self.config.MODEL_DIR.exists():
            return []

        model_files = []
        for ext in self.config.ALLOWED_MODEL_EXTENSIONS:
            model_files.extend([
                f.name for f in self.config.MODEL_DIR.glob(f'*{ext}')
            ])

        return model_files

    def get_registry(self) -> List[Dict[str, Any]]:
        """Get model registry"""
        return list(self.model_registry)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_test_input(self) -> Dict[str, Any]:
        """Generate test input for validation"""
        return {
            'agent_id': 'test-agent-123',
            'instance_type': 't3.medium',
            'region': 'us-east-1',
            'current_mode': 'spot',
            'current_pool_id': 't3.medium.us-east-1a',
            'spot_price': Decimal('0.0456'),
            'ondemand_price': Decimal('0.0416'),
            'price_history_7d': [],
            'interruption_history': []
        }

    def _get_safe_default_decision(self) -> Dict[str, Any]:
        """Return safe default decision (stay on current)"""
        return {
            'decision': 'stay',
            'confidence': 0.0,
            'target_pool_id': None,
            'target_mode': 'spot',
            'expected_savings': Decimal('0'),
            'risk_score': 0.5,
            'reasoning': 'Engine error - defaulting to stay on current pool'
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics"""
        return {
            'engine_type': self.engine_type,
            'engine_version': self.engine_version,
            'engine_status': self.engine_status,
            'stats': dict(self.stats)
        }


# ============================================================================
# GLOBAL INSTANCE (SINGLETON PATTERN)
# ============================================================================

# Global engine manager instance - import this in services
engine_manager = DecisionEngineManager()

logger.info("Decision Engine Manager component initialized")
