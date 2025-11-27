"""
ML-Based Decision Engine for AWS Spot Instance Optimization
===========================================================

This module provides a machine learning-based decision engine that uses
trained ML models to make intelligent decisions about when to switch
between spot instances and on-demand instances.

Features:
- Dynamic model loading from model directory
- Pluggable architecture for custom ML models
- Graceful fallback to rule-based decisions when ML models unavailable
- Model registry integration for tracking loaded models
- Comprehensive logging and error handling

Usage:
    1. Place your trained ML models (.pkl, .h5, etc.) in the models directory
    2. Implement the load() method to load your specific models
    3. Implement the _ml_based_decision() method with your prediction logic
    4. The engine will automatically fall back to rule-based decisions if models fail

Example:
    ```python
    import joblib

    engine = MLBasedDecisionEngine(model_dir='./models', db_connection_func=get_db)
    engine.load()

    decision = engine.make_decision(
        agent_data={'current_mode': 'spot', 'instance_type': 't3.medium'},
        pricing_data={'spot_price': 0.025, 'ondemand_price': 0.0416},
        market_data={'trend': 'rising'}
    )
    ```

Author: AWS Spot Optimizer Team
Version: 1.0.0
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MLBasedDecisionEngine:
    """
    ML-Based Decision Engine for Spot Instance Optimization

    This engine uses machine learning models to make intelligent decisions about
    when to switch between spot instances and on-demand instances.
    """

    version = '1.0.0'

    def __init__(self, model_dir: str, db_connection_func):
        """
        Initialize the ML-based decision engine.

        Sets up the engine with paths to ML models and database connection.
        Models are not loaded until load() is called.

        Args:
            model_dir (str): Path to directory containing ML model files
                           (.pkl, .h5, .pth, .onnx, etc.)
            db_connection_func (callable): Function that returns a database
                                          connection for querying historical data

        Attributes:
            model_dir (Path): Resolved path to model directory
            db_connection_func (callable): Database connection function
            models (dict): Dictionary of loaded model objects, keyed by model name
            models_loaded (bool): Flag indicating whether models have been loaded
        """
        self.model_dir = Path(model_dir)
        self.db_connection_func = db_connection_func
        self.models = {}  # Will store loaded models: {'model_name': model_object}
        self.models_loaded = False

        logger.info(f"ML-Based Decision Engine initialized with model_dir: {model_dir}")

    def load(self):
        """
        Load ML models from model directory

        Override this method to load your trained models:
        - Price prediction models
        - Interruption risk models
        - Cost optimization models

        Example:
            import joblib
            self.models['price_predictor'] = joblib.load(self.model_dir / 'price_model.pkl')
            self.models['risk_predictor'] = joblib.load(self.model_dir / 'risk_model.pkl')
        """
        logger.info(f"Loading ML models from {self.model_dir}...")

        # Check if model directory has any .pkl or .h5 files
        model_files = list(self.model_dir.glob('*.pkl')) + list(self.model_dir.glob('*.h5'))

        if model_files:
            logger.info(f"Found {len(model_files)} model files: {[f.name for f in model_files]}")
            logger.info("⚠️  Models found but not loaded. Implement load() method to use them.")
            # TODO: Implement model loading logic here
        else:
            logger.info("No ML model files found. Using rule-based fallback logic.")

        self.models_loaded = True
        return True

    def get_model_info(self):
        """
        Get information about loaded models

        Returns:
            list: List of dicts containing model information
        """
        models_info = []

        for model_name, model in self.models.items():
            models_info.append({
                'model_name': model_name,
                'model_type': 'sklearn' if hasattr(model, 'predict') else 'unknown',
                'version': self.version,
                'loaded_at': datetime.utcnow()
            })

        return models_info

    def make_decision(self, agent_data: Dict, pricing_data: Dict,
                     market_data: Optional[Dict] = None) -> Dict:
        """
        Make a switching decision for an agent based on current data.

        This is the main decision-making method. It uses ML models if available,
        otherwise falls back to rule-based logic for safety.

        Args:
            agent_data (dict): Agent information including:
                - instance_type: EC2 instance type (e.g., 't3.medium')
                - region: AWS region (e.g., 'us-east-1')
                - current_mode: Current mode ('spot' or 'ondemand')
                - auto_switch_enabled: Whether auto-switching is enabled
                - switching_threshold: Minimum savings % to trigger switch
            pricing_data (dict): Current pricing information including:
                - spot_price: Current spot price for instance type
                - ondemand_price: On-demand price for comparison
                - pool_id: Spot pool identifier
                - price_trend: Recent price movement direction
            market_data (dict, optional): Market conditions and historical data:
                - interruption_rate: Recent interruption frequency
                - price_volatility: Price stability metric
                - availability_score: Pool availability rating

        Returns:
            dict: Decision dictionary with the following keys:
                - decision_type (str): Action to take
                    - 'stay_spot': Keep current spot instance
                    - 'switch_to_spot': Switch from on-demand to spot
                    - 'switch_to_ondemand': Switch from spot to on-demand
                    - 'stay_ondemand': Keep current on-demand instance
                - recommended_pool_id (int|None): Pool ID to switch to (if applicable)
                - risk_score (float): Estimated interruption risk (0.0-1.0)
                - expected_savings (float): Expected hourly cost savings in dollars
                - confidence (float): Decision confidence level (0.0-1.0)
                - reason (str): Human-readable explanation of decision

        Example:
            >>> decision = engine.make_decision(
            ...     agent_data={'current_mode': 'spot', 'instance_type': 't3.medium'},
            ...     pricing_data={'spot_price': 0.025, 'ondemand_price': 0.0416}
            ... )
            >>> print(decision['decision_type'])
            'stay_spot'
        """
        # If ML models are loaded, use them for predictions
        if self.models:
            return self._ml_based_decision(agent_data, pricing_data, market_data)

        # Fallback to rule-based decision logic for safety
        logger.info("Using rule-based decision (ML models not loaded)")
        return self._rule_based_decision(agent_data, pricing_data)

    def _ml_based_decision(self, agent_data, pricing_data, market_data):
        """
        ML-based decision logic

        TODO: Implement your ML prediction pipeline here:
        1. Feature engineering from agent_data, pricing_data, market_data
        2. Run predictions through loaded models
        3. Combine predictions to make final decision
        """
        logger.info("⚠️  ML-based decision not implemented. Using rule-based fallback.")
        return self._rule_based_decision(agent_data, pricing_data)

    def _rule_based_decision(self, agent_data: Dict, pricing_data: Dict) -> Dict:
        """
        Simple rule-based decision logic (fallback when ML models not available).

        This provides safe, conservative decision-making using simple heuristics
        based on spot/on-demand price ratio. It ensures the system remains
        functional even when ML models fail or are not available.

        Decision Rules:
        1. If spot price > 80% of on-demand: Switch to on-demand (poor savings)
        2. If spot price < 70% of on-demand: Switch to spot (good savings)
        3. Otherwise: Stay in current mode (adequate but not compelling)

        Args:
            agent_data: Agent configuration and current state
            pricing_data: Current pricing information

        Returns:
            Decision dictionary with recommendation and reasoning
        """
        current_mode = agent_data.get('current_mode', 'on-demand')
        spot_price = pricing_data.get('spot_price', 0)
        ondemand_price = pricing_data.get('ondemand_price', 0)

        # Validation: Can't make decision without pricing data
        if ondemand_price == 0 or spot_price == 0:
            logger.warning("Insufficient pricing data for decision making")
            return {
                'decision_type': 'stay_spot' if current_mode == 'spot' else 'stay_ondemand',
                'recommended_pool_id': None,
                'risk_score': 0.0,
                'expected_savings': 0.0,
                'confidence': 0.5,
                'reason': 'Insufficient pricing data - staying in current mode for safety'
            }

        # Calculate savings percentage (how much cheaper spot is vs on-demand)
        savings_percent = ((ondemand_price - spot_price) / ondemand_price) * 100
        hourly_savings = ondemand_price - spot_price

        # Rule 1: If spot price is > 80% of on-demand, switch to on-demand
        # Reasoning: Less than 20% savings doesn't justify interruption risk
        if spot_price / ondemand_price > 0.8:
            return {
                'decision_type': 'switch_to_ondemand',
                'recommended_pool_id': None,
                'risk_score': 0.6,
                'expected_savings': 0.0,
                'confidence': 0.7,
                'reason': f'Spot price too high (only {savings_percent:.1f}% savings) - switching to on-demand for stability'
            }

        # Rule 2: If spot price offers >30% savings, recommend spot
        # Reasoning: 30%+ savings justifies the interruption risk
        if savings_percent > 30 and current_mode != 'spot':
            return {
                'decision_type': 'switch_to_spot',
                'recommended_pool_id': pricing_data.get('pool_id'),
                'risk_score': 0.2,  # Assume low risk for good pricing
                'expected_savings': hourly_savings,
                'confidence': 0.8,
                'reason': f'Excellent savings opportunity ({savings_percent:.1f}% cheaper than on-demand, ${hourly_savings:.4f}/hour)'
            }

        # Rule 3: Stay with current mode
        # Reasoning: Savings are adequate but not compelling enough to switch
        return {
            'decision_type': 'stay_spot' if current_mode == 'spot' else 'stay_ondemand',
            'recommended_pool_id': pricing_data.get('pool_id') if current_mode == 'spot' else None,
            'risk_score': 0.3,
            'expected_savings': max(0, hourly_savings),
            'confidence': 0.6,
            'reason': f'Current mode is optimal ({savings_percent:.1f}% savings, ${abs(hourly_savings):.4f}/hour)'
        }


# Alias for backward compatibility
MLBasedEngine = MLBasedDecisionEngine
