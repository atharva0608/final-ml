import argparse
import os
import subprocess
import sys
import tarfile


# --- 1. SAFE DEPENDENCY INJECTION ---
def install_dependencies():
    """
    Installs missing high-performance libraries (Polars, LightGBM)
    while respecting pre-installed SageMaker libraries.
    """
    packages_to_install = []

    # Check for Polars (Not in standard image)
    try:
        import polars  # noqa: F401 - Dependency check only
    except ImportError:
        packages_to_install.append("polars>=0.20.0")

    # Check for LightGBM (Not in standard image)
    try:
        import lightgbm  # noqa: F401 - Dependency check only
    except ImportError:
        packages_to_install.append("lightgbm>=4.0.0")

    # Check for PyArrow (Often present but old in SageMaker images; Polars needs it)
    try:
        import pyarrow  # noqa: F401 - Dependency check only
    except ImportError:
        packages_to_install.append("pyarrow>=10.0.0")

    if packages_to_install:
        print(f"Installing missing dependencies: {', '.join(packages_to_install)}...")
        # '--only-binary :all:' prevents compiling from source (slow/fragile)
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages_to_install, "--only-binary", ":all:"])


# Run installation BEFORE other imports to avoid runtime conflicts
install_dependencies()

import lightgbm as lgb  # noqa: E402 - Import after dependency installation
import polars as pl  # noqa: E402 - Import after dependency installation

# --- 2. CONSTANTS ---
TEST_SPLIT_RATIO = 0.15  # Last 15% of data for test set
DEFAULT_THRESHOLD = 0.01  # 1% change threshold for "moving markets"


# --- 3. ACID TEST LOGIC (Optimized) ---
def run_acid_test(
    test_df, model, features, target_col="future_savings", current_col="Savings", threshold=DEFAULT_THRESHOLD
):
    print(f"\n{'='*20} ACID TEST (Dynamic MAPE) {'='*20}")
    print(f"Processing {test_df.height:,} rows with Polars...")

    # Validate required columns exist
    required_cols = [target_col, current_col]
    missing = [c for c in required_cols if c not in test_df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Cannot run Acid Test.")

    # Convert to Pandas for categorical handling (matches training pipeline)
    test_df_pd = test_df.to_pandas()

    # Convert categorical columns to category dtype (required for LightGBM)
    categorical_cols = ["instance_family", "instance_size", "AZ"]
    for col in categorical_cols:
        if col in test_df_pd.columns:
            test_df_pd[col] = test_df_pd[col].astype("category")
            print(f"  Converted {col} to category dtype")

    # 1. Predictions
    # Validate model features exist in test data
    missing_features = set(features) - set(test_df_pd.columns)
    if missing_features:
        raise ValueError(f"Model requires missing features: {sorted(missing_features)}")

    # Pass DataFrame directly (not numpy) to preserve categorical dtype
    X_df = test_df_pd[features]

    if isinstance(model, lgb.Booster):
        best_iter = model.best_iteration if model.best_iteration > 0 else -1
        y_pred = model.predict(X_df, num_iteration=best_iter)
    else:
        y_pred = model.predict(X_df)

    # 2. Evaluation (Back to Polars for fast operations)
    # Note: We already have target_col and current_col in the original Polars df
    df_eval = test_df.select([target_col, current_col]).with_columns(
        [
            pl.Series(name="prediction", values=y_pred),
            (pl.col(target_col) - pl.col(current_col)).abs().alias("actual_delta"),
        ]
    )

    # 3. Filter for Moving Markets
    total_markets = df_eval.height
    moving_market_df = df_eval.filter(pl.col("actual_delta") > threshold)
    n_moving = moving_market_df.height

    print(f"  Moving Markets: {n_moving:,} / {total_markets:,} ({n_moving/total_markets*100:.1f}%)")

    if n_moving == 0:
        print(f"No moving markets found (threshold={threshold}). Try lower threshold.")
        return

    # 4. Metrics
    metrics = moving_market_df.select(
        [
            pl.col("actual_delta").mean().alias("baseline_mae"),
            (pl.col(target_col) - pl.col("prediction")).abs().mean().alias("model_mae"),
        ]
    ).to_dict(as_series=False)

    baseline_mae = metrics["baseline_mae"][0]
    model_mae = metrics["model_mae"][0]

    # Guard against division by zero
    if baseline_mae == 0:
        print("Baseline MAE is zero - all markets are perfectly static.")
        print("   Cannot calculate improvement percentage.")
        return

    improvement = (baseline_mae - model_mae) / baseline_mae * 100

    print(f"  - Persistence MAE: {baseline_mae:.4f}")
    print(f"  - Model MAE:       {model_mae:.4f}")

    print("\nVERDICT:")
    if improvement > 5.0:
        print(f"  PASS. Beats persistence by {improvement:.2f}%")
    elif improvement > 0:
        print(f"  MARGINAL. Beats persistence by {improvement:.2f}%")
    else:
        print(f"  FAIL. Worse than persistence ({improvement:.2f}%)")


# --- 4. MAIN EXECUTION ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # SageMaker automatically mounts S3 buckets to these environment variables
    parser.add_argument("--test_data", type=str, default=os.environ.get("SM_CHANNEL_TEST"))
    parser.add_argument("--model_dir", type=str, default=os.environ.get("SM_CHANNEL_MODEL"))
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f'Minimum price delta to qualify as "moving market" (default: {DEFAULT_THRESHOLD})',
    )
    args = parser.parse_args()

    # A. Load Model
    print(f"Loading model from {args.model_dir}...")

    # Handle the fact that SageMaker Training Jobs might not untar input channels automatically
    model_tar = os.path.join(args.model_dir, "model.tar.gz")
    extract_path = args.model_dir

    if os.path.exists(model_tar):
        print("Extracting model.tar.gz...")
        with tarfile.open(model_tar, "r:gz") as tar:
            tar.extractall(path=extract_path)

    # Find the regressor model file (prioritize regressor over classifier)
    files = os.listdir(extract_path)
    regressor_file = next((f for f in files if "regressor" in f.lower() and f.endswith(".txt")), None)

    if not regressor_file:
        # Fallback: any .txt file that's not the tar
        regressor_file = next((f for f in files if f.endswith(".txt") and not f.endswith(".tar.gz")), None)

    if not regressor_file:
        raise FileNotFoundError(f"No regressor model found in {extract_path}. Files: {files}")

    print(f"Initializing LightGBM Regressor with {regressor_file}...")
    model = lgb.Booster(model_file=os.path.join(extract_path, regressor_file))

    # Extract horizon from model filename (e.g., regressor_6.txt -> 6)
    try:
        horizon = int("".join(filter(str.isdigit, regressor_file)))
    except ValueError:
        print("Could not extract horizon from filename. Using default: 6")
        horizon = 6
    print(f"Model horizon: {horizon} intervals")

    # B. Load Data & Create Test Split (Lazy/Memory-Efficient)
    # Use lazy loading to avoid OOM on large datasets
    data_file = os.path.join(args.test_data, "preprocessed_features.parquet")
    print(f"Loading Data (Lazy Mode): {data_file}")

    # Lazy scan - doesn't load into memory yet
    df_lazy = pl.scan_parquet(data_file)

    # Count total rows (this is fast - reads metadata only)
    n_rows = df_lazy.select(pl.len()).collect().item()
    print(f"Total Rows: {n_rows:,}")

    # Calculate split index for test set (using constant for clarity)
    test_start_idx = int(n_rows * (1 - TEST_SPLIT_RATIO))

    print(f"Extracting Test Set (Last 15%): Row {test_start_idx:,} to {n_rows:,}")

    # Lazy operations: sort, slice, then collect ONLY what we need
    # This loads only ~32M rows instead of all 211M
    df = df_lazy.sort("timestamp").slice(test_start_idx, n_rows - test_start_idx).collect()

    print(f"Test Set Size: {df.height:,} rows (Loaded into memory)")

    # B2. Generate targets if missing (Just-in-Time, like train_wrapper.py)
    if "future_savings" not in df.columns:
        print("Target 'future_savings' not found. Generating targets...")
        # Import and use Polars target generation (sys already imported at top)
        sys.path.append(os.getcwd())  # Ensure src is in path
        from src.data_polars import prepare_targets_polars

        # Generate targets using Polars (fast) with correct horizon
        df = prepare_targets_polars(df, horizon=horizon, return_polars=True)
        print(f"Targets generated. Rows after dropna: {df.height:,}")

    # C. Run Acid Test
    run_acid_test(df, model, model.feature_name(), threshold=args.threshold)
