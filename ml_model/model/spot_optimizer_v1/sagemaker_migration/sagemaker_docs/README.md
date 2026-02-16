# SageMaker Migration Guide

This folder contains everything needed to deploy the LightGBM Spot Optimizer to AWS SageMaker for full-dataset training and hyperparameter optimization.

## File Structure

```
sagemaker_migration/
├── scripts/
│   ├── submit_preprocessing_job.py  # Launches SageMaker Processing Job for feature engineering
│   ├── preprocess_features_sagemaker.py  # Worker script (runs in Processing Job container)
│   ├── hpo_submitter.py             # Launches distributed hyperparameter optimization
│   ├── submit_final_training.py     # Launches final production training with best params
│   └── train_wrapper.py             # Entry point that runs inside SageMaker training containers
├── sagemaker_docs/
│   ├── README.md                    # This guide
│   ├── AWS_SETUP_GUIDE.md          # Complete setup walkthrough
│   ├── SAGEMAKER_PREPROCESSING.md  # Preprocessing job details
│   ├── HPO_GUIDE.md                # HPO workflow guide
│   └── HOW_sagemaker_WORKS.md      # Technical deep-dive
└── .sagemakerignore                 # Excludes unnecessary files from upload
```

## Quick Start

### 1. Prerequisites
- AWS CLI configured with profiles (`nisha_chothe` or `ml-project`)
- S3 Bucket created in our region
- SageMaker Execution Role created

### 2. Upload Data to S3
See [AWS_SETUP_GUIDE.md](sagemaker_docs/AWS_SETUP_GUIDE.md) for region-specific commands.

Example for Oregon (ml-project):
```bash
aws s3 cp Data/ s3://sagemaker-oregon-ml-project/data/ --recursive --profile ml-project
```

### 3. Run Preprocessing (Recommended)
Generate preprocessed features for fast HPO:
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_preprocessing_job.py \
    --bucket sagemaker-oregon-ml-project \
    --role arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject \
    --profile ml-project
```

### 4. Launch HPO
See [HPO_GUIDE.md](sagemaker_docs/HPO_GUIDE.md) for complete workflow.

---

## How It Works

### Processing Job (Feature Engineering)
- **Script**: `scripts/submit_preprocessing_job.py` (orchestrator) + `scripts/preprocess_features_sagemaker.py` (worker)
- **Purpose**: Materializes all features ONCE to speed up HPO trials
- **Instance**: `ml.r5.8xlarge` (256GB RAM, required for 214M rows)
- **Cost**: ~$2.50 for 45-50 minutes (Spot Optimized)
- **Output**: `s3://BUCKET/preprocessed/preprocessed_features.parquet`

### HPO Job
- **Script**: `scripts/hpo_submitter.py`
- **Purpose**: Finds optimal hyperparameters using Bayesian Optimization
- **Instance**: `ml.r5.8xlarge` (256GB RAM)
- **Parallelism**: 10 concurrent trials
- **Cost**: ~$15.00 - $20.00 for 100 trials (Canary: ~$0.20)

### Final Training
- **Script**: `scripts/submit_final_training.py`
- **Purpose**: Trains production model with best hyperparameters on 100% of data
- **Instance**: `ml.r5.8xlarge`
- **Output**: `model.tar.gz` containing trained models, metrics, and visualizations

### Worker Script
- **File**: `scripts/train_wrapper.py`
- **Runs inside** SageMaker containers
- Handles SageMaker environment variables (`SM_CHANNEL_TRAINING`, `SM_MODEL_DIR`)
- Imports `src.model` and `src.data` directly (no code duplication)
- Supports both raw and preprocessed data paths
- Saves models, plots, and reports to S3 automatically

## Outputs
After jobs complete, check S3:
- Training: `s3://BUCKET/output/lgbm-*/output/model.tar.gz`
- Preprocessing: `s3://BUCKET/preprocessed/preprocessed_features.parquet`

## Learn More
- [AWS_SETUP_GUIDE.md](sagemaker_docs/AWS_SETUP_GUIDE.md) - Complete setup walkthrough
- [HPO_GUIDE.md](sagemaker_docs/HPO_GUIDE.md) - Step-by-step HPO workflow
- [HOW_sagemaker_WORKS.md](sagemaker_docs/HOW_sagemaker_WORKS.md) - Technical deep-dive
