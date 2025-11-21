"""
Replica Coordinator - Central orchestration for replica management and data quality

This component is the BRAIN of replica management:
1. Emergency replica orchestration (auto-switch mode)
2. Data gap filling and deduplication from multiple agents
3. Manual replica lifecycle management
4. Independence from ML models

Architecture:
- Runs as background service in backend
- Monitors agent heartbeats and AWS interruption signals
- Coordinates replica creation/promotion/termination
- Ensures data quality and completeness
- Works independently of ML model availability
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import statistics

from database_utils import execute_query

logger = logging.getLogger(__name__)

class ReplicaCoordinator:
    """
    Central coordinator for replica management and data quality.

    This is the single source of truth for:
    - Emergency replica creation and failover
    - Manual replica lifecycle management
    - Data gap filling and deduplication
    - Agent coordination
    """

    def __init__(self):
        self.running = False
        self.monitor_thread = None
        self.data_quality_thread = None

        # Tracking state
        self.agent_states = {}  # agent_id -> state info
        self.emergency_active = {}  # agent_id -> emergency context

        logger.info("ReplicaCoordinator initialized")

    def start(self):
        """Start the coordinator background services"""
        if self.running:
            logger.warning("ReplicaCoordinator already running")
            return

        self.running = True

        # Start monitoring thread for emergency handling
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="ReplicaCoordinator-Monitor"
        )
        self.monitor_thread.start()

        # Start data quality thread
        self.data_quality_thread = threading.Thread(
            target=self._data_quality_loop,
            daemon=True,
            name="ReplicaCoordinator-DataQuality"
        )
        self.data_quality_thread.start()

        logger.info("✓ ReplicaCoordinator started (monitor + data quality)")

    def stop(self):
        """Stop the coordinator"""
        self.running = False
        logger.info("ReplicaCoordinator stopped")

    # =========================================================================
    # EMERGENCY REPLICA ORCHESTRATION (Auto-Switch Mode)
    # =========================================================================

    def _monitor_loop(self):
        """
        Main monitoring loop for emergency replica orchestration.

        Responsibilities:
        1. Monitor agents for interruption signals
        2. Create emergency replicas on rebalance
        3. Promote replicas on termination
        4. Hand back control to ML models after emergency
        5. Maintain manual replicas when enabled
        """
        logger.info("Emergency monitor loop started")

        while self.running:
            try:
                # Get all active agents
                agents = execute_query("""
                    SELECT id, client_id, instance_id, auto_switch_enabled,
                           manual_replica_enabled, replica_count, current_replica_id,
                           last_interruption_signal, last_heartbeat_at
                    FROM agents
                    WHERE enabled = TRUE AND status = 'online'
                """, fetch=True)

                for agent in (agents or []):
                    agent_id = agent['id']

                    # Handle auto-switch mode (emergency)
                    if agent['auto_switch_enabled']:
                        self._handle_auto_switch_mode(agent)

                    # Handle manual replica mode
                    elif agent['manual_replica_enabled']:
                        self._handle_manual_replica_mode(agent)

                time.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error(f"Monitor loop error: {e}", exc_info=True)
                time.sleep(30)

    def _handle_auto_switch_mode(self, agent: Dict):
        """
        Handle emergency replica orchestration for auto-switch mode.

        Flow:
        1. Monitor for interruption signals (via spot_interruption_events)
        2. On rebalance: Create replica in cheapest pool
        3. Replica stays until termination notice
        4. On termination: Promote replica, connect to central server
        5. Hand back control to ML models
        """
        agent_id = agent['id']

        # Check for recent interruption events
        recent_interruption = execute_query("""
            SELECT signal_type, detected_at, replica_id, failover_completed
            FROM spot_interruption_events
            WHERE agent_id = %s
            ORDER BY detected_at DESC
            LIMIT 1
        """, (agent_id,), fetch_one=True)

        if not recent_interruption:
            # No interruption - normal operation
            # ML models have control
            return

        signal_type = recent_interruption['signal_type']
        detected_at = recent_interruption['detected_at']
        replica_id = recent_interruption['replica_id']
        failover_completed = recent_interruption['failover_completed']

        # Check if this is a recent event (within last 2 hours)
        if detected_at and (datetime.now() - detected_at).total_seconds() > 7200:
            # Old event - emergency is over, ML has control
            return

        # EMERGENCY MODE ACTIVE
        logger.info(f"Emergency mode active for agent {agent_id}: {signal_type}")

        if signal_type == 'rebalance-recommendation':
            # Rebalance detected - ensure replica exists
            if not replica_id or not agent['current_replica_id']:
                logger.warning(f"Rebalance detected but no replica for agent {agent_id}")
                # Replica should have been created by endpoint, but double-check
                self._ensure_replica_exists(agent)
            else:
                # Replica exists - monitor its readiness
                replica = execute_query("""
                    SELECT status, sync_status, state_transfer_progress
                    FROM replica_instances
                    WHERE id = %s AND is_active = TRUE
                """, (replica_id,), fetch_one=True)

                if replica:
                    logger.info(f"Replica {replica_id} status: {replica['status']}, "
                               f"sync: {replica['sync_status']}, "
                               f"progress: {replica['state_transfer_progress']}%")

        elif signal_type == 'termination-notice':
            # Termination imminent - failover should have occurred
            if not failover_completed:
                logger.critical(f"Termination notice but failover NOT completed for agent {agent_id}!")
                # Try to complete failover
                self._complete_emergency_failover(agent, replica_id)
            else:
                logger.info(f"Failover completed for agent {agent_id}, handing back to ML models")
                # Emergency is over - ML models can take over
                # Mark emergency as complete
                execute_query("""
                    UPDATE spot_interruption_events
                    SET metadata = JSON_SET(COALESCE(metadata, '{}'), '$.emergency_complete', TRUE)
                    WHERE agent_id = %s AND detected_at = %s
                """, (agent_id, detected_at))

    def _ensure_replica_exists(self, agent: Dict):
        """Ensure replica exists for agent during emergency"""
        agent_id = agent['id']

        # Check if replica already exists
        existing_replica = execute_query("""
            SELECT id FROM replica_instances
            WHERE agent_id = %s AND is_active = TRUE
            AND status NOT IN ('terminated', 'promoted')
        """, (agent_id,), fetch_one=True)

        if existing_replica:
            return existing_replica['id']

        # No replica - need to create one
        logger.warning(f"Creating emergency replica for agent {agent_id}")

        # Get instance details
        instance = execute_query("""
            SELECT instance_type, region, current_pool_id
            FROM instances
            WHERE agent_id = %s AND is_active = TRUE
        """, (agent_id,), fetch_one=True)

        if not instance:
            logger.error(f"Cannot create replica - no active instance for agent {agent_id}")
            return None

        # Find cheapest pool
        cheapest_pool = execute_query("""
            SELECT sp.id, sp.az, psc.spot_price
            FROM spot_pools sp
            LEFT JOIN (
                SELECT pool_id, spot_price,
                       ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY time_bucket DESC) as rn
                FROM pricing_snapshots_clean
            ) psc ON psc.pool_id = sp.id AND psc.rn = 1
            WHERE sp.instance_type = %s
              AND sp.region = %s
              AND sp.id != %s
            ORDER BY psc.spot_price ASC
            LIMIT 1
        """, (instance['instance_type'], instance['region'], instance['current_pool_id']), fetch_one=True)

        if not cheapest_pool:
            logger.error(f"No alternative pool found for agent {agent_id}")
            return None

        # Create replica record
        import uuid
        replica_id = str(uuid.uuid4())

        execute_query("""
            INSERT INTO replica_instances (
                id, agent_id, instance_id, replica_type, pool_id,
                instance_type, region, az, status, created_by,
                parent_instance_id, hourly_cost, is_active
            ) VALUES (
                %s, %s, %s, 'automatic-rebalance', %s,
                %s, %s, %s, 'launching', 'coordinator',
                %s, %s, TRUE
            )
        """, (
            replica_id, agent_id, f"emergency-{replica_id[:8]}",
            cheapest_pool['id'], instance['instance_type'],
            instance['region'], cheapest_pool['az'],
            agent['instance_id'], cheapest_pool['spot_price']
        ))

        # Update agent
        execute_query("""
            UPDATE agents
            SET current_replica_id = %s, replica_count = replica_count + 1
            WHERE id = %s
        """, (replica_id, agent_id))

        logger.info(f"✓ Created emergency replica {replica_id} for agent {agent_id}")
        return replica_id

    def _complete_emergency_failover(self, agent: Dict, replica_id: str):
        """Complete emergency failover by promoting replica"""
        agent_id = agent['id']

        if not replica_id:
            logger.error(f"Cannot complete failover - no replica_id for agent {agent_id}")
            return False

        # Check replica status
        replica = execute_query("""
            SELECT status, sync_status FROM replica_instances
            WHERE id = %s AND is_active = TRUE
        """, (replica_id,), fetch_one=True)

        if not replica:
            logger.error(f"Cannot complete failover - replica {replica_id} not found")
            return False

        if replica['status'] not in ('ready', 'syncing'):
            logger.warning(f"Replica {replica_id} not ready (status: {replica['status']}), "
                          f"but termination imminent - promoting anyway")

        # Promote replica
        import uuid
        new_instance_id = str(uuid.uuid4())

        execute_query("""
            INSERT INTO instances (
                id, client_id, instance_type, region, az,
                current_pool_id, current_mode, is_active, installed_at
            )
            SELECT
                %s, a.client_id, ri.instance_type, ri.region, ri.az,
                ri.pool_id, 'spot', TRUE, NOW()
            FROM replica_instances ri
            JOIN agents a ON ri.agent_id = a.id
            WHERE ri.id = %s
        """, (new_instance_id, replica_id))

        # Update agent
        execute_query("""
            UPDATE agents
            SET instance_id = %s,
                current_replica_id = NULL,
                last_failover_at = NOW(),
                interruption_handled_count = interruption_handled_count + 1
            WHERE id = %s
        """, (new_instance_id, agent_id))

        # Mark replica as promoted
        execute_query("""
            UPDATE replica_instances
            SET status = 'promoted',
                promoted_at = NOW(),
                failover_completed_at = NOW()
            WHERE id = %s
        """, (replica_id,))

        # Update interruption event
        execute_query("""
            UPDATE spot_interruption_events
            SET failover_completed = TRUE,
                success = TRUE
            WHERE agent_id = %s AND replica_id = %s
            ORDER BY detected_at DESC
            LIMIT 1
        """, (agent_id, replica_id))

        logger.info(f"✓ Emergency failover completed for agent {agent_id}")
        return True

    def _handle_manual_replica_mode(self, agent: Dict):
        """
        Handle manual replica mode - continuous replica maintenance.

        Flow:
        1. Ensure exactly ONE replica exists at all times
        2. If replica is terminated/promoted, create new one immediately
        3. Continue loop until manual_replica_enabled = FALSE
        """
        agent_id = agent['id']
        replica_count = agent['replica_count'] or 0

        # Check for active replicas
        active_replicas = execute_query("""
            SELECT id, status FROM replica_instances
            WHERE agent_id = %s
              AND is_active = TRUE
              AND status NOT IN ('terminated', 'promoted')
        """, (agent_id,), fetch=True)

        active_count = len(active_replicas or [])

        if active_count == 0:
            # No active replica - create one
            logger.info(f"Manual mode: Creating replica for agent {agent_id}")
            self._create_manual_replica(agent)

        elif active_count > 1:
            # Too many replicas - should only be 1
            logger.warning(f"Manual mode: Agent {agent_id} has {active_count} replicas, should be 1")
            # Keep the newest, terminate others
            newest = active_replicas[0]
            for replica in active_replicas[1:]:
                execute_query("""
                    UPDATE replica_instances
                    SET is_active = FALSE, status = 'terminated', terminated_at = NOW()
                    WHERE id = %s
                """, (replica['id'],))

        # Check if user promoted a replica
        recently_promoted = execute_query("""
            SELECT id, promoted_at FROM replica_instances
            WHERE agent_id = %s
              AND status = 'promoted'
              AND promoted_at >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
        """, (agent_id,), fetch_one=True)

        if recently_promoted:
            # User just promoted a replica - create new one for the new primary
            logger.info(f"Manual mode: Replica promoted for agent {agent_id}, creating new replica")
            time.sleep(2)  # Brief delay to let promotion complete
            self._create_manual_replica(agent)

    def _create_manual_replica(self, agent: Dict):
        """Create manual replica in cheapest available pool"""
        agent_id = agent['id']

        # Get instance details
        instance = execute_query("""
            SELECT instance_type, region, current_pool_id
            FROM instances
            WHERE agent_id = %s AND is_active = TRUE
        """, (agent_id,), fetch_one=True)

        if not instance:
            logger.error(f"Cannot create manual replica - no active instance for agent {agent_id}")
            return None

        # Find cheapest pool (different from current)
        pools = execute_query("""
            SELECT sp.id, sp.az, psc.spot_price
            FROM spot_pools sp
            LEFT JOIN (
                SELECT pool_id, spot_price,
                       ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY time_bucket DESC) as rn
                FROM pricing_snapshots_clean
            ) psc ON psc.pool_id = sp.id AND psc.rn = 1
            WHERE sp.instance_type = %s
              AND sp.region = %s
            ORDER BY psc.spot_price ASC
            LIMIT 2
        """, (instance['instance_type'], instance['region']), fetch=True)

        if not pools:
            logger.error(f"No pools found for agent {agent_id}")
            return None

        # Select pool (if current is cheapest, use 2nd cheapest)
        target_pool = None
        for pool in pools:
            if pool['id'] != instance['current_pool_id']:
                target_pool = pool
                break

        if not target_pool and len(pools) > 1:
            target_pool = pools[1]  # Use second cheapest
        elif not target_pool:
            target_pool = pools[0]  # Use only available pool

        # Create replica
        import uuid
        replica_id = str(uuid.uuid4())

        execute_query("""
            INSERT INTO replica_instances (
                id, agent_id, instance_id, replica_type, pool_id,
                instance_type, region, az, status, created_by,
                parent_instance_id, hourly_cost, is_active
            ) VALUES (
                %s, %s, %s, 'manual', %s,
                %s, %s, %s, 'launching', 'coordinator',
                %s, %s, TRUE
            )
        """, (
            replica_id, agent_id, f"manual-{replica_id[:8]}",
            target_pool['id'], instance['instance_type'],
            instance['region'], target_pool['az'],
            agent['instance_id'], target_pool['spot_price']
        ))

        # Update agent
        execute_query("""
            UPDATE agents
            SET current_replica_id = %s, replica_count = 1
            WHERE id = %s
        """, (replica_id, agent_id))

        logger.info(f"✓ Created manual replica {replica_id} for agent {agent_id} in pool {target_pool['id']}")
        return replica_id

    # =========================================================================
    # DATA QUALITY MANAGEMENT - Gap Filling & Deduplication
    # =========================================================================

    def _data_quality_loop(self):
        """
        Data quality management loop.

        Responsibilities:
        1. Compare data from primary and replica agents
        2. Fill gaps where data is missing
        3. Deduplicate overlapping data (keep one)
        4. Interpolate missing data using neighboring values
        5. Ensure clean, complete database
        """
        logger.info("Data quality loop started")

        while self.running:
            try:
                # Process pricing data
                self._process_pricing_data_quality()

                time.sleep(300)  # Run every 5 minutes

            except Exception as e:
                logger.error(f"Data quality loop error: {e}", exc_info=True)
                time.sleep(60)

    def _process_pricing_data_quality(self):
        """
        Process pricing data for quality assurance.

        Steps:
        1. Find time buckets with data from multiple sources
        2. Deduplicate by keeping highest confidence score
        3. Find gaps (missing time buckets)
        4. Fill gaps using interpolation
        """
        # Get all pools with recent data
        pools = execute_query("""
            SELECT DISTINCT pool_id
            FROM pricing_snapshots_clean
            WHERE time_bucket >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """, fetch=True)

        for pool in (pools or []):
            pool_id = pool['pool_id']
            self._deduplicate_pool_data(pool_id)
            self._fill_pool_gaps(pool_id)

    def _deduplicate_pool_data(self, pool_id: int):
        """
        Remove duplicate entries for same pool+time_bucket.
        Keep entry with highest confidence score.
        """
        # Find duplicates (same pool + time_bucket)
        duplicates = execute_query("""
            SELECT time_bucket, COUNT(*) as count
            FROM pricing_snapshots_clean
            WHERE pool_id = %s
              AND time_bucket >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY time_bucket
            HAVING count > 1
        """, (pool_id,), fetch=True)

        if not duplicates:
            return

        logger.info(f"Found {len(duplicates)} duplicate time buckets for pool {pool_id}")

        for dup in duplicates:
            time_bucket = dup['time_bucket']

            # Get all entries for this time bucket
            entries = execute_query("""
                SELECT id, confidence_score, data_source, source_type
                FROM pricing_snapshots_clean
                WHERE pool_id = %s AND time_bucket = %s
                ORDER BY confidence_score DESC, id ASC
            """, (pool_id, time_bucket), fetch=True)

            if len(entries) <= 1:
                continue

            # Keep first (highest confidence), delete rest
            keep_id = entries[0]['id']
            delete_ids = [e['id'] for e in entries[1:]]

            for delete_id in delete_ids:
                execute_query("""
                    DELETE FROM pricing_snapshots_clean WHERE id = %s
                """, (delete_id,))

            logger.debug(f"Deduplicated time_bucket {time_bucket}: kept id={keep_id}, deleted {len(delete_ids)} entries")

    def _fill_pool_gaps(self, pool_id: int):
        """
        Fill gaps in pricing data using interpolation.

        Strategy:
        - For small gaps (1-2 buckets): Linear interpolation
        - For larger gaps: Average of neighboring values
        - If no neighboring data: Use last known value
        """
        # Get all time buckets for last 24 hours
        start_time = datetime.now() - timedelta(hours=24)

        # Get existing data points
        data_points = execute_query("""
            SELECT time_bucket, spot_price, ondemand_price
            FROM pricing_snapshots_clean
            WHERE pool_id = %s
              AND time_bucket >= %s
            ORDER BY time_bucket ASC
        """, (pool_id, start_time), fetch=True)

        if not data_points or len(data_points) < 2:
            return  # Not enough data to interpolate

        # Generate expected time buckets (every 5 minutes)
        expected_buckets = []
        current_bucket = start_time.replace(minute=(start_time.minute // 5) * 5, second=0, microsecond=0)
        end_time = datetime.now()

        while current_bucket <= end_time:
            expected_buckets.append(current_bucket)
            current_bucket += timedelta(minutes=5)

        # Find missing buckets
        existing_times = {dp['time_bucket'] for dp in data_points}
        missing_buckets = [b for b in expected_buckets if b not in existing_times]

        if not missing_buckets:
            return  # No gaps

        logger.info(f"Filling {len(missing_buckets)} gaps for pool {pool_id}")

        # Sort data points by time
        sorted_data = sorted(data_points, key=lambda x: x['time_bucket'])

        for missing_time in missing_buckets:
            # Find neighboring data points
            before = None
            after = None

            for i, dp in enumerate(sorted_data):
                if dp['time_bucket'] < missing_time:
                    before = dp
                elif dp['time_bucket'] > missing_time and not after:
                    after = dp
                    break

            # Interpolate
            if before and after:
                # Linear interpolation
                time_diff = (after['time_bucket'] - before['time_bucket']).total_seconds()
                time_to_missing = (missing_time - before['time_bucket']).total_seconds()
                ratio = time_to_missing / time_diff

                spot_price = before['spot_price'] + (after['spot_price'] - before['spot_price']) * ratio
                ondemand_price = before['ondemand_price'] if before['ondemand_price'] else after['ondemand_price']

                confidence = 0.7  # Interpolated data has lower confidence
                method = 'linear'

            elif before:
                # Use last known value
                spot_price = before['spot_price']
                ondemand_price = before['ondemand_price']
                confidence = 0.5
                method = 'last-known'

            elif after:
                # Use next known value
                spot_price = after['spot_price']
                ondemand_price = after['ondemand_price']
                confidence = 0.5
                method = 'next-known'
            else:
                continue  # No data to interpolate from

            # Insert interpolated data
            bucket_start = missing_time
            bucket_end = missing_time + timedelta(minutes=5)

            # Get pool details
            pool_info = execute_query("""
                SELECT instance_type, region, az
                FROM spot_pools WHERE id = %s
            """, (pool_id,), fetch_one=True)

            if pool_info:
                execute_query("""
                    INSERT INTO pricing_snapshots_clean (
                        pool_id, instance_type, region, az,
                        spot_price, ondemand_price,
                        time_bucket, bucket_start, bucket_end,
                        source_type, confidence_score, data_source
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, 'interpolated', %s, 'interpolated'
                    )
                """, (
                    pool_id, pool_info['instance_type'], pool_info['region'], pool_info['az'],
                    spot_price, ondemand_price,
                    missing_time, bucket_start, bucket_end,
                    confidence
                ))

                logger.debug(f"Filled gap at {missing_time} using {method} interpolation")

        logger.info(f"✓ Filled {len(missing_buckets)} gaps for pool {pool_id}")


# Global coordinator instance
coordinator = ReplicaCoordinator()


def start_replica_coordinator():
    """Start the replica coordinator (called from backend initialization)"""
    coordinator.start()


def stop_replica_coordinator():
    """Stop the replica coordinator"""
    coordinator.stop()
