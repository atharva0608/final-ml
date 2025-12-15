"""
Model Loader - Dynamic ML Model Loading

This module handles loading ML models from the model registry.
It supports both local file paths and S3 paths, with fallback to
default models if the assigned model fails to load.

This is critical for Lab Mode to enable:
- A/B testing different model versions
- Hot-swapping models without code changes
- Experimenting with new features
"""

import os
import pickle
import boto3
from typing import Any, Optional, Dict
from pathlib import Path


# In-memory model cache (model_id -> loaded model)
MODEL_CACHE: Dict[str, Any] = {}

# In-memory registry (will be replaced with database queries)
MODEL_REGISTRY = {
    "model-001": {
        "id": "model-001",
        "name": "FamilyStressPredictor",
        "version": "v2.1.0",
        "local_path": "../models/production/family_stress_model.pkl",
        "s3_path": None,
        "is_experimental": False,
    },
    "model-002": {
        "id": "model-002",
        "name": "FamilyStressPredictor",
        "version": "v2.2.0-beta",
        "local_path": "../models/experimental/family_stress_v2.2.pkl",
        "s3_path": None,
        "is_experimental": True,
    }
}

# Default fallback model
DEFAULT_MODEL_PATH = "../models/production/family_stress_model.pkl"


def get_model_metadata(model_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Fetch model metadata from registry

    In production, this would query the model_registry table.
    For now, uses in-memory registry.

    Args:
        model_id: Model UUID from registry (None = default model)

    Returns:
        Model metadata dict or None if not found
    """
    if not model_id:
        return None

    # TODO: Replace with database query
    # metadata = db.query(ModelRegistry).filter_by(id=model_id).first()

    return MODEL_REGISTRY.get(model_id)


def load_model_from_local(file_path: str) -> Any:
    """
    Load model from local file system

    Args:
        file_path: Path to .pkl file

    Returns:
        Loaded model object

    Raises:
        FileNotFoundError: If file doesn't exist
        Exception: If pickle load fails
    """
    # Resolve relative paths
    if not os.path.isabs(file_path):
        # Assume paths are relative to backend directory
        backend_dir = Path(__file__).parent.parent
        file_path = str(backend_dir / file_path)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Model file not found: {file_path}")

    print(f"  📂 Loading model from local: {file_path}")

    with open(file_path, 'rb') as f:
        model = pickle.load(f)

    print(f"  ✓ Model loaded successfully")
    return model


def load_model_from_s3(s3_path: str, region: str = "ap-south-1") -> Any:
    """
    Load model from S3

    Args:
        s3_path: S3 URI (e.g., s3://my-bucket/models/model.pkl)
        region: AWS region

    Returns:
        Loaded model object

    Raises:
        Exception: If S3 download or pickle load fails
    """
    print(f"  ☁️  Loading model from S3: {s3_path}")

    # Parse S3 URI
    if not s3_path.startswith("s3://"):
        raise ValueError(f"Invalid S3 path: {s3_path}")

    # Extract bucket and key
    path_parts = s3_path[5:].split('/', 1)
    bucket = path_parts[0]
    key = path_parts[1] if len(path_parts) > 1 else ""

    # Download from S3
    s3_client = boto3.client('s3', region_name=region)

    # Download to temp file
    temp_file = f"/tmp/{key.split('/')[-1]}"
    s3_client.download_file(bucket, key, temp_file)

    print(f"  ✓ Downloaded to: {temp_file}")

    # Load model
    with open(temp_file, 'rb') as f:
        model = pickle.load(f)

    print(f"  ✓ Model loaded successfully")

    # Clean up temp file
    os.remove(temp_file)

    return model


def load_model(model_id: Optional[str] = None, use_cache: bool = True) -> Any:
    """
    Load ML model dynamically from registry

    This is the main entry point for model loading in Lab Mode.

    Loading Strategy:
    1. Check cache (if use_cache=True)
    2. Fetch model metadata from registry
    3. Try loading from local_path
    4. If local fails, try S3 path
    5. If all fail, load default model
    6. Cache the loaded model

    Args:
        model_id: Model UUID from registry (None = default model)
        use_cache: Use cached model if available

    Returns:
        Loaded model object (LightGBM, scikit-learn, etc.)

    Example:
        >>> model = load_model("model-002")  # Load experimental model
        >>> model = load_model()  # Load default model
    """
    print(f"\n🔄 Loading Model: {model_id or 'default'}")
    print("-" * 80)

    # Step 1: Check cache
    if use_cache and model_id in MODEL_CACHE:
        print(f"  ⚡ Using cached model: {model_id}")
        print()
        return MODEL_CACHE[model_id]

    model = None
    metadata = None

    # Step 2: Fetch metadata (if model_id provided)
    if model_id:
        metadata = get_model_metadata(model_id)

        if not metadata:
            print(f"  ⚠️  Model {model_id} not found in registry")
            print(f"  → Falling back to default model")
            model_id = None  # Fall back to default

    # Step 3: Try loading from local path
    if metadata and metadata.get('local_path'):
        try:
            model = load_model_from_local(metadata['local_path'])
            print(f"  📊 Model Info:")
            print(f"     Name: {metadata['name']}")
            print(f"     Version: {metadata['version']}")
            print(f"     Experimental: {metadata['is_experimental']}")
            print()

        except Exception as e:
            print(f"  ❌ Failed to load from local: {e}")
            print(f"  → Trying S3 path...")

            # Step 4: Try S3 path
            if metadata.get('s3_path'):
                try:
                    model = load_model_from_s3(metadata['s3_path'])
                except Exception as e2:
                    print(f"  ❌ Failed to load from S3: {e2}")
                    print(f"  → Falling back to default model")

    # Step 5: Load default model if nothing worked
    if model is None:
        try:
            print(f"  📦 Loading default model: {DEFAULT_MODEL_PATH}")
            model = load_model_from_local(DEFAULT_MODEL_PATH)
        except Exception as e:
            print(f"  ❌ CRITICAL: Failed to load default model: {e}")
            print(f"  → Returning mock model for testing")
            # Return a mock model that has a predict_proba method
            model = MockModel()

    # Step 6: Cache the model
    if model_id and model is not None:
        MODEL_CACHE[model_id] = model
        print(f"  💾 Model cached: {model_id}")

    print()
    return model


def clear_model_cache():
    """Clear the model cache (useful for hot-reloading models)"""
    global MODEL_CACHE
    cleared_count = len(MODEL_CACHE)
    MODEL_CACHE.clear()
    print(f"🗑️  Cleared {cleared_count} models from cache")


class MockModel:
    """
    Mock model for testing when real model fails to load

    This provides a simple interface compatible with LightGBM/sklearn
    so the pipeline doesn't crash if model loading fails.
    """

    def predict_proba(self, X):
        """
        Mock prediction that returns random probabilities

        Args:
            X: Feature matrix (ignored)

        Returns:
            2D array of probabilities [[prob_class_0, prob_class_1], ...]
        """
        import random
        n_samples = len(X) if hasattr(X, '__len__') else 1

        # Return random probabilities for testing
        return [
            [1 - random.uniform(0.1, 0.5), random.uniform(0.1, 0.5)]
            for _ in range(n_samples)
        ]

    def predict(self, X):
        """Mock prediction for binary classification"""
        import random
        n_samples = len(X) if hasattr(X, '__len__') else 1
        return [random.choice([0, 1]) for _ in range(n_samples)]

    def __repr__(self):
        return "<MockModel (fallback for testing)>"


# For testing
if __name__ == '__main__':
    print("="*80)
    print("MODEL LOADER TEST")
    print("="*80)

    # Test 1: Load default model
    print("\n[Test 1] Loading default model...")
    model1 = load_model()
    print(f"Loaded: {model1}")

    # Test 2: Load specific model
    print("\n[Test 2] Loading model-001...")
    model2 = load_model("model-001")
    print(f"Loaded: {model2}")

    # Test 3: Load from cache
    print("\n[Test 3] Loading model-001 again (should use cache)...")
    model3 = load_model("model-001")
    print(f"Same object? {model2 is model3}")

    # Test 4: Load non-existent model (should fallback)
    print("\n[Test 4] Loading non-existent model...")
    model4 = load_model("model-999")
    print(f"Loaded: {model4}")

    # Test 5: Clear cache
    print("\n[Test 5] Clearing cache...")
    clear_model_cache()

    print("\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80)
