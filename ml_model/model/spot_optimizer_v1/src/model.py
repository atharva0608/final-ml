"""
Hybrid LightGBM model: Regressor + Classifier
Designed to forecast savings and classify stability simultaneously.
"""
import json
from pathlib import Path
from typing import Dict, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    f1_score,
    mean_absolute_percentage_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from src.data import prepare_targets


class HybridSpotModel:
    """
    Hybrid model combining:
    1. Regressor: Predicts future savings%
    2. Classifier: Predicts instability risk (probability of deviation from baseline)

    Note: Classifier outputs 'risk_score' where higher values indicate higher risk.
    """

    def __init__(self, horizon: int = 6, device: str = "cpu", n_jobs: int = 8):
        """
        Args:
            horizon: Forecast horizon in 10-min intervals (6=1h, 36=6h, 144=24h)
            device: 'cpu' or 'gpu'
            n_jobs: Number of CPU cores
        """
        self.horizon = horizon
        self.device = device
        self.n_jobs = n_jobs

        # Models
        self.regressor = None
        self.classifier = None

        # Feature importance will be stored here
        self.regressor_importance = None
        self.classifier_importance = None

        # REF: AUDIT-FIX - Store optimal threshold for consistent usage
        self.optimal_threshold = 0.5  # Default, can be updated via optimize_threshold()

    def prepare_targets(self, df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Wrapper for shared target preparation logic."""
        return prepare_targets(df, horizon)

    def train_regressor(
        self, X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series, params: Dict = None
    ) -> lgb.Booster:
        """Train LightGBM regressor for savings prediction."""

        if params is None:
            # Optuna-optimized parameters (MAPE=0.27%, Trial #92)
            params = {
                "objective": "regression",
                "metric": "mape",
                "boosting_type": "gbdt",
                # Tree structure (Optuna-optimized)
                "num_leaves": 78,
                "max_depth": 7,
                "min_child_samples": 25,
                "min_child_weight": 0.000614,
                # Regularization (Optuna-optimized Jan 22 2026)
                "lambda_l2": 2.1811543831298962e-07,
                "lambda_l1": 0.0008726032755201592,
                # Sampling (Optuna-optimized)
                "learning_rate": 0.09696897462943847,
                "feature_fraction": 0.742566,
                "bagging_fraction": 0.887717,
                "bagging_freq": 6,
                # System
                "verbose": -1,
                "device": self.device,
                "n_jobs": self.n_jobs,
                "seed": 42,
            }

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        print(f"  Training Regressor (horizon={self.horizon})...")
        model = lgb.train(
            params,
            train_data,
            num_boost_round=1000,
            valid_sets=[train_data, val_data],
            valid_names=["train", "val"],
            callbacks=[lgb.early_stopping(100, verbose=True)],
        )

        # Store feature importance
        self.regressor_importance = pd.DataFrame(
            {"feature": X_train.columns, "importance": model.feature_importance(importance_type="gain")}
        ).sort_values("importance", ascending=False)

        print("  Regressor trained")
        print(f"  Top 5 features: {self.regressor_importance.head(5)['feature'].tolist()}")

        return model

    def train_classifier(
        self, X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series, params: Dict = None
    ) -> lgb.Booster:
        """
        Train LightGBM classifier for instability risk prediction.

        Target: is_unstable (1 = Risk, 0 = Safe)
        Output: Calibrated probability (0.0 to 1.0) representing risk score.
        """

        if params is None:
            # Default parameters for Risk Score prediction
            # Uses binary_logloss for calibrated probabilities
            # Note: scale_pos_weight removed to ensure true probability calibration
            params = {
                "objective": "binary",
                "metric": "binary_logloss",  # Optimizes for calibrated probabilities
                "boosting_type": "gbdt",
                # Tree structure (Optuna-optimized Jan 22 2026)
                # Note: scale_pos_weight is injected dynamically by train_wrapper.py
                "num_leaves": 45,
                "max_depth": 6,
                "min_child_samples": 315,
                "min_child_weight": 0.001,
                # Regularization
                "lambda_l2": 0.1,
                "lambda_l1": 0.0,
                # Sampling
                "learning_rate": 0.03482301132025348,
                "feature_fraction": 0.8,
                "bagging_fraction": 0.8,
                "bagging_freq": 5,
                # System
                "verbose": -1,
                "device": self.device,
                "n_jobs": self.n_jobs,
                "seed": 42,
            }

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        print(f"  Training Classifier (horizon={self.horizon})...")
        model = lgb.train(
            params,
            train_data,
            num_boost_round=1000,
            valid_sets=[train_data, val_data],
            valid_names=["train", "val"],
            callbacks=[lgb.early_stopping(100, verbose=True)],
        )

        # Store feature importance
        self.classifier_importance = pd.DataFrame(
            {"feature": X_train.columns, "importance": model.feature_importance(importance_type="gain")}
        ).sort_values("importance", ascending=False)

        print("  Classifier trained")
        print(f"  Top 5 features: {self.classifier_importance.head(5)['feature'].tolist()}")

        return model

    def fit(
        self,
        X_train: pd.DataFrame,
        X_val: pd.DataFrame,
        y_reg_train: pd.Series,
        y_reg_val: pd.Series,
        y_clf_train: pd.Series,
        y_clf_val: pd.Series,
        regressor_params: Dict = None,
        classifier_params: Dict = None,
    ):
        """
        Train both models using pre-extracted targets (Memory Optimized).

        Args:
            X_train, X_val: Feature DataFrames
            y_reg_train, y_reg_val: Targets for Regressor (future_savings)
            y_clf_train, y_clf_val: Targets for Classifier (is_unstable)
        """
        print(f"\n Training Hybrid Model (Horizon: {self.horizon} intervals)...")

        # Train regressor
        self.regressor = self.train_regressor(X_train, y_reg_train, X_val, y_reg_val, regressor_params)

        # Train classifier
        self.classifier = self.train_classifier(X_train, y_clf_train, X_val, y_clf_val, classifier_params)

        print(f" Hybrid model trained for horizon {self.horizon}")

    def predict(self, X: pd.DataFrame, threshold: float = 0.5) -> Dict:
        """
        Predict both savings and instability risk.

        Args:
            X: Feature DataFrame
            threshold: Risk threshold for labeling (default 0.5)
                       > threshold implies High Risk ("unsafe")
                       <= threshold implies Low Risk ("safe")

        Returns:
            Dict with:
            - 'savings': Predicted future savings (continuous)
            - 'risk_score': Probability of instability (0.0 = Safe, 1.0 = High Risk)
            - 'risk_label': Binary label ("safe" or "unsafe") based on threshold
        """
        pred_savings = self.regressor.predict(X)
        pred_risk = self.classifier.predict(X)  # Probability of is_unstable=1

        # Vectorized mapping of risk probability to labels
        # High risk score (> threshold) = "unsafe"
        # Low risk score (<= threshold) = "safe"
        labels = np.where(pred_risk > threshold, "unsafe", "safe")

        return {
            "savings": pred_savings,
            "risk_score": pred_risk,  # 0.0-1.0, higher = more risk
            "risk_label": labels,  # "safe" or "unsafe"
        }

    def optimize_threshold(
        self,
        X_val: pd.DataFrame,
        val_df: pd.DataFrame = None,
        metric: str = "f1",
        thresholds: np.ndarray = None,
        y_val: pd.Series = None,
    ) -> Tuple[float, Dict]:
        """
        Find optimal classification threshold to maximize a given metric.

        Args:
            X_val: Validation features
            val_df: Validation DataFrame (optional if y_val provided)
            metric: Metric to optimize ('f1', 'recall', 'precision')
            thresholds: Array of thresholds to test
            y_val: Validation targets (is_unstable). If provided, val_df ignored for target prep.
        """
        # Prepare validation targets
        if y_val is None:
            if val_df is None:
                raise ValueError("Must provide either val_df or y_val")
            if "future_savings" not in val_df.columns or "is_unstable" not in val_df.columns:
                val_df = self.prepare_targets(val_df, self.horizon)
            y_val = val_df["is_unstable"]
            # Align indices if we had to prep targets
            if len(X_val) != len(y_val):
                X_val = X_val.loc[y_val.index]

        # Get predicted probabilities
        pred_probs = self.classifier.predict(X_val)

        # Default threshold range
        if thresholds is None:
            thresholds = np.arange(0.1, 0.95, 0.05)

        best_threshold = 0.5
        best_score = 0.0
        best_metrics = {"f1": 0.0, "precision": 0.0, "recall": 0.0}

        print(f"\nOptimizing classification threshold for '{metric}'...")
        print(f"   Testing {len(thresholds)} thresholds: [{thresholds[0]:.2f}, {thresholds[-1]:.2f}]")

        results = []
        for thresh in thresholds:
            # Apply threshold
            pred_labels = (pred_probs > thresh).astype(int)

            # Calculate metrics
            f1 = f1_score(y_val, pred_labels, zero_division=0)
            precision = precision_score(y_val, pred_labels, zero_division=0)
            recall = recall_score(y_val, pred_labels, zero_division=0)

            # Select metric to optimize
            if metric == "f1":
                score = f1
            elif metric == "recall":
                score = recall
            elif metric == "precision":
                score = precision
            else:
                raise ValueError(f"Unknown metric: {metric}. Use 'f1', 'recall', or 'precision'.")

            results.append({"threshold": thresh, "f1": f1, "precision": precision, "recall": recall, "score": score})

            # Track best
            if score > best_score:
                best_score = score
                best_threshold = thresh
                best_metrics = {"f1": f1, "precision": precision, "recall": recall}

        print(f"\n   Optimal threshold: {best_threshold:.2f}")
        print("   Metrics at optimal threshold:")
        print(f"     F1:        {best_metrics['f1']:.4f}")
        print(f"     Precision: {best_metrics['precision']:.4f}")
        print(f"     Recall:    {best_metrics['recall']:.4f}")

        # Store results for inspection
        self.threshold_optimization_results = pd.DataFrame(results)

        # REF: AUDIT-FIX - Store optimal threshold for use in evaluate() and predict()
        self.optimal_threshold = best_threshold

        return best_threshold, best_metrics

    def evaluate(self, X_test: pd.DataFrame, test_df: pd.DataFrame) -> Dict:
        """Evaluate both models on test set."""
        if "future_savings" not in test_df.columns or "is_unstable" not in test_df.columns:
            test_df = self.prepare_targets(test_df, self.horizon)
        X_test = X_test.loc[test_df.index]

        # Regressor metrics
        pred_savings = self.regressor.predict(X_test)

        # REF: AUDIT-FIX - Changed from > 1.0 to > 0.1 to not ignore low-savings pools
        mape_mask = test_df["future_savings"].abs() > 0.1  # Only savings > 0.1%
        if mape_mask.sum() > 0:
            mape = mean_absolute_percentage_error(test_df.loc[mape_mask, "future_savings"], pred_savings[mape_mask])
        else:
            mape = 0.0

        rmse = np.sqrt(mean_squared_error(test_df["future_savings"], pred_savings))
        r2 = r2_score(test_df["future_savings"], pred_savings)

        # Classifier metrics (Risk Score)
        pred_risk_prob = self.classifier.predict(X_test)
        # REF: AUDIT-FIX - Use self.optimal_threshold instead of hardcoded 0.5
        pred_risk = (pred_risk_prob > self.optimal_threshold).astype(int)
        f1 = f1_score(test_df["is_unstable"], pred_risk)
        precision = precision_score(test_df["is_unstable"], pred_risk, zero_division=0)
        recall = recall_score(test_df["is_unstable"], pred_risk, zero_division=0)
        auc = roc_auc_score(test_df["is_unstable"], pred_risk_prob)

        metrics = {
            "regressor": {"mape": mape, "rmse": rmse, "r2": r2},
            "classifier": {"f1": f1, "precision": precision, "recall": recall, "auc": auc},
        }

        print(f"\n Evaluation (Horizon {self.horizon}):")
        print(f"  Regressor - MAPE: {mape:.4f}, RMSE: {rmse:.4f}, R²: {r2:.4f}")
        print(f"  Classifier (Risk) - F1: {f1:.4f}, AUC: {auc:.4f}, Precision: {precision:.4f}, Recall: {recall:.4f}")

        return metrics

    def save(self, output_dir: str):
        """Save models and feature importance."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save models
        self.regressor.save_model(str(output_path / f"regressor_{self.horizon}.txt"))
        self.classifier.save_model(str(output_path / f"classifier_{self.horizon}.txt"))

        # Save feature importance
        self.regressor_importance.to_csv(output_path / f"feature_importance_reg_{self.horizon}.csv", index=False)
        self.classifier_importance.to_csv(output_path / f"feature_importance_clf_{self.horizon}.csv", index=False)

        # REF: AUDIT-FIX - Save metadata (threshold)
        metadata = {"optimal_threshold": self.optimal_threshold}
        with open(output_path / f"metadata_{self.horizon}.json", "w") as f:
            json.dump(metadata, f)

        print(f"  Models and metadata saved to {output_path}")

        # Attempt ONNX Export (Zero-Trust Sandbox)
        try:
            self.export_onnx(str(output_path))
        except Exception as e:
            # Structured Logging for Debugging
            error_details = {"error": type(e).__name__, "message": str(e)}
            print(f"  [WARNING] ONNX Export Failed (Job Continuing): {error_details}")

    def export_onnx(self, output_dir: str):
        """
        Export models to ONNX format (Sandboxed).

        Zero-Trust Protocol:
        1. Lazy Imports (Blast Radius Containment)
        2. Dynamic Shape Validation (Prevent Empty Models)
        3. Native API (LGBM 4.0 Compatibility)
        """
        # 1. Sandboxed Imports
        try:
            import onnx
            import onnxmltools  # noqa: F401
            from onnxconverter_common.data_types import FloatTensorType
            from onnxmltools import convert_lightgbm
        except ImportError as e:
            raise ImportError(f"ONNX import failed: {e}") from e

        print(f"  Exporting ONNX models to {output_dir}...")
        output_path = Path(output_dir)

        # 2. Export Regressor
        # Dynamic shape definition to avoid attributes errors
        n_features_reg = self.regressor.num_feature()
        if n_features_reg <= 0:
            raise ValueError("Regressor has 0 features. Cannot export.")

        initial_types_reg = [("input", FloatTensorType([None, n_features_reg]))]

        # Native API conversion with Safe Opset
        onnx_reg = convert_lightgbm(self.regressor, initial_types=initial_types_reg, target_opset=14)
        onnx.save(onnx_reg, str(output_path / f"regressor_{self.horizon}.onnx"))

        # 3. Export Classifier
        n_features_clf = self.classifier.num_feature()
        if n_features_clf > 0:
            initial_types_clf = [("input", FloatTensorType([None, n_features_clf]))]

            onnx_clf = convert_lightgbm(self.classifier, initial_types=initial_types_clf, target_opset=14)
            onnx.save(onnx_clf, str(output_path / f"classifier_{self.horizon}.onnx"))

        print("  [SUCCESS] ONNX Export Completed.")

    @classmethod
    def load(cls, model_dir: str, horizon: int):
        """Load trained models."""
        model_path = Path(model_dir)

        instance = cls(horizon=horizon)
        instance.regressor = lgb.Booster(model_file=str(model_path / f"regressor_{horizon}.txt"))
        instance.classifier = lgb.Booster(model_file=str(model_path / f"classifier_{horizon}.txt"))

        # REF: AUDIT-FIX - Load metadata (threshold)
        metadata_path = model_path / f"metadata_{horizon}.json"
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
            instance.optimal_threshold = metadata.get("optimal_threshold", 0.5)
            print(f"  Previously optimized threshold loaded: {instance.optimal_threshold}")

        return instance


if __name__ == "__main__":
    print(" Hybrid model module loaded!")
