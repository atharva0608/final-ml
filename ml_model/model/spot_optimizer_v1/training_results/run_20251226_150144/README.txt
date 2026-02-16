============================================================
TRAINING RUN SUMMARY
============================================================

Timestamp: 2025-12-26T15:11:38.417142

TRAINING SETTINGS:
----------------------------------------
  Horizons: [36]
  Sample Families: ['c6i', 'm6i', 'r6i']
  Lag Intervals: [6, 24, 144]
  Rolling Windows: [24, 144]
  Filter Critical Pools: True
  Pool Risk Feature: True

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
    Regressor RMSE: 2.0104
    Regressor R²:   0.9716
    Classifier F1:  0.5790
    Classifier AUC: 0.6475
