#!/usr/bin/env python3
"""
Pre-Training Validation Test

Run this locally to verify the training code before expensive SageMaker execution.
Tests: imports, model creation, small data workflow.

Usage:
    python sagemaker_migration/scripts/test_training_code.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd


def test_imports():
    """Test all required imports work."""
    print("\n1️⃣  Testing imports...")

    from src.data import chronological_split, prepare_targets

    print("    src.data")

    from src.model import HybridSpotModel

    print("    src.model")

    from src.backtest import WalkForwardBacktest

    print("    src.backtest")

    from src.visualize import ModelVisualizer

    print("    src.visualize")

    from src.data_polars import prepare_targets_polars

    print("    src.data_polars")

    import lightgbm as lgb

    print(f"    lightgbm (v{lgb.__version__})")

    import polars as pl

    print(f"    polars (v{pl.__version__})")

    return True


def test_model_creation():
    """Test model can be instantiated."""
    print("\n2️⃣  Testing model creation...")

    from src.model import HybridSpotModel

    model = HybridSpotModel(horizon=6, n_jobs=4)
    print(f"    HybridSpotModel created (horizon={model.horizon})")
    print(f"    Default threshold: {model.optimal_threshold}")

    return True


def test_small_data_workflow():
    """Test training on synthetic small data."""
    print("\n3️⃣  Testing small data workflow...")

    import lightgbm as lgb
    from src.model import HybridSpotModel

    # Create synthetic data (mimics real structure)
    np.random.seed(42)
    n_samples = 1000
    n_features = 10

    # Features
    X = pd.DataFrame(np.random.randn(n_samples, n_features), columns=[f"feature_{i}" for i in range(n_features)])

    # Targets
    df = pd.DataFrame(
        {
            "future_savings": np.random.uniform(0.3, 0.7, n_samples),
            "is_unstable": np.random.randint(0, 2, n_samples),
            "timestamp": pd.date_range("2024-01-01", periods=n_samples, freq="10min"),
        }
    )

    # Split
    train_size = int(0.7 * n_samples)
    val_size = int(0.15 * n_samples)

    train_idx = slice(0, train_size)
    val_idx = slice(train_size, train_size + val_size)
    test_idx = slice(train_size + val_size, n_samples)

    X_train, X_val, X_test = X.iloc[train_idx], X.iloc[val_idx], X.iloc[test_idx]
    train_df, val_df, test_df = df.iloc[train_idx].copy(), df.iloc[val_idx].copy(), df.iloc[test_idx].copy()

    print(f"    Synthetic data created: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # Quick regressor test
    reg_params = {
        "objective": "regression",
        "metric": "mape",
        "num_leaves": 10,
        "learning_rate": 0.1,
        "verbose": -1,
        "n_jobs": 2,
    }

    train_data = lgb.Dataset(X_train, label=train_df["future_savings"])
    val_data = lgb.Dataset(X_val, label=val_df["future_savings"], reference=train_data)

    regressor = lgb.train(
        reg_params,
        train_data,
        num_boost_round=10,
        valid_sets=[val_data],
        callbacks=[lgb.early_stopping(5, verbose=False)],
    )
    print("    LightGBM regressor trained")

    # Quick classifier test
    clf_params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "num_leaves": 10,
        "learning_rate": 0.1,
        "verbose": -1,
        "n_jobs": 2,
    }

    train_data_clf = lgb.Dataset(X_train, label=train_df["is_unstable"])
    val_data_clf = lgb.Dataset(X_val, label=val_df["is_unstable"], reference=train_data_clf)

    classifier = lgb.train(
        clf_params,
        train_data_clf,
        num_boost_round=10,
        valid_sets=[val_data_clf],
        callbacks=[lgb.early_stopping(5, verbose=False)],
    )
    print("    LightGBM classifier trained")

    # Test predictions
    pred_reg = regressor.predict(X_test)
    pred_clf = classifier.predict(X_test)

    print(f"    Predictions generated: reg_shape={pred_reg.shape}, clf_shape={pred_clf.shape}")

    return True


def test_visualization_imports():
    """Test visualization dependencies."""
    print("\n4️⃣  Testing visualization dependencies...")

    try:
        import matplotlib

        print(f"    matplotlib (v{matplotlib.__version__})")
    except ImportError:
        print("   ️ matplotlib not installed (will be installed on SageMaker)")
        return True  # Not a failure for local test

    try:
        import seaborn

        print(f"    seaborn (v{seaborn.__version__})")
    except ImportError:
        print("   ️ seaborn not installed (will be installed on SageMaker)")
        return True

    return True


def main():
    print("=" * 60)
    print("PRE-TRAINING VALIDATION TEST")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Model Creation", test_model_creation),
        ("Small Data Workflow", test_small_data_workflow),
        ("Visualization Imports", test_visualization_imports),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n    FAILED: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = " PASS" if passed else " FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n All tests passed! Safe to run on SageMaker.")
        return 0
    else:
        print("\n️ Some tests failed. Review before running on SageMaker.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
