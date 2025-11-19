"""
AWS Spot Optimizer - Central Server Backend v3.0
==============================================================
Modular, production-ready central server with:
- Pluggable decision engine architecture
- Model registry and management
- Agent connection management
- Comprehensive logging and monitoring
- RESTful API for frontend and agents
==============================================================
"""

import os
import sys
import json
import secrets
import string
import logging
import importlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error, pooling
from marshmallow import Schema, fields, validate, ValidationError
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('central_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

class Config:
    """Server configuration with environment variable support"""
    
    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
    DB_NAME = os.getenv('DB_NAME', 'spot_optimizer')
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 10))
    
    # Decision Engine
    DECISION_ENGINE_MODULE = os.getenv('DECISION_ENGINE_MODULE', 'decision_engines.ml_based_engine')
    DECISION_ENGINE_CLASS = os.getenv('DECISION_ENGINE_CLASS', 'MLBasedDecisionEngine')
    MODEL_DIR = Path(os.getenv('MODEL_DIR', './models'))
    
    # Server
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Agent Communication
    AGENT_HEARTBEAT_TIMEOUT = int(os.getenv('AGENT_HEARTBEAT_TIMEOUT', 120))  # seconds
    
    # Background Jobs
    ENABLE_BACKGROUND_JOBS = os.getenv('ENABLE_BACKGROUND_JOBS', 'True').lower() == 'true'

config = Config()

# ==============================================================================
# FLASK APP INITIALIZATION
# ==============================================================================

app = Flask(__name__)
CORS(app)

# ==============================================================================
# DATABASE CONNECTION POOLING
# ==============================================================================

connection_pool = None

def init_db_pool():
    """Initialize database connection pool"""
    global connection_pool
    try:
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="spot_optimizer_pool",
            pool_size=config.DB_POOL_SIZE,
            pool_reset_session=True,
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            autocommit=False
        )
        logger.info(f"✓ Database connection pool initialized (size: {config.DB_POOL_SIZE})")
    except Error as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise

def get_db_connection():
    """Get connection from pool"""
    try:
        return connection_pool.get_connection()
    except Error as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise

def execute_query(query: str, params: tuple = None, fetch: bool = False, 
                 fetch_one: bool = False, commit: bool = True) -> Any:
    """Execute database query with error handling"""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        if fetch_one:
            result = cursor.fetchone()
        elif fetch:
            result = cursor.fetchall()
        else:
            result = cursor.lastrowid if cursor.lastrowid else None
            
        if commit and not fetch and not fetch_one:
            connection.commit()
            
        return result
    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Query execution error: {e}")
        logger.error(f"Query: {query}")
        log_system_event('database_error', 'error', str(e), metadata={'query': query[:200]})
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def generate_client_token() -> str:
    """Generate a secure random client token"""
    alphabet = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(32))
    return f"token-{random_part}"

def generate_client_id() -> str:
    """Generate a unique client ID"""
    return f"client-{secrets.token_hex(4)}"

def log_system_event(event_type: str, severity: str, message: str, 
                     client_id: str = None, agent_id: str = None, 
                     instance_id: str = None, metadata: dict = None):
    """Log system event to database"""
    try:
        execute_query("""
            INSERT INTO system_events (event_type, severity, client_id, agent_id, 
                                      instance_id, message, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (event_type, severity, client_id, agent_id, instance_id, 
              message, json.dumps(metadata) if metadata else None))
    except Exception as e:
        logger.error(f"Failed to log system event: {e}")

def create_notification(message: str, severity: str = 'info', client_id: str = None):
    """Create a notification"""
    try:
        execute_query("""
            INSERT INTO notifications (message, severity, client_id, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (message, severity, client_id))
        logger.info(f"Notification created: {message[:50]}...")
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")

# ==============================================================================
# INPUT VALIDATION SCHEMAS
# ==============================================================================

class AgentRegistrationSchema(Schema):
    """Validation schema for agent registration"""
    client_token = fields.Str(required=True)
    hostname = fields.Str(required=True, validate=validate.Length(max=255))
    logical_agent_id = fields.Str(required=True, validate=validate.Length(max=128))
    instance_id = fields.Str(required=True, validate=validate.Regexp(r'^i-[a-f0-9]+$'))
    instance_type = fields.Str(required=True, validate=validate.Length(max=64))
    region = fields.Str(required=True, validate=validate.Regexp(r'^[a-z]+-[a-z]+-\d+$'))
    az = fields.Str(required=True, validate=validate.Regexp(r'^[a-z]+-[a-z]+-\d+[a-z]$'))
    ami_id = fields.Str(required=True, validate=validate.Regexp(r'^ami-[a-f0-9]+$'))
    mode = fields.Str(required=True, validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
    agent_version = fields.Str(required=True, validate=validate.Length(max=32))
    private_ip = fields.Str(required=False, validate=validate.Length(max=45))
    public_ip = fields.Str(required=False, validate=validate.Length(max=45))

class HeartbeatSchema(Schema):
    """Validation schema for heartbeat"""
    status = fields.Str(required=True, validate=validate.OneOf(['online', 'offline', 'disabled', 'switching', 'error']))
    instance_id = fields.Str(required=True)
    instance_type = fields.Str(required=True)
    mode = fields.Str(required=True)
    az = fields.Str(required=True)

class PricingReportSchema(Schema):
    """Validation schema for pricing report"""
    instance = fields.Dict(required=True)
    pricing = fields.Dict(required=True)

class SwitchReportSchema(Schema):
    """Validation schema for switch report"""
    old_instance = fields.Dict(required=True)
    new_instance = fields.Dict(required=True)
    timing = fields.Dict(required=True)
    pricing = fields.Dict(required=True)
    trigger = fields.Str(required=True, validate=validate.OneOf(['manual', 'model', 'emergency', 'scheduled']))
    command_id = fields.Int(required=False)

class ForceSwitchSchema(Schema):
    """Validation schema for force switch"""
    target = fields.Str(required=True, validate=validate.OneOf(['ondemand', 'pool']))
    pool_id = fields.Str(required=False, validate=validate.Length(max=128))

# ==============================================================================
# AUTHENTICATION MIDDLEWARE
# ==============================================================================

def require_client_token(f):
    """Validate client token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.json.get('client_token') if request.json else None
        
        if not token:
            return jsonify({'error': 'Missing client token'}), 401
        
        client = execute_query(
            "SELECT id, name FROM clients WHERE client_token = %s AND status = 'active'",
            (token,),
            fetch_one=True
        )
        
        if not client:
            log_system_event('auth_failed', 'warning', 'Invalid client token attempt')
            return jsonify({'error': 'Invalid client token'}), 401
        
        request.client_id = client['id']
        request.client_name = client['name']
        return f(*args, **kwargs)
    
    return decorated_function

# ==============================================================================
# DECISION ENGINE MANAGEMENT
# ==============================================================================

class DecisionEngineManager:
    """Manages decision engine lifecycle and model registry"""
    
    def __init__(self):
        self.engine = None
        self.engine_type = None
        self.engine_version = None
        self.models_loaded = False
        
    def load_engine(self):
        """Load decision engine dynamically"""
        try:
            logger.info(f"Loading decision engine: {config.DECISION_ENGINE_MODULE}.{config.DECISION_ENGINE_CLASS}")
            
            # Import module dynamically
            module = importlib.import_module(config.DECISION_ENGINE_MODULE)
            engine_class = getattr(module, config.DECISION_ENGINE_CLASS)
            
            # Initialize engine
            self.engine = engine_class(
                model_dir=config.MODEL_DIR,
                db_connection_func=get_db_connection
            )
            
            # Load models
            self.engine.load()
            
            self.engine_type = config.DECISION_ENGINE_CLASS
            self.engine_version = getattr(self.engine, 'version', 'unknown')
            self.models_loaded = True
            
            logger.info(f"✓ Decision engine loaded: {self.engine_type} v{self.engine_version}")
            log_system_event('decision_engine_loaded', 'info', 
                           f'Decision engine {self.engine_type} loaded successfully')
            
            # Register models in database
            self._register_models()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load decision engine: {e}", exc_info=True)
            log_system_event('decision_engine_load_failed', 'error', str(e))
            self.models_loaded = False
            return False
    
    def _register_models(self):
        """Register loaded models in the database"""
        if not hasattr(self.engine, 'get_model_info'):
            return
            
        try:
            models_info = self.engine.get_model_info()
            
            for model_info in models_info:
                execute_query("""
                    INSERT INTO model_registry 
                    (id, model_name, model_type, version, file_path, is_active, 
                     performance_metrics, config, loaded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        is_active = VALUES(is_active),
                        loaded_at = NOW()
                """, (
                    model_info.get('id'),
                    model_info.get('name'),
                    model_info.get('type'),
                    model_info.get('version'),
                    model_info.get('file_path'),
                    model_info.get('is_active', True),
                    json.dumps(model_info.get('metrics', {})),
                    json.dumps(model_info.get('config', {}))
                ))
            
            logger.info(f"✓ Registered {len(models_info)} models in database")
            
        except Exception as e:
            logger.error(f"Failed to register models: {e}")
    
    def make_decision(self, instance: dict, pricing: dict, config_data: dict,
                     recent_switches_count: int, last_switch_time: datetime) -> dict:
        """Make switching decision using loaded engine"""
        if not self.engine or not self.models_loaded:
            return self._get_default_decision(instance)
        
        try:
            start_time = datetime.utcnow()
            
            decision = self.engine.make_decision(
                instance=instance,
                pricing=pricing,
                config=config_data,
                recent_switches_count=recent_switches_count,
                last_switch_time=last_switch_time
            )
            
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log decision
            self._log_decision(instance, decision, execution_time)
            
            return decision
            
        except Exception as e:
            logger.error(f"Decision engine error: {e}", exc_info=True)
            log_system_event('decision_error', 'error', str(e), 
                           instance_id=instance.get('instance_id'))
            return self._get_default_decision(instance)
    
    def _get_default_decision(self, instance: dict) -> dict:
        """Return safe default decision when engine fails"""
        return {
            'instance_id': instance.get('instance_id'),
            'risk_score': 0.0,
            'recommended_action': 'stay',
            'recommended_mode': instance.get('current_mode'),
            'recommended_pool_id': instance.get('current_pool_id'),
            'expected_savings_per_hour': 0.0,
            'allowed': False,
            'reason': 'Decision engine unavailable - staying in current mode for safety'
        }
    
    def _log_decision(self, instance: dict, decision: dict, execution_time_ms: int):
        """Log decision to database"""
        try:
            models_used = []
            if hasattr(self.engine, 'get_models_used'):
                models_used = self.engine.get_models_used()
            
            execute_query("""
                INSERT INTO decision_engine_log
                (engine_type, engine_version, instance_id, input_data, output_decision,
                 execution_time_ms, models_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                self.engine_type,
                self.engine_version,
                instance.get('instance_id'),
                json.dumps(instance),
                json.dumps(decision),
                execution_time_ms,
                json.dumps(models_used)
            ))
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")

# Initialize decision engine manager
decision_engine_manager = DecisionEngineManager()

# ==============================================================================
# AGENT-FACING API ENDPOINTS
# ==============================================================================

@app.route('/api/agents/register', methods=['POST'])
@require_client_token
def register_agent():
    """Register new agent with validation"""
    data = request.json
    
    schema = AgentRegistrationSchema()
    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        log_system_event('validation_error', 'warning', 
                        f"Agent registration validation failed: {e.messages}")
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    
    try:
        agent_id = f"agent-{validated_data['instance_id'][:8]}-{secrets.token_hex(4)}"
        
        # Check if agent exists
        existing = execute_query(
            "SELECT id FROM agents WHERE logical_agent_id = %s AND client_id = %s",
            (validated_data['logical_agent_id'], request.client_id),
            fetch_one=True
        )
        
        if existing:
            agent_id = existing['id']
            # Update existing agent
            execute_query("""
                UPDATE agents 
                SET status = 'online', hostname = %s, agent_version = %s,
                    private_ip = %s, public_ip = %s, last_heartbeat = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (
                validated_data.get('hostname'),
                validated_data.get('agent_version'),
                validated_data.get('private_ip'),
                validated_data.get('public_ip'),
                agent_id
            ))
        else:
            # Insert new agent
            execute_query("""
                INSERT INTO agents 
                (id, client_id, logical_agent_id, hostname, status, agent_version,
                 private_ip, public_ip, last_heartbeat)
                VALUES (%s, %s, %s, %s, 'online', %s, %s, %s, NOW())
            """, (
                agent_id,
                request.client_id,
                validated_data['logical_agent_id'],
                validated_data.get('hostname'),
                validated_data.get('agent_version'),
                validated_data.get('private_ip'),
                validated_data.get('public_ip')
            ))
            
            # Create default config
            execute_query("""
                INSERT INTO agent_configs (agent_id)
                VALUES (%s)
            """, (agent_id,))
            
            create_notification(
                f"New agent registered: {agent_id}",
                'info',
                request.client_id
            )
        
        # Get agent config
        config_data = execute_query("""
            SELECT ac.*, a.enabled, a.auto_switch_enabled, a.auto_terminate_enabled
            FROM agent_configs ac
            JOIN agents a ON a.id = ac.agent_id
            WHERE ac.agent_id = %s
        """, (agent_id,), fetch_one=True)
        
        # Handle instance registration
        instance_exists = execute_query(
            "SELECT id, baseline_ondemand_price FROM instances WHERE id = %s",
            (validated_data['instance_id'],),
            fetch_one=True
        )
        
        if not instance_exists:
            # Get latest on-demand price
            latest_od_price = execute_query("""
                SELECT price FROM ondemand_price_snapshots
                WHERE region = %s AND instance_type = %s
                ORDER BY captured_at DESC
                LIMIT 1
            """, (validated_data['region'], validated_data['instance_type']), fetch_one=True)
            
            baseline_price = latest_od_price['price'] if latest_od_price else 0.1
            
            execute_query("""
                INSERT INTO instances 
                (id, client_id, agent_id, instance_type, region, az, ami_id,
                 current_mode, is_active, baseline_ondemand_price, installed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, NOW())
            """, (
                validated_data['instance_id'],
                request.client_id,
                agent_id,
                validated_data['instance_type'],
                validated_data['region'],
                validated_data['az'],
                validated_data['ami_id'],
                validated_data['mode'],
                baseline_price
            ))
        
        log_system_event('agent_registered', 'info', 
                        f"Agent {agent_id} registered successfully",
                        request.client_id, agent_id, validated_data['instance_id'])
        
        return jsonify({
            'agent_id': agent_id,
            'client_id': request.client_id,
            'config': {
                'enabled': config_data['enabled'],
                'auto_switch_enabled': config_data['auto_switch_enabled'],
                'auto_terminate_enabled': config_data['auto_terminate_enabled'],
                'min_savings_percent': float(config_data['min_savings_percent']),
                'risk_threshold': float(config_data['risk_threshold']),
                'max_switches_per_week': config_data['max_switches_per_week'],
                'min_pool_duration_hours': config_data['min_pool_duration_hours']
            }
        })
        
    except Exception as e:
        logger.error(f"Agent registration error: {e}", exc_info=True)
        log_system_event('agent_registration_failed', 'error', str(e), 
                        request.client_id)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/heartbeat', methods=['POST'])
@require_client_token
def agent_heartbeat(agent_id: str):
    """Update agent heartbeat"""
    data = request.json
    
    schema = HeartbeatSchema()
    try:
        schema.load(data)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    
    try:
        prev_status = execute_query(
            "SELECT status FROM agents WHERE id = %s",
            (agent_id,),
            fetch_one=True
        )
        
        new_status = data.get('status', 'online')
        
        execute_query("""
            UPDATE agents 
            SET status = %s, last_heartbeat = NOW()
            WHERE id = %s AND client_id = %s
        """, (new_status, agent_id, request.client_id))
        
        # Check for status change
        if prev_status and prev_status['status'] != new_status:
            if new_status == 'offline':
                create_notification(
                    f"Agent {agent_id} went offline",
                    'warning',
                    request.client_id
                )
            elif new_status == 'online' and prev_status['status'] == 'offline':
                create_notification(
                    f"Agent {agent_id} is back online",
                    'info',
                    request.client_id
                )
        
        # Update client sync time
        execute_query(
            "UPDATE clients SET last_sync_at = NOW() WHERE id = %s",
            (request.client_id,)
        )
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/pricing-report', methods=['POST'])
@require_client_token
def pricing_report(agent_id: str):
    """Receive pricing data from agent"""
    data = request.json
    
    schema = PricingReportSchema()
    try:
        schema.load(data)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    
    try:
        instance = data['instance']
        pricing = data['pricing']
        
        # Update instance pricing
        execute_query("""
            UPDATE instances
            SET ondemand_price = %s, updated_at = NOW()
            WHERE id = %s AND client_id = %s
        """, (pricing['on_demand_price'], instance['instance_id'], request.client_id))
        
        # Store spot pool data
        for pool in pricing['spot_pools']:
            pool_id = pool['pool_id']
            
            # Ensure pool exists
            execute_query("""
                INSERT INTO spot_pools (id, instance_type, region, az)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE id = id
            """, (pool_id, instance['instance_type'], instance['region'], pool['az']))
            
            # Store price snapshot
            execute_query("""
                INSERT INTO spot_price_snapshots (pool_id, price, captured_at)
                VALUES (%s, %s, NOW())
            """, (pool_id, pool['price']))
        
        # Store on-demand price snapshot
        execute_query("""
            INSERT INTO ondemand_price_snapshots (region, instance_type, price, captured_at)
            VALUES (%s, %s, %s, NOW())
        """, (instance['region'], instance['instance_type'], pricing['on_demand_price']))
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Pricing report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/config', methods=['GET'])
@require_client_token
def get_agent_config(agent_id: str):
    """Get agent configuration"""
    try:
        config_data = execute_query("""
            SELECT ac.*, a.enabled, a.auto_switch_enabled, a.auto_terminate_enabled
            FROM agent_configs ac
            JOIN agents a ON a.id = ac.agent_id
            WHERE ac.agent_id = %s AND a.client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)
        
        if not config_data:
            return jsonify({'error': 'Agent not found'}), 404
        
        return jsonify({
            'enabled': config_data['enabled'],
            'auto_switch_enabled': config_data['auto_switch_enabled'],
            'auto_terminate_enabled': config_data['auto_terminate_enabled'],
            'min_savings_percent': float(config_data['min_savings_percent']),
            'risk_threshold': float(config_data['risk_threshold']),
            'max_switches_per_week': config_data['max_switches_per_week'],
            'min_pool_duration_hours': config_data['min_pool_duration_hours']
        })
        
    except Exception as e:
        logger.error(f"Get config error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/pending-commands', methods=['GET'])
@require_client_token
def get_pending_commands(agent_id: str):
    """Get pending commands for agent (sorted by priority)"""
    try:
        commands = execute_query("""
            SELECT * FROM pending_switch_commands
            WHERE agent_id = %s AND executed_at IS NULL
            ORDER BY priority DESC, created_at ASC
        """, (agent_id,), fetch=True)
        
        return jsonify([{
            'id': cmd['id'],
            'instance_id': cmd['instance_id'],
            'target_mode': cmd['target_mode'],
            'target_pool_id': cmd['target_pool_id'],
            'priority': cmd['priority'],
            'terminate_wait_seconds': cmd['terminate_wait_seconds'],
            'created_at': cmd['created_at'].isoformat()
        } for cmd in commands or []])
        
    except Exception as e:
        logger.error(f"Get pending commands error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/commands/<int:command_id>/executed', methods=['POST'])
@require_client_token
def mark_command_executed(agent_id: str, command_id: int):
    """Mark command as executed"""
    data = request.json
    
    try:
        execute_query("""
            UPDATE pending_switch_commands
            SET executed_at = NOW(),
                execution_result = %s
            WHERE id = %s AND agent_id = %s
        """, (json.dumps(data), command_id, agent_id))
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Mark command executed error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/switch-report', methods=['POST'])
@require_client_token
def switch_report(agent_id: str):
    """Record switch event"""
    data = request.json
    
    schema = SwitchReportSchema()
    try:
        schema.load(data)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    
    try:
        old_inst = data['old_instance']
        new_inst = data['new_instance']
        timing = data['timing']
        prices = data['pricing']
        
        savings_impact = (prices.get('old_spot', prices['on_demand']) - 
                         prices.get('new_spot', prices['on_demand']))
        
        # Insert switch event
        execute_query("""
            INSERT INTO switch_events (
                client_id, agent_id, instance_id, old_instance_id, new_instance_id,
                event_trigger, from_mode, to_mode, from_pool_id, to_pool_id,
                on_demand_price, old_spot_price, new_spot_price, savings_impact,
                ami_id, timing_data, timestamp
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.client_id, agent_id, new_inst['instance_id'],
            old_inst['instance_id'], new_inst['instance_id'],
            data['trigger'], old_inst['mode'], new_inst['mode'],
            old_inst.get('pool_id'), new_inst.get('pool_id'),
            prices['on_demand'], prices.get('old_spot'), prices.get('new_spot'),
            savings_impact, new_inst.get('ami_id'),
            json.dumps(timing),
            timing.get('instance_launched_at', datetime.utcnow().isoformat())
        ))
        
        # Deactivate old instance
        execute_query("""
            UPDATE instances
            SET is_active = FALSE, terminated_at = %s
            WHERE id = %s AND client_id = %s
        """, (timing.get('old_terminated_at'), old_inst['instance_id'], request.client_id))
        
        # Register new instance
        execute_query("""
            INSERT INTO instances (
                id, client_id, agent_id, instance_type, region, az, ami_id,
                current_mode, current_pool_id, spot_price, ondemand_price,
                is_active, installed_at, last_switch_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
            ON DUPLICATE KEY UPDATE
                current_mode = VALUES(current_mode),
                current_pool_id = VALUES(current_pool_id),
                spot_price = VALUES(spot_price),
                is_active = TRUE,
                last_switch_at = VALUES(last_switch_at)
        """, (
            new_inst['instance_id'], request.client_id, agent_id,
            new_inst['instance_type'], new_inst['region'], new_inst['az'],
            new_inst.get('ami_id'), new_inst['mode'], new_inst.get('pool_id'),
            prices.get('new_spot', 0), prices['on_demand'],
            timing.get('instance_launched_at'), timing.get('instance_launched_at')
        ))
        
        # Update total savings
        if savings_impact > 0:
            execute_query("""
                UPDATE clients
                SET total_savings = total_savings + %s
                WHERE id = %s
            """, (savings_impact * 24, request.client_id))  # Convert to daily savings
        
        create_notification(
            f"Instance switched: {new_inst['instance_id']} - Saved ${savings_impact:.4f}/hr",
            'info',
            request.client_id
        )
        
        log_system_event('switch_completed', 'info',
                        f"Switch from {old_inst['instance_id']} to {new_inst['instance_id']}",
                        request.client_id, agent_id, new_inst['instance_id'],
                        metadata={'savings_impact': float(savings_impact)})
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Switch report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/termination', methods=['POST'])
@require_client_token
def report_termination(agent_id: str):
    """Report instance termination"""
    data = request.json
    
    try:
        log_system_event('instance_terminated', 'warning',
                        data.get('reason', 'Unknown reason'),
                        request.client_id, agent_id,
                        metadata=data)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Termination report error: {e}")
        return jsonify({'error': str(e)}), 500

# Continuing central_server_v3.py...

@app.route('/api/agents/<agent_id>/decide', methods=['POST'])
@require_client_token
def get_decision(agent_id: str):
    """Get switching decision from decision engine"""
    data = request.json
    
    try:
        instance = data['instance']
        pricing = data['pricing']
        
        # Get agent config
        config_data = execute_query("""
            SELECT ac.*, a.enabled, a.auto_switch_enabled
            FROM agent_configs ac
            JOIN agents a ON a.id = ac.agent_id
            WHERE ac.agent_id = %s AND a.client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)
        
        if not config_data or not config_data['enabled']:
            return jsonify({
                'instance_id': instance['instance_id'],
                'risk_score': 0.0,
                'recommended_action': 'stay',
                'recommended_mode': instance['current_mode'],
                'recommended_pool_id': instance.get('current_pool_id'),
                'expected_savings_per_hour': 0.0,
                'allowed': False,
                'reason': 'Agent disabled'
            })
        
        # Get recent switches count
        recent_switches = execute_query("""
            SELECT COUNT(*) as count
            FROM switch_events
            WHERE agent_id = %s AND timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """, (agent_id,), fetch_one=True)
        
        # Get last switch time
        last_switch = execute_query("""
            SELECT timestamp FROM switch_events
            WHERE instance_id = %s OR new_instance_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (instance['instance_id'], instance['instance_id']), fetch_one=True)
        
        # Make decision
        decision = decision_engine_manager.make_decision(
            instance=instance,
            pricing=pricing,
            config_data=config_data,
            recent_switches_count=recent_switches['count'] if recent_switches else 0,
            last_switch_time=last_switch['timestamp'] if last_switch else None
        )
        
        # Store decision in database
        execute_query("""
            INSERT INTO risk_scores (
                client_id, instance_id, agent_id, risk_score, recommended_action,
                recommended_pool_id, recommended_mode, expected_savings_per_hour,
                allowed, reason, model_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.client_id, instance['instance_id'], agent_id,
            decision.get('risk_score'), decision.get('recommended_action'),
            decision.get('recommended_pool_id'), decision.get('recommended_mode'),
            decision.get('expected_savings_per_hour'), decision.get('allowed'),
            decision.get('reason'), decision_engine_manager.engine_version
        ))
        
        return jsonify(decision)
        
    except Exception as e:
        logger.error(f"Decision error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ==============================================================================
# CLIENT/ADMIN MANAGEMENT ENDPOINTS
# ==============================================================================

@app.route('/api/admin/clients/create', methods=['POST'])
def create_client():
    """Create a new client with auto-generated token"""
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Client name is required'}), 400
    
    client_name = data['name'].strip()
    
    if not client_name or len(client_name) > 255:
        return jsonify({'error': 'Invalid client name'}), 400
    
    try:
        # Check if exists
        existing = execute_query(
            "SELECT id FROM clients WHERE name = %s",
            (client_name,),
            fetch_one=True
        )
        
        if existing:
            return jsonify({'error': f'Client with name "{client_name}" already exists'}), 409
        
        client_id = generate_client_id()
        client_token = generate_client_token()
        
        execute_query("""
            INSERT INTO clients (id, name, status, client_token, created_at, total_savings)
            VALUES (%s, %s, 'active', %s, NOW(), 0.0000)
        """, (client_id, client_name, client_token))
        
        create_notification(f"New client created: {client_name}", 'info', client_id)
        log_system_event('client_created', 'info', f"Client {client_name} created",
                        client_id=client_id, metadata={'client_name': client_name})
        
        logger.info(f"✓ New client created: {client_name} ({client_id})")
        
        return jsonify({
            'success': True,
            'client': {
                'id': client_id,
                'name': client_name,
                'token': client_token,
                'status': 'active'
            }
        })
        
    except Exception as e:
        logger.error(f"Create client error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/clients/<client_id>', methods=['DELETE'])
def delete_client(client_id: str):
    """Delete a client and all associated data (cascades)"""
    try:
        client = execute_query(
            "SELECT id, name FROM clients WHERE id = %s",
            (client_id,),
            fetch_one=True
        )
        
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        client_name = client['name']
        
        execute_query("DELETE FROM clients WHERE id = %s", (client_id,))
        
        log_system_event('client_deleted', 'warning',
                        f"Client {client_name} ({client_id}) deleted permanently",
                        metadata={'deleted_client_id': client_id, 'deleted_client_name': client_name})
        
        logger.warning(f"⚠ Client deleted: {client_name} ({client_id})")
        
        return jsonify({
            'success': True,
            'message': f"Client '{client_name}' and all associated data have been deleted"
        })
        
    except Exception as e:
        logger.error(f"Delete client error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/clients/<client_id>/regenerate-token', methods=['POST'])
def regenerate_client_token(client_id: str):
    """Regenerate client token (invalidates old token)"""
    try:
        client = execute_query(
            "SELECT id, name FROM clients WHERE id = %s",
            (client_id,),
            fetch_one=True
        )
        
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        new_token = generate_client_token()
        
        execute_query(
            "UPDATE clients SET client_token = %s WHERE id = %s",
            (new_token, client_id)
        )
        
        create_notification(
            f"API token regenerated for client: {client['name']}. All agents need new token.",
            'warning',
            client_id
        )
        
        log_system_event('token_regenerated', 'warning',
                        f"Token regenerated for {client['name']}",
                        client_id=client_id)
        
        logger.warning(f"⚠ Token regenerated for client: {client['name']} ({client_id})")
        
        return jsonify({
            'success': True,
            'token': new_token,
            'message': 'Token regenerated successfully. Update all agents with the new token.'
        })
        
    except Exception as e:
        logger.error(f"Regenerate token error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/clients/<client_id>/token', methods=['GET'])
def get_client_token(client_id: str):
    """Get client token (for admin viewing)"""
    try:
        client = execute_query(
            "SELECT client_token, name FROM clients WHERE id = %s",
            (client_id,),
            fetch_one=True
        )
        
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        return jsonify({
            'token': client['client_token'],
            'client_name': client['name']
        })
        
    except Exception as e:
        logger.error(f"Get client token error: {e}")
        return jsonify({'error': str(e)}), 500

# ==============================================================================
# FRONTEND API ENDPOINTS
# ==============================================================================

@app.route('/api/admin/stats', methods=['GET'])
def get_global_stats():
    """Get global statistics"""
    try:
        stats = execute_query("""
            SELECT 
                COUNT(DISTINCT c.id) as total_accounts,
                COUNT(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) as agents_online,
                COUNT(DISTINCT a.id) as agents_total,
                COUNT(DISTINCT sp.id) as pools_covered,
                SUM(c.total_savings) as total_savings,
                COUNT(se.id) as total_switches,
                COUNT(CASE WHEN se.event_trigger = 'manual' THEN 1 END) as manual_switches,
                COUNT(CASE WHEN se.event_trigger = 'model' THEN 1 END) as model_switches
            FROM clients c
            LEFT JOIN agents a ON a.client_id = c.id
            LEFT JOIN spot_pools sp ON 1=1
            LEFT JOIN switch_events se ON se.client_id = c.id
        """, fetch_one=True)
        
        backend_health = 'Healthy'
        if not decision_engine_manager.models_loaded:
            backend_health = 'Decision Engine Not Loaded'
        
        return jsonify({
            'totalAccounts': stats['total_accounts'] or 0,
            'agentsOnline': stats['agents_online'] or 0,
            'agentsTotal': stats['agents_total'] or 0,
            'poolsCovered': stats['pools_covered'] or 0,
            'totalSavings': float(stats['total_savings'] or 0),
            'totalSwitches': stats['total_switches'] or 0,
            'manualSwitches': stats['manual_switches'] or 0,
            'modelSwitches': stats['model_switches'] or 0,
            'backendHealth': backend_health,
            'decisionEngineLoaded': decision_engine_manager.models_loaded,
            'mlModelsLoaded': decision_engine_manager.models_loaded
        })
        
    except Exception as e:
        logger.error(f"Get global stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/clients', methods=['GET'])
def get_all_clients():
    """Get all clients"""
    try:
        clients = execute_query("""
            SELECT 
                c.*,
                COUNT(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) as agents_online,
                COUNT(DISTINCT a.id) as agents_total,
                COUNT(DISTINCT CASE WHEN i.is_active = TRUE THEN i.id END) as instances
            FROM clients c
            LEFT JOIN agents a ON a.client_id = c.id
            LEFT JOIN instances i ON i.client_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """, fetch=True)
        
        return jsonify([{
            'id': client['id'],
            'name': client['name'],
            'status': client['status'],
            'agentsOnline': client['agents_online'] or 0,
            'agentsTotal': client['agents_total'] or 0,
            'instances': client['instances'] or 0,
            'totalSavings': float(client['total_savings'] or 0),
            'lastSync': client['last_sync_at'].isoformat() if client['last_sync_at'] else None
        } for client in clients or []])
        
    except Exception as e:
        logger.error(f"Get all clients error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>', methods=['GET'])
def get_client_details(client_id: str):
    """Get client overview"""
    try:
        client = execute_query("""
            SELECT 
                c.*,
                COUNT(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) as agents_online,
                COUNT(DISTINCT a.id) as agents_total,
                COUNT(DISTINCT CASE WHEN i.is_active = TRUE THEN i.id END) as instances
            FROM clients c
            LEFT JOIN agents a ON a.client_id = c.id
            LEFT JOIN instances i ON i.client_id = c.id
            WHERE c.id = %s
            GROUP BY c.id
        """, (client_id,), fetch_one=True)
        
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        return jsonify({
            'id': client['id'],
            'name': client['name'],
            'status': client['status'],
            'agentsOnline': client['agents_online'] or 0,
            'agentsTotal': client['agents_total'] or 0,
            'instances': client['instances'] or 0,
            'totalSavings': float(client['total_savings'] or 0),
            'lastSync': client['last_sync_at'].isoformat() if client['last_sync_at'] else None
        })
        
    except Exception as e:
        logger.error(f"Get client details error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/agents', methods=['GET'])
def get_client_agents(client_id: str):
    """Get all agents for client"""
    try:
        agents = execute_query("""
            SELECT a.*, ac.min_savings_percent, ac.risk_threshold,
                   ac.max_switches_per_week, ac.min_pool_duration_hours
            FROM agents a
            LEFT JOIN agent_configs ac ON ac.agent_id = a.id
            WHERE a.client_id = %s
            ORDER BY a.last_heartbeat DESC
        """, (client_id,), fetch=True)
        
        return jsonify([{
            'id': agent['id'],
            'status': agent['status'],
            'lastHeartbeat': agent['last_heartbeat'].isoformat() if agent['last_heartbeat'] else None,
            'instanceCount': agent['instance_count'] or 0,
            'enabled': agent['enabled'],
            'auto_switch_enabled': agent['auto_switch_enabled'],
            'auto_terminate_enabled': agent['auto_terminate_enabled']
        } for agent in agents or []])
        
    except Exception as e:
        logger.error(f"Get agents error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/agents/<agent_id>/toggle-enabled', methods=['POST'])
def toggle_agent(agent_id: str):
    """Enable/disable agent"""
    data = request.json
    
    try:
        execute_query("""
            UPDATE agents
            SET enabled = %s
            WHERE id = %s
        """, (data['enabled'], agent_id))
        
        log_system_event('agent_toggled', 'info',
                        f"Agent {agent_id} {'enabled' if data['enabled'] else 'disabled'}",
                        agent_id=agent_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Toggle agent error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/agents/<agent_id>/settings', methods=['POST'])
def update_agent_settings(agent_id: str):
    """Update agent settings"""
    data = request.json
    
    try:
        updates = []
        params = []
        
        if 'auto_switch_enabled' in data:
            updates.append("auto_switch_enabled = %s")
            params.append(data['auto_switch_enabled'])
        
        if 'auto_terminate_enabled' in data:
            updates.append("auto_terminate_enabled = %s")
            params.append(data['auto_terminate_enabled'])
        
        if updates:
            params.append(agent_id)
            execute_query(f"""
                UPDATE agents
                SET {', '.join(updates)}
                WHERE id = %s
            """, tuple(params))
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Update agent settings error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/agents/<agent_id>/config', methods=['POST'])
def update_agent_config(agent_id: str):
    """Update agent configuration parameters"""
    data = request.json
    
    try:
        updates = []
        params = []
        
        if 'min_savings_percent' in data:
            updates.append("min_savings_percent = %s")
            params.append(data['min_savings_percent'])
        
        if 'risk_threshold' in data:
            updates.append("risk_threshold = %s")
            params.append(data['risk_threshold'])
        
        if 'max_switches_per_week' in data:
            updates.append("max_switches_per_week = %s")
            params.append(data['max_switches_per_week'])
        
        if 'min_pool_duration_hours' in data:
            updates.append("min_pool_duration_hours = %s")
            params.append(data['min_pool_duration_hours'])
        
        if updates:
            params.append(agent_id)
            execute_query(f"""
                UPDATE agent_configs
                SET {', '.join(updates)}
                WHERE agent_id = %s
            """, tuple(params))
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Update agent config error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/instances', methods=['GET'])
def get_client_instances(client_id: str):
    """Get all instances for client with filtering"""
    status = request.args.get('status', 'all')
    mode = request.args.get('mode', 'all')
    search = request.args.get('search', '')
    
    try:
        query = "SELECT * FROM instances WHERE client_id = %s"
        params = [client_id]
        
        if status == 'active':
            query += " AND is_active = TRUE"
        elif status == 'terminated':
            query += " AND is_active = FALSE"
        
        if mode != 'all':
            query += " AND current_mode = %s"
            params.append(mode)
        
        if search:
            query += " AND (id LIKE %s OR instance_type LIKE %s)"
            params.extend([f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY created_at DESC"
        
        instances = execute_query(query, tuple(params), fetch=True)
        
        return jsonify([{
            'id': inst['id'],
            'type': inst['instance_type'],
            'az': inst['az'],
            'mode': inst['current_mode'],
            'poolId': inst['current_pool_id'] or 'n/a',
            'spotPrice': float(inst['spot_price'] or 0),
            'onDemandPrice': float(inst['ondemand_price'] or 0),
            'lastSwitch': inst['last_switch_at'].isoformat() if inst['last_switch_at'] else None
        } for inst in instances or []])
        
    except Exception as e:
        logger.error(f"Get instances error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/instances/<instance_id>/pricing', methods=['GET'])
def get_instance_pricing(instance_id: str):
    """Get pricing details for instance"""
    try:
        instance = execute_query("""
            SELECT instance_type, region, ondemand_price, current_pool_id
            FROM instances
            WHERE id = %s
        """, (instance_id,), fetch_one=True)
        
        if not instance:
            return jsonify({'error': 'Instance not found'}), 404
        
        pools = execute_query("""
            SELECT 
                sp.id as pool_id,
                sp.az,
                sps.price,
                sps.captured_at
            FROM spot_pools sp
            JOIN (
                SELECT pool_id, price, captured_at,
                       ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
                FROM spot_price_snapshots
            ) sps ON sps.pool_id = sp.id AND sps.rn = 1
            WHERE sp.instance_type = %s AND sp.region = %s
            ORDER BY sps.price ASC
        """, (instance['instance_type'], instance['region']), fetch=True)
        
        ondemand_price = float(instance['ondemand_price'] or 0)
        
        return jsonify({
            'onDemand': {
                'name': 'On-Demand',
                'price': ondemand_price
            },
            'pools': [{
                'id': pool['pool_id'],
                'price': float(pool['price']),
                'savings': ((ondemand_price - float(pool['price'])) / ondemand_price * 100) if ondemand_price > 0 else 0
            } for pool in pools or []]
        })
        
    except Exception as e:
        logger.error(f"Get instance pricing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/instances/<instance_id>/metrics', methods=['GET'])
def get_instance_metrics(instance_id: str):
    """Get comprehensive instance metrics"""
    try:
        metrics = execute_query("""
            SELECT 
                i.id,
                i.instance_type,
                i.current_mode,
                i.current_pool_id,
                i.spot_price,
                i.ondemand_price,
                i.baseline_ondemand_price,
                TIMESTAMPDIFF(HOUR, i.installed_at, NOW()) as uptime_hours,
                TIMESTAMPDIFF(HOUR, i.last_switch_at, NOW()) as hours_since_last_switch,
                (SELECT COUNT(*) FROM switch_events WHERE new_instance_id = i.id) as total_switches,
                (SELECT COUNT(*) FROM switch_events 
                 WHERE new_instance_id = i.id 
                 AND timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)) as switches_last_7_days,
                (SELECT COUNT(*) FROM switch_events 
                 WHERE new_instance_id = i.id 
                 AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as switches_last_30_days,
                (SELECT SUM(savings_impact * 24) FROM switch_events 
                 WHERE new_instance_id = i.id 
                 AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as savings_last_30_days,
                (SELECT SUM(savings_impact * 24) FROM switch_events 
                 WHERE new_instance_id = i.id) as total_savings
            FROM instances i
            WHERE i.id = %s
        """, (instance_id,), fetch_one=True)
        
        if not metrics:
            return jsonify({'error': 'Instance not found'}), 404
        
        return jsonify({
            'id': metrics['id'],
            'instanceType': metrics['instance_type'],
            'currentMode': metrics['current_mode'],
            'currentPoolId': metrics['current_pool_id'],
            'spotPrice': float(metrics['spot_price'] or 0),
            'onDemandPrice': float(metrics['ondemand_price'] or 0),
            'baselineOnDemandPrice': float(metrics['baseline_ondemand_price'] or 0),
            'uptimeHours': metrics['uptime_hours'] or 0,
            'hoursSinceLastSwitch': metrics['hours_since_last_switch'] or 0,
            'totalSwitches': metrics['total_switches'] or 0,
            'switchesLast7Days': metrics['switches_last_7_days'] or 0,
            'switchesLast30Days': metrics['switches_last_30_days'] or 0,
            'savingsLast30Days': float(metrics['savings_last_30_days'] or 0),
            'totalSavings': float(metrics['total_savings'] or 0)
        })
        
    except Exception as e:
        logger.error(f"Get instance metrics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/instances/<instance_id>/force-switch', methods=['POST'])
def force_instance_switch(instance_id: str):
    """Manually force instance switch"""
    data = request.json
    
    schema = ForceSwitchSchema()
    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    
    try:
        instance = execute_query("""
            SELECT agent_id, client_id FROM instances WHERE id = %s
        """, (instance_id,), fetch_one=True)
        
        if not instance or not instance['agent_id']:
            return jsonify({'error': 'Instance or agent not found'}), 404
        
        target_mode = validated_data['target']
        target_pool_id = validated_data.get('pool_id') if target_mode == 'pool' else None
        
        # Insert pending command with manual priority (75)
        execute_query("""
            INSERT INTO pending_switch_commands 
            (client_id, agent_id, instance_id, target_mode, target_pool_id, priority, created_at)
            VALUES (%s, %s, %s, %s, %s, 75, NOW())
        """, (instance['client_id'], instance['agent_id'], instance_id, target_mode, target_pool_id))
        
        create_notification(
            f"Manual switch queued for {instance_id}",
            'warning',
            instance['client_id']
        )
        
        log_system_event('manual_switch_requested', 'info',
                        f"Manual switch requested for {instance_id} to {target_mode}",
                        instance['client_id'], instance['agent_id'], instance_id,
                        metadata={'target': target_mode, 'pool_id': target_pool_id})
        
        return jsonify({
            'success': True,
            'message': 'Switch command queued. Agent will execute on next check.'
        })
        
    except Exception as e:
        logger.error(f"Force switch error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/savings', methods=['GET'])
def get_client_savings(client_id: str):
    """Get savings data for charts"""
    range_param = request.args.get('range', 'monthly')
    
    try:
        if range_param == 'monthly':
            savings = execute_query("""
                SELECT 
                    CONCAT(MONTHNAME(CONCAT(year, '-', month, '-01'))) as name,
                    baseline_cost as onDemandCost,
                    actual_cost as modelCost,
                    savings
                FROM client_savings_monthly
                WHERE client_id = %s
                ORDER BY year DESC, month DESC
                LIMIT 12
            """, (client_id,), fetch=True)
            
            savings = list(reversed(savings)) if savings else []
            
            return jsonify([{
                'name': s['name'],
                'savings': float(s['savings']),
                'onDemandCost': float(s['onDemandCost']),
                'modelCost': float(s['modelCost'])
            } for s in savings])
        
        return jsonify([])
        
    except Exception as e:
        logger.error(f"Get savings error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/switch-history', methods=['GET'])
def get_switch_history(client_id: str):
    """Get switch history"""
    instance_id = request.args.get('instance_id')
    
    try:
        query = """
            SELECT *
            FROM switch_events
            WHERE client_id = %s
        """
        params = [client_id]
        
        if instance_id:
            query += " AND (old_instance_id = %s OR new_instance_id = %s)"
            params.extend([instance_id, instance_id])
        
        query += " ORDER BY timestamp DESC LIMIT 100"
        
        history = execute_query(query, tuple(params), fetch=True)
        
        return jsonify([{
            'id': h['id'],
            'instanceId': h['new_instance_id'],
            'timestamp': h['timestamp'].isoformat(),
            'fromMode': h['from_mode'],
            'toMode': h['to_mode'],
            'fromPool': h['from_pool_id'] or 'n/a',
            'toPool': h['to_pool_id'] or 'n/a',
            'trigger': h['event_trigger'],
            'price': float(h['new_spot_price'] or h['on_demand_price'] or 0),
            'savingsImpact': float(h['savings_impact'] or 0)
        } for h in history or []])
        
    except Exception as e:
        logger.error(f"Get switch history error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/stats/charts', methods=['GET'])
def get_client_chart_data(client_id: str):
    """Get comprehensive chart data for client dashboard"""
    try:
        savings_trend = execute_query("""
            SELECT 
                MONTHNAME(CONCAT(year, '-', month, '-01')) as month,
                savings,
                baseline_cost,
                actual_cost
            FROM client_savings_monthly
            WHERE client_id = %s
            ORDER BY year DESC, month DESC
            LIMIT 12
        """, (client_id,), fetch=True)
        
        mode_dist = execute_query("""
            SELECT 
                current_mode,
                COUNT(*) as count
            FROM instances
            WHERE client_id = %s AND is_active = TRUE
            GROUP BY current_mode
        """, (client_id,), fetch=True)
        
        switch_freq = execute_query("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as switches
            FROM switch_events
            WHERE client_id = %s
              AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
        """, (client_id,), fetch=True)
        
        return jsonify({
            'savingsTrend': [{
                'month': s['month'],
                'savings': float(s['savings']),
                'baseline': float(s['baseline_cost']),
                'actual': float(s['actual_cost'])
            } for s in reversed(savings_trend or [])],
            'modeDistribution': [{
                'mode': m['current_mode'],
                'count': m['count']
            } for m in mode_dist or []],
            'switchFrequency': [{
                'date': s['date'].isoformat(),
                'switches': s['switches']
            } for s in switch_freq or []]
        })
    except Exception as e:
        logger.error(f"Get chart data error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """Get recent notifications"""
    client_id = request.args.get('client_id')
    limit = int(request.args.get('limit', 10))
    
    try:
        query = """
            SELECT id, message, severity, is_read, created_at
            FROM notifications
        """
        params = []
        
        if client_id:
            query += " WHERE client_id = %s OR client_id IS NULL"
            params.append(client_id)
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        notifications = execute_query(query, tuple(params), fetch=True)
        
        return jsonify([{
            'id': n['id'],
            'message': n['message'],
            'severity': n['severity'],
            'isRead': n['is_read'],
            'time': n['created_at'].isoformat()
        } for n in notifications or []])
    except Exception as e:
        logger.error(f"Get notifications error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/<int:notif_id>/mark-read', methods=['POST'])
def mark_notification_read(notif_id: int):
    """Mark notification as read"""
    try:
        execute_query("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE id = %s
        """, (notif_id,))
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Mark notification read error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    """Mark all notifications as read"""
    client_id = request.json.get('client_id') if request.json else None
    
    try:
        if client_id:
            execute_query("""
                UPDATE notifications
                SET is_read = TRUE
                WHERE client_id = %s OR client_id IS NULL
            """, (client_id,))
        else:
            execute_query("UPDATE notifications SET is_read = TRUE")
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Mark all read error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/activity', methods=['GET'])
def get_recent_activity():
    """Get recent system activity"""
    try:
        events = execute_query("""
            SELECT 
                event_type as type,
                message as text,
                created_at as time,
                severity
            FROM system_events
            WHERE severity IN ('info', 'warning')
            ORDER BY created_at DESC
            LIMIT 50
        """, fetch=True)
        
        activity = []
        for i, event in enumerate(events or []):
            event_type_map = {
                'switch_completed': 'switch',
                'agent_registered': 'agent',
                'manual_switch_requested': 'switch',
                'savings_computed': 'event',
                'client_created': 'event',
                'client_deleted': 'event',
                'token_regenerated': 'event'
            }
            
            activity.append({
                'id': i + 1,
                'type': event_type_map.get(event['type'], 'event'),
                'text': event['text'],
                'time': event['time'].isoformat() if event['time'] else 'unknown'
            })
        
        return jsonify(activity)
        
    except Exception as e:
        logger.error(f"Get activity error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/system-health', methods=['GET'])
def get_system_health():
    """Get system health information"""
    try:
        db_status = 'Connected'
        try:
            execute_query("SELECT 1", fetch_one=True)
        except:
            db_status = 'Disconnected'
        
        engine_status = 'Loaded' if decision_engine_manager.models_loaded else 'Not Loaded'
        
        pool_active = connection_pool._cnx_queue.qsize() if connection_pool else 0
        
        return jsonify({
            'apiStatus': 'Healthy',
            'database': db_status,
            'decisionEngine': engine_status,
            'connectionPool': f'{pool_active}/{config.DB_POOL_SIZE}',
            'timestamp': datetime.utcnow().isoformat(),
            'modelStatus': {
                'decisionEngineLoaded': decision_engine_manager.models_loaded,
                'mlModelsLoaded': decision_engine_manager.models_loaded,
                'engineType': decision_engine_manager.engine_type or 'None'
            }
        })
    except Exception as e:
        logger.error(f"System health check error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        execute_query("SELECT 1", fetch_one=True)
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'decision_engine_loaded': decision_engine_manager.models_loaded,
            'database': 'connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

# ==============================================================================
# BACKGROUND JOBS
# ==============================================================================

def compute_monthly_savings_job():
    """Compute monthly savings for all clients"""
    try:
        logger.info("Starting monthly savings computation...")
        
        clients = execute_query("SELECT id FROM clients WHERE status = 'active'", fetch=True)
        
        now = datetime.utcnow()
        year = now.year
        month = now.month
        
        for client in (clients or []):
            try:
                # Calculate baseline (on-demand) cost
                baseline = execute_query("""
                    SELECT SUM(baseline_ondemand_price * 24 * 30) as cost
                    FROM instances
                    WHERE client_id = %s AND is_active = TRUE
                """, (client['id'],), fetch_one=True)
                
                # Calculate actual cost from switch events
                actual = execute_query("""
                    SELECT 
                        SUM(CASE 
                            WHEN to_mode = 'spot' THEN new_spot_price * 24 * 30
                            ELSE on_demand_price * 24 * 30
                        END) as cost
                    FROM switch_events
                    WHERE client_id = %s 
                    AND YEAR(timestamp) = %s 
                    AND MONTH(timestamp) = %s
                """, (client['id'], year, month), fetch_one=True)
                
                baseline_cost = float(baseline['cost'] or 0)
                actual_cost = float(actual['cost'] or 0) if actual else baseline_cost
                savings = max(0, baseline_cost - actual_cost)
                
                # Store monthly savings
                execute_query("""
                    INSERT INTO client_savings_monthly 
                    (client_id, year, month, baseline_cost, actual_cost, savings)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        baseline_cost = VALUES(baseline_cost),
                        actual_cost = VALUES(actual_cost),
                        savings = VALUES(savings),
                        computed_at = NOW()
                """, (client['id'], year, month, baseline_cost, actual_cost, savings))
                
            except Exception as e:
                logger.error(f"Failed to compute savings for client {client['id']}: {e}")
        
        logger.info(f"✓ Monthly savings computed for {len(clients or [])} clients")
        log_system_event('savings_computed', 'info',
                        f"Computed monthly savings for {len(clients or [])} clients")
        
    except Exception as e:
        logger.error(f"Savings computation job failed: {e}")
        log_system_event('savings_computation_failed', 'error', str(e))

def cleanup_old_data_job():
    """Clean up old time-series data"""
    try:
        logger.info("Starting data cleanup...")
        
        execute_query("""
            DELETE FROM spot_price_snapshots 
            WHERE captured_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)
        
        execute_query("""
            DELETE FROM ondemand_price_snapshots 
            WHERE captured_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)
        
        execute_query("""
            DELETE FROM risk_scores 
            WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY)
        """)
        
        execute_query("""
            DELETE FROM decision_engine_log 
            WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)
        
        logger.info("✓ Old data cleaned up")
        log_system_event('data_cleanup', 'info', 'Cleaned up old time-series data')
        
    except Exception as e:
        logger.error(f"Data cleanup job failed: {e}")
        log_system_event('cleanup_failed', 'error', str(e))

def check_agent_health_job():
    """Check agent health and mark stale agents as offline"""
    try:
        timeout = config.AGENT_HEARTBEAT_TIMEOUT
        
        stale_agents = execute_query(f"""
            SELECT id, client_id FROM agents
            WHERE status = 'online' 
            AND last_heartbeat < DATE_SUB(NOW(), INTERVAL {timeout} SECOND)
        """, fetch=True)
        
        for agent in (stale_agents or []):
            execute_query("""
                UPDATE agents SET status = 'offline' WHERE id = %s
            """, (agent['id'],))
            
            create_notification(
                f"Agent {agent['id']} marked offline (heartbeat timeout)",
                'warning',
                agent['client_id']
            )
        
        if stale_agents:
            logger.info(f"Marked {len(stale_agents)} stale agents as offline")
        
    except Exception as e:
        logger.error(f"Agent health check job failed: {e}")

# ==============================================================================
# APPLICATION STARTUP
# ==============================================================================

def initialize_app():
    """Initialize application on startup"""
    logger.info("="*80)
    logger.info("AWS Spot Optimizer - Central Server v3.0")
    logger.info("="*80)
    
    # Initialize database
    init_db_pool()
    
    # Load decision engine
    decision_engine_manager.load_engine()
    
    # Start background jobs
    if config.ENABLE_BACKGROUND_JOBS:
        scheduler = BackgroundScheduler()
        
        # Monthly savings computation (daily at 1 AM)
        scheduler.add_job(compute_monthly_savings_job, 'cron', hour=1, minute=0)
        logger.info("✓ Scheduled monthly savings computation job")
        
        # Data cleanup (daily at 2 AM)
        scheduler.add_job(cleanup_old_data_job, 'cron', hour=2, minute=0)
        logger.info("✓ Scheduled data cleanup job")
        
        # Agent health check (every 5 minutes)
        scheduler.add_job(check_agent_health_job, 'interval', minutes=5)
        logger.info("✓ Scheduled agent health check job")
        
        scheduler.start()
        logger.info("✓ Background jobs started")
    
    logger.info("="*80)
    logger.info(f"Server initialized successfully")
    logger.info(f"Decision Engine: {decision_engine_manager.engine_type or 'None'}")
    logger.info(f"Models Loaded: {decision_engine_manager.models_loaded}")
    logger.info(f"Listening on {config.HOST}:{config.PORT}")
    logger.info("="*80)

# Initialize on import (for gunicorn)
initialize_app()

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG
    )
