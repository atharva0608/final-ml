# AWS Spot Optimizer - Project Overview

> **V1 and V2 Implementation Plans, Training Roadmap, and Infrastructure Analysis**

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         AWS SPOT OPTIMIZER                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────┐         ┌─────────────────────┐                  │
│   │      V1 SYSTEM      │         │      V2 SYSTEM      │                  │
│   │  (Internal Logic)   │         │  (External Engine)  │                  │
│   └──────────┬──────────┘         └──────────┬──────────┘                  │
│              │                               │                              │
│              ▼                               ▼                              │
│   ┌──────────────────┐           ┌──────────────────────┐                  │
│   │ Historical Data  │           │ Historical + AWS API │                  │
│   │ + Model Predict  │           │ Interruption Data    │                  │
│   └──────────────────┘           └──────────────────────┘                  │
│              │                               │                              │
│              ▼                               ▼                              │
│   ┌──────────────────┐           ┌──────────────────────┐                  │
│   │ Risk Zone:       │           │ Risk Zone:           │                  │
│   │ Safe/Warn/Danger │           │ (Enhanced accuracy)  │                  │
│   └──────────────────┘           └──────────────────────┘                  │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## V1: Internal Decision System

**Location:** `spot_optimizer_v1/`
**Status:**  Complete and production-ready

### Key Features
| Feature | Description |
|---------|-------------|
| Multi-horizon forecasting | 1h, 6h, 24h predictions |
| Hybrid model | Regressor (savings) + Classifier (stability) |
| Family Stress Index | Cross-instance contagion detection |
| Family-Time Patterns | Learned time patterns per instance family |
| Z-score risk zones | Instance-specific thresholds |
| Walk-forward backtesting | Time-series validation |
| SHAP analysis | Feature importance interpretability |

### Project Structure
```
spot_optimizer_v1/
├── src/
│   ├── data.py       # Data loading + feature engineering
│   ├── model.py      # LightGBM hybrid model
│   ├── backtest.py   # Walk-forward validation
│   └── shap.py       # SHAP analysis
├── scripts/
│   ├── train.py      # Training pipeline
│   └── backtest.py   # Backtesting script
├── config/config.yaml
├── docs/TECHNICAL_DOCS.md
└── README.md
```

---

## V2: External Decision Engine

**Location:** `spot_optimizer_v2/`
**Status:** ⏳ Skeleton (requires V1 trained models + AWS API)

### How V2 Differs from V1
| Aspect | V1 Internal | V2 External |
|--------|-------------|-------------|
| Data source | Historical only | Historical + AWS API |
| Accuracy | Good | Better (with live data) |
| Latency | ~10ms | ~50ms (API call) |
| Dependencies | None | AWS API (boto3) |

### V1 vs V2 Decision Logic

**V1 (Internal - Current Production):**
- **Inputs**: Historical Price + Computed Stability Features.
- **Output 1 (Savings)**: Predicted % savings (Regressor).
- **Output 2 (Risk)**: Probability of instability (Classifier, 0.0-1.0).
- **Decision**:
  - If `Risk Score > 0.5` → **Unsafe**.
  - If `Z-Score < -3.0` → **Danger Zone**.

**V2 (External - Planned):**
- **Inputs**: All V1 outputs + **Live AWS API Interruption Rate**.
- **Logic**:
  - `Risk_Adjusted = V1_Risk_Prob + (AWS_Interruption_Freq * Weight)`
  - Use live frequency to catch "black swan" events not in history.

### V2 Structure
```
spot_optimizer_v2/
├── src/decision/
│   └── external_engine.py   # V2 decision logic
└── README.md
```

---

## Training Roadmap

### Phases Overview

| Phase | Trials | Time (M4) | Time (GPU) | Target |
|-------|--------|-----------|------------|--------|
| 1. Baseline | 0 | 1 hr | - | MAPE < 10%, F1 > 60% |
| 2. Quick Tune | 10 | 3 hrs | 1 hr | Better than baseline |
| 3. Medium Tune | 50 | 10 hrs | 2 hrs | MAPE < 5%, F1 > 75% |
| 4. Deep Tune | 100 | 20 hrs | 4 hrs | MAPE < 3%, F1 > 80% |
| 5. Production | 1 | 1 hr | 0.5 hr | Final deployment |

### Current Status
- [x] V1 code complete
- [x] Documentation complete
- [x] Walk-forward backtesting implemented
- [x] SHAP analysis added
- [ ] **Phase 1: Baseline Training** ← START HERE
- [ ] Phase 2-5: Optuna tuning

### Quick Start
```bash
cd spot_optimizer_v1
conda activate lightgbm
python scripts/train.py
```

---

## GPU Infrastructure

### RAM Requirements

| Mode | RAM Needed |
|------|------------|
| LightGBM Baseline (30% sample) | 12-16 GB |
| LightGBM + Optuna (100 trials) | 16-24 GB |
| TFT Training | 32-48 GB |
| TFT + HPO | 48-64 GB |

### GPU Pricing (Vast.ai - Best Value)

| GPU | $/hr | 100 Optuna Trials |
|-----|------|-------------------|
| RTX 4090 | $0.35 | ~$1.50 |
| A100 40GB | $0.55 | ~$2.00 |
| A100 80GB | $0.70 | ~$2.50 |

### Cloud Comparison (TFT 100 Trials)

| Platform | Cost |
|----------|------|
| **Vast.ai A100** | **~$210**  |
| GCP Preemptible V100 | ~$270 |
| GCP Standard V100 | ~$865 |
| AWS SageMaker P3 | ~$1,150 |

---

## 39 Features

| Category | Count | Examples |
|----------|-------|----------|
| Temporal | 10 | hour, is_weekend, cyclical |
| Lag | 3 | 1h, 4h, 24h lookback |
| Rolling | 8 | mean/std/min/max windows |
| Price Dynamics | 5 | velocity, volatility, saturation |
| Family-Time | 6 | Learned patterns |
| Family Stress | 3 | Contagion detection |
| Events | 3 | Holidays, stress events |
| Pool Risk | 1 | Zero-savings rate |

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Regressor MAPE | < 5% |
| Classifier F1 | > 80% |
| Memory usage | < 12 GB on M4 |
| No data leakage | Verified |
