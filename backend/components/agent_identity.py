"""
================================================================================
AGENT IDENTITY COMPONENT - Agent Minting & Migration Manager
================================================================================

COMPONENT PURPOSE:
------------------
Manages the lifecycle and persistent identity of all agents. Ensures that every
initial launch registers as a new agent, but upon any switch or replica creation,
the new instance inherits the identity of the original agent. This prevents
duplicate agent records and maintains clean agent tracking across instance migrations.

KEY RESPONSIBILITIES:
--------------------
1. Agent Minting: Create new agent with unique logical_agent_id
2. Identity Preservation: Transfer identity during switches/failovers
3. Instance Migration: Update instance_id while preserving agent identity
4. Deduplication: Prevent multiple agents with same logical ID
5. Cleanup: Handle terminated agent cleanup

SCENARIO EXAMPLES:
-----------------

Scenario 1: Initial Agent Registration (Minting New Identity)
-------------------------------------------------------------
Fresh EC2 instance starts, agent installed for first time

Agent Identity Processing:
1. Receives registration:
   {
     'hostname': 'web-server-01',
     'instance_id': 'i-initial123',
     'instance_type': 't3.medium',
     'region': 'us-east-1',
     'az': 'us-east-1a',
     'client_token': 'token-abc...'
   }

2. Checks if agent exists:
   SELECT * FROM agents
   WHERE client_id = '<client_id>'
     AND logical_agent_id = 'web-server-01'

3. Not found → MINT NEW AGENT:
   logical_agent_id = 'web-server-01'  # From hostname
   agent_id = generate_uuid() = 'agent-abc-123'

4. Creates agent record:
   INSERT INTO agents (
     id, client_id, logical_agent_id,
     instance_id, instance_type, region, az,
     status, installed_at
   ) VALUES (
     'agent-abc-123', '<client_id>', 'web-server-01',
     'i-initial123', 't3.medium', 'us-east-1', 'us-east-1a',
     'online', NOW()
   )

5. Creates instance record:
   INSERT INTO instances (
     id, client_id, agent_id,
     instance_type, region, az,
     current_mode, is_active
   ) VALUES (
     'i-initial123', '<client_id>', 'agent-abc-123',
     't3.medium', 'us-east-1', 'us-east-1a',
     'ondemand', TRUE
   )

Result: New agent 'web-server-01' created with ID 'agent-abc-123'

Scenario 2: Switch - Identity Inheritance
-----------------------------------------
Agent switches from i-old123 to i-new456

Agent Identity Processing:
1. Switch completed, new instance i-new456 starts
2. Agent on i-new456 registers with SAME hostname: 'web-server-01'
3. Checks if agent exists:
   SELECT * FROM agents
   WHERE client_id = '<client_id>'
     AND logical_agent_id = 'web-server-01'

4. FOUND → INHERIT IDENTITY:
   agent_id = 'agent-abc-123'  # Same UUID as before

5. Updates agent record (DOES NOT create new agent):
   UPDATE agents
   SET instance_id = 'i-new456',
       az = 'us-east-1b',  # May have changed
       current_pool_id = 't3.medium.us-east-1b',
       last_switch_at = NOW(),
       instance_count = instance_count + 1,
       updated_at = NOW()
   WHERE id = 'agent-abc-123'

6. Creates new instance record:
   INSERT INTO instances (
     id, client_id, agent_id,
     ...
   ) VALUES (
     'i-new456', '<client_id>', 'agent-abc-123',  # Same agent_id!
     ...
   )

7. Marks old instance as inactive:
   UPDATE instances
   SET is_active = FALSE,
       terminated_at = NOW()
   WHERE id = 'i-old123'

Result: Agent 'web-server-01' preserved, now on i-new456
        Switch history maintained, single logical agent

Scenario 3: Replica Creation - Temporary Identity
-------------------------------------------------
Manual replica created for failover preparation

Agent Identity Processing:
1. Replica instance i-replica789 launched
2. Replica agent registers with suffix: 'web-server-01-replica'
3. Checks for parent agent:
   SELECT * FROM agents
   WHERE client_id = '<client_id>'
     AND logical_agent_id = 'web-server-01'

4. FOUND → CREATE TEMPORARY REPLICA IDENTITY:
   replica_logical_id = 'web-server-01-replica'
   replica_agent_id = generate_uuid() = 'agent-replica-xyz'

5. Creates replica agent record:
   INSERT INTO agents (
     id, client_id, logical_agent_id,
     instance_id, ...
   ) VALUES (
     'agent-replica-xyz', '<client_id>', 'web-server-01-replica',
     'i-replica789', ...
   )

6. Links to replica_instances table:
   INSERT INTO replica_instances (
     id, agent_id, instance_id, replica_type, status
   ) VALUES (
     'replica-uuid', 'agent-abc-123', 'i-replica789', 'manual', 'ready'
   )

Result: Replica tracked separately but linked to primary agent

Scenario 4: Replica Promotion - Identity Merge
----------------------------------------------
Replica promoted to primary (manual or automatic)

Agent Identity Processing:
1. Replica i-replica789 promoted to primary
2. Deletes temporary replica agent:
   DELETE FROM agents WHERE id = 'agent-replica-xyz'

3. Updates primary agent to new instance:
   UPDATE agents
   SET instance_id = 'i-replica789',
       current_pool_id = 't3.medium.us-east-1c',
       last_failover_at = NOW()
   WHERE id = 'agent-abc-123'

4. Updates replica_instances:
   UPDATE replica_instances
   SET status = 'promoted', promoted_at = NOW()
   WHERE instance_id = 'i-replica789'

5. Creates instance record under primary agent:
   INSERT INTO instances (
     id, client_id, agent_id, ...
   ) VALUES (
     'i-replica789', '<client_id>', 'agent-abc-123', ...
   )

Result: Replica identity merged into primary, continuity maintained

Scenario 5: Duplicate Detection (Prevented)
-------------------------------------------
Someone tries to register duplicate agent

Agent Identity Processing:
1. Registration attempt with logical_agent_id = 'web-server-01'
2. Checks for existing:
   SELECT * FROM agents
   WHERE client_id = '<client_id>'
     AND logical_agent_id = 'web-server-01'

3. FOUND + is_active = TRUE → REJECT:
   {
     'success': False,
     'error': 'Agent with this logical ID already active',
     'existing_agent_id': 'agent-abc-123',
     'existing_instance_id': 'i-current999'
   }

4. If user wants to force:
   - Mark old agent as 'replaced'
   - Create new agent with same logical_agent_id
   - Log replacement in system_events

Result: Prevents duplicate agents, maintains data integrity

CONFIGURATION:
-------------
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Any

from backend.database_manager import execute_query
from backend.utils import generate_uuid, log_system_event

logger = logging.getLogger(__name__)


class AgentIdentityConfig:
    """Agent identity configuration"""

    # Identity Rules
    ALLOW_DUPLICATES = False  # Prevent multiple agents with same logical ID
    AUTO_INHERIT_ON_SWITCH = True  # Automatically inherit identity after switch
    REPLICA_SUFFIX = '-replica'  # Suffix for replica agent logical IDs


class AgentIdentityManager:
    """
    Agent Identity Manager - Lifecycle & Migration Controller

    Manages agent identities across instance switches and failovers.

    Example Usage:

    from backend.components.agent_identity import agent_identity_manager

    # Mint new agent (first registration)
    agent = agent_identity_manager.mint_agent(
        client_id='client-123',
        logical_agent_id='web-server-01',
        instance_id='i-initial123',
        instance_type='t3.medium',
        region='us-east-1',
        az='us-east-1a'
    )

    # Migrate to new instance (after switch)
    agent_identity_manager.migrate_agent(
        logical_agent_id='web-server-01',
        client_id='client-123',
        new_instance_id='i-new456',
        new_az='us-east-1b'
    )
    """

    def __init__(self, config: AgentIdentityConfig = None):
        """Initialize Agent Identity Manager"""
        self.config = config or AgentIdentityConfig()
        logger.info("Agent Identity Manager initialized")

    def mint_agent(
        self,
        client_id: str,
        logical_agent_id: str,
        instance_id: str,
        instance_type: str,
        region: str,
        az: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Mint new agent (first registration)

        Args:
            client_id: Client UUID
            logical_agent_id: Persistent logical ID (usually hostname)
            instance_id: EC2 instance ID
            instance_type: Instance type
            region: AWS region
            az: Availability zone
            **kwargs: Additional agent metadata

        Returns:
            {
                'agent_id': 'uuid',
                'is_new': True,
                'logical_agent_id': 'web-server-01'
            }
        """
        # Check if agent already exists
        existing = self.get_agent_by_logical_id(client_id, logical_agent_id)

        if existing:
            if not self.config.ALLOW_DUPLICATES:
                logger.warning(
                    f"Agent already exists: logical_id={logical_agent_id}, "
                    f"agent_id={existing['id']}"
                )
                # Migrate instead of create
                return self.migrate_agent(
                    logical_agent_id=logical_agent_id,
                    client_id=client_id,
                    new_instance_id=instance_id,
                    new_az=az,
                    **kwargs
                )

        # Create new agent
        agent_id = generate_uuid()

        execute_query("""
            INSERT INTO agents (
                id, client_id, logical_agent_id,
                instance_id, instance_type, region, az,
                status, installed_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'online', NOW(), NOW())
        """, (agent_id, client_id, logical_agent_id, instance_id, instance_type, region, az))

        log_system_event(
            'agent_minted',
            'info',
            f'New agent minted: {logical_agent_id}',
            client_id=client_id,
            agent_id=agent_id,
            instance_id=instance_id
        )

        logger.info(f"Agent minted: agent_id={agent_id}, logical_id={logical_agent_id}")

        return {
            'agent_id': agent_id,
            'is_new': True,
            'logical_agent_id': logical_agent_id
        }

    def migrate_agent(
        self,
        logical_agent_id: str,
        client_id: str,
        new_instance_id: str,
        new_az: str = None,
        new_pool_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Migrate agent to new instance (after switch/failover)

        Preserves agent identity, updates instance details.

        Args:
            logical_agent_id: Agent logical ID
            client_id: Client UUID
            new_instance_id: New EC2 instance ID
            new_az: New availability zone (if changed)
            new_pool_id: New pool ID
            **kwargs: Additional updates

        Returns:
            {
                'agent_id': 'uuid',
                'migrated': True,
                'old_instance_id': 'i-old123',
                'new_instance_id': 'i-new456'
            }
        """
        # Get existing agent
        agent = self.get_agent_by_logical_id(client_id, logical_agent_id)

        if not agent:
            raise ValueError(f"Agent not found: {logical_agent_id}")

        old_instance_id = agent['instance_id']

        # Update agent
        updates = {
            'instance_id': new_instance_id,
            'last_switch_at': 'NOW()',
            'instance_count': 'instance_count + 1'
        }

        if new_az:
            updates['az'] = new_az

        if new_pool_id:
            updates['current_pool_id'] = new_pool_id

        # Build UPDATE query
        set_clause = ', '.join([
            f"{k} = {v}" if v == 'NOW()' or 'instance_count' in v else f"{k} = %s"
            for k, v in updates.items()
        ])

        values = [
            v for k, v in updates.items()
            if v != 'NOW()' and 'instance_count' not in v
        ]
        values.append(agent['id'])

        execute_query(f"""
            UPDATE agents
            SET {set_clause}, updated_at = NOW()
            WHERE id = %s
        """, tuple(values))

        log_system_event(
            'agent_migrated',
            'info',
            f'Agent migrated: {logical_agent_id} from {old_instance_id} to {new_instance_id}',
            client_id=client_id,
            agent_id=agent['id'],
            instance_id=new_instance_id
        )

        logger.info(
            f"Agent migrated: agent_id={agent['id']}, "
            f"old_instance={old_instance_id}, new_instance={new_instance_id}"
        )

        return {
            'agent_id': agent['id'],
            'migrated': True,
            'old_instance_id': old_instance_id,
            'new_instance_id': new_instance_id
        }

    def get_agent_by_logical_id(
        self,
        client_id: str,
        logical_agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get agent by logical ID"""
        return execute_query("""
            SELECT *
            FROM agents
            WHERE client_id = %s AND logical_agent_id = %s
            LIMIT 1
        """, (client_id, logical_agent_id), fetch_one=True)

    def cleanup_terminated_agent(self, agent_id: str):
        """Mark agent as terminated and cleanup"""
        execute_query("""
            UPDATE agents
            SET status = 'terminated',
                enabled = FALSE,
                terminated_at = NOW()
            WHERE id = %s
        """, (agent_id,))

        logger.info(f"Agent terminated: agent_id={agent_id}")


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

agent_identity_manager = AgentIdentityManager()
