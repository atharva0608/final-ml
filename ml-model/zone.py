import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
import os
from datetime import timedelta, datetime
from matplotlib.patches import Rectangle, Patch
from scipy import stats

warnings.filterwarnings('ignore')
sns.set_style('whitegrid')

# ============================================================================
# IMPROVED CONFIGURATION
# ============================================================================
CONFIG = {
    'files': [
        '/Users/atharvapudale/Downloads/aws_2023_2024_complete_24months.csv',
        '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(1-2-3-25).csv',
        '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(4-5-6-25).csv',
        '/Users/atharvapudale/Downloads/mumbai_spot_data_sorted_asc(7-8-9-25).csv'
    ],
    'target_instances': ['t3.medium', 't4g.medium', 'c5.large', 't4g.small'],
    'region_filter': 'ap-south-1',
    'output_dir': 'output_enhanced_zones/',
    
    'analysis_year': 2024,
    
    # ZONE CALCULATIONS (ANNUAL - Relative to pool history)
    'green_percentile': 70,      
    'yellow_percentile': 90,     
    'orange_percentile': 95,     
    'green_window_days': 365,    
    'yellow_window_days': 548,   
    'orange_window_days': 730,   
    'red_window_years': 3,       
    
    # VOLATILITY DETECTION (QUARTERLY - Seasonal patterns)
    'volatility_quarterly': True,              # NEW: Calculate per quarter
    'volatility_window_hours': 6,              
    'volatility_threshold_sigma': 2.5,         
    'min_volatile_duration_hours': 1,          
    'volatility_merge_gap_hours': 2,           
    
    # DATA QUALITY
    'min_data_points': 100,                 
    'outlier_iqr_multiplier': 3,            
}

Path(CONFIG['output_dir']).mkdir(parents=True, exist_ok=True)

# ============================================================================
# DATA LOADING (Same as before)
# ============================================================================
def load_and_clean_data(files, targets):
    """Load and clean spot price data with robust outlier removal"""
    print("📊 Loading spot price data...")
    dfs = []
    
    for f in files:
        if not os.path.exists(f):
            print(f"   ⚠️  File not found: {Path(f).name}")
            continue
        try:
            df = pd.read_csv(f)
            df.columns = [c.lower().replace('_', '').replace(' ', '') for c in df.columns]
            
            col_map = {}
            for col in df.columns:
                if 'spotprice' in col or col == 'price':
                    col_map[col] = 'SpotPrice'
                elif 'instancetype' in col:
                    col_map[col] = 'InstanceType'
                elif 'zone' in col or col == 'az':
                    col_map[col] = 'AvailabilityZone'
                elif 'time' in col or 'date' in col:
                    col_map[col] = 'Timestamp'
            
            df = df.rename(columns=col_map)
            required = ['Timestamp', 'InstanceType', 'AvailabilityZone', 'SpotPrice']
            if not all(c in df.columns for c in required):
                continue
            
            df = df[df['InstanceType'].isin(targets)]
            if 'Region' in df.columns:
                df = df[df['Region'] == CONFIG['region_filter']]
            
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True).dt.tz_localize(None)
            df['SpotPrice'] = pd.to_numeric(df['SpotPrice'], errors='coerce').abs()
            df = df[df['SpotPrice'] > 0]
            
            Q1, Q3 = df['SpotPrice'].quantile([0.25, 0.75])
            IQR = Q3 - Q1
            upper_bound = Q3 + CONFIG['outlier_iqr_multiplier'] * IQR
            df = df[df['SpotPrice'] <= upper_bound]
            df = df.dropna(subset=['SpotPrice'])
            dfs.append(df)
            print(f"   ✅ Loaded {Path(f).name}: {len(df):,} rows")
            
        except Exception as e:
            print(f"   ❌ Error loading {Path(f).name}: {e}")
    
    if not dfs:
        raise ValueError("No data loaded successfully!")
    
    full_df = pd.concat(dfs, ignore_index=True)
    full_df = full_df.sort_values('Timestamp').drop_duplicates()
    full_df['PoolID'] = full_df['InstanceType'] + "_" + full_df['AvailabilityZone']
    
    print(f"\n✅ Total loaded: {len(full_df):,} rows")
    print(f"   Date range: {full_df['Timestamp'].min().date()} → {full_df['Timestamp'].max().date()}\n")
    
    return full_df

# ============================================================================
# ZONE CALCULATION (ANNUAL - Same as before)
# ============================================================================
def calculate_enhanced_zones(df, analysis_year):
    """Calculate zones using research-backed percentile methodology"""
    
    print("=" * 80)
    print("ZONE CALCULATION (Annual - Relative to Pool History)")
    print("=" * 80 + "\n")
    
    zones_dict = {}
    analysis_end = datetime(analysis_year, 12, 31)
    
    for pool in sorted(df['PoolID'].unique()):
        pool_data = df[df['PoolID'] == pool].copy()
        
        if len(pool_data) < CONFIG['min_data_points']:
            continue
        
        year_data = pool_data[pool_data['Timestamp'].dt.year == analysis_year]
        if len(year_data) < CONFIG['min_data_points']:
            continue
        
        # GREEN ZONE: P70 from 12-month window
        green_start = analysis_end - timedelta(days=CONFIG['green_window_days'])
        green_data = pool_data[(pool_data['Timestamp'] >= green_start) & 
                               (pool_data['Timestamp'] <= analysis_end)]
        if len(green_data) < 50:
            green_data = year_data
        green_upper = green_data['SpotPrice'].quantile(CONFIG['green_percentile'] / 100)
        
        # YELLOW ZONE: P90 from 18-month window
        yellow_start = analysis_end - timedelta(days=CONFIG['yellow_window_days'])
        yellow_data = pool_data[(pool_data['Timestamp'] >= yellow_start) & 
                                (pool_data['Timestamp'] <= analysis_end)]
        if len(yellow_data) < 50:
            yellow_data = year_data
        yellow_upper = yellow_data['SpotPrice'].quantile(CONFIG['yellow_percentile'] / 100)
        
        # ORANGE ZONE: P95 from 24-month window
        orange_start = analysis_end - timedelta(days=CONFIG['orange_window_days'])
        orange_data = pool_data[(pool_data['Timestamp'] >= orange_start) & 
                                (pool_data['Timestamp'] <= analysis_end)]
        if len(orange_data) < 50:
            orange_data = year_data
        orange_upper = orange_data['SpotPrice'].quantile(CONFIG['orange_percentile'] / 100)
        
        # RED ZONE: Historical max + 10% buffer
        red_start = analysis_end - timedelta(days=CONFIG['red_window_years'] * 365)
        red_data = pool_data[(pool_data['Timestamp'] >= red_start) & 
                            (pool_data['Timestamp'] <= analysis_end)]
        if len(red_data) < 50:
            red_data = pool_data
        red_upper = red_data['SpotPrice'].max() * 1.10
        
        # Ensure monotonic boundaries
        if yellow_upper <= green_upper:
            yellow_upper = green_upper * 1.15
        if orange_upper <= yellow_upper:
            orange_upper = yellow_upper * 1.10
        if red_upper <= orange_upper:
            red_upper = orange_upper * 1.10
        
        # Calculate distribution
        prices = year_data['SpotPrice']
        in_green = (prices <= green_upper).sum()
        in_yellow = ((prices > green_upper) & (prices <= yellow_upper)).sum()
        in_orange = ((prices > yellow_upper) & (prices <= orange_upper)).sum()
        in_red = (prices > orange_upper).sum()
        total = len(prices)
        
        mean_price = prices.mean()
        cv = (prices.std() / mean_price) * 100
        
        zones_dict[pool] = {
            'green_upper': green_upper,
            'yellow_upper': yellow_upper,
            'orange_upper': orange_upper,
            'red_upper': red_upper,
            'year_min': prices.min(),
            'year_max': prices.max(),
            'year_mean': mean_price,
            'year_median': prices.median(),
            'year_std': prices.std(),
            'cv_percent': cv,
            'in_green_pct': (in_green / total) * 100,
            'in_yellow_pct': (in_yellow / total) * 100,
            'in_orange_pct': (in_orange / total) * 100,
            'in_red_pct': (in_red / total) * 100,
        }
        
        print(f"   {pool}: Green={zones_dict[pool]['in_green_pct']:.1f}% | CV={cv:.1f}%")
    
    print()
    return zones_dict

# ============================================================================
# QUARTERLY VOLATILITY DETECTION (NEW!)
# ============================================================================
def detect_quarterly_volatility(pool_data, analysis_year):
    """
    Detect volatility QUARTERLY instead of annually
    This captures seasonal infrastructure changes better
    """
    df = pool_data.copy().sort_values('Timestamp')
    year_data = df[df['Timestamp'].dt.year == analysis_year].copy()
    
    if len(year_data) < 100:
        year_data['Is_Volatile'] = False
        year_data['Volatile_Group'] = 0
        year_data['Quarter'] = 0
        return year_data
    
    # Define quarters
    quarters = [
        (1, datetime(analysis_year, 1, 1), datetime(analysis_year, 3, 31)),   # Q1
        (2, datetime(analysis_year, 4, 1), datetime(analysis_year, 6, 30)),   # Q2
        (3, datetime(analysis_year, 7, 1), datetime(analysis_year, 9, 30)),   # Q3
        (4, datetime(analysis_year, 10, 1), datetime(analysis_year, 12, 31)), # Q4
    ]
    
    year_data['Is_Volatile'] = False
    year_data['Volatile_Group'] = 0
    year_data['Quarter'] = 0
    
    window_size = int(CONFIG['volatility_window_hours'] * 6)  # 6 records per hour
    global_group_id = 1
    
    for q_num, q_start, q_end in quarters:
        quarter_data = year_data[
            (year_data['Timestamp'] >= q_start) & 
            (year_data['Timestamp'] <= q_end)
        ].copy()
        
        if len(quarter_data) < window_size:
            continue
        
        # Calculate rolling std dev for this quarter
        quarter_data['Rolling_StdDev'] = quarter_data['SpotPrice'].rolling(
            window=window_size,
            min_periods=window_size // 2
        ).std()
        
        # Establish baseline from green zone prices IN THIS QUARTER
        green_threshold = quarter_data['SpotPrice'].quantile(0.70)
        baseline_data = quarter_data[quarter_data['SpotPrice'] <= green_threshold]
        
        if len(baseline_data) < window_size:
            continue
        
        # Calculate quarterly baseline volatility
        baseline_std = baseline_data['Rolling_StdDev'].mean()
        baseline_sigma = baseline_data['Rolling_StdDev'].std()
        volatility_threshold = baseline_std + (CONFIG['volatility_threshold_sigma'] * baseline_sigma)
        
        # Mark volatile periods
        quarter_data['Is_Volatile'] = (
            (quarter_data['SpotPrice'] <= green_threshold) & 
            (quarter_data['Rolling_StdDev'] > volatility_threshold) &
            (quarter_data['Rolling_StdDev'].notna())
        )
        
        # Group consecutive volatile periods
        quarter_data = group_volatile_periods_quarterly(quarter_data, global_group_id)
        global_group_id = quarter_data['Volatile_Group'].max() + 1
        
        # Mark quarter number
        quarter_data['Quarter'] = q_num
        
        # Update main dataframe
        year_data.loc[quarter_data.index, 'Is_Volatile'] = quarter_data['Is_Volatile']
        year_data.loc[quarter_data.index, 'Volatile_Group'] = quarter_data['Volatile_Group']
        year_data.loc[quarter_data.index, 'Quarter'] = q_num
        year_data.loc[quarter_data.index, 'Rolling_StdDev'] = quarter_data['Rolling_StdDev']
    
    return year_data

def group_volatile_periods_quarterly(df, start_group_id):
    """Group consecutive volatile points"""
    min_records = int(CONFIG['min_volatile_duration_hours'] * 6)
    merge_gap = timedelta(hours=CONFIG['volatility_merge_gap_hours'])
    
    df['Volatile_Group'] = 0
    
    if not df['Is_Volatile'].any():
        return df
    
    volatile_indices = df[df['Is_Volatile']].index.tolist()
    
    if len(volatile_indices) < min_records:
        df['Is_Volatile'] = False
        return df
    
    group_id = start_group_id
    current_group = [volatile_indices[0]]
    
    for i in range(1, len(volatile_indices)):
        curr_idx = volatile_indices[i]
        prev_idx = volatile_indices[i-1]
        
        time_gap = df.loc[curr_idx, 'Timestamp'] - df.loc[prev_idx, 'Timestamp']
        
        if time_gap <= merge_gap:
            current_group.append(curr_idx)
        else:
            if len(current_group) >= min_records:
                df.loc[current_group, 'Volatile_Group'] = group_id
                group_id += 1
            current_group = [curr_idx]
    
    if len(current_group) >= min_records:
        df.loc[current_group, 'Volatile_Group'] = group_id
    
    df['Is_Volatile'] = df['Volatile_Group'] > 0
    return df

# ============================================================================
# ENHANCED VISUALIZATION WITH ZOOMED VOLATILITY
# ============================================================================
def create_enhanced_plot_quarterly(pool_data, pool, zones, analysis_year):
    """Create plot with quarterly volatility and zoomed views"""
    
    year_data = pool_data[pool_data['Timestamp'].dt.year == analysis_year].copy()
    
    if len(year_data) < CONFIG['min_data_points']:
        return
    
    # Detect quarterly volatility
    year_data = detect_quarterly_volatility(year_data, analysis_year)
    
    vol_count = year_data['Is_Volatile'].sum()
    vol_pct = (vol_count / len(year_data)) * 100
    num_periods = year_data['Volatile_Group'].max()
    
    print(f"   📊 {pool}")
    print(f"      Quarterly Volatility: {vol_pct:.2f}% | Periods: {int(num_periods)}")
    print(f"      CV: {zones['cv_percent']:.1f}% | Mean: ${zones['year_mean']:.5f}")
    
    # Create main figure
    fig = plt.figure(figsize=(24, 16))
    gs = fig.add_gridspec(3, 1, height_ratios=[3.5, 1, 1.5], hspace=0.3)
    
    ax1 = fig.add_subplot(gs[0, 0])  # Price chart
    ax2 = fig.add_subplot(gs[1, 0])  # Volatility indicator
    ax3 = fig.add_subplot(gs[2, 0])  # Zoomed volatility view
    
    y_max = zones['red_upper'] * 1.05
    
    # --- MAIN PRICE CHART ---
    ax1.fill_between(year_data['Timestamp'], 0, zones['green_upper'],
                     color='#27ae60', alpha=0.20,
                     label=f'🟢 SAFE (P0-P70): <${zones["green_upper"]:.5f}', zorder=1)
    
    ax1.fill_between(year_data['Timestamp'], zones['green_upper'], zones['yellow_upper'],
                     color='#f39c12', alpha=0.25,
                     label=f'🟡 ELEVATED (P70-P90): ${zones["green_upper"]:.5f}-${zones["yellow_upper"]:.5f}', zorder=1)
    
    ax1.fill_between(year_data['Timestamp'], zones['yellow_upper'], zones['orange_upper'],
                     color='#e67e22', alpha=0.30,
                     label=f'🟠 HIGH RISK (P90-P95): ${zones["yellow_upper"]:.5f}-${zones["orange_upper"]:.5f}', zorder=1)
    
    ax1.fill_between(year_data['Timestamp'], zones['orange_upper'], zones['red_upper'],
                     color='#c0392b', alpha=0.35,
                     label=f'🔴 CRITICAL (P95+): >${zones["orange_upper"]:.5f}', zorder=1)
    
    # Purple volatility boxes
    volatile_data = year_data[year_data['Is_Volatile']]
    if len(volatile_data) > 0:
        for group_id in volatile_data['Volatile_Group'].unique():
            if group_id == 0:
                continue
            
            group = volatile_data[volatile_data['Volatile_Group'] == group_id]
            start = group['Timestamp'].min()
            end = group['Timestamp'].max()
            duration_h = (end - start).total_seconds() / 3600
            quarter = group['Quarter'].iloc[0]
            
            rect = Rectangle((start, 0), end - start, zones['green_upper'],
                           facecolor='#9b59b6', alpha=0.35,
                           edgecolor='#8e44ad', linewidth=2.5, zorder=4)
            ax1.add_patch(rect)
            
            if duration_h >= 1:
                mid = start + (end - start) / 2
                ax1.text(mid, zones['green_upper'] * 0.35,
                        f"⚡{duration_h:.1f}h\nQ{quarter}",
                        ha='center', va='center', fontsize=8, fontweight='bold',
                        color='white',
                        bbox=dict(boxstyle='round,pad=0.5', facecolor='#8e44ad',
                                alpha=0.9, edgecolor='white', linewidth=1.5), zorder=6)
    
    ax1.plot(year_data['Timestamp'], year_data['SpotPrice'],
            linewidth=1.8, color='#2c3e50', alpha=0.85, label='Spot Price', zorder=5)
    
    ax1.axhline(zones['year_median'], color='#16a085', linewidth=2.5,
               linestyle=':', alpha=0.8, label=f'Median: ${zones["year_median"]:.5f}', zorder=7)
    
    ax1.axhline(zones['year_mean'], color='#2980b9', linewidth=2.5,
               linestyle='--', alpha=0.8, label=f'Mean: ${zones["year_mean"]:.5f}', zorder=7)
    
    handles, labels = ax1.get_legend_handles_labels()
    handles.append(Patch(facecolor='#9b59b6', alpha=0.5, edgecolor='#8e44ad', linewidth=2,
                        label='⚡ Abnormal Volatility (Quarterly)'))
    ax1.legend(handles=handles, loc='upper left', fontsize=10, ncol=2,
              framealpha=0.95, edgecolor='gray', shadow=True)
    
    ax1.set_ylim(0, y_max)
    ax1.set_ylabel('Spot Price (USD)', fontsize=14, fontweight='bold')
    ax1.set_title(
        f'{pool} - Year {analysis_year} Enhanced Analysis (Quarterly Volatility)\n' +
        f'Green: {zones["in_green_pct"]:.1f}% | Yellow: {zones["in_yellow_pct"]:.1f}% | ' +
        f'Orange: {zones["in_orange_pct"]:.1f}% | Red: {zones["in_red_pct"]:.1f}% | ' +
        f'⚡Volatile: {vol_pct:.1f}% | CV: {zones["cv_percent"]:.1f}%',
        fontsize=15, fontweight='bold', pad=20
    )
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=0.8)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.5f}'))
    
    # --- VOLATILITY INDICATOR ---
    ax2.plot(year_data['Timestamp'], year_data['Rolling_StdDev'],
            linewidth=1.5, color='#9b59b6', alpha=0.8,
            label=f'Rolling StdDev (6h, Quarterly Baseline)')
    
    if len(volatile_data) > 0:
        ax2.scatter(volatile_data['Timestamp'], volatile_data['Rolling_StdDev'],
                   color='#c0392b', s=25, alpha=0.8, zorder=5, label='Volatile Periods')
    
    ax2.set_ylabel('Volatility', fontsize=12, fontweight='bold')
    ax2.set_title('Volatility Indicator (Quarterly Baselines)', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper right', fontsize=10, framealpha=0.95)
    ax2.grid(True, alpha=0.3, linestyle='--')
    
    # --- ZOOMED VOLATILITY VIEW ---
    if len(volatile_data) > 0:
        # Find most significant volatile period
        max_group = volatile_data.groupby('Volatile_Group')['Rolling_StdDev'].max().idxmax()
        focus_group = volatile_data[volatile_data['Volatile_Group'] == max_group]
        
        start_focus = focus_group['Timestamp'].min() - timedelta(hours=12)
        end_focus = focus_group['Timestamp'].max() + timedelta(hours=12)
        
        zoom_data = year_data[
            (year_data['Timestamp'] >= start_focus) & 
            (year_data['Timestamp'] <= end_focus)
        ]
        
        ax3.plot(zoom_data['Timestamp'], zoom_data['SpotPrice'],
                linewidth=2, color='#2c3e50', alpha=0.9, label='Spot Price')
        
        ax3.axhline(zones['green_upper'], color='#27ae60', linewidth=2,
                   linestyle='--', alpha=0.7, label='Green Upper')
        
        # Highlight volatile region
        group_start = focus_group['Timestamp'].min()
        group_end = focus_group['Timestamp'].max()
        ax3.axvspan(group_start, group_end, color='#9b59b6', alpha=0.3, label='Volatile Period')
        
        ax3.set_ylabel('Spot Price (USD)', fontsize=11, fontweight='bold')
        ax3.set_xlabel('Date', fontsize=11, fontweight='bold')
        ax3.set_title(f'Zoomed View: Most Significant Volatility Period (Group {int(max_group)})',
                     fontsize=11, fontweight='bold')
        ax3.legend(loc='upper right', fontsize=9, framealpha=0.95)
        ax3.grid(True, alpha=0.3, linestyle='--')
        ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.5f}'))
    else:
        ax3.text(0.5, 0.5, 'No significant volatility detected',
                ha='center', va='center', fontsize=14, transform=ax3.transAxes)
        ax3.set_xlabel('Date', fontsize=11, fontweight='bold')
    
    plt.tight_layout()
    
    filename = f"{CONFIG['output_dir']}{pool}_{analysis_year}_quarterly.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"      ✅ Saved: {filename}")

# ============================================================================
# MAIN EXECUTION
# ============================================================================
def main():
    print("\n" + "=" * 80)
    print(" AWS SPOT PRICE ANALYSIS - QUARTERLY VOLATILITY DETECTION")
    print("=" * 80 + "\n")
    
    try:
        df = load_and_clean_data(CONFIG['files'], CONFIG['target_instances'])
        zones_dict = calculate_enhanced_zones(df, CONFIG['analysis_year'])
        
        if not zones_dict:
            print("❌ No zones calculated")
            return
        
        print("\n" + "=" * 80)
        print("GENERATING VISUALIZATIONS (Quarterly Volatility)")
        print("=" * 80 + "\n")
        
        for pool in sorted(zones_dict.keys()):
            pool_data = df[df['PoolID'] == pool].copy()
            create_enhanced_plot_quarterly(pool_data, pool, zones_dict[pool], CONFIG['analysis_year'])
        
        print("\n✅ ANALYSIS COMPLETE!")
        print(f"📁 Output: {CONFIG['output_dir']}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
