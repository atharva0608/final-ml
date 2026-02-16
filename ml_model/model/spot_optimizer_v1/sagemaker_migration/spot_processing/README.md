# SageMaker Spot Preprocessing

This directory contains logic to run the **Feature Engineering Pipeline** on **SageMaker Training Jobs** (instead of Processing Jobs).

## Why?
*   **Processing Jobs (`SKLearnProcessor`)**: Do NOT support Spot Instances. Cost: ~$5.00/run (On-Demand).
*   **Training Jobs (`Estimator`)**: Support **Managed Spot Training**. Cost: ~$1.50/run (**~70% Savings**).

## Architecture

1.  **Submitter (`submit_spot_processing.py`)**:
    *   Uses `sagemaker.estimator.Estimator`
    *   Sets `use_spot_instances=True`
    *   Mounts data to `/opt/ml/input/data/training`
    *   Uses standard Scikit-Learn image

2.  **Worker (`preprocess_spot_wrapper.py`)**:
    *   Runs inside the container.
    *   Installs dependencies from `requirements_sagemaker.txt`.
    *   Calls shared logic in `src/data.py` (which is now optimized).
    *   Uploads output directly to `s3://BUCKET/preprocessed/preprocessed_features.parquet`.

## How to Run

Run this from the root of the workspace:

```bash
python spot_optimizer_v1/sagemaker_migration/spot_processing/submit_spot_processing.py \
    --bucket YOUR_BUCKET_NAME \
    --role YOUR_ROLE_ARN \
    --profile YOUR_AWS_PROFILE
```

## Optimizations Included
The shared `src/data.py` has been heavily optimized:
*   **Polars (New)**: `src/data_polars.py` handles heavy rolling windows (>60x speedup).
*   **Memory**: In-place operations (no `df.copy()`).
*   **Speed**: Single global sort (no redundant sorting of 214M rows).
*   **Events**: `merge_asof` instead of broadcasting.

## Performance Benchmarks (ml.r5.8xlarge)
*   **Pandas (Old)**: Rolling features took >135 minutes (Timeout).
*   **Polars (New)**: Rolling features took **~2 minutes**.
*   **Total Job Time**: ~1 hour 15 minutes.
*   **Memory Usage (Run #13)**: Peak **91%**, Average **73%**.
    *   *Note*: This confirms `ml.r5.8xlarge` (256GB) is the *minimum* viable instance size. `ml.r5.4xlarge` (128GB) would have OOM'd.

## Configuration Parameters (Run #13)
The following settings were hardcoded in `preprocess_spot_wrapper.py` for this optimized run:

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Instance Type** | `ml.r5.8xlarge` | 32 vCPUs, 256GB RAM (Spot) |
| **Lag Intervals** | `[6, 24, 144]` | 1h, 4h, 24h lags |
| **Rolling Windows** | `[24, 72, 144]` | 4h, 12h, 24h windows |
| **Horizon** | `6` | 1-hour prediction target |
| **Stress Features** | `True` | Family Stress Index enabled |
| **Pool Filtering** | `True` | Filtered critical pools (>20% zeros) |
| **Sample Families** | `None` | processed **ALL** instance families |

## Troubleshooting
If the job dies with "AlgorithmError", check CloudWatch logs.
Common issues:
*   **Spot Interruption**: SageMaker will auto-retry.
*   **Memory**: `ml.r5.8xlarge` (256GB) should be sufficient for 214M rows.
