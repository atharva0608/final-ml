import argparse
import gc  # Memory optimization
import json
import logging
import os
import subprocess
import sys


# SAFE DEPENDENCY INJECTION (Only install what's missing)
def install_dependencies(skip_backtest: bool = True):
    """Installs missing libraries without touching container's pandas/numpy.

    Args:
        skip_backtest: If False (production mode), also install matplotlib/seaborn
    """
    packages_to_install = []

    # Check for LightGBM
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        packages_to_install.append("lightgbm>=4.0.0")

    # Check for Polars
    try:
        import polars  # noqa: F401
    except ImportError:
        packages_to_install.append("polars>=0.20.0")

    # Check for Optuna
    try:
        import optuna  # noqa: F401
    except ImportError:
        packages_to_install.append("optuna>=3.0.0")

    # Check for PyArrow (Critical for Polars <-> Pandas)
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        packages_to_install.append("pyarrow>=11.0.0")

    # Check for PyYAML
    try:
        import yaml  # noqa: F401
    except ImportError:
        packages_to_install.append("pyyaml")

    # Check for tqdm
    try:
        import tqdm  # noqa: F401
    except ImportError:
        packages_to_install.append("tqdm")

    # For production runs (with visualization), also install matplotlib/seaborn
    # Use specific versions compatible with pandas 1.1.3
    if not skip_backtest:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            packages_to_install.append("matplotlib>=3.5.0,<3.6.0")
        try:
            import seaborn  # noqa: F401
        except ImportError:
            packages_to_install.append("seaborn>=0.11.0,<0.12.0")

    # Install non-ONNX packages first
    if packages_to_install:
        print(f"Installing missing dependencies: {', '.join(packages_to_install)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages_to_install])

    # Install ONNX tools LAST to prevent protobuf conflicts (Defensive)
    # CRITICAL: Every package in the ONNX stack must be pinned to EXACT versions.
    # Loose pins (e.g. onnxmltools>=1.13.0) let pip pull skl2onnx 1.20.0
    # which is incompatible with onnx 1.15.0, causing runtime ImportError.
    #
    # Verified compatible stack (Feb 12, 2026):
    #   protobuf==3.20.3  (SageMaker container constraint)
    #   onnx==1.15.0      (last version supporting protobuf 3.x)
    #   onnxconverter-common==1.13.0  (pinned to protobuf 3.20.x)
    #   skl2onnx==1.16.0  (compatible with onnx 1.15.0)
    #   onnxmltools==1.12.0  (compatible with above stack)
    onnx_needs_install = False
    try:
        import onnx
        import onnxmltools  # noqa: F401
        from onnxconverter_common.data_types import FloatTensorType  # noqa: F401
        from onnxmltools import convert_lightgbm  # noqa: F401

        # Version gate: onnx 1.16+ requires protobuf>=4.25.1 (conflicts with 3.20.3)
        onnx_version = tuple(int(x) for x in onnx.__version__.split(".")[:2])
        if onnx_version >= (1, 16):
            print(f"  [ONNX] Detected incompatible onnx {onnx.__version__}. Forcing reinstall...")
            onnx_needs_install = True
    except ImportError as e:
        print(f"  [ONNX] Import check failed: {e}. Will install compatible stack...")
        onnx_needs_install = True

    if onnx_needs_install:
        # Force exact compatible versions -- no ranges, no flexibility
        onnx_packages = [
            "protobuf==3.20.3",
            "onnx==1.15.0",
            "onnxconverter-common==1.13.0",
            "skl2onnx==1.16.0",
            "onnxmltools==1.12.0",
        ]
        print(f"Installing ONNX stack (pinned): {', '.join(onnx_packages)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--force-reinstall", *onnx_packages])

    # Always verify the full ONNX import chain after install
    try:
        import importlib

        import onnx
        import onnxmltools  # noqa: F811

        importlib.reload(onnx)
        importlib.reload(onnxmltools)
        from onnxconverter_common.data_types import FloatTensorType  # noqa: F401,F811
        from onnxmltools import convert_lightgbm  # noqa: F401,F811

        print(f"  [ONNX Verified] onnx={onnx.__version__}, onnxmltools={onnxmltools.__version__}")
    except ImportError as e:
        print(f"  [ONNX CRITICAL] Full import chain verification FAILED: {e}")
        print("  [ONNX CRITICAL] ONNX export will NOT work this run.")


# Initial install (without viz deps - will re-check after args parsing)
install_dependencies(skip_backtest=True)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def check_imports():
    """Diagnose import issues."""
    logger.info("Checking dependencies...")
    try:
        import numpy as np

        logger.info(f"Numpy version: {np.__version__}")
    except ImportError as e:
        logger.error(f"Failed to import numpy: {e}")

    try:
        import pandas as pd

        logger.info(f"Pandas version: {pd.__version__}")
    except ImportError as e:
        logger.error(f"Failed to import pandas: {e}")

    try:
        import lightgbm as lgb

        logger.info(f"LightGBM version: {lgb.__version__}")
    except ImportError as e:
        logger.error(f"Failed to import lightgbm: {e}")


# Defer imports to avoid top-level crashes
# from src.backtest import WalkForwardBacktest
# from src.data import chronological_split, engineer_all_features, load_all_data, load_stress_events
# from src.model import HybridSpotModel
# from src.visualize import ModelVisualizer


def main():
    logger.info("=" * 80)
    logger.info("SAGEMAKER TRAINING WRAPPER STARTED")
    logger.info("=" * 80)

    # --- 2. PARSE ARGUMENTS ---
    # SageMaker passes hyperparameters as args and paths as env vars
    parser = argparse.ArgumentParser()

    # SageMaker Directory Paths (Env Vars mapped to args)
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR"))
    parser.add_argument("--train", type=str, default=os.environ.get("SM_CHANNEL_TRAINING"))

    # Hyperparameters (Can be tuned) - Regressor (Trial #92 Defaults)
    parser.add_argument("--num_leaves", type=int, default=78)
    parser.add_argument("--learning_rate", type=float, default=0.09697)
    parser.add_argument("--max_depth", type=int, default=7)
    parser.add_argument("--lambda_l1", type=float, default=0.00087)
    parser.add_argument("--lambda_l2", type=float, default=2.18e-7)
    parser.add_argument("--min_child_samples", type=int, default=25)
    parser.add_argument("--horizon", type=int, default=6)  # 1h horizon (optimized for memory)
    parser.add_argument("--sample_fraction", type=float, default=1.0)  # For fast HPO trials
    parser.add_argument("--skip_backtest", type=int, default=0, help="Skip backtesting (1=True, 0=False)")

    # Classifier-specific hyperparameters (separate tuning)
    parser.add_argument("--clf_learning_rate", type=float, default=0.03482)
    parser.add_argument("--clf_num_leaves", type=int, default=45)
    parser.add_argument("--clf_min_child_samples", type=int, default=315)

    args, _ = parser.parse_known_args()

    print(f"Data Source: {args.train}")
    print(f"Model Output: {args.model_dir}")
    print(f"Params: leaves={args.num_leaves}, lr={args.learning_rate}, depth={args.max_depth}")

    # --- 2b. INSTALL VIZ DEPENDENCIES IF NEEDED ---
    # Now that we know skip_backtest, install matplotlib/seaborn if visualization is enabled
    if not args.skip_backtest:
        print("Production mode: Checking visualization dependencies...")
        install_dependencies(skip_backtest=False)

    # --- 3. CONFIGURATION OVERRIDE ---
    # Create a config dict dynamically based on args + hardcoded defaults
    # This replaces loading config.yaml

    check_imports()

    # Deferred imports - must happen AFTER requirements are installed

    import pandas as pd  # noqa: E402

    try:
        from src.backtest import WalkForwardBacktest
        from src.data import engineer_all_features, load_all_data, load_stress_events
        from src.data_polars import chronological_split_polars
        from src.model import HybridSpotModel

        # ModelVisualizer imported later only if needed (requires matplotlib)
    except Exception as e:
        logger.error("Failed to import src modules.")
        logger.error(f"Error: {e}")
        # Debug sys.path
        logger.info(f"sys.path: {json.dumps(sys.path, indent=2)}")
        # List current directory
        logger.info(f"Current Dir: {os.getcwd()}")
        logger.info(f"Directory Contents: {os.listdir(os.getcwd())}")
        if os.path.exists("src"):
            logger.info(f"src Contents: {os.listdir('src')}")
        sys.exit(1)

    # 3a. Find files (SageMaker mounts input channel to args.train)
    import glob

    parquet_files = glob.glob(os.path.join(args.train, "*.parquet"))
    stress_file_path = os.path.join(args.train, "mumbai_stress_events_validated.csv")

    if not parquet_files:
        print(f" ERROR: No parquet files found in {args.train}")
        print(" Verify that the S3 bucket path is correct and contains data.")
        # We can't proceed without data
        sys.exit(1)

    config = {
        # WARNING: These values are HARDCODED for SageMaker speed/autonomy.
        # They MUST stay synced with config/config.yaml.
        # If you change config.yaml, you MUST update these values manually or risking "Silent Failure".
        "data": {
            "parquet_files": parquet_files,  # Correct key for load_all_data
            "stress_events": stress_file_path,  # Correct key for load_stress_events
            "sample_families": [],  # Load ALL
        },
        "features": {
            "lag_intervals": [6, 24, 144],
            "rolling_windows": [24, 144],  # 4h, 24h (Restored to match HPO)
            "horizons": [args.horizon],
            "use_family_stress": True,
            "filter_critical_pools": True,
            "add_pool_risk_feature": True,
        },
        "model": {"n_jobs": 8, "early_stopping_rounds": 100},  # SageMaker instances usually have 4+ cores
    }

    sampled = False
    df_pl = None
    # Track where the features are stored (either existing input or generated temp)
    valid_features_path = None

    try:
        # --- 4. LOAD & PREPROCESS DATA (Polars Optimized) ---
        preprocessed_path = os.path.join(args.train, "preprocessed_features.parquet")

        if os.path.exists(preprocessed_path):
            logger.info("FAST PATH: Loading Preprocessed Features (Polars)")
            logger.info(f"File: {preprocessed_path}")
            valid_features_path = preprocessed_path

            import polars as pl

            # Lazy loading is not ideal here as we need to sample and materialize
            df_pl = pl.read_parquet(preprocessed_path)

            # --- 4a. Target Generation (Polars) ---
            if "is_unstable" not in df_pl.columns:
                logger.info(f"Target 'is_unstable' not found. Generating targets for horizon={args.horizon}...")
                try:
                    from src.data_polars import prepare_targets_polars

                    # Pass Polars DF, get Polars DF back (avoiding pandas conversion)
                    df_pl = prepare_targets_polars(df_pl, horizon=args.horizon, return_polars=True)
                except ImportError:
                    logger.warning("src.data_polars missing. Falling back to Pandas target generation (Slow)")
                    # This path requires converting to pandas early
                    df = df_pl.to_pandas()
                    df = df.sort_values(["InstanceType", "AZ", "timestamp"])
                    from src.data import prepare_targets

                    df = prepare_targets(df, horizon=args.horizon)
                    # Convert back to Polars for sampling? No, stay in pandas if we hit this path
                    df_pl = None

            # --- 4b. HPO Sampling (Polars) ---
            if args.sample_fraction < 1.0 and df_pl is not None:
                original_size = df_pl.height
                step = int(1 / args.sample_fraction)
                step = max(1, step)

                # Polars optimized sampling (gather_every)
                df_pl = df_pl.gather_every(step)
                print(
                    f" Sampled dataset for HPO (Polars): {original_size:,} -> {df_pl.height:,} ({args.sample_fraction*100:.0f}%)"
                )
                sampled = True

            if df_pl is not None:
                # OPTIMIZATION: Keep in Polars! Do NOT convert to Pandas yet.
                logger.info("Keeping data in Polars for memory-efficient splitting...")
                # df = df_pl.to_pandas()  <-- REMOVED
                pass

        else:
            logger.info("SLOW PATH: Loading Raw Data & Engineering Features")
            print("\n[Phase 1] Loading Data...")
            df = load_all_data(config)
            events = load_stress_events(config)

            print("\n[Phase 2] Engineering Features...")
            df = engineer_all_features(df, events, config)

            # Convert to Polars for unified pipeline
            logger.info("Converting Raw Data to Polars for splitting...")
            import polars as pl

            df_pl = pl.from_pandas(df)
            del df
            gc.collect()

            # CHECKPOINT: Save generated features for Backtest reload
            # Use /tmp to handle read-only input volumes
            valid_features_path = "/tmp/preprocessed_features.parquet"
            logger.info(f"SLOW PATH: Saving generated features to {valid_features_path} for backtest reload...")
            df_pl.write_parquet(valid_features_path)

    except Exception as e:
        logger.error("FATAL ERROR during Data Loading/Preprocessing:")
        logger.error(str(e))
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Ensure targets exist (Polars check)
    if "is_unstable" not in df_pl.columns:
        logger.info("Generating targets (Polars fallback)...")
        from src.data_polars import prepare_targets_polars

        # Ensure sorted
        df_pl = df_pl.sort(["InstanceType", "AZ", "timestamp"])
        df_pl = prepare_targets_polars(df_pl, horizon=args.horizon, return_polars=True)

    # HPO Sampling (Polars)
    if args.sample_fraction < 1.0 and not sampled:
        original_size = df_pl.height
        step = int(1 / args.sample_fraction)
        df_pl = df_pl.gather_every(step)
        print(
            f" Sampled dataset for HPO (Polars): {original_size:,} -> {df_pl.height:,} ({args.sample_fraction*100:.0f}%)"
        )

    # Split (Polars-First Strategy)
    logger.info("Splitting data in Polars (Memory Optimized)...")
    train_pl, val_pl, test_pl = chronological_split_polars(df_pl)

    # Extract Categories BEFORE deleting df_pl (for unified schema)
    # We will need these to cast category columns in Pandas later
    cat_info = {}
    categorical_cols = ["instance_family", "instance_size", "AZ"]
    for col in categorical_cols:
        if col in df_pl.columns:
            unique_cats = df_pl.select(pl.col(col).unique()).to_series().to_list()
            cat_info[col] = unique_cats
            logger.info(f"Captured {len(unique_cats)} categories for {col}")

    # REF: OPTIMIZATION - Keep df_pl for reconstruction if performing backtest
    # Only delete if we are SURE we don't need it or can reconstruct it cheaply
    # But since we need to pass full df to backtest, we should re-assemble from splits or keep it.
    # Given memory constraints, re-assembly from splits (which we keep) is safer than keeping 2 copies.

    del df_pl  # Critical memory release
    gc.collect()
    print(f"Rows (Polars): Train={train_pl.height}, Val={val_pl.height}, Test={test_pl.height}")

    # OPTIMIZATION: Defer test_pl to disk to free ~15-20 GB during training
    test_tmp_path = "/tmp/test_split.parquet"
    test_pl.write_parquet(test_tmp_path)
    del test_pl
    gc.collect()
    logger.info(f"Test split saved to {test_tmp_path} and freed from memory")

    # --- 5. DATA PREPARATION (JIT Conversion) ---
    logger.info("Converting Train/Val to Pandas (JIT)...")

    # Convert Train
    train_df = train_pl.to_pandas()
    del train_pl
    gc.collect()

    # Convert Val
    val_df = val_pl.to_pandas()
    del val_pl
    gc.collect()

    # Apply Unified Categories (captured from Polars)
    for col, categories in cat_info.items():
        cat_dtype = pd.CategoricalDtype(categories=categories)
        if col in train_df.columns:
            train_df[col] = train_df[col].astype(cat_dtype)
        if col in val_df.columns:
            val_df[col] = val_df[col].astype(cat_dtype)
            logger.info(f"Applied unified categories to {col}")

    # Define features from train_df (after category conversion)
    feature_cols = [
        c
        for c in train_df.columns
        if c
        not in [
            # Identifier columns (not features)
            "timestamp",
            "InstanceType",
            "AvailabilityZone",
            "Region",
            "ProductDescription",
            "OndemandPrice",  # Reference price, not a feature
            # Target columns (leakage prevention)
            "SpotPrice",
            "Savings",
            "is_unstable",
            "price_position",
            "future_savings",
        ]
    ]

    # --- 6. TRAIN MODEL ---
    print("\n[Phase 3] Training Model...")
    model = HybridSpotModel(horizon=args.horizon, n_jobs=config["model"]["n_jobs"])

    # Construct params dict from args
    # Note: Using args for Regressor, keeping Classifier defaults or could expose more args
    reg_params = {
        "num_leaves": args.num_leaves,
        "learning_rate": args.learning_rate,
        "max_depth": args.max_depth,
        "lambda_l1": args.lambda_l1,
        "lambda_l2": args.lambda_l2,
        "min_child_samples": args.min_child_samples,
        "metric": "mape",
        "n_jobs": 8,
        "verbose": -1,
        "max_bin": 63,  # Speed optimization (Huge memory/time savings)
    }

    # Calculate scale_pos_weight dynamically to handle class imbalance
    # This fixes the AUC=0.5 issue where the model ignored the minority "Unstable" class
    n_pos = train_df["is_unstable"].sum()
    n_neg = len(train_df) - n_pos
    scale_pos_weight = n_neg / n_pos if n_pos > 0 else 1.0
    logger.info(f"Class Imbalance: {n_pos} Positive (Unstable) vs {n_neg} Negative (Stable)")
    logger.info(f"Calculated scale_pos_weight: {scale_pos_weight:.2f}")

    # Classifier params (Risk Score) - uses separate hyperparameters
    clf_params = {
        "num_leaves": args.clf_num_leaves,
        "learning_rate": args.clf_learning_rate,
        "max_depth": args.max_depth,  # Shared with regressor
        "min_child_samples": args.clf_min_child_samples,
        "scale_pos_weight": scale_pos_weight,  # CRITICAL FIX for Imbalance
        "metric": "binary_logloss",
        "n_jobs": 8,
        "verbose": -1,
        "max_bin": 63,  # Speed optimization
    }

    # Note: num_boost_round (1000) and early_stopping (100) are controlled
    # inside model.py's train_regressor()/train_classifier(), not via params dict.
    print("Production mode: Using FULL training rounds (1000 max, 100 early stop)")

    # Train
    # Prepare X, y in-place to save memory
    print("Preparing Training Data (In-Place)...")
    # Extract targets and remove from DF to save memory
    # NEW (FIXED) - Only strip Train. Keep Val intact for optimization.
    y_reg_train = train_df.pop("future_savings")
    y_clf_train = train_df.pop("is_unstable")

    # Val targets are just references (No memory cost)
    y_reg_val = val_df["future_savings"]
    y_clf_val = val_df["is_unstable"]

    # Drop non-feature columns to convert train_df to X_train in-place
    keep_cols = set(feature_cols)
    drop_train = [c for c in train_df.columns if c not in keep_cols]
    if drop_train:
        train_df.drop(columns=drop_train, inplace=True)

    gc.collect()

    model.fit(
        X_train=train_df,
        X_val=val_df[feature_cols],  # Explicitly select features
        y_reg_train=y_reg_train,
        y_reg_val=y_reg_val,
        y_clf_train=y_clf_train,
        y_clf_val=y_clf_val,
        regressor_params=reg_params,
        classifier_params=clf_params,
    )

    # Cleanup Training Data immediately (Keep val_df for eval)
    print("Cleaning up training data...")
    del train_df, y_reg_train, y_reg_val, y_clf_train
    gc.collect()

    # CRITICAL FIX: Optimize threshold before evaluation
    # This ensures the validation metrics reflect the best possible decision boundary
    # val_df now has all columns (metadata + targets), so we can pass it directly
    model.optimize_threshold(val_df[feature_cols], val_df)
    # Now cleanup y_clf_val
    del y_clf_val

    # Report metrics for SageMaker HPO to parse
    # REF: AUDIT-FIX - Use nested dict access (was val_metrics['regressor_mape'])
    val_metrics = model.evaluate(val_df[feature_cols], val_df)
    print(f"REPORT_METRIC:regressor_mape={val_metrics['regressor']['mape']}")
    print(f"REPORT_METRIC:classifier_auc={val_metrics['classifier']['auc']}")

    # Now valid to delete val_df
    del val_df
    gc.collect()

    # --- 6a. IMMEDIATE SAVE (Safety) ---
    # Save model immediately after training to prevent loss if Viz/Eval crashes
    print("\n[Phase 3b] Saving Model Artifacts (Safety Save)...")

    # [AUDIT FIX] Save the Category Mapping (captured earlier in Phase 4)
    if not cat_info:
        print("  [WARNING] No categorical mappings found! Inference might fail if model uses categories.")
    else:
        # Save Artifact
        map_path = os.path.join(args.model_dir, "category_mapping.json")
        try:
            with open(map_path, "w") as f:
                json.dump(cat_info, f, indent=2)
            print(f"  [SUCCESS] Category mapping saved to {map_path}")
        except Exception as e:
            print(f"  [ERROR] Failed to write category mapping: {e}")

    model.save(args.model_dir)

    # --- 7. EVALUATE & BACKTEST ---
    print("\n[Phase 4] Evaluation & Backtesting...")

    # Standard Eval (JIT Convert Test)
    # Reload test split from disk (saved earlier to free memory during training)
    logger.info("Reloading Test split from disk...")
    import polars as pl

    test_pl = pl.read_parquet(test_tmp_path)
    test_df = test_pl.to_pandas()
    del test_pl
    gc.collect()

    # Apply categories to Test
    for col, categories in cat_info.items():
        cat_dtype = pd.CategoricalDtype(categories=categories)
        if col in test_df.columns:
            test_df[col] = test_df[col].astype(cat_dtype)

    metrics = model.evaluate(test_df[feature_cols], test_df)

    # Walk-Forward Backtest (Skip during HPO for speed)
    if not args.skip_backtest:
        print("Running Backtest...")

        # We must reload because training destroyed 'timestamp', 'InstanceType', etc.
        logger.info("Reloading dataset for backtest (Memory Safe)...")
        # USE THE TRACKED PATH (handles both Fast Path and Slow/Temp Path)
        if not valid_features_path or not os.path.exists(valid_features_path):
            logger.error("Feature file not found for backtest! (Did Slow Path logic fail to save?)")
            # fallback to args.train location if variable lost (unlikely)
            valid_features_path = os.path.join(args.train, "preprocessed_features.parquet")

        logger.info(f"Loading from: {valid_features_path}")
        import polars as pl

        df_pl = pl.read_parquet(valid_features_path)

        # Generate targets if needed
        if "is_unstable" not in df_pl.columns:
            from src.data_polars import prepare_targets_polars

            df_pl = prepare_targets_polars(df_pl, horizon=args.horizon, return_polars=True)

        df = df_pl.to_pandas()
        del df_pl
        gc.collect()

        # AUDIT-FIX: Re-apply categorical types (lost during Parquet reload)
        for col, categories in cat_info.items():
            cat_dtype = pd.CategoricalDtype(categories=categories)
            if col in df.columns:
                df[col] = df[col].astype(cat_dtype)
                logger.info(f"Re-applied unified categories to backtest data: {col}")

        backtester = WalkForwardBacktest(n_splits=3)  # Reduced splits for speed on cloud
        # Pass HPO-tuned params to backtest for consistent evaluation
        backtest_results = backtester.run_backtest(
            df=df,
            feature_cols=feature_cols,
            horizon=args.horizon,
            n_jobs=8,
            regressor_params=reg_params,
            classifier_params=clf_params,
            threshold=model.optimal_threshold,
        )

        # --- 8. VISUALIZE ---
        print("\n[Phase 5] Generating Visualizations...")
        from src.visualize import ModelVisualizer  # Import only when needed (requires matplotlib)

        # Wrap Visualization in try/except to prevent crash from failing job
        try:
            viz = ModelVisualizer(args.model_dir)
            viz.generate_essential_dashboards(
                model=model,
                X_test=test_df[feature_cols],
                test_df=test_df,
                feature_names=feature_cols,
                horizon=args.horizon,
                backtest_results=backtest_results,
            )
        except Exception as e:
            logger.error(f"Visualization failed: {e}")
            import traceback

            traceback.print_exc()
            print("Creating empty visualization placeholder to satisfy output artifacts...")
            # Optional: touch a file so downstream doesn't panic
            with open(os.path.join(args.model_dir, "visualization_failed.txt"), "w") as f:
                f.write(str(e))
    else:
        print("Skipping backtest & visualization (HPO mode)")
        backtest_results = {"skipped": True, "reason": "HPO optimization"}

    # --- 9. SAVE REPORTS ---
    print("\n[Phase 6] Saving Additional Reports...")
    # Model already saved in Phase 3b

    # Save metrics
    with open(os.path.join(args.model_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)

    # Save backtest results
    with open(os.path.join(args.model_dir, "backtest_results.json"), "w") as f:
        json.dump(backtest_results, f, default=str)

    print("\n TRAINING JOB COMPLETE. Artifacts saved to model_dir.")


if __name__ == "__main__":
    main()
