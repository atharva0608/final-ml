"""
ML-Based Decision Engine

This is a machine learning-based decision engine for AWS Spot instance optimization.
Upload your trained ML models to this directory to activate intelligent decision making.
"""

import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class MLBasedDecisionEngine:
    """
    ML-Based Decision Engine for Spot Instance Optimization

    This engine uses machine learning models to make intelligent decisions about
    when to switch between spot instances and on-demand instances.
    """

    version = '1.0.0'

    def __init__(self, model_dir, db_connection_func):
        """
        Initialize the ML-based decision engine

        Args:
            model_dir: Path to directory containing ML model files
            db_connection_func: Function to get database connection
        """
        self.model_dir = Path(model_dir)
        self.db_connection_func = db_connection_func
        self.models = {}
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

    def make_decision(self, agent_data, pricing_data, market_data=None):
        """
        Make a decision for an agent based on current data

        Args:
            agent_data (dict): Agent information (instance_type, region, current_mode, etc.)
            pricing_data (dict): Current pricing information
            market_data (dict, optional): Market conditions and historical data

        Returns:
            dict: Decision with keys:
                - decision_type: 'stay_spot', 'switch_to_spot', 'switch_to_ondemand'
                - recommended_pool_id: Pool to switch to (if applicable)
                - risk_score: Estimated interruption risk (0-1)
                - expected_savings: Expected cost savings
                - confidence: Decision confidence (0-1)
                - reason: Human-readable explanation
        """

        # If ML models are loaded, use them for predictions
        if self.models:
            return self._ml_based_decision(agent_data, pricing_data, market_data)

        # Fallback to rule-based decision logic
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

    def _rule_based_decision(self, agent_data, pricing_data):
        """
        Simple rule-based decision logic (fallback when ML models not available)
        """
        current_mode = agent_data.get('current_mode', 'on-demand')
        spot_price = pricing_data.get('spot_price', 0)
        ondemand_price = pricing_data.get('ondemand_price', 0)

        if ondemand_price == 0:
            return {
                'decision_type': 'stay_spot' if current_mode == 'spot' else 'stay_ondemand',
                'recommended_pool_id': None,
                'risk_score': 0.0,
                'expected_savings': 0.0,
                'confidence': 0.5,
                'reason': 'Insufficient pricing data'
            }

        # Calculate savings percentage
        savings_percent = ((ondemand_price - spot_price) / ondemand_price) * 100

        # Rule 1: If spot price is > 80% of on-demand, switch to on-demand
        if spot_price / ondemand_price > 0.8:
            return {
                'decision_type': 'switch_to_ondemand',
                'recommended_pool_id': None,
                'risk_score': 0.6,
                'expected_savings': 0.0,
                'confidence': 0.7,
                'reason': f'Spot price too high ({savings_percent:.1f}% savings only)'
            }

        # Rule 2: If spot price offers >30% savings, recommend spot
        if savings_percent > 30 and current_mode != 'spot':
            return {
                'decision_type': 'switch_to_spot',
                'recommended_pool_id': pricing_data.get('pool_id'),
                'risk_score': 0.2,
                'expected_savings': ondemand_price - spot_price,
                'confidence': 0.8,
                'reason': f'Good savings opportunity ({savings_percent:.1f}% cheaper than on-demand)'
            }

        # Rule 3: Stay with current mode
        return {
            'decision_type': 'stay_spot' if current_mode == 'spot' else 'stay_ondemand',
            'recommended_pool_id': pricing_data.get('pool_id') if current_mode == 'spot' else None,
            'risk_score': 0.3,
            'expected_savings': max(0, ondemand_price - spot_price),
            'confidence': 0.6,
            'reason': f'Current mode is optimal ({savings_percent:.1f}% savings)'
        }


# Alias for backward compatibility
MLBasedEngine = MLBasedDecisionEngine
