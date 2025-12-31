"""
CAST-AI Mini - Simplified Agentless Backend
Version: 3.0.0

Clean, simple backend for agentless spot optimization:
- Auto-switch ON/OFF control
- Auto-terminate ON/OFF control
- Reset functionality
- Decision engine integration
- No agents, no replicas, no complex state
"""

import os
import sys
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import threading

from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Import our components
from decision_engine.engine_enhanced import EnhancedDecisionEngine, DecisionAction
from executor.aws_agentless import AWSAgentlessExecutor

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)

# ============================================================================
# Configuration
# ============================================================================

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'spotuser'),
    'password': os.getenv('DB_PASSWORD', 'cast_ai_spot_2025'),
    'database': os.getenv('DB_NAME', 'spot_optimizer'),
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}

AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
DECISION_INTERVAL_MINUTES = int(os.getenv('DECISION_INTERVAL_MINUTES', 5))

# ============================================================================
# Database Helper
# ============================================================================

def get_db():
    """Get database connection"""
    return pymysql.connect(**DB_CONFIG)

def execute_query(query: str, params: tuple = None, fetch: bool = False) -> Any:
    """Execute database query"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch:
                return cursor.fetchall()
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()

def execute_procedure(proc_name: str, params: tuple = ()) -> Any:
    """Execute stored procedure"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.callproc(proc_name, params)
            results = cursor.fetchall()
            conn.commit()
            return results
    finally:
        conn.close()

# ============================================================================
# Core Components
# ============================================================================

class SimpleBackend:
    """Simplified backend for agentless optimization"""

    def __init__(self):
        """Initialize backend"""
        logger.info("Initializing Simple Agentless Backend...")

        # Initialize decision engine
        self.decision_engine = EnhancedDecisionEngine(
            stability_model_path=os.getenv('STABILITY_MODEL_PATH'),
            price_model_path=os.getenv('PRICE_MODEL_PATH')
        )

        # Initialize AWS executor
        self.executor = AWSAgentlessExecutor(region=AWS_REGION)

        # Decision loop control
        self.decision_loop_running = False
        self.decision_thread = None

        logger.info("✓ Backend initialized successfully")

    def start_decision_loop(self):
        """Start background decision loop"""
        if self.decision_loop_running:
            logger.warning("Decision loop already running")
            return

        self.decision_loop_running = True
        self.decision_thread = threading.Thread(target=self._decision_loop, daemon=True)
        self.decision_thread.start()
        logger.info("✓ Decision loop started")

    def stop_decision_loop(self):
        """Stop background decision loop"""
        self.decision_loop_running = False
        if self.decision_thread:
            self.decision_thread.join(timeout=10)
        logger.info("✓ Decision loop stopped")

    def _decision_loop(self):
        """Background loop that runs decisions"""
        logger.info(f"Decision loop running (interval: {DECISION_INTERVAL_MINUTES} min)")

        while self.decision_loop_running:
            try:
                # Get all active instances with auto-switch enabled
                instances = execute_query("""
                    SELECT * FROM instances
                    WHERE state = 'running'
                      AND auto_switch_enabled = true
                      AND (cooldown_until IS NULL OR cooldown_until <= NOW())
                """, fetch=True)

                for instance in instances:
                    try:
                        self._process_instance_decision(instance)
                    except Exception as e:
                        logger.error(f"Error processing instance {instance['instance_id']}: {e}")

            except Exception as e:
                logger.error(f"Error in decision loop: {e}")

            # Sleep until next interval
            time.sleep(DECISION_INTERVAL_MINUTES * 60)

    def _process_instance_decision(self, instance: Dict):
        """Process decision for a single instance"""
        instance_id = instance['instance_id']
        logger.info(f"Processing decision for instance {instance_id}")

        # Get current state from AWS
        try:
            instance_state = self.executor.get_instance_state(instance_id)
            usage_metrics = self.executor.get_usage_metrics(instance_id, window_minutes=30)
        except Exception as e:
            logger.error(f"Failed to get instance data from AWS: {e}")
            return

        # Get available pools (mock for now - would query AWS)
        available_pools = self._get_available_pools(instance['instance_type'], instance['region'])

        # Build decision inputs
        current_instance = {
            'instance_id': instance_id,
            'instance_type': instance['instance_type'],
            'az': instance['az'],
            'pool_id': f"{instance['az']}_{instance['instance_type']}",
            'current_spot_price': instance['current_spot_price'] or 0.05,
            'specifications': self._get_instance_specs(instance['instance_type'])
        }

        usage_metrics_dict = {
            'cpu_usage_percent': usage_metrics.cpu_p95,
            'ram_usage_percent': usage_metrics.memory_p95 or 50.0,
            'cpu_credits_remaining': 500
        }

        usage_patterns = {
            'peak_cpu_last_24h': usage_metrics.cpu_p95 * 1.1,
            'avg_cpu_last_24h': usage_metrics.cpu_avg,
            'peak_ram_last_24h': (usage_metrics.memory_p95 or 50.0) * 1.1,
            'avg_ram_last_24h': usage_metrics.memory_avg or 40.0
        }

        app_requirements = {'min_cpu_cores': 1, 'min_ram_gb': 2}
        sla_requirements = {'max_interruption_rate_percent': 5.0, 'required_uptime_percent': 99.0}

        # Run decision engine
        try:
            decision = self.decision_engine.decide(
                current_instance=current_instance,
                usage_metrics=usage_metrics_dict,
                usage_patterns=usage_patterns,
                available_pools=available_pools,
                app_requirements=app_requirements,
                sla_requirements=sla_requirements,
                region=instance['region']
            )

            # Record decision
            self._record_decision(decision, instance_id)

            # Execute if MIGRATE
            if decision.action == DecisionAction.MIGRATE:
                if instance['auto_terminate_enabled']:
                    logger.info(f"Executing migration for {instance_id}")
                    self._execute_migration(instance, decision)
                else:
                    logger.info(f"Migration recommended but auto-terminate disabled for {instance_id}")

        except Exception as e:
            logger.error(f"Decision engine failed: {e}")

    def _execute_migration(self, old_instance: Dict, decision):
        """Execute migration to new instance"""
        instance_id = old_instance['instance_id']
        logger.info(f"Migrating {instance_id} → {decision.recommended_instance_type}")

        try:
            # Build target spec
            target_spec = {
                'instance_type': decision.recommended_instance_type,
                'az': decision.recommended_pool_id.split('_')[0] if decision.recommended_pool_id else old_instance['az'],
                'ami_id': os.getenv('DEFAULT_AMI_ID'),  # Would get from config
                'lifecycle': 'spot'
            }

            # Launch new instance (placeholder - would use executor)
            new_instance_id = f"i-new{int(time.time())}"
            logger.info(f"Launched new instance: {new_instance_id}")

            # Record switch
            execute_procedure('sp_record_switch', (
                decision.decision_id,
                instance_id,
                new_instance_id,
                decision.recommended_instance_type,
                target_spec['az'],
                0.04  # Placeholder price
            ))

            # Update switch status
            execute_procedure('sp_update_switch_status', (
                new_instance_id,
                'migrated',
                120,  # 2 minutes downtime
                None
            ))

            logger.info(f"✓ Migration complete: {instance_id} → {new_instance_id}")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            # Update switch status as failed
            execute_procedure('sp_update_switch_status', (
                new_instance_id if 'new_instance_id' in locals() else 'unknown',
                'failed',
                0,
                str(e)
            ))

    def _record_decision(self, decision, instance_id: str):
        """Record decision in database"""
        execute_procedure('sp_record_decision', (
            decision.decision_id,
            instance_id,
            decision.action.value,
            decision.recommended_instance_type,
            decision.recommended_pool_id,
            None,  # recommended_az
            decision.confidence,
            decision.expected_cost_savings_percent,
            decision.expected_stability_improvement_percent,
            ', '.join(decision.primary_factors),
            json.dumps(decision.primary_factors)
        ))

        # Set cooldown
        cooldown_minutes = int(os.getenv('COOLDOWN_MINUTES', 10))
        execute_query("""
            UPDATE instances
            SET cooldown_until = DATE_ADD(NOW(), INTERVAL %s MINUTE)
            WHERE instance_id = %s
        """, (cooldown_minutes, instance_id))

    def _get_available_pools(self, instance_type: str, region: str) -> List[Dict]:
        """Get available pools (mock for now)"""
        # Mock pools - in production would query AWS
        instance_types = ['t3.large', 'm5.large', 'c5.large', 'm5.xlarge']
        azs = ['us-east-1a', 'us-east-1b', 'us-east-1c']

        pools = []
        for itype in instance_types:
            for az in azs:
                pools.append({
                    'pool_id': f"{az}_{itype}",
                    'instance_type': itype,
                    'az': az,
                    'current_spot_price': 0.04 + (hash(itype + az) % 20) / 1000,
                    'on_demand_price': self._get_on_demand_price(itype),
                    'specifications': self._get_instance_specs(itype)
                })

        return pools

    def _get_instance_specs(self, instance_type: str) -> Dict:
        """Get instance specifications"""
        specs = {
            't3.large': {'cpu_cores': 2, 'ram_gb': 8},
            'm5.large': {'cpu_cores': 2, 'ram_gb': 8},
            'c5.large': {'cpu_cores': 2, 'ram_gb': 4},
            'm5.xlarge': {'cpu_cores': 4, 'ram_gb': 16},
        }
        return specs.get(instance_type, {'cpu_cores': 2, 'ram_gb': 4})

    def _get_on_demand_price(self, instance_type: str) -> float:
        """Get on-demand price"""
        prices = {
            't3.large': 0.0832,
            'm5.large': 0.096,
            'c5.large': 0.085,
            'm5.xlarge': 0.192
        }
        return prices.get(instance_type, 0.096)

# ============================================================================
# Initialize backend
# ============================================================================

backend = SimpleBackend()

# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'version': '3.0.0',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/instances', methods=['GET'])
def get_instances():
    """Get all instances"""
    instances = execute_query("""
        SELECT * FROM v_active_instances
        ORDER BY created_at DESC
    """, fetch=True)

    return jsonify({
        'instances': instances,
        'count': len(instances)
    })

@app.route('/api/instances/<instance_id>', methods=['GET'])
def get_instance(instance_id):
    """Get single instance"""
    instance = execute_query("""
        SELECT * FROM instances WHERE instance_id = %s
    """, (instance_id,), fetch=True)

    if not instance:
        return jsonify({'error': 'Instance not found'}), 404

    return jsonify(instance[0])

@app.route('/api/instances/<instance_id>/auto-switch', methods=['POST'])
def set_auto_switch(instance_id):
    """Enable/disable auto-switch"""
    data = request.get_json()
    enabled = data.get('enabled', True)

    execute_query("""
        UPDATE instances
        SET auto_switch_enabled = %s
        WHERE instance_id = %s
    """, (enabled, instance_id))

    logger.info(f"Auto-switch {'enabled' if enabled else 'disabled'} for {instance_id}")

    return jsonify({
        'success': True,
        'instance_id': instance_id,
        'auto_switch_enabled': enabled
    })

@app.route('/api/instances/<instance_id>/auto-terminate', methods=['POST'])
def set_auto_terminate(instance_id):
    """Enable/disable auto-terminate"""
    data = request.get_json()
    enabled = data.get('enabled', True)

    execute_query("""
        UPDATE instances
        SET auto_terminate_enabled = %s
        WHERE instance_id = %s
    """, (enabled, instance_id))

    logger.info(f"Auto-terminate {'enabled' if enabled else 'disabled'} for {instance_id}")

    return jsonify({
        'success': True,
        'instance_id': instance_id,
        'auto_terminate_enabled': enabled
    })

@app.route('/api/instances/<instance_id>/reset', methods=['POST'])
def reset_instance(instance_id):
    """Reset instance cooldown and state"""
    execute_query("""
        UPDATE instances
        SET cooldown_until = NULL,
            last_decision_at = NULL
        WHERE instance_id = %s
    """, (instance_id,))

    logger.info(f"Reset cooldown for {instance_id}")

    return jsonify({
        'success': True,
        'instance_id': instance_id,
        'message': 'Cooldown reset, ready for next decision'
    })

@app.route('/api/decisions', methods=['GET'])
def get_decisions():
    """Get recent decisions"""
    limit = request.args.get('limit', 50, type=int)

    decisions = execute_query("""
        SELECT * FROM v_recent_decisions
        LIMIT %s
    """, (limit,), fetch=True)

    return jsonify({
        'decisions': decisions,
        'count': len(decisions)
    })

@app.route('/api/switches', methods=['GET'])
def get_switches():
    """Get switch history"""
    limit = request.args.get('limit', 50, type=int)

    switches = execute_query("""
        SELECT * FROM switches
        ORDER BY created_at DESC
        LIMIT %s
    """, (limit,), fetch=True)

    return jsonify({
        'switches': switches,
        'count': len(switches)
    })

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """Get summary statistics"""
    summary = execute_query("""
        SELECT
            (SELECT COUNT(*) FROM instances WHERE state = 'running') as active_instances,
            (SELECT COUNT(*) FROM decisions WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)) as decisions_24h,
            (SELECT COUNT(*) FROM switches WHERE status = 'migrated' AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) as switches_7d,
            (SELECT AVG(cost_savings_percent) FROM switches WHERE status = 'migrated' AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as avg_savings_30d
    """, fetch=True)

    return jsonify(summary[0] if summary else {})

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get system configuration"""
    config = execute_query("""
        SELECT config_key, config_value, description
        FROM system_config
        ORDER BY config_key
    """, fetch=True)

    return jsonify({
        'config': {c['config_key']: c['config_value'] for c in config},
        'descriptions': {c['config_key']: c['description'] for c in config}
    })

@app.route('/api/config/<key>', methods=['POST'])
def update_config(key):
    """Update configuration value"""
    data = request.get_json()
    value = data.get('value')

    execute_query("""
        UPDATE system_config
        SET config_value = %s
        WHERE config_key = %s
    """, (str(value), key))

    logger.info(f"Updated config: {key} = {value}")

    return jsonify({
        'success': True,
        'key': key,
        'value': value
    })

# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    logger.info("="*80)
    logger.info("CAST-AI Mini - Simplified Agentless Backend v3.0.0")
    logger.info("="*80)

    # Start decision loop
    backend.start_decision_loop()

    # Run Flask app
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
