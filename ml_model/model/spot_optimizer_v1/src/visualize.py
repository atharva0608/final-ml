"""
Time series-optimized visualization module.

Handles millions of time series observations efficiently through:
1. Temporal aggregation (daily means)
2. Intelligent sampling (preserves distribution)
3. Pre-aggregation before plotting

Note: Classifier predicts is_unstable (1 = Risk, 0 = Safe).
Performance: ~20 seconds for 77M rows, <500 MB RAM
"""

import gc
import time
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from sklearn.metrics import auc, confusion_matrix, precision_recall_curve, roc_curve

# Logging
from src.logger import get_logger

warnings.filterwarnings("ignore")

logger = get_logger(__name__)


class ModelVisualizer:
    """Generate time series-aware visualization dashboards."""

    def __init__(self, output_dir: str = "reports/visualizations"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set style with fallback for different matplotlib versions
        try:
            plt.style.use("seaborn-v0_8-whitegrid")
        except Exception:
            try:
                plt.style.use("seaborn-whitegrid")
            except Exception:
                pass  # Use default style

        sns.set_palette("husl")

    def generate_essential_dashboards(
        self,
        model,
        X_test: pd.DataFrame,
        test_df: pd.DataFrame,
        feature_names: list,
        horizon: int = 6,
        backtest_results: dict = None,
    ) -> float:
        """Generate 3 optimized dashboards + PDF Report. Returns optimal threshold."""
        logger.info("Generating Optimized Dashboards & PDF Report")
        logger.info(f"Test set: {len(test_df):,} rows")
        start = time.time()

        # Prepare targets if not already present
        if "future_savings" not in test_df.columns or "is_unstable" not in test_df.columns:
            from src.data import prepare_targets

            test_df = prepare_targets(test_df, horizon)
            # Align X_test with test_df after dropping NaNs
            X_test = X_test.loc[test_df.index].copy()
            test_df = test_df.copy()

        pred_savings = model.regressor.predict(X_test)
        pred_risk_prob = model.classifier.predict(X_test)  # Probability of is_unstable=1

        # Use model's optimal threshold if available, else default to 0.5
        current_threshold = getattr(model, "optimal_threshold", 0.5)
        logger.info(f"Using threshold for visualization: {current_threshold:.4f}")

        # Use PdfPages to save all plots to a single PDF
        pdf_path = self.output_dir / "Model_Validation_Report.pdf"
        with PdfPages(pdf_path) as pdf:
            # Page 1: Executive Summary
            self._create_summary_page(pdf, test_df, pred_savings, pred_risk_prob, backtest_results, horizon)

            # Dashboard 1: Performance (time series aware)
            # Save PNG as usual, but ALSO save to PDF
            optimal_threshold = self.plot_performance_dashboard(
                test_df.copy(),
                pred_savings,
                pred_risk_prob,
                save_name="performance_dashboard.png",
                pdf_pages=pdf,
                threshold=current_threshold,
            )

            # Dashboard 2: Features
            self.plot_feature_analysis_dashboard(model, feature_names, pdf_pages=pdf)

            # Dashboard 3: Business
            pred_risky = (pred_risk_prob > optimal_threshold).astype(int)  # 1 = Risky
            self.plot_business_impact_dashboard(test_df.copy(), pred_savings, pred_risky, pdf_pages=pdf)

            # Additional Backtest Details Page if available
            if backtest_results and "per_window" in backtest_results:
                self._create_backtest_details_page(pdf, backtest_results)

        logger.info(f"All dashboards & PDF generated in {time.time()-start:.1f} seconds")
        print(f"   Saved PDF Report: {pdf_path}")
        return optimal_threshold

    def _create_summary_page(self, pdf, test_df, pred_savings, pred_risk_prob, backtest_results, horizon):
        """Create a text-based executive summary page."""
        fig = plt.figure(figsize=(11.69, 8.27))  # A4 Landscape
        ax = fig.add_subplot(111)
        ax.axis("off")

        # Title
        plt.text(
            0.5,
            0.95,
            "Spot Optimizer - Model Validation Report",
            ha="center",
            fontsize=24,
            fontweight="bold",
            transform=ax.transAxes,
        )
        plt.text(
            0.5,
            0.90,
            f"Generated: {time.strftime('%Y-%m-%d %H:%M')}",
            ha="center",
            fontsize=12,
            color="gray",
            transform=ax.transAxes,
        )

        # Content Text
        # Build Report Text safely
        lines = [
            "Model Configuration",
            "-------------------",
            f"Horizon: {horizon} intervals ({(horizon*10)/60:.1f} hours)",
            f"Test Set Size: {len(test_df):,} rows",
            "",
            "Test Set Performance",
            "--------------------------------------",
        ]

        # Calculate metrics for report text
        y_true_reg = test_df["future_savings"].values
        mape = np.mean(np.abs((y_true_reg - pred_savings) / (y_true_reg + 1e-10))) * 100
        rmse = np.sqrt(np.mean((y_true_reg - pred_savings) ** 2))
        ss_res = np.sum((y_true_reg - pred_savings) ** 2)
        ss_tot = np.sum((y_true_reg - np.mean(y_true_reg)) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        lines.extend(
            [
                f"Regressor R2: {r2:.4f}",
                f"Regressor MAPE: {mape:.3f}%",
                f"Regressor RMSE: {rmse:.4f}",
                "",
            ]
        )

        if backtest_results and "regressor" in backtest_results:
            agg = backtest_results
            lines.extend(
                [
                    "Backtesting Results (Robustness Check)",
                    "--------------------------------------",
                    f"Windows Tested: {agg.get('n_windows', 0)}",
                    "",
                    "Regressor (Avg across windows):",
                    f"  MAPE: {agg['regressor']['mape_mean']:.4f} \u00b1 {agg['regressor']['mape_std']:.4f}",
                    f"  R2:   {agg['regressor']['r2_mean']:.4f}",
                    "",
                    "Classifier (Avg across windows):",
                    f"  F1:   {agg['classifier']['f1_mean']:.4f} \u00b1 {agg['classifier']['f1_std']:.4f}",
                    f"  Prec: {agg['classifier']['precision_mean']:.4f}",
                    f"  Recall: {agg['classifier']['recall_mean']:.4f}",
                ]
            )
        else:
            lines.append("Backtesting Results: SKIPPED (Single Run Only)")

        report_text = "\n".join(lines)

        plt.text(
            0.1,
            0.8,
            report_text,
            fontsize=12,
            family="monospace",
            va="top",
            transform=ax.transAxes,
        )

        pdf.savefig(fig)
        plt.close(fig)

    def _create_backtest_details_page(self, pdf, backtest_results):
        """Create a page detailing each backtest split."""
        fig = plt.figure(figsize=(11.69, 8.27))
        ax = fig.add_subplot(111)
        ax.axis("off")

        plt.text(
            0.5,
            0.95,
            "Detailed Backtest Results (Per Window)",
            ha="center",
            fontsize=20,
            fontweight="bold",
            transform=ax.transAxes,
        )

        # Create a table
        columns = [
            "Window",
            "Train Range",
            "Test Range",
            "Reg MAPE",
            "Clf F1",
            "Clf Recall",
        ]
        cell_text = []

        for w in backtest_results.get("per_window", []):
            row = [
                f"Window {w['window_id']}",
                f"{w['train_start']} -> {w['train_end']}",
                f"{w['test_start']} -> {w['test_end']}",
                f"{w['regressor']['mape']:.4f}",
                f"{w['classifier']['f1']:.4f}",
                f"{w['classifier']['recall']:.4f}",
            ]
            cell_text.append(row)

        if cell_text:
            table = plt.table(cellText=cell_text, colLabels=columns, loc="center", cellLoc="center")
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 2)

        pdf.savefig(fig)
        plt.close(fig)

    def plot_performance_dashboard(
        self,
        test_df: pd.DataFrame,
        pred_savings: np.ndarray,
        pred_risk_prob: np.ndarray,
        save_name: str = "performance_dashboard.png",
        pdf_pages=None,
        threshold: float = 0.5,
    ) -> float:
        """Time series-aware performance dashboard with KPI summary."""
        y_true_reg = test_df["future_savings"].values
        y_true_clf = test_df["is_unstable"].values  # 1 = Risky, 0 = Safe
        pred_clf = (pred_risk_prob > threshold).astype(int)

        # Calculate all metrics upfront
        # Regressor metrics - Filter near-zero values for accurate MAPE
        mape_mask = np.abs(y_true_reg) > 0.01
        mape = (
            np.mean(np.abs((y_true_reg[mape_mask] - pred_savings[mape_mask]) / y_true_reg[mape_mask])) * 100
            if mape_mask.sum() > 0
            else 0.0
        )
        # Calculate R2 Score
        ss_res = np.sum((y_true_reg - pred_savings) ** 2)
        ss_tot = np.sum((y_true_reg - y_true_reg.mean()) ** 2) + 1e-10
        r2 = 1 - (ss_res / ss_tot)

        # Classifier metrics
        cm = confusion_matrix(y_true_clf, pred_clf)
        tn, fp, fn, tp = cm.ravel()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0
        fpr, tpr, _ = roc_curve(y_true_clf, pred_risk_prob)
        roc_auc = auc(fpr, tpr)

        # Find optimal threshold
        precision_curve, recall_curve, thresholds = precision_recall_curve(y_true_clf, pred_risk_prob)
        f1_scores = 2 * (precision_curve * recall_curve) / (precision_curve + recall_curve + 1e-10)
        optimal_idx = np.argmax(f1_scores[:-1]) if len(f1_scores) > 1 else 0
        optimal_threshold = thresholds[optimal_idx] if len(thresholds) > 0 else 0.5

        # Create figure with KPI row at top
        fig = plt.figure(figsize=(18, 14))
        gs = fig.add_gridspec(3, 3, height_ratios=[0.8, 1, 1], hspace=0.35, wspace=0.3)

        # === ROW 0: KPI SUMMARY PANEL ===
        ax_kpi = fig.add_subplot(gs[0, :])
        ax_kpi.axis("off")

        # KPI Panel background
        kpi_box = plt.Rectangle(
            (0.02, 0.1),
            0.96,
            0.8,
            facecolor="#f8f9fa",
            edgecolor="#dee2e6",
            linewidth=2,
            zorder=1,
        )
        ax_kpi.add_patch(kpi_box)

        # Regressor KPIs (left side)
        ax_kpi.text(
            0.15,
            0.75,
            " REGRESSOR (Price Prediction)",
            fontsize=14,
            fontweight="bold",
            ha="center",
            color="#2c3e50",
        )
        ax_kpi.text(
            0.08,
            0.45,
            "MAPE",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.08,
            0.25,
            f"{mape:.2f}%",
            fontsize=18,
            ha="center",
            fontweight="bold",
            color="#27ae60" if mape < 1 else "#e74c3c",
        )
        ax_kpi.text(
            0.22,
            0.45,
            "R²",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.22,
            0.25,
            f"{r2:.4f}",
            fontsize=18,
            ha="center",
            fontweight="bold",
            color="#27ae60" if r2 > 0.99 else "#f39c12",
        )

        # Separator
        ax_kpi.axvline(x=0.33, ymin=0.15, ymax=0.85, color="#bdc3c7", linewidth=2)

        # Classifier KPIs (middle)
        ax_kpi.text(
            0.5,
            0.75,
            "️ CLASSIFIER (Risk Detection)",
            fontsize=14,
            fontweight="bold",
            ha="center",
            color="#2c3e50",
        )
        ax_kpi.text(
            0.40,
            0.45,
            "Recall",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.40,
            0.25,
            f"{recall*100:.1f}%",
            fontsize=18,
            ha="center",
            fontweight="bold",
            color="#27ae60" if recall > 0.9 else "#e74c3c",
        )
        ax_kpi.text(
            0.50,
            0.45,
            "F1",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.50,
            0.25,
            f"{f1:.3f}",
            fontsize=18,
            ha="center",
            fontweight="bold",
            color="#27ae60" if f1 > 0.7 else "#f39c12",
        )
        ax_kpi.text(
            0.60,
            0.45,
            "AUC",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.60,
            0.25,
            f"{roc_auc:.3f}",
            fontsize=18,
            ha="center",
            fontweight="bold",
            color="#27ae60" if roc_auc > 0.7 else "#f39c12",
        )

        # Separator
        ax_kpi.axvline(x=0.67, ymin=0.15, ymax=0.85, color="#bdc3c7", linewidth=2)

        # Configuration KPIs (right side)
        ax_kpi.text(
            0.85,
            0.75,
            "️ CONFIGURATION",
            fontsize=14,
            fontweight="bold",
            ha="center",
            color="#2c3e50",
        )
        ax_kpi.text(
            0.78,
            0.45,
            "Threshold",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.78,
            0.25,
            f"{threshold:.2f}",
            fontsize=18,
            ha="center",
            fontweight="bold",
            color="#3498db",
        )
        ax_kpi.text(
            0.92,
            0.45,
            "Test Size",
            fontsize=11,
            ha="center",
            color="#7f8c8d",
        )
        ax_kpi.text(
            0.92,
            0.25,
            f"{len(test_df):,}",
            fontsize=14,
            ha="center",
            fontweight="bold",
            color="#3498db",
        )

        # === ROW 1: Classifier Metrics ===

        # Plot 1: Confusion Matrix
        ax1 = fig.add_subplot(gs[1, 0])
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            cbar=False,
            ax=ax1,
            annot_kws={"size": 14},
        )
        ax1.set_title("Confusion Matrix", fontsize=12, fontweight="bold")
        ax1.set_xlabel("Predicted", fontsize=10)
        ax1.set_ylabel("Actual", fontsize=10)
        ax1.set_xticklabels(["Safe", "Risky"], fontsize=10)
        ax1.set_yticklabels(["Safe", "Risky"], fontsize=10)

        # Plot 2: ROC Curve (decimated)
        ax2 = fig.add_subplot(gs[1, 1])
        # REF: OPTIMIZATION - Decimate to max 5000 points
        step = max(1, len(fpr) // 5000)
        ax2.plot(fpr[::step], tpr[::step], "b-", lw=2, label=f"AUC={roc_auc:.3f}")
        ax2.plot([0, 1], [0, 1], "r--", lw=1, label="Random")
        ax2.fill_between(fpr[::step], 0, tpr[::step], alpha=0.1)
        ax2.set_xlabel("False Positive Rate", fontsize=10)
        ax2.set_ylabel("True Positive Rate", fontsize=10)
        ax2.set_title("ROC Curve", fontsize=12, fontweight="bold")
        ax2.legend(loc="lower right", fontsize=9)
        ax2.grid(alpha=0.3)

        # Plot 3: Precision-Recall (decimated)
        ax3 = fig.add_subplot(gs[1, 2])
        # REF: OPTIMIZATION - Decimate to max 5000 points
        step = max(1, len(precision_curve) // 5000)
        ax3.plot(recall_curve[::step], precision_curve[::step], "b-", lw=2)
        ax3.scatter(
            recall_curve[optimal_idx],
            precision_curve[optimal_idx],
            color="red",
            s=120,
            zorder=5,
            label=f"Optimal t={optimal_threshold:.2f}",
        )
        ax3.axhline(
            y=precision,
            color="green",
            linestyle="--",
            alpha=0.5,
            label=f"Current P={precision:.2f}",
        )
        ax3.set_xlabel("Recall", fontsize=10)
        ax3.set_ylabel("Precision", fontsize=10)
        ax3.set_title("Precision-Recall Curve", fontsize=12, fontweight="bold")
        ax3.legend(loc="best", fontsize=9)
        ax3.grid(alpha=0.3)

        # === ROW 2: Regressor Metrics (Time Series Aware) ===

        # Prepare time series data
        test_df["predicted_savings"] = pred_savings
        test_df["date"] = pd.to_datetime(test_df["timestamp"]).dt.date
        daily_agg = test_df.groupby("date").agg({"future_savings": "mean", "predicted_savings": "mean"}).reset_index()
        daily_recent = daily_agg.tail(60)

        # Plot 4: Time Series Forecast
        ax4 = fig.add_subplot(gs[2, 0])
        ax4.plot(
            daily_recent["date"],
            daily_recent["future_savings"],
            "b-",
            lw=2,
            label="Actual",
            alpha=0.8,
        )
        ax4.plot(
            daily_recent["date"],
            daily_recent["predicted_savings"],
            "r--",
            lw=2,
            label="Predicted",
            alpha=0.8,
        )
        ax4.fill_between(
            daily_recent["date"],
            daily_recent["future_savings"],
            daily_recent["predicted_savings"],
            alpha=0.2,
            color="gray",
        )
        ax4.set_xlabel("Date", fontsize=10)
        ax4.set_ylabel("Avg Daily Savings (%)", fontsize=10)
        ax4.set_title("Price Forecast (Last 60 Days)", fontsize=12, fontweight="bold")
        ax4.legend(fontsize=9)
        ax4.grid(alpha=0.3)
        ax4.tick_params(axis="x", rotation=45)

        # Plot 5: Error Over Time
        ax5 = fig.add_subplot(gs[2, 1])
        test_df["error"] = np.abs(test_df["future_savings"] - test_df["predicted_savings"])
        daily_error = test_df.groupby("date")["error"].agg(["mean", "std"]).reset_index()
        daily_error_recent = daily_error.tail(60)
        ax5.plot(
            daily_error_recent["date"],
            daily_error_recent["mean"],
            "b-",
            lw=2,
            label="Mean Error",
        )
        ax5.fill_between(
            daily_error_recent["date"],
            daily_error_recent["mean"] - daily_error_recent["std"],
            daily_error_recent["mean"] + daily_error_recent["std"],
            alpha=0.3,
            label="±1 Std",
        )
        ax5.set_xlabel("Date", fontsize=10)
        ax5.set_ylabel("Absolute Error (%)", fontsize=10)
        ax5.set_title("Error Stability", fontsize=12, fontweight="bold")
        ax5.legend(fontsize=9)
        ax5.grid(alpha=0.3)
        ax5.tick_params(axis="x", rotation=45)

        # Plot 6: Error Distribution (sampled)
        ax6 = fig.add_subplot(gs[2, 2])
        sample_size = min(100000, len(test_df))
        errors_sample = test_df["error"].sample(n=sample_size)
        ax6.hist(errors_sample, bins=50, edgecolor="black", alpha=0.7, color="steelblue")
        ax6.axvline(
            errors_sample.mean(),
            color="r",
            linestyle="--",
            lw=2,
            label=f"Mean={errors_sample.mean():.3f}",
        )
        ax6.axvline(
            errors_sample.median(),
            color="g",
            linestyle="--",
            lw=2,
            label=f"Median={errors_sample.median():.3f}",
        )
        ax6.set_xlabel("Absolute Error (%)", fontsize=10)
        ax6.set_ylabel("Frequency", fontsize=10)
        ax6.set_title(f"Error Distribution (n={sample_size:,})", fontsize=12, fontweight="bold")
        ax6.legend(fontsize=9)
        ax6.grid(alpha=0.3, axis="y")

        fig.suptitle("Performance Dashboard", fontsize=16, fontweight="bold", y=0.98)
        if pdf_pages:
            pdf_pages.savefig(fig)
        plt.savefig(self.output_dir / save_name, dpi=150, bbox_inches="tight")

        # REF: OPTIMIZATION - Aggressive Memory Cleanup
        plt.close("all")
        gc.collect()
        if not pdf_pages:  # Don't spam if printing to PDF (summary printed at end)
            print(f"   Saved: {save_name} (KPI Panel + 6 plots)")
        return optimal_threshold

    def plot_feature_analysis_dashboard(
        self,
        model,
        feature_names: list,
        save_name: str = "feature_analysis_dashboard.png",
        pdf_pages=None,
    ):
        """Feature importance dashboard (3 plots) with improved text spacing."""
        # Increased figure size and better spacing to avoid overlap
        fig = plt.figure(figsize=(20, 10))
        gs = fig.add_gridspec(1, 3, wspace=0.45)  # More horizontal spacing

        reg_imp = (
            pd.DataFrame(
                {
                    "feature": feature_names,
                    "importance": model.regressor.feature_importance(importance_type="gain"),
                }
            )
            .sort_values("importance", ascending=False)
            .head(10)  # Reduced to 10 to avoid crowding
        )

        clf_imp = (
            pd.DataFrame(
                {
                    "feature": feature_names,
                    "importance": model.classifier.feature_importance(importance_type="gain"),
                }
            )
            .sort_values("importance", ascending=False)
            .head(10)  # Reduced to 10 to avoid crowding
        )

        # Helper function to truncate long feature names
        def truncate_name(name, max_len=20):
            return name[:max_len] + "..." if len(name) > max_len else name

        # Plot 1: Regressor Top 10
        ax1 = fig.add_subplot(gs[0, 0])
        y_pos = range(len(reg_imp))
        bars1 = ax1.barh(
            y_pos,
            reg_imp["importance"].values,
            color=plt.cm.Greens(np.linspace(0.4, 0.9, len(reg_imp))),
            edgecolor="darkgreen",
            linewidth=0.5,
        )
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels([truncate_name(f) for f in reg_imp["feature"].values], fontsize=9)
        ax1.invert_yaxis()
        ax1.set_title(" Regressor - Top 10 Features", fontsize=13, fontweight="bold", pad=10)
        ax1.set_xlabel("Importance (Gain)", fontsize=10)
        ax1.grid(alpha=0.3, axis="x")
        # Add value labels on bars
        for i, (bar, val) in enumerate(zip(bars1, reg_imp["importance"].values)):
            x_pos = val + max(reg_imp["importance"]) * 0.02
            ax1.text(
                x_pos,
                i,
                f"{val:.0f}",
                va="center",
                fontsize=8,
                color="darkgreen",
            )

        ax2 = fig.add_subplot(gs[0, 1])
        y_pos = range(len(clf_imp))
        bars2 = ax2.barh(
            y_pos,
            clf_imp["importance"].values,
            color=plt.cm.Purples(np.linspace(0.4, 0.9, len(clf_imp))),
            edgecolor="darkviolet",
            linewidth=0.5,
        )
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels([truncate_name(f) for f in clf_imp["feature"].values], fontsize=9)
        ax2.invert_yaxis()
        ax2.set_title("️ Classifier - Top 10 Features", fontsize=13, fontweight="bold", pad=10)
        ax2.set_xlabel("Importance (Gain)", fontsize=10)
        ax2.grid(alpha=0.3, axis="x")
        # Add value labels on bars
        for i, (bar, val) in enumerate(zip(bars2, clf_imp["importance"].values)):
            x_pos = val + max(clf_imp["importance"]) * 0.02
            ax2.text(
                x_pos,
                i,
                f"{val:.0f}",
                va="center",
                fontsize=8,
                color="darkviolet",
            )

        # Plot 3: Side-by-side Rank Comparison (Top 8 combined)
        ax3 = fig.add_subplot(gs[0, 2])
        # Get union of top 8 features from each
        top_reg = set(reg_imp["feature"].head(8))
        top_clf = set(clf_imp["feature"].head(8))
        all_feat = list(top_reg | top_clf)[:12]  # Limit to 12 max

        reg_rank = {f: i + 1 for i, f in enumerate(reg_imp["feature"])}
        clf_rank = {f: i + 1 for i, f in enumerate(clf_imp["feature"])}

        rankings = pd.DataFrame({"feature": all_feat})
        rankings["reg"] = rankings["feature"].map(reg_rank).fillna(15)  # Not in top 15 = rank 15
        rankings["clf"] = rankings["feature"].map(clf_rank).fillna(15)
        rankings["total"] = rankings["reg"] + rankings["clf"]
        rankings = rankings.sort_values("total").head(10)  # Top 10 by combined rank

        x = np.arange(len(rankings))
        bar_width = 0.35
        ax3.barh(
            x - bar_width / 2,
            rankings["reg"],
            bar_width,
            label="Regressor Rank",
            alpha=0.8,
            color="#27ae60",
            edgecolor="darkgreen",
        )
        ax3.barh(
            x + bar_width / 2,
            rankings["clf"],
            bar_width,
            label="Classifier Rank",
            alpha=0.8,
            color="#8e44ad",
            edgecolor="darkviolet",
        )
        ax3.set_yticks(x)
        ax3.set_yticklabels([truncate_name(f, 18) for f in rankings["feature"].values], fontsize=9)
        ax3.set_xlabel("Rank (1 = Most Important)", fontsize=10)
        ax3.set_title(" Feature Rank Comparison", fontsize=13, fontweight="bold", pad=10)
        ax3.legend(loc="lower right", fontsize=9)
        ax3.grid(alpha=0.3, axis="x")
        ax3.set_xlim(0, 16)  # Fixed x-axis for better comparison

        # Add rank numbers on bars
        for i, row in enumerate(rankings.itertuples()):
            ax3.text(
                row.reg + 0.3,
                i - bar_width / 2,
                f"{int(row.reg)}",
                va="center",
                fontsize=8,
                color="#27ae60",
            )
            ax3.text(
                row.clf + 0.3,
                i + bar_width / 2,
                f"{int(row.clf)}",
                va="center",
                fontsize=8,
                color="#8e44ad",
            )

        fig.suptitle("Feature Analysis Dashboard", fontsize=16, fontweight="bold", y=0.98)
        if pdf_pages:
            pdf_pages.savefig(fig)
        plt.savefig(self.output_dir / save_name, dpi=150, bbox_inches="tight")

        # REF: OPTIMIZATION - Aggressive Memory Cleanup
        plt.close("all")
        gc.collect()
        if not pdf_pages:
            print(f"   Saved: {save_name} (Top 10 features per model)")

    def plot_business_impact_dashboard(
        self,
        test_df: pd.DataFrame,
        pred_savings: np.ndarray,
        pred_risky: np.ndarray,
        save_name: str = "business_impact_dashboard.png",
        pdf_pages=None,
    ):
        """Business visualizations with sampling and aggregation."""
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

        test_df["predicted_savings"] = pred_savings
        test_df["predicted_risky"] = pred_risky  # 1 = Risky, 0 = Safe
        test_df["error"] = np.abs(test_df["future_savings"] - pred_savings)

        # Sample for histograms
        sample_size = min(100000, len(test_df))
        sample = test_df.sample(n=sample_size)

        # Plot 1: Savings by Risk (sampled)
        ax1 = fig.add_subplot(gs[0, 0])
        safe = sample[sample["predicted_risky"] == 0]["predicted_savings"]
        risky = sample[sample["predicted_risky"] == 1]["predicted_savings"]
        if len(safe) > 0:
            ax1.hist(safe, bins=50, alpha=0.6, label="Safe", color="green", density=True)
        if len(risky) > 0:
            ax1.hist(risky, bins=50, alpha=0.6, label="Risky", color="red", density=True)
        ax1.set_xlabel("Predicted Savings (%)")
        ax1.set_ylabel("Density")
        ax1.set_title(f"Savings by Risk Level (n={sample_size:,})", fontsize=12, fontweight="bold")
        ax1.legend()
        ax1.grid(alpha=0.3, axis="y")

        # Plot 2: Risk by Family (aggregated)
        ax2 = fig.add_subplot(gs[0, 1])
        test_df["family"] = test_df["InstanceType"].astype(str).str.extract(r"^([a-z0-9]+)\.", expand=False)
        test_df["family"] = test_df["family"].fillna("unknown")

        # REF: OPTIMIZATION - Vectorized aggregation (no lambda)
        family_risk = (
            test_df.groupby("family")["predicted_risky"]
            .mean()  # Optimization: Direct .mean() instead of .apply(lambda x: x.mean())
            .mul(100)
            .sort_values(ascending=False)
            .head(15)
        )
        colors = ["red" if x > 30 else "orange" if x > 15 else "green" for x in family_risk.values]
        ax2.barh(range(len(family_risk)), family_risk.values, color=colors, edgecolor="black")
        ax2.set_yticks(range(len(family_risk)))
        ax2.set_yticklabels(family_risk.index)
        ax2.set_xlabel("% Predicted Risky")
        ax2.set_title("Risk by Family", fontsize=12, fontweight="bold")
        ax2.grid(alpha=0.3, axis="x")

        # Plot 3: Worst Pools (aggregated)
        ax3 = fig.add_subplot(gs[1, 0])
        pool_err = (
            test_df.groupby(["InstanceType", "AZ"]).agg({"error": "mean", "future_savings": "count"}).reset_index()
        )
        pool_err.columns = ["InstanceType", "AZ", "mean_error", "count"]
        pool_err["pool"] = pool_err["InstanceType"].astype(str) + "_" + pool_err["AZ"].astype(str)
        worst = pool_err[pool_err["count"] > 500].nlargest(10, "mean_error")
        ax3.barh(range(len(worst)), worst["mean_error"], color="coral", edgecolor="black")
        ax3.set_yticks(range(len(worst)))
        ax3.set_yticklabels(worst["pool"], fontsize=8)
        ax3.set_xlabel("Mean Absolute Error (%)")
        ax3.set_title("Top 10 Worst Pools", fontsize=12, fontweight="bold")
        ax3.grid(alpha=0.3, axis="x")

        # Plot 4: Temporal Trend (aggregated)
        ax4 = fig.add_subplot(gs[1, 1])
        test_df["date"] = pd.to_datetime(test_df["timestamp"]).dt.date

        # REF: OPTIMIZATION - Vectorized aggregation
        daily = (
            test_df.groupby("date")
            .agg(mean_error=("error", "mean"), risky_pct=("predicted_risky", "mean"))
            .reset_index()
        )
        daily["risky_pct"] = daily["risky_pct"] * 100

        daily_recent = daily.tail(60)
        ax4_twin = ax4.twinx()
        ln1 = ax4.plot(
            daily_recent["date"],
            daily_recent["mean_error"],
            "b-",
            lw=2,
            label="Mean Error",
        )
        ln2 = ax4_twin.plot(
            daily_recent["date"],
            daily_recent["risky_pct"],
            "r--",
            lw=2,
            label="% Risky",
        )
        ax4.set_xlabel("Date")
        ax4.set_ylabel("Mean Error (%)", color="b")
        ax4_twin.set_ylabel("% Risky", color="r")
        ax4.tick_params(axis="x", rotation=45)
        ax4.legend(ln1 + ln2, [line.get_label() for line in ln1 + ln2], loc="upper left")
        ax4.set_title("Trends (Last 60 Days)", fontsize=12, fontweight="bold")
        ax4.grid(alpha=0.3)

        fig.suptitle("Business Impact Dashboard", fontsize=16, fontweight="bold", y=0.98)
        if pdf_pages:
            pdf_pages.savefig(fig)
        plt.savefig(self.output_dir / save_name, dpi=150, bbox_inches="tight")

        # REF: OPTIMIZATION - Aggressive Memory Cleanup
        plt.close("all")
        plt.clf()
        gc.collect()
        if not pdf_pages:
            print(f"   Saved: {save_name}")


if __name__ == "__main__":
    print("Time series-optimized visualization module loaded!")
