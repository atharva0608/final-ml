#!/usr/bin/env python3
"""
SageMaker Environment Check Submitter

PURPOSE:
    Submits a lightweight SageMaker training job to inspect the container's environment.
    It runs `analyze_container_env.py` which prints installed libraries and versions.

USAGE:
    python sagemaker_migration/scripts/submit_env_check.py --bucket <S3_BUCKET> --role <IAM_ROLE_ARN> [--profile <AWS_PROFILE>]

EXAMPLE:
    python sagemaker_migration/scripts/submit_env_check.py \
        --bucket spot-optimizer-training \
        --role arn:aws:iam::123456789012:role/SageMakerSpotRole

OUTPUT:
    The job logs (viewable in CloudWatch or standard output if wait=True) will show:
    - Python version
    - Versions of critical libraries (lightgbm, pandas, numpy, etc.)
    - Full `pip freeze` output
"""
import argparse
from datetime import datetime

import boto3
import sagemaker
from sagemaker import Session
from sagemaker.sklearn.estimator import SKLearn


def run_env_check(bucket_name, role_arn, profile_name=None):
    boto_sess = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
    sess = Session(boto_session=boto_sess)

    print("=" * 60)
    print(f" SAGEMAKER ENV CHECK ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 60)

    estimator = SKLearn(
        entry_point="sagemaker_migration/scripts/analyze_container_env.py",
        source_dir="spot_optimizer_v1",
        role=role_arn,
        use_spot_instances=True,
        max_run=600,
        max_wait=1200,
        instance_type="ml.m5.xlarge",  # Small instance is fine
        instance_count=1,
        framework_version="1.2-1",
        py_version="py3",
        sagemaker_session=sess,
        dependencies=[],  # No extra dependencies, we want to see BASE container state
    )

    print("\n Submitting Environment Check Job...")
    # Passing dummy inputs to trigger training job
    estimator.fit(wait=True)  # blocking so we can see logs immediately


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", type=str, required=True, help="S3 bucket name")
    parser.add_argument("--role", type=str, required=True, help="SageMaker Execution Role ARN")
    parser.add_argument("--profile", type=str, default=None, help="AWS CLI Profile")

    args = parser.parse_args()

    run_env_check(args.bucket, args.role, args.profile)
