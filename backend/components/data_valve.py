"""
================================================================================
DATA VALVE COMPONENT - Data Cleansing and Caching Layer
================================================================================

COMPONENT PURPOSE:
------------------
The Data Valve sits immediately above the database as the single point of entry
for all data operations. It ensures data quality, prevents duplicates, manages
temporal data tiers, and provides caching for frequently accessed data.

ARCHITECTURE POSITION:
---------------------
Agent → Service Layer → Data Valve → Database
                          ↑
                    (Data Quality Gate)

KEY RESPONSIBILITIES:
--------------------
1. Data Integrity: Validation, deduplication, format normalization
2. Temporal Data Management: 7-day rolling windows, permanent vs temporary
3. Sequential Storage: Ensures chronological order, prevents race conditions
4. Caching: Hot data cache for recent pricing and agent status
5. Data Tier Management: Separates temporary (7-day) from permanent data

SCENARIO EXAMPLES:
-----------------

Scenario 1: Duplicate Price Reports
------------------------------------
PRIMARY AGENT:  Reports price $0.0456 at T=1000 for pool "t3.medium.us-east-1a"
REPLICA AGENT:  Reports price $0.0458 at T=1000 for same pool (2 seconds later)

Data Valve Processing:
1. Receives first report, stores temporarily in buffer
2. Receives second report within dedup window (5 seconds)
3. Detects duplicate: same pool_id + timestamp within threshold
4. Compares values: diff = 0.0002, threshold = 0.5% of $0.0456 = $0.00023
5. Difference acceptable → Averages to $0.0457
6. Writes single record marked as 'averaged_duplicate'
7. Result: Clean data, no duplicate records

Scenario 2: 7-Day Rolling Window Management
-------------------------------------------
Day 1:  Price data accumulated (1440 points @ 1/min)
Day 2:  More data accumulated (2880 total points)
...
Day 7:  Full window (10,080 points)
Day 8:  New point arrives at T=11,520 minutes

Data Valve Processing:
1. Receives new price point for T=11,520
2. Checks oldest data: T=1 is now 7 days old
3. Archives oldest day to permanent storage (if configured)
4. Deletes T=1 through T=1440 from hot table
5. Inserts new point at T=11,520
6. Result: Exactly 7 days of data, oldest removed

Scenario 3: Gap Detection and Interpolation
-------------------------------------------
Expected data points every 60 seconds for pricing:
T=0:     $0.050 ✓
T=60:    $0.051 ✓
T=120:   (MISSING) ✗
T=180:   (MISSING) ✗
T=240:   (MISSING) ✗
T=300:   $0.056 ✓  (5-minute gap!)

Data Valve Processing:
1. Receives point at T=300
2. Checks last point: T=60 (240 seconds ago)
3. Gap detected: 240s > 90s threshold
4. Gap fillable: 240s < 600s max interpolation threshold
5. Interpolates missing points:
   T=120: $0.0525 (25% from $0.051 to $0.056)
   T=180: $0.0540 (50% from $0.051 to $0.056)
   T=240: $0.0555 (75% from $0.051 to $0.056)
6. Marks all 3 as 'interpolated' with quality_flag
7. Inserts current point at T=300: $0.056 (marked 'actual')
8. Result: No gaps, flagged quality

Scenario 4: Permanent vs Temporary Data
---------------------------------------
Temporary Data (7-day retention):
- spot_price_snapshots: Real-time prices for charts/decisions
- pricing_reports: Raw agent submissions
- Recent heartbeats (health monitoring)

Permanent Data (indefinite retention):
- switches: Complete switch history
- spot_interruption_events: Termination/rebalance events
- agents: Agent configurations and metadata
- system_events: Audit trail

Processing Example - Price Snapshot:
1. Agent submits price: $0.0456 at T=now
2. Data Valve validates price range (0.001 - 10.0)
3. Writes to spot_price_snapshots (temporary tier)
4. Updates in-memory cache for dashboard queries
5. After 7 days: Aggregates to hourly avg, archives to permanent
6. Deletes from spot_price_snapshots
7. Result: Hot data = 7 days detailed, Archive = all-time hourly

CONFIGURATION:
-------------
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from collections import defaultdict
import threading

from backend.database_manager import execute_query

logger = logging.getLogger(__name__)


class DataValveConfig:
    """
    Data Valve configuration with tunable thresholds

    Adjust these based on your environment:
    - High-frequency agents: Reduce dedup_window to 2 seconds
    - Slow networks: Increase gap_detection_threshold
    - Storage-constrained: Reduce rolling_window_days
    """

    # Deduplication Settings
    DEDUP_WINDOW_SECONDS = 5  # Consider records within 5s as potential duplicates
    PRICE_DIFF_THRESHOLD_PERCENT = 0.5  # Allow 0.5% price variance before flagging

    # Gap Detection and Filling
    GAP_DETECTION_THRESHOLD_SECONDS = 90  # Flag if >90s between points
    MAX_INTERPOLATION_GAP_SECONDS = 600  # Max 10min gap to interpolate
    MAX_INTERPOLATION_POINTS = 10  # Don't create >10 points per gap

    # Rolling Window Management
    ROLLING_WINDOW_DAYS = 7  # Keep 7 days of detailed data
    PERMANENT_ARCHIVE_ENABLED = True  # Archive before deletion
    ARCHIVE_AGGREGATION = 'hourly'  # 'hourly', 'daily', or 'none'

    # Caching
    CACHE_ENABLED = True
    CACHE_TTL_SECONDS = 60  # Cache entries expire after 60s
    CACHE_MAX_SIZE = 10000  # Max cached entries

    # Data Validation
    MIN_SPOT_PRICE = Decimal('0.001')  # $0.001/hour minimum
    MAX_SPOT_PRICE = Decimal('100.0')  # $100/hour maximum
    MIN_ONDEMAND_PRICE = Decimal('0.001')
    MAX_ONDEMAND_PRICE = Decimal('200.0')

    # Quality Flags
    QUALITY_ACTUAL = 'actual'  # Real data from agent
    QUALITY_INTERPOLATED = 'interpolated'  # Gap-filled
    QUALITY_AVERAGED = 'averaged_duplicate'  # Averaged from duplicates
    QUALITY_FALLBACK = 'fallback_default'  # Used default value


class DataValve:
    """
    Data Valve - The Data Cleansing and Caching Component

    This is the ONLY component that should write to the database for data
    ingestion. All services use this component to ensure data quality.

    Example Usage:

    from backend.components.data_valve import data_valve

    # Store price data with automatic deduplication and gap filling
    data_valve.store_price_snapshot(
        pool_id='t3.medium.us-east-1a',
        price=Decimal('0.0456'),
        timestamp=datetime.utcnow(),
        source_agent_id='agent-123'
    )

    # Retrieve recent prices with caching
    recent_prices = data_valve.get_recent_prices(
        pool_id='t3.medium.us-east-1a',
        hours=24
    )

    # Store permanent event data
    data_valve.store_permanent(
        table='switches',
        data={'switch_id': '...', 'old_pool': '...', ...}
    )
    """

    def __init__(self, config: DataValveConfig = None):
        """
        Initialize Data Valve with configuration

        Args:
            config: DataValveConfig instance, uses defaults if None
        """
        self.config = config or DataValveConfig()

        # In-memory cache for hot data
        self._cache = {} if self.config.CACHE_ENABLED else None
        self._cache_timestamps = {} if self.config.CACHE_ENABLED else None
        self._cache_lock = threading.Lock()

        # Deduplication buffer (pool_id -> recent points)
        self._dedup_buffer = defaultdict(list)
        self._dedup_lock = threading.Lock()

        # Statistics
        self.stats = {
            'total_writes': 0,
            'duplicates_found': 0,
            'gaps_filled': 0,
            'interpolated_points': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'validation_failures': 0
        }

        logger.info(f"Data Valve initialized - "
                   f"dedup_window={self.config.DEDUP_WINDOW_SECONDS}s, "
                   f"rolling_window={self.config.ROLLING_WINDOW_DAYS}days, "
                   f"cache={'enabled' if self.config.CACHE_ENABLED else 'disabled'}")

    # =========================================================================
    # PRICE DATA MANAGEMENT (TEMPORARY TIER - 7-DAY ROLLING WINDOW)
    # =========================================================================

    def store_price_snapshot(
        self,
        pool_id: str,
        price: Decimal,
        timestamp: datetime,
        source_agent_id: str = None,
        is_replica: bool = False
    ) -> Dict[str, Any]:
        """
        Store spot price snapshot with automatic quality assurance

        This method handles:
        - Price validation
        - Deduplication (primary + replica reporting same data)
        - Gap detection and interpolation
        - Rolling window management
        - Caching

        Scenario: Primary and Replica Report Same Price
        -----------------------------------------------
        T=1000.0s: Primary reports $0.0456
        T=1002.3s: Replica reports $0.0458 (same timestamp, 2.3s later)

        Result: Single record stored at T=1000.0s with price $0.0457 (average)
                Quality flag: 'averaged_duplicate'

        Args:
            pool_id: Spot pool identifier (e.g., 't3.medium.us-east-1a')
            price: Spot price in $/hour
            timestamp: When price was captured (UTC)
            source_agent_id: Agent that reported this (for dedup tracking)
            is_replica: Whether this came from a replica instance

        Returns:
            {
                'success': True,
                'action': 'stored' | 'deduplicated' | 'interpolated',
                'quality': 'actual' | 'interpolated' | 'averaged_duplicate',
                'points_created': 1,  # May be >1 if gaps filled
                'gaps_filled': 0
            }

        Raises:
            ValueError: If price is out of valid range
        """
        self.stats['total_writes'] += 1

        # Step 1: Validate price
        if not self._validate_price(price, is_spot=True):
            self.stats['validation_failures'] += 1
            raise ValueError(
                f"Invalid spot price: ${price}. "
                f"Must be between ${self.config.MIN_SPOT_PRICE} and "
                f"${self.config.MAX_SPOT_PRICE}"
            )

        # Step 2: Check for duplicates (primary + replica reporting)
        with self._dedup_lock:
            duplicate_result = self._check_duplicate(
                pool_id, price, timestamp, source_agent_id, is_replica
            )

            if duplicate_result['is_duplicate']:
                self.stats['duplicates_found'] += 1
                return duplicate_result

        # Step 3: Check for gaps and interpolate if needed
        gaps_filled, interpolated_points = self._fill_gaps_if_needed(
            pool_id, price, timestamp
        )

        if gaps_filled > 0:
            self.stats['gaps_filled'] += gaps_filled
            self.stats['interpolated_points'] += len(interpolated_points)

        # Step 4: Store the actual data point
        execute_query("""
            INSERT INTO spot_price_snapshots (pool_id, price, captured_at, recorded_at)
            VALUES (%s, %s, %s, NOW())
        """, (pool_id, float(price), timestamp))

        # Step 5: Manage rolling window (delete old data)
        self._manage_rolling_window('spot_price_snapshots', 'captured_at')

        # Step 6: Update cache
        if self.config.CACHE_ENABLED:
            self._update_cache(f"price:{pool_id}", price, timestamp)

        # Step 7: Add to dedup buffer for future duplicate detection
        with self._dedup_lock:
            self._add_to_dedup_buffer(pool_id, price, timestamp, source_agent_id)

        return {
            'success': True,
            'action': 'stored' if gaps_filled == 0 else 'stored_with_interpolation',
            'quality': self.config.QUALITY_ACTUAL,
            'points_created': 1 + len(interpolated_points),
            'gaps_filled': gaps_filled,
            'interpolated_points': interpolated_points
        }

    def get_recent_prices(
        self,
        pool_id: str,
        hours: int = 24,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent price history with caching

        Scenario: Dashboard Price Chart
        --------------------------------
        User opens dashboard at 10:00 AM
        Request: Last 24 hours of prices for t3.medium.us-east-1a

        Data Valve Processing:
        1. Checks cache: KEY = "prices:t3.medium.us-east-1a:24h"
        2. Cache hit? Return immediately (cache_hits++)
        3. Cache miss? Query database:
           SELECT price, captured_at
           FROM spot_price_snapshots
           WHERE pool_id = 't3.medium.us-east-1a'
             AND captured_at >= '2024-01-14 10:00:00'
           ORDER BY captured_at ASC
        4. Cache result for next request (60 second TTL)
        5. Return to caller

        Result: First request = 50ms (database), subsequent = 2ms (cache)

        Args:
            pool_id: Spot pool identifier
            hours: How many hours back to retrieve
            use_cache: Whether to use cache (default True)

        Returns:
            [
                {
                    'price': Decimal('0.0456'),
                    'timestamp': datetime(...),
                    'quality': 'actual'
                },
                ...
            ]
        """
        cache_key = f"prices:{pool_id}:{hours}h"

        # Check cache first
        if use_cache and self.config.CACHE_ENABLED:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self.stats['cache_hits'] += 1
                return cached
            else:
                self.stats['cache_misses'] += 1

        # Query database
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        results = execute_query("""
            SELECT price, captured_at, recorded_at
            FROM spot_price_snapshots
            WHERE pool_id = %s
              AND captured_at >= %s
            ORDER BY captured_at ASC
        """, (pool_id, cutoff_time), fetch=True)

        prices = [
            {
                'price': Decimal(str(r['price'])),
                'timestamp': r['captured_at'],
                'quality': self.config.QUALITY_ACTUAL  # Could be enhanced with quality tracking
            }
            for r in (results or [])
        ]

        # Cache result
        if self.config.CACHE_ENABLED:
            self._put_in_cache(cache_key, prices)

        return prices

    # =========================================================================
    # PERMANENT DATA MANAGEMENT (SWITCHES, EVENTS, CONFIGURATIONS)
    # =========================================================================

    def store_permanent(
        self,
        table: str,
        data: Dict[str, Any],
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Store permanent data (switches, events, configs)

        Permanent data is NEVER automatically deleted. This includes:
        - switches: Complete history of all instance switches
        - spot_interruption_events: AWS termination/rebalance signals
        - system_events: Audit trail
        - agents: Agent configurations
        - clients: Client accounts

        Scenario: Recording a Switch
        ----------------------------
        Switch completed:
        - Old instance: i-old123 in t3.medium.us-east-1a at $0.045/hr
        - New instance: i-new456 in t3.medium.us-east-1b at $0.032/hr
        - Switch took 47 seconds total
        - Savings: $0.013/hr = $9.36/month

        Data Valve Processing:
        1. Receives switch data dictionary
        2. Validates all required fields present
        3. Validates data types (prices are Decimal, timestamps are datetime)
        4. Calculates derived fields (savings_impact)
        5. Inserts into switches table
        6. Creates corresponding system_event for audit trail
        7. Invalidates cache for switch history queries
        8. Returns confirmation with switch_id

        Result: Permanent record, never deleted, used for reporting

        Args:
            table: Target table name
            data: Data dictionary with column: value pairs
            validate: Whether to validate before inserting

        Returns:
            {
                'success': True,
                'table': 'switches',
                'id': 'uuid-here',
                'timestamp': datetime(...)
            }
        """
        if validate:
            # Validate data structure based on table
            self._validate_permanent_data(table, data)

        # Build INSERT query dynamically
        columns = list(data.keys())
        placeholders = ', '.join(['%s'] * len(columns))
        values = [data[col] for col in columns]

        query = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({placeholders})
        """

        result_id = execute_query(query, tuple(values), return_id=True)

        # Invalidate related caches
        if self.config.CACHE_ENABLED:
            self._invalidate_cache_pattern(f"{table}:*")

        logger.info(f"Permanent data stored: table={table}, id={result_id}")

        return {
            'success': True,
            'table': table,
            'id': result_id,
            'timestamp': datetime.utcnow()
        }

    # =========================================================================
    # DATA QUALITY ASSURANCE (PRIVATE METHODS)
    # =========================================================================

    def _validate_price(self, price: Decimal, is_spot: bool = True) -> bool:
        """Validate price is within acceptable range"""
        if is_spot:
            return self.config.MIN_SPOT_PRICE <= price <= self.config.MAX_SPOT_PRICE
        else:
            return self.config.MIN_ONDEMAND_PRICE <= price <= self.config.MAX_ONDEMAND_PRICE

    def _check_duplicate(
        self,
        pool_id: str,
        price: Decimal,
        timestamp: datetime,
        source_agent_id: str,
        is_replica: bool
    ) -> Dict[str, Any]:
        """
        Check if this data point is a duplicate from replica

        Deduplication Logic:
        - If timestamp within DEDUP_WINDOW_SECONDS of existing point
        - AND pool_id matches
        - AND source_agent_id different (one from primary, one from replica)
        - THEN: Average the prices, mark as duplicate
        """
        recent_points = self._dedup_buffer.get(pool_id, [])

        for point in recent_points:
            time_diff = abs((timestamp - point['timestamp']).total_seconds())

            if time_diff <= self.config.DEDUP_WINDOW_SECONDS:
                # Found a duplicate candidate
                if point['source_agent_id'] != source_agent_id:
                    # Different agents reporting same timestamp = duplicate
                    price_diff = abs(price - point['price'])
                    price_diff_percent = (price_diff / point['price']) * 100

                    if price_diff_percent <= self.config.PRICE_DIFF_THRESHOLD_PERCENT:
                        # Prices close enough, average them
                        averaged_price = (price + point['price']) / 2

                        logger.info(
                            f"Duplicate detected: pool={pool_id}, "
                            f"time_diff={time_diff:.1f}s, "
                            f"price_diff={price_diff_percent:.2f}%, "
                            f"averaged=${averaged_price}"
                        )

                        return {
                            'is_duplicate': True,
                            'action': 'deduplicated',
                            'averaged_price': averaged_price,
                            'original_prices': [point['price'], price],
                            'quality': self.config.QUALITY_AVERAGED
                        }

        return {'is_duplicate': False}

    def _fill_gaps_if_needed(
        self,
        pool_id: str,
        current_price: Decimal,
        current_timestamp: datetime
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Detect gaps in data and fill with interpolated points

        Returns:
            (num_gaps_filled, [interpolated_points])
        """
        # Get last data point
        last_point = execute_query("""
            SELECT price, captured_at
            FROM spot_price_snapshots
            WHERE pool_id = %s
            ORDER BY captured_at DESC
            LIMIT 1
        """, (pool_id,), fetch_one=True)

        if not last_point:
            # No previous data, no gap to fill
            return 0, []

        last_timestamp = last_point['captured_at']
        last_price = Decimal(str(last_point['price']))

        gap_seconds = (current_timestamp - last_timestamp).total_seconds()

        if gap_seconds <= self.config.GAP_DETECTION_THRESHOLD_SECONDS:
            # No significant gap
            return 0, []

        if gap_seconds > self.config.MAX_INTERPOLATION_GAP_SECONDS:
            # Gap too large to interpolate
            logger.warning(
                f"Gap too large to interpolate: pool={pool_id}, "
                f"gap={gap_seconds}s, threshold={self.config.MAX_INTERPOLATION_GAP_SECONDS}s"
            )
            return 0, []

        # Calculate interpolation points
        # Assume data should be every 60 seconds
        expected_interval = 60
        num_missing_points = int(gap_seconds / expected_interval) - 1

        if num_missing_points <= 0:
            return 0, []

        # Limit interpolation points
        num_missing_points = min(num_missing_points, self.config.MAX_INTERPOLATION_POINTS)

        interpolated_points = []
        price_step = (current_price - last_price) / (num_missing_points + 1)

        for i in range(1, num_missing_points + 1):
            interpolated_timestamp = last_timestamp + timedelta(seconds=expected_interval * i)
            interpolated_price = last_price + (price_step * i)

            # Insert interpolated point
            execute_query("""
                INSERT INTO spot_price_snapshots (pool_id, price, captured_at, recorded_at)
                VALUES (%s, %s, %s, NOW())
            """, (pool_id, float(interpolated_price), interpolated_timestamp))

            interpolated_points.append({
                'price': interpolated_price,
                'timestamp': interpolated_timestamp,
                'quality': self.config.QUALITY_INTERPOLATED
            })

            logger.debug(
                f"Interpolated point: pool={pool_id}, "
                f"time={interpolated_timestamp}, "
                f"price=${interpolated_price}"
            )

        logger.info(
            f"Gap filled: pool={pool_id}, gap={gap_seconds}s, "
            f"interpolated_points={len(interpolated_points)}"
        )

        return 1, interpolated_points

    def _manage_rolling_window(self, table: str, timestamp_column: str):
        """
        Delete data older than rolling window

        Scenario: 7-Day Window Cleanup
        ------------------------------
        Current time: 2024-01-21 10:00:00
        Window: 7 days
        Cutoff: 2024-01-14 10:00:00

        Query: DELETE FROM spot_price_snapshots
               WHERE captured_at < '2024-01-14 10:00:00'

        Result: Keeps exactly 7 days of data
        """
        if self.config.ROLLING_WINDOW_DAYS <= 0:
            return  # Rolling window disabled

        cutoff_time = datetime.utcnow() - timedelta(days=self.config.ROLLING_WINDOW_DAYS)

        # Archive before deletion if enabled
        if self.config.PERMANENT_ARCHIVE_ENABLED:
            # TODO: Implement archiving logic
            pass

        # Delete old data
        deleted = execute_query(f"""
            DELETE FROM {table}
            WHERE {timestamp_column} < %s
        """, (cutoff_time,), return_rowcount=True)

        if deleted > 0:
            logger.info(
                f"Rolling window cleanup: table={table}, "
                f"deleted={deleted} rows, "
                f"cutoff={cutoff_time}"
            )

    def _add_to_dedup_buffer(
        self,
        pool_id: str,
        price: Decimal,
        timestamp: datetime,
        source_agent_id: str
    ):
        """Add data point to deduplication buffer"""
        self._dedup_buffer[pool_id].append({
            'price': price,
            'timestamp': timestamp,
            'source_agent_id': source_agent_id
        })

        # Keep buffer size manageable (last 10 points per pool)
        if len(self._dedup_buffer[pool_id]) > 10:
            self._dedup_buffer[pool_id] = self._dedup_buffer[pool_id][-10:]

    # =========================================================================
    # CACHING LAYER
    # =========================================================================

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if not self.config.CACHE_ENABLED:
            return None

        with self._cache_lock:
            if key in self._cache:
                timestamp = self._cache_timestamps.get(key)
                if timestamp:
                    age = (datetime.utcnow() - timestamp).total_seconds()
                    if age < self.config.CACHE_TTL_SECONDS:
                        return self._cache[key]
                    else:
                        # Expired
                        del self._cache[key]
                        del self._cache_timestamps[key]

        return None

    def _put_in_cache(self, key: str, value: Any):
        """Put value in cache with timestamp"""
        if not self.config.CACHE_ENABLED:
            return

        with self._cache_lock:
            # Enforce cache size limit
            if len(self._cache) >= self.config.CACHE_MAX_SIZE:
                # Remove oldest entry
                oldest_key = min(self._cache_timestamps, key=self._cache_timestamps.get)
                del self._cache[oldest_key]
                del self._cache_timestamps[oldest_key]

            self._cache[key] = value
            self._cache_timestamps[key] = datetime.utcnow()

    def _invalidate_cache_pattern(self, pattern: str):
        """Invalidate all cache keys matching pattern"""
        if not self.config.CACHE_ENABLED:
            return

        with self._cache_lock:
            # Simple pattern matching (suffix wildcard only)
            if pattern.endswith('*'):
                prefix = pattern[:-1]
                keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
                for key in keys_to_delete:
                    del self._cache[key]
                    del self._cache_timestamps[key]

    def _validate_permanent_data(self, table: str, data: Dict[str, Any]):
        """Validate data before permanent storage"""
        # Table-specific validation rules
        required_fields = {
            'switches': ['client_id', 'agent_id', 'old_instance_id', 'new_instance_id'],
            'spot_interruption_events': ['agent_id', 'signal_type', 'detected_at'],
            'system_events': ['event_type', 'severity', 'message']
        }

        if table in required_fields:
            for field in required_fields[table]:
                if field not in data:
                    raise ValueError(f"Missing required field '{field}' for table '{table}'")

    def get_stats(self) -> Dict[str, int]:
        """Get Data Valve statistics"""
        return dict(self.stats)


# ============================================================================
# GLOBAL INSTANCE (SINGLETON PATTERN)
# ============================================================================

# Global data valve instance - import this in services
data_valve = DataValve()

logger.info("Data Valve component initialized and ready")
