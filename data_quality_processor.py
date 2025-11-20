"""
Data Quality & Deduplication Processor
Handles pricing data deduplication, gap detection, and price interpolation.

This module implements:
1. Real-time deduplication pipeline
2. Gap detection and filling algorithms
3. Price interpolation with multiple strategies
4. ML dataset preparation with quality filtering
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import statistics

from database_utils import execute_query

logger = logging.getLogger(__name__)

# ============================================================================
# DEDUPLICATION PIPELINE
# ============================================================================

def process_pricing_submission(
    submission_id: str,
    source_instance_id: str,
    source_agent_id: str,
    source_type: str,
    pool_id: int,
    instance_type: str,
    region: str,
    az: str,
    spot_price: Decimal,
    ondemand_price: Optional[Decimal],
    observed_at: datetime,
    submitted_at: datetime,
    client_id: str,
    batch_id: Optional[str] = None
) -> Dict:
    """
    Process a single pricing submission through the deduplication pipeline.

    Returns:
        dict: {
            'accepted': bool,
            'duplicate': bool,
            'reason': str,
            'clean_snapshot_id': int | None
        }
    """
    try:
        # Step 1: Insert into raw table
        execute_query("""
            INSERT INTO pricing_submissions_raw (
                submission_id, source_instance_id, source_agent_id, source_type,
                pool_id, instance_type, region, az, spot_price, ondemand_price,
                observed_at, submitted_at, client_id, batch_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            submission_id, source_instance_id, source_agent_id, source_type,
            pool_id, instance_type, region, az, float(spot_price),
            float(ondemand_price) if ondemand_price else None,
            observed_at, submitted_at, client_id, batch_id
        ))

        # Step 2: Check for exact duplicates (same submission_id already exists)
        existing = execute_query("""
            SELECT submission_id FROM pricing_submissions_raw
            WHERE submission_id = %s
        """, (submission_id,), fetch=True)

        if len(existing) > 1:  # Found duplicate
            execute_query("""
                UPDATE pricing_submissions_raw
                SET is_duplicate = TRUE, duplicate_of = %s
                WHERE submission_id = %s
            """, (existing[0]['submission_id'], submission_id))

            logger.debug(f"Duplicate submission detected: {submission_id}")
            return {'accepted': False, 'duplicate': True, 'reason': 'exact_duplicate'}

        # Step 3: Time-window bucketing (5-minute buckets)
        time_bucket = _round_to_bucket(observed_at, bucket_minutes=5)

        # Step 4: Check if we already have data for this time bucket
        existing_snapshot = execute_query("""
            SELECT id, source_type, confidence_score, spot_price
            FROM pricing_snapshots_clean
            WHERE pool_id = %s AND time_bucket = %s
        """, (pool_id, time_bucket), fetch=True)

        if existing_snapshot:
            # Determine if this submission should replace existing
            existing = existing_snapshot[0]
            should_replace = _should_replace_snapshot(
                existing_source_type=existing['source_type'],
                existing_confidence=existing['confidence_score'],
                new_source_type=source_type,
                existing_price=existing['spot_price'],
                new_price=spot_price
            )

            if not should_replace:
                # Mark as duplicate but keep in raw table
                execute_query("""
                    UPDATE pricing_submissions_raw
                    SET is_duplicate = TRUE
                    WHERE submission_id = %s
                """, (submission_id,))

                logger.debug(f"Lower priority submission for bucket {time_bucket}: {submission_id}")
                return {'accepted': False, 'duplicate': True, 'reason': 'lower_priority'}

            # Replace existing snapshot
            execute_query("""
                UPDATE pricing_snapshots_clean
                SET spot_price = %s,
                    ondemand_price = %s,
                    savings_percent = %s,
                    source_instance_id = %s,
                    source_agent_id = %s,
                    source_type = %s,
                    source_submission_id = %s,
                    confidence_score = %s
                WHERE id = %s
            """, (
                float(spot_price),
                float(ondemand_price) if ondemand_price else None,
                _calculate_savings(spot_price, ondemand_price) if ondemand_price else None,
                source_instance_id,
                source_agent_id,
                source_type,
                submission_id,
                _get_confidence_score(source_type),
                existing['id']
            ))

            logger.info(f"Replaced snapshot {existing['id']} with submission {submission_id}")
            return {'accepted': True, 'duplicate': False, 'reason': 'replaced_existing', 'clean_snapshot_id': existing['id']}

        # Step 5: Create new clean snapshot
        bucket_start = time_bucket
        bucket_end = time_bucket + timedelta(minutes=5, seconds=-1)

        result = execute_query("""
            INSERT INTO pricing_snapshots_clean (
                pool_id, instance_type, region, az, spot_price, ondemand_price,
                savings_percent, time_bucket, bucket_start, bucket_end,
                source_instance_id, source_agent_id, source_type, source_submission_id,
                confidence_score, data_source
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'measured'
            )
        """, (
            pool_id, instance_type, region, az,
            float(spot_price),
            float(ondemand_price) if ondemand_price else None,
            _calculate_savings(spot_price, ondemand_price) if ondemand_price else None,
            time_bucket, bucket_start, bucket_end,
            source_instance_id, source_agent_id, source_type, submission_id,
            _get_confidence_score(source_type)
        ))

        snapshot_id = result  # Last insert ID

        logger.info(f"Created clean snapshot {snapshot_id} from submission {submission_id}")
        return {'accepted': True, 'duplicate': False, 'reason': 'new_snapshot', 'clean_snapshot_id': snapshot_id}

    except Exception as e:
        logger.error(f"Error processing submission {submission_id}: {e}", exc_info=True)
        return {'accepted': False, 'duplicate': False, 'reason': f'error: {str(e)}'}


def deduplicate_batch(start_time: datetime, end_time: datetime) -> Dict:
    """
    Run deduplication on a batch of raw submissions.
    Used for batch processing or catching up after downtime.
    """
    try:
        job_id = execute_query("""
            INSERT INTO data_processing_jobs (job_type, status, start_time, end_time)
            VALUES ('deduplication', 'running', %s, %s)
        """, (start_time, end_time))

        # Get all raw submissions in time range that haven't been processed
        raw_submissions = execute_query("""
            SELECT *
            FROM pricing_submissions_raw
            WHERE received_at BETWEEN %s AND %s
              AND is_duplicate = FALSE
            ORDER BY received_at ASC
        """, (start_time, end_time), fetch=True)

        stats = {
            'processed': 0,
            'duplicates_found': 0,
            'new_snapshots': 0,
            'replaced': 0,
            'errors': 0
        }

        for submission in (raw_submissions or []):
            result = process_pricing_submission(
                submission_id=submission['submission_id'],
                source_instance_id=submission['source_instance_id'],
                source_agent_id=submission['source_agent_id'],
                source_type=submission['source_type'],
                pool_id=submission['pool_id'],
                instance_type=submission['instance_type'],
                region=submission['region'],
                az=submission['az'],
                spot_price=Decimal(str(submission['spot_price'])),
                ondemand_price=Decimal(str(submission['ondemand_price'])) if submission['ondemand_price'] else None,
                observed_at=submission['observed_at'],
                submitted_at=submission['submitted_at'],
                client_id=submission['client_id'],
                batch_id=submission.get('batch_id')
            )

            stats['processed'] += 1

            if result['duplicate']:
                stats['duplicates_found'] += 1
            elif result['accepted']:
                if result['reason'] == 'new_snapshot':
                    stats['new_snapshots'] += 1
                elif result['reason'] == 'replaced_existing':
                    stats['replaced'] += 1
            else:
                stats['errors'] += 1

        # Update job
        execute_query("""
            UPDATE data_processing_jobs
            SET status = 'completed',
                records_processed = %s,
                duplicates_found = %s,
                completed_at = NOW(),
                result_summary = %s
            WHERE id = %s
        """, (stats['processed'], stats['duplicates_found'], json.dumps(stats), job_id))

        logger.info(f"Deduplication batch completed: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error in deduplication batch: {e}", exc_info=True)
        execute_query("""
            UPDATE data_processing_jobs
            SET status = 'failed', error_log = %s, completed_at = NOW()
            WHERE id = %s
        """, (str(e), job_id))
        raise


# ============================================================================
# GAP DETECTION & FILLING
# ============================================================================

def detect_and_fill_gaps(pool_id: int, start_time: datetime, end_time: datetime) -> Dict:
    """
    Detect gaps in pricing data for a specific pool and fill them using interpolation.
    """
    try:
        job_id = execute_query("""
            INSERT INTO data_processing_jobs (job_type, status, start_time, end_time)
            VALUES ('gap-filling', 'running', %s, %s)
        """, (start_time, end_time))

        # Get pool details
        pool = execute_query("""
            SELECT * FROM spot_pools WHERE id = %s
        """, (pool_id,), fetch=True)[0]

        # Get all existing snapshots in time range
        snapshots = execute_query("""
            SELECT time_bucket, spot_price, ondemand_price
            FROM pricing_snapshots_clean
            WHERE pool_id = %s
              AND time_bucket BETWEEN %s AND %s
            ORDER BY time_bucket ASC
        """, (pool_id, start_time, end_time), fetch=True)

        if not snapshots or len(snapshots) == 0:
            logger.warning(f"No snapshots found for pool {pool_id} in range {start_time} to {end_time}")
            return {'gaps_found': 0, 'gaps_filled': 0}

        # Detect gaps
        gaps = []
        current_time = _round_to_bucket(start_time, bucket_minutes=5)
        end_bucket = _round_to_bucket(end_time, bucket_minutes=5)

        snapshot_times = {s['time_bucket']: s for s in snapshots}

        while current_time <= end_bucket:
            if current_time not in snapshot_times:
                gaps.append(current_time)
            current_time += timedelta(minutes=5)

        logger.info(f"Found {len(gaps)} gaps for pool {pool_id}")

        stats = {
            'gaps_found': len(gaps),
            'gaps_filled': 0,
            'interpolations_created': 0
        }

        # Fill each gap
        for gap_time in gaps:
            result = _fill_gap(
                pool_id=pool_id,
                pool=pool,
                gap_time=gap_time,
                snapshots=snapshot_times
            )

            if result['success']:
                stats['gaps_filled'] += 1
                if result.get('interpolated'):
                    stats['interpolations_created'] += 1

        # Update job
        execute_query("""
            UPDATE data_processing_jobs
            SET status = 'completed',
                gaps_filled = %s,
                interpolations_created = %s,
                completed_at = NOW(),
                result_summary = %s
            WHERE id = %s
        """, (stats['gaps_filled'], stats['interpolations_created'], json.dumps(stats), job_id))

        logger.info(f"Gap filling completed for pool {pool_id}: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error in gap detection/filling: {e}", exc_info=True)
        execute_query("""
            UPDATE data_processing_jobs
            SET status = 'failed', error_log = %s, completed_at = NOW()
            WHERE id = %s
        """, (str(e), job_id))
        raise


def _fill_gap(
    pool_id: int,
    pool: Dict,
    gap_time: datetime,
    snapshots: Dict[datetime, Dict]
) -> Dict:
    """Fill a single gap using appropriate interpolation strategy"""
    try:
        # Find nearest snapshots before and after
        before_price, before_time = _find_nearest_snapshot(gap_time, snapshots, direction='before')
        after_price, after_time = _find_nearest_snapshot(gap_time, snapshots, direction='after')

        if not before_price or not after_price:
            logger.warning(f"Cannot interpolate for {gap_time}: missing boundary prices")
            return {'success': False, 'reason': 'missing_boundaries'}

        # Calculate gap duration in buckets
        gap_buckets = _calculate_gap_buckets(before_time, after_time)

        # Determine interpolation strategy based on gap size
        if gap_buckets <= 2:
            # Short gap: linear interpolation
            interpolated_price = _linear_interpolation(
                before_price, after_price, before_time, after_time, gap_time
            )
            method = 'linear'
            confidence = 0.85
            gap_type = 'short'

        elif gap_buckets <= 6:
            # Medium gap: weighted average
            interpolated_price = _weighted_average_interpolation(
                pool_id, before_price, after_price, before_time, after_time, gap_time
            )
            method = 'weighted-average'
            confidence = 0.75
            gap_type = 'medium'

        elif gap_buckets <= 24:
            # Long gap: cross-pool inference
            interpolated_price = _cross_pool_interpolation(
                pool, gap_time, before_price, after_price
            )
            method = 'cross-pool'
            confidence = 0.70
            gap_type = 'long'

        else:
            # Very long gap: don't interpolate
            logger.warning(f"Gap too long ({gap_buckets} buckets) for pool {pool_id} at {gap_time}")
            return {'success': False, 'reason': 'gap_too_long'}

        # Create interpolated snapshot record
        execute_query("""
            INSERT INTO pricing_snapshots_interpolated (
                pool_id, instance_type, region, az, time_bucket,
                gap_duration_minutes, gap_type, interpolation_method,
                confidence_score, price_before, price_after,
                timestamp_before, timestamp_after, interpolated_price
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            pool_id, pool['instance_type'], pool['region'], pool['az'],
            gap_time, gap_buckets * 5, gap_type, method, confidence,
            float(before_price), float(after_price), before_time, after_time,
            float(interpolated_price)
        ))

        # Insert into clean snapshots table
        bucket_start = gap_time
        bucket_end = gap_time + timedelta(minutes=5, seconds=-1)

        execute_query("""
            INSERT INTO pricing_snapshots_clean (
                pool_id, instance_type, region, az, spot_price,
                time_bucket, bucket_start, bucket_end,
                source_type, confidence_score, data_source,
                interpolation_method
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, 'interpolated', %s, 'interpolated', %s
            )
        """, (
            pool_id, pool['instance_type'], pool['region'], pool['az'],
            float(interpolated_price), gap_time, bucket_start, bucket_end,
            confidence, method
        ))

        logger.debug(f"Filled gap at {gap_time} for pool {pool_id} using {method}")
        return {'success': True, 'interpolated': True, 'method': method, 'confidence': confidence}

    except Exception as e:
        logger.error(f"Error filling gap: {e}", exc_info=True)
        return {'success': False, 'reason': f'error: {str(e)}'}


# ============================================================================
# INTERPOLATION ALGORITHMS
# ============================================================================

def _linear_interpolation(
    price_before: Decimal,
    price_after: Decimal,
    time_before: datetime,
    time_after: datetime,
    target_time: datetime
) -> Decimal:
    """Linear interpolation between two prices"""
    total_gap = (time_after - time_before).total_seconds()
    time_from_before = (target_time - time_before).total_seconds()

    if total_gap == 0:
        return price_before

    ratio = time_from_before / total_gap
    interpolated = price_before + (price_after - price_before) * Decimal(str(ratio))

    return round(interpolated, 6)


def _weighted_average_interpolation(
    pool_id: int,
    price_before: Decimal,
    price_after: Decimal,
    time_before: datetime,
    time_after: datetime,
    target_time: datetime
) -> Decimal:
    """Weighted average with decay factor"""
    # Get surrounding prices for more context
    surrounding = execute_query("""
        SELECT time_bucket, spot_price,
               ABS(TIMESTAMPDIFF(SECOND, time_bucket, %s)) as time_distance
        FROM pricing_snapshots_clean
        WHERE pool_id = %s
          AND time_bucket BETWEEN %s AND %s
          AND time_bucket != %s
        ORDER BY time_distance ASC
        LIMIT 6
    """, (target_time, pool_id, time_before - timedelta(hours=1), time_after + timedelta(hours=1), target_time), fetch=True)

    if not surrounding or len(surrounding) == 0:
        # Fall back to linear
        return _linear_interpolation(price_before, price_after, time_before, time_after, target_time)

    # Calculate weighted average
    weighted_sum = Decimal('0')
    weight_total = Decimal('0')

    for s in surrounding:
        weight = Decimal('1') / (Decimal(str(s['time_distance'] + 1)))
        weighted_sum += Decimal(str(s['spot_price'])) * weight
        weight_total += weight

    if weight_total == 0:
        return _linear_interpolation(price_before, price_after, time_before, time_after, target_time)

    return round(weighted_sum / weight_total, 6)


def _cross_pool_interpolation(
    pool: Dict,
    target_time: datetime,
    price_before: Decimal,
    price_after: Decimal
) -> Decimal:
    """Cross-pool inference using peer pools"""
    # Find peer pools (same instance type, different AZ)
    peer_pools = execute_query("""
        SELECT p.id, p.az,
               psc_before.spot_price as price_before,
               psc_after.spot_price as price_after
        FROM spot_pools p
        LEFT JOIN pricing_snapshots_clean psc_before
            ON p.id = psc_before.pool_id
            AND psc_before.time_bucket = (
                SELECT MAX(time_bucket)
                FROM pricing_snapshots_clean
                WHERE pool_id = p.id AND time_bucket < %s
            )
        LEFT JOIN pricing_snapshots_clean psc_after
            ON p.id = psc_after.pool_id
            AND psc_after.time_bucket = (
                SELECT MIN(time_bucket)
                FROM pricing_snapshots_clean
                WHERE pool_id = p.id AND time_bucket > %s
            )
        WHERE p.instance_type = %s
          AND p.region = %s
          AND p.id != %s
          AND p.is_available = TRUE
    """, (target_time, target_time, pool['instance_type'], pool['region'], pool['id']), fetch=True)

    if not peer_pools or len(peer_pools) == 0:
        # Fall back to linear
        return _linear_interpolation(price_before, price_after, None, None, target_time)

    # Calculate median price change across peers
    price_changes = []
    for peer in peer_pools:
        if peer['price_before'] and peer['price_after']:
            change_pct = (peer['price_after'] - peer['price_before']) / peer['price_before']
            price_changes.append(change_pct)

    if not price_changes:
        return _linear_interpolation(price_before, price_after, None, None, target_time)

    median_change = statistics.median(price_changes)

    # Apply median change to our pool
    interpolated = price_before * (Decimal('1') + Decimal(str(median_change)))

    return round(interpolated, 6)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _round_to_bucket(dt: datetime, bucket_minutes: int = 5) -> datetime:
    """Round datetime to nearest bucket"""
    seconds_in_bucket = bucket_minutes * 60
    timestamp = int(dt.timestamp())
    rounded_timestamp = (timestamp // seconds_in_bucket) * seconds_in_bucket
    return datetime.fromtimestamp(rounded_timestamp)


def _should_replace_snapshot(
    existing_source_type: str,
    existing_confidence: Decimal,
    new_source_type: str,
    existing_price: Decimal,
    new_price: Decimal
) -> bool:
    """Determine if new submission should replace existing snapshot"""
    # Source priority: primary > replica-automatic > replica-manual > interpolated
    priority = {
        'primary': 4,
        'replica-automatic': 3,
        'replica-manual': 2,
        'interpolated': 1
    }

    existing_priority = priority.get(existing_source_type, 0)
    new_priority = priority.get(new_source_type, 0)

    if new_priority > existing_priority:
        return True

    if new_priority == existing_priority:
        # If same priority and prices differ significantly, flag for review
        if abs(new_price - existing_price) / existing_price > 0.10:  # 10% difference
            logger.warning(f"Price discrepancy detected: existing={existing_price}, new={new_price}")
        return False  # Keep first one received

    return False


def _get_confidence_score(source_type: str) -> Decimal:
    """Get confidence score based on source type"""
    scores = {
        'primary': Decimal('1.00'),
        'replica-automatic': Decimal('0.95'),
        'replica-manual': Decimal('0.95'),
        'interpolated': Decimal('0.70')
    }
    return scores.get(source_type, Decimal('0.50'))


def _calculate_savings(spot_price: Decimal, ondemand_price: Optional[Decimal]) -> Optional[Decimal]:
    """Calculate savings percentage"""
    if not ondemand_price or ondemand_price == 0:
        return None

    savings = ((ondemand_price - spot_price) / ondemand_price) * Decimal('100')
    return round(savings, 2)


def _find_nearest_snapshot(
    target_time: datetime,
    snapshots: Dict[datetime, Dict],
    direction: str = 'before'
) -> Tuple[Optional[Decimal], Optional[datetime]]:
    """Find nearest snapshot in given direction"""
    times = sorted(snapshots.keys())

    if direction == 'before':
        valid_times = [t for t in times if t < target_time]
        if not valid_times:
            return None, None
        nearest_time = max(valid_times)
    else:  # after
        valid_times = [t for t in times if t > target_time]
        if not valid_times:
            return None, None
        nearest_time = min(valid_times)

    snapshot = snapshots[nearest_time]
    return Decimal(str(snapshot['spot_price'])), nearest_time


def _calculate_gap_buckets(time_before: datetime, time_after: datetime) -> int:
    """Calculate number of 5-minute buckets in gap"""
    gap_seconds = (time_after - time_before).total_seconds()
    return int(gap_seconds / 300)  # 300 seconds = 5 minutes


# ============================================================================
# ML DATASET PREPARATION
# ============================================================================

def refresh_ml_dataset() -> Dict:
    """Refresh the ML training dataset materialized table"""
    try:
        job_id = execute_query("""
            INSERT INTO data_processing_jobs (
                job_type, status, start_time, end_time
            ) VALUES (
                'ml-dataset-refresh', 'running', NOW() - INTERVAL 2 YEAR, NOW()
            )
        """)

        # Clear existing data
        execute_query("TRUNCATE TABLE pricing_snapshots_ml")

        # Insert high-quality data with features
        execute_query("""
            INSERT INTO pricing_snapshots_ml (
                pool_id, instance_type, region, az, spot_price, ondemand_price,
                savings_percent, time_bucket, hour_of_day, day_of_week,
                day_of_month, month, year, confidence_score, data_source,
                price_change_1h, price_change_24h, price_volatility_6h, pool_rank_by_price
            )
            SELECT
                psc.pool_id,
                psc.instance_type,
                psc.region,
                psc.az,
                psc.spot_price,
                COALESCE(psc.ondemand_price, od.price) as ondemand_price,
                psc.savings_percent,
                psc.time_bucket,
                HOUR(psc.time_bucket) as hour_of_day,
                DAYOFWEEK(psc.time_bucket) as day_of_week,
                DAY(psc.time_bucket) as day_of_month,
                MONTH(psc.time_bucket) as month,
                YEAR(psc.time_bucket) as year,
                psc.confidence_score,
                psc.data_source,

                -- Price change features
                psc.spot_price - LAG(psc.spot_price, 12) OVER (
                    PARTITION BY psc.pool_id ORDER BY psc.time_bucket
                ) as price_change_1h,

                psc.spot_price - LAG(psc.spot_price, 288) OVER (
                    PARTITION BY psc.pool_id ORDER BY psc.time_bucket
                ) as price_change_24h,

                -- Volatility (std dev over 6 hours)
                STDDEV(psc.spot_price) OVER (
                    PARTITION BY psc.pool_id
                    ORDER BY psc.time_bucket
                    ROWS BETWEEN 71 PRECEDING AND CURRENT ROW
                ) as price_volatility_6h,

                -- Rank within region
                RANK() OVER (
                    PARTITION BY psc.instance_type, psc.region, psc.time_bucket
                    ORDER BY psc.spot_price ASC
                ) as pool_rank_by_price

            FROM pricing_snapshots_clean psc
            LEFT JOIN (
                SELECT instance_type, region, AVG(ondemand_price) as price
                FROM pricing_snapshots_clean
                WHERE ondemand_price IS NOT NULL
                GROUP BY instance_type, region
            ) od ON psc.instance_type = od.instance_type AND psc.region = od.region

            WHERE psc.confidence_score >= 0.95  -- Only high-confidence data
              AND psc.time_bucket >= NOW() - INTERVAL 2 YEAR

            ORDER BY psc.pool_id, psc.time_bucket
        """)

        rows_inserted = execute_query("SELECT COUNT(*) as cnt FROM pricing_snapshots_ml", fetch=True)[0]['cnt']

        execute_query("""
            UPDATE data_processing_jobs
            SET status = 'completed',
                records_processed = %s,
                completed_at = NOW(),
                result_summary = %s
            WHERE id = %s
        """, (rows_inserted, json.dumps({'rows_inserted': rows_inserted}), job_id))

        logger.info(f"ML dataset refreshed: {rows_inserted} rows")
        return {'success': True, 'rows_inserted': rows_inserted}

    except Exception as e:
        logger.error(f"Error refreshing ML dataset: {e}", exc_info=True)
        execute_query("""
            UPDATE data_processing_jobs
            SET status = 'failed', error_log = %s, completed_at = NOW()
            WHERE id = %s
        """, (str(e), job_id))
        raise


# ============================================================================
# SCHEDULED JOBS
# ============================================================================

def run_hourly_deduplication():
    """Run deduplication for the last hour (scheduled job)"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)
    return deduplicate_batch(start_time, end_time)


def run_daily_gap_filling():
    """Run gap filling for all pools from last 24 hours (scheduled job)"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)

    pools = execute_query("""
        SELECT id FROM spot_pools WHERE is_available = TRUE
    """, fetch=True)

    total_stats = {'gaps_found': 0, 'gaps_filled': 0, 'interpolations_created': 0}

    for pool in (pools or []):
        try:
            stats = detect_and_fill_gaps(pool['id'], start_time, end_time)
            total_stats['gaps_found'] += stats.get('gaps_found', 0)
            total_stats['gaps_filled'] += stats.get('gaps_filled', 0)
            total_stats['interpolations_created'] += stats.get('interpolations_created', 0)
        except Exception as e:
            logger.error(f"Error filling gaps for pool {pool['id']}: {e}")

    logger.info(f"Daily gap filling completed: {total_stats}")
    return total_stats


def run_ml_dataset_refresh():
    """Refresh ML dataset (scheduled every 6 hours)"""
    return refresh_ml_dataset()
