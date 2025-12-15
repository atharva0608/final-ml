# 🔧 Hybrid On-Demand Price Handling - "Trust, but Verify"

## ✅ Implementation Complete!

**Strategy**: Prefer CSV truth over static dictionary, with intelligent fallbacks

---

## 🎯 The Problem This Solves

### Before (Static Dictionary Only)
```python
# Old approach - ALWAYS used static CONFIG dictionary
df['on_demand_price'] = df['instance_type'].map(CONFIG['on_demand_prices'])
```

**Problems**:
1. ❌ Ignores historical price changes in CSV data
2. ❌ Can't capture AWS price updates over time
3. ❌ If CSV has real on-demand prices, they're discarded

**Example failure**:
- CSV says: `c5.large` was `$0.096` in Jan 2024, `$0.090` in Dec 2024
- Old code: Uses `$0.096` for ALL rows (static dictionary)
- **Result**: Discount depth calculated incorrectly for Dec 2024 data!

---

### After (Hybrid Approach)
```python
# New approach - Smart 3-tier strategy
if 'on_demand_price' in df.columns:
    # CSV has the column - use it!
    if has_gaps:
        # Patch gaps with dictionary
    else:
        # Use CSV entirely
else:
    # CSV missing column - use dictionary
```

**Benefits**:
1. ✅ Respects historical truth (captures price changes over time)
2. ✅ Handles missing data gracefully (patches gaps)
3. ✅ Works with legacy datasets (falls back to dictionary)
4. ✅ Never crashes (triple fallback system)

---

## 🔧 Implementation Details

### CHANGE 1: Enhanced Column Detection

**Updated**: `standardize_columns()` function

**What it does**: Actively hunts for on-demand price columns with various naming conventions

```python
# Hunt for on-demand price column
on_demand_price_col = None

for col in df.columns:
    col_lower = col.lower()

    # Catches: "ondemandprice", "on_demand_price", "OnDemandPrice"
    if 'demand' in col_lower and 'price' in col_lower:
        on_demand_price_col = col

    # Catches: "od_price", "odprice", "OD_Price"
    elif 'od' in col_lower and 'price' in col_lower:
        on_demand_price_col = col
```

**Column mapping**:
```python
if on_demand_price_col:
    col_mapping[on_demand_price_col] = 'on_demand_price'
    # Keep this column (don't drop it!)
    required_cols.append('on_demand_price')
```

**Diagnostic output** (first chunk only):
```
📋 Column mapping:
  Timestamp: 'Time' → 'timestamp'
  Instance: 'InstanceType' → 'instance_type'
  AZ: 'AvailabilityZone' → 'availability_zone'
  Spot Price: 'SpotPrice' → 'spot_price'
  On-Demand Price: 'OndemandPrice' → 'on_demand_price'
✓ Found REAL On-Demand Price column in CSV! (Captures historical changes)
```

---

### CHANGE 2: Three-Tier Hybrid Logic

**Updated**: `load_data_efficient()` function

**Scenario A: CSV Column Exists & Complete**

CSV has on-demand prices with no gaps:

```python
if 'on_demand_price' in df.columns:
    missing_mask = df['on_demand_price'].isna() | (df['on_demand_price'] == 0)

    if missing_mask.sum() == 0:
        # No gaps - use CSV entirely!
        print("✓ Using CSV on-demand prices (complete, no gaps)")
```

**Output**:
```
✓ Using CSV on-demand prices (complete, no gaps)
```

**What this means**: Your CSV has perfect on-demand price data. The model will use historical prices (captures AWS price changes over time).

---

**Scenario B: CSV Column Missing Entirely**

CSV doesn't have an on-demand price column:

```python
if 'on_demand_price' not in df.columns:
    # Create column from CONFIG dictionary
    print("ℹ️ Using Static CONFIG Dictionary for On-Demand prices (CSV column missing)")
    df['on_demand_price'] = df['instance_type'].map(CONFIG['on_demand_prices'])
```

**Output**:
```
On-Demand Price: NOT FOUND
⚠️ On-Demand Price column MISSING. Will use Static Dictionary.

ℹ️ Using Static CONFIG Dictionary for On-Demand prices (CSV column missing)
```

**What this means**: Your CSV is legacy data without on-demand prices. The model uses static 2024 prices from CONFIG.

---

**Scenario C: CSV Column Exists with Gaps**

CSV has on-demand prices but some rows are missing (NaN) or zero:

```python
if 'on_demand_price' in df.columns:
    missing_mask = df['on_demand_price'].isna() | (df['on_demand_price'] == 0)

    if missing_mask.sum() > 0:
        # Patch gaps with CONFIG dictionary
        print(f"🔧 Patching {missing_mask.sum():,} missing on-demand prices using CONFIG dictionary")
        df.loc[missing_mask, 'on_demand_price'] = df.loc[missing_mask, 'instance_type'].map(CONFIG['on_demand_prices'])
```

**Output**:
```
✓ Found REAL On-Demand Price column in CSV! (Captures historical changes)

🔧 Patching 1,234 missing on-demand prices using CONFIG dictionary
```

**What this means**: Your CSV has mostly good data with some gaps. The model uses CSV where available, patches gaps with dictionary.

---

### CHANGE 3: Final Safety Net

After all logic, check if any rows still have missing on-demand prices:

```python
# Final Safety Check: Any NaNs left?
final_missing = df['on_demand_price'].isna()

if final_missing.sum() > 0:
    # Instance type not in CONFIG dictionary - use spot*4 fallback
    print(f"⚠️ {final_missing.sum():,} rows still missing OD price (instance type not in CONFIG)")
    print(f"   Using spot*4.0 fallback for these rows")
    df.loc[final_missing, 'on_demand_price'] = df.loc[final_missing, 'spot_price'] * 4.0
```

**When this triggers**: You have an instance type that's not in the CONFIG dictionary (e.g., new instance type AWS just released).

**Output**:
```
⚠️ 42 rows still missing OD price (instance type not in CONFIG)
   Using spot*4.0 fallback for these rows
```

**What this means**: Some rows had unknown instance types. The model estimates on-demand price as `spot_price × 4` (conservative fallback).

---

## 📊 Output Examples

### Example 1: Perfect CSV (Scenario A)
```
📂 Loading training data...
  File: aws_mumbai_2023_all.csv
  Required instances: 17

📋 Column mapping:
  Timestamp: 'Time' → 'timestamp'
  Instance: 'InstanceType' → 'instance_type'
  AZ: 'AvailabilityZone' → 'availability_zone'
  Spot Price: 'SpotPrice' → 'spot_price'
  On-Demand Price: 'OndemandPrice' → 'on_demand_price'
✓ Found REAL On-Demand Price column in CSV! (Captures historical changes)

  Rows before filter: 1,243,908
  Rows after filter: 862,341 (69.3%)

✓ Using CSV on-demand prices (complete, no gaps)

✓ Loaded: 862,341 rows
  Memory: 42.3 MB
```

**Interpretation**: CSV has perfect on-demand price data. Model uses historical prices.

---

### Example 2: CSV with Gaps (Scenario C)
```
📂 Loading training data...
  File: aws_mumbai_2023_all.csv
  Required instances: 17

📋 Column mapping:
  Timestamp: 'Time' → 'timestamp'
  Instance: 'InstanceType' → 'instance_type'
  AZ: 'AvailabilityZone' → 'availability_zone'
  Spot Price: 'SpotPrice' → 'spot_price'
  On-Demand Price: 'OndemandPrice' → 'on_demand_price'
✓ Found REAL On-Demand Price column in CSV! (Captures historical changes)

  Rows before filter: 1,243,908
  Rows after filter: 862,341 (69.3%)

🔧 Patching 12,456 missing on-demand prices using CONFIG dictionary

✓ Loaded: 862,341 rows
  Memory: 42.3 MB
```

**Interpretation**: CSV has on-demand prices but 12,456 rows were missing (NaN or zero). Model patched gaps with CONFIG dictionary.

---

### Example 3: Legacy CSV (Scenario B)
```
📂 Loading training data...
  File: aws_mumbai_2023_all.csv
  Required instances: 17

📋 Column mapping:
  Timestamp: 'Time' → 'timestamp'
  Instance: 'InstanceType' → 'instance_type'
  AZ: 'AvailabilityZone' → 'availability_zone'
  Spot Price: 'SpotPrice' → 'spot_price'
  On-Demand Price: NOT FOUND
⚠️ On-Demand Price column MISSING. Will use Static Dictionary.

  Rows before filter: 1,243,908
  Rows after filter: 862,341 (69.3%)

ℹ️ Using Static CONFIG Dictionary for On-Demand prices (CSV column missing)

✓ Loaded: 862,341 rows
  Memory: 42.3 MB
```

**Interpretation**: CSV doesn't have on-demand prices. Model uses static 2024 prices from CONFIG.

---

### Example 4: Unknown Instance Type (Safety Net)
```
📂 Loading training data...
  File: aws_mumbai_2024_all.csv
  Required instances: 17

📋 Column mapping:
  ...
  On-Demand Price: NOT FOUND
⚠️ On-Demand Price column MISSING. Will use Static Dictionary.

  Rows before filter: 1,243,908
  Rows after filter: 862,341 (69.3%)

ℹ️ Using Static CONFIG Dictionary for On-Demand prices (CSV column missing)

⚠️ 142 rows still missing OD price (instance type not in CONFIG)
   Using spot*4.0 fallback for these rows

✓ Loaded: 862,341 rows
  Memory: 42.3 MB
```

**Interpretation**: CSV doesn't have on-demand prices, AND 142 rows have instance types not in CONFIG (e.g., new AWS instance type). Model uses `spot*4` fallback for those rows.

---

## 🎓 Why This Matters

### Historical Accuracy

AWS occasionally adjusts on-demand prices:

**Example**:
- **Jan 2024**: `c5.large` on-demand = `$0.096`
- **Dec 2024**: `c5.large` on-demand = `$0.090` (6% reduction!)

**Old approach**: Uses `$0.096` for all 2024 data (static dictionary)
**New approach**: Uses `$0.096` for Jan, `$0.090` for Dec (CSV truth)

**Impact on discount_depth**:
```
Spot price: $0.030

Old (static $0.096):
  discount_depth = 1 - (0.030 / 0.096) = 0.688 (68.8% savings)

New (dynamic $0.090 in Dec):
  discount_depth = 1 - (0.030 / 0.090) = 0.667 (66.7% savings)

Difference: 2.1 percentage points!
```

This affects the `stress_x_discount` interaction feature, which uses `discount_depth` to calculate economic buffer.

---

### Robustness

**Old approach**: Crashes if CONFIG is missing an instance type
**New approach**: 3 fallbacks prevent crashes:
1. CSV column (if available)
2. CONFIG dictionary (if available)
3. `spot*4` (always works)

---

## 🚀 How to Use

### If Your CSV Has On-Demand Price Column

**No action needed!** The code will automatically:
1. Detect the column (works with various names: `ondemandprice`, `on_demand_price`, `od_price`)
2. Use it for on-demand prices
3. Patch any gaps with CONFIG dictionary
4. Report status during load

---

### If Your CSV Doesn't Have On-Demand Price Column

**No action needed!** The code will automatically:
1. Detect that the column is missing
2. Use CONFIG dictionary for all on-demand prices
3. Report status during load

---

### If You Want to Verify Which Mode Is Active

Look for these messages in the output:

**CSV column found**:
```
✓ Found REAL On-Demand Price column in CSV! (Captures historical changes)
✓ Using CSV on-demand prices (complete, no gaps)
```

**CSV column missing**:
```
⚠️ On-Demand Price column MISSING. Will use Static Dictionary.
ℹ️ Using Static CONFIG Dictionary for On-Demand prices (CSV column missing)
```

**CSV column found with gaps**:
```
✓ Found REAL On-Demand Price column in CSV! (Captures historical changes)
🔧 Patching 1,234 missing on-demand prices using CONFIG dictionary
```

---

## 🔍 Troubleshooting

### Q: I have on-demand prices in my CSV but it says "NOT FOUND"

**A**: Check your column name. Supported variations:
- `ondemandprice`, `OndemandPrice`, `ONDEMANDPRICE`
- `on_demand_price`, `On_Demand_Price`, `ON_DEMAND_PRICE`
- `od_price`, `OD_Price`, `OD_PRICE`
- `odprice`, `ODPrice`, `ODPRICE`

If your column is named differently (e.g., `fixed_price`), rename it to one of the above.

---

### Q: It says "Using CSV on-demand prices" but my discount_depth looks wrong

**A**: Check your CSV data:
```python
# Quick check
import pandas as pd
df = pd.read_csv('aws_mumbai_2023_all.csv')

print(df[['InstanceType', 'OndemandPrice']].head(20))
print(df['OndemandPrice'].describe())
```

Look for:
- **All zeros**: Your CSV has the column but it's empty
- **Same value for all instances**: Your CSV might have a data quality issue
- **NaN values**: Your CSV has gaps (will be patched automatically)

---

### Q: Performance impact?

**A**: Negligible!
- Column detection: Happens once per chunk (first chunk only for verbose output)
- Dictionary lookup: O(1) operation (hash map)
- Memory: No additional memory (column already in CSV or created from dictionary)

---

## 📊 Summary Table

| Scenario | CSV Column? | Gaps? | Source | Fallback |
|----------|-------------|-------|--------|----------|
| **A** | ✅ Yes | ❌ No | CSV | N/A |
| **B** | ❌ No | N/A | CONFIG | spot*4 |
| **C** | ✅ Yes | ✅ Yes | CSV + CONFIG | spot*4 |

**Triple Safety Net**:
1. **CSV** (if available, complete)
2. **CONFIG** (if CSV missing or has gaps)
3. **spot*4** (if CONFIG doesn't have instance type)

---

## ✅ Benefits Summary

### Accuracy
- ✅ Captures AWS price changes over time (Jan vs Dec 2024)
- ✅ Uses real historical data when available
- ✅ More accurate `discount_depth` calculation

### Robustness
- ✅ Handles 3 scenarios (perfect CSV, gaps, missing column)
- ✅ Never crashes (triple fallback system)
- ✅ Works with legacy datasets

### Flexibility
- ✅ Detects various column naming conventions
- ✅ No configuration changes needed
- ✅ Automatic mode selection

### Transparency
- ✅ Clear diagnostic messages
- ✅ Reports which mode is active
- ✅ Warns when using fallbacks

---

**Status**: ✅ **IMPLEMENTED AND PUSHED**

Pull the latest code and run - the hybrid logic will automatically activate!

```bash
git pull origin claude/design-agentl-system-01WHZAbcQYmJdWUDHUuSbFQG
cd ml-model
python family_stress_model.py
```

Look for the on-demand price status messages in the output to confirm which mode is active.
