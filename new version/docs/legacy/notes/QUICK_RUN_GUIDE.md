# Quick Run Guide - Family Stress Model

## 🚀 How to Run (1 Minute)

```bash
cd /home/user/final-ml/ml-model
python family_stress_model.py
```

**Expected Runtime**: 10-15 minutes on M4 MacBook Air

---

## 📊 What to Look For in Output

### 1. Price Range Diagnostics

**This section** (appears early):
```
📊 Calculating Price Position (7-day window)...
  Diagnostic: Checking price volatility...
    c5.large_ap-south-1a: min=$0.0848, max=$0.0853, range=$0.0005
    c5.xlarge_ap-south-1a: min=$0.1696, max=$0.1706, range=$0.0010
    t3.large_ap-south-1b: min=$0.0528, max=$0.0531, range=$0.0003
```

**✓ GOOD**: Range > $0.0001 (has variance)
**⚠️ WARNING**: Range < $0.0001 (very stable)
**❌ BAD**: Range = $0.0000 (no variance - data issue!)

---

### 2. Feature Statistics

**Look for these sections**:

```
📊 Calculating Price Position (7-day window)...
  ✓ Price Position calculated
  Mean: 0.342   ← Should be 0.2-0.6
  Std: 0.187    ← Should be > 0.01 (NOT 0.000!)
  Min: 0.000, Max: 1.000

📈 Calculating Price Velocity & Volatility (backup features)...
  ✓ Price Velocity calculated
  Velocity Mean: 0.000056, Std: 0.001234  ← Should have std > 0
  Volatility Mean: 0.000234, Std: 0.000456  ← Should have std > 0
  CV Mean: 0.000401, Std: 0.000234  ← Should have std > 0

💰 Calculating Discount Depth...
  ✓ Discount Depth calculated
  Mean: 0.721   ← Should be 0.5-0.8
  Std: 0.023    ← Should be > 0.01

🔥 Calculating Family Stress Index (VECTORIZED - Pivot Table)...
  Processing c5 family...
  Processing t4g family...
  Processing t3 family...
  Mean: 0.358   ← Should be 0.2-0.6
  Std: 0.192    ← Should be > 0.01 (NOT 0.000!)
```

**✓ GOOD**: All Std > 0.01
**⚠️ WARNING**: Std between 0.001-0.01 (low variance)
**❌ BAD**: Std = 0.000 (zero variance - features useless!)

---

### 3. Target Variable Statistics

```
🎯 Creating target variable (VECTORIZED - Rolling Max)...
  For training data (2023-2024):
  Unstable samples: 32,135 (1.2%)  ← Should be 1-10%
  Stable samples: 2,645,773 (98.8%)

  For test data (2025 Q1):
  Unstable samples: 26,842 (1.0%)
  Stable samples: 2,654,381 (99.0%)
```

**✓ GOOD**: 1-10% unstable samples
**⚠️ WARNING**: 0.1-1% (model can still train but will be weaker)
**❌ BAD**: <0.1% (too few positive samples to learn)

---

### 4. Data Quality Validation (NEW!)

```
🔍 Data Quality Validation...
  price_position      : Mean=0.342000, Std=0.187000  ✓
  price_velocity_1h   : Mean=0.000056, Std=0.001234  ✓
  price_volatility_6h : Mean=0.000234, Std=0.000456  ✓
  price_cv_6h         : Mean=0.000401, Std=0.000234  ✓
  discount_depth      : Mean=0.721000, Std=0.023456  ✓
  family_stress       : Mean=0.358000, Std=0.192000  ✓
  hour_sin            : Mean=0.000123, Std=0.707000  ✓
  hour_cos            : Mean=0.000891, Std=0.707000  ✓
  is_weekend          : Mean=0.286000, Std=0.452000  ✓
  is_business_hours   : Mean=0.375000, Std=0.484000  ✓
```

**✓ ALL GREEN**: Ready to train!

**If you see**:
```
  price_position      : Mean=0.000000, Std=0.000000  ⚠️  ZERO VARIANCE - Feature may not be useful!
  family_stress       : Mean=0.000000, Std=0.000000  ⚠️  ZERO VARIANCE - Feature may not be useful!

⚠️  WARNING: 2 features have zero variance!
  Features: price_position, family_stress

  Recommendations:
  1. Check raw price data for actual volatility
  2. Reduce window size (try 3-day or 24-hour)
  3. Consider using velocity/volatility features instead
  4. Use different time period with more price movement
```

**Action**:
- Velocity features should still work (price_velocity_1h, etc.)
- Model can still train but won't use zero-variance features
- Consider reducing window size (edit line 107 in family_stress_model.py)

---

### 5. Model Training

```
🤖 Training LightGBM Binary Classifier...
  Features: 10
  Training samples: 2,645,773
  Positive samples: 32,135 (1.2%)
  scale_pos_weight: 82.3
  Training...
  ✓ Model trained successfully
```

**Should complete in**: 2-5 minutes

---

### 6. Model Evaluation

```
📈 Evaluating model on test data...

  Confusion Matrix:
                Predicted
                0         1
  Actual  0     2,630,000 24,381
          1     10,737    26,105

  Classification Metrics:
    Precision: 0.72  ← Should be >0.65
    Recall: 0.68     ← Should be >0.60
    F1 Score: 0.70   ← Should be >0.65
    AUC: 0.85        ← Should be >0.75

  ✓ AUC (0.85) exceeds target (0.75) ✅
```

**✓ GOOD**: AUC >0.75, Precision >0.65, Recall >0.60
**⚠️ WARNING**: AUC 0.65-0.75 (model is learning but weak)
**❌ BAD**: AUC <0.65 (model is barely better than random)

---

### 7. Feature Importance

```
🔍 Feature Importance Analysis:

  Top 5 Features:
    1. family_stress       0.352  ← Should be #1 or #2! (hardware contagion)
    2. price_velocity_1h   0.243
    3. discount_depth      0.178
    4. price_volatility_6h 0.087
    5. hour_sin            0.065
```

**✓ EXCELLENT**: `family_stress` is #1 → Hardware contagion hypothesis validated!
**✓ GOOD**: `family_stress` in top 3 → Signal is working
**⚠️ WARNING**: `family_stress` < top 5 → Signal is weak
**❌ BAD**: `family_stress` near bottom → Not capturing hardware dependency

**If velocity features dominate**: Market is very stable, velocity is more useful than position

---

### 8. Graphs Generated

```
📊 Generating visualizations...
  ✓ Precision-Recall curve saved
  ✓ Feature importance saved
  ✓ Prediction timeline saved
```

**Check these files**:
1. `./training/plots/precision_recall_curve.png`
2. `./training/plots/feature_importance_bar_chart.png`
3. `./training/plots/prediction_timeline_overlay.png`

---

## ✅ Success Checklist

Run through this after model completes:

### Data Quality
- [ ] Price ranges > $0.0001 (has actual variance)
- [ ] All features have Std > 0.000001 (no zero variance)
- [ ] Unstable samples >1% (enough to train)

### Model Performance
- [ ] AUC >0.75 (target met)
- [ ] Precision >0.65 (when model says "unsafe", it's usually right)
- [ ] Recall >0.60 (model catches most real unstable periods)

### Feature Validation
- [ ] `family_stress` in top 3 features (hardware contagion working)
- [ ] Velocity features useful if market is stable
- [ ] No warnings about zero variance

### Output Files
- [ ] 3 graphs generated in `./training/plots/`
- [ ] Model saved to `./models/uploaded/family_stress_model.pkl`
- [ ] Metrics saved to `./training/outputs/evaluation_metrics.txt`

---

## 🔧 Common Issues

### Issue 1: "Price Position = 0.000 ± 0.000"

**Cause**: Mumbai prices are extremely stable

**Solution**: Velocity features should compensate! Check:
```
Price Velocity: Mean=?, Std=?
```
- If velocity has std > 0.001: ✓ Backup features working
- If velocity also = 0: Data has NO movement at all

**Fix**: Reduce window size
```python
# Edit line 107:
'price_position_window_days': 3,  # Try 3-day or even 1-day
```

---

### Issue 2: "Only 0.02% unstable samples"

**Cause**: 1% spike threshold still too high for stable market

**Solution**: Lower threshold
```python
# Edit line 102:
'spike_threshold': 0.005,  # 0.5% instead of 1%
```

**Or**: Accept that market is very stable and model will detect rare events

---

### Issue 3: "AUC = 0.52 (random guessing)"

**Cause**: Features have zero variance OR data is too stable

**Solution**:
1. Check data quality validation output
2. If zero variance: Use velocity-only features
3. If data is flat: Try different time period with more volatility

---

### Issue 4: "Family stress importance is very low"

**Cause**: Hardware contagion signal is weak in your data

**Possible reasons**:
1. Family members don't actually correlate (wrong family grouping)
2. Not enough signal instances (add more to 'signals' list)
3. Data period was too stable (no capacity crunches)

**Validation**: Check if large instances spike when small ones get interrupted

---

## 🎯 Target Metrics

| Metric | Minimum | Good | Excellent |
|--------|---------|------|-----------|
| **AUC** | 0.75 | 0.80 | 0.85+ |
| **Precision** | 0.65 | 0.70 | 0.75+ |
| **Recall** | 0.60 | 0.65 | 0.70+ |
| **F1** | 0.65 | 0.70 | 0.75+ |
| **Unstable %** | 1% | 3% | 5%+ |
| **family_stress rank** | Top 5 | Top 3 | #1 |

---

## 📞 Troubleshooting Guide

### Data Issues
- **All prices identical**: Data quality problem - check source CSV
- **No variance in features**: Reduce window size or use velocity-only
- **Too few unstable samples**: Lower spike threshold

### Model Issues
- **AUC <0.60**: Features have no signal - check data quality
- **Precision = 0**: No positive predictions - check class imbalance
- **Family stress low importance**: Hardware contagion not present in data

### Performance Issues
- **Runtime >30 min**: Check data size, reduce if needed
- **Out of RAM**: Use chunked loading (already implemented)
- **Stuck at family stress**: Should complete in 2-3 seconds (vectorized)

---

## 📚 Documentation

- **FAMILY_STRESS_MODEL_GUIDE.md**: Complete technical guide
- **PERFORMANCE_FIXES.md**: 3 critical performance optimizations
- **STABLE_MARKET_SOLUTIONS.md**: Zero variance problem solutions
- **MODEL_COMPARISON.md**: Comparison with other models
- **LATEST_UPDATES.md**: Recent changes and improvements

---

**Status**: ✅ **Ready to Run**

Simply execute:
```bash
python family_stress_model.py
```

Check output against this guide and you'll know immediately if results are good!
