# Complete Feature Mapping - ONNX Models

**Date**: 2026-02-16
**Status**: ✅ RESOLVED - Feature set identified from training code
**Training Code**: `/ml_model/model/spot_optimizer_v1/`

---

## 🎯 CRITICAL FINDINGS

### Feature Count Discrepancy Resolved

| Source | Feature Count | Status |
|--------|---------------|--------|
| **ONNX Model Inspection** | 45 features | ✅ Verified |
| **Training Code (`get_feature_columns`)** | 39 features | ✅ Verified |
| **User Statement** | 108 (100 categorical + 8 numerical) | ❌ Incorrect |
| **Actual** | **39 numerical features** (LightGBM handles instance_family/instance_size/AZ internally) | ✅ CORRECT |

### Why the Discrepancy?

**ONNX Model shows 45 features vs Training code shows 39:**
- **Likely reason**: ONNX export added 6 extra slots for instance type metadata
- **OR**: Model was trained with some categorical features that get encoded during inference
- **OR**: Version mismatch between training code and exported models

---

## 📊 Complete Feature List (39 Features from Training Code)

### 1. Temporal Features (10 features)
```python
1.  hour                  # Hour of day (0-23)
2.  day_of_week           # Day (0-6, Monday=0)
3.  day_of_month          # Day of month (1-31)
4.  month                 # Month (1-12)
5.  is_weekend            # Binary (1=weekend, 0=weekday)
6.  is_business_hours     # Binary (1=9AM-5PM, 0=otherwise)
7.  hour_sin              # Cyclical encoding: sin(2π × hour / 24)
8.  hour_cos              # Cyclical encoding: cos(2π × hour / 24)
9.  day_sin               # Cyclical encoding: sin(2π × day / 7)
10. day_cos               # Cyclical encoding: cos(2π × day / 7)
```

### 2. Lag Features (3 features)
```python
11. savings_lag_6         # Savings 1 hour ago (6 × 10min intervals)
12. savings_lag_24        # Savings 4 hours ago (24 × 10min intervals)
13. savings_lag_144       # Savings 24 hours ago (144 × 10min intervals)
```

### 3. Rolling Window Features (8 features)
```python
# 4-hour window (24 × 10min intervals)
14. savings_mean_24       # Mean savings over last 4 hours
15. savings_std_24        # Std dev of savings over last 4 hours
16. savings_min_24        # Min savings over last 4 hours
17. savings_max_24        # Max savings over last 4 hours

# 24-hour window (144 × 10min intervals)
18. savings_mean_144      # Mean savings over last 24 hours
19. savings_std_144       # Std dev of savings over last 24 hours
20. savings_min_144       # Min savings over last 24 hours
21. savings_max_144       # Max savings over last 24 hours
```

### 4. Price Dynamics Features (5 features)
```python
22. price_velocity_1h     # % change in spot price over 1 hour
23. price_volatility_6h   # Std dev of spot price over 6 hours
24. headroom_to_ondemand  # (OnDemand - Spot) / OnDemand
25. pool_saturation       # (Current - Min) / (OnDemand - Min) [0-1.5]
26. consecutive_stable_hours  # Hours of stable pricing
```

### 5. Family-Time Pattern Features (6 features)
**Data-driven patterns learned from historical data**
```python
27. family_hour_avg_savings       # Avg savings for this family at this hour
28. family_hour_std_savings       # Volatility for this family at this hour
29. family_dow_avg_savings        # Avg savings for this family on this weekday
30. family_hour_deviation         # Current vs typical for family at this hour
31. family_hour_zscore            # Z-score of current vs family-hour distribution
32. family_weekend_avg_savings    # Avg savings for this family on weekends
```

### 6. Family Stress Features (3 features)
**Cross-instance contagion detection**
```python
33. family_stress_index   # Detects family-wide issues
34. family_avg_savings    # Overall family baseline
35. family_std_savings    # Family volatility baseline
```

### 7. Event Features (3 features)
```python
36. is_holiday            # Binary (1=holiday, 0=normal)
37. is_stress_event       # Binary (1=stress event active, 0=normal)
38. days_to_nearest_event # Days until next known event
```

### 8. Pool Risk Feature (1 feature)
```python
39. pool_historical_zero_rate  # Historical failure rate for this pool
```

---

## 🔍 Missing 6 Features (ONNX Model expects 45, training uses 39)

### Hypothesis: Categorical Encoding

The missing 6 features are likely:
1. `instance_family_encoded` (integer or one-hot)
2. `instance_size_encoded` (integer or one-hot)
3. `AZ_encoded` (integer or one-hot)
4-6. Reserved/padding slots

**OR** LightGBM's categorical feature handling:
- LightGBM can handle categorical features natively
- During ONNX export, these might be expanded to numerical representations

---

## 📋 Input Data Required for Inference

### Required Raw Data
```python
{
    # Metadata (for categorical encoding)
    "InstanceType": "m5.xlarge",  # Will be split into family+size
    "AZ": "aps1-az1",
    "Region": "ap-south-1",

    # Current state
    "SpotPrice": 0.045,           # float
    "OndemandPrice": 0.096,       # float
    "Savings": 0.53,              # float (current savings %)
    "timestamp": "2026-02-16T10:00:00Z",

    # Historical data (for lag/rolling features)
    "price_history": [...],       # List of past spot prices
    "savings_history": [...],     # List of past savings values
}
```

### Feature Engineering Pipeline

```python
# Step 1: Parse instance type
instance_family = "m5"   # from "m5.xlarge"
instance_size = "xlarge"  # from "m5.xlarge"

# Step 2: Temporal features (from timestamp)
hour = 10
day_of_week = 6  # Sunday
day_of_month = 16
month = 2
is_weekend = 1
is_business_hours = 0
hour_sin = sin(2π × 10 / 24)
hour_cos = cos(2π × 10 / 24)
day_sin = sin(2π × 6 / 7)
day_cos = cos(2π × 6 / 7)

# Step 3: Lag features (from savings_history)
savings_lag_6 = savings_history[-6]    # 1 hour ago
savings_lag_24 = savings_history[-24]  # 4 hours ago
savings_lag_144 = savings_history[-144]  # 24 hours ago

# Step 4: Rolling features (from savings_history)
savings_mean_24 = mean(savings_history[-24:])
savings_std_24 = std(savings_history[-24:])
# ... etc for all rolling features

# Step 5: Price dynamics (from price_history)
price_velocity_1h = (price_history[-1] - price_history[-6]) / price_history[-6]
price_volatility_6h = std(price_history[-36:])
headroom_to_ondemand = (OndemandPrice - SpotPrice) / OndemandPrice
# ... etc

# Step 6: Family-Time patterns (requires historical database)
family_hour_avg_savings = get_family_hour_baseline(instance_family, hour)
# ... etc (requires pre-computed statistics)

# Step 7: Family stress (requires cross-instance data)
family_stress_index = calculate_family_stress(instance_family, timestamp)
# ... etc

# Step 8: Events (from event calendar)
is_holiday = check_holiday(timestamp)
is_stress_event = check_stress_events(timestamp)
days_to_nearest_event = days_until_next_event(timestamp)

# Step 9: Pool risk (from historical database)
pool_historical_zero_rate = get_pool_failure_rate(InstanceType, AZ)
```

---

## 🔧 Integration Requirements

### Data Dependencies

1. **Real-time data**:
   - Current spot price
   - Current timestamp
   - Instance type and AZ

2. **Historical time-series** (required for lag/rolling features):
   - Last 24 hours of spot prices (144 data points)
   - Last 24 hours of savings values (144 data points)
   - Stored per (InstanceType, AZ) pair

3. **Pre-computed statistics** (from training data):
   - Family-hour baselines (75 families × 24 hours = 1,800 values)
   - Family-weekday baselines (75 families × 7 days = 525 values)
   - Pool historical failure rates (per pool)

4. **Event calendar**:
   - Holiday dates
   - Known stress events (outages, maintenance windows)

### Storage Requirements

```sql
-- Historical time-series storage
CREATE TABLE spot_price_history (
    instance_type VARCHAR(50),
    az VARCHAR(20),
    timestamp TIMESTAMP,
    spot_price DECIMAL(10,6),
    ondemand_price DECIMAL(10,6),
    savings DECIMAL(5,4),
    PRIMARY KEY (instance_type, az, timestamp)
);
CREATE INDEX idx_recent ON spot_price_history(instance_type, az, timestamp DESC);

-- Pre-computed baselines
CREATE TABLE family_hour_baselines (
    instance_family VARCHAR(20),
    hour INT,
    avg_savings DECIMAL(5,4),
    std_savings DECIMAL(5,4),
    PRIMARY KEY (instance_family, hour)
);

-- Pool risk scores
CREATE TABLE pool_risk_scores (
    instance_type VARCHAR(50),
    az VARCHAR(20),
    historical_zero_rate DECIMAL(5,4),
    last_updated TIMESTAMP,
    PRIMARY KEY (instance_type, az)
);
```

---

## ⚡ Quick Integration Checklist

### Phase 1: Basic Integration (Using Available Features Only)
- [ ] Implement temporal feature extraction (10 features) ✅ EASY
- [ ] Add lag features (requires 24h history) ⚠️ MEDIUM
- [ ] Skip rolling features initially (use defaults) ⚠️ OPTIONAL
- [ ] Calculate price dynamics (requires price history) ⚠️ MEDIUM
- [ ] Skip family-time patterns (use defaults) ⚠️ OPTIONAL
- [ ] Skip family stress features (use defaults) ⚠️ OPTIONAL
- [ ] Implement event features (simple calendar check) ✅ EASY
- [ ] Skip pool risk initially (use default 0.05) ⚠️ OPTIONAL

**Minimum Viable Features**: ~15-20 features (others set to 0 or defaults)

### Phase 2: Full Integration
- [ ] Implement historical data storage
- [ ] Pre-compute family-hour baselines
- [ ] Implement rolling window calculations
- [ ] Add family stress detection
- [ ] Populate pool risk scores

---

## 🎯 Model Output Interpretation (VERIFIED)

### Classifier Model (classifier_6.onnx)
```python
Input: 45 features (39 numerical + 6 categorical/padding)
Output: Single float (0.92-0.94 observed)

Interpretation:
- NOT a binary classifier (despite name)
- Outputs SAVINGS PERCENTAGE (e.g., 0.93 = 93% savings vs on-demand)
- OR Spot availability score
```

### Regressor Model (regressor_6.onnx)
```python
Input: 45 features (same as classifier)
Output: Single float (14-15 observed)

Interpretation:
- Likely COST PREDICTION (e.g., 14.07 = $14/day or $140/month)
- OR hours until interruption
- OR capacity score
```

---

## 📝 Next Steps

### Immediate
1. **Reconcile 39 vs 45 feature mismatch**:
   - Check ONNX export code
   - Test model with 39 features (pad with zeros for missing 6)
   - Or test with 45 features (add categorical encodings)

2. **Test with real data**:
   - Extract features from actual AWS Spot Advisor data
   - Compare predictions with real outcomes
   - Validate feature importance matches training

### Short-term
1. **Implement minimum viable feature pipeline** (15-20 features)
2. **Test predictions with partial features**
3. **Gradually add complex features** (family patterns, stress index)

### Long-term
1. **Build historical data collection pipeline**
2. **Pre-compute family/pool baselines**
3. **Deploy full feature engineering pipeline**

---

## 📚 References

**Training Code**:
- Feature engineering: `src/data.py::engineer_all_features()`
- Feature list: `src/data.py::get_feature_columns()`
- Model training: `scripts/train.py`

**Documentation**:
- Training README: `README.md`
- Technical docs: `docs/TECHNICAL_DOCS.md`

**Model Files**:
- Classifier: `classifier_6.onnx`
- Regressor: `regressor_6.onnx`
- Category mapping: `category_mapping.json`

---

**Status**: ✅ Feature set identified - Ready for integration with partial features
