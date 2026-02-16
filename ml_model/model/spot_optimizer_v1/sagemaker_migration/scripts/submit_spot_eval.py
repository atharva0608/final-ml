# This code is used with acid test entrypoint for ACID TEST

import argparse

import boto3
import sagemaker
from sagemaker.sklearn.estimator import SKLearn

# --- CONSTANTS ---
MAX_RUN_SECONDS = 600  # 10 minutes max training time
MAX_WAIT_SECONDS = 900  # 15 minutes max wait (includes spot interruption recovery)


def get_best_model_artifact_uri(session, job_name_prefix=None):
    """Auto-detects the best model from HPO using the provided session."""
    client = session.client("sagemaker")

    # Find latest HPO Job
    # Only include NameContains if a prefix is provided (empty string triggers validation error)
    list_args = {"SortBy": "CreationTime", "SortOrder": "Descending", "MaxResults": 1}
    if job_name_prefix:
        list_args["NameContains"] = job_name_prefix

    tuner_resp = client.list_hyper_parameter_tuning_jobs(**list_args)
    if not tuner_resp["HyperParameterTuningJobSummaries"]:
        raise ValueError("No HPO jobs found.")

    tuner_name = tuner_resp["HyperParameterTuningJobSummaries"][0]["HyperParameterTuningJobName"]

    # Get Best Training Job
    desc = client.describe_hyper_parameter_tuning_job(HyperParameterTuningJobName=tuner_name)

    # Check if HPO job has completed and has a best job
    if "BestTrainingJob" not in desc:
        status = desc.get("HyperParameterTuningJobStatus", "Unknown")
        raise ValueError(
            f"HPO job '{tuner_name}' has no BestTrainingJob yet. " f"Status: {status}. Wait for job to complete."
        )

    best_job_name = desc["BestTrainingJob"]["TrainingJobName"]
    s3_uri = client.describe_training_job(TrainingJobName=best_job_name)["ModelArtifacts"]["S3ModelArtifacts"]

    print(f"Target Model: {best_job_name}")
    print(f"   Artifact: {s3_uri}")
    return s3_uri


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", type=str, required=True, help="S3 Bucket with Test Data")
    parser.add_argument("--role", type=str, required=True, help="SageMaker Execution Role ARN")
    parser.add_argument("--profile", type=str, default=None, help="AWS CLI Profile")
    parser.add_argument("--region", type=str, default="us-east-2", help="AWS Region (default: us-east-2)")
    parser.add_argument("--model-uri", type=str, default=None, help="S3 URI of the model artifact (optional)")
    args = parser.parse_args()

    session = (
        boto3.Session(profile_name=args.profile, region_name=args.region)
        if args.profile
        else boto3.Session(region_name=args.region)
    )
    sagemaker_session = sagemaker.Session(boto_session=session)

    # --- CONFIG ---
    # Assuming test data is standardized in the bucket
    S3_TEST_DATA = f"s3://{args.bucket}/preprocessed"

    # Use provided URI or auto-detect
    if args.model_uri:
        S3_MODEL_URI = args.model_uri
        print(f"Target Model (Manual): {S3_MODEL_URI}")
    else:
        try:
            S3_MODEL_URI = get_best_model_artifact_uri(session)
        except Exception as e:
            print(f"Error auto-detecting model: {e}")
            print("   Please provide --model-uri explicitly.")
            return

    # --- SPOT INSTANCE DEFINITION ---
    estimator = SKLearn(
        entry_point="sagemaker_migration/scripts/acid_test_entrypoint.py",
        source_dir="spot_optimizer_v1",  # Upload whole project to allow src access
        role=args.role,
        instance_count=1,
        instance_type="ml.m5.xlarge",  # Updated: Cheaper and sufficient for inference
        framework_version="1.2-1",  # Updated: Matches project standard
        py_version="py3",
        sagemaker_session=sagemaker_session,
        use_spot_instances=True,  # <--- CHEAP MODE
        max_run=MAX_RUN_SECONDS,  # Training timeout
        max_wait=MAX_WAIT_SECONDS,  # Total wait timeout (must be > max_run)
        # dependencies=[]  <-- REMOVED. We install explicitly in entrypoint
    )

    print("\nSubmitting Acid Test to SageMaker Spot...")
    estimator.fit({"test": S3_TEST_DATA, "model": S3_MODEL_URI})  # Mounts model.tar.gz to /opt/ml/input/data/model


if __name__ == "__main__":
    main()
