"""
================================================================================
SENTINEL COMPONENT - Continuous Monitoring & Fallback Trigger
================================================================================

COMPONENT PURPOSE:
------------------
The Sentinel is the system's watchdog - continuously monitoring all incoming
data from agents for service disruption signals. It acts as the SOLE GATEWAY
for interruption detection and triggers the Smart Emergency Fallback (SEF)
when AWS sends rebalance or termination notices.

KEY RESPONSIBILITIES:
--------------------
1. Continuous Monitoring: Watches all agent heartbeats and pricing reports
2. Interruption Detection: Detects AWS rebalance and termination notices
3. Fallback Trigger: Dispatches urgent signals to SEF component
4. Health Monitoring: Tracks agent health and connectivity
5. Alert System: Creates notifications for critical events

ARCHITECTURE POSITION:
---------------------
Agent Data → Sentinel → SEF / Data Valve
               ↓
        (Interruption Detection)

SCENARIO EXAMPLES:
-----------------

Scenario 1: Rebalance Recommendation Detection
----------------------------------------------
Timeline:
T=0s:    Agent detects rebalance recommendation via AWS metadata endpoint
T=2s:    Agent sends POST /api/agents/<id>/interruption with signal_type='rebalance-recommendation'
T=3s:    Sentinel receives interruption signal

Sentinel Processing:
1. Validates signal authenticity (checks AWS metadata format)
2. Checks if this agent already has active rebalance notice (dedup)
3. Logs to spot_interruption_events table:
   {
     'agent_id': 'agent-123',
     'signal_type': 'rebalance-recommendation',
     'detected_at': '2024-01-15 14:30:03',
     'instance_id': 'i-current789'
   }
4. Calculates time-to-potential-termination: Unknown (could be 10 min - 2 hours)
5. Triggers SEF with urgency=MEDIUM:
   SEF.handle_rebalance_notice(
     agent_id='agent-123',
     instance_id='i-current789',
     detected_at=datetime(...)
   )
6. Creates notification: "Rebalance notice detected for Agent-123"
7. Updates agent record: last_rebalance_recommendation_at = NOW()

Result: SEF creates emergency replica in cheapest pool, ready for failover

Scenario 2: Termination Notice Detection (2-Minute Warning)
-----------------------------------------------------------
Timeline:
T=0s:    AWS marks instance for termination
T=1s:    Agent detects termination notice (2-minute countdown starts)
T=2s:    Agent sends POST /api/agents/<id>/interruption with signal_type='termination-notice'
T=3s:    Sentinel receives signal

Sentinel Processing:
1. Validates termination notice (CRITICAL - highest priority)
2. Logs to spot_interruption_events:
   {
     'signal_type': 'termination-notice',
     'detected_at': '2024-01-15 14:45:03',
     'time_to_termination_seconds': 117  # Calculated from agent timestamp
   }
3. Triggers SEF with urgency=CRITICAL:
   SEF.handle_termination_imminent(
     agent_id='agent-123',
     instance_id='i-current789',
     termination_time='2024-01-15 14:47:00',
     has_replica=True  # Checks if replica already exists
   )
4. Creates HIGH SEVERITY notification: "CRITICAL: Instance terminating in 2 minutes"
5. Updates agent: last_termination_notice_at = NOW()

Result: SEF promotes existing replica (if available) in <15 seconds,
        OR creates emergency instance in <60 seconds

Scenario 3: Agent Health Degradation Detection
----------------------------------------------
Timeline:
T=0:     Agent sends normal heartbeat
T=60s:   Agent sends normal heartbeat
T=120s:  Agent sends normal heartbeat
T=180s:  (NO HEARTBEAT - missed!)
T=240s:  (NO HEARTBEAT - missed!)
T=300s:  Sentinel detects pattern

Sentinel Processing:
1. Monitors heartbeat intervals continuously
2. Detects gap: Last heartbeat 300 seconds ago (threshold = 180s)
3. Checks recent pricing reports: Last report 295 seconds ago
4. Calculates health score: DEGRADED
5. Logs system_event:
   {
     'event_type': 'agent_health_degraded',
     'severity': 'warning',
     'message': 'Agent-123 missed 2 consecutive heartbeats',
     'metadata': {
       'last_heartbeat': '2024-01-15 14:40:00',
       'seconds_since': 300,
       'expected_interval': 60
     }
   }
6. Creates notification: "Agent-123 may be experiencing connectivity issues"
7. Does NOT trigger SEF (not an AWS interruption)
8. Marks agent status as 'degraded'

Result: Operations team alerted, agent may self-recover or need investigation

Scenario 4: False Positive Detection (Signal Deduplication)
----------------------------------------------------------
Timeline:
T=0s:    Agent sends rebalance notice
T=3s:    Sentinel processes, creates replica
T=30s:   Agent sends ANOTHER rebalance notice (duplicate)

Sentinel Processing:
1. Receives second rebalance signal
2. Checks recent signals:
   SELECT * FROM spot_interruption_events
   WHERE agent_id = 'agent-123'
     AND signal_type = 'rebalance-recommendation'
     AND detected_at > NOW() - INTERVAL 15 MINUTE
3. Finds existing signal from 30 seconds ago
4. Compares: Same signal type, same instance, within dedup window (15 min)
5. REJECTS duplicate:
   logger.info("Duplicate rebalance signal ignored")
6. Updates existing signal: last_seen_at = NOW()
7. Does NOT trigger SEF again

Result: No duplicate replicas created, system stable

Scenario 5: Cascading Failure Prevention
----------------------------------------
Timeline:
T=0:     5 agents all running normally
T=10s:   AWS announces capacity issues in entire AZ
T=11s:   All 5 agents receive rebalance notices simultaneously
T=12s:   All 5 agents report to Sentinel

Sentinel Processing:
1. Receives 5 rebalance signals within 2 seconds
2. Detects pattern: Multiple agents, same AZ, same time
3. Identifies as potential AZ-wide issue
4. Triggers SEF for each agent BUT with rate limiting:
   - Process agent-1 immediately
   - Queue agent-2 with 3s delay
   - Queue agent-3 with 6s delay
   - Queue agent-4 with 9s delay
   - Queue agent-5 with 12s delay
5. Creates HIGH SEVERITY notification:
   "Multiple agents experiencing issues in us-east-1a - possible AZ disruption"
6. Logs cluster event:
   {
     'event_type': 'cluster_disruption',
     'affected_agents': 5,
     'affected_az': 'us-east-1a',
     'signal_type': 'rebalance-recommendation'
   }

Result: Controlled failover, prevents thundering herd on AWS API,
        all agents migrate safely over 15 seconds

CONFIGURATION:
-------------
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
import threading
import time

from backend.database_manager import execute_query
from backend.utils import log_system_event, generate_uuid

logger = logging.getLogger(__name__)


class SentinelConfig:
    """
    Sentinel monitoring configuration

    Adjust these thresholds based on your infrastructure:
    - HEARTBEAT_TIMEOUT: Increase for slow networks
    - DEDUP_WINDOW: Reduce if agents send frequent updates
    - RATE_LIMIT_WINDOW: Adjust for cascading failure scenarios
    """

    # Health Monitoring
    HEARTBEAT_TIMEOUT_SECONDS = 180  # Mark degraded after 3 minutes
    HEARTBEAT_CRITICAL_SECONDS = 600  # Mark offline after 10 minutes
    PRICING_REPORT_TIMEOUT_SECONDS = 300  # Flag if no pricing for 5 minutes

    # Interruption Detection
    DEDUP_WINDOW_MINUTES = 15  # Ignore duplicate signals within 15 min
    TERMINATION_WARNING_SECONDS = 120  # AWS gives 2-minute warning
    REBALANCE_MAX_AGE_MINUTES = 120  # Rebalance notice expires after 2 hours

    # Rate Limiting (Cascading Failure Prevention)
    RATE_LIMIT_WINDOW_SECONDS = 10  # Window to detect burst of signals
    RATE_LIMIT_THRESHOLD = 3  # >3 signals in window = rate limit
    RATE_LIMIT_DELAY_SECONDS = 3  # Delay between processing in burst

    # Alert Severities
    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_ERROR = 'error'
    SEVERITY_CRITICAL = 'critical'


class InterruptionSignalType:
    """AWS interruption signal types"""
    REBALANCE_RECOMMENDATION = 'rebalance-recommendation'
    TERMINATION_NOTICE = 'termination-notice'
    SPOT_INSTANCE_INTERRUPTION = 'spot-instance-interruption'


class SentinelComponent:
    """
    Sentinel Component - The System Watchdog

    Continuously monitors all agent data for disruption signals and
    triggers appropriate responses through the SEF component.

    Example Usage:

    from backend.components.sentinel import sentinel

    # Register interruption signal
    sentinel.process_interruption_signal(
        agent_id='agent-123',
        instance_id='i-current789',
        signal_type=InterruptionSignalType.REBALANCE_RECOMMENDATION,
        detected_at=datetime.utcnow(),
        metadata={'action': 'rebalance-recommendation', 'time': '2024-01-15T14:30:00Z'}
    )

    # Monitor agent health
    health = sentinel.check_agent_health('agent-123')
    # Returns: {'status': 'healthy', 'last_heartbeat_seconds_ago': 45, ...}

    # Register callback for SEF trigger
    sentinel.register_sef_callback(sef_component.handle_rebalance_notice)
    """

    def __init__(self, config: SentinelConfig = None):
        """Initialize Sentinel with configuration"""
        self.config = config or SentinelConfig()

        # SEF callback (registered by orchestrator)
        self._sef_callbacks = {
            'rebalance': None,
            'termination': None
        }

        # Rate limiting tracking
        self._signal_timestamps = defaultdict(list)
        self._rate_limit_lock = threading.Lock()

        # Statistics
        self.stats = {
            'total_signals_received': 0,
            'rebalance_signals': 0,
            'termination_signals': 0,
            'duplicates_rejected': 0,
            'rate_limited_signals': 0,
            'sef_triggers': 0
        }

        logger.info("Sentinel Component initialized - monitoring active")

    # =========================================================================
    # INTERRUPTION SIGNAL PROCESSING
    # =========================================================================

    def process_interruption_signal(
        self,
        agent_id: str,
        instance_id: str,
        signal_type: str,
        detected_at: datetime,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process AWS interruption signal from agent

        This is the main entry point for all interruption signals.
        Implements deduplication, rate limiting, and SEF triggering.

        Args:
            agent_id: Agent UUID
            instance_id: EC2 instance ID
            signal_type: Type of signal (rebalance, termination)
            detected_at: When agent detected the signal
            metadata: Additional signal data from AWS

        Returns:
            {
                'accepted': True,
                'action': 'sef_triggered',
                'signal_id': 'uuid',
                'duplicate': False,
                'rate_limited': False
            }

        Example:
            result = sentinel.process_interruption_signal(
                agent_id='agent-123',
                instance_id='i-abc123',
                signal_type=InterruptionSignalType.TERMINATION_NOTICE,
                detected_at=datetime.utcnow(),
                metadata={'time': '2024-01-15T14:45:00Z'}
            )
        """
        self.stats['total_signals_received'] += 1

        # Step 1: Check for duplicate signal
        if self._is_duplicate_signal(agent_id, signal_type, detected_at):
            self.stats['duplicates_rejected'] += 1
            logger.info(
                f"Duplicate signal rejected: agent={agent_id}, "
                f"type={signal_type}, instance={instance_id}"
            )
            return {
                'accepted': False,
                'action': 'duplicate_rejected',
                'duplicate': True
            }

        # Step 2: Rate limiting check (cascading failure prevention)
        rate_limited, delay = self._should_rate_limit(agent_id, signal_type)

        if rate_limited:
            self.stats['rate_limited_signals'] += 1
            logger.warning(
                f"Rate limiting applied: agent={agent_id}, "
                f"delay={delay}s, type={signal_type}"
            )
            # Process after delay
            time.sleep(delay)

        # Step 3: Log to database
        signal_id = self._log_interruption_event(
            agent_id, instance_id, signal_type, detected_at, metadata
        )

        # Step 4: Update agent record
        self._update_agent_interruption_timestamp(agent_id, signal_type)

        # Step 5: Create notification
        self._create_interruption_notification(agent_id, signal_type, instance_id)

        # Step 6: Trigger SEF
        sef_result = self._trigger_sef(agent_id, instance_id, signal_type, detected_at, metadata)

        # Step 7: Track in rate limiter
        self._track_signal_for_rate_limiting(agent_id, signal_type)

        # Update stats
        if signal_type == InterruptionSignalType.REBALANCE_RECOMMENDATION:
            self.stats['rebalance_signals'] += 1
        elif signal_type == InterruptionSignalType.TERMINATION_NOTICE:
            self.stats['termination_signals'] += 1

        self.stats['sef_triggers'] += 1

        logger.info(
            f"Interruption signal processed: signal_id={signal_id}, "
            f"agent={agent_id}, type={signal_type}, sef_triggered={sef_result is not None}"
        )

        return {
            'accepted': True,
            'action': 'sef_triggered' if sef_result else 'logged',
            'signal_id': signal_id,
            'duplicate': False,
            'rate_limited': rate_limited,
            'sef_result': sef_result
        }

    # =========================================================================
    # AGENT HEALTH MONITORING
    # =========================================================================

    def check_agent_health(self, agent_id: str) -> Dict[str, Any]:
        """
        Check comprehensive agent health status

        Analyzes:
        - Heartbeat freshness
        - Pricing report freshness
        - Recent errors
        - Connection quality

        Returns:
            {
                'status': 'healthy' | 'degraded' | 'critical' | 'offline',
                'last_heartbeat_seconds_ago': 45,
                'last_pricing_seconds_ago': 52,
                'health_score': 95,  # 0-100
                'issues': ['No issues'],
                'recommendation': 'continue_monitoring'
            }
        """
        # Get agent data
        agent = execute_query("""
            SELECT
                id, status, last_heartbeat_at,
                TIMESTAMPDIFF(SECOND, last_heartbeat_at, NOW()) as heartbeat_age_sec
            FROM agents
            WHERE id = %s
        """, (agent_id,), fetch_one=True)

        if not agent:
            return {
                'status': 'unknown',
                'error': 'Agent not found'
            }

        # Get last pricing report
        pricing = execute_query("""
            SELECT
                TIMESTAMPDIFF(SECOND, MAX(received_at), NOW()) as pricing_age_sec
            FROM pricing_reports
            WHERE agent_id = %s
        """, (agent_id,), fetch_one=True)

        heartbeat_age = agent.get('heartbeat_age_sec') or 999999
        pricing_age = pricing.get('pricing_age_sec') if pricing else 999999

        # Calculate health status
        issues = []
        health_score = 100

        # Check heartbeat
        if heartbeat_age > self.config.HEARTBEAT_CRITICAL_SECONDS:
            status = 'offline'
            health_score = 0
            issues.append(f'No heartbeat for {heartbeat_age}s (critical)')
        elif heartbeat_age > self.config.HEARTBEAT_TIMEOUT_SECONDS:
            status = 'degraded'
            health_score = 50
            issues.append(f'No heartbeat for {heartbeat_age}s (timeout)')
        else:
            status = 'healthy'
            # Deduct points for slow heartbeats
            if heartbeat_age > 90:
                health_score -= 20
                issues.append(f'Heartbeat delayed ({heartbeat_age}s)')

        # Check pricing reports
        if pricing_age > self.config.PRICING_REPORT_TIMEOUT_SECONDS:
            health_score -= 30
            issues.append(f'No pricing reports for {pricing_age}s')

        if not issues:
            issues = ['No issues']

        # Recommendation
        if status == 'offline':
            recommendation = 'investigate_immediately'
        elif status == 'degraded':
            recommendation = 'monitor_closely'
        else:
            recommendation = 'continue_monitoring'

        return {
            'status': status,
            'last_heartbeat_seconds_ago': heartbeat_age,
            'last_pricing_seconds_ago': pricing_age,
            'health_score': max(0, health_score),
            'issues': issues,
            'recommendation': recommendation
        }

    def monitor_all_agents(self) -> Dict[str, Any]:
        """
        Monitor all agents and return summary

        This method is typically called by background jobs.

        Returns:
            {
                'total_agents': 10,
                'healthy': 8,
                'degraded': 1,
                'offline': 1,
                'alerts_created': 2
            }
        """
        agents = execute_query("""
            SELECT id, logical_agent_id, status
            FROM agents
            WHERE enabled = TRUE
        """, fetch=True)

        summary = {
            'total_agents': len(agents or []),
            'healthy': 0,
            'degraded': 0,
            'offline': 0,
            'critical': 0,
            'alerts_created': 0
        }

        for agent in (agents or []):
            health = self.check_agent_health(agent['id'])

            status = health['status']
            if status == 'healthy':
                summary['healthy'] += 1
            elif status == 'degraded':
                summary['degraded'] += 1
                # Create alert for degraded
                self._create_health_alert(agent['id'], health)
                summary['alerts_created'] += 1
            elif status == 'offline':
                summary['offline'] += 1
                # Create alert for offline
                self._create_health_alert(agent['id'], health)
                summary['alerts_created'] += 1

        return summary

    # =========================================================================
    # SEF CALLBACK REGISTRATION
    # =========================================================================

    def register_sef_callback(
        self,
        callback_type: str,
        callback: Callable
    ):
        """
        Register callback for SEF triggering

        Args:
            callback_type: 'rebalance' or 'termination'
            callback: Function to call when signal detected

        Example:
            sentinel.register_sef_callback(
                'rebalance',
                sef.handle_rebalance_notice
            )
        """
        self._sef_callbacks[callback_type] = callback
        logger.info(f"SEF callback registered: type={callback_type}")

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _is_duplicate_signal(
        self,
        agent_id: str,
        signal_type: str,
        detected_at: datetime
    ) -> bool:
        """Check if this signal was already received recently"""
        cutoff = datetime.utcnow() - timedelta(minutes=self.config.DEDUP_WINDOW_MINUTES)

        existing = execute_query("""
            SELECT id
            FROM spot_interruption_events
            WHERE agent_id = %s
              AND signal_type = %s
              AND detected_at >= %s
            LIMIT 1
        """, (agent_id, signal_type, cutoff), fetch_one=True)

        return existing is not None

    def _should_rate_limit(
        self,
        agent_id: str,
        signal_type: str
    ) -> tuple[bool, int]:
        """
        Check if signal should be rate limited

        Returns:
            (should_limit: bool, delay_seconds: int)
        """
        with self._rate_limit_lock:
            now = time.time()
            cutoff = now - self.config.RATE_LIMIT_WINDOW_SECONDS

            # Get recent signals for this type
            recent_signals = [
                ts for ts in self._signal_timestamps[signal_type]
                if ts > cutoff
            ]

            if len(recent_signals) >= self.config.RATE_LIMIT_THRESHOLD:
                # Rate limit applies
                delay = len(recent_signals) * self.config.RATE_LIMIT_DELAY_SECONDS
                return True, delay
            else:
                return False, 0

    def _track_signal_for_rate_limiting(self, agent_id: str, signal_type: str):
        """Track signal timestamp for rate limiting"""
        with self._rate_limit_lock:
            self._signal_timestamps[signal_type].append(time.time())

            # Keep only recent timestamps
            cutoff = time.time() - (self.config.RATE_LIMIT_WINDOW_SECONDS * 2)
            self._signal_timestamps[signal_type] = [
                ts for ts in self._signal_timestamps[signal_type]
                if ts > cutoff
            ]

    def _log_interruption_event(
        self,
        agent_id: str,
        instance_id: str,
        signal_type: str,
        detected_at: datetime,
        metadata: Dict[str, Any]
    ) -> str:
        """Log interruption event to database"""
        signal_id = generate_uuid()

        execute_query("""
            INSERT INTO spot_interruption_events (
                id, agent_id, instance_id, signal_type,
                detected_at, metadata, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            signal_id, agent_id, instance_id, signal_type,
            detected_at, str(metadata) if metadata else None
        ))

        return signal_id

    def _update_agent_interruption_timestamp(self, agent_id: str, signal_type: str):
        """Update agent's last interruption timestamp"""
        if signal_type == InterruptionSignalType.REBALANCE_RECOMMENDATION:
            execute_query("""
                UPDATE agents
                SET last_rebalance_recommendation_at = NOW(),
                    interruption_handled_count = interruption_handled_count + 1
                WHERE id = %s
            """, (agent_id,))
        elif signal_type == InterruptionSignalType.TERMINATION_NOTICE:
            execute_query("""
                UPDATE agents
                SET last_termination_notice_at = NOW(),
                    interruption_handled_count = interruption_handled_count + 1
                WHERE id = %s
            """, (agent_id,))

    def _create_interruption_notification(
        self,
        agent_id: str,
        signal_type: str,
        instance_id: str
    ):
        """Create user-facing notification"""
        if signal_type == InterruptionSignalType.REBALANCE_RECOMMENDATION:
            message = f"Rebalance recommendation detected for instance {instance_id}"
            severity = self.config.SEVERITY_WARNING
        elif signal_type == InterruptionSignalType.TERMINATION_NOTICE:
            message = f"CRITICAL: Instance {instance_id} terminating in 2 minutes"
            severity = self.config.SEVERITY_CRITICAL
        else:
            message = f"Interruption signal detected: {signal_type}"
            severity = self.config.SEVERITY_WARNING

        log_system_event(
            event_type='interruption_signal',
            severity=severity,
            message=message,
            agent_id=agent_id,
            instance_id=instance_id,
            metadata={'signal_type': signal_type}
        )

    def _trigger_sef(
        self,
        agent_id: str,
        instance_id: str,
        signal_type: str,
        detected_at: datetime,
        metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Trigger appropriate SEF callback"""
        if signal_type == InterruptionSignalType.REBALANCE_RECOMMENDATION:
            callback = self._sef_callbacks.get('rebalance')
            if callback:
                return callback(
                    agent_id=agent_id,
                    instance_id=instance_id,
                    detected_at=detected_at,
                    metadata=metadata
                )
        elif signal_type == InterruptionSignalType.TERMINATION_NOTICE:
            callback = self._sef_callbacks.get('termination')
            if callback:
                return callback(
                    agent_id=agent_id,
                    instance_id=instance_id,
                    detected_at=detected_at,
                    metadata=metadata
                )

        return None

    def _create_health_alert(self, agent_id: str, health: Dict[str, Any]):
        """Create health alert notification"""
        status = health['status']
        issues = ', '.join(health['issues'])

        if status == 'offline':
            severity = self.config.SEVERITY_ERROR
        elif status == 'degraded':
            severity = self.config.SEVERITY_WARNING
        else:
            severity = self.config.SEVERITY_INFO

        log_system_event(
            event_type='agent_health_alert',
            severity=severity,
            message=f"Agent health {status}: {issues}",
            agent_id=agent_id,
            metadata={'health_score': health['health_score']}
        )

    def get_stats(self) -> Dict[str, int]:
        """Get Sentinel statistics"""
        return dict(self.stats)


# ============================================================================
# GLOBAL INSTANCE (SINGLETON PATTERN)
# ============================================================================

# Global sentinel instance - import this in services
sentinel = SentinelComponent()

logger.info("Sentinel Component initialized and monitoring")
