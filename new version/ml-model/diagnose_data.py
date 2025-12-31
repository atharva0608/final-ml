#!/usr/bin/env python3
"""
Data Quality Diagnostic Tool

Checks your CSV files to understand why prices have zero variance.
"""

import pandas as pd
import numpy as np
from pathlib import Path

def diagnose_csv(file_path, name="Data"):
    """Diagnose a CSV file for data quality issues"""

    print(f"\n{'='*80}")
    print(f"DIAGNOSING: {name}")
    print(f"File: {file_path}")
    print(f"{'='*80}\n")

    try:
        # Load sample
        print(f"📂 Loading sample (first 100K rows)...")
        df = pd.read_csv(file_path, nrows=100000)

        print(f"  ✓ Shape: {df.shape}")
        print(f"  ✓ Columns: {list(df.columns)}")

        # Identify timestamp column
        ts_cols = [col for col in df.columns if any(x in col.lower() for x in ['time', 'date'])]
        price_cols = [col for col in df.columns if 'price' in col.lower()]
        instance_cols = [col for col in df.columns if 'instance' in col.lower() or 'type' in col.lower()]

        print(f"\n  Identified columns:")
        print(f"    Timestamp: {ts_cols}")
        print(f"    Price: {price_cols}")
        print(f"    Instance: {instance_cols}")

        if not price_cols:
            print(f"\n  ❌ ERROR: No price column found!")
            return

        price_col = price_cols[0]
        instance_col = instance_cols[0] if instance_cols else None

        # Check price statistics
        print(f"\n📊 Price Statistics (column: '{price_col}'):")
        print(f"  Count: {df[price_col].count():,}")
        print(f"  Mean: ${df[price_col].mean():.6f}")
        print(f"  Std: ${df[price_col].std():.6f}")
        print(f"  Min: ${df[price_col].min():.6f}")
        print(f"  Max: ${df[price_col].max():.6f}")
        print(f"  Range: ${df[price_col].max() - df[price_col].min():.6f}")
        print(f"  Unique values: {df[price_col].nunique():,}")

        # Check if all prices are identical
        if df[price_col].std() < 1e-6:
            print(f"\n  ❌ CRITICAL: All prices are virtually identical!")
            print(f"     Price: ${df[price_col].iloc[0]:.6f}")
            print(f"     This explains why features have zero variance.")
        elif df[price_col].std() < 0.01:
            print(f"\n  ⚠️  WARNING: Very low price variance (std < $0.01)")
        else:
            print(f"\n  ✓ Prices have reasonable variance")

        # Check per instance type
        if instance_col:
            print(f"\n📦 Per-Instance Statistics (column: '{instance_col}'):")
            instance_types = df[instance_col].unique()[:10]  # First 10

            for inst in instance_types:
                inst_prices = df[df[instance_col] == inst][price_col]
                if len(inst_prices) > 0:
                    print(f"  {inst:20s}: n={len(inst_prices):6,} | "
                          f"mean=${inst_prices.mean():.4f} | "
                          f"std=${inst_prices.std():.6f} | "
                          f"range=${inst_prices.max()-inst_prices.min():.6f}")

                    # Flag if no variance
                    if inst_prices.std() < 1e-6:
                        print(f"    ⚠️  ZERO variance - all prices = ${inst_prices.iloc[0]:.6f}")

        # Check time distribution
        if ts_cols:
            ts_col = ts_cols[0]
            print(f"\n⏰ Time Distribution (column: '{ts_col}'):")
            try:
                df[ts_col] = pd.to_datetime(df[ts_col], format='mixed', errors='coerce')
                print(f"  First timestamp: {df[ts_col].min()}")
                print(f"  Last timestamp: {df[ts_col].max()}")
                print(f"  Duration: {df[ts_col].max() - df[ts_col].min()}")
                print(f"  Total rows: {len(df):,}")
            except:
                print(f"  ⚠️  Could not parse timestamps")

        # Check for duplicates
        print(f"\n🔍 Data Quality Checks:")
        if instance_col and ts_cols:
            dups = df.duplicated(subset=[instance_col, ts_cols[0]]).sum()
            print(f"  Duplicate (instance+timestamp): {dups:,} rows ({dups/len(df)*100:.1f}%)")

        nulls = df.isnull().sum().sum()
        print(f"  Null values: {nulls:,}")

        # Sample rows
        print(f"\n📋 Sample Rows (first 10):")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(df.head(10).to_string(index=False))

        # Price distribution
        print(f"\n📊 Price Distribution:")
        print(df[price_col].describe())

        # Check if prices are multiples of something
        if df[price_col].std() > 1e-6:
            # Find smallest non-zero difference
            sorted_prices = np.sort(df[price_col].unique())
            if len(sorted_prices) > 1:
                diffs = np.diff(sorted_prices)
                min_diff = diffs[diffs > 0].min() if len(diffs[diffs > 0]) > 0 else 0
                print(f"  Smallest price increment: ${min_diff:.6f}")

        # Check for suspicious patterns
        print(f"\n🔍 Suspicious Patterns:")
        unique_prices = df[price_col].nunique()
        if unique_prices == 1:
            print(f"  ❌ ALL prices are identical: ${df[price_col].iloc[0]:.6f}")
            print(f"     This is a DATA QUALITY ISSUE!")
        elif unique_prices < 10:
            print(f"  ⚠️  Only {unique_prices} unique prices (suspiciously low)")
            print(f"     Unique values: {sorted(df[price_col].unique())}")
        else:
            print(f"  ✓ {unique_prices:,} unique prices (normal)")

    except FileNotFoundError:
        print(f"\n❌ ERROR: File not found!")
        print(f"   Expected: {file_path}")
        print(f"\n   Please update file paths in this script or in family_stress_model.py")
        print(f"   Line 44-45 in family_stress_model.py")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run diagnostics on training and test data"""

    print("\n" + "="*80)
    print("AWS SPOT DATA QUALITY DIAGNOSTIC TOOL")
    print("="*80)
    print("\nThis tool checks your CSV files for data quality issues.")
    print("It will help identify why features have zero variance.\n")

    # Update these paths to match your data location
    training_file = '/Users/atharvapudale/Downloads/aws_mumbai_2023_all.csv'
    test_file = '/Users/atharvapudale/Downloads/aws_mumbai_2024_all.csv'

    # Diagnose training data
    diagnose_csv(training_file, "Training Data (2023)")

    # Diagnose test data
    diagnose_csv(test_file, "Test Data (2024)")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY & RECOMMENDATIONS")
    print("="*80)
    print("""
If you see "ZERO variance" or "all prices identical":

  1. Check your data source:
     - Are you pulling from the right AWS region?
     - Is the data filtered/aggregated incorrectly?
     - Does the time period have market activity?

  2. Common causes:
     - Data export included only on-demand prices (not spot)
     - Time period when spot instances were not available
     - Data aggregated to daily averages (removes variance)
     - Wrong column being read as price

  3. Solutions:
     - Re-export data from AWS Spot Price History
     - Use a different time period (2022 or 2025)
     - Check that you're using spot_price column (not on_demand)
     - Verify data has 10-minute granularity (not hourly/daily)

If you see "reasonable variance":
  - Data is good!
  - Model should train successfully
  - Check that feature engineering is working correctly
    """)

    print(f"\nDiagnostics complete! Review output above for issues.\n")


if __name__ == "__main__":
    main()
