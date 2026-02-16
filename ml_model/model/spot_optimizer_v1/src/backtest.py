"""
Walk-Forward Backtesting Module for V1 Spot Optimizer.

Implements time-series cross-validation with rolling windows to validate
model performance across multiple time periods.

Note: Classifier predicts is_unstable (1 = Risk, 0 = Safe) for Risk Score output.
What it is: A Library module.
Content: Defines the WalkForwardBacktest class.
Purpose: It contains the logic for splitting time-series data, training loops, and calculating metrics.
It is designed to be reusable and doesn't know about your specific configuration or file paths.
Usage: Do not run this file directly.
"""
import gc
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from src.data import prepare_targets

# Logging
from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestWindow:
    """Represents a single backtesting window."""

    window_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_size: int
    test_size: int
    metrics: Dict = None


class WalkForwardBacktest:
    """
    Walk-Forward Backtesting for time series models.

    Strategy:
        Train on window 1, test on window 2
        Expand training to windows 1+2, test on window 3
        Continue until all data is tested

    This simulates real-world deployment where you retrain periodically
    on accumulating historical data.
    """

    def __init__(self, n_splits: int = 5, test_size_months: int = 2, min_train_months: int = 6, gap_days: int = 0):
        """
        Initialize walk-forward backtester.

        Args:
            n_splits: Number of test windows
            test_size_months: Size of each test window in months
            min_train_months: Minimum training period in months
            gap_days: Gap between train and test to prevent leakage
        """
        self.n_splits = n_splits
        self.test_size_months = test_size_months
        self.min_train_months = min_train_months
        self.gap_days = gap_days
        self.windows: List[BacktestWindow] = []
        self.results: List[Dict] = []

    def create_windows(self, df: pd.DataFrame) -> List[BacktestWindow]:
        """
        Create backtest windows from data.

        Args:
            df: DataFrame with 'timestamp' column

        Returns:
            List of BacktestWindow objects
        """
        df = df.sort_values("timestamp")

        min_date = df["timestamp"].min()
        max_date = df["timestamp"].max()

        total_months = (max_date.year - min_date.year) * 12 + (max_date.month - min_date.month)

        print("\n Creating Walk-Forward Windows")
        print(f" Date range: {min_date.date()} to {max_date.date()}")
        print(f" Total months: {total_months}")
        print(f" Test window size: {self.test_size_months} months")
        print(f" Min train size: {self.min_train_months} months")

        windows = []

        # Calculate window boundaries
        test_months_needed = self.n_splits * self.test_size_months
        available_test_months = total_months - self.min_train_months

        if test_months_needed > available_test_months:
            actual_splits = max(1, available_test_months // self.test_size_months)
            print(f" Reducing splits from {self.n_splits} to {actual_splits}")
            self.n_splits = actual_splits

        # Create windows
        for i in range(self.n_splits):
            # Training ends at min_train + i * test_size months from start
            train_months = self.min_train_months + i * self.test_size_months
            train_end = min_date + pd.DateOffset(months=train_months)

            # Gap
            test_start = train_end + pd.Timedelta(days=self.gap_days)

            # Test window
            test_end = test_start + pd.DateOffset(months=self.test_size_months)

            # Don't exceed data range
            if test_end > max_date:
                test_end = max_date

            # Get actual row counts
            train_mask = (df["timestamp"] >= min_date) & (df["timestamp"] < train_end)
            test_mask = (df["timestamp"] >= test_start) & (df["timestamp"] <= test_end)

            window = BacktestWindow(
                window_id=i + 1,
                train_start=min_date,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_size=train_mask.sum(),
                test_size=test_mask.sum(),
            )
            windows.append(window)

            print(f"\n  Window {i+1}:")
            print(f"    Train: {min_date.date()} → {train_end.date()} ({window.train_size:,} rows)")
            print(f"    Test:  {test_start.date()} → {test_end.date()} ({window.test_size:,} rows)")

        self.windows = windows
        return windows

    def run_backtest(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        horizon: int,
        n_jobs: int = 4,
        early_stopping_rounds: int = 100,
        regressor_params: Optional[Dict] = None,
        classifier_params: Optional[Dict] = None,
        threshold: float = 0.5,
    ) -> Dict:
        """
        Run walk-forward backtesting.

        Args:
            df: Full DataFrame with features
            feature_cols: List of feature column names
            horizon: Prediction horizon in intervals
            n_jobs: Number of parallel jobs
            early_stopping_rounds: Early stopping patience
            regressor_params: Optional HPO-tuned regressor params
            classifier_params: Optional HPO-tuned classifier params
            threshold: Classification threshold (default 0.5, used if optimization fails/skipped)

        Returns:
            Dict with aggregated metrics
        """
        # Lazy import to avoid circular dependencies
        from src.model import HybridSpotModel

        if not self.windows:
            self.create_windows(df)

        logger.info("=" * 60)
        logger.info(f"WALK-FORWARD BACKTESTING (Horizon: {horizon})")
        logger.info("=" * 60)

        # Prepare targets on FULL Dataframe if not present
        if "future_savings" not in df.columns or "is_unstable" not in df.columns:
            print("  Pre-calculating targets on full dataset...")
            df = prepare_targets(df, horizon)

        all_metrics = []

        for window in self.windows:
            logger.info(f"Window {window.window_id}/{len(self.windows)}")

            # Split data for this window
            train_mask = (df["timestamp"] >= window.train_start) & (df["timestamp"] < window.train_end)
            test_mask = (df["timestamp"] >= window.test_start) & (df["timestamp"] <= window.test_end)

            # Extract window data
            window_train_df = df[train_mask].reset_index(drop=True)
            test_df = df[test_mask].reset_index(drop=True)

            # Further split window_train_df into sub-train (80%) and sub-val (20%)
            # This is crucial for optimizing the threshold without leaking test data
            # Use chronological split for the sub-split
            split_idx = int(len(window_train_df) * 0.8)
            train_df = window_train_df.iloc[:split_idx]
            val_df = window_train_df.iloc[split_idx:]

            # Get features
            X_train = train_df[feature_cols]
            X_val = val_df[feature_cols]
            X_test = test_df[feature_cols]

            # Get targets
            y_reg_train = train_df["future_savings"]
            y_reg_val = val_df["future_savings"]
            y_clf_train = train_df["is_unstable"]
            y_clf_val = val_df["is_unstable"]

            # Initialize Model
            model = HybridSpotModel(horizon=horizon, n_jobs=n_jobs)

            # Train (Fit)
            # Note: early_stopping_rounds is handled inside fit -> train_regressor/train_classifier
            model.fit(
                X_train,
                X_val,
                y_reg_train,
                y_reg_val,
                y_clf_train,
                y_clf_val,
                regressor_params=regressor_params,
                classifier_params=classifier_params,
            )

            # Optimize Threshold on Validation Set
            # This ensures the threshold is tuned for this specific time window
            opt_threshold, _ = model.optimize_threshold(X_val, y_val=y_clf_val, metric="f1")

            # Evaluate on Test Set using Optimized Threshold
            # model.evaluate uses model.optimal_threshold internally
            metrics = model.evaluate(X_test, test_df)

            # Add window metadata
            metrics.update(
                {
                    "window_id": window.window_id,
                    "train_start": str(window.train_start.date()),
                    "train_end": str(window.train_end.date()),
                    "test_start": str(window.test_start.date()),
                    "test_end": str(window.test_end.date()),
                    "train_size": len(window_train_df),  # Original full train size
                    "test_size": len(test_df),
                    "optimal_threshold": opt_threshold,
                }
            )

            window.metrics = metrics
            all_metrics.append(metrics)

            print(f"  Reg MAPE: {metrics['regressor']['mape']:.4f}")
            print(f"  Clf F1:   {metrics['classifier']['f1']:.4f}")
            print(f"  Threshold: {opt_threshold:.4f}")

            # Cleanup
            del train_df, val_df, test_df, X_train, X_val, X_test, model
            gc.collect()

        self.results = all_metrics

        # Aggregate metrics
        aggregated = self._aggregate_metrics(all_metrics)

        return aggregated

    def _aggregate_metrics(self, all_metrics: List[Dict]) -> Dict:
        """Aggregate metrics across all windows."""
        if not all_metrics:
            return {}

        reg_mapes = [m["regressor"]["mape"] for m in all_metrics]
        reg_rmses = [m["regressor"]["rmse"] for m in all_metrics]
        reg_r2s = [m["regressor"]["r2"] for m in all_metrics]
        clf_f1s = [m["classifier"]["f1"] for m in all_metrics]
        clf_precs = [m["classifier"]["precision"] for m in all_metrics]
        clf_recalls = [m["classifier"]["recall"] for m in all_metrics]

        aggregated = {
            "n_windows": len(all_metrics),
            "regressor": {
                "mape_mean": float(np.mean(reg_mapes)),
                "mape_std": float(np.std(reg_mapes)),
                "rmse_mean": float(np.mean(reg_rmses)),
                "r2_mean": float(np.mean(reg_r2s)),
            },
            "classifier": {
                "f1_mean": float(np.mean(clf_f1s)),
                "f1_std": float(np.std(clf_f1s)),
                "precision_mean": float(np.mean(clf_precs)),
                "recall_mean": float(np.mean(clf_recalls)),
            },
            "per_window": all_metrics,
        }

        print(f"\n{'='*60}")
        print(f"AGGREGATED RESULTS ({len(all_metrics)} windows)")
        print(f"{'='*60}")
        print(
            f"  Regressor MAPE: {aggregated['regressor']['mape_mean']:.4f} ± {aggregated['regressor']['mape_std']:.4f}"
        )
        print(f"  Regressor R²:   {aggregated['regressor']['r2_mean']:.4f}")
        print(f"  Classifier F1:  {aggregated['classifier']['f1_mean']:.4f} ± {aggregated['classifier']['f1_std']:.4f}")

        return aggregated

    def save_results(self, output_path: str):
        """Save backtest results to JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(
                {
                    "n_splits": self.n_splits,
                    "test_size_months": self.test_size_months,
                    "min_train_months": self.min_train_months,
                    "results": self.results,
                },
                f,
                indent=2,
            )

        print(f"\n Results saved to {output_path}")


if __name__ == "__main__":
    print("Walk-Forward Backtesting module loaded!")
