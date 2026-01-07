"""
ML Model Server (MOD-AI-01)
Predicts Spot interruption probability using trained ML models
"""
import logging
import pickle
import os
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from redis import Redis

from backend.models.ml_model import MLModel
from backend.core.config import settings

logger = logging.getLogger(__name__)


class MLModelServer:
    """
    MOD-AI-01: Serves ML model predictions for Spot interruption forecasting

    Responsibilities:
    - Load trained models from disk
    - Predict interruption probability
    - Hot-reload models when new versions are promoted
    - Validate model contracts
    """

    def __init__(self, db: Session, redis_client: Redis):
        self.db = db
        self.redis = redis_client
        self.current_model = None
        self.model_version = None
        self._load_production_model()

    def predict_interruption_risk(
        self,
        instance_type: str,
        availability_zone: str,
        spot_price_history: list,
        region: str = "us-east-1"
    ) -> Dict[str, Any]:
        """
        Predict Spot interruption probability

        Args:
            instance_type: EC2 instance type (e.g., "c5.xlarge")
            availability_zone: AZ (e.g., "us-east-1a")
            spot_price_history: List of recent Spot prices [0.45, 0.42, 0.48]
            region: AWS region

        Returns:
            {
                "prediction_id": "uuid-1234",
                "interruption_probability": 0.85,  # 0-1
                "confidence_score": 0.92,  # 0-1
                "recommended_action": "AVOID",  # SAFE, CAUTION, AVOID
                "model_version": "v1.2.0",
                "timestamp": "2026-01-02T10:00:00Z"
            }
        """
        logger.info(f"[MOD-AI-01] Predicting interruption risk for {instance_type} in {availability_zone}")

        # If no model loaded, use fallback heuristics
        if self.current_model is None:
            return self._fallback_prediction(instance_type, availability_zone, spot_price_history)

        try:
            # Prepare feature vector
            features = self._prepare_features(instance_type, availability_zone, spot_price_history)

            # Make prediction
            probability = float(self.current_model.predict_proba([features])[0][1])
            confidence = 0.85  # Simplified - in production, use model's confidence score

            # Determine recommendation
            if probability < 0.2:
                recommendation = "SAFE"
            elif probability < 0.5:
                recommendation = "CAUTION"
            else:
                recommendation = "AVOID"

            result = {
                "prediction_id": f"pred-{datetime.utcnow().timestamp()}",
                "interruption_probability": round(probability, 3),
                "confidence_score": round(confidence, 2),
                "recommended_action": recommendation,
                "model_version": self.model_version or "v1.0.0",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            logger.info(f"[MOD-AI-01] Prediction: {probability:.3f} ({recommendation})")
            return result

        except Exception as e:
            logger.error(f"[MOD-AI-01] Prediction failed: {str(e)}, using fallback")
            return self._fallback_prediction(instance_type, availability_zone, spot_price_history)

    def promote_model_to_production(self, model_id: str) -> Dict[str, Any]:
        """
        Promote a tested model to production

        Args:
            model_id: UUID of the ML model to promote

        Returns:
            {"success": True, "model_version": "v1.2.0", "message": "Model promoted"}
        """
        logger.info(f"[MOD-AI-01] Promoting model {model_id} to production")

        # Update database
        model = self.db.query(MLModel).filter(MLModel.id == model_id).first()
        if not model:
            return {"success": False, "error": "Model not found"}

        # Demote current production model
        current_prod = self.db.query(MLModel).filter(MLModel.status == "production").all()
        for m in current_prod:
            m.status = "retired"

        # Promote new model
        model.status = "production"
        model.validated_at = datetime.utcnow()
        self.db.commit()

        # Broadcast Redis event for hot reload
        self.redis.publish("model:update", model_id)

        # Reload model in this instance
        self._load_production_model()

        logger.info(f"[MOD-AI-01] Model {model.version} promoted to production")
        return {
            "success": True,
            "model_version": model.version,
            "message": "Model promoted and hot-reloaded"
        }

    def validate_model_contract(self, model_path: str) -> Dict[str, Any]:
        """
        Validate that a model matches the v1.0 contract

        Args:
            model_path: Path to the pickle file

        Returns:
            {"valid": True, "errors": []}
        """
        logger.info(f"[MOD-AI-01] Validating model contract for {model_path}")

        try:
            # Load model
            with open(model_path, 'rb') as f:
                model = pickle.load(f)

            # Test with sample input
            test_features = self._prepare_features("c5.xlarge", "us-east-1a", [0.45, 0.42, 0.48])

            # Check if model can predict
            prediction = model.predict_proba([test_features])

            # Validate output shape
            if prediction.shape != (1, 2):  # Binary classification
                return {"valid": False, "errors": ["Invalid output shape"]}

            # Check probability range
            prob = prediction[0][1]
            if prob < 0 or prob > 1:
                return {"valid": False, "errors": ["Probability out of range [0, 1]"]}

            logger.info(f"[MOD-AI-01] Model contract validation passed")
            return {"valid": True, "errors": []}

        except Exception as e:
            logger.error(f"[MOD-AI-01] Model validation failed: {str(e)}")
            return {"valid": False, "errors": [str(e)]}

    # Private methods

    def _load_production_model(self):
        """Load the current production model from disk"""
        try:
            # Query production model from database
            prod_model = self.db.query(MLModel).filter(MLModel.status == "production").first()

            if prod_model and os.path.exists(prod_model.file_path):
                with open(prod_model.file_path, 'rb') as f:
                    self.current_model = pickle.load(f)
                self.model_version = prod_model.version
                logger.info(f"[MOD-AI-01] Loaded production model {prod_model.version}")
            else:
                logger.warning(f"[MOD-AI-01] No production model found, using fallback heuristics")
                self.current_model = None

        except Exception as e:
            logger.error(f"[MOD-AI-01] Failed to load model: {str(e)}")
            self.current_model = None

    def _prepare_features(self, instance_type: str, az: str, price_history: list) -> list:
        """Prepare feature vector for model input"""
        now = datetime.utcnow()

        # Extract features
        instance_family = instance_type.split('.')[0]  # e.g., "c5"
        instance_size = instance_type.split('.')[1] if '.' in instance_type else "large"

        # Encode instance family (simplified - in production, use one-hot encoding)
        family_map = {"c5": 0, "m5": 1, "r5": 2, "t3": 3}
        family_encoded = family_map.get(instance_family, 0)

        # Encode size
        size_map = {"large": 0, "xlarge": 1, "2xlarge": 2, "4xlarge": 3}
        size_encoded = size_map.get(instance_size, 0)

        # AZ encoded (simplified)
        az_encoded = ord(az[-1]) - ord('a')  # 'a'=0, 'b'=1, etc.

        # Price features
        avg_price = sum(price_history) / len(price_history) if price_history else 0.5
        price_volatility = max(price_history) - min(price_history) if len(price_history) > 1 else 0

        # Temporal features
        hour_of_day = now.hour
        day_of_week = now.weekday()

        # Feature vector (matches training data format)
        features = [
            family_encoded,
            size_encoded,
            az_encoded,
            avg_price,
            price_volatility,
            hour_of_day,
            day_of_week
        ]

        return features

    def _fallback_prediction(self, instance_type: str, az: str, price_history: list) -> Dict[str, Any]:
        """Static heuristic prediction when ML model unavailable"""
        # Static risk scores based on AWS Spot Advisor data
        base_risks = {
            "c5.large": 0.05,
            "c5.xlarge": 0.08,
            "m5.large": 0.12,
            "m5.xlarge": 0.15,
            "r5.large": 0.10,
            "r5.xlarge": 0.18,
            "t3.medium": 0.03,
        }

        probability = base_risks.get(instance_type, 0.20)

        # Adjust for price volatility
        if len(price_history) > 1:
            volatility = (max(price_history) - min(price_history)) / sum(price_history)
            probability += volatility * 0.2  # Add up to 20% risk for high volatility

        probability = min(probability, 0.99)

        recommendation = "SAFE" if probability < 0.2 else "CAUTION" if probability < 0.5 else "AVOID"

        return {
            "prediction_id": f"fallback-{datetime.utcnow().timestamp()}",
            "interruption_probability": round(probability, 3),
            "confidence_score": 0.60,  # Lower confidence for heuristics
            "recommended_action": recommendation,
            "model_version": "fallback-heuristic-v1",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


def get_ml_model_server(db: Session, redis_client: Redis) -> MLModelServer:
    """Get ML Model Server instance"""
    return MLModelServer(db, redis_client)
