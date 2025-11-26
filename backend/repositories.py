"""
Repository Layer for Database Operations
========================================

This module provides a repository pattern implementation for database
access, consolidating common queries and reducing code duplication.

Each repository class handles a specific domain (agents, replicas, pools, etc.)
and encapsulates all database operations for that domain.

Benefits:
- Single source of truth for each query type
- Easier to maintain and test
- Consistent error handling
- Better separation of concerns

Author: AWS Spot Optimizer Team
Version: 1.0.0
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import logging

from exceptions import NotFoundError, DatabaseError

logger = logging.getLogger(__name__)


class AgentRepository:
    """
    Repository for agent-related database operations.

    Handles all queries related to agent registration, status,
    configuration, and lifecycle management.
    """

    @staticmethod
    def get_by_id(execute_query, agent_id: str, client_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get agent by ID with optional client filtering.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier
            client_id: Optional client ID for authorization check

        Returns:
            Agent data dictionary or None if not found
        """
        query = "SELECT * FROM agents WHERE id = %s"
        params = [agent_id]

        if client_id:
            query += " AND client_id = %s"
            params.append(client_id)

        return execute_query(query, tuple(params), fetch_one=True)

    @staticmethod
    def get_or_404(execute_query, agent_id: str, client_id: Optional[str] = None) -> Dict:
        """
        Get agent by ID or raise 404 error.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier
            client_id: Optional client ID for authorization check

        Returns:
            Agent data dictionary

        Raises:
            NotFoundError: If agent not found
        """
        agent = AgentRepository.get_by_id(execute_query, agent_id, client_id)
        if not agent:
            raise NotFoundError(f'Agent {agent_id} not found')
        return agent

    @staticmethod
    def update_heartbeat(execute_query, agent_id: str, status: str = 'online'):
        """
        Update agent heartbeat timestamp and status.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier
            status: Agent status (online, offline, switching, etc.)
        """
        execute_query("""
            UPDATE agents
            SET last_heartbeat_at = NOW(), status = %s
            WHERE id = %s
        """, (status, agent_id))

    @staticmethod
    def get_config(execute_query, agent_id: str) -> Dict:
        """
        Get agent configuration and decision settings.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier

        Returns:
            Dictionary with agent configuration
        """
        return execute_query("""
            SELECT auto_switch_enabled, switching_threshold,
                   preferred_instance_types, preferred_regions,
                   manual_replica_enabled, replica_count,
                   auto_terminate_enabled, max_switches_per_day
            FROM agents WHERE id = %s
        """, (agent_id,), fetch_one=True)

    @staticmethod
    def decrement_replica_count(execute_query, agent_id: str, replica_id: str):
        """
        Decrement replica count and clear current_replica_id if needed.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier
            replica_id: Replica ID to clear from current_replica_id
        """
        execute_query("""
            UPDATE agents
            SET replica_count = GREATEST(0, replica_count - 1),
                current_replica_id = CASE
                    WHEN current_replica_id = %s THEN NULL
                    ELSE current_replica_id
                END
            WHERE id = %s
        """, (replica_id, agent_id))


class ReplicaRepository:
    """
    Repository for replica instance database operations.

    Handles all queries related to replica creation, status updates,
    promotion, and termination.
    """

    @staticmethod
    def get_by_id(execute_query, replica_id: str, agent_id: str) -> Optional[Dict]:
        """
        Get replica by ID for specific agent.

        Args:
            execute_query: Database query execution function
            replica_id: Replica identifier
            agent_id: Agent identifier for authorization

        Returns:
            Replica data dictionary or None if not found
        """
        return execute_query("""
            SELECT * FROM replica_instances
            WHERE id = %s AND agent_id = %s
        """, (replica_id, agent_id), fetch_one=True)

    @staticmethod
    def get_or_404(execute_query, replica_id: str, agent_id: str) -> Dict:
        """
        Get replica by ID or raise 404 error.

        Args:
            execute_query: Database query execution function
            replica_id: Replica identifier
            agent_id: Agent identifier for authorization

        Returns:
            Replica data dictionary

        Raises:
            NotFoundError: If replica not found
        """
        replica = ReplicaRepository.get_by_id(execute_query, replica_id, agent_id)
        if not replica:
            raise NotFoundError(f'Replica {replica_id} not found')
        return replica

    @staticmethod
    def get_active_for_agent(execute_query, agent_id: str) -> List[Dict]:
        """
        Get all active replicas for an agent.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier

        Returns:
            List of active replica dictionaries (empty list if none)
        """
        return execute_query("""
            SELECT * FROM replica_instances
            WHERE agent_id = %s
              AND is_active = TRUE
              AND status NOT IN ('terminated', 'promoted', 'failed')
        """, (agent_id,), fetch=True) or []

    @staticmethod
    def count_active(execute_query, agent_id: str) -> int:
        """
        Count active replicas for an agent.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier

        Returns:
            Number of active replicas
        """
        result = execute_query("""
            SELECT COUNT(*) as count FROM replica_instances
            WHERE agent_id = %s
              AND is_active = TRUE
              AND status NOT IN ('terminated', 'promoted', 'failed')
        """, (agent_id,), fetch_one=True)
        return result['count'] if result else 0

    @staticmethod
    def mark_as_terminated(execute_query, replica_id: str):
        """
        Mark replica as terminated.

        Args:
            execute_query: Database query execution function
            replica_id: Replica identifier
        """
        execute_query("""
            UPDATE replica_instances
            SET status = 'terminated', is_active = FALSE, terminated_at = NOW()
            WHERE id = %s
        """, (replica_id,))

    @staticmethod
    def get_instance_id(execute_query, replica_id: str) -> Optional[str]:
        """
        Get EC2 instance ID for a replica.

        Args:
            execute_query: Database query execution function
            replica_id: Replica identifier

        Returns:
            EC2 instance ID or None if not found
        """
        result = execute_query("""
            SELECT instance_id FROM replica_instances WHERE id = %s
        """, (replica_id,), fetch_one=True)
        return result['instance_id'] if result else None


class PoolRepository:
    """
    Repository for spot pool database operations.

    Handles queries for finding pools, getting pricing information,
    and pool availability checks.
    """

    @staticmethod
    def get_latest_price(execute_query, pool_id: int) -> Optional[Decimal]:
        """
        Get latest spot price for a pool.

        Args:
            execute_query: Database query execution function
            pool_id: Pool identifier

        Returns:
            Latest spot price or None if no data available
        """
        result = execute_query("""
            SELECT spot_price FROM pricing_snapshots_clean
            WHERE pool_id = %s
            ORDER BY time_bucket DESC
            LIMIT 1
        """, (pool_id,), fetch_one=True)
        return result['spot_price'] if result else None

    @staticmethod
    def find_cheapest_available(execute_query, instance_type: str, region: str,
                               exclude_pool_id: Optional[int] = None,
                               exclude_zones: List[str] = None,
                               limit: int = 2) -> List[Dict]:
        """
        Find cheapest available pools with current pricing.

        Args:
            execute_query: Database query execution function
            instance_type: EC2 instance type (e.g., 't3.medium')
            region: AWS region (e.g., 'us-east-1')
            exclude_pool_id: Optional pool ID to exclude from results
            exclude_zones: Optional list of availability zones to exclude
            limit: Maximum number of results to return

        Returns:
            List of pool dictionaries with pricing, sorted by price
        """
        query = """
            SELECT sp.id, sp.az, sp.instance_type, sp.region,
                   COALESCE(sps.price, 0.05) as spot_price
            FROM spot_pools sp
            LEFT JOIN (
                SELECT pool_id, price,
                       ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
                FROM spot_price_snapshots
                WHERE captured_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            ) sps ON sps.pool_id = sp.id AND sps.rn = 1
            WHERE sp.instance_type = %s
              AND sp.region = %s
              AND sp.is_available = TRUE
        """
        params = [instance_type, region]

        # Add optional filters
        if exclude_pool_id:
            query += " AND sp.id != %s"
            params.append(exclude_pool_id)

        if exclude_zones:
            placeholders = ','.join(['%s'] * len(exclude_zones))
            query += f" AND sp.az NOT IN ({placeholders})"
            params.extend(exclude_zones)

        query += f" ORDER BY COALESCE(sps.price, 999999) ASC LIMIT {limit}"

        return execute_query(query, tuple(params), fetch=True) or []


class PricingRepository:
    """
    Repository for pricing data operations.

    Handles queries for current prices, historical trends,
    and on-demand pricing.
    """

    @staticmethod
    def get_ondemand_price(execute_query, instance_type: str, region: str) -> Decimal:
        """
        Get on-demand price for instance type in region.

        Args:
            execute_query: Database query execution function
            instance_type: EC2 instance type
            region: AWS region

        Returns:
            On-demand hourly price (returns default if not found)
        """
        result = execute_query("""
            SELECT price FROM ondemand_prices
            WHERE instance_type = %s AND region = %s
            LIMIT 1
        """, (instance_type, region), fetch_one=True)

        # Return default price if not found (fallback)
        return result['price'] if result else Decimal('0.0416')


class SystemEventRepository:
    """
    Repository for system event logging.

    Provides methods to log various system events for monitoring
    and audit purposes.
    """

    @staticmethod
    def log_event(execute_query, event_type: str, severity: str, message: str,
                  agent_id: Optional[str] = None,
                  instance_id: Optional[str] = None,
                  client_id: Optional[str] = None,
                  metadata: Optional[Dict] = None):
        """
        Log system event to database.

        Args:
            execute_query: Database query execution function
            event_type: Type of event (e.g., 'replica_promoted', 'agent_registered')
            severity: Severity level ('info', 'warning', 'error', 'critical')
            message: Human-readable event message
            agent_id: Optional agent ID associated with event
            instance_id: Optional instance ID associated with event
            client_id: Optional client ID associated with event
            metadata: Optional additional event metadata as dictionary
        """
        import json
        execute_query("""
            INSERT INTO system_events (
                event_type, severity, agent_id, instance_id, client_id, message, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            event_type, severity, agent_id, instance_id, client_id,
            message, json.dumps(metadata) if metadata else None
        ))

    @staticmethod
    def log_replica_promoted(execute_query, agent_id: str, replica_id: str,
                           instance_id: str, old_instance_id: str, demoted: bool):
        """
        Log replica promotion event with full context.

        Args:
            execute_query: Database query execution function
            agent_id: Agent identifier
            replica_id: Replica identifier
            instance_id: New primary instance ID
            old_instance_id: Old primary instance ID
            demoted: Whether old primary was demoted to replica
        """
        SystemEventRepository.log_event(
            execute_query,
            event_type='replica_promoted',
            severity='info',
            message=f"Replica {replica_id} promoted to primary, "
                   f"old primary {'demoted to replica' if demoted else 'marked as zombie'}",
            agent_id=agent_id,
            instance_id=instance_id,
            metadata={
                'replica_id': replica_id,
                'old_instance_id': old_instance_id,
                'demoted': demoted
            }
        )
