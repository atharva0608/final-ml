#!/usr/bin/env python3
"""
Submit SageMaker SPOT Preprocessing Job (As a Training Job)

This script launches the preprocessing pipeline as a SageMaker TRAINING Job.
Why? Because Training Jobs support "Managed Spot Training", which saves ~70% cost.
Processing Jobs (SKLearnProcessor) do NOT support Spot instances.
"""
import argparse
from datetime import datetime

import boto3
import sagemaker
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput


def submit_spot_preprocessing(bucket_name, role_arn, profile_name=None):
    print("=" * 80)
    print(f" SUBMITTING SPOT PREPROCESSING JOB ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 80)
    print(f"   Bucket:  {bucket_name}")
    print(f"   Role:    {role_arn}")
    print(f"   Profile: {profile_name or 'default'}")

    # Setup Session
    boto_sess = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
    sess = sagemaker.Session(boto_session=boto_sess)

    # 1. Get Image URI
    # We use the standard Scikit-Learn training image
    image_uri = sagemaker.image_uris.retrieve(
        framework="sklearn",
        region=boto_sess.region_name,
        version="1.2-1",
        py_version="py3",
        instance_type="ml.r5.8xlarge",
    )

    # 2. Define Estimator with SPOT CONFIG
    estimator = Estimator(
        image_uri=image_uri,
        role=role_arn,
        instance_count=1,
        instance_type="ml.r5.8xlarge",
        # Spot Configuration
        use_spot_instances=True,  # <--- KEY SAVINGS
        max_run=3600 * 4,  # 4 hours max runtime
        max_wait=3600 * 5,  # 5 hours max wait (must be > max_run)
        base_job_name="lgbm-spot-prep",
        sagemaker_session=sess,
        # Entry Point
        source_dir=".",  # Upload current directory (includes src/ and scripts/)
        entry_point="spot_optimizer_v1/sagemaker_migration/spot_processing/preprocess_spot_wrapper.py",
        # Pass arguments to the script
        hyperparameters={"output-bucket": bucket_name, "output-prefix": "preprocessed"},
    )

    # 3. Define Inputs
    # We mount the Data directory to /opt/ml/input/data/training
    inputs = {"training": TrainingInput(s3_data=f"s3://{bucket_name}/Data/", distribution="FullyReplicated")}

    print("\n Submitting Managed Spot Training Job...")
    print("   Instance: ml.r5.8xlarge (Spot)")
    print("   Max Runtime: 4 hours")
    print("   Savings: ~60-70%")

    estimator.fit(inputs, wait=True, logs=True)

    print("\n SPOT PROCESSING COMPLETE")
    print(f"   Output should be at: s3://{bucket_name}/preprocessed/preprocessed_features.parquet")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", type=str, required=True)
    parser.add_argument("--role", type=str, required=True)
    parser.add_argument("--profile", type=str, default=None)
    args = parser.parse_args()

    submit_spot_preprocessing(args.bucket, args.role, args.profile)
