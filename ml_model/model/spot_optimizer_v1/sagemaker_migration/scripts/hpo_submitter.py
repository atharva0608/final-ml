import argparse
import subprocess
import sys
from datetime import datetime

import boto3
from sagemaker import Session
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.tuner import ContinuousParameter, HyperparameterTuner, IntegerParameter

"""
SageMaker Hyperparameter Tuning Submitter.

This script launches a distributed HPO job across multiple SageMaker instances.
It uses Managed Spot Training to reduce costs by ~70%.

MODES:
1. RAW (Slow): ~30 mins/trial
2. PREPROCESSED (Recommended): ~8-15 mins/trial (Optimized)

Instance:
- ml.r5.8xlarge (256GB RAM): Recommended for 100% dataset (Fastest)
- ml.r5.2xlarge (64GB RAM): Sufficient for HPO with 20% sample_fraction (Cheapest)

Parallelism: 10 parallel jobs.
Total Trials: 100.
Estimated Cost: ~$15.00 (Optimized with Spot & Reduced Rounds).
"""


def run_preprocessing(bucket_name, role_arn, profile_name=None):
    """Runs the local preprocessing script."""
    print("\n" + "=" * 80)
    print("  RUNNING PREPROCESSING (Locally)")
    print("=" * 80)

    cmd = [
        "python",
        "spot_optimizer_v1/sagemaker_migration/scripts/submit_preprocessing_job.py",
        "--bucket",
        bucket_name,
        "--role",
        role_arn,
    ]
    if profile_name:
        cmd.extend(["--profile", profile_name])

    try:
        subprocess.check_call(cmd)
        print("\nPreprocessing Complete & Uploaded.")
    except subprocess.CalledProcessError as e:
        print(f"\nPreprocessing Failed: {e}")
        sys.exit(1)


def launch_hpo(
    bucket_name,
    role_arn,
    n_trials=100,
    local_mode=False,
    profile_name=None,
    use_preprocessed=True,
    horizon=6,
    sample_fraction=0.20,
):
    # Setup proper SageMaker session
    boto_sess = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
    sess = Session(boto_session=boto_sess)

    print("=" * 80)
    print(f" SAGEMAKER HPO SUBMISSION ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 80)
    print(f"   Profile: {profile_name if profile_name else 'default'}")
    print(f"   Bucket:  {bucket_name}")
    print(f"   Role:    {role_arn}")
    print(f"   Trials:  {n_trials}")
    print(f"   Mode:    {'LOCAL' if local_mode else 'CLOUD'}")
    print(f"   Data:    {'PREPROCESSED (Fast)' if use_preprocessed else 'RAW (Slow)'}")

    # 1. Resource Validation
    try:
        s3 = boto_sess.resource("s3")
        s3.meta.client.head_bucket(Bucket=bucket_name)
    except Exception:
        print(f" ERROR: S3 Bucket '{bucket_name}' not found or no permission!")
        return

    # 2. Define S3 Input Path
    # Optimized: Use preprocessed data (~8 mins/trial)
    # Naive: Use raw data (~30 mins/trial)
    if use_preprocessed:
        # Note: Could use per-horizon folders (e.g., preprocessed_6) in the future
        s3_input = f"s3://{bucket_name}/preprocessed"
    else:
        s3_input = f"s3://{bucket_name}/data"

    print(f"\nInput Channel: {s3_input}")

    # 3. Define the Estimator Base
    # Note: Using ml.r5.8xlarge for the 256GB RAM needed for 214M rows
    estimator = SKLearn(
        entry_point="sagemaker_migration/scripts/train_wrapper.py",
        source_dir="spot_optimizer_v1",
        role=role_arn,
        # Managed Spot Instances (Massive Cost Savings)
        use_spot_instances=True,
        max_run=3600 * 4,  # 4 hour limit per trial
        max_wait=3600 * 5,  # Must be > max_run for Spot
        # Infrastructure
        instance_type="local" if local_mode else "ml.r5.8xlarge",
        instance_count=1,
        # Frameworks
        framework_version="1.2-1",
        py_version="py3",
        # Static Hyperparameters (Fixed during tuning)
        hyperparameters={
            "horizon": horizon,  # Dynamic horizon
            "sample_fraction": sample_fraction,  # Configurable sampling
            "skip_backtest": "1",  # 1=True, 0=False
        },
        sagemaker_session=sess,
        # Dependencies installed by train_wrapper.py itself (safer than SageMaker auto-install)
    )

    # 4. Define Tuning Configuration
    tuner = HyperparameterTuner(
        estimator=estimator,
        objective_metric_name="val_mape",
        objective_type="Minimize",
        hyperparameter_ranges={
            # Regressor hyperparameters
            "num_leaves": IntegerParameter(20, 80),
            "learning_rate": ContinuousParameter(0.01, 0.15, scaling_type="Logarithmic"),
            "max_depth": IntegerParameter(5, 12),
            "min_child_samples": IntegerParameter(10, 100),
            "lambda_l1": ContinuousParameter(1e-8, 1.0, scaling_type="Logarithmic"),
            "lambda_l2": ContinuousParameter(1e-8, 1.0, scaling_type="Logarithmic"),
            # Classifier-specific hyperparameters (separate tuning)
            "clf_learning_rate": ContinuousParameter(0.005, 0.05, scaling_type="Logarithmic"),
            "clf_num_leaves": IntegerParameter(10, 50),
            "clf_min_child_samples": IntegerParameter(50, 500),
        },
        metric_definitions=[
            {"Name": "val_mape", "Regex": "REPORT_METRIC:regressor_mape=([0-9\\.]+)"},
            {"Name": "val_auc", "Regex": "REPORT_METRIC:classifier_auc=([0-9\\.]+)"},
        ],
        max_jobs=n_trials,  # Dynamic trials (1 for canary, 100 for full)
        max_parallel_jobs=10,  # 10x Parallelism
        base_tuning_job_name="lgbm-hpo-risk-score",
        strategy="Bayesian",  # Use Bayesian Optimization (Smart search)
        early_stopping_type="Auto",  # Prune poorly performing trials automatically
    )

    # 5. Launch Tuning Job
    print(f"\n Launching {n_trials} trials (10 parallel jobs)...")
    tuner.fit({"training": s3_input})

    print("\n HPO JOB SUBMITTED SUCCESSFULLY")
    print(f"   Tuning Job Name: {tuner.latest_tuning_job.name}")
    print(
        f"   Monitor progress at: https://console.aws.amazon.com/sagemaker/home?region={sess.boto_region_name}#/hyper-tuning-jobs/{tuner.latest_tuning_job.name}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit SageMaker HPO Job")
    parser.add_argument("--bucket", type=str, required=True, help="S3 bucket name containing data/")
    parser.add_argument("--role", type=str, required=True, help="SageMaker Execution Role ARN")
    parser.add_argument("--trials", type=int, default=100, help="Number of HPO trials (Default: 100)")
    parser.add_argument("--profile", type=str, default=None, help="AWS CLI Profile to use (e.g., nisha_chothe)")
    parser.add_argument("--horizon", type=int, default=6, help="Prediction horizon intervals (Default: 6)")
    parser.add_argument("--preprocess", action="store_true", help="Run preprocessing script BEFORE submitting HPO")
    parser.add_argument(
        "--use-preprocessed", action="store_true", default=True, help="Use preprocessed data (Default: True)"
    )
    parser.add_argument("--no-preprocessed", dest="use_preprocessed", action="store_false", help="Use raw data (Slow)")
    parser.add_argument("--local", action="store_true", help="Run in local mode (for logic debugging)")
    parser.add_argument(
        "--sample-fraction", type=float, default=0.20, help="Fraction of data to use for HPO (Default: 0.20 = ~1/5th)"
    )

    args = parser.parse_args()

    if args.preprocess:
        run_preprocessing(args.bucket, args.role, args.profile)

    launch_hpo(
        args.bucket,
        args.role,
        args.trials,
        args.local,
        args.profile,
        args.use_preprocessed,
        args.horizon,
        args.sample_fraction,
    )
