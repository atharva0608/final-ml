"""
Test script to verify optimize_threshold method works correctly.
"""
import os
import sys

import numpy as np
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath("/Users/nisha/ECC/ML/LightGBM/spot_optimizer_v1"))

from src.model import HybridSpotModel


# Mock LightGBM Booster
class MockBooster:
    def predict(self, X):
        """Return random probabilities for testing"""
        np.random.seed(42)
        return np.random.rand(len(X))


# Create mock data
n_samples = 100
n_features = 40

X_mock = pd.DataFrame(np.random.rand(n_samples, n_features), columns=[f"feature_{i}" for i in range(n_features)])

# Create mock validation dataframe with required columns
val_df_mock = pd.DataFrame(
    {
        "timestamp": pd.date_range("2024-01-01", periods=n_samples, freq="10min"),
        "InstanceType": ["c6i.large"] * n_samples,
        "AZ": ["ap-south-1a"] * n_samples,
        "Savings": np.random.rand(n_samples) * 100,
        "SpotPrice": np.random.rand(n_samples) * 10,
        "OndemandPrice": np.random.rand(n_samples) * 15 + 10,  # Higher than SpotPrice
    }
)

# Create model instance
model = HybridSpotModel(horizon=6)
model.regressor = MockBooster()
model.classifier = MockBooster()

print("=" * 60)
print("THRESHOLD OPTIMIZATION TEST")
print("=" * 60)

try:
    # Test optimize_threshold
    print("\n1. Testing optimize_threshold with F1 metric...")
    best_threshold, best_metrics = model.optimize_threshold(X_val=X_mock, val_df=val_df_mock, metric="f1")

    print("\n Test 1 PASSED")
    print(f"  Returned threshold: {best_threshold}")
    print(f"  Type: {type(best_threshold)}")
    assert isinstance(best_threshold, (float, np.floating)), "Threshold should be a float"
    assert 0 <= best_threshold <= 1, "Threshold should be between 0 and 1"
    assert "f1" in best_metrics, "Metrics should contain F1"
    assert "precision" in best_metrics, "Metrics should contain Precision"
    assert "recall" in best_metrics, "Metrics should contain Recall"

    # Test with recall metric
    print("\n2. Testing optimize_threshold with Recall metric...")
    recall_threshold, recall_metrics = model.optimize_threshold(X_val=X_mock, val_df=val_df_mock, metric="recall")
    print("\n Test 2 PASSED")
    print(f"  Returned threshold: {recall_threshold}")

    # Test with precision metric
    print("\n3. Testing optimize_threshold with Precision metric...")
    precision_threshold, precision_metrics = model.optimize_threshold(
        X_val=X_mock, val_df=val_df_mock, metric="precision"
    )
    print("\n Test 3 PASSED")
    print(f"  Returned threshold: {precision_threshold}")

    # Check that optimization results are stored
    print("\n4. Checking that optimization results are stored...")
    assert hasattr(model, "threshold_optimization_results"), "Results should be stored"
    assert isinstance(model.threshold_optimization_results, pd.DataFrame), "Results should be a DataFrame"
    print(f"  Results shape: {model.threshold_optimization_results.shape}")
    print(f"  Columns: {list(model.threshold_optimization_results.columns)}")
    print("\n Test 4 PASSED")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ")
    print("=" * 60)

except Exception as e:
    print(f"\n TEST FAILED: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
