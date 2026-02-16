# SageMaker Preprocessing Job Guide

This document explains how to run the **Feature Engineering** step on a robust SageMaker Processing cluster instead of our local machine.

## The Problem
Our dataset (200M+ rows) requires **~100GB RAM** for feature engineering (lag features, rolling windows).
- **Local Machine**: Crashes (OOM Error)
- **SageMaker Training Instance**: Expensive if doing it repeatedly for HPO

## The Solution: A Dedicated Processing Job
We use **SageMaker Processing** to spin up a temporary, high-memory instance (`ml.r5.8xlarge`, 256GB RAM) to do the heavy lifting **once**.

### Workflow
1. **We** run `submit_preprocessing_job.py` from our laptop.
2. **SageMaker** spins up a cluster.
3. **Cluster** downloads raw data from S3.
4. **Cluster** bundles our local `spot_optimizer_v1` code (so it can use `src.data`).
5. **Cluster** runs `preprocess_features_sagemaker.py`.
6. **Cluster** saves the result (`preprocessed_features.parquet`) to S3.
7. **Cluster** shuts down.

---

##  How to Run

**Command:**
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_preprocessing_job.py \
    --bucket YOUR_BUCKET_NAME \
    --role YOUR_SAGEMAKER_ROLE_ARN \
    --profile YOUR_PROFILE_NAME
```

**Example (Profile: nisha_chothe):**
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_preprocessing_job.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe
```

**Example (Profile: ml-project, Region: us-west-2):**
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_preprocessing_job.py \
    --bucket sagemaker-oregon-ml-project \
    --role arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject \
    --profile ml-project
```

> [!NOTE]
> If the command above fails with a "Region" error, run:
> `aws configure set region us-west-2 --profile ml-project`


---

##  File Structure

- **Orchestrator**: `sagemaker_migration/scripts/submit_preprocessing_job.py`
  - Runs locally. Submits the request to AWS.
- **Worker**: `sagemaker_migration/scripts/preprocess_features_sagemaker.py`
  - Runs in the cloud. Does the actual Polars work (Rust-optimized).
- **Output**: `s3://YOUR_BUCKET/preprocessed/preprocessed_features.parquet`

##  FAQ

**Q: Why do we see "Uploading ..."?**
A: The script bundles our local code (`spot_optimizer_v1`) and uploads it to S3 so the SageMaker instance can import the project modules.

**Q: What if we change `src/data.py`?**
A: We must re-run the preprocessing job! The HPO job reads the *saved* parquet file, not the live code for features.

**Q: How much does it cost?**
A: Approx **$2.50** per run (45-50 mins on ml.r5.8xlarge).
