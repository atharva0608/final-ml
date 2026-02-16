#!/usr/bin/env python3
"""
SageMaker Processing Script - Feature Engineering

This script runs INSIDE a SageMaker Processing Job.
It reads raw data from /opt/ml/processing/input/data/
and writes preprocessed features to /opt/ml/processing/output/
"""
import glob
import os
import subprocess
import sys

# Install all dependencies from requirements.txt BEFORE importing src modules
print("Installing dependencies from requirements.txt...")
subprocess.check_call(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "-r",
        "/opt/ml/processing/input/code/spot_optimizer_v1/sagemaker_migration/requirements_sagemaker.txt",
    ]
)
print("Dependencies installed successfully.\n")

# Setup logging
import logging  # noqa: E402

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, "/opt/ml/processing/input/code")
sys.path.insert(0, "/opt/ml/processing/input/code/spot_optimizer_v1")

from src.data import engineer_all_features, load_all_data, load_stress_events  # noqa: E402


def main():
    print("=" * 80)
    print("SAGEMAKER FEATURE PREPROCESSING")
    print("=" * 80)

    # SageMaker paths
    input_dir = "/opt/ml/processing/input/data"
    output_dir = "/opt/ml/processing/output"

    print(f"\n[Phase 1] Locating Data in {input_dir}...")

    # Find files
    parquet_files = glob.glob(os.path.join(input_dir, "*.parquet"))
    csv_files = glob.glob(os.path.join(input_dir, "*.csv"))
    stress_file = csv_files[0] if csv_files else None

    if not parquet_files:
        print(f"ERROR: No .parquet files found in {input_dir}")
        return

    print(f"  Found {len(parquet_files)} parquet files")
    print(f"  Found stress events: {os.path.exists(stress_file)}")

    # Config
    config = {
        "data": {"parquet_files": parquet_files, "stress_events": stress_file, "sample_families": []},  # Load ALL
        "features": {
            "lag_intervals": [6, 24, 144],
            "rolling_windows": [24, 72, 144],  # 4h, 12h, 24h
            "horizons": [6],  # 1h feature generation
            "use_family_stress": True,
            "filter_critical_pools": True,
            "add_pool_risk_feature": True,
        },
    }

    # Process
    print("\n[Phase 2] Loading & Engineering Features (This takes ~35-40 mins)...")

    try:
        df = load_all_data(config)
        events = load_stress_events(config)
        df = engineer_all_features(df, events, config)
        print(f"\nFeature Engineering Complete. Shape: {df.shape}")
    except Exception as e:
        print(f"\nERROR during processing: {e}")
        raise

    # Save
    output_file = os.path.join(output_dir, "preprocessed_features.parquet")
    print(f"\n[Phase 3] Saving to {output_file}...")

    # Explicitly cast categorical columns before saving
    # This prevents 'ValueError: pandas dtypes must be int, float or bool' in LightGBM
    # when reloading the data later.
    categorical_cols = ["InstanceType", "AZ", "Region", "instance_family", "instance_size"]
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype("category")
            print(f"  Cast {col} to category")

    os.makedirs(output_dir, exist_ok=True)
    df.to_parquet(output_file, compression="snappy", index=False)

    file_size_mb = os.path.getsize(output_file) / 1e6
    print(f"  Size: {file_size_mb:.2f} MB")
    print("\nDONE. Output will be uploaded to S3 by SageMaker.")


if __name__ == "__main__":
    main()
