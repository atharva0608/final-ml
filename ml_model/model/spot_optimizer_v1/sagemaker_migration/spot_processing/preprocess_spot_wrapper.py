#!/usr/bin/env python3
"""
SageMaker Spot Preprocessing Worker Script

This script adapts the feature engineering logic to run inside a SageMaker TRAINING container.
This allows us to use Managed Spot Training (use_spot_instances=True) to save ~70% cost.

Key Differences from Processing Job:
1. Input Path: /opt/ml/input/data/training (instead of /opt/ml/processing/input)
2. Dependencies: Must be installed at runtime (sklearn images are bare)
3. Output: Uploads directly to S3 via boto3 (simpler than model.tar.gz for data files)
"""
import argparse
import glob
import logging
import os
import subprocess
import sys

import boto3
import pandas as pd

# Setup Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


def install_dependencies():
    """Install dependencies from requirements_sagemaker.txt located in code dir."""
    logger.info("Installing dependencies...")

    # In Training Jobs, code is usually at /opt/ml/code
    # check for requirements file
    req_path = "/opt/ml/code/spot_optimizer_v1/sagemaker_migration/requirements_sagemaker.txt"

    if not os.path.exists(req_path):
        # Fallback: look in current dir/spot_optimizer_v1/...
        req_path = "spot_optimizer_v1/sagemaker_migration/requirements_sagemaker.txt"

    if os.path.exists(req_path):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", req_path])
        logger.info("Dependencies installed successfully.")
    else:
        logger.warning(f"Requirements file not found at {req_path}. Assuming dependencies are pre-installed.")


def main():
    logger.info("=" * 80)
    logger.info("SAGEMAKER SPOT PREPROCESSING (TRAINING MODE)")
    logger.info("=" * 80)

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-bucket", type=str, required=True)
    parser.add_argument("--output-prefix", type=str, default="preprocessed")
    args, _ = parser.parse_known_args()

    # 1. Install Libs
    install_dependencies()

    # 2. Setup Paths
    # Add code to path so we can import src.data
    sys.path.insert(0, "/opt/ml/code")
    sys.path.insert(0, "/opt/ml/code/spot_optimizer_v1")

    # Import AFTER install
    try:
        from src.data import engineer_all_features, load_all_data, load_stress_events
    except ImportError as e:
        logger.error(f"Failed to import src modules. Path: {sys.path}")
        raise e

    # SageMaker Training Data Path
    input_dir = "/opt/ml/input/data/training"

    logger.info(f"[Phase 1] Locating Data in {input_dir}...")

    parquet_files = glob.glob(os.path.join(input_dir, "*.parquet"))
    csv_files = glob.glob(os.path.join(input_dir, "*.csv"))
    # Recursively check subdirs if flat search fails (sometimes S3 cp adds structure)
    if not parquet_files:
        parquet_files = glob.glob(os.path.join(input_dir, "**", "*.parquet"), recursive=True)

    stress_file = None
    # Find stress events file
    for f in csv_files + glob.glob(os.path.join(input_dir, "**", "*.csv"), recursive=True):
        if "events" in f.lower():
            stress_file = f
            break

    if not parquet_files:
        logger.error(f"No .parquet files found in {input_dir}")
        sys.exit(1)

    logger.info(f"  Found {len(parquet_files)} parquet files")
    logger.info(f"  Stress events file: {stress_file}")

    # 3. Config
    config = {
        "data": {"parquet_files": parquet_files, "stress_events": stress_file, "sample_families": []},  # Load ALL
        "features": {
            "lag_intervals": [6, 24, 144],
            "rolling_windows": [24, 72, 144],  # 4h, 12h, 24h
            "horizons": [6],
            "use_family_stress": True,
            "filter_critical_pools": True,
            "add_pool_risk_feature": True,
        },
    }

    # 4. Processing
    logger.info(f"\n[Phase 2] Loading & Engineering Features...")
    df = load_all_data(config)

    if stress_file:
        events = load_stress_events(config)
    else:
        logger.warning("No stress events file found! Skipping event features.")
        events = pd.DataFrame(columns=["date", "event_name", "event_type"])  # Empty dummy

    df = engineer_all_features(df, events, config)
    logger.info(f"\nFeature Engineering Complete. Shape: {df.shape}")

    # 5. Save & Upload
    output_filename = "preprocessed_features.parquet"
    local_path = os.path.join("/tmp", output_filename)

    logger.info(f"\n[Phase 3] Saving to {local_path}...")
    df.to_parquet(local_path, compression="snappy", index=False)

    s3_key = f"{args.output_prefix}/{output_filename}"
    s3_uri = f"s3://{args.output_bucket}/{s3_key}"

    logger.info(f"Uploading to {s3_uri}...")
    s3 = boto3.client("s3")
    s3.upload_file(local_path, args.output_bucket, s3_key)

    logger.info("DONE. Spot Preprocessing Successful.")


if __name__ == "__main__":
    main()
