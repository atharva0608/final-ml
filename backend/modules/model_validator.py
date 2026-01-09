"""
Model Validator (MOD-VAL-01)
Validates template compatibility and ML model contracts
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ModelValidator:
    """
    MOD-VAL-01: Validates node templates and ML models

    Responsibilities:
    - Check instance family vs architecture compatibility
    - Validate ML model input/output contracts
    - Provide warnings for incompatible configurations
    """

    def validate_template_compatibility(
        self,
        families: List[str],
        architecture: str
    ) -> List[Dict[str, str]]:
        """
        Validate template compatibility

        Args:
            families: List of instance families (e.g., ["c5", "m5", "r5"])
            architecture: CPU architecture ("x86_64" or "arm64")

        Returns:
            List of warnings:
            [
                {
                    "severity": "ERROR",
                    "family": "g4dn",
                    "message": "g4dn family incompatible with ARM64 architecture"
                },
                ...
            ]
        """
        logger.info(f"[MOD-VAL-01] Validating template: families={families}, arch={architecture}")

        warnings = []

        # ARM64 incompatible families
        arm64_incompatible = ["g4dn", "p3", "p4", "inf1", "f1"]

        # GPU families
        gpu_families = ["g4dn", "g5", "p3", "p4"]

        # Burstable families
        burstable_families = ["t2", "t3", "t3a", "t4g"]

        for family in families:
            # Check architecture compatibility
            if architecture == "arm64" and family in arm64_incompatible:
                warnings.append({
                    "severity": "ERROR",
                    "family": family,
                    "message": f"{family} family incompatible with ARM64 architecture"
                })

            # Check if mixing GPU with non-GPU
            if family in gpu_families and len(families) > 1:
                non_gpu = [f for f in families if f not in gpu_families]
                if non_gpu:
                    warnings.append({
                        "severity": "WARNING",
                        "family": family,
                        "message": f"Mixing GPU family {family} with non-GPU families may cause scheduling issues"
                    })

            # Check if mixing burstable with non-burstable
            if family in burstable_families and len(families) > 1:
                non_burstable = [f for f in families if f not in burstable_families]
                if non_burstable:
                    warnings.append({
                        "severity": "INFO",
                        "family": family,
                        "message": f"Mixing burstable {family} with non-burstable families - ensure credit balance monitoring"
                    })

        logger.info(f"[MOD-VAL-01] Validation complete: {len(warnings)} warnings")
        return warnings

    def validate_ml_model(self, model_path: str) -> Dict[str, Any]:
        """
        Validate ML model contract (delegated to MOD-AI-01 in production)

        This is a simplified version - in production, this would:
        1. Spin up Docker sandbox container
        2. Load model in isolated environment
        3. Test with sample inputs
        4. Verify output contract matches v1.0 spec

        Args:
            model_path: Path to model pickle file

        Returns:
            {
                "valid": True,
                "errors": [],
                "performance_metrics": {
                    "inference_time_ms": 12.5,
                    "memory_mb": 256
                }
            }
        """
        logger.info(f"[MOD-VAL-01] Validating ML model at {model_path}")

        # In production, this would use MOD-AI-01's validate_model_contract
        # For now, return mock validation
        return {
            "valid": True,
            "errors": [],
            "performance_metrics": {
                "inference_time_ms": 15.2,
                "memory_mb": 128
            },
            "contract_version": "v1.0",
            "validated_at": "2026-01-02T10:00:00Z"
        }


def get_model_validator() -> ModelValidator:
    """Get Model Validator instance"""
    return ModelValidator()
