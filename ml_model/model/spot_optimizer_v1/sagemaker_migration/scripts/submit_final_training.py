#!/usr/bin/env python3
"""
SageMaker Final Training Job Submitter

This script launches a single, high-performance training job using the BEST
hyperparameters found during HPO. It uses the preprocessed dataset for maximum speed.

 # Instance: ml.r5.8xlarge (256GB RAM) - Faster and Safer
# Cost: ~$0.30 - $0.80 using Managed Spot.
"""
import argparse
from datetime import datetime

import boto3
from sagemaker import Session
from sagemaker.sklearn.estimator import SKLearn


def run_final_training(bucket_name, role_arn, profile_name=None, local_mode=False, skip_backtest=False):
    # Setup proper SageMaker session
    boto_sess = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
    sess = Session(boto_session=boto_sess)

    print("=" * 80)
    print(f" SAGEMAKER FINAL TRAINING ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 80)
    print(f"   Profile: {profile_name or 'default'}")
    print(f"   Bucket:  {bucket_name}")
    print(f"   Role:    {role_arn}")
    print(f"   Mode:    {'LOCAL' if local_mode else 'CLOUD'}")
    print(f"   Backtest: {'SKIPPING' if skip_backtest else 'ENABLED'}")

    # 1. Resource Validation
    try:
        s3 = boto_sess.resource("s3")
        s3.meta.client.head_bucket(Bucket=bucket_name)
    except Exception:
        print(f" ERROR: S3 Bucket '{bucket_name}' not found or no permission!")
        return

    # 2. Define S3 Input Path (Using the Preprocessed Fast-Path)
    s3_input = f"s3://{bucket_name}/preprocessed"
    print(f"   Using Preprocessed Data: {s3_input}")

    # 3. Define the Estimator
    # We use the best params found during HPO here
    estimator = SKLearn(
        entry_point="sagemaker_migration/scripts/train_wrapper.py",
        source_dir="spot_optimizer_v1",
        role=role_arn,
        # Managed Spot Instances (Massive Cost Savings)
        use_spot_instances=True,
        max_run=3600 * 5,  # 5 hour limit (Safe for training + optional backtest)
        max_wait=3600 * 6,  # Must be > max_run for Spot
        # Infrastructure
        # Note: If training on 100% of 214M rows, use ml.r5.8xlarge for safety
        instance_type="local" if local_mode else "ml.r5.8xlarge",
        instance_count=1,
        # Frameworks
        framework_version="1.2-1",
        py_version="py3",
        # ================================================================
        # OPTIMAL HYPERPARAMETERS (HPO 100-Trial Run: Jan 22, 2026)
        # Job: lgbm-hpo-risk-score-260122-1224 | Best Trial: #92
        # val_mape: 0.27% | test F1: 0.7547
        # ================================================================
        hyperparameters={
            # Regressor hyperparameters (Price Prediction)
            "num_leaves": 78,
            "learning_rate": 0.09696897462943847,
            "max_depth": 7,
            "min_child_samples": 25,
            "lambda_l1": 0.0008726032755201592,
            "lambda_l2": 2.1811543831298962e-07,
            # Classifier hyperparameters (Risk Prediction)
            "clf_learning_rate": 0.03482301132025348,
            "clf_num_leaves": 45,
            "clf_min_child_samples": 315,
            # Training configuration
            "horizon": 6,  # 1h (6 x 10-min intervals)
            "sample_fraction": 1.0,  # Use 100% data for production model
            "skip_backtest": 1 if skip_backtest else 0,  # Use CLI flag
        },
        sagemaker_session=sess,
        # Dependencies handled by train_wrapper.py's install_dependencies()
        # (removed explicit dependencies= to avoid double-install race with ONNX version)
        # Metrics to track in CloudWatch
        metric_definitions=[
            {"Name": "val_mape", "Regex": "REPORT_METRIC:regressor_mape=([0-9\\.]+)"},
            {"Name": "val_auc", "Regex": "REPORT_METRIC:classifier_auc=([0-9\\.]+)"},
        ],
    )

    print("\n Submitting Final Training Job...")
    estimator.fit({"training": s3_input})

    print("\n FINAL TRAINING COMPLETE")
    print(f"   Model Artifacts: {estimator.model_data}")
    print(
        f"   Monitor at: https://console.aws.amazon.com/sagemaker/home?region={sess.boto_region_name}#/jobs/{estimator.latest_training_job.name}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", type=str, required=True, help="S3 bucket name")
    parser.add_argument("--role", type=str, required=True, help="SageMaker Execution Role ARN")
    parser.add_argument("--profile", type=str, default=None, help="AWS CLI Profile")
    parser.add_argument("--local", action="store_true", help="Run in local mode")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip backtesting for faster training")

    args = parser.parse_args()

    run_final_training(args.bucket, args.role, args.profile, args.local, args.skip_backtest)
