#!/usr/bin/env python3
"""
Training script for V1 Internal Decision system.
Trains hybrid model for single horizon: 6h

Creates timestamped run folders in training_results/ with:
- models/: Trained LightGBM models
- reports/: Metrics JSON
- feature_importance/: CSV files
- README.txt: Training summary
Usage:
    python spot_optimizer_v1/scripts/train.py
"""
import os
import sys
from datetime import datetime

# Add project root to path so imports work from any directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402
from src.data import (  # noqa: E402
    chronological_split,
    engineer_all_features,
    get_feature_columns,
    load_all_data,
    load_config,
    load_stress_events,
    prepare_targets,
)
from src.model import HybridSpotModel  # noqa: E402
from src.visualize import ModelVisualizer  # noqa: E402


def compute_pool_baselines(train_df: pd.DataFrame) -> dict:
    """Compute baseline mean and std for each pool."""
    print("\n Computing Pool Baselines for Z-Score Classification...")

    # REF: AUDIT-FIX - Vectorized using .agg() instead of loop
    stats = train_df.groupby(["InstanceType", "AZ"])["Savings"].agg(["mean", "std", "count"])

    baselines = {}
    for (instance_type, az), row in stats.iterrows():
        pool_id = f"{instance_type}_{az}"
        baselines[pool_id] = {
            "instance_type": instance_type,
            "az": az,
            "mean_savings": float(row["mean"]),
            "std_savings": float(row["std"]) if pd.notna(row["std"]) else 0.0,
            "count": int(row["count"]),
        }

    print(f"Computed baselines for {len(baselines)} pools")
    return baselines


def create_run_folder() -> Path:
    """Create timestamped run folder within training_results."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = Path("training_results") / f"run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "models").mkdir(exist_ok=True)
    (run_folder / "reports").mkdir(exist_ok=True)
    (run_folder / "feature_importance").mkdir(exist_ok=True)
    return run_folder


def save_training_summary(run_folder: Path, config: dict, data_info: dict, results: dict):
    """Save training settings and results summary."""
    summary = {
        "timestamp": datetime.now().isoformat(),
        "training_settings": {
            "horizons": config["features"]["horizons"],
            "sample_families": config["data"].get("sample_families", []),
            "lag_intervals": config["features"]["lag_intervals"],
            "rolling_windows": config["features"]["rolling_windows"],
            "use_family_stress": config["features"]["use_family_stress"],
            "filter_critical_pools": config["features"].get("filter_critical_pools", True),
            "add_pool_risk_feature": config["features"].get("add_pool_risk_feature", True),
        },
        "model_params": {
            "num_leaves": 21,
            "max_depth": 9,
            "lambda_l2": 0.319265,
            "learning_rate": 0.075129,
            "early_stopping_rounds": 100,
        },
        "data_info": data_info,
        "results": results,
    }

    # Save as JSON
    with open(run_folder / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Save human-readable summary
    with open(run_folder / "README.txt", "w") as f:
        f.write("=" * 60 + "\n")
        f.write("TRAINING RUN SUMMARY\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Timestamp: {summary['timestamp']}\n\n")

        f.write("TRAINING SETTINGS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"  Horizons: {config['features']['horizons']}\n")
        families = config["data"].get("sample_families", [])
        f.write(f"  Sample Families: {families if families else 'ALL'}\n")
        f.write(f"  Lag Intervals: {config['features']['lag_intervals']}\n")
        f.write(f"  Rolling Windows: {config['features']['rolling_windows']}\n")
        f.write(f"  Filter Critical Pools: {config['features'].get('filter_critical_pools', True)}\n")
        f.write(f"  Pool Risk Feature: {config['features'].get('add_pool_risk_feature', True)}\n\n")

        f.write("DATA INFO:\n")
        f.write("-" * 40 + "\n")
        for key, value in data_info.items():
            f.write(f"  {key}: {value:,}\n")
        f.write("\n")

        f.write("RESULTS:\n")
        f.write("-" * 40 + "\n")
        for horizon, metrics in results.items():
            f.write(f"\n  {horizon}:\n")
            f.write(f"    Regressor MAPE: {metrics['regressor']['mape']:.4f}\n")
            f.write(f"    Regressor RMSE: {metrics['regressor']['rmse']:.4f}\n")
            f.write(f"    Regressor R²:   {metrics['regressor']['r2']:.4f}\n")
            f.write(f"    Classifier F1:  {metrics['classifier']['f1']:.4f}\n")
            f.write(f"    Classifier AUC: {metrics['classifier']['auc']:.4f}\n")


def main():
    print("=" * 80)
    print("AWS SPOT OPTIMIZER - V1 TRAINING")
    print("=" * 80)

    # Create run folder
    run_folder = create_run_folder()
    print(f"\n Run folder: {run_folder}")

    # Load config
    # Load config (searching from project root for robustness)
    config_path = os.path.join(project_root, "config/config.yaml")
    config = load_config(config_path)

    # REF: OPTIMIZATION - Feature caching to skip recomputation
    cache_path = Path(project_root) / "data" / "preprocessed_features_cache.parquet"

    if cache_path.exists():
        print(f"\n Loading cached features from {cache_path}...")
        df = pd.read_parquet(cache_path)
        print(f"  Loaded {len(df):,} rows from cache.")
    else:
        # Load data
        print("\n Loading data...")
        df = load_all_data(config)
        events = load_stress_events(config)

        # Feature engineering (BEFORE split to prevent data leakage)
        df = engineer_all_features(df, events, config)

        # Save to cache for next run
        print(f"\n Saving features to cache: {cache_path}")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        print(f"  Saved {len(df):,} rows.")

    # Prepare targets (BEFORE split to avoid rolling window reset and ensure consistency)
    horizon = config["features"]["horizons"][0]
    print(f"\n Preparing targets (horizon={horizon})...")
    df = prepare_targets(df, horizon)

    # Chronological split
    train_df, val_df, test_df = chronological_split(
        df, train_pct=config["split"]["train"], val_pct=config["split"]["val"], test_pct=config["split"]["test"]
    )

    # Store data info
    data_info = {
        "total_rows": len(df),
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "test_rows": len(test_df),
        "n_features": len(get_feature_columns()),
        "n_pools": df.groupby(["InstanceType", "AZ"]).ngroups,
    }

    # Compute and save pool baselines
    baselines = compute_pool_baselines(train_df)
    with open(run_folder / "pool_baselines.json", "w") as f:
        json.dump(baselines, f, indent=2)
    print("   Saved pool baselines")

    # Get feature columns
    feature_cols = get_feature_columns()
    print(f"\n Features: {len(feature_cols)}")
    print(f"  {', '.join(feature_cols[:10])}...")

    # Prepare features
    X_train = train_df[feature_cols]
    X_val = val_df[feature_cols]
    X_test = test_df[feature_cols]

    # Train models
    print("\n" + "=" * 80)
    print("TRAINING MODELS")
    print("=" * 80)

    results = {}

    for horizon in config["features"]["horizons"]:
        # REF: OPTIMIZATION - Safe horizon mapping with fallback
        horizon_name = {6: "1h", 36: "6h", 144: "24h"}.get(horizon, f"{horizon}int")
        print(f"\n{'='*80}")
        print(f"HORIZON: {horizon_name} ({horizon} intervals)")
        print(f"{'='*80}")

        model = HybridSpotModel(horizon=horizon, n_jobs=config["model"]["n_jobs"])

        # Targets already exist in train_df/val_df from prepare_targets() at line 174
        model.fit(
            X_train,
            X_val,
            y_reg_train=train_df["future_savings"],
            y_reg_val=val_df["future_savings"],
            y_clf_train=train_df["is_unstable"],
            y_clf_val=val_df["is_unstable"],
        )

        # REF: AUDIT-FIX - Optimize threshold before evaluation
        print("  Optimizing classification threshold...")
        model.optimize_threshold(X_val, val_df)

        metrics = model.evaluate(X_test, test_df.copy())

        # Save model
        model.save(str(run_folder / "models"))

        # Save feature importance
        if hasattr(model, "regressor_importance"):
            model.regressor_importance.to_csv(
                run_folder / "feature_importance" / f"regressor_{horizon_name}.csv", index=False
            )
        if hasattr(model, "classifier_importance"):
            model.classifier_importance.to_csv(
                run_folder / "feature_importance" / f"classifier_{horizon_name}.csv", index=False
            )

        results[horizon_name] = metrics

    # Save results
    with open(run_folder / "reports" / "training_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Save training summary
    save_training_summary(run_folder, config, data_info, results)

    # Generate visualizations
    visualizer = ModelVisualizer(output_dir=str(run_folder / "visualizations"))
    optimal_threshold = visualizer.generate_essential_dashboards(
        model=model, X_test=X_test, test_df=test_df, feature_names=feature_cols
    )
    print(f"  Optimal classifier threshold: {optimal_threshold:.3f}")

    print("\n" + "=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)
    print(f"\n All outputs saved to: {run_folder}/")
    print("   ├── models/           : Trained LightGBM models")
    print("   ├── reports/          : Metrics JSON")
    print("   ├── feature_importance/ : CSV files")
    print("   └── README.txt        : Training summary")

    print("\n Summary:")
    for horizon, metrics in results.items():
        print(f"\n{horizon}:")
        print(f"Regressor MAPE: {metrics['regressor']['mape']:.4f}")
        print(f"Classifier F1:  {metrics['classifier']['f1']:.4f}")


if __name__ == "__main__":
    main()
