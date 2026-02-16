# AWS SageMaker Setup Guide (From Scratch)

This guide will help us set up the 3 requirements to run our LightGBM model on the cloud: an **Account**, an **S3 Bucket** (storage), and an **IAM Role** (permission).

---

## Phase 1: AWS Account & CLI (The Connection)


1.  **Create AWS Account**: Go to [aws.amazon.com](https://aws.amazon.com) and sign up.
2.  **Install AWS CLI**:
    *   **Mac**:
        ```bash
        curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
        sudo installer -pkg AWSCLIV2.pkg -target /
        ```
    *   Verify: `aws --version`
3.  **Configure Credentials**:
    *   **Option A: Static Keys (Standard)**:
        *   Go to **IAM Console** -> **Users** -> **Create User**.
        *   Attach Policy: `AdministratorAccess`.
        *   Create **Access Key** for CLI.
        *   Run:
            ```bash
            aws configure
            # Enter Key ID, Secret Key, Region (us-east-2), Output (json)
            ```

    *   **Option B: AWS SSO (Corporate/Enterprise)**:
        *   Run: `aws configure sso`
        *   Enter the Start URL (e.g., `https://my-company.awsapps.com/start`) and Region (`us-east-2`).
        *   It will open a browser to login.
        *   Select the account and role.

    *   **Note for Python**: The Python scripts (`boto3`) will automatically use whatever you configured here. You do NOT need to change the code.

### 1.1 Managing AWS Profiles (Cheat Sheet)

**A. Check Profiles**
`aws configure list-profiles`

**B. Check/Set Region**
```bash
# Check current region of a profile
aws configure get region --profile ml-project

# Change region (e.g., to us-east-1)
aws configure set region us-east-1 --profile ml-project
```

**C. Switch Profiles**
```bash
# Recommended: Use flag per command
aws s3 ls --profile ml-project

# Or set for session
export AWS_PROFILE=ml-project
```

---

## Phase 2: S3 Bucket (The Storage)
SageMaker needs a place to read our data and write our models.

1.  **Create Bucket** (Must be unique globally):
    ### Option A: Quick Copy (Profile: nisha_chothe)
    ```bash
    aws s3 mb s3://ml-sagemaker-lightgbm --region us-east-2 --profile nisha_chothe
    ```

    ### Option B: Quick Copy (Profile: ml-project, Region: us-west-2)
    ```bash
    aws s3 mb s3://sagemaker-oregon-ml-project --region us-west-2 --profile ml-project
    ```

    ### Option B: Reference Template
    ```bash
    aws s3 mb s3://YOUR_BUCKET_NAME --region us-east-2 --profile YOUR_PROFILE_NAME
    ```

2.  **Upload Data**:
    This command uploads the parquet files and stress events to the cloud.

    ### Option A: Quick Copy (Profile: nisha_chothe)
    ```bash
    aws s3 cp Data/ s3://ml-sagemaker-lightgbm/data/ --recursive --profile nisha_chothe
    ```

    ### Option B: Quick Copy (Profile: ml-project)
    ```bash
    aws s3 cp Data/ s3://sagemaker-oregon-ml-project/data/ --recursive --profile ml-project
    ```

    ### Option B: Reference Template
    ```bash
    aws s3 cp Data/ s3://YOUR_BUCKET_NAME/data/ --recursive --profile YOUR_PROFILE_NAME
    ```
    *Verify*: We should see our files at `s3://nisha-lgbm-data-2026/data/`.

---

A **SageMaker Execution Role** is an IAM role that allows the SageMaker service (running on AWS instances) to perform actions on our behalf, such as reading data from S3, writing models, and logging to CloudWatch.

### 1. Create the Role
1.  Go to the **[IAM Roles Console](https://console.aws.amazon.com/iam/home#/roles)**.
2.  Click **Create role**.
3.  **Select trusted entity**:
    *   Entity type: **AWS Service**.
    *   Service or use case: **SageMaker**.
    *   Use case: **SageMaker - Execution**.
4.  Click **Next**.

### 2. Attach Permissions (Policies)
Attach the following managed policies to ensure the cloud instances have proper access:
1.  **`AmazonSageMakerFullAccess`**: Allows launching and managing training/processing jobs.
2.  **`AmazonS3FullAccess`**: Allows reading training data and writing model artifacts.
3.  **`CloudWatchLogsFullAccess`**: (Optional but Recommended) Allows the script to stream logs for real-time monitoring.

### 3. Understanding the Trust Relationship
For the role to work, it must have a **Trust Policy** that allows SageMaker to "Assume" the role. This is created automatically if you follow the steps above, but it looks like this:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "sagemaker.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 4. Locate the Role ARN
Once created, find the role in the list and copy the **Role ARN**.
- It will look like: `arn:aws:iam::ACCOUNT_ID:role/SageMaker-Execution-Role`
- We will need to paste this into our `hpo_submitter.py` or `submit_final_training.py` scripts.

---

## Phase 4: Launch HPO

Now you have everything needed. Replace the values below with yours:

```bash
# 1. Install SageMaker SDK
pip install sagemaker boto3
```

## 4.1. Run Canary HPO (1 Trial)

### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe \
    --trials 1
```

### Option B: Quick Copy (Profile: ml-project)
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
    --bucket YOUR_S3_BUCKET_NAME \
    --role YOUR_SAGEMAKER_ROLE_ARN \
    --profile YOUR_PROFILE_NAME \
    --trials 1
```

> [!TIP]
> **Why 1 Trial?** This "Canary" run verifies the S3 permissions and Memory usage ($0.05 cost) before we commit to the big run.

## 4.2. The Full Run (100 Trials)
Once the Canary succeeds, launch the big job:

### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/hpo_submitter.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe \
    --trials 100
```

### Option B: Quick Copy (Profile: ml-project)
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
    --bucket YOUR_S3_BUCKET_NAME \
    --role YOUR_SAGEMAKER_ROLE_ARN \
    --profile YOUR_PROFILE_NAME \
    --trials 100
```

---

## Phase 5: Final Training (Production Model)

Once HPO determines the best hyperparameters, run the final training job on the full dataset:

### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_final_training.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe
```

### Option B: Quick Copy (Profile: ml-project)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_final_training.py \
    --bucket sagemaker-oregon-ml-project \
    --role arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject \
    --profile ml-project
```

##### Profile: `ml-project` (Oregon / us-west-2)
*   **Bucket**: `sagemaker-oregon-ml-project`
*   **Role**: `arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject`

> [!WARNING]
> **Working Directory**: Run this command from `/Users/nisha/ECC/ML/LightGBM/` (parent of `spot_optimizer_v1/`), NOT from inside `spot_optimizer_v1/`.

*   **Command**:
    ```bash
    # From /Users/nisha/ECC/ML/LightGBM/ directory:
    python spot_optimizer_v1/sagemaker_migration/scripts/submit_preprocessing_job.py \
        --bucket sagemaker-oregon-ml-project \
        --role arn:aws:iam::654654204633:role/SageMaker-ExecutionRole-MLProject \
        --profile ml-project
    ```

### Option C: Dry Run (Local Docker Mode)
To validte the logic locally before submitting to cloud (Requires Docker):
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_final_training.py \
    --bucket ml-sagemaker-lightgbm \
    --role ... \
    --profile nisha_chothe \
    --local
```

---

## Appendix: Region Management

If the quota is in a different region than the profile's default, update the profile or specify the region in the commands.

**To set Oregon (us-west-2) as default for ml-project:**
```bash
aws configure set region us-west-2 --profile ml-project
```

---

## Phase 6: Evaluation (The "Acid Test")
After HPO or Final Training, we must verify if the model is learning "Physics" (Predicting Change) or just "Persistence" (Memorizing the last price).

**Run the Spot Evaluation Job:**
This spins up a cheap `ml.m5.large` Spot Instance to run the validation against robust metrics (Dynamic MAPE).

### Option A: Quick Copy (Profile: nisha_chothe)
```bash
python spot_optimizer_v1/sagemaker_migration/scripts/submit_spot_eval.py \
    --bucket ml-sagemaker-lightgbm \
    --role arn:aws:iam::888245942216:role/service-role/AmazonSageMaker-ExecutionRole-20260105T172312 \
    --profile nisha_chothe
```
*   **Result**: Look for ` VERDICT` in the logs (CloudWatch or Console).
*   **Pass**: Model beats persistence > 0%.
*   **Fail**: Model is worse/equal to persistence.
