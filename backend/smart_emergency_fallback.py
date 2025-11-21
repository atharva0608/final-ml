"""
Smart Emergency Fallback System
=================================

This component is the heart of the AWS Spot Optimizer's reliability system.
It handles all data coming from agents, ensures data quality, manages replicas,
and provides zero-downtime failover during spot interruptions.

Key Features:
1. Intercepts and processes all agent data
2. Passive monitoring until AWS interruption signals
3. Automatic replica creation in cheapest/safest pools
4. Data quality assurance (deduplication, gap filling)
5. Manual replica mode with continuous hot standby
6. Works independently of ML models (fallback when models fail)
7. Mutual exclusion between auto and manual modes

Author: AWS Spot Optimizer Team
Version: 2.0.0
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SmartEmergencyFallback:
    """
    Smart Emergency Fallback (SEF) Component

    This component sits between agents and the database, processing all incoming
    data and handling emergency situations automatically.

    Architecture:

    Agent (Primary) ──┐
                      ├──> SEF Component ──> Database
    Agent (Replica) ──┘      │
                             │
                             ├──> Replica Manager
                             ├──> Data Quality Processor
                             └──> Gap Filler
    """

    def __init__(self, db_connection):
        """
        Initialize Smart Emergency Fallback System

        Args:
            db_connection: MySQL database connection for storing/retrieving data
        """
        self.db = db_connection

        # State tracking
        self.active_agents = {}  # agent_id -> agent_info
        self.agent_replicas = {}  # agent_id -> replica_info
        self.manual_mode_agents = set()  # agents with manual replica mode enabled

        # Data quality settings
        self.data_retention_window = 300  # Keep 5 minutes of recent data for comparison
        self.recent_data_buffer = {}  # Temporary buffer for deduplication
        self.gap_detection_threshold = 600  # Flag gap if >10 minutes missing
        self.interpolation_max_gap = 1800  # Max 30 min gap to interpolate

        # Replica management settings
        self.rebalance_risk_threshold = 0.30  # Create replica if risk >30%
        self.termination_grace_period = 120  # 2 minutes for emergency actions

        logger.info("Smart Emergency Fallback System initialized")

    # =========================================================================
    # PART 1: DATA INTERCEPTION AND QUALITY ASSURANCE
    # =========================================================================

    def process_incoming_data(self, agent_id: str, data_type: str, payload: dict) -> dict:
        """
        Main entry point for ALL data from agents.

        This function intercepts every piece of data before it reaches the database.
        It performs:
        1. Data validation
        2. Deduplication (when both primary and replica report)
        3. Temporary buffering for comparison
        4. Gap detection

        Args:
            agent_id: Unique identifier of the agent sending data
            data_type: Type of data (pricing, heartbeat, status, etc.)
            payload: The actual data payload

        Returns:
            Processed and validated data ready for database insertion
        """
        logger.debug(f"SEF: Processing {data_type} data from agent {agent_id}")

        # Step 1: Validate incoming data
        if not self._validate_data(data_type, payload):
            logger.warning(f"SEF: Invalid data from agent {agent_id}, discarding")
            return {"status": "rejected", "reason": "validation_failed"}

        # Step 2: Check if this agent has a replica
        has_replica = agent_id in self.agent_replicas
        replica_id = self.agent_replicas.get(agent_id, {}).get('replica_id')

        # Step 3: Buffer data for deduplication comparison
        if has_replica:
            buffered_data = self._buffer_for_comparison(agent_id, data_type, payload)

            # If we have data from both primary and replica, compare and deduplicate
            if buffered_data['has_both']:
                processed_data = self._compare_and_deduplicate(
                    buffered_data['primary_data'],
                    buffered_data['replica_data']
                )
                return processed_data
            else:
                # Wait for replica data (will be processed when replica reports)
                return {"status": "buffered", "waiting_for": "replica_data"}

        # Step 4: No replica, process immediately
        processed_data = self._prepare_for_database(agent_id, data_type, payload)

        # Step 5: Detect gaps and fill if needed
        self._detect_and_fill_gaps(agent_id, data_type, processed_data)

        return processed_data

    def _validate_data(self, data_type: str, payload: dict) -> bool:
        """
        Validate incoming data structure and values.

        Returns:
            True if data is valid, False otherwise
        """
        required_fields = {
            'pricing': ['timestamp', 'spot_price', 'pool_id'],
            'heartbeat': ['timestamp', 'status'],
            'interruption': ['signal_type', 'timestamp']
        }

        if data_type not in required_fields:
            return True  # Unknown type, let it pass

        # Check all required fields are present
        for field in required_fields[data_type]:
            if field not in payload:
                logger.error(f"Missing required field '{field}' in {data_type} data")
                return False

        # Additional validation for pricing data
        if data_type == 'pricing':
            if payload['spot_price'] <= 0 or payload['spot_price'] > 100:
                logger.error(f"Invalid spot price: {payload['spot_price']}")
                return False

        return True

    def _buffer_for_comparison(self, agent_id: str, data_type: str, payload: dict) -> dict:
        """
        Buffer data from both primary and replica for comparison.

        This ensures we have data from both sources before processing,
        allowing us to deduplicate and choose the best data.

        Returns:
            dict with 'has_both', 'primary_data', 'replica_data'
        """
        timestamp = payload.get('timestamp', time.time())
        buffer_key = f"{agent_id}:{data_type}:{int(timestamp)}"

        if buffer_key not in self.recent_data_buffer:
            self.recent_data_buffer[buffer_key] = {
                'primary': None,
                'replica': None,
                'created_at': time.time()
            }

        # Determine if this is from primary or replica
        is_replica = payload.get('is_replica', False)

        if is_replica:
            self.recent_data_buffer[buffer_key]['replica'] = payload
        else:
            self.recent_data_buffer[buffer_key]['primary'] = payload

        # Check if we have both
        has_both = (
            self.recent_data_buffer[buffer_key]['primary'] is not None and
            self.recent_data_buffer[buffer_key]['replica'] is not None
        )

        return {
            'has_both': has_both,
            'primary_data': self.recent_data_buffer[buffer_key]['primary'],
            'replica_data': self.recent_data_buffer[buffer_key]['replica']
        }

    def _compare_and_deduplicate(self, primary_data: dict, replica_data: dict) -> dict:
        """
        Compare data from primary and replica agents, deduplicate and choose best.

        Strategy:
        1. If data is identical -> use primary (less overhead)
        2. If data differs slightly -> average numeric values
        3. If one is clearly better (more complete) -> use that one
        4. Always prefer primary unless replica has better data quality

        Args:
            primary_data: Data from primary agent
            replica_data: Data from replica agent

        Returns:
            Single deduplicated data record
        """
        logger.debug("SEF: Comparing data from primary and replica")

        # For pricing data, compare spot prices
        if 'spot_price' in primary_data and 'spot_price' in replica_data:
            primary_price = primary_data['spot_price']
            replica_price = replica_data['spot_price']

            # If prices are identical, use primary
            if abs(primary_price - replica_price) < 0.000001:
                logger.debug("SEF: Prices identical, using primary data")
                return self._prepare_for_database(
                    primary_data.get('agent_id'),
                    'pricing',
                    primary_data
                )

            # If prices differ, average them and flag for review
            averaged_price = (primary_price + replica_price) / 2.0
            logger.info(f"SEF: Price discrepancy detected. Primary: ${primary_price:.6f}, "
                       f"Replica: ${replica_price:.6f}, Using average: ${averaged_price:.6f}")

            # Create merged data with averaged price
            merged_data = primary_data.copy()
            merged_data['spot_price'] = averaged_price
            merged_data['data_quality_flag'] = 'averaged_dual_source'
            merged_data['primary_price'] = primary_price
            merged_data['replica_price'] = replica_price

            return self._prepare_for_database(
                primary_data.get('agent_id'),
                'pricing',
                merged_data
            )

        # For non-pricing data, prefer primary
        return self._prepare_for_database(
            primary_data.get('agent_id'),
            primary_data.get('type', 'unknown'),
            primary_data
        )

    def _detect_and_fill_gaps(self, agent_id: str, data_type: str, current_data: dict):
        """
        Detect gaps in data timeline and fill them using interpolation.

        This ensures continuous, gap-free data even when:
        - Agent loses connection temporarily
        - Agent is switching between instances
        - Replica promotion causes brief data loss

        Strategy:
        1. Query last data point timestamp
        2. Calculate gap duration
        3. If gap < threshold, interpolate missing values
        4. Insert interpolated data points
        """
        if data_type != 'pricing':
            return  # Only fill gaps for pricing data

        current_timestamp = current_data.get('timestamp', time.time())

        # Get last data point for this agent
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("""
            SELECT timestamp, spot_price, pool_id
            FROM pricing_reports
            WHERE agent_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (agent_id,))

        last_data = cursor.fetchone()
        cursor.close()

        if not last_data:
            return  # No previous data, can't detect gaps

        last_timestamp = last_data['timestamp']
        gap_duration = current_timestamp - last_timestamp

        # Check if gap exists
        if gap_duration > self.gap_detection_threshold:
            logger.warning(f"SEF: Gap detected for agent {agent_id}: "
                          f"{gap_duration:.0f} seconds")

            # Only interpolate if gap is not too large
            if gap_duration <= self.interpolation_max_gap:
                self._fill_gap_with_interpolation(
                    agent_id,
                    last_data,
                    current_data,
                    gap_duration
                )
            else:
                logger.error(f"SEF: Gap too large ({gap_duration:.0f}s) to interpolate, "
                           "flagging for manual review")
                # Insert a flag in the database
                self._flag_data_quality_issue(agent_id, 'large_gap', gap_duration)

    def _fill_gap_with_interpolation(self, agent_id: str, start_data: dict,
                                     end_data: dict, gap_duration: float):
        """
        Fill data gap using linear interpolation.

        For pricing data, we interpolate spot prices between the last known
        price and the current price, creating artificial data points at
        regular intervals (e.g., every 5 minutes).

        Args:
            agent_id: Agent identifier
            start_data: Last known data point before gap
            end_data: First data point after gap
            gap_duration: Size of gap in seconds
        """
        logger.info(f"SEF: Filling {gap_duration:.0f}s gap with interpolation for agent {agent_id}")

        # Configuration
        interpolation_interval = 300  # Insert point every 5 minutes
        num_points = int(gap_duration / interpolation_interval)

        if num_points <= 0:
            return  # Gap too small to interpolate

        # Extract values to interpolate
        start_price = start_data['spot_price']
        end_price = end_data['spot_price']
        start_time = start_data['timestamp']

        # Create interpolated points
        cursor = self.db.cursor()

        for i in range(1, num_points + 1):
            # Linear interpolation
            ratio = i / (num_points + 1)
            interpolated_price = start_price + (end_price - start_price) * ratio
            interpolated_time = start_time + (interpolation_interval * i)

            # Insert interpolated data point
            try:
                cursor.execute("""
                    INSERT INTO pricing_reports
                    (agent_id, timestamp, spot_price, pool_id, data_quality_flag, source_type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    agent_id,
                    interpolated_time,
                    interpolated_price,
                    start_data['pool_id'],
                    'interpolated',
                    'smart_emergency_fallback'
                ))
            except Exception as e:
                logger.error(f"SEF: Error inserting interpolated data: {e}")

        self.db.commit()
        cursor.close()

        logger.info(f"SEF: Inserted {num_points} interpolated data points")

    def _prepare_for_database(self, agent_id: str, data_type: str, payload: dict) -> dict:
        """
        Prepare processed data for database insertion.

        Adds metadata about processing:
        - Processing timestamp
        - Data quality flags
        - Source information
        """
        processed = payload.copy()
        processed['processed_by'] = 'smart_emergency_fallback'
        processed['processed_at'] = time.time()
        processed['agent_id'] = agent_id
        processed['type'] = data_type

        return processed

    def _flag_data_quality_issue(self, agent_id: str, issue_type: str, details: any):
        """
        Flag data quality issues for monitoring and manual review.
        """
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO system_events
            (event_type, severity, agent_id, message, metadata)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            'data_quality_issue',
            'warning',
            agent_id,
            f"Data quality issue detected: {issue_type}",
            f'{{"issue_type": "{issue_type}", "details": "{details}"}}'
        ))
        self.db.commit()
        cursor.close()

    # =========================================================================
    # PART 2: REPLICA MANAGEMENT (AUTOMATIC MODE)
    # =========================================================================

    def handle_rebalance_recommendation(self, agent_id: str, signal_data: dict) -> dict:
        """
        Handle AWS Rebalance Recommendation (10-15 minute warning).

        This is the first level of interruption warning. We use this time to:
        1. Assess risk of actual termination
        2. Create replica if risk is high enough
        3. Keep replica in hot standby
        4. Monitor for termination notice

        SEF takes control here and makes autonomous decisions even if ML models fail.

        Args:
            agent_id: Agent receiving the rebalance signal
            signal_data: Information about the rebalance signal

        Returns:
            Action taken (create_replica, monitor, ignore)
        """
        logger.warning(f"SEF: Rebalance recommendation received for agent {agent_id}")

        # Check if agent is in manual mode (manual mode has priority)
        if agent_id in self.manual_mode_agents:
            logger.info(f"SEF: Agent {agent_id} in manual mode, automatic replica disabled")
            return {"action": "skipped", "reason": "manual_mode_active"}

        # Step 1: Calculate interruption risk
        risk_score = self._calculate_interruption_risk(agent_id, signal_data)

        logger.info(f"SEF: Calculated interruption risk for {agent_id}: {risk_score:.2%}")

        # Step 2: Decide whether to create replica
        if risk_score >= self.rebalance_risk_threshold:
            logger.warning(f"SEF: Risk threshold exceeded ({risk_score:.2%} >= "
                          f"{self.rebalance_risk_threshold:.2%}), creating replica")

            # Step 3: Find cheapest safe pool for replica
            target_pool = self._find_safest_cheapest_pool(agent_id)

            # Step 4: Create replica
            replica_info = self._create_replica(agent_id, target_pool, reason='rebalance_recommendation')

            # Step 5: Track replica
            self.agent_replicas[agent_id] = replica_info

            # Step 6: Hand control back to ML model after replica is ready
            self._notify_replica_ready(agent_id, replica_info)

            return {
                "action": "created_replica",
                "replica_id": replica_info['replica_id'],
                "pool_id": target_pool['pool_id'],
                "risk_score": risk_score
            }
        else:
            logger.info(f"SEF: Risk below threshold, monitoring situation")
            return {
                "action": "monitor",
                "risk_score": risk_score,
                "reason": "risk_below_threshold"
            }

    def handle_termination_notice(self, agent_id: str, termination_data: dict) -> dict:
        """
        Handle AWS Termination Notice (2 minute warning).

        This is CRITICAL. We have 2 minutes to:
        1. Check if replica exists
        2. If yes: Promote replica to primary (instant failover)
        3. If no: Emergency snapshot and launch
        4. Update database and routing

        SEF operates completely autonomously here - no time for ML model decisions.

        Args:
            agent_id: Agent being terminated
            termination_data: Termination details

        Returns:
            Failover result
        """
        logger.critical(f"SEF: TERMINATION NOTICE for agent {agent_id}! "
                       f"Executing emergency failover...")

        start_time = time.time()

        # Step 1: Check for existing replica
        if agent_id in self.agent_replicas:
            replica_info = self.agent_replicas[agent_id]
            logger.info(f"SEF: Replica exists ({replica_info['replica_id']}), "
                       "performing instant failover")

            # Step 2: Promote replica to primary
            result = self._promote_replica_to_primary(agent_id, replica_info)

            # Step 3: Update agent registration
            self._update_agent_instance(agent_id, replica_info['instance_id'])

            # Step 4: Clean up old instance (will be terminated by AWS)
            self._mark_instance_terminated(termination_data.get('instance_id'))

            # Step 5: Remove from replicas dict (it's now primary)
            del self.agent_replicas[agent_id]

            failover_time = time.time() - start_time

            logger.info(f"SEF: Failover completed in {failover_time:.2f}s")

            return {
                "action": "replica_promoted",
                "new_instance_id": replica_info['instance_id'],
                "failover_time_seconds": failover_time,
                "data_loss": False
            }
        else:
            logger.error(f"SEF: No replica exists for agent {agent_id}! "
                        "Executing emergency snapshot...")

            # Step 2: Emergency snapshot and launch (slower path)
            result = self._emergency_snapshot_and_launch(agent_id, termination_data)

            failover_time = time.time() - start_time

            logger.warning(f"SEF: Emergency recovery completed in {failover_time:.2f}s")

            return {
                "action": "emergency_recovery",
                "new_instance_id": result['instance_id'],
                "failover_time_seconds": failover_time,
                "data_loss": result.get('data_loss', True)
            }

    def _calculate_interruption_risk(self, agent_id: str, signal_data: dict) -> float:
        """
        Calculate probability of actual termination following rebalance signal.

        Factors considered:
        1. Historical interruption rate for this pool
        2. Time of day patterns
        3. Instance age
        4. Current spot price trend

        Returns:
            Risk score between 0.0 and 1.0
        """
        risk_factors = []

        # Factor 1: Pool interruption history
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("""
            SELECT COUNT(*) as interruptions
            FROM spot_interruption_events
            WHERE pool_id = (SELECT current_pool_id FROM agents WHERE id = %s)
            AND detected_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
        """, (agent_id,))

        result = cursor.fetchone()
        interruption_count = result['interruptions'] if result else 0

        # More interruptions = higher risk
        interruption_risk = min(interruption_count / 10.0, 1.0)  # Cap at 1.0
        risk_factors.append(interruption_risk * 0.4)  # 40% weight

        # Factor 2: Instance age (older instances more likely to be reclaimed)
        cursor.execute("""
            SELECT TIMESTAMPDIFF(SECOND, installed_at, NOW()) as age_seconds
            FROM agents WHERE id = %s
        """, (agent_id,))

        result = cursor.fetchone()
        if result and result['age_seconds']:
            age_hours = result['age_seconds'] / 3600.0
            # Risk increases with age, peaks around 8-12 hours
            age_risk = min(age_hours / 12.0, 1.0)
            risk_factors.append(age_risk * 0.3)  # 30% weight

        # Factor 3: Spot price volatility (rising prices = higher risk)
        cursor.execute("""
            SELECT spot_price
            FROM pricing_reports
            WHERE agent_id = %s
            ORDER BY timestamp DESC
            LIMIT 10
        """, (agent_id,))

        prices = [row['spot_price'] for row in cursor.fetchall()]
        if len(prices) >= 2:
            price_trend = (prices[0] - prices[-1]) / prices[-1]  # % change
            volatility_risk = max(0.0, price_trend)  # Rising = risky
            risk_factors.append(min(volatility_risk, 1.0) * 0.3)  # 30% weight

        cursor.close()

        # Combine risk factors
        total_risk = sum(risk_factors) if risk_factors else 0.5  # Default 50% if no data

        return total_risk

    def _find_safest_cheapest_pool(self, agent_id: str) -> dict:
        """
        Find the safest AND cheapest pool for replica.

        Balances two goals:
        1. Low interruption risk (safety)
        2. Low cost (efficiency)

        Returns:
            Pool information with pool_id, price, safety_score
        """
        cursor = self.db.cursor(dictionary=True)

        # Get agent's instance type and region
        cursor.execute("""
            SELECT instance_type, region
            FROM agents
            WHERE id = %s
        """, (agent_id,))

        agent_info = cursor.fetchone()
        if not agent_info:
            raise ValueError(f"Agent {agent_id} not found")

        # Find pools with same instance type, ranked by safety and price
        cursor.execute("""
            SELECT
                sp.id as pool_id,
                sp.az,
                (SELECT price FROM spot_price_snapshots sps
                 WHERE sps.pool_id = sp.id
                 ORDER BY captured_at DESC LIMIT 1) as current_price,
                COALESCE(
                    (SELECT reliability_score FROM pool_reliability_metrics prm
                     WHERE prm.pool_id = sp.id
                     ORDER BY period_start DESC LIMIT 1),
                    100.0
                ) as safety_score
            FROM spot_pools sp
            WHERE sp.instance_type = %s
            AND sp.region = %s
            AND sp.is_active = TRUE
            HAVING current_price IS NOT NULL
            ORDER BY safety_score DESC, current_price ASC
            LIMIT 5
        """, (agent_info['instance_type'], agent_info['region']))

        pools = cursor.fetchall()
        cursor.close()

        if not pools:
            raise ValueError(f"No available pools for instance type {agent_info['instance_type']}")

        # Pick the best pool (highest safety, lowest price)
        best_pool = pools[0]

        logger.info(f"SEF: Selected pool {best_pool['pool_id']} for replica. "
                   f"Price: ${best_pool['current_price']:.6f}, "
                   f"Safety: {best_pool['safety_score']:.1f}/100")

        return best_pool

    def _create_replica(self, agent_id: str, target_pool: dict, reason: str) -> dict:
        """
        Create a replica instance in the target pool.

        This involves:
        1. Taking snapshot of current instance
        2. Launching new instance from snapshot
        3. Setting up state sync
        4. Registering replica in database

        Args:
            agent_id: Primary agent
            target_pool: Pool to launch replica in
            reason: Reason for replica creation

        Returns:
            Replica information
        """
        logger.info(f"SEF: Creating replica for agent {agent_id} in pool {target_pool['pool_id']}")

        # In a real implementation, this would:
        # 1. Call AWS EC2 API to create snapshot
        # 2. Launch new instance from snapshot in target AZ
        # 3. Configure networking and state sync

        # For this implementation, we'll simulate the process
        import uuid
        replica_id = f"replica-{uuid.uuid4().hex[:8]}"
        replica_instance_id = f"i-replica-{uuid.uuid4().hex[:8]}"

        # Register replica in database
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO replica_instances
            (id, agent_id, instance_id, replica_type, pool_id, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            replica_id,
            agent_id,
            replica_instance_id,
            'automatic-rebalance' if reason == 'rebalance_recommendation' else 'automatic-termination',
            target_pool['pool_id'],
            'launching',
            'smart_emergency_fallback'
        ))
        self.db.commit()
        cursor.close()

        replica_info = {
            'replica_id': replica_id,
            'instance_id': replica_instance_id,
            'pool_id': target_pool['pool_id'],
            'status': 'launching',
            'created_at': time.time(),
            'reason': reason
        }

        logger.info(f"SEF: Replica {replica_id} created successfully")

        return replica_info

    def _promote_replica_to_primary(self, agent_id: str, replica_info: dict) -> dict:
        """
        Promote replica to become the new primary instance.

        Steps:
        1. Update routing to direct traffic to replica
        2. Mark replica as promoted in database
        3. Update agent record with new instance ID
        4. Notify monitoring systems
        """
        logger.info(f"SEF: Promoting replica {replica_info['replica_id']} to primary")

        cursor = self.db.cursor()

        # Update replica status
        cursor.execute("""
            UPDATE replica_instances
            SET status = 'promoted', promoted_at = NOW()
            WHERE id = %s
        """, (replica_info['replica_id'],))

        # Log the promotion event
        cursor.execute("""
            INSERT INTO system_events
            (event_type, severity, agent_id, message, metadata)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            'replica_promoted',
            'info',
            agent_id,
            f"Replica {replica_info['replica_id']} promoted to primary",
            f'{{"replica_id": "{replica_info["replica_id"]}", "instance_id": "{replica_info["instance_id"]}"}}'
        ))

        self.db.commit()
        cursor.close()

        return {"status": "success", "new_instance_id": replica_info['instance_id']}

    def _update_agent_instance(self, agent_id: str, new_instance_id: str):
        """Update agent record with new instance ID after failover."""
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE agents
            SET instance_id = %s, last_failover_at = NOW()
            WHERE id = %s
        """, (new_instance_id, agent_id))
        self.db.commit()
        cursor.close()

    def _mark_instance_terminated(self, instance_id: str):
        """Mark old instance as terminated."""
        if not instance_id:
            return

        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE instances
            SET is_active = FALSE, terminated_at = NOW()
            WHERE id = %s
        """, (instance_id,))
        self.db.commit()
        cursor.close()

    def _emergency_snapshot_and_launch(self, agent_id: str, termination_data: dict) -> dict:
        """
        Emergency path when no replica exists.

        This is slower (30-60 seconds typically) and may result in brief data loss.
        """
        logger.warning("SEF: Executing emergency snapshot and launch (no replica available)")

        # Simulate emergency launch
        import uuid
        new_instance_id = f"i-emergency-{uuid.uuid4().hex[:8]}"

        return {
            "instance_id": new_instance_id,
            "data_loss": True,
            "recovery_time": 45.0  # Simulated
        }

    def _notify_replica_ready(self, agent_id: str, replica_info: dict):
        """
        Notify ML model that replica is ready and hand control back.

        SEF has done its job of ensuring availability. Now ML can make
        optimization decisions with the safety net in place.
        """
        logger.info(f"SEF: Replica ready for agent {agent_id}, handing control to ML model")

        # Update replica status
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE replica_instances
            SET status = 'ready', ready_at = NOW()
            WHERE id = %s
        """, (replica_info['replica_id'],))
        self.db.commit()
        cursor.close()

    # =========================================================================
    # PART 3: MANUAL REPLICA MODE
    # =========================================================================

    def enable_manual_replica_mode(self, agent_id: str) -> dict:
        """
        Enable manual replica mode for an agent.

        When manual mode is enabled:
        1. System continuously maintains a hot standby replica
        2. Auto-switch is completely disabled
        3. ML model decisions are ignored
        4. User can manually switch to replica at any time
        5. After switch, a new replica is automatically created
        6. Process repeats until manual mode is disabled

        IMPORTANT: Auto and manual modes are mutually exclusive.

        Args:
            agent_id: Agent to enable manual mode for

        Returns:
            Status and replica information
        """
        logger.info(f"SEF: Enabling manual replica mode for agent {agent_id}")

        # Step 1: Check if auto mode is enabled
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("""
            SELECT auto_switch_enabled, auto_terminate_enabled
            FROM agents
            WHERE id = %s
        """, (agent_id,))

        agent_info = cursor.fetchone()
        cursor.close()

        if not agent_info:
            return {"status": "error", "reason": "agent_not_found"}

        # Step 2: Enforce mutual exclusion
        if agent_info['auto_switch_enabled'] or agent_info['auto_terminate_enabled']:
            logger.error(f"SEF: Cannot enable manual mode while auto mode is active for {agent_id}")
            return {
                "status": "error",
                "reason": "auto_mode_active",
                "message": "Please disable auto-switch and auto-terminate before enabling manual replica mode"
            }

        # Step 3: Add to manual mode tracking
        self.manual_mode_agents.add(agent_id)

        # Step 4: Update database
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE agents
            SET manual_replica_enabled = TRUE, replica_enabled = TRUE
            WHERE id = %s
        """, (agent_id,))
        self.db.commit()
        cursor.close()

        # Step 5: Create initial replica
        target_pool = self._find_safest_cheapest_pool(agent_id)
        replica_info = self._create_replica(agent_id, target_pool, reason='manual_mode')

        # Step 6: Track replica
        self.agent_replicas[agent_id] = replica_info

        logger.info(f"SEF: Manual replica mode enabled for agent {agent_id}, "
                   f"replica {replica_info['replica_id']} created")

        return {
            "status": "success",
            "mode": "manual_replica",
            "replica_id": replica_info['replica_id'],
            "replica_instance_id": replica_info['instance_id'],
            "pool_id": target_pool['pool_id']
        }

    def disable_manual_replica_mode(self, agent_id: str) -> dict:
        """
        Disable manual replica mode.

        This will:
        1. Terminate the current replica
        2. Remove agent from manual mode tracking
        3. Allow auto mode to be enabled again

        Args:
            agent_id: Agent to disable manual mode for

        Returns:
            Status
        """
        logger.info(f"SEF: Disabling manual replica mode for agent {agent_id}")

        # Step 1: Remove from tracking
        if agent_id in self.manual_mode_agents:
            self.manual_mode_agents.remove(agent_id)

        # Step 2: Terminate replica if exists
        if agent_id in self.agent_replicas:
            replica_info = self.agent_replicas[agent_id]
            self._terminate_replica(replica_info['replica_id'])
            del self.agent_replicas[agent_id]

        # Step 3: Update database
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE agents
            SET manual_replica_enabled = FALSE, replica_enabled = FALSE
            WHERE id = %s
        """, (agent_id,))
        self.db.commit()
        cursor.close()

        logger.info(f"SEF: Manual replica mode disabled for agent {agent_id}")

        return {"status": "success", "mode": "disabled"}

    def execute_manual_switch(self, agent_id: str) -> dict:
        """
        Execute manual switch to replica.

        When user clicks the manual switch button:
        1. Check if replica exists and is ready
        2. Promote replica to primary
        3. Terminate old primary
        4. Create NEW replica for next switch
        5. Return status

        This provides zero-downtime manual switching capability.

        Args:
            agent_id: Agent to switch

        Returns:
            Switch result with new instance IDs
        """
        logger.info(f"SEF: Executing manual switch for agent {agent_id}")

        # Step 1: Verify manual mode is enabled
        if agent_id not in self.manual_mode_agents:
            return {
                "status": "error",
                "reason": "manual_mode_not_enabled",
                "message": "Manual replica mode must be enabled before switching"
            }

        # Step 2: Check replica exists
        if agent_id not in self.agent_replicas:
            return {
                "status": "error",
                "reason": "no_replica",
                "message": "No replica available for switching"
            }

        replica_info = self.agent_replicas[agent_id]

        # Step 3: Check replica is ready
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("""
            SELECT status FROM replica_instances WHERE id = %s
        """, (replica_info['replica_id'],))

        result = cursor.fetchone()
        cursor.close()

        if not result or result['status'] != 'ready':
            return {
                "status": "error",
                "reason": "replica_not_ready",
                "message": f"Replica status: {result['status'] if result else 'unknown'}"
            }

        # Step 4: Get current instance ID (will be terminated)
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("""
            SELECT instance_id FROM agents WHERE id = %s
        """, (agent_id,))

        current = cursor.fetchone()
        old_instance_id = current['instance_id'] if current else None
        cursor.close()

        # Step 5: Promote replica to primary
        self._promote_replica_to_primary(agent_id, replica_info)

        # Step 6: Update agent record
        self._update_agent_instance(agent_id, replica_info['instance_id'])

        # Step 7: Terminate old instance
        if old_instance_id:
            self._mark_instance_terminated(old_instance_id)

        # Step 8: Remove from replicas (it's now primary)
        del self.agent_replicas[agent_id]

        # Step 9: Create NEW replica for next switch
        target_pool = self._find_safest_cheapest_pool(agent_id)
        new_replica_info = self._create_replica(agent_id, target_pool, reason='manual_mode')
        self.agent_replicas[agent_id] = new_replica_info

        logger.info(f"SEF: Manual switch completed for agent {agent_id}. "
                   f"Old: {old_instance_id}, New: {replica_info['instance_id']}, "
                   f"Next replica: {new_replica_info['replica_id']}")

        return {
            "status": "success",
            "old_instance_id": old_instance_id,
            "new_instance_id": replica_info['instance_id'],
            "next_replica_id": new_replica_info['replica_id'],
            "next_replica_instance_id": new_replica_info['instance_id']
        }

    def _terminate_replica(self, replica_id: str):
        """Terminate a replica instance."""
        logger.info(f"SEF: Terminating replica {replica_id}")

        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE replica_instances
            SET status = 'terminated', terminated_at = NOW()
            WHERE id = %s
        """, (replica_id,))
        self.db.commit()
        cursor.close()

    # =========================================================================
    # PART 4: UTILITY AND MONITORING
    # =========================================================================

    def get_agent_status(self, agent_id: str) -> dict:
        """
        Get comprehensive status of agent and its replica.

        Returns:
            Full status including mode, replica info, data quality metrics
        """
        cursor = self.db.cursor(dictionary=True)

        # Get agent info
        cursor.execute("""
            SELECT
                id, instance_id, status, current_mode,
                auto_switch_enabled, manual_replica_enabled,
                replica_enabled, replica_count,
                last_heartbeat_at
            FROM agents
            WHERE id = %s
        """, (agent_id,))

        agent_info = cursor.fetchone()

        if not agent_info:
            cursor.close()
            return {"status": "error", "reason": "agent_not_found"}

        # Get replica info if exists
        replica_info = None
        if agent_id in self.agent_replicas:
            replica_id = self.agent_replicas[agent_id]['replica_id']
            cursor.execute("""
                SELECT id, instance_id, status, created_at, ready_at
                FROM replica_instances
                WHERE id = %s
            """, (replica_id,))
            replica_info = cursor.fetchone()

        # Get recent data quality metrics
        cursor.execute("""
            SELECT COUNT(*) as total_points,
                   SUM(CASE WHEN data_quality_flag = 'interpolated' THEN 1 ELSE 0 END) as interpolated_points,
                   SUM(CASE WHEN data_quality_flag = 'averaged_dual_source' THEN 1 ELSE 0 END) as averaged_points
            FROM pricing_reports
            WHERE agent_id = %s
            AND timestamp > DATE_SUB(NOW(), INTERVAL 1 HOUR)
        """, (agent_id,))

        data_quality = cursor.fetchone()
        cursor.close()

        return {
            "status": "success",
            "agent": agent_info,
            "replica": replica_info,
            "mode": "manual" if agent_id in self.manual_mode_agents else "auto",
            "data_quality": data_quality
        }

    def cleanup_old_buffers(self):
        """
        Periodic cleanup of data buffers.

        Should be called every few minutes to prevent memory bloat.
        """
        current_time = time.time()
        expired_keys = []

        for key, buffer_data in self.recent_data_buffer.items():
            age = current_time - buffer_data['created_at']
            if age > self.data_retention_window:
                expired_keys.append(key)

        for key in expired_keys:
            del self.recent_data_buffer[key]

        if expired_keys:
            logger.debug(f"SEF: Cleaned up {len(expired_keys)} expired data buffers")


# =========================================================================
# HELPER FUNCTIONS FOR INTEGRATION
# =========================================================================

def initialize_sef(db_connection) -> SmartEmergencyFallback:
    """
    Initialize the Smart Emergency Fallback system.

    Call this once when backend starts.

    Args:
        db_connection: MySQL database connection

    Returns:
        Initialized SEF instance
    """
    sef = SmartEmergencyFallback(db_connection)
    logger.info("Smart Emergency Fallback System ready")
    return sef


def integrate_with_backend(flask_app, sef_instance):
    """
    Integrate SEF with Flask backend.

    This adds middleware to intercept agent data and API endpoints
    for manual control.

    Args:
        flask_app: Flask application instance
        sef_instance: Initialized SEF instance
    """
    from flask import request, jsonify

    # Endpoint: Enable manual replica mode
    @flask_app.route('/api/agents/<agent_id>/manual-replica/enable', methods=['POST'])
    def enable_manual_replica(agent_id):
        result = sef_instance.enable_manual_replica_mode(agent_id)
        return jsonify(result)

    # Endpoint: Disable manual replica mode
    @flask_app.route('/api/agents/<agent_id>/manual-replica/disable', methods=['POST'])
    def disable_manual_replica(agent_id):
        result = sef_instance.disable_manual_replica_mode(agent_id)
        return jsonify(result)

    # Endpoint: Execute manual switch
    @flask_app.route('/api/agents/<agent_id>/manual-switch', methods=['POST'])
    def manual_switch(agent_id):
        result = sef_instance.execute_manual_switch(agent_id)
        return jsonify(result)

    # Endpoint: Get agent status
    @flask_app.route('/api/agents/<agent_id>/sef-status', methods=['GET'])
    def get_sef_status(agent_id):
        result = sef_instance.get_agent_status(agent_id)
        return jsonify(result)

    logger.info("SEF integrated with Flask backend")
