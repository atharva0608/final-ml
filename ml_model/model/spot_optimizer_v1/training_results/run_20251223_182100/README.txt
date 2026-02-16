============================================================
TRAINING RUN SUMMARY
============================================================

Timestamp: 2025-12-23T18:21:00

TRAINING SETTINGS:
----------------------------------------
  Horizons: [36]
  Sample Families: ['c6i', 'm6i', 'r6i']
  Lag Intervals: [6, 24, 144]
  Rolling Windows: [24, 144]
  Filter Critical Pools: True
  Pool Risk Feature: True
  Use Family Stress: True

MODEL PARAMS:
----------------------------------------
  num_leaves: 31
  max_depth: 8
  lambda_l2: 0.1
  learning_rate: 0.05
  early_stopping_rounds: 100
  is_unbalance: True (classifier)

DATA INFO:
----------------------------------------
  total_rows: 13,755,918
  train_rows: 9,629,142
  val_rows: 2,063,388
  test_rows: 2,063,388
  n_features: 37
  n_pools: 90

RESULTS:
----------------------------------------

  6h:
    Regressor MAPE: 0.0046
    Regressor RMSE: 2.0168
    Regressor R²:   0.9714
    Classifier F1:  0.2904
    Classifier AUC: 0.6507
    Classifier Precision: 0.5086
    Classifier Recall: 0.2032

NOTES:
----------------------------------------
  - First training run with pool risk feature
  - Critical pools (>20% zeros) filtered out
  - MAPE filter applied for near-zero values
  - Regressor performs excellently (0.46% error)
  - Classifier needs improvement (low recall)
