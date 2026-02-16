# SageMaker HPO Guide - Risk Score Optimizer

This guide explains how to run the Hyperparameter Optimization (HPO) for the LightGBM Spot Optimizer across 214 million rows of data.

## 1. Prerequisites
- **Data in S3**: Ensure the `.parquet` files and `mumbai_stress_events_validated.csv` are in `s3://YOUR_BUCKET/data/`.
- **AWS Permissions**: Our CLI/Environment must have `SageMakerFullAccess` permissions.

## 2. Infrastructure
- **Instance**: `ml.r5.8xlarge` (32 vCPU, 256GB RAM).
- **Why**: Feature engineering on 214M rows requires high memory.
- **Cost Savings**: The script uses **Managed Spot Instances**, reducing costs from **~$50.00** down to **~$15.00** (approx 70% savings) for the entire 100-trial run.

## 3. Tunable Parameters (New!)
We now tune **Regressor** and **Classifier** independently to solve class imbalance:
- **Regressor**: `num_leaves`, `learning_rate`, etc. (Target: MAPE)
- **Classifier**: `clf_num_leaves`, `clf_learning_rate`, `clf_min_child_samples` (Target: AUC)


## 4. Pre-process Features (Required One-Time Step)
Before running any HPO trials, we must engineer the features once and upload them to S3. This saves ~38 hours of compute time.

### Option A: Quick Copy (Our Config)
```bash
### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket ml-sagemaker-lightgbm \
    --profile nisha_chothe \
    --preprocess
```

### Option B: Quick Copy (Profile: ml-project)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket sagemaker-oregon-ml-project \
    --profile ml-project \
    --preprocess
```
```

### Option B: Reference Template
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket YOUR_BUCKET_NAME \
    --profile YOUR_PROFILE_NAME \
    --preprocess
```
*Wait for this to complete (approx 15-20 mins) and print "Upload Successful".*

## 5. Run Canary HPO (1 Trial)
Now verify the full pipeline with a single trial using the preprocessed data.### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe \
    --trials 1
```

### Option B: Quick Copy (Profile: ml-project, Region: us-west-2)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket sagemaker-oregon-ml-project \
    --role arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject \
    --profile ml-project \
    --trials 1
```

### Option B: Reference Template
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket YOUR_BUCKET_NAME \
    --role YOUR_ROLE_ARN \
    --profile YOUR_PROFILE_NAME \
    --trials 1
```

## 6. The Full Run (100 Trials)
Once the Canary succeeds, launch the big job:

### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe \
    --trials 100
```

### Option B: Quick Copy (Profile: ml-project, Region: us-west-2)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket sagemaker-oregon-ml-project \
    --role arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject \
    --profile ml-project \
    --trials 100
```

### Option B: Reference Template
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket YOUR_BUCKET_NAME \
    --role YOUR_ROLE_ARN \
    --profile YOUR_PROFILE_NAME \
    --trials 100
```

## 7. What happens next?
1. **Parallel Execution**: SageMaker spins up **10 parallel instances**.
2. **Bayesian Optimization**: Each trial learns from the previous ones to find the "peak" performance faster.
3. **Internal Sampling**: Each instance engineers the full dataset but then samples down to **20%** for the actual tuning trials to ensure speed while maintaining lag/rolling window accuracy.
4. **Monitoring**: We can watch the metrics (MAPE and LogLoss) in the SageMaker Console or CloudWatch.
5. **Early Stopping (Pruning)**: SageMaker automatically monitors the trials. If a trial's performance is significantly worse than the others (e.g., MAPE is 2x the median), SageMaker will "prune" (terminate) it early to save time and spot instance costs.

---

## 8. Pruning vs. Early Stopping
In our architecture, we use two types of "early stops" to maximize efficiency:

| Feature | Level | Tool | Goal |
| :--- | :--- | :--- | :--- |
| **Model Early Stopping** | Trial-level | LightGBM (`callbacks`) | Stop a *single* trial if the validation score stops improving for 100 rounds. |
| **HPO Pruning** | Job-level | SageMaker (`EarlyStoppingConfig`) | Stop an *entire trial* if its early performance is mathematically unlikely to beat the current best. |

**Impact**: Pruning typically reduces the total HPO cost by **20-30%** by not finishing "lost cause" experiments.

---

## 9. Fetching Results
Once complete, the best parameters will be visible in the SageMaker Console under **Best Training Job**.

### Manual Steps after HPO:
1. Identify the `best_params_regressor` and `best_params_classifier`.
2. Update `src/model.py` with these values in the `__init__` or `train_` methods.
3. Run the final training on the **full 100% dataset** (no sampling) to produce the production model.

```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_final_training.py \
    --bucket YOUR_S3_BUCKET_NAME \
    --role YOUR_SAGEMAKER_ROLE_ARN
```
