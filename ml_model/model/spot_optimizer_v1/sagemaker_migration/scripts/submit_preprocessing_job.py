#!/usr/bin/env python3
"""
SageMaker Processing Job - Feature Engineering

This script submits a SageMaker Processing job to engineer features from raw data.
The job runs on ml.r5.8xlarge (256GB RAM) to handle 214M rows.

Output: Preprocessed Parquet file saved to s3://BUCKET/preprocessed/
"""
import argparse
from datetime import datetime

import boto3
from sagemaker import Session
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.sklearn.processing import SKLearnProcessor


def submit_preprocessing_job(bucket_name, role_arn, profile_name=None):
    print("=" * 80)
    print(f" SUBMITTING PREPROCESSING JOB ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 80)
    print(f"   Bucket:  {bucket_name}")
    print(f"   Role:    {role_arn}")
    print(f"   Profile: {profile_name or 'default'}")

    # Setup proper SageMaker session
    boto_sess = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
    sess = Session(boto_session=boto_sess)

    # Create SKLearnProcessor (Handles source_dir bundling automatically)
    processor = SKLearnProcessor(
        framework_version="1.2-1",
        role=role_arn,
        instance_count=1,
        instance_type="ml.r5.8xlarge",  # 256GB RAM (upgraded from 4xlarge)
        volume_size_in_gb=100,
        max_runtime_in_seconds=3600 * 4,  # 4 hour limit (Safe for 214M rows)
        base_job_name="lgbm-preprocessing",
        sagemaker_session=sess,
        tags=[{"Key": "project", "Value": "ml-project"}],
    )

    # Define I/O
    inputs = [
        # Data
        ProcessingInput(
            source=f"s3://{bucket_name}/Data/",
            destination="/opt/ml/processing/input/data",
            s3_data_distribution_type="FullyReplicated",
        ),
        # Source Code (since source_dir isn't supported in this SDK version for .run)
        ProcessingInput(source="spot_optimizer_v1", destination="/opt/ml/processing/input/code/spot_optimizer_v1"),
    ]

    outputs = [
        ProcessingOutput(
            source="/opt/ml/processing/output",
            destination=f"s3://{bucket_name}/preprocessed/",
            output_name="preprocessed",
        )
    ]

    # Submit job
    print("\n Submitting Processing Job...")
    print("   Instance: ml.r5.8xlarge (256GB RAM, 32 vCPUs)")
    print("   Estimated time: 35-40 mins")
    print("   Estimated cost: $0.60")

    processor.run(
        code="spot_optimizer_v1/sagemaker_migration/scripts/preprocess_features_sagemaker.py",
        inputs=inputs,
        outputs=outputs,
        wait=True,  # Block until complete
        logs=True,  # Stream logs to console
    )

    print("\n PREPROCESSING COMPLETE")
    print(f"   Output: s3://{bucket_name}/preprocessed/preprocessed_features.parquet")
    print("   You can now run HPO!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit SageMaker Preprocessing Job")
    parser.add_argument("--bucket", type=str, required=True, help="S3 bucket name")
    parser.add_argument("--role", type=str, required=True, help="SageMaker Execution Role ARN")
    parser.add_argument("--profile", type=str, default=None, help="AWS CLI Profile")

    args = parser.parse_args()

    submit_preprocessing_job(args.bucket, args.role, args.profile)
