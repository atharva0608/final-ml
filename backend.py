"""
AWS Spot Optimizer - Central Server Backend v4.1
==============================================================
Fully compatible with Agent v4.0 and MySQL Schema v5.1

Features:
- All v4.0 features preserved
- File upload for Decision Engine and ML Models
- Automatic model reloading after upload
- Enhanced system health endpoint
- Pluggable decision engine architecture
- Model registry and management
- Agent connection management
- Comprehensive logging and monitoring
- RESTful API for frontend and agents
- Replica configuration support
- Full dashboard endpoints
- Notification system
- Background jobs
==============================================================
"""

import os
import sys
import json
import secrets
import string
import logging
import importlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps
from decimal import Decimal

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.utils import secure_filename
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
    DECISION_ENGINE_DIR = Path(os.getenv('DECISION_ENGINE_DIR', './decision_engines'))

    # File Upload
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size
    ALLOWED_MODEL_EXTENSIONS = {'.pkl', '.joblib', '.h5', '.pb', '.pth', '.onnx', '.pt'}
    ALLOWED_ENGINE_EXTENSIONS = {'.py', '.pkl', '.joblib'}

    # Server
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Agent Communication
    AGENT_HEARTBEAT_TIMEOUT = int(os.getenv('AGENT_HEARTBEAT_TIMEOUT', 120))
    
    # Background Jobs
    ENABLE_BACKGROUND_JOBS = os.getenv('ENABLE_BACKGROUND_JOBS', 'True').lower() == 'true'

config = Config()

# ==============================================================================
# FLASK APP INITIALIZATION
# ==============================================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
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
            result = cursor.lastrowid if cursor.lastrowid else cursor.rowcount
            
        if commit and not fetch and not fetch_one:
            connection.commit()
            
        return result
    except Error as e:
        if connection:
            connection.rollback()
        logger.error(f"Query execution error: {e}")
        logger.error(f"Query: {query[:200]}")
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

def generate_uuid() -> str:
    """Generate UUID"""
    return str(uuid.uuid4())

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
            INSERT INTO notifications (id, message, severity, client_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (generate_uuid(), message, severity, client_id))
        logger.info(f"Notification created: {message[:50]}...")
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")

# ==============================================================================
# INPUT VALIDATION SCHEMAS
# ==============================================================================

class AgentRegistrationSchema(Schema):
    """Validation schema for agent registration"""
    client_token = fields.Str(required=True)
    hostname = fields.Str(required=False, validate=validate.Length(max=255))
    logical_agent_id = fields.Str(required=True, validate=validate.Length(max=255))
    instance_id = fields.Str(required=True)
    instance_type = fields.Str(required=True, validate=validate.Length(max=64))
    region = fields.Str(required=True)
    az = fields.Str(required=True)
    ami_id = fields.Str(required=False)
    mode = fields.Str(required=True, validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
    agent_version = fields.Str(required=False, validate=validate.Length(max=32))
    private_ip = fields.Str(required=False, validate=validate.Length(max=45))
    public_ip = fields.Str(required=False, validate=validate.Length(max=45))

class HeartbeatSchema(Schema):
    """Validation schema for heartbeat"""
    status = fields.Str(required=True, validate=validate.OneOf(['online', 'offline', 'disabled', 'switching', 'error']))
    instance_id = fields.Str(required=False)
    instance_type = fields.Str(required=False)
    mode = fields.Str(required=False)
    az = fields.Str(required=False)

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
    trigger = fields.Str(required=True)
    command_id = fields.Str(required=False)

class ForceSwitchSchema(Schema):
    """Validation schema for force switch"""
    target = fields.Str(required=True, validate=validate.OneOf(['ondemand', 'pool', 'spot']))
    pool_id = fields.Str(required=False, validate=validate.Length(max=128))
    new_instance_type = fields.Str(required=False, validate=validate.Length(max=50))

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
            "SELECT id, name FROM clients WHERE client_token = %s AND is_active = TRUE",
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
            logger.warning(f"Decision engine not loaded: {e}")
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
                    model_info.get('id', generate_uuid()),
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
        logical_agent_id = validated_data['logical_agent_id']
        
        # Check if agent exists
        existing = execute_query(
            "SELECT id FROM agents WHERE logical_agent_id = %s AND client_id = %s",
            (logical_agent_id, request.client_id),
            fetch_one=True
        )
        
        if existing:
            agent_id = existing['id']
            # Update existing agent
            execute_query("""
                UPDATE agents 
                SET status = 'online',
                    hostname = %s,
                    instance_id = %s,
                    instance_type = %s,
                    region = %s,
                    az = %s,
                    ami_id = %s,
                    current_mode = %s,
                    current_pool_id = %s,
                    agent_version = %s,
                    private_ip = %s,
                    public_ip = %s,
                    last_heartbeat_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (
                validated_data.get('hostname'),
                validated_data['instance_id'],
                validated_data['instance_type'],
                validated_data['region'],
                validated_data['az'],
                validated_data.get('ami_id'),
                validated_data['mode'],
                f"{validated_data['instance_type']}.{validated_data['az']}" if validated_data['mode'] == 'spot' else None,
                validated_data.get('agent_version'),
                validated_data.get('private_ip'),
                validated_data.get('public_ip'),
                agent_id
            ))
        else:
            # Insert new agent
            agent_id = generate_uuid()
            execute_query("""
                INSERT INTO agents 
                (id, client_id, logical_agent_id, hostname, instance_id, instance_type,
                 region, az, ami_id, current_mode, current_pool_id, agent_version,
                 private_ip, public_ip, status, last_heartbeat_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'online', NOW())
            """, (
                agent_id,
                request.client_id,
                logical_agent_id,
                validated_data.get('hostname'),
                validated_data['instance_id'],
                validated_data['instance_type'],
                validated_data['region'],
                validated_data['az'],
                validated_data.get('ami_id'),
                validated_data['mode'],
                f"{validated_data['instance_type']}.{validated_data['az']}" if validated_data['mode'] == 'spot' else None,
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
                f"New agent registered: {logical_agent_id}",
                'info',
                request.client_id
            )
        
        # Handle instance registration
        instance_exists = execute_query(
            "SELECT id FROM instances WHERE id = %s",
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
                validated_data.get('ami_id'),
                validated_data['mode'],
                baseline_price
            ))
        
        # Get agent config
        config_data = execute_query("""
            SELECT 
                a.enabled,
                a.auto_switch_enabled,
                a.auto_terminate_enabled,
                a.terminate_wait_seconds,
                a.replica_enabled,
                a.replica_count,
                COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
                COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
                COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
                COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
            FROM agents a
            LEFT JOIN agent_configs ac ON ac.agent_id = a.id
            WHERE a.id = %s
        """, (agent_id,), fetch_one=True)
        
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
                'terminate_wait_seconds': config_data['terminate_wait_seconds'],
                'replica_enabled': config_data['replica_enabled'],
                'replica_count': config_data['replica_count'],
                'min_savings_percent': float(config_data['min_savings_percent']),
                'risk_threshold': float(config_data['risk_threshold']),
                'max_switches_per_week': config_data['max_switches_per_week'],
                'min_pool_duration_hours': config_data['min_pool_duration_hours']
            }
        })
        
    except Exception as e:
        logger.error(f"Agent registration error: {e}", exc_info=True)
        log_system_event('agent_registration_failed', 'error', str(e), request.client_id)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/heartbeat', methods=['POST'])
@require_client_token
def agent_heartbeat(agent_id: str):
    """Update agent heartbeat"""
    data = request.json or {}
    
    try:
        new_status = data.get('status', 'online')
        
        # Get previous status
        prev = execute_query(
            "SELECT status FROM agents WHERE id = %s AND client_id = %s",
            (agent_id, request.client_id),
            fetch_one=True
        )
        
        if not prev:
            return jsonify({'error': 'Agent not found'}), 404
        
        # Update heartbeat
        execute_query("""
            UPDATE agents 
            SET status = %s, 
                last_heartbeat_at = NOW(),
                instance_id = COALESCE(%s, instance_id),
                instance_type = COALESCE(%s, instance_type),
                current_mode = COALESCE(%s, current_mode),
                az = COALESCE(%s, az)
            WHERE id = %s AND client_id = %s
        """, (
            new_status,
            data.get('instance_id'),
            data.get('instance_type'),
            data.get('mode'),
            data.get('az'),
            agent_id,
            request.client_id
        ))
        
        # Check for status change
        if prev['status'] != new_status:
            if new_status == 'offline':
                create_notification(f"Agent {agent_id} went offline", 'warning', request.client_id)
            elif new_status == 'online' and prev['status'] == 'offline':
                create_notification(f"Agent {agent_id} is back online", 'info', request.client_id)
        
        # Update client sync time
        execute_query(
            "UPDATE clients SET last_sync_at = NOW() WHERE id = %s",
            (request.client_id,)
        )
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/config', methods=['GET'])
@require_client_token
def get_agent_config(agent_id: str):
    """Get agent configuration"""
    try:
        config_data = execute_query("""
            SELECT 
                a.enabled,
                a.auto_switch_enabled,
                a.auto_terminate_enabled,
                a.terminate_wait_seconds,
                a.replica_enabled,
                a.replica_count,
                COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
                COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
                COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
                COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
            FROM agents a
            LEFT JOIN agent_configs ac ON ac.agent_id = a.id
            WHERE a.id = %s AND a.client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)
        
        if not config_data:
            return jsonify({'error': 'Agent not found'}), 404
        
        return jsonify({
            'enabled': config_data['enabled'],
            'auto_switch_enabled': config_data['auto_switch_enabled'],
            'auto_terminate_enabled': config_data['auto_terminate_enabled'],
            'terminate_wait_seconds': config_data['terminate_wait_seconds'],
            'replica_enabled': config_data['replica_enabled'],
            'replica_count': config_data['replica_count'],
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
        # Check both commands table and pending_switch_commands for compatibility
        commands = execute_query("""
            SELECT 
                id,
                instance_id,
                target_mode,
                target_pool_id,
                priority,
                terminate_wait_seconds,
                created_at
            FROM commands
            WHERE agent_id = %s AND status = 'pending'
            
            UNION ALL
            
            SELECT 
                CAST(id AS CHAR) as id,
                instance_id,
                target_mode,
                target_pool_id,
                priority,
                terminate_wait_seconds,
                created_at
            FROM pending_switch_commands
            WHERE agent_id = %s AND executed_at IS NULL
            
            ORDER BY priority DESC, created_at ASC
        """, (agent_id, agent_id), fetch=True)
        
        return jsonify([{
            'id': str(cmd['id']),
            'instance_id': cmd['instance_id'],
            'target_mode': cmd['target_mode'],
            'target_pool_id': cmd['target_pool_id'],
            'priority': cmd['priority'],
            'terminate_wait_seconds': cmd['terminate_wait_seconds'],
            'created_at': cmd['created_at'].isoformat() if cmd['created_at'] else None
        } for cmd in commands or []])
        
    except Exception as e:
        logger.error(f"Get pending commands error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/commands/<command_id>/executed', methods=['POST'])
@require_client_token
def mark_command_executed(agent_id: str, command_id: str):
    """Mark command as executed"""
    data = request.json or {}
    
    try:
        success = data.get('success', True)
        message = data.get('message', '')
        
        # Try to update in commands table first
        execute_query("""
            UPDATE commands
            SET status = %s,
                success = %s,
                message = %s,
                executed_at = NOW(),
                completed_at = NOW()
            WHERE id = %s AND agent_id = %s
        """, (
            'completed' if success else 'failed',
            success,
            message,
            command_id,
            agent_id
        ))
        
        # Also try pending_switch_commands for backwards compatibility
        if command_id.isdigit():
            execute_query("""
                UPDATE pending_switch_commands
                SET executed_at = NOW(),
                    execution_result = %s
                WHERE id = %s AND agent_id = %s
            """, (json.dumps(data), int(command_id), agent_id))
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Mark command executed error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/pricing-report', methods=['POST'])
@require_client_token
def pricing_report(agent_id: str):
    """Receive pricing data from agent"""
    data = request.json
    
    try:
        instance = data.get('instance', {})
        pricing = data.get('pricing', {})
        
        # Update instance pricing
        execute_query("""
            UPDATE instances
            SET ondemand_price = %s, spot_price = %s, updated_at = NOW()
            WHERE id = %s AND client_id = %s
        """, (
            pricing.get('on_demand_price'),
            pricing.get('current_spot_price'),
            instance.get('instance_id'),
            request.client_id
        ))
        
        # Store pricing report
        report_id = generate_uuid()
        execute_query("""
            INSERT INTO pricing_reports (
                id, agent_id, instance_id, instance_type, region, az,
                current_mode, current_pool_id, on_demand_price, current_spot_price,
                cheapest_pool_id, cheapest_pool_price, spot_pools, collected_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            report_id,
            agent_id,
            instance.get('instance_id'),
            instance.get('instance_type'),
            instance.get('region'),
            instance.get('az'),
            instance.get('mode'),
            instance.get('pool_id'),
            pricing.get('on_demand_price'),
            pricing.get('current_spot_price'),
            pricing.get('cheapest_pool', {}).get('pool_id') if pricing.get('cheapest_pool') else None,
            pricing.get('cheapest_pool', {}).get('price') if pricing.get('cheapest_pool') else None,
            json.dumps(pricing.get('spot_pools', [])),
            pricing.get('collected_at')
        ))
        
        # Store spot pool prices
        for pool in pricing.get('spot_pools', []):
            pool_id = pool['pool_id']
            
            # Ensure pool exists
            execute_query("""
                INSERT INTO spot_pools (id, instance_type, region, az)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE updated_at = NOW()
            """, (pool_id, instance.get('instance_type'), instance.get('region'), pool['az']))
            
            # Store price snapshot
            execute_query("""
                INSERT INTO spot_price_snapshots (pool_id, price)
                VALUES (%s, %s)
            """, (pool_id, pool['price']))
        
        # Store on-demand price snapshot
        if pricing.get('on_demand_price'):
            execute_query("""
                INSERT INTO ondemand_price_snapshots (region, instance_type, price)
                VALUES (%s, %s, %s)
            """, (instance.get('region'), instance.get('instance_type'), pricing['on_demand_price']))
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Pricing report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/switch-report', methods=['POST'])
@require_client_token
def switch_report(agent_id: str):
    """Record switch event"""
    data = request.json
    
    try:
        old_inst = data.get('old_instance', {})
        new_inst = data.get('new_instance', {})
        timing = data.get('timing', {})
        prices = data.get('pricing', {})
        
        # Calculate savings impact
        old_price = prices.get('old_spot') or prices.get('on_demand', 0)
        new_price = prices.get('new_spot') or prices.get('on_demand', 0)
        savings_impact = old_price - new_price
        
        # Insert switch record
        switch_id = generate_uuid()
        execute_query("""
            INSERT INTO switches (
                id, client_id, agent_id, command_id,
                old_instance_id, old_instance_type, old_region, old_az, old_mode, old_pool_id, old_ami_id,
                new_instance_id, new_instance_type, new_region, new_az, new_mode, new_pool_id, new_ami_id,
                on_demand_price, old_spot_price, new_spot_price, savings_impact,
                event_trigger, trigger_type, timing_data,
                initiated_at, ami_created_at, instance_launched_at, instance_ready_at, old_terminated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        """, (
            switch_id, request.client_id, agent_id, data.get('command_id'),
            old_inst.get('instance_id'), old_inst.get('instance_type'), old_inst.get('region'),
            old_inst.get('az'), old_inst.get('mode'), old_inst.get('pool_id'), old_inst.get('ami_id'),
            new_inst.get('instance_id'), new_inst.get('instance_type'), new_inst.get('region'),
            new_inst.get('az'), new_inst.get('mode'), new_inst.get('pool_id'), new_inst.get('ami_id'),
            prices.get('on_demand'), prices.get('old_spot'), prices.get('new_spot'), savings_impact,
            data.get('trigger'), data.get('trigger'), json.dumps(timing),
            timing.get('initiated_at'), timing.get('ami_created_at'),
            timing.get('instance_launched_at'), timing.get('instance_ready_at'),
            timing.get('old_terminated_at')
        ))
        
        # Deactivate old instance
        execute_query("""
            UPDATE instances
            SET is_active = FALSE, terminated_at = %s
            WHERE id = %s AND client_id = %s
        """, (timing.get('old_terminated_at'), old_inst.get('instance_id'), request.client_id))
        
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
            new_inst.get('instance_id'), request.client_id, agent_id,
            new_inst.get('instance_type'), new_inst.get('region'), new_inst.get('az'),
            new_inst.get('ami_id'), new_inst.get('mode'), new_inst.get('pool_id'),
            prices.get('new_spot', 0), prices.get('on_demand'),
            timing.get('instance_launched_at'), timing.get('instance_launched_at')
        ))
        
        # Update agent with new instance info
        execute_query("""
            UPDATE agents
            SET instance_id = %s,
                current_mode = %s,
                current_pool_id = %s,
                last_switch_at = NOW()
            WHERE id = %s
        """, (
            new_inst.get('instance_id'),
            new_inst.get('mode'),
            new_inst.get('pool_id'),
            agent_id
        ))
        
        # Update total savings
        if savings_impact > 0:
            execute_query("""
                UPDATE clients
                SET total_savings = total_savings + %s
                WHERE id = %s
            """, (savings_impact * 24, request.client_id))
        
        create_notification(
            f"Instance switched: {new_inst.get('instance_id')} - Saved ${savings_impact:.4f}/hr",
            'info',
            request.client_id
        )
        
        log_system_event('switch_completed', 'info',
                        f"Switch from {old_inst.get('instance_id')} to {new_inst.get('instance_id')}",
                        request.client_id, agent_id, new_inst.get('instance_id'),
                        metadata={'savings_impact': float(savings_impact)})
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Switch report error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/termination', methods=['POST'])
@require_client_token
def report_termination(agent_id: str):
    """Report instance termination"""
    data = request.json or {}
    
    try:
        reason = data.get('reason', 'Unknown')
        
        # Update agent status
        execute_query("""
            UPDATE agents
            SET status = 'offline',
                terminated_at = NOW()
            WHERE id = %s AND client_id = %s
        """, (agent_id, request.client_id))
        
        create_notification(
            f"Agent {agent_id} terminated: {reason}",
            'warning',
            request.client_id
        )
        
        log_system_event('instance_terminated', 'warning',
                        reason, request.client_id, agent_id, metadata=data)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Termination report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/replica-config', methods=['GET'])
@require_client_token
def get_replica_config(agent_id: str):
    """Get replica configuration for agent"""
    try:
        config_data = execute_query("""
            SELECT replica_enabled, replica_count
            FROM agents
            WHERE id = %s AND client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)
        
        if not config_data:
            return jsonify({'error': 'Agent not found'}), 404
        
        return jsonify({
            'enabled': config_data['replica_enabled'],
            'count': config_data['replica_count']
        })
        
    except Exception as e:
        logger.error(f"Get replica config error: {e}")
        return jsonify({'error': str(e)}), 500

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
            SELECT 
                a.enabled,
                a.auto_switch_enabled,
                COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
                COALESCE(ac.risk_threshold, 0.30) as risk_threshold,
                COALESCE(ac.max_switches_per_week, 10) as max_switches_per_week,
                COALESCE(ac.min_pool_duration_hours, 2) as min_pool_duration_hours
            FROM agents a
            LEFT JOIN agent_configs ac ON ac.agent_id = a.id
            WHERE a.id = %s AND a.client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)
        
        if not config_data or not config_data['enabled']:
            return jsonify({
                'instance_id': instance.get('instance_id'),
                'risk_score': 0.0,
                'recommended_action': 'stay',
                'recommended_mode': instance.get('current_mode'),
                'recommended_pool_id': instance.get('current_pool_id'),
                'expected_savings_per_hour': 0.0,
                'allowed': False,
                'reason': 'Agent disabled'
            })
        
        # Get recent switches count
        recent_switches = execute_query("""
            SELECT COUNT(*) as count
            FROM switches
            WHERE agent_id = %s AND initiated_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """, (agent_id,), fetch_one=True)
        
        # Get last switch time
        last_switch = execute_query("""
            SELECT initiated_at FROM switches
            WHERE agent_id = %s
            ORDER BY initiated_at DESC
            LIMIT 1
        """, (agent_id,), fetch_one=True)
        
        # Make decision
        decision = decision_engine_manager.make_decision(
            instance=instance,
            pricing=pricing,
            config_data=config_data,
            recent_switches_count=recent_switches['count'] if recent_switches else 0,
            last_switch_time=last_switch['initiated_at'] if last_switch else None
        )
        
        # Store decision in database
        execute_query("""
            INSERT INTO risk_scores (
                client_id, instance_id, agent_id, risk_score, recommended_action,
                recommended_pool_id, recommended_mode, expected_savings_per_hour,
                allowed, reason, model_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.client_id, instance.get('instance_id'), agent_id,
            decision.get('risk_score'), decision.get('recommended_action'),
            decision.get('recommended_pool_id'), decision.get('recommended_mode'),
            decision.get('expected_savings_per_hour'), decision.get('allowed'),
            decision.get('reason'), decision_engine_manager.engine_version
        ))

        # Log decision to history table for analytics
        try:
            execute_query("""
                INSERT INTO agent_decision_history (
                    agent_id, client_id, decision_type, recommended_action,
                    recommended_pool_id, risk_score, expected_savings,
                    current_mode, current_pool_id, current_price, decision_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                agent_id,
                request.client_id,
                decision.get('recommended_action', 'stay'),
                decision.get('recommended_action'),
                decision.get('recommended_pool_id'),
                decision.get('risk_score', 0),
                decision.get('expected_savings_per_hour', 0),
                instance.get('current_mode'),
                instance.get('current_pool_id'),
                pricing.get('current_spot_price', 0)
            ))
        except Exception as log_error:
            # Don't fail the request if logging fails
            logger.warning(f"Failed to log decision history: {log_error}")

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
    data = request.json or {}
    
    client_name = data.get('name', '').strip()
    if not client_name:
        return jsonify({'error': 'Client name is required'}), 400
    
    try:
        # Check if exists
        existing = execute_query(
            "SELECT id FROM clients WHERE name = %s",
            (client_name,),
            fetch_one=True
        )
        
        if existing:
            return jsonify({'error': f'Client "{client_name}" already exists'}), 409
        
        client_id = generate_uuid()
        client_token = generate_client_token()
        email = data.get('email', f"{client_name.lower().replace(' ', '_')}@example.com")
        
        execute_query("""
            INSERT INTO clients (id, name, email, client_token, is_active, total_savings)
            VALUES (%s, %s, %s, %s, TRUE, 0.0000)
        """, (client_id, client_name, email, client_token))
        
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
    """Delete a client and all associated data"""
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
    """Regenerate client token"""
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
    """Get client token"""
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
                COALESCE(SUM(c.total_savings), 0) as total_savings
            FROM clients c
            LEFT JOIN agents a ON a.client_id = c.id
        """, fetch_one=True)
        
        switch_stats = execute_query("""
            SELECT 
                COUNT(*) as total_switches,
                COUNT(CASE WHEN event_trigger = 'manual' THEN 1 END) as manual_switches,
                COUNT(CASE WHEN event_trigger = 'model' THEN 1 END) as model_switches
            FROM switches
        """, fetch_one=True)
        
        pool_count = execute_query(
            "SELECT COUNT(*) as count FROM spot_pools WHERE is_active = TRUE",
            fetch_one=True
        )
        
        backend_health = 'Healthy'
        if not decision_engine_manager.models_loaded:
            backend_health = 'Decision Engine Not Loaded'
        
        return jsonify({
            'totalAccounts': stats['total_accounts'] or 0,
            'agentsOnline': stats['agents_online'] or 0,
            'agentsTotal': stats['agents_total'] or 0,
            'poolsCovered': pool_count['count'] if pool_count else 0,
            'totalSavings': float(stats['total_savings'] or 0),
            'totalSwitches': switch_stats['total_switches'] if switch_stats else 0,
            'manualSwitches': switch_stats['manual_switches'] if switch_stats else 0,
            'modelSwitches': switch_stats['model_switches'] if switch_stats else 0,
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
            'status': 'active' if client['is_active'] else 'inactive',
            'agentsOnline': client['agents_online'] or 0,
            'agentsTotal': client['agents_total'] or 0,
            'instances': client['instances'] or 0,
            'totalSavings': float(client['total_savings'] or 0),
            'lastSync': client['last_sync_at'].isoformat() if client['last_sync_at'] else None
        } for client in clients or []])
        
    except Exception as e:
        logger.error(f"Get all clients error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/clients/growth', methods=['GET'])
def get_clients_growth():
    """Get client growth analytics over time"""
    try:
        days = request.args.get('days', 30, type=int)

        # Limit to reasonable range
        days = min(max(days, 1), 365)

        growth_data = execute_query("""
            SELECT
                snapshot_date,
                total_clients,
                new_clients_today,
                active_clients
            FROM clients_daily_snapshot
            WHERE snapshot_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY snapshot_date ASC
        """, (days,), fetch=True)

        return jsonify([{
            'date': g['snapshot_date'].isoformat() if g['snapshot_date'] else None,
            'total': g['total_clients'],
            'new': g['new_clients_today'],
            'active': g['active_clients']
        } for g in growth_data or []])

    except Exception as e:
        logger.error(f"Get clients growth error: {e}")
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
            'status': 'active' if client['is_active'] else 'inactive',
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
            ORDER BY a.last_heartbeat_at DESC
        """, (client_id,), fetch=True)
        
        return jsonify([{
            'id': agent['id'],
            'logicalAgentId': agent['logical_agent_id'],
            'instanceId': agent['instance_id'],
            'instanceType': agent['instance_type'],
            'region': agent['region'],
            'az': agent['az'],
            'currentMode': agent['current_mode'],
            'status': agent['status'],
            'lastHeartbeat': agent['last_heartbeat_at'].isoformat() if agent['last_heartbeat_at'] else None,
            'instanceCount': agent['instance_count'] or 0,
            'enabled': agent['enabled'],
            'autoSwitchEnabled': agent['auto_switch_enabled'],
            'autoTerminateEnabled': agent['auto_terminate_enabled'],
            'agentVersion': agent['agent_version']
        } for agent in agents or []])
        
    except Exception as e:
        logger.error(f"Get agents error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/agents/decisions', methods=['GET'])
def get_agents_decisions(client_id: str):
    """Get agent decision history with pricing health status"""
    try:
        # Get all active agents with last decision
        agents_data = execute_query("""
            SELECT
                a.id,
                a.logical_agent_id,
                a.status,
                a.current_mode,
                a.current_pool_id,

                -- Last decision (subquery)
                (SELECT decision_type FROM agent_decision_history adh
                 WHERE adh.agent_id = a.id
                 ORDER BY decision_time DESC LIMIT 1) as last_decision,

                (SELECT decision_time FROM agent_decision_history adh
                 WHERE adh.agent_id = a.id
                 ORDER BY decision_time DESC LIMIT 1) as last_decision_time

            FROM agents a
            WHERE a.client_id = %s AND a.status = 'online'
            ORDER BY a.logical_agent_id
        """, (client_id,), fetch=True)

        result = []
        for agent in (agents_data or []):
            # Get last 5 pricing reports for health check
            recent_reports = execute_query("""
                SELECT received_at, ondemand_price, current_spot_price
                FROM pricing_reports
                WHERE agent_id = %s
                ORDER BY received_at DESC
                LIMIT 5
            """, (agent['id'],), fetch=True)

            # Count recent reports (within last 10 minutes)
            recent_count = execute_query("""
                SELECT COUNT(*) as cnt
                FROM pricing_reports
                WHERE agent_id = %s
                  AND received_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
            """, (agent['id'],), fetch_one=True)
            recent_reports_count = recent_count['cnt'] if recent_count else 0

            # Health check: at least 5 reports in last 10 minutes
            is_healthy = recent_reports_count >= 5

            # Calculate time elapsed since last decision
            time_elapsed = None
            if agent.get('last_decision_time'):
                try:
                    delta = datetime.utcnow() - agent['last_decision_time']
                    minutes_ago = int(delta.total_seconds() / 60)
                    time_elapsed = {
                        'minutes': minutes_ago,
                        'formatted': f"{minutes_ago} minutes ago" if minutes_ago > 0 else "Just now"
                    }
                except Exception as e:
                    logger.warning(f"Error calculating time elapsed: {e}")

            result.append({
                'agentId': agent['id'],
                'agentName': agent['logical_agent_id'],
                'status': agent['status'],
                'lastDecision': {
                    'type': agent.get('last_decision'),
                    'time': agent['last_decision_time'].isoformat() if agent.get('last_decision_time') else None,
                    'elapsed': time_elapsed
                },
                'pricingHealth': {
                    'status': 'healthy' if is_healthy else 'unhealthy',
                    'recentReportsCount': recent_reports_count,
                    'recentReports': [{
                        'time': r['received_at'].isoformat() if r.get('received_at') else None,
                        'onDemandPrice': float(r['ondemand_price']) if r.get('ondemand_price') else 0,
                        'spotPrice': float(r['current_spot_price']) if r.get('current_spot_price') else 0
                    } for r in (recent_reports or [])]
                }
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"Get agents decisions error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/agents/<agent_id>/toggle-enabled', methods=['POST'])
def toggle_agent(agent_id: str):
    """Enable/disable agent"""
    data = request.json or {}
    
    try:
        execute_query("""
            UPDATE agents
            SET enabled = %s
            WHERE id = %s
        """, (data.get('enabled', True), agent_id))
        
        log_system_event('agent_toggled', 'info',
                        f"Agent {agent_id} {'enabled' if data.get('enabled') else 'disabled'}",
                        agent_id=agent_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Toggle agent error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/agents/<agent_id>/settings', methods=['POST'])
def update_agent_settings(agent_id: str):
    """Update agent settings"""
    data = request.json or {}
    
    try:
        updates = []
        params = []
        
        if 'auto_switch_enabled' in data:
            updates.append("auto_switch_enabled = %s")
            params.append(data['auto_switch_enabled'])
        
        if 'auto_terminate_enabled' in data:
            updates.append("auto_terminate_enabled = %s")
            params.append(data['auto_terminate_enabled'])
        
        if 'replica_enabled' in data:
            updates.append("replica_enabled = %s")
            params.append(data['replica_enabled'])
        
        if 'replica_count' in data:
            updates.append("replica_count = %s")
            params.append(data['replica_count'])
        
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
    """Update agent configuration - simplified to only termination timeout"""
    data = request.json or {}

    try:
        # Only accept terminate_wait_minutes (converted to seconds)
        if 'terminate_wait_minutes' in data:
            terminate_wait_seconds = int(data['terminate_wait_minutes']) * 60

            execute_query("""
                UPDATE agents
                SET terminate_wait_seconds = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (terminate_wait_seconds, agent_id))

            logger.info(f"Updated agent {agent_id} termination timeout to {terminate_wait_seconds}s")

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
            'region': inst['region'],
            'az': inst['az'],
            'mode': inst['current_mode'],
            'poolId': inst['current_pool_id'] or 'n/a',
            'spotPrice': float(inst['spot_price'] or 0),
            'onDemandPrice': float(inst['ondemand_price'] or 0),
            'isActive': inst['is_active'],
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
                'az': pool['az'],
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
                (SELECT COUNT(*) FROM switches WHERE new_instance_id = i.id) as total_switches,
                (SELECT COUNT(*) FROM switches 
                 WHERE new_instance_id = i.id 
                 AND initiated_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) as switches_last_7_days,
                (SELECT COUNT(*) FROM switches 
                 WHERE new_instance_id = i.id 
                 AND initiated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as switches_last_30_days,
                (SELECT SUM(savings_impact * 24) FROM switches 
                 WHERE new_instance_id = i.id 
                 AND initiated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as savings_last_30_days,
                (SELECT SUM(savings_impact * 24) FROM switches 
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

@app.route('/api/client/instances/<instance_id>/available-options', methods=['GET'])
def get_instance_available_options(instance_id: str):
    """Get available pools and instance types for switching"""
    try:
        # Get current instance information
        agent = execute_query("""
            SELECT instance_type, region, az FROM agents WHERE instance_id = %s
        """, (instance_id,), fetch_one=True)

        if not agent:
            return jsonify({'error': 'Instance not found'}), 404

        current_type = agent['instance_type']
        region = agent['region']

        # Get available pools for current instance type
        pools = execute_query("""
            SELECT
                sp.id as pool_id,
                sp.az,
                sp.instance_type,
                spr.price as current_price
            FROM spot_pools sp
            LEFT JOIN (
                SELECT
                    pool_id,
                    price,
                    ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
                FROM spot_price_snapshots
            ) spr ON spr.pool_id = sp.id AND spr.rn = 1
            WHERE sp.instance_type = %s
              AND sp.region = %s
              AND sp.is_active = TRUE
            ORDER BY spr.price ASC
        """, (current_type, region), fetch=True)

        # Get instance types in same family (e.g., t3.medium -> t3.*)
        base_family = current_type.split('.')[0] if current_type else ''
        instance_types = execute_query("""
            SELECT DISTINCT instance_type
            FROM spot_pools
            WHERE region = %s
              AND instance_type LIKE %s
              AND is_active = TRUE
            ORDER BY instance_type
        """, (region, f"{base_family}.%"), fetch=True) if base_family else []

        return jsonify({
            'currentType': current_type,
            'currentRegion': region,
            'currentAz': agent.get('az'),
            'availablePools': [{
                'id': p['pool_id'],
                'az': p['az'],
                'instanceType': p['instance_type'],
                'price': float(p['current_price']) if p.get('current_price') else None
            } for p in pools or []],
            'availableTypes': [t['instance_type'] for t in instance_types or []]
        })

    except Exception as e:
        logger.error(f"Get available options error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/instances/<instance_id>/force-switch', methods=['POST'])
def force_instance_switch(instance_id: str):
    """Manually force instance switch"""
    data = request.json or {}
    
    schema = ForceSwitchSchema()
    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    
    try:
        instance = execute_query("""
            SELECT agent_id, client_id FROM instances WHERE id = %s
        """, (instance_id,), fetch_one=True)
        
        if not instance:
            # Try to find agent by instance_id
            agent = execute_query("""
                SELECT id, client_id FROM agents WHERE instance_id = %s
            """, (instance_id,), fetch_one=True)
            
            if not agent:
                return jsonify({'error': 'Instance or agent not found'}), 404
            
            instance = {'agent_id': agent['id'], 'client_id': agent['client_id']}
        
        if not instance.get('agent_id'):
            return jsonify({'error': 'No agent assigned to instance'}), 404
        
        target_mode = validated_data['target']
        target_pool_id = validated_data.get('pool_id')
        new_instance_type = validated_data.get('new_instance_type')

        # Build metadata for logging
        metadata = {
            'target': target_mode,
            'pool_id': target_pool_id
        }
        if new_instance_type:
            metadata['new_instance_type'] = new_instance_type
            # Note: Instance type changes require agent-side support
            logger.info(f"Instance type change requested: {new_instance_type}")

        # Insert pending command with manual priority (75)
        command_id = generate_uuid()
        execute_query("""
            INSERT INTO commands
            (id, client_id, agent_id, instance_id, command_type, target_mode, target_pool_id, priority, status, created_by)
            VALUES (%s, %s, %s, %s, 'switch', %s, %s, 75, 'pending', 'manual')
        """, (
            command_id,
            instance['client_id'],
            instance['agent_id'],
            instance_id,
            target_mode if target_mode != 'pool' else 'spot',
            target_pool_id
        ))

        notification_msg = f"Manual switch queued for {instance_id}"
        if new_instance_type:
            notification_msg += f" (type: {new_instance_type})"

        create_notification(
            notification_msg,
            'warning',
            instance['client_id']
        )

        log_system_event('manual_switch_requested', 'info',
                        f"Manual switch requested for {instance_id} to {target_mode}",
                        instance['client_id'], instance['agent_id'], instance_id,
                        metadata=metadata)
        
        return jsonify({
            'success': True,
            'command_id': command_id,
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
                    MONTHNAME(CONCAT(year, '-', LPAD(month, 2, '0'), '-01')) as name,
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
                'savings': float(s['savings'] or 0),
                'onDemandCost': float(s['onDemandCost'] or 0),
                'modelCost': float(s['modelCost'] or 0)
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
            FROM switches
            WHERE client_id = %s
        """
        params = [client_id]
        
        if instance_id:
            query += " AND (old_instance_id = %s OR new_instance_id = %s)"
            params.extend([instance_id, instance_id])
        
        query += " ORDER BY initiated_at DESC LIMIT 100"
        
        history = execute_query(query, tuple(params), fetch=True)
        
        return jsonify([{
            'id': h['id'],
            'oldInstanceId': h['old_instance_id'],
            'newInstanceId': h['new_instance_id'],
            'timestamp': h['initiated_at'].isoformat() if h['initiated_at'] else None,
            'fromMode': h['old_mode'],
            'toMode': h['new_mode'],
            'fromPool': h['old_pool_id'] or 'n/a',
            'toPool': h['new_pool_id'] or 'n/a',
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
                MONTHNAME(CONCAT(year, '-', LPAD(month, 2, '0'), '-01')) as month,
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
                DATE(initiated_at) as date,
                COUNT(*) as switches
            FROM switches
            WHERE client_id = %s
              AND initiated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            GROUP BY DATE(initiated_at)
            ORDER BY date ASC
        """, (client_id,), fetch=True)
        
        return jsonify({
            'savingsTrend': [{
                'month': s['month'],
                'savings': float(s['savings'] or 0),
                'baseline': float(s['baseline_cost'] or 0),
                'actual': float(s['actual_cost'] or 0)
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

@app.route('/api/notifications/<notif_id>/mark-read', methods=['POST'])
def mark_notification_read(notif_id: str):
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
    data = request.json or {}
    client_id = data.get('client_id')
    
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

        # Count model files in MODEL_DIR
        model_files_count = 0
        try:
            if config.MODEL_DIR.exists():
                model_files_count = len([f for f in config.MODEL_DIR.glob('*') if f.is_file()])
        except Exception as e:
            logger.warning(f"Could not count model files: {e}")

        # Get active models from registry
        active_models = []
        try:
            models = execute_query("""
                SELECT model_name, version, is_active, created_at
                FROM model_registry
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 10
            """, fetch=True)
            active_models = [{
                'name': m['model_name'],
                'version': m['version'],
                'active': bool(m['is_active'])
            } for m in (models or [])]
        except Exception as e:
            logger.warning(f"Could not fetch models from registry: {e}")

        return jsonify({
            'apiStatus': 'Healthy',
            'database': db_status,
            'decisionEngine': engine_status,
            'connectionPool': f'{pool_active}/{config.DB_POOL_SIZE}',
            'timestamp': datetime.utcnow().isoformat(),
            'modelStatus': {
                'loaded': decision_engine_manager.models_loaded,
                'name': decision_engine_manager.engine_type or 'None',
                'version': decision_engine_manager.engine_version or 'N/A',
                'filesUploaded': model_files_count,
                'activeModels': active_models
            },
            'decisionEngineStatus': {
                'loaded': decision_engine_manager.models_loaded,
                'type': decision_engine_manager.engine_type or 'None',
                'version': decision_engine_manager.engine_version or 'N/A'
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
# FILE UPLOAD ENDPOINTS
# ==============================================================================

def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Check if file extension is allowed"""
    return Path(filename).suffix.lower() in allowed_extensions

@app.route('/api/admin/decision-engine/upload', methods=['POST'])
def upload_decision_engine():
    """Upload decision engine files"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files selected'}), 400

        uploaded_files = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)

                # Validate file extension
                if not allowed_file(filename, config.ALLOWED_ENGINE_EXTENSIONS):
                    return jsonify({
                        'error': f'File type not allowed: {filename}. Allowed types: {", ".join(config.ALLOWED_ENGINE_EXTENSIONS)}'
                    }), 400

                # Save file
                file_path = config.DECISION_ENGINE_DIR / filename
                file.save(str(file_path))
                uploaded_files.append(filename)
                logger.info(f"✓ Uploaded decision engine file: {filename}")

        # Reload decision engine
        logger.info("Reloading decision engine after file upload...")
        success = decision_engine_manager.load_engine()

        if success:
            log_system_event('decision_engine_updated', 'info',
                           f'Decision engine files uploaded and reloaded: {", ".join(uploaded_files)}')

            return jsonify({
                'success': True,
                'message': 'Decision engine files uploaded and reloaded successfully',
                'files': uploaded_files,
                'engine_status': {
                    'loaded': decision_engine_manager.models_loaded,
                    'type': decision_engine_manager.engine_type,
                    'version': decision_engine_manager.engine_version
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Files uploaded but failed to reload decision engine',
                'files': uploaded_files
            }), 500

    except Exception as e:
        logger.error(f"Decision engine upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/ml-models/upload', methods=['POST'])
def upload_ml_models():
    """Upload ML model files"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files selected'}), 400

        uploaded_files = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)

                # Validate file extension
                if not allowed_file(filename, config.ALLOWED_MODEL_EXTENSIONS):
                    return jsonify({
                        'error': f'File type not allowed: {filename}. Allowed types: {", ".join(config.ALLOWED_MODEL_EXTENSIONS)}'
                    }), 400

                # Save file
                file_path = config.MODEL_DIR / filename
                file.save(str(file_path))
                uploaded_files.append(filename)
                logger.info(f"✓ Uploaded ML model file: {filename}")

        # Reload decision engine to pick up new models
        logger.info("Reloading decision engine to load new ML models...")
        success = decision_engine_manager.load_engine()

        if success:
            # Get updated model count
            model_files_count = len([f for f in config.MODEL_DIR.glob('*') if f.is_file()])

            # Get active models from registry
            active_models = []
            try:
                models = execute_query("""
                    SELECT model_name, version, is_active
                    FROM model_registry
                    WHERE is_active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 10
                """, fetch=True)
                active_models = [{
                    'name': m['model_name'],
                    'version': m['version'],
                    'active': bool(m['is_active'])
                } for m in (models or [])]
            except Exception as e:
                logger.warning(f"Could not fetch models from registry: {e}")

            log_system_event('ml_models_updated', 'info',
                           f'ML model files uploaded and loaded: {", ".join(uploaded_files)}')

            return jsonify({
                'success': True,
                'message': 'ML model files uploaded and loaded successfully',
                'files': uploaded_files,
                'model_status': {
                    'loaded': decision_engine_manager.models_loaded,
                    'filesUploaded': model_files_count,
                    'activeModels': active_models
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Files uploaded but failed to reload models',
                'files': uploaded_files
            }), 500

    except Exception as e:
        logger.error(f"ML models upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ==============================================================================
# BACKGROUND JOBS
# ==============================================================================

def snapshot_clients_daily():
    """Take daily snapshot of client counts for growth analytics"""
    try:
        logger.info("Taking daily client snapshot...")

        # Get current counts
        today_count = execute_query(
            "SELECT COUNT(*) as cnt FROM clients WHERE is_active = TRUE",
            fetch_one=True
        )
        total_clients = today_count['cnt'] if today_count else 0

        # Get yesterday's count to calculate new clients
        yesterday_row = execute_query("""
            SELECT total_clients FROM clients_daily_snapshot
            ORDER BY snapshot_date DESC LIMIT 1
        """, fetch_one=True)
        yesterday_count = yesterday_row['total_clients'] if yesterday_row else 0

        new_clients_today = total_clients - yesterday_count if yesterday_count else total_clients

        # Insert today's snapshot
        execute_query("""
            INSERT INTO clients_daily_snapshot
            (snapshot_date, total_clients, new_clients_today, active_clients)
            VALUES (CURDATE(), %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_clients=%s,
                new_clients_today=%s,
                active_clients=%s
        """, (total_clients, new_clients_today, total_clients,
              total_clients, new_clients_today, total_clients))

        logger.info(f"✓ Daily snapshot: {total_clients} total, {new_clients_today} new")
    except Exception as e:
        logger.error(f"Daily snapshot error: {e}")

def compute_monthly_savings_job():
    """Compute monthly savings for all clients"""
    try:
        logger.info("Starting monthly savings computation...")
        
        clients = execute_query("SELECT id FROM clients WHERE is_active = TRUE", fetch=True)
        
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
                            WHEN new_mode = 'spot' THEN new_spot_price * 24 * 30
                            ELSE on_demand_price * 24 * 30
                        END) as cost
                    FROM switches
                    WHERE client_id = %s 
                    AND YEAR(initiated_at) = %s 
                    AND MONTH(initiated_at) = %s
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
            AND last_heartbeat_at < DATE_SUB(NOW(), INTERVAL {timeout} SECOND)
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
    logger.info("AWS Spot Optimizer - Central Server v4.1")
    logger.info("="*80)

    # Create necessary directories
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    config.DECISION_ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"✓ Ensured directories exist: {config.MODEL_DIR}, {config.DECISION_ENGINE_DIR}")

    # Initialize database
    init_db_pool()

    # Load decision engine
    decision_engine_manager.load_engine()
    
    # Start background jobs
    if config.ENABLE_BACKGROUND_JOBS:
        scheduler = BackgroundScheduler()

        # Daily client snapshot (daily at 12:05 AM)
        scheduler.add_job(snapshot_clients_daily, 'cron', hour=0, minute=5)
        logger.info("✓ Scheduled daily client snapshot job")

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
