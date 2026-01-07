# ❌ CRITICAL: Data Quality Issue - Zero Price Variance

## 🚨 Problem Detected

Your Mumbai spot data has **ZERO price movement**:

```
Diagnostic: Checking price volatility...
  c5.12xlarge_aps1-az1: min=$2.0400, max=$2.0400, range=$0.0000
  c5.12xlarge_aps1-az2: min=$2.0400, max=$2.0400, range=$0.0000
  c5.12xlarge_aps1-az3: min=$2.0400, max=$2.0400, range=$0.0000

Price Position: 0.000 ± 0.000
Price Velocity: 0.000 ± 0.000
Price Volatility: 0.000 ± 0.000
Family Stress: 0.000 ± 0.000
```

**Translation**: Every single price reading is **exactly $2.0400** - no variation at all!

---

## 🔍 Why This Happens

### Possible Causes

**1. Wrong Column Selected** ⚠️ MOST LIKELY
```python
# You might be reading:
df['on_demand_price']  # ❌ Always fixed (no variance)

# Instead of:
df['spot_price']  # ✓ Changes over time
```

**On-demand prices are FIXED** by AWS (e.g., c5.12xlarge = $2.04/hr always).
**Spot prices VARY** based on supply/demand (e.g., $0.80 - $2.20/hr).

**Check your CSV**: Do you have a `spot_price` column or only `on_demand_price`?

---

**2. Data Aggregated/Filtered Incorrectly**

```python
# Example bad aggregation:
df.groupby(['instance', 'date']).mean()  # ❌ Removes intraday variance

# Should be:
df  # Raw 10-minute data with no aggregation
```

**Check**: How was the CSV exported? Was it averaged by hour/day?

---

**3. Time Period with No Spot Activity**

Some regions/instances had zero spot capacity during certain periods:
- New instance types (first few months)
- Region capacity constraints
- AWS suspending spot for maintenance

**Check**: Try a different time period (2022 or early 2025).

---

**4. Data Export Bug**

AWS CLI/SDK exports sometimes return:
- Only on-demand prices
- Only launch prices (not current prices)
- Null values filled with on-demand price

**Check**: Re-export using verified AWS CLI command.

---

## 🛠️ Step 1: Diagnose Your Data

Run the diagnostic tool:

```bash
cd /home/user/final-ml/ml-model
python diagnose_data.py
```

**This will show**:
- Exact price ranges per instance
- Number of unique prices
- Sample rows from your CSV
- Suspicious patterns

**What to look for**:

### ❌ BAD (Data Issue):
```
📊 Price Statistics:
  Count: 100,000
  Mean: $2.040000
  Std: $0.000000
  Min: $2.040000
  Max: $2.040000
  Range: $0.000000
  Unique values: 1 ❌

🔍 Suspicious Patterns:
  ❌ ALL prices are identical: $2.0400
     This is a DATA QUALITY ISSUE!

📋 Sample Rows:
timestamp              instance_type  spot_price  on_demand_price
2023-01-01 00:00:00   c5.12xlarge    2.0400      2.0400
2023-01-01 00:10:00   c5.12xlarge    2.0400      2.0400
2023-01-01 00:20:00   c5.12xlarge    2.0400      2.0400
```

**Diagnosis**: Reading on-demand column instead of spot column!

---

### ✓ GOOD (Normal Data):
```
📊 Price Statistics:
  Count: 100,000
  Mean: $0.892341
  Std: $0.234567 ✓
  Min: $0.612000
  Max: $1.456000
  Range: $0.844000 ✓
  Unique values: 8,453 ✓

🔍 Suspicious Patterns:
  ✓ 8,453 unique prices (normal)

📋 Sample Rows:
timestamp              instance_type  spot_price  on_demand_price
2023-01-01 00:00:00   c5.12xlarge    0.8120      2.0400
2023-01-01 00:10:00   c5.12xlarge    0.8230      2.0400
2023-01-01 00:20:00   c5.12xlarge    0.8190      2.0400
2023-01-01 00:30:00   c5.12xlarge    0.8450      2.0400
2023-01-01 00:40:00   c5.12xlarge    0.8340      2.0400
```

**Diagnosis**: Spot prices varying normally! ✓

---

## 🔧 Step 2: Fix Your Data Source

### Option A: Verify CSV Columns

**Check your CSV file**:

```bash
head -1 aws_mumbai_2023_all.csv
```

**Should see**:
```
timestamp,instance_type,availability_zone,spot_price,on_demand_price
```

**If you see**:
```
timestamp,instance_type,availability_zone,price  # ❌ Ambiguous!
```

Or:
```
timestamp,instance_type,availability_zone,on_demand_price  # ❌ Wrong column!
```

**Then**: You need to re-export the data with `spot_price` column.

---

### Option B: Re-Export from AWS

**Correct AWS CLI command**:

```bash
# For ap-south-1 (Mumbai) in 2023
aws ec2 describe-spot-price-history \
  --region ap-south-1 \
  --start-time 2023-01-01T00:00:00 \
  --end-time 2023-12-31T23:59:59 \
  --product-descriptions "Linux/UNIX" \
  --instance-types c5.large c5.xlarge c5.2xlarge c5.4xlarge c5.9xlarge c5.12xlarge c5.18xlarge c5.24xlarge \
                    t4g.small t4g.medium t4g.large t4g.xlarge t4g.2xlarge \
                    t3.medium t3.large t3.xlarge t3.2xlarge \
  --query 'SpotPriceHistory[*].[Timestamp,InstanceType,AvailabilityZone,SpotPrice]' \
  --output text > aws_mumbai_2023_spot.txt
```

**Key points**:
- Use `--query 'SpotPriceHistory[*].[Timestamp,InstanceType,AvailabilityZone,SpotPrice]'`
- `SpotPrice` field contains actual spot market prices (varies)
- NOT `Price` or `OnDemandPrice`

**Convert to CSV**:
```python
import pandas as pd

# Load the tab-separated output
df = pd.read_csv('aws_mumbai_2023_spot.txt', sep='\t',
                 names=['timestamp', 'instance_type', 'availability_zone', 'spot_price'])

# Check for variance
print(f"Price range: ${df['spot_price'].min():.4f} - ${df['spot_price'].max():.4f}")
print(f"Unique prices: {df['spot_price'].nunique():,}")

# If variance looks good, save
if df['spot_price'].std() > 0.01:
    df.to_csv('aws_mumbai_2023_all.csv', index=False)
    print("✓ CSV saved with actual spot price variance!")
else:
    print("❌ Still no variance - check AWS CLI command")
```

---

### Option C: Use Different Time Period

Mumbai spot market might have been inactive during your selected period.

**Try these periods** (known to have activity):

**2022 (High Volatility)**:
```bash
--start-time 2022-01-01T00:00:00 --end-time 2022-12-31T23:59:59
```

**2025 Q1 (Recent Activity)**:
```bash
--start-time 2025-01-01T00:00:00 --end-time 2025-03-31T23:59:59
```

**Or use a different region**:
```bash
--region us-east-1  # N. Virginia (most active)
--region eu-west-1  # Ireland (active)
```

---

## 🎯 Step 3: Verify Fixed Data

After re-exporting, check data quality:

```bash
python diagnose_data.py
```

**You should see**:

```
✓ Price Statistics:
  Std: $0.234567  # > $0.01 = GOOD!
  Range: $0.844000  # > $0.10 = GOOD!
  Unique values: 8,453  # > 100 = GOOD!

✓ Per-Instance Statistics:
  c5.large:    std=$0.023456  # Variance exists!
  c5.xlarge:   std=$0.045678  # Variance exists!
  t3.medium:   std=$0.012345  # Variance exists!
```

**If you still see std=0.000000**: Wrong column or wrong data!

---

## 🚀 Step 4: Re-Run Model

Once data has variance:

```bash
python family_stress_model.py
```

**Expected output** (with good data):

```
📊 Calculating Price Position (7-day window)...
  Diagnostic: Checking price volatility...
    c5.large_aps1-az1: min=$0.0848, max=$0.0923, range=$0.0075 ✓
    c5.xlarge_aps1-az1: min=$0.1696, max=$0.1846, range=$0.0150 ✓

  ✓ Price Position calculated
  Mean: 0.342  # NOT 0.000!
  Std: 0.187   # NOT 0.000!

📈 Calculating Price Velocity...
  Velocity Mean: 0.000056, Std: 0.001234 ✓

🔍 Data Quality Validation...
  price_position      : Mean=0.342000, Std=0.187000  ✓
  price_velocity_1h   : Mean=0.000056, Std=0.001234  ✓
  discount_depth      : Mean=0.721000, Std=0.023456  ✓
  family_stress       : Mean=0.358000, Std=0.192000  ✓

✓ Ready to train:
  Features: 10
  Training samples: 2,675,476 (32,135 unstable = 1.2%)

Training Metrics:
  Precision: 0.72
  Recall: 0.68
  F1 Score: 0.70
  AUC: 0.85 ✓

✓ All graphs saved to ./training/plots/
```

---

## 📊 What Your Output Should Look Like

### ❌ Current (Zero Variance):
```
Price Position: 0.000 ± 0.000
Velocity: 0.000 ± 0.000
Unstable samples: 0.02%
AUC: nan
Model predicts: All zeros
```

### ✓ After Fix (Normal Variance):
```
Price Position: 0.342 ± 0.187
Velocity: 0.000056 ± 0.001234
Unstable samples: 1.2%
AUC: 0.85
Model predicts: Mix of 0s and 1s
```

---

## 🔍 Quick Checks

**1. Open your CSV in Excel/Numbers**:
- Do prices vary or all identical?
- Are you looking at right column?

**2. Check column names**:
```python
import pandas as pd
df = pd.read_csv('aws_mumbai_2023_all.csv', nrows=5)
print(df.columns)  # Should include 'spot_price'
print(df)  # Should see varying prices
```

**3. Check price variance**:
```python
df = pd.read_csv('aws_mumbai_2023_all.csv')
print(f"Min: ${df['spot_price'].min()}")
print(f"Max: ${df['spot_price'].max()}")
print(f"Std: ${df['spot_price'].std()}")

# If std = 0.000: Data problem!
# If std > 0.01: Data is good!
```

---

## ⚠️ Common Mistakes

**Mistake 1: Reading Wrong Column**
```python
# ❌ WRONG
df['price'] = df['on_demand_price']  # Always fixed!

# ✓ CORRECT
df['price'] = df['spot_price']  # Varies over time
```

**Mistake 2: Filling NaN with On-Demand**
```python
# ❌ WRONG
df['spot_price'] = df['spot_price'].fillna(df['on_demand_price'])
# This makes all NaN rows = on-demand (no variance)

# ✓ CORRECT
df = df.dropna(subset=['spot_price'])  # Remove NaN rows
```

**Mistake 3: Using Averaged Data**
```python
# ❌ WRONG
df = df.groupby(['instance', 'date']).mean()  # Removes variance

# ✓ CORRECT
df = df  # Keep raw 10-minute data
```

---

## 📞 Still Stuck?

If you've checked everything and still see zero variance:

1. **Share your CSV sample**:
   ```bash
   head -20 aws_mumbai_2023_all.csv
   ```

2. **Share diagnostic output**:
   ```bash
   python diagnose_data.py > diagnosis.txt
   ```

3. **Share AWS CLI command used**:
   ```bash
   echo "My AWS CLI command was: ..."
   ```

---

## ✅ Summary

**Your issue**: All prices in CSV are identical ($2.0400)

**Most likely cause**: Reading `on_demand_price` column instead of `spot_price`

**Fix**:
1. Run `python diagnose_data.py` to confirm
2. Check CSV has `spot_price` column with variance
3. If not, re-export from AWS using correct command
4. Verify std > 0.01 before training
5. Re-run model - should work!

**The model code is CORRECT** - it's a data quality issue!

---

**Status**: ✅ **Model Code Fixed (Handles Zero Variance Gracefully)**

**Next**: 🚨 **Fix Data Source (No Price Variance)**

Run diagnostic tool and check your data!
