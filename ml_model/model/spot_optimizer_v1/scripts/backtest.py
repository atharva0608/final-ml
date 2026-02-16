#!/usr/bin/env python3
"""
Walk-Forward Backtesting Script for V1 Spot Optimizer.

Runs time-series cross-validation to validate model across multiple time periods.

Usage:
    python spot_optimizer_v1/scripts/backtest.py
"""
import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

import json
from pathlib import Path

from src.backtest import WalkForwardBacktest
from src.data import engineer_all_features, get_feature_columns, load_all_data, load_config, load_stress_events


def main():
    print("=" * 80)
    print("AWS SPOT OPTIMIZER - WALK-FORWARD BACKTESTING")
    print("=" * 80)

    # Create output directory
    Path("reports").mkdir(exist_ok=True)

    # Load config
    config = load_config("config/config.yaml")

    # Load data
    df = load_all_data(config)
    events = load_stress_events(config)

    # Feature engineering
    print("\n" + "=" * 80)
    print("FEATURE ENGINEERING")
    print("=" * 80)

    df = engineer_all_features(df, events, config)

    # Get feature columns
    feature_cols = get_feature_columns()

    print(f"\n Features: {len(feature_cols)}")

    # Run backtesting for each horizon
    all_results = {}

    for horizon in config["features"]["horizons"]:
        horizon_name = {6: "1h", 36: "6h", 144: "24h"}[horizon]

        print(f"\n{'='*80}")
        print(f"BACKTESTING HORIZON: {horizon_name}")
        print(f"{'='*80}")

        # Create backtester
        backtester = WalkForwardBacktest(n_splits=5, test_size_months=2, min_train_months=6, gap_days=0)

        # Run backtest (targets are prepared inside run_backtest on the full DF)
        results = backtester.run_backtest(
            df=df.copy(),  # Copy to avoid affecting other horizons in loop
            feature_cols=feature_cols,
            horizon=horizon,
            n_jobs=config["model"]["n_jobs"],
            early_stopping_rounds=config["model"]["early_stopping_rounds"],
        )

        # Save results
        backtester.save_results(f"reports/backtest_{horizon_name}.json")

        all_results[horizon_name] = results

    # Save combined results
    with open("reports/backtest_combined.json", "w") as f:
        json.dump(all_results, f, indent=2)

    # Print summary
    print("\n" + "=" * 80)
    print("BACKTESTING COMPLETE")
    print("=" * 80)
    print("\n Summary:")

    for horizon_name, results in all_results.items():
        if results:
            print(f"\n{horizon_name}:")
            print(f"  Avg MAPE: {results['regressor']['mape_mean']:.4f} ± {results['regressor']['mape_std']:.4f}")
            print(f"  Avg F1:   {results['classifier']['f1_mean']:.4f} ± {results['classifier']['f1_std']:.4f}")

    print("\nResults saved to: reports/")


if __name__ == "__main__":
    main()
