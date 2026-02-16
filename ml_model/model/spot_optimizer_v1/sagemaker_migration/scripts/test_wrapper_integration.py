#!/usr/bin/env python3
"""
Integration Test for train_wrapper.py

PURPOSE:
    Tests the full execution flow of train_wrapper.py without actually training models.
    Mocks LightGBM and internal modules to verify workflow logic.

WHAT IT TESTS:
    - Preprocessed parquet loading (FAST PATH)
    - Polars → Pandas conversion
    - Categorical dtype handling
    - Memory-optimized model.fit() signature
    - SageMaker environment simulation

USAGE:
    python spot_optimizer_v1/sagemaker_migration/scripts/test_wrapper_integration.py

DEPENDENCIES:
    - Real: polars, pandas, numpy
    - Mocked: lightgbm, src.model, src.backtest, src.visualize, src.data

DURATION:
    ~10 seconds

WHY RUN THIS:
    Catches integration bugs before expensive SageMaker submission.
"""
import os
import shutil
import sys
import warnings

import numpy as np
import pandas as pd
import polars as pl

warnings.filterwarnings("ignore")


def run_test():
    # 1. Setup paths
    base_dir = os.getcwd()
    test_data_dir = os.path.join(base_dir, "tmp_test_data_integ")
    model_dir = os.path.join(base_dir, "tmp_model_dir_integ")

    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir)
    if os.path.exists(model_dir):
        shutil.rmtree(model_dir)

    os.makedirs(test_data_dir)
    os.makedirs(model_dir)

    print(f"Test Data Dir: {test_data_dir}")
    print(f"Model Dir: {model_dir}")

    try:
        # 2. Create Dummy Data (Parquet)
        print("Creating dummy data...")
        n_samples = 500  # Enough for split
        df = pd.DataFrame(
            {
                "feature_1": np.random.randn(n_samples),
                "feature_2": np.random.randn(n_samples),
                "future_savings": np.random.uniform(0, 1, n_samples),
                "is_unstable": np.random.randint(0, 2, n_samples),
                "timestamp": pd.date_range("2024-01-01", periods=n_samples, freq="1h"),
                "instance_family": ["c5"] * n_samples,
                "instance_size": ["xlarge"] * n_samples,
                "AZ": ["us-east-1a"] * n_samples,
            }
        )

        # Save as parquet to match "Fast Path"
        pl.from_pandas(df).write_parquet(os.path.join(test_data_dir, "preprocessed_features.parquet"))

        # 3. Setup Env Vars
        os.environ["SM_CHANNEL_TRAINING"] = test_data_dir
        os.environ["SM_MODEL_DIR"] = model_dir

        # 4. Mock sys.argv
        sys.argv = [
            "train_wrapper.py",
            "--train",
            test_data_dir,
            "--model-dir",
            model_dir,
            "--sample_fraction",
            "1.0",
            "--horizon",
            "1",
            "--skip_backtest",
            "0",  # Ensure backtest reload path is tested
            "--num_leaves",
            "10",
            "--clf_num_leaves",
            "10",
        ]

        # 4b. Mock LightGBM and Internal Modules (Bypass libomp/install issues)
        from unittest.mock import MagicMock

        sys.modules["joblib"] = MagicMock()
        mock_lgb = MagicMock()
        mock_lgb.__version__ = "4.0.0"
        sys.modules["lightgbm"] = mock_lgb

        sys.modules["src.model"] = MagicMock()
        sys.modules["src.backtest"] = MagicMock()
        sys.modules["src.visualize"] = MagicMock()
        # We want real src.data if possible, but fine to mock if needed.
        # train_wrapper imports chronological_split from src.data
        # Let's try to mock src.data too to be safe, but we need side_effect for split if we want to test flow
        mock_data = MagicMock()

        # chronological_split returns 3 dfs
        def mock_split(df):
            return df.iloc[:10], df.iloc[10:20], df.iloc[20:]

        mock_data.chronological_split = mock_split
        mock_data.prepare_targets = MagicMock(return_value=pd.DataFrame())  # Unused if loading parquet
        sys.modules["src.data"] = mock_data

        # Mock src.data_polars imports
        mock_data_pl = MagicMock()

        def mock_split_pl_func(df):
            # Return real sliced Polars DFs (since we have real Polars in test env)
            n = df.height
            # Simple split logic for test data (total 500 rows)
            return df.slice(0, 50), df.slice(50, 50), df.slice(100, n - 100)

        mock_data_pl.chronological_split_polars = mock_split_pl_func
        mock_data_pl.prepare_targets_polars = MagicMock(side_effect=lambda df, **kwargs: df)
        sys.modules["src.data_polars"] = mock_data_pl

        # 5. Import and Run
        # Make sure current dir is in path
        sys.path.append(base_dir)

        print("Importing train_wrapper...")
        from sagemaker_migration.scripts import train_wrapper

        # Mock install_dependencies inside train_wrapper to avoid pip calls
        train_wrapper.install_dependencies = MagicMock()

        print("Running train_wrapper.main()...")
        train_wrapper.main()

        print("\n[SUCCESS]: train_wrapper ran without error.")

        # VERIFICATION: Check if model.fit was called with correct args
        mock_model_instance = sys.modules["src.model"].HybridSpotModel.return_value
        if mock_model_instance.fit.called:
            print("   [OK] model.fit() called")
            # We could check args if we want deep verification
            args, kwargs = mock_model_instance.fit.call_args
            # Check if y_reg_train is passed
            if "y_reg_train" in kwargs:
                print("   [OK] y_reg_train passed (Memory Fix Confirmed)")
            else:
                print("   [ERROR] y_reg_train NOT passed!")
        else:
            print("   [ERROR] model.fit() NOT called!")

    except Exception as e:
        print(f"\n[FAILURE]: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Cleanup
        if os.path.exists(test_data_dir):
            shutil.rmtree(test_data_dir)
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)


if __name__ == "__main__":
    run_test()
