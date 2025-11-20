"""
Replica Management API
Handles manual and automatic replica creation, monitoring, and failover operations.

This module provides:
1. Manual replica management (user-controlled)
2. Automatic spot interruption defense
3. State transfer and failover orchestration
4. Replica monitoring and health checks
"""

import json
import uuid
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import logging

from flask import jsonify, request
from database_utils import execute_query

logger = logging.getLogger(__name__)

# ============================================================================
# MANUAL REPLICA MANAGEMENT ENDPOINTS
# ============================================================================

def create_manual_replica(app):
    """POST /api/agents/<agent_id>/replicas - Create manual replica"""
    @app.route('/api/agents/<agent_id>/replicas', methods=['POST'])
    def create_replica_endpoint(agent_id):
        """
        Create a manual replica for an agent instance.

        Request body:
        {
            "pool_id": 123,  # optional - auto-select if not provided
            "exclude_zones": ["us-east-1a"],  # optional
            "max_hourly_cost": 0.50,  # optional
            "tags": {"key": "value"}  # optional
        }
        """
        try:
            data = request.get_json() or {}

            # Validate agent exists and is active
            agent = execute_query("""
                SELECT a.*, i.id as instance_id, i.instance_type, i.region,
                       i.current_pool_id, i.current_mode
                FROM agents a
                JOIN instances i ON a.instance_id = i.id
                WHERE a.id = %s AND a.status = 'online'
            """, (agent_id,), fetch=True)

            if not agent or len(agent) == 0:
                return jsonify({'error': 'Agent not found or offline'}), 404

            agent = agent[0]

            # Check if manual replicas are enabled for this agent
            if not agent.get('manual_replica_enabled'):
                return jsonify({
                    'error': 'Manual replicas not enabled for this agent',
                    'hint': 'Enable manual_replica_enabled in agent settings'
                }), 400

            # Check current replica count
            if agent.get('replica_count', 0) >= 2:
                return jsonify({
                    'error': 'Maximum replica limit reached',
                    'current_count': agent['replica_count'],
                    'max_allowed': 2
                }), 400

            # Determine target pool
            target_pool_id = data.get('pool_id')
            if not target_pool_id:
                # Auto-select cheapest compatible pool
                # If current pool is cheapest, select second cheapest
                target_pool_id = _select_cheapest_pool(
                    instance_type=agent['instance_type'],
                    region=agent['region'],
                    current_pool_id=agent['current_pool_id'],
                    exclude_zones=data.get('exclude_zones', []),
                    max_cost=data.get('max_hourly_cost')
                )

                if not target_pool_id:
                    return jsonify({
                        'error': 'No suitable pool found',
                        'hint': 'Try adjusting exclude_zones or max_hourly_cost'
                    }), 400

            # Get pool details
            pool = execute_query("""
                SELECT * FROM spot_pools WHERE id = %s
            """, (target_pool_id,), fetch=True)

            if not pool or len(pool) == 0:
                return jsonify({'error': 'Pool not found'}), 404

            pool = pool[0]

            # Validate pool compatibility
            if pool['instance_type'] != agent['instance_type']:
                return jsonify({
                    'error': 'Pool instance type mismatch',
                    'agent_type': agent['instance_type'],
                    'pool_type': pool['instance_type']
                }), 400

            # Get current spot price
            latest_price = execute_query("""
                SELECT spot_price, ondemand_price
                FROM pricing_snapshots_clean
                WHERE pool_id = %s
                ORDER BY time_bucket DESC
                LIMIT 1
            """, (target_pool_id,), fetch=True)

            hourly_cost = latest_price[0]['spot_price'] if latest_price else None

            # Create replica record
            replica_id = str(uuid.uuid4())
            replica_instance_id = f"replica-{replica_id[:8]}"  # Placeholder - actual EC2 instance ID comes later

            execute_query("""
                INSERT INTO replica_instances (
                    id, agent_id, instance_id, replica_type, pool_id,
                    instance_type, region, az, status, created_by,
                    parent_instance_id, hourly_cost, tags
                ) VALUES (
                    %s, %s, %s, 'manual', %s, %s, %s, %s, 'launching',
                    %s, %s, %s, %s
                )
            """, (
                replica_id,
                agent_id,
                replica_instance_id,
                target_pool_id,
                pool['instance_type'],
                pool['region'],
                pool['az'],
                data.get('created_by', 'unknown'),
                agent['instance_id'],
                hourly_cost,
                json.dumps(data.get('tags', {}))
            ))

            # Update agent replica count
            execute_query("""
                UPDATE agents
                SET replica_count = replica_count + 1,
                    current_replica_id = CASE WHEN current_replica_id IS NULL THEN %s ELSE current_replica_id END
                WHERE id = %s
            """, (replica_id, agent_id))

            logger.info(f"Created manual replica {replica_id} for agent {agent_id} in pool {target_pool_id}")

            return jsonify({
                'success': True,
                'replica_id': replica_id,
                'instance_id': replica_instance_id,
                'pool': {
                    'id': pool['id'],
                    'name': pool['pool_name'],
                    'instance_type': pool['instance_type'],
                    'region': pool['region'],
                    'az': pool['az']
                },
                'hourly_cost': float(hourly_cost) if hourly_cost else None,
                'status': 'launching',
                'message': 'Replica is launching. Connect your agent to establish sync.'
            }), 201

        except Exception as e:
            logger.error(f"Error creating replica: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def list_replicas(app):
    """GET /api/agents/<agent_id>/replicas - List all replicas for an agent"""
    @app.route('/api/agents/<agent_id>/replicas', methods=['GET'])
    def list_replicas_endpoint(agent_id):
        """List all replicas (active and terminated) for an agent"""
        try:
            include_terminated = request.args.get('include_terminated', 'false').lower() == 'true'

            query = """
                SELECT
                    ri.*,
                    sp.pool_name,
                    sp.instance_type,
                    sp.region,
                    sp.az,
                    TIMESTAMPDIFF(SECOND, ri.created_at, COALESCE(ri.terminated_at, NOW())) as age_seconds
                FROM replica_instances ri
                LEFT JOIN spot_pools sp ON ri.pool_id = sp.id
                WHERE ri.agent_id = %s
            """

            if not include_terminated:
                query += " AND ri.is_active = TRUE"

            query += " ORDER BY ri.created_at DESC"

            replicas = execute_query(query, (agent_id,), fetch=True)

            result = []
            for r in (replicas or []):
                result.append({
                    'id': r['id'],
                    'instance_id': r['instance_id'],
                    'type': r['replica_type'],
                    'status': r['status'],
                    'sync_status': r['sync_status'],
                    'sync_latency_ms': r['sync_latency_ms'],
                    'state_transfer_progress': float(r['state_transfer_progress']) if r['state_transfer_progress'] else 0.0,
                    'pool': {
                        'id': r['pool_id'],
                        'name': r.get('pool_name'),
                        'instance_type': r.get('instance_type'),
                        'region': r.get('region'),
                        'az': r.get('az')
                    },
                    'cost': {
                        'hourly': float(r['hourly_cost']) if r['hourly_cost'] else None,
                        'total': float(r['total_cost']) if r['total_cost'] else 0.0
                    },
                    'created_by': r['created_by'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                    'ready_at': r['ready_at'].isoformat() if r['ready_at'] else None,
                    'terminated_at': r['terminated_at'].isoformat() if r['terminated_at'] else None,
                    'age_seconds': r['age_seconds'],
                    'is_active': bool(r['is_active']),
                    'tags': json.loads(r['tags']) if r['tags'] else {}
                })

            return jsonify({
                'replicas': result,
                'total': len(result)
            }), 200

        except Exception as e:
            logger.error(f"Error listing replicas: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def promote_replica(app):
    """POST /api/agents/<agent_id>/replicas/<replica_id>/promote - Promote replica to primary"""
    @app.route('/api/agents/<agent_id>/replicas/<replica_id>/promote', methods=['POST'])
    def promote_replica_endpoint(agent_id, replica_id):
        """
        Promote replica to primary (manual failover).

        Request body:
        {
            "demote_old_primary": true,  # or false to terminate
            "wait_for_sync": true  # wait for final state sync
        }
        """
        try:
            data = request.get_json() or {}
            demote_old_primary = data.get('demote_old_primary', True)
            wait_for_sync = data.get('wait_for_sync', True)

            # Validate replica exists and is ready
            replica = execute_query("""
                SELECT * FROM replica_instances
                WHERE id = %s AND agent_id = %s AND is_active = TRUE
            """, (replica_id, agent_id), fetch=True)

            if not replica or len(replica) == 0:
                return jsonify({'error': 'Replica not found or inactive'}), 404

            replica = replica[0]

            if replica['status'] not in ('ready', 'syncing'):
                return jsonify({
                    'error': 'Replica not ready for promotion',
                    'current_status': replica['status'],
                    'required_status': 'ready or syncing'
                }), 400

            # Get current primary instance
            agent = execute_query("""
                SELECT a.*, i.id as instance_id
                FROM agents a
                JOIN instances i ON a.instance_id = i.id
                WHERE a.id = %s
            """, (agent_id,), fetch=True)

            if not agent or len(agent) == 0:
                return jsonify({'error': 'Agent not found'}), 404

            agent = agent[0]
            old_instance_id = agent['instance_id']

            # Begin promotion process
            # Step 1: Update replica status to 'promoted'
            execute_query("""
                UPDATE replica_instances
                SET status = 'promoted',
                    promoted_at = NOW(),
                    is_active = TRUE
                WHERE id = %s
            """, (replica_id,))

            # Step 2: Create new instance record for the replica
            new_instance_id = str(uuid.uuid4())
            execute_query("""
                INSERT INTO instances (
                    id, client_id, instance_type, region, az,
                    current_pool_id, current_mode, spot_price, ondemand_price,
                    is_active, installed_at
                )
                SELECT
                    %s, a.client_id, ri.instance_type, ri.region, ri.az,
                    ri.pool_id, 'spot', ri.hourly_cost, NULL,
                    TRUE, NOW()
                FROM replica_instances ri
                JOIN agents a ON ri.agent_id = a.id
                WHERE ri.id = %s
            """, (new_instance_id, replica_id))

            # Step 3: Update agent to point to new instance
            execute_query("""
                UPDATE agents
                SET instance_id = %s,
                    current_replica_id = NULL,
                    last_failover_at = NOW()
                WHERE id = %s
            """, (new_instance_id, agent_id))

            # Step 4: Record the switch
            execute_query("""
                INSERT INTO instance_switches (
                    agent_id, old_instance_id, new_instance_id,
                    switch_reason, switched_at, success
                )
                VALUES (%s, %s, %s, 'manual-replica-promotion', NOW(), TRUE)
            """, (agent_id, old_instance_id, new_instance_id))

            # Step 5: Handle old primary
            if demote_old_primary:
                # Create replica record for old primary
                demoted_replica_id = str(uuid.uuid4())
                execute_query("""
                    INSERT INTO replica_instances (
                        id, agent_id, instance_id, replica_type, pool_id,
                        instance_type, region, az, status, created_by,
                        parent_instance_id
                    )
                    SELECT
                        %s, %s, i.id, 'manual', i.current_pool_id,
                        i.instance_type, i.region, i.az, 'ready', 'system',
                        %s
                    FROM instances i
                    WHERE i.id = %s
                """, (demoted_replica_id, agent_id, new_instance_id, old_instance_id))
            else:
                # Mark old instance as inactive
                execute_query("""
                    UPDATE instances SET is_active = FALSE WHERE id = %s
                """, (old_instance_id,))

            # Step 6: Decrement replica count (promoted replica no longer counted)
            execute_query("""
                UPDATE agents
                SET replica_count = GREATEST(0, replica_count - 1)
                WHERE id = %s
            """, (agent_id,))

            logger.info(f"Promoted replica {replica_id} to primary for agent {agent_id}")

            return jsonify({
                'success': True,
                'message': 'Replica promoted to primary',
                'new_instance_id': new_instance_id,
                'old_instance_id': old_instance_id,
                'demoted': demote_old_primary,
                'switch_time': datetime.now().isoformat()
            }), 200

        except Exception as e:
            logger.error(f"Error promoting replica: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def delete_replica(app):
    """DELETE /api/agents/<agent_id>/replicas/<replica_id> - Delete replica"""
    @app.route('/api/agents/<agent_id>/replicas/<replica_id>', methods=['DELETE'])
    def delete_replica_endpoint(agent_id, replica_id):
        """Gracefully terminate a replica"""
        try:
            # Validate replica exists
            replica = execute_query("""
                SELECT * FROM replica_instances
                WHERE id = %s AND agent_id = %s
            """, (replica_id, agent_id), fetch=True)

            if not replica or len(replica) == 0:
                return jsonify({'error': 'Replica not found'}), 404

            replica = replica[0]

            if not replica['is_active']:
                return jsonify({
                    'error': 'Replica already terminated',
                    'terminated_at': replica['terminated_at'].isoformat() if replica['terminated_at'] else None
                }), 400

            # Mark as terminated
            execute_query("""
                UPDATE replica_instances
                SET status = 'terminated',
                    is_active = FALSE,
                    terminated_at = NOW()
                WHERE id = %s
            """, (replica_id,))

            # Decrement agent replica count
            execute_query("""
                UPDATE agents
                SET replica_count = GREATEST(0, replica_count - 1),
                    current_replica_id = CASE
                        WHEN current_replica_id = %s THEN NULL
                        ELSE current_replica_id
                    END
                WHERE id = %s
            """, (replica_id, agent_id))

            logger.info(f"Deleted replica {replica_id} for agent {agent_id}")

            return jsonify({
                'success': True,
                'message': 'Replica terminated',
                'replica_id': replica_id,
                'terminated_at': datetime.now().isoformat()
            }), 200

        except Exception as e:
            logger.error(f"Error deleting replica: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


# ============================================================================
# AUTOMATIC SPOT INTERRUPTION DEFENSE
# ============================================================================

def create_emergency_replica(app):
    """POST /api/agents/<agent_id>/create-emergency-replica - Emergency replica for interruption"""
    @app.route('/api/agents/<agent_id>/create-emergency-replica', methods=['POST'])
    def create_emergency_replica_endpoint(agent_id):
        """
        Create emergency replica in response to spot interruption signal.

        Request body:
        {
            "signal_type": "rebalance-recommendation" | "termination-notice",
            "termination_time": "2025-01-20T10:45:00Z",  # optional, for termination notice
            "instance_id": "i-1234567890abcdef0",
            "pool_id": 123,
            "preferred_zones": ["us-east-1b", "us-east-1c"],
            "exclude_zones": ["us-east-1a"],
            "urgency": "high" | "critical"
        }
        """
        try:
            data = request.get_json() or {}

            signal_type = data.get('signal_type')
            if signal_type not in ('rebalance-recommendation', 'termination-notice'):
                return jsonify({'error': 'Invalid signal_type'}), 400

            # Get agent details
            agent = execute_query("""
                SELECT a.*, i.id as instance_id, i.instance_type, i.region,
                       i.current_pool_id, i.spot_price, i.created_at as instance_created_at
                FROM agents a
                JOIN instances i ON a.instance_id = i.id
                WHERE a.id = %s
            """, (agent_id,), fetch=True)

            if not agent or len(agent) == 0:
                return jsonify({'error': 'Agent not found'}), 404

            agent = agent[0]

            # Emergency replicas are ONLY created if auto_switch_enabled = true
            # This ties emergency failover to the auto-switch mode
            if not agent.get('auto_switch_enabled'):
                logger.warning(f"Emergency replica creation skipped for agent {agent_id} - auto_switch_enabled is OFF")
                return jsonify({
                    'error': 'Emergency replica creation disabled',
                    'reason': 'auto_switch_enabled is OFF. Enable auto-switch mode in agent configuration to allow automatic emergency replicas.',
                    'hint': 'Turn on Auto-Switch Mode in agent settings to enable emergency failover protection'
                }), 403

            logger.warning(f"Emergency replica creation for agent {agent_id} - auto_switch_enabled is ON")

            # Select best pool for emergency replica
            target_pool_id = _select_safest_pool(
                instance_type=agent['instance_type'],
                region=agent['region'],
                current_pool_id=agent['current_pool_id'],
                preferred_zones=data.get('preferred_zones', []),
                exclude_zones=data.get('exclude_zones', [])
            )

            if not target_pool_id:
                return jsonify({
                    'error': 'No suitable pool found for emergency replica',
                    'hint': 'All pools may be at risk or unavailable'
                }), 500

            # Get pool details
            pool = execute_query("""
                SELECT * FROM spot_pools WHERE id = %s
            """, (target_pool_id,), fetch=True)[0]

            # Get current price
            latest_price = execute_query("""
                SELECT spot_price FROM pricing_snapshots_clean
                WHERE pool_id = %s
                ORDER BY time_bucket DESC
                LIMIT 1
            """, (target_pool_id,), fetch=True)

            hourly_cost = latest_price[0]['spot_price'] if latest_price else None

            # Create emergency replica
            replica_id = str(uuid.uuid4())
            replica_instance_id = f"emergency-{replica_id[:8]}"

            replica_type = 'automatic-rebalance' if signal_type == 'rebalance-recommendation' else 'automatic-termination'

            execute_query("""
                INSERT INTO replica_instances (
                    id, agent_id, instance_id, replica_type, pool_id,
                    instance_type, region, az, status, created_by,
                    parent_instance_id, hourly_cost,
                    interruption_signal_type, interruption_detected_at, termination_time
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, 'launching', 'system',
                    %s, %s, %s, NOW(), %s
                )
            """, (
                replica_id,
                agent_id,
                replica_instance_id,
                replica_type,
                target_pool_id,
                pool['instance_type'],
                pool['region'],
                pool['az'],
                agent['instance_id'],
                hourly_cost,
                signal_type,
                data.get('termination_time')
            ))

            # Update agent
            execute_query("""
                UPDATE agents
                SET replica_count = replica_count + 1,
                    current_replica_id = %s,
                    last_interruption_signal = NOW()
                WHERE id = %s
            """, (replica_id, agent_id))

            # Log interruption event
            execute_query("""
                INSERT INTO spot_interruption_events (
                    instance_id, agent_id, pool_id, signal_type,
                    detected_at, termination_time, response_action,
                    replica_id, instance_age_hours
                ) VALUES (
                    %s, %s, %s, %s, NOW(), %s, 'created-replica', %s,
                    TIMESTAMPDIFF(HOUR, %s, NOW())
                )
            """, (
                data.get('instance_id'),
                agent_id,
                agent['current_pool_id'],
                signal_type,
                data.get('termination_time'),
                replica_id,
                agent['instance_created_at']
            ))

            logger.warning(f"Created emergency replica {replica_id} for agent {agent_id} due to {signal_type}")

            return jsonify({
                'success': True,
                'replica_id': replica_id,
                'instance_id': replica_instance_id,
                'pool': {
                    'id': pool['id'],
                    'name': pool['pool_name'],
                    'az': pool['az']
                },
                'hourly_cost': float(hourly_cost) if hourly_cost else None,
                'message': 'Emergency replica created. Connect immediately for state sync.',
                'urgency': 'critical' if signal_type == 'termination-notice' else 'high'
            }), 201

        except Exception as e:
            logger.error(f"Error creating emergency replica: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def handle_termination_imminent(app):
    """POST /api/agents/<agent_id>/termination-imminent - Handle 2-minute termination notice"""
    @app.route('/api/agents/<agent_id>/termination-imminent', methods=['POST'])
    def handle_termination_imminent_endpoint(agent_id):
        """
        Handle imminent termination (2-minute warning).
        Immediately promote replica if available.

        Request body:
        {
            "instance_id": "i-1234567890abcdef0",
            "termination_time": "2025-01-20T10:47:00Z",
            "replica_id": "uuid-of-ready-replica"  # optional
        }
        """
        try:
            data = request.get_json() or {}

            # Get current replica
            replica_id = data.get('replica_id') or execute_query("""
                SELECT id FROM replica_instances
                WHERE agent_id = %s AND is_active = TRUE
                  AND status IN ('ready', 'syncing')
                ORDER BY
                    CASE WHEN status = 'ready' THEN 1 ELSE 2 END,
                    created_at ASC
                LIMIT 1
            """, (agent_id,), fetch=True)

            if replica_id and isinstance(replica_id, list):
                replica_id = replica_id[0]['id'] if len(replica_id) > 0 else None

            if not replica_id:
                # No replica available - trigger emergency snapshot
                logger.error(f"CRITICAL: No replica available for agent {agent_id} with 2-minute termination notice!")

                execute_query("""
                    INSERT INTO spot_interruption_events (
                        instance_id, agent_id, signal_type, detected_at,
                        termination_time, response_action, success, error_message
                    ) VALUES (
                        %s, %s, 'termination-notice', NOW(), %s,
                        'emergency-snapshot', FALSE, 'No replica available'
                    )
                """, (data.get('instance_id'), agent_id, data.get('termination_time')))

                return jsonify({
                    'success': False,
                    'error': 'No replica available',
                    'action': 'emergency_snapshot_required',
                    'message': 'Agent should create emergency state snapshot and upload to S3'
                }), 500

            # Promote replica immediately
            start_time = time.time()

            # Auto-promote the replica (similar to manual promote but faster)
            agent = execute_query("""
                SELECT instance_id FROM agents WHERE id = %s
            """, (agent_id,), fetch=True)[0]

            old_instance_id = agent['instance_id']

            # Create new instance record for promoted replica
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

            # Update replica status
            execute_query("""
                UPDATE replica_instances
                SET status = 'promoted',
                    promoted_at = NOW(),
                    failover_completed_at = NOW()
                WHERE id = %s
            """, (replica_id,))

            # Record switch
            execute_query("""
                INSERT INTO instance_switches (
                    agent_id, old_instance_id, new_instance_id,
                    switch_reason, switched_at, success
                )
                VALUES (%s, %s, %s, 'automatic-interruption-failover', NOW(), TRUE)
            """, (agent_id, old_instance_id, new_instance_id))

            # Mark old instance as terminated
            execute_query("""
                UPDATE instances SET is_active = FALSE WHERE id = %s
            """, (old_instance_id,))

            # Update interruption event
            failover_time_ms = int((time.time() - start_time) * 1000)

            execute_query("""
                UPDATE spot_interruption_events
                SET replica_ready = TRUE,
                    failover_completed = TRUE,
                    failover_time_ms = %s,
                    success = TRUE
                WHERE instance_id = %s AND agent_id = %s
                ORDER BY detected_at DESC
                LIMIT 1
            """, (failover_time_ms, data.get('instance_id'), agent_id))

            logger.warning(f"FAILOVER COMPLETED: Agent {agent_id} failed over to replica {replica_id} in {failover_time_ms}ms")

            return jsonify({
                'success': True,
                'message': 'Automatic failover completed',
                'new_instance_id': new_instance_id,
                'replica_id': replica_id,
                'failover_time_ms': failover_time_ms,
                'action': 'replica_promoted'
            }), 200

        except Exception as e:
            logger.error(f"Error handling termination: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def update_replica_sync_status(app):
    """POST /api/agents/<agent_id>/replicas/<replica_id>/sync-status - Update sync status"""
    @app.route('/api/agents/<agent_id>/replicas/<replica_id>/sync-status', methods=['POST'])
    def update_replica_sync_status_endpoint(agent_id, replica_id):
        """
        Update replica sync status (called by agent).

        Request body:
        {
            "sync_status": "syncing" | "synced" | "out-of-sync",
            "sync_latency_ms": 150,
            "state_transfer_progress": 85.5,
            "status": "ready"  # optional - update overall status
        }
        """
        try:
            data = request.get_json() or {}

            updates = []
            params = []

            if 'sync_status' in data:
                updates.append("sync_status = %s")
                params.append(data['sync_status'])

            if 'sync_latency_ms' in data:
                updates.append("sync_latency_ms = %s")
                params.append(data['sync_latency_ms'])

            if 'state_transfer_progress' in data:
                updates.append("state_transfer_progress = %s")
                params.append(data['state_transfer_progress'])

                # Auto-update status to ready if 100%
                if data['state_transfer_progress'] >= 100.0:
                    updates.append("status = 'ready'")
                    updates.append("ready_at = NOW()")

            if 'status' in data:
                updates.append("status = %s")
                params.append(data['status'])

                if data['status'] == 'ready' and 'ready_at' not in updates:
                    updates.append("ready_at = NOW()")

            updates.append("last_sync_at = NOW()")

            if not updates:
                return jsonify({'error': 'No updates provided'}), 400

            params.extend([replica_id, agent_id])

            query = f"""
                UPDATE replica_instances
                SET {', '.join(updates)}
                WHERE id = %s AND agent_id = %s
            """

            execute_query(query, tuple(params))

            return jsonify({
                'success': True,
                'message': 'Sync status updated'
            }), 200

        except Exception as e:
            logger.error(f"Error updating sync status: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _select_cheapest_pool(
    instance_type: str,
    region: str,
    current_pool_id: Optional[int] = None,
    exclude_zones: List[str] = None,
    max_cost: Optional[float] = None
) -> Optional[int]:
    """
    Select cheapest compatible pool.
    If current instance is already in the cheapest pool, select the second cheapest.
    """
    exclude_zones = exclude_zones or []

    query = """
        SELECT p.id, p.az, psc.spot_price
        FROM spot_pools p
        JOIN pricing_snapshots_clean psc ON p.id = psc.pool_id
        WHERE p.instance_type = %s
          AND p.region = %s
          AND p.is_available = TRUE
    """
    params = [instance_type, region]

    if exclude_zones:
        placeholders = ','.join(['%s'] * len(exclude_zones))
        query += f" AND p.az NOT IN ({placeholders})"
        params.extend(exclude_zones)

    if max_cost:
        query += " AND psc.spot_price <= %s"
        params.append(max_cost)

    query += """
        AND psc.time_bucket >= NOW() - INTERVAL 5 MINUTE
        ORDER BY psc.spot_price ASC
        LIMIT 2
    """

    results = execute_query(query, tuple(params), fetch=True)

    if not results:
        return None

    # If current pool is the cheapest, return second cheapest
    if current_pool_id and len(results) >= 2 and results[0]['id'] == current_pool_id:
        logger.info(f"Current pool {current_pool_id} is cheapest, selecting second cheapest: {results[1]['id']}")
        return results[1]['id']

    # Otherwise return cheapest (that's not current)
    for result in results:
        if not current_pool_id or result['id'] != current_pool_id:
            return result['id']

    return None


def _select_safest_pool(
    instance_type: str,
    region: str,
    current_pool_id: int,
    preferred_zones: List[str] = None,
    exclude_zones: List[str] = None
) -> Optional[int]:
    """Select safest pool (lowest interruption risk)"""
    exclude_zones = exclude_zones or []
    preferred_zones = preferred_zones or []

    # Get interruption history for all pools
    query = """
        SELECT
            p.id,
            p.az,
            psc.spot_price,
            COUNT(sie.id) as interruption_count,
            MAX(sie.detected_at) as last_interruption
        FROM spot_pools p
        JOIN pricing_snapshots_clean psc ON p.id = psc.pool_id
        LEFT JOIN spot_interruption_events sie
            ON sie.pool_id = p.id
            AND sie.detected_at >= NOW() - INTERVAL 24 HOUR
        WHERE p.instance_type = %s
          AND p.region = %s
          AND p.id != %s
          AND p.is_available = TRUE
    """
    params = [instance_type, region, current_pool_id]

    if exclude_zones:
        placeholders = ','.join(['%s'] * len(exclude_zones))
        query += f" AND p.az NOT IN ({placeholders})"
        params.extend(exclude_zones)

    query += """
        AND psc.time_bucket >= NOW() - INTERVAL 5 MINUTE
        GROUP BY p.id, p.az, psc.spot_price
        ORDER BY
            CASE WHEN p.az IN ({}) THEN 0 ELSE 1 END,
            interruption_count ASC,
            psc.spot_price ASC
        LIMIT 1
    """.format(','.join(['%s'] * len(preferred_zones)) if preferred_zones else 'NULL')

    if preferred_zones:
        params.extend(preferred_zones)

    result = execute_query(query, tuple(params), fetch=True)
    return result[0]['id'] if result else None


# ============================================================================
# REGISTER ALL ENDPOINTS
# ============================================================================

def register_replica_management_endpoints(app):
    """Register all replica management endpoints with Flask app"""
    create_manual_replica(app)
    list_replicas(app)
    promote_replica(app)
    delete_replica(app)
    create_emergency_replica(app)
    handle_termination_imminent(app)
    update_replica_sync_status(app)

    logger.info("Replica management endpoints registered")
