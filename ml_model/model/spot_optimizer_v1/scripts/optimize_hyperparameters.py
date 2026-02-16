#!/usr/bin/env python3
"""
Unified Optuna Hyperparameter Optimization Script.

Features:
- TimeSeriesSplit Cross-Validation (3-5 splits)
- LightGBM Pruning Callback for efficiency
- Configurable systematic sampling
- Binary logloss optimization for calibrated probabilities
- Supports both Regressor and Classifier

Usage:
    # Standard optimization (uses config.yaml settings)
    python spot_optimizer_v1/scripts/optimize_hyperparameters.py

    # Quick dry run (1 trial, no CV)
    python spot_optimizer_v1/scripts/optimize_hyperparameters.py --dry-run

    # Regressor only
    python spot_optimizer_v1/scripts/optimize_hyperparameters.py --regressor-only

    # Classifier only
    python spot_optimizer_v1/scripts/optimize_hyperparameters.py --classifier-only
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from optuna.integration import LightGBMPruningCallback
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from sklearn.metrics import log_loss, mean_absolute_percentage_error
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings("ignore")

from src.data import (
    engineer_all_features,
    get_feature_columns,
    load_all_data,
    load_config,
    load_stress_events,
    prepare_targets,
)


def systematic_sample(df: pd.DataFrame, fraction: float) -> pd.DataFrame:
    """
    Systematic sampling: Take every Nth row to preserve temporal coverage.

    Args:
        df: Input DataFrame (must be sorted by timestamp)
        fraction: Fraction to sample (e.g., 0.2 = 20%)

    Returns:
        Sampled DataFrame maintaining time-series properties
    """
    if fraction >= 1.0:
        return df

    step = int(1 / fraction)
    n_sample = int(len(df) * fraction)

    sampled = df.iloc[::step].head(n_sample).copy()

    print(f"  Systematic Sampling: {len(df):,} → {len(sampled):,} rows ({fraction*100:.0f}%)")
    print(f"  Time range: {sampled['timestamp'].min()} to {sampled['timestamp'].max()}")

    return sampled


class OptunaOptimizer:
    """
    Hyperparameter optimization with TimeSeriesSplit CV and Pruning.
    """

    def __init__(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        model_type: str = "regressor",
        n_cv_splits: int = 3,
        enable_pruning: bool = True,
        n_jobs: int = 8,
    ):
        # REF: OPTIMIZATION - Don't store X/y to allow garbage collection
        # Pass X/y to optimize() method instead
        self.X = X  # Reference only, will be None-d after optimize
        self.y = y
        self.model_type = model_type
        self.n_cv_splits = n_cv_splits
        self.enable_pruning = enable_pruning
        self.n_jobs = n_jobs

        # REF: OPTIMIZATION - Check GPU availability
        try:
            import torch

            self.device = "gpu" if torch.cuda.is_available() else "cpu"
        except ImportError:
            self.device = "cpu"
        print(f"  Device: {self.device}")

    def suggest_params(self, trial: optuna.Trial) -> Dict:
        """Suggest hyperparameters with optimized search space."""
        # REF: OPTIMIZATION - Added dynamic early stopping
        early_stopping = trial.suggest_int("early_stopping", 20, 100)

        params = {
            "objective": "regression" if self.model_type == "regressor" else "binary",
            "metric": "mape" if self.model_type == "regressor" else "binary_logloss",
            "boosting_type": "gbdt",
            "verbosity": -1,
            "n_jobs": self.n_jobs,
            "seed": 42,
            # REF: OPTIMIZATION - GPU support
            "device": self.device,
            # Tree structure
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "min_child_weight": trial.suggest_float("min_child_weight", 1e-4, 1.0, log=True),
            # Regularization
            "lambda_l1": trial.suggest_float("lambda_l1", 1e-4, 1.0, log=True),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-4, 1.0, log=True),
            # Sampling
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 0.95),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 0.95),
            "bagging_freq": trial.suggest_int("bagging_freq", 1, 10),
        }

        # Store early_stopping for use in objective
        trial.set_user_attr("early_stopping", early_stopping)

        return params

    def objective(self, trial: optuna.Trial) -> float:
        """
        Objective function with TimeSeriesSplit CV and optional pruning.

        Returns:
            float: Mean CV score (MAPE for regressor, logloss for classifier)
        """
        params = self.suggest_params(trial)

        # TimeSeriesSplit for proper time-series CV
        tscv = TimeSeriesSplit(n_splits=self.n_cv_splits)
        cv_scores = []

        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(self.X)):
            X_train_fold = self.X.iloc[train_idx]
            y_train_fold = self.y.iloc[train_idx]
            X_val_fold = self.X.iloc[val_idx]
            y_val_fold = self.y.iloc[val_idx]

            # Create datasets
            train_data = lgb.Dataset(X_train_fold, label=y_train_fold)
            val_data = lgb.Dataset(X_val_fold, label=y_val_fold, reference=train_data)

            # REF: OPTIMIZATION - Use dynamic early stopping from trial
            early_stopping_rounds = trial.user_attrs.get("early_stopping", 50)
            callbacks = [lgb.early_stopping(early_stopping_rounds, verbose=False)]

            # Add pruning callback if enabled
            if self.enable_pruning:
                callbacks.append(LightGBMPruningCallback(trial, f'valid_0_{params["metric"]}', valid_name="valid_0"))

            try:
                model = lgb.train(
                    params,
                    train_data,
                    num_boost_round=500,
                    valid_sets=[val_data],
                    valid_names=["valid_0"],
                    callbacks=callbacks,
                )
            except optuna.TrialPruned:
                raise  # Re-raise to let Optuna handle it
            except Exception as e:
                print(f"    Fold {fold_idx+1} failed: {e}")
                return float("inf") if self.model_type == "regressor" else 10.0

            # Evaluate
            pred = model.predict(X_val_fold)

            if self.model_type == "regressor":
                # REF: AUDIT-FIX - Changed from > 1.0 to > 0.1 to not ignore low-savings pools
                mask = y_val_fold.abs() > 0.1
                if mask.sum() > 0:
                    score = mean_absolute_percentage_error(y_val_fold[mask], pred[mask])
                else:
                    score = float("inf")
            else:
                # Binary log loss (for calibrated probabilities)
                score = log_loss(y_val_fold, pred)

            cv_scores.append(score)

            # Report intermediate value for pruning
            if self.enable_pruning:
                trial.report(np.mean(cv_scores), fold_idx)

                # Check if should prune
                if trial.should_prune():
                    raise optuna.TrialPruned()

        return np.mean(cv_scores)

    def optimize(self, n_trials: int = 100, timeout: int = 3600, study_name: str = None) -> optuna.Study:
        """
        Run optimization with optional persistence.

        Args:
            n_trials: Number of trials
            timeout: Time limit in seconds
            study_name: Name for study

        Returns:
            Completed Optuna study
        """
        if study_name is None:
            study_name = f"{self.model_type}_optimization"

        print(f"\n{'='*70}")
        print(f"OPTUNA OPTIMIZATION: {self.model_type.upper()}")
        print(f"{'='*70}")
        print(f"  CV Strategy: TimeSeriesSplit ({self.n_cv_splits} folds)")
        print(f"  Pruning: {'Enabled' if self.enable_pruning else 'Disabled'}")
        print(f"  Trials: {n_trials}")
        print(f"  Train samples: {len(self.X):,}")

        # REF: OPTIMIZATION - Added SQLite persistence for trial recovery
        study = optuna.create_study(
            study_name=study_name,
            direction="minimize",
            sampler=TPESampler(seed=42),
            pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10),
            storage="sqlite:///optuna_hpo.db",
            load_if_exists=True,
        )

        # Optimize
        start_time = time.time()

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        study.optimize(self.objective, n_trials=n_trials, timeout=timeout, show_progress_bar=True)

        elapsed = time.time() - start_time

        # Results
        print(f"\n{'='*70}")
        print("OPTIMIZATION COMPLETE")
        print(f"{'='*70}")
        print(f"  Time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"  Trials completed: {len(study.trials)}")
        print(f"  Pruned trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])}")
        print(f"  Best value: {study.best_value:.6f}")
        print("\n  Best parameters:")
        for key, value in study.best_params.items():
            if isinstance(value, float):
                print(f"    {key}: {value:.6f}")
            else:
                print(f"    {key}: {value}")

        return study


def main():
    parser = argparse.ArgumentParser(description="Unified Optuna hyperparameter tuning")
    parser.add_argument("--dry-run", action="store_true", help="Quick test: 1 trial, no CV")
    parser.add_argument("--regressor-only", action="store_true", help="Tune regressor only")
    parser.add_argument("--classifier-only", action="store_true", help="Tune classifier only")
    parser.add_argument(
        "--no-sampling",
        action="store_true",
        help="Use full data (ignore sample_fraction)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("UNIFIED OPTUNA HYPERPARAMETER TUNING")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Load config
    # Load config (searching from project root for robustness)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, "config/config.yaml")
    config = load_config(config_path)

    # Override for dry run
    if args.dry_run:
        config["optuna"]["n_trials"] = 1
        config["optuna"]["n_cv_splits"] = 1
        config["optuna"]["sample_fraction"] = 0.05
        print("\n DRY RUN MODE: 1 trial, 1 CV split, 5% data")

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("models/hpo_results")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print("\n Loading data...")
    df = load_all_data(config)
    events = load_stress_events(config)

    print(f"  Total rows: {len(df):,}")

    # Feature engineering
    print("\n Feature engineering...")
    df = engineer_all_features(df, events, config)

    # Prepare targets (MUST BE DONE BEFORE SAMPLING to ensure correct temporal shift)
    horizon = config["features"]["horizons"][0]
    print(f"\n Preparing targets (horizon={horizon})...")
    df = prepare_targets(df, horizon)

    # Systematic sampling for HPO
    if not args.no_sampling:
        sample_fraction = config["optuna"]["sample_fraction"]
        df = systematic_sample(df, sample_fraction)

    # Note: For HPO, we take the entire remaining dataset and let TimeSeriesSplit
    # handle internal validation folds.
    feature_cols = get_feature_columns()
    X = df[feature_cols]

    print(f"\n Final dataset for HPO: {len(df):,} rows, {len(feature_cols)} features")

    results = {}

    # Tune regressor
    if not args.classifier_only:
        optimizer = OptunaOptimizer(
            X=X,
            y=df["future_savings"],
            model_type="regressor",
            n_cv_splits=config["optuna"]["n_cv_splits"],
            enable_pruning=config["optuna"]["enable_pruning"],
            n_jobs=config["model"]["n_jobs"],
        )

        study_reg = optimizer.optimize(
            n_trials=config["optuna"]["n_trials"],
            timeout=config["optuna"]["timeout_seconds"],
            study_name="regressor_optimization",
        )

        results["regressor"] = {
            "best_params": study_reg.best_params,
            "best_value": study_reg.best_value,
            "n_trials": len(study_reg.trials),
            "n_pruned": len([t for t in study_reg.trials if t.state == optuna.trial.TrialState.PRUNED]),
        }

    # Tune classifier
    if not args.regressor_only:
        optimizer = OptunaOptimizer(
            X=X,
            y=df["is_unstable"],
            model_type="classifier",
            n_cv_splits=config["optuna"]["n_cv_splits"],
            enable_pruning=config["optuna"]["enable_pruning"],
            n_jobs=config["model"]["n_jobs"],
        )

        study_clf = optimizer.optimize(
            n_trials=config["optuna"]["n_trials"],
            timeout=config["optuna"]["timeout_seconds"],
            study_name="classifier_optimization",
        )

        results["classifier"] = {
            "best_params": study_clf.best_params,
            "best_value": study_clf.best_value,
            "n_trials": len(study_clf.trials),
            "n_pruned": len([t for t in study_clf.trials if t.state == optuna.trial.TrialState.PRUNED]),
        }

    # Save results
    results_path = output_dir / f"optuna_results_{timestamp}.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*70}")
    print("TUNING COMPLETE")
    print(f"{'='*70}")
    print(f"\n Results saved to: {results_path}")

    if "regressor" in results:
        print("\n Regressor:")
        print(f"  Best MAPE: {results['regressor']['best_value']:.6f}")
        print(f"  Trials: {results['regressor']['n_trials']} ({results['regressor']['n_pruned']} pruned)")

    if "classifier" in results:
        print("\n Classifier:")
        print(f"  Best Log Loss: {results['classifier']['best_value']:.4f}")
        print(f"  Trials: {results['classifier']['n_trials']} ({results['classifier']['n_pruned']} pruned)")

    print("\n Next steps:")
    print(f"  1. Review results: cat {results_path}")
    print("  2. Copy best params to src/model.py")
    print("  3. Train on full data: python scripts/train.py")


if __name__ == "__main__":
    main()
