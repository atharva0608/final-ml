"""
AWS Spot Optimizer - Central Server Backend v4.3
==============================================================
Fully compatible with Agent v4.0 and MySQL Schema v5.1

Features:
- All v4.0 features preserved
- File upload for Decision Engine and ML Models
- Automatic backend restart after upload (dev & production)
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

SWITCHING WORKFLOW ARCHITECTURE:
==============================================================
This system supports multiple switching workflows with different triggers:

1. NORMAL ML-BASED SWITCHING (Controlled by auto_switch_enabled)
   ---------------------------------------------------------------
   Endpoint: GET /api/agents/<agent_id>/switch-recommendation
   - Always returns ML-based recommendation (works even if auto_switch is OFF)
   - Shows users what the system suggests
   - Response includes 'will_auto_execute' flag based on auto_switch_enabled

   Endpoint: POST /api/agents/<agent_id>/issue-switch-command
   - CHECKS auto_switch_enabled before creating command
   - If auto_switch is OFF: Returns 403 error
   - If auto_switch is ON: Creates switch command in 'commands' table
   - Agent polls /api/agents/<agent_id>/pending-commands and executes

   Workflow:
   a) When auto_switch is ON:
      - ML model recommends switch → Command issued automatically → Agent executes
   b) When auto_switch is OFF:
      - ML model recommends switch → Shown as suggestion only → No action taken
      - User must manually switch via UI (uses manual override endpoint)

2. EMERGENCY SCENARIOS (ALWAYS BYPASS auto_switch and ML models)
   ---------------------------------------------------------------
   Endpoint: POST /api/agents/<agent_id>/create-emergency-replica
   - Triggered by AWS rebalance recommendation or termination notice
   - BYPASSES auto_replica_enabled setting (emergency override)
   - Works even if ML models are not loaded or broken
   - Creates replica immediately in safest available pool

   Endpoint: POST /api/agents/<agent_id>/termination-imminent
   - Handles 2-minute termination warning
   - BYPASSES all settings and ML models
   - Promotes existing replica to primary (if available)
   - Failover completes in <15 seconds typically
   - Works even if decision engine is offline

   Workflow:
   - AWS sends rebalance/termination notice → Agent calls emergency endpoint
   - Backend creates replica OR promotes existing replica
   - NO checks for auto_switch, auto_replica, or ML model state
   - This is a safety mechanism - ALWAYS executes

3. MANUAL REPLICA CREATION (User-controlled failover preparation)
   ---------------------------------------------------------------
   Endpoint: POST /api/agents/<agent_id>/replicas
   - User creates replica manually from UI
   - Replica stays active until manually promoted or deleted
   - Checks manual_replica_enabled setting

   Endpoint: POST /api/agents/<agent_id>/replicas/<replica_id>/promote
   - User manually promotes replica to primary
   - Used for planned maintenance or manual failover
   - Available in instance section UI

   Workflow:
   - User clicks "Create Replica" → Replica created and syncing
   - Replica stays ready (not auto-promoted)
   - User clicks "Switch to Replica" when ready → Manual promotion
   - If not used, can be deleted manually

4. MANUAL OVERRIDE SWITCHING (User-initiated, bypasses auto_switch check)
   ---------------------------------------------------------------
   (Can be implemented in future if needed - direct UI switch button)


KEY DIFFERENCES:
- Normal switching: Respects auto_switch_enabled, uses ML models
- Emergency: Ignores all settings, bypasses ML models, always executes
- Manual replica: User-controlled timing, requires manual promotion
- Manual override: User decision, bypasses auto_switch (future feature)

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
import signal
import subprocess
import threading
import time
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

# Database utilities are defined later in this file (lines 4524-4566)
# No need to import - functions are in same file after consolidation

# Configure logging FIRST (before using logger)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('central_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Replica coordinator is defined later in this file (line 4639)
# Will be initialized after Flask app is created (line 3680)
# Cannot import or initialize here because class is defined later
replica_coordinator = None

# ==============================================================================
# CONFIGURATION
# ==============================================================================

class Config:
    """Server configuration with environment variable support"""
    
    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'spotuser')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'SpotUser2024!')
    DB_NAME = os.getenv('DB_NAME', 'spot_optimizer')
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 50))  # Increased from 30 to 50 for better concurrency
    
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
# NOTE: Database functions (init_db_pool, get_db_connection, execute_query) are
# now imported from database_utils.py to enable sharing with replica_coordinator

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
    mode = fields.Str(required=False, missing='unknown', validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
    agent_version = fields.Str(required=False, validate=validate.Length(max=32))
    private_ip = fields.Str(required=False, validate=validate.Length(max=45))
    public_ip = fields.Str(required=False, validate=validate.Length(max=45))

class HeartbeatSchema(Schema):
    """Validation schema for heartbeat"""
    status = fields.Str(required=True, validate=validate.OneOf(['online', 'offline', 'disabled', 'switching', 'error', 'deleted']))
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
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '').strip()

        # Fallback to JSON body
        if not token:
            token = request.json.get('client_token') if request.json else None
            if token:
                token = token.strip()

        if not token:
            logger.warning(f"Missing client token - endpoint: {request.path}")
            return jsonify({'error': 'Missing client token'}), 401

        # Log token prefix for debugging (first 8 chars only)
        token_preview = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else token[:8]

        # Check if client exists and is active
        client = execute_query(
            "SELECT id, name, is_active FROM clients WHERE client_token = %s",
            (token,),
            fetch_one=True
        )

        if not client:
            logger.warning(f"Invalid client token attempt - token: {token_preview}, endpoint: {request.path}")
            log_system_event('auth_failed', 'warning',
                           f'Invalid client token attempt for endpoint {request.path}')
            return jsonify({'error': 'Invalid client token'}), 401

        if not client['is_active']:
            logger.warning(f"Inactive client attempted access - client_id: {client['id']}, endpoint: {request.path}")
            log_system_event('auth_failed', 'warning',
                           f'Inactive client {client["id"]} attempted access',
                           client['id'])
            return jsonify({'error': 'Client account is not active'}), 403

        # Token is valid and client is active
        request.client_id = client['id']
        request.client_name = client['name']
        logger.debug(f"Token validated - client: {client['name']}, endpoint: {request.path}")
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

    # Log registration attempt for debugging
    logger.info(f"Agent registration attempt from client {request.client_id}")
    logger.debug(f"Registration data: {data}")

    schema = AgentRegistrationSchema()
    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        logger.warning(f"Agent registration validation failed: {e.messages}")
        log_system_event('validation_error', 'warning',
                        f"Agent registration validation failed: {e.messages}",
                        request.client_id)
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        logical_agent_id = validated_data['logical_agent_id']

        # Log successful validation
        logger.info(f"Agent registration validated: logical_id={logical_agent_id}, instance_id={validated_data['instance_id']}, mode={validated_data['mode']}")
        
        # Check if agent exists
        existing = execute_query(
            "SELECT id FROM agents WHERE logical_agent_id = %s AND client_id = %s",
            (logical_agent_id, request.client_id),
            fetch_one=True
        )
        
        if existing:
            agent_id = existing['id']
            logger.info(f"Updating existing agent: agent_id={agent_id}, logical_id={logical_agent_id}")

            # Check if this instance is a zombie or terminated - if so, don't let it update the agent
            instance_status_check = execute_query("""
                SELECT instance_status, is_primary
                FROM instances
                WHERE id = %s
            """, (validated_data['instance_id'],), fetch_one=True)

            # If this is a zombie or terminated instance, or not primary, reject the registration update
            if instance_status_check:
                status = instance_status_check.get('instance_status')
                is_primary = instance_status_check.get('is_primary')

                if status in ('zombie', 'terminated') or not is_primary:
                    logger.warning(f"Rejecting registration from non-primary/zombie instance {validated_data['instance_id']} (status={status}, is_primary={is_primary})")
                    # Return success but don't update agent - zombie should not become primary again
                    return jsonify({
                        'agent_id': agent_id,
                        'client_id': request.client_id,
                        'message': 'Instance is not primary, registration ignored',
                        'config': {
                            'enabled': False,
                            'auto_switch_enabled': False,
                            'auto_terminate_enabled': False,
                            'terminate_wait_seconds': 0,
                            'replica_enabled': False,
                            'replica_count': 0,
                            'min_savings_percent': 0,
                            'risk_threshold': 0,
                            'max_switches_per_week': 0,
                            'min_pool_duration_hours': 0
                        }
                    })

            # Update existing agent (only if instance is primary or doesn't exist in instances table yet)
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
            logger.info(f"Creating new agent: agent_id={agent_id}, logical_id={logical_agent_id}")
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
                SELECT price FROM ondemand_prices
                WHERE region = %s AND instance_type = %s
                LIMIT 1
            """, (validated_data['region'], validated_data['instance_type']), fetch_one=True)

            if not latest_od_price:
                # Fallback to snapshots if ondemand_prices table is empty
                latest_od_price = execute_query("""
                    SELECT price FROM ondemand_price_snapshots
                    WHERE region = %s AND instance_type = %s
                    ORDER BY captured_at DESC
                    LIMIT 1
                """, (validated_data['region'], validated_data['instance_type']), fetch_one=True)

            baseline_price = latest_od_price['price'] if latest_od_price else 0.0416  # Default t3.medium price

            # Get spot price if in spot mode
            spot_price = 0
            if validated_data['mode'] == 'spot':
                pool_id = validated_data.get('pool_id', f"{validated_data['instance_type']}.{validated_data['az']}")
                latest_spot = execute_query("""
                    SELECT price FROM spot_price_snapshots
                    WHERE pool_id = %s
                    ORDER BY captured_at DESC
                    LIMIT 1
                """, (pool_id,), fetch_one=True)
                spot_price = latest_spot['price'] if latest_spot else baseline_price * 0.3  # Estimate 70% savings

            execute_query("""
                INSERT INTO instances
                (id, client_id, agent_id, instance_type, region, az, ami_id,
                 current_mode, current_pool_id, spot_price, ondemand_price, baseline_ondemand_price,
                 is_active, installed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
            """, (
                validated_data['instance_id'],
                request.client_id,
                agent_id,
                validated_data['instance_type'],
                validated_data['region'],
                validated_data['az'],
                validated_data.get('ami_id'),
                validated_data['mode'],
                validated_data.get('pool_id') if validated_data['mode'] == 'spot' else None,
                spot_price if validated_data['mode'] == 'spot' else 0,
                baseline_price,
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
                        f"Agent {logical_agent_id} registered successfully",
                        request.client_id, agent_id, validated_data['instance_id'])

        logger.info(f"✓ Agent registered successfully: agent_id={agent_id}, logical_id={logical_agent_id}, instance_id={validated_data['instance_id']}, mode={validated_data['mode']}")

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

        # Get previous status and current instance
        prev = execute_query(
            "SELECT status, instance_id FROM agents WHERE id = %s AND client_id = %s",
            (agent_id, request.client_id),
            fetch_one=True
        )

        if not prev:
            return jsonify({'error': 'Agent not found'}), 404

        # If instance_id is being updated, check if it's from a zombie/terminated instance
        new_instance_id = data.get('instance_id')
        if new_instance_id and new_instance_id != prev.get('instance_id'):
            # Check if the new instance is a zombie or terminated
            instance_check = execute_query("""
                SELECT instance_status, is_primary
                FROM instances
                WHERE id = %s
            """, (new_instance_id,), fetch_one=True)

            if instance_check:
                status = instance_check.get('instance_status')
                is_primary = instance_check.get('is_primary')

                if status in ('zombie', 'terminated') or not is_primary:
                    logger.warning(f"Rejecting heartbeat instance_id update from zombie/non-primary {new_instance_id}")
                    # Don't allow zombie instances to update the agent's instance_id
                    new_instance_id = None  # Prevent the update

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
            new_instance_id,
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
                a.manual_replica_enabled,
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
            'manual_replica_enabled': config_data['manual_replica_enabled'],
            'min_savings_percent': float(config_data['min_savings_percent']),
            'risk_threshold': float(config_data['risk_threshold']),
            'max_switches_per_week': config_data['max_switches_per_week'],
            'min_pool_duration_hours': config_data['min_pool_duration_hours']
        })
        
    except Exception as e:
        logger.error(f"Get config error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/instances-to-terminate', methods=['GET'])
@require_client_token
def get_instances_to_terminate(agent_id: str):
    """
    Get list of instances that should be terminated by the agent.

    Returns instances that are:
    1. Marked as 'zombie' and past their terminate_wait_seconds
    2. Marked as 'terminated' in replica_instances but not yet terminated in AWS

    The agent's Cleanup worker should poll this endpoint and terminate instances via AWS EC2 API.
    """
    try:
        # Get agent's auto_terminate setting and terminate_wait_seconds
        agent = execute_query("""
            SELECT auto_terminate_enabled, terminate_wait_seconds, region
            FROM agents
            WHERE id = %s AND client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)

        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        instances_to_terminate = []

        # Only proceed if auto_terminate is enabled
        if agent['auto_terminate_enabled']:
            terminate_wait_seconds = agent['terminate_wait_seconds'] or 300

            # Get zombie instances past their termination wait period
            zombie_instances = execute_query("""
                SELECT
                    i.id as instance_id,
                    i.instance_type,
                    i.az,
                    i.instance_status,
                    i.terminated_at,
                    TIMESTAMPDIFF(SECOND, i.updated_at, NOW()) as seconds_since_zombie
                FROM instances i
                WHERE i.instance_status = 'zombie'
                  AND i.is_active = FALSE
                  AND i.region = %s
                  AND TIMESTAMPDIFF(SECOND, i.updated_at, NOW()) >= %s
                  AND (i.termination_attempted_at IS NULL OR i.termination_attempted_at < DATE_SUB(NOW(), INTERVAL 5 MINUTE))
            """, (agent['region'], terminate_wait_seconds), fetch=True)

            for inst in zombie_instances or []:
                instances_to_terminate.append({
                    'instance_id': inst['instance_id'],
                    'instance_type': inst['instance_type'],
                    'az': inst['az'],
                    'reason': 'zombie_timeout',
                    'seconds_waiting': inst['seconds_since_zombie']
                })

            # Get replica instances marked as terminated but not yet terminated in AWS
            terminated_replicas = execute_query("""
                SELECT
                    ri.instance_id,
                    ri.instance_type,
                    ri.az,
                    ri.status,
                    TIMESTAMPDIFF(SECOND, ri.terminated_at, NOW()) as seconds_since_marked
                FROM replica_instances ri
                WHERE ri.agent_id = %s
                  AND ri.status = 'terminated'
                  AND ri.instance_id IS NOT NULL
                  AND ri.instance_id != ''
                  AND (ri.termination_attempted_at IS NULL OR ri.termination_attempted_at < DATE_SUB(NOW(), INTERVAL 5 MINUTE))
            """, (agent_id,), fetch=True)

            for rep in terminated_replicas or []:
                instances_to_terminate.append({
                    'instance_id': rep['instance_id'],
                    'instance_type': rep['instance_type'],
                    'az': rep['az'],
                    'reason': 'replica_terminated',
                    'seconds_since_marked': rep['seconds_since_marked']
                })

        logger.info(f"Agent {agent_id} fetched {len(instances_to_terminate)} instances to terminate")

        return jsonify({
            'instances': instances_to_terminate,
            'auto_terminate_enabled': agent['auto_terminate_enabled'],
            'terminate_wait_seconds': agent.get('terminate_wait_seconds', 300)
        })

    except Exception as e:
        logger.error(f"Get instances to terminate error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/termination-report', methods=['POST'])
@require_client_token
def receive_termination_report(agent_id: str):
    """
    Receive termination report from agent after terminating instances.

    Request body:
    {
        "instance_id": "i-1234567890abcdef0",
        "success": true/false,
        "error": "error message if failed",
        "terminated_at": "2025-11-25T12:00:00"
    }
    """
    try:
        data = request.json or {}
        instance_id = data.get('instance_id')
        success = data.get('success', False)
        error_message = data.get('error')
        terminated_at = data.get('terminated_at')

        if not instance_id:
            return jsonify({'error': 'instance_id required'}), 400

        if success:
            # Mark instance as actually terminated in AWS
            execute_query("""
                UPDATE instances
                SET
                    instance_status = 'terminated',
                    is_active = FALSE,
                    terminated_at = %s,
                    termination_attempted_at = NOW(),
                    termination_confirmed = TRUE
                WHERE id = %s
            """, (terminated_at or datetime.utcnow(), instance_id))

            # Also mark in replica_instances if it exists
            execute_query("""
                UPDATE replica_instances
                SET
                    status = 'terminated',
                    terminated_at = %s,
                    termination_attempted_at = NOW(),
                    termination_confirmed = TRUE
                WHERE instance_id = %s
            """, (terminated_at or datetime.utcnow(), instance_id))

            logger.info(f"✓ Instance {instance_id} confirmed terminated by agent {agent_id}")

            # Log system event
            execute_query("""
                INSERT INTO system_events (event_type, severity, agent_id, message, metadata)
                VALUES ('instance_terminated', 'info', %s, %s, %s)
            """, (agent_id,
                  f"Instance {instance_id} terminated in AWS",
                  json.dumps({'instance_id': instance_id, 'terminated_at': terminated_at})))
        else:
            # Mark termination attempt but note it failed
            execute_query("""
                UPDATE instances
                SET termination_attempted_at = NOW()
                WHERE id = %s
            """, (instance_id,))

            execute_query("""
                UPDATE replica_instances
                SET termination_attempted_at = NOW()
                WHERE instance_id = %s
            """, (instance_id,))

            logger.error(f"✗ Failed to terminate instance {instance_id}: {error_message}")

            # Log system event
            execute_query("""
                INSERT INTO system_events (event_type, severity, agent_id, message, metadata)
                VALUES ('instance_termination_failed', 'warning', %s, %s, %s)
            """, (agent_id,
                  f"Failed to terminate instance {instance_id}: {error_message}",
                  json.dumps({'instance_id': instance_id, 'error': error_message})))

        return jsonify({
            'success': True,
            'message': 'Termination report recorded'
        })

    except Exception as e:
        logger.error(f"Termination report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/pending-commands', methods=['GET'])
@require_client_token
def get_pending_commands(agent_id: str):
    """Get pending commands for agent (sorted by priority)"""
    try:
        # Check both commands table and pending_switch_commands for compatibility
        commands = execute_query("""
            SELECT
                CAST(id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as id,
                CAST(instance_id AS CHAR(64) CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as instance_id,
                CAST(target_mode AS CHAR(20) CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as target_mode,
                CAST(target_pool_id AS CHAR(128) CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as target_pool_id,
                priority,
                terminate_wait_seconds,
                created_at
            FROM commands
            WHERE agent_id = %s AND status = 'pending'

            UNION ALL

            SELECT
                CAST(id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as id,
                CAST(instance_id AS CHAR(64) CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as instance_id,
                CAST(target_mode AS CHAR(20) CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as target_mode,
                CAST(target_pool_id AS CHAR(128) CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci as target_pool_id,
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

        # Get agent's auto_terminate setting
        agent = execute_query("""
            SELECT auto_terminate_enabled FROM agents WHERE id = %s
        """, (agent_id,), fetch_one=True)

        auto_terminate_enabled = agent.get('auto_terminate_enabled', True) if agent else True

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

        # Handle old instance based on auto_terminate setting
        if auto_terminate_enabled and timing.get('old_terminated_at'):
            # Mark old instance as terminated
            execute_query("""
                UPDATE instances
                SET is_active = FALSE,
                    terminated_at = %s,
                    instance_status = 'terminated',
                    is_primary = FALSE
                WHERE id = %s AND client_id = %s
            """, (timing.get('old_terminated_at'), old_inst.get('instance_id'), request.client_id))
            logger.info(f"Old instance {old_inst.get('instance_id')} marked as terminated (auto_terminate=ON)")
        else:
            # Mark old instance as zombie (still running but not primary)
            execute_query("""
                UPDATE instances
                SET instance_status = 'zombie',
                    is_primary = FALSE,
                    is_active = FALSE
                WHERE id = %s AND client_id = %s
            """, (old_inst.get('instance_id'), request.client_id))
            logger.info(f"Old instance {old_inst.get('instance_id')} marked as zombie (auto_terminate=OFF)")

        # Register new instance as primary
        execute_query("""
            INSERT INTO instances (
                id, client_id, agent_id, instance_type, region, az, ami_id,
                current_mode, current_pool_id, spot_price, ondemand_price,
                is_active, instance_status, is_primary, installed_at, last_switch_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, 'running_primary', TRUE, %s, %s)
            ON DUPLICATE KEY UPDATE
                current_mode = VALUES(current_mode),
                current_pool_id = VALUES(current_pool_id),
                spot_price = VALUES(spot_price),
                is_active = TRUE,
                instance_status = 'running_primary',
                is_primary = TRUE,
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

@app.route('/api/agents/<agent_id>/cleanup-report', methods=['POST'])
@require_client_token
def receive_cleanup_report(agent_id: str):
    """Receive and log cleanup operation results from agents"""
    data = request.json or {}

    try:
        timestamp = data.get('timestamp')
        snapshots = data.get('snapshots', {})
        amis = data.get('amis', {})

        # Count totals
        deleted_snapshots = len(snapshots.get('deleted', []))
        deleted_amis = len(amis.get('deleted_amis', []))
        failed_snapshots = len(snapshots.get('failed', []))
        failed_amis = len(amis.get('failed', []))
        total_failed = failed_snapshots + failed_amis

        # Insert into cleanup_logs table
        execute_query("""
            INSERT INTO cleanup_logs (
                agent_id, client_id, cleanup_type,
                deleted_snapshots_count, deleted_amis_count, failed_count,
                details, cutoff_date, executed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            agent_id,
            request.client_id,
            'full',
            deleted_snapshots,
            deleted_amis,
            total_failed,
            json.dumps(data),
            snapshots.get('cutoff_date'),
            timestamp or datetime.utcnow()
        ))

        # Update agent's last_cleanup_at
        execute_query("""
            UPDATE agents
            SET last_cleanup_at = NOW()
            WHERE id = %s AND client_id = %s
        """, (agent_id, request.client_id))

        # Log system event
        log_system_event(
            'cleanup_completed',
            'info',
            f"Cleaned {deleted_snapshots} snapshots, {deleted_amis} AMIs. Failed: {total_failed}",
            request.client_id,
            agent_id,
            metadata=data
        )

        logger.info(f"Cleanup report received from agent {agent_id}: {deleted_snapshots} snapshots, {deleted_amis} AMIs deleted")

        return jsonify({
            'success': True,
            'message': 'Cleanup report recorded',
            'deleted_snapshots': deleted_snapshots,
            'deleted_amis': deleted_amis,
            'failed_count': total_failed
        })

    except Exception as e:
        logger.error(f"Cleanup report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/rebalance-recommendation', methods=['POST'])
@require_client_token
def handle_rebalance_recommendation(agent_id: str):
    """Handle EC2 rebalance recommendations with risk analysis"""
    data = request.json or {}

    try:
        instance_id = data.get('instance_id')
        detected_at = data.get('detected_at')

        # Get agent details
        agent = execute_query("""
            SELECT current_pool_id, instance_type, region, az, current_mode
            FROM agents
            WHERE id = %s AND client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)

        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        # Update agent rebalance timestamp
        execute_query("""
            UPDATE agents
            SET last_rebalance_recommendation_at = NOW()
            WHERE id = %s
        """, (agent_id,))

        # Calculate risk score for current pool
        # Simple risk calculation based on recent interruptions
        interruptions = execute_query("""
            SELECT COUNT(*) as count
            FROM spot_interruption_events
            WHERE pool_id = %s
              AND detected_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        """, (agent['current_pool_id'],), fetch_one=True)

        interruption_count = interruptions['count'] if interruptions else 0
        risk_score = min(interruption_count / 30.0, 1.0)  # Normalize to 0-1

        # Insert into termination_events table
        execute_query("""
            INSERT INTO termination_events (
                agent_id, instance_id, event_type,
                detected_at, status, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            agent_id,
            instance_id,
            'rebalance_recommendation',
            detected_at or datetime.utcnow(),
            'detected',
            json.dumps({'risk_score': risk_score, 'current_pool': agent['current_pool_id']})
        ))

        # Find alternative pools with lower risk
        alternative_pools = execute_query("""
            SELECT sp.id, sp.pool_name, sp.instance_type, sp.az,
                   COALESCE(COUNT(sie.id), 0) as interruption_count
            FROM spot_pools sp
            LEFT JOIN spot_interruption_events sie
                ON sp.id = sie.pool_id
                AND sie.detected_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            WHERE sp.instance_type = %s
              AND sp.region = %s
              AND sp.az != %s
              AND sp.is_active = TRUE
            GROUP BY sp.id
            ORDER BY interruption_count ASC
            LIMIT 1
        """, (agent['instance_type'], agent['region'], agent['az']), fetch=True)

        # Determine action based on risk
        if risk_score > 0.30 and alternative_pools:
            action = 'switch'
            target_pool = alternative_pools[0]
            reason = f"Current pool has elevated interruption risk ({risk_score:.2%})"
        else:
            action = 'monitor'
            target_pool = None
            reason = f"Risk is acceptable ({risk_score:.2%}), continuing to monitor"

        # Log system event
        log_system_event(
            'rebalance_recommendation',
            'warning',
            f"Rebalance recommendation for {instance_id}. Risk: {risk_score:.2%}. Action: {action}",
            request.client_id,
            agent_id,
            metadata={'risk_score': risk_score, 'action': action}
        )

        response = {
            'success': True,
            'action': action,
            'risk_score': risk_score,
            'reason': reason
        }

        if target_pool:
            response.update({
                'target_mode': 'spot',
                'target_pool_id': target_pool['id'],
                'target_pool_name': target_pool['pool_name']
            })

        return jsonify(response)

    except Exception as e:
        logger.error(f"Rebalance recommendation error: {e}")
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

@app.route('/api/agents/<agent_id>/switch-recommendation', methods=['GET'])
@require_client_token
def get_switch_recommendation(agent_id: str):
    """
    Get ML-based switch recommendation for an agent (ALWAYS returns suggestion).
    This endpoint provides recommendations regardless of auto_switch_enabled setting.
    Use this to show suggestions to users even when auto-switch is disabled.
    """
    try:
        # Get agent and instance details
        agent_data = execute_query("""
            SELECT
                a.id, a.hostname, a.enabled, a.auto_switch_enabled,
                a.current_mode, a.current_pool_id, a.instance_id,
                i.instance_type, i.region, i.az, i.spot_price, i.ondemand_price,
                sp.pool_name, sp.az as pool_az,
                COALESCE(ac.min_savings_percent, 15.00) as min_savings_percent,
                COALESCE(ac.risk_threshold, 0.30) as risk_threshold
            FROM agents a
            JOIN instances i ON a.instance_id = i.id
            LEFT JOIN spot_pools sp ON i.current_pool_id = sp.id
            LEFT JOIN agent_configs ac ON ac.agent_id = a.id
            WHERE a.id = %s AND a.client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)

        if not agent_data:
            return jsonify({'error': 'Agent not found'}), 404

        # Get recent pricing data
        pricing_data = execute_query("""
            SELECT pool_id, spot_price, time_bucket
            FROM pricing_snapshots_clean
            WHERE pool_id = %s
            ORDER BY time_bucket DESC
            LIMIT 10
        """, (agent_data['current_pool_id'],), fetch=True)

        # Get alternative pools
        alternative_pools = execute_query("""
            SELECT
                sp.id, sp.pool_name, sp.instance_type, sp.az,
                psc.spot_price, psc.time_bucket
            FROM spot_pools sp
            JOIN pricing_snapshots_clean psc ON sp.id = psc.pool_id
            WHERE sp.instance_type = %s
              AND sp.region = %s
              AND sp.id != %s
              AND psc.time_bucket >= NOW() - INTERVAL 5 MINUTE
            ORDER BY psc.spot_price ASC
            LIMIT 5
        """, (agent_data['instance_type'], agent_data['region'], agent_data['current_pool_id']), fetch=True)

        # Prepare data for decision engine
        instance_info = {
            'instance_id': agent_data['instance_id'],
            'instance_type': agent_data['instance_type'],
            'region': agent_data['region'],
            'current_mode': agent_data['current_mode'],
            'current_pool_id': agent_data['current_pool_id']
        }

        pricing_info = {
            'spot_price': float(agent_data['spot_price']) if agent_data['spot_price'] else 0,
            'ondemand_price': float(agent_data['ondemand_price']) if agent_data['ondemand_price'] else 0,
            'pool_id': agent_data['current_pool_id']
        }

        # Get recommendation from decision engine
        if decision_engine_manager.engine and decision_engine_manager.models_loaded:
            decision = decision_engine_manager.engine.make_decision(
                instance_info, pricing_info, {'alternative_pools': alternative_pools}
            )
        else:
            # Fallback: simple rule-based logic
            savings_percent = 0
            if agent_data['ondemand_price'] and agent_data['spot_price']:
                savings_percent = ((agent_data['ondemand_price'] - agent_data['spot_price']) / agent_data['ondemand_price']) * 100

            decision = {
                'decision_type': 'stay_spot' if agent_data['current_mode'] == 'spot' else 'stay_ondemand',
                'recommended_pool_id': agent_data['current_pool_id'],
                'risk_score': 0.3,
                'expected_savings': float(agent_data['ondemand_price'] - agent_data['spot_price']) if agent_data['ondemand_price'] and agent_data['spot_price'] else 0,
                'confidence': 0.6,
                'reason': f'Current configuration optimal ({savings_percent:.1f}% savings)'
            }

        # Add auto_switch status to response
        response = {
            **decision,
            'agent_id': agent_id,
            'auto_switch_enabled': agent_data['auto_switch_enabled'],
            'will_auto_execute': agent_data['auto_switch_enabled'] and decision.get('decision_type') not in ('stay_spot', 'stay_ondemand'),
            'current_pool': {
                'id': agent_data['current_pool_id'],
                'name': agent_data.get('pool_name'),
                'az': agent_data.get('pool_az')
            },
            'alternative_pools': [
                {
                    'id': p['id'],
                    'name': p['pool_name'],
                    'az': p['az'],
                    'spot_price': float(p['spot_price'])
                } for p in (alternative_pools or [])
            ]
        }

        logger.info(f"Switch recommendation for agent {agent_id}: {decision.get('decision_type')} (auto_switch={agent_data['auto_switch_enabled']})")

        return jsonify(response)

    except Exception as e:
        logger.error(f"Switch recommendation error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agents/<agent_id>/issue-switch-command', methods=['POST'])
@require_client_token
def issue_switch_command(agent_id: str):
    """
    Issue a switch command to an agent (CHECKS auto_switch_enabled).
    If auto_switch is disabled, returns error. If enabled, creates switch command.

    Request body:
    {
        "target_mode": "spot" | "ondemand",
        "target_pool_id": 123,  # required for spot mode
        "reason": "ML recommendation",
        "priority": 5  # 1-10, default 5
    }
    """
    try:
        data = request.json or {}

        # Get agent configuration including terminate settings
        agent = execute_query("""
            SELECT id, hostname, auto_switch_enabled, auto_terminate_enabled,
                   terminate_wait_seconds, enabled, instance_id, current_mode, current_pool_id
            FROM agents
            WHERE id = %s AND client_id = %s
        """, (agent_id, request.client_id), fetch_one=True)

        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        if not agent['enabled']:
            return jsonify({
                'error': 'Agent is disabled',
                'hint': 'Enable the agent first'
            }), 400

        # CHECK AUTO_SWITCH_ENABLED - This is the key check
        if not agent['auto_switch_enabled']:
            return jsonify({
                'error': 'Auto-switch is disabled for this agent',
                'hint': 'Enable auto_switch_enabled in agent settings, or use manual switch from UI',
                'auto_switch_enabled': False
            }), 403

        # Validate request
        target_mode = data.get('target_mode')
        if target_mode not in ('spot', 'ondemand'):
            return jsonify({'error': 'Invalid target_mode'}), 400

        target_pool_id = data.get('target_pool_id')
        if target_mode == 'spot' and not target_pool_id:
            return jsonify({'error': 'target_pool_id required for spot mode'}), 400

        # Don't create redundant command if already in target state
        if agent['current_mode'] == target_mode and (target_mode != 'spot' or agent['current_pool_id'] == target_pool_id):
            return jsonify({
                'success': False,
                'message': 'Agent already in target state',
                'current_mode': agent['current_mode'],
                'current_pool_id': agent['current_pool_id']
            }), 200

        # Determine terminate_wait_seconds based on auto_terminate setting
        # If auto_terminate is disabled, set to 0 to signal agent NOT to terminate old instance
        if agent['auto_terminate_enabled']:
            terminate_wait = agent['terminate_wait_seconds'] or 300
        else:
            terminate_wait = 0  # Signal: DO NOT terminate old instance

        # Create switch command
        command_id = generate_uuid()
        execute_query("""
            INSERT INTO commands (
                id, agent_id, client_id, instance_id,
                target_mode, target_pool_id, priority,
                terminate_wait_seconds, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
        """, (
            command_id,
            agent_id,
            request.client_id,
            agent['instance_id'],
            target_mode,
            target_pool_id,
            data.get('priority', 5),
            terminate_wait
        ))

        logger.info(f"✓ Switch command issued for agent {agent_id}: {target_mode} (pool: {target_pool_id}), auto_terminate={agent['auto_terminate_enabled']}, terminate_wait={terminate_wait}s")

        create_notification(
            f"Switch command issued to {agent.get('hostname', agent_id)}: {target_mode}",
            'info',
            request.client_id
        )

        return jsonify({
            'success': True,
            'command_id': command_id,
            'agent_id': agent_id,
            'target_mode': target_mode,
            'target_pool_id': target_pool_id,
            'reason': data.get('reason', 'Manual command'),
            'message': 'Switch command queued. Agent will execute on next heartbeat.',
            'auto_switch_enabled': True
        }), 201

    except Exception as e:
        logger.error(f"Issue switch command error: {e}", exc_info=True)
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
            INSERT INTO clients (id, name, email, client_token, is_active, status, total_savings)
            VALUES (%s, %s, %s, %s, TRUE, 'active', 0.0000)
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

@app.route('/api/admin/instances', methods=['GET'])
def get_all_instances_global():
    """Get all instances across all clients (global view)"""
    try:
        # Get filters from query params
        status = request.args.get('status')  # 'active', 'terminated'
        mode = request.args.get('mode')  # 'spot', 'on-demand'
        region = request.args.get('region')

        query = """
            SELECT
                i.*,
                c.name as client_name,
                c.id as client_id,
                a.logical_agent_id,
                a.status as agent_status
            FROM instances i
            LEFT JOIN clients c ON i.client_id = c.id
            LEFT JOIN agents a ON i.id = a.instance_id
            WHERE 1=1
        """
        params = []

        # Filter by instance_status for proper active/terminated separation
        if status:
            if status == 'active':
                # Active space: primary + replica instances only
                query += " AND i.instance_status IN ('running_primary', 'running_replica')"
            elif status == 'terminated':
                # Terminated space: zombie + terminated instances only
                query += " AND i.instance_status IN ('zombie', 'terminated')"

        if mode:
            query += " AND i.current_mode = %s"
            params.append(mode)

        if region:
            query += " AND i.region = %s"
            params.append(region)

        query += " ORDER BY i.created_at DESC LIMIT 500"

        instances = execute_query(query, tuple(params), fetch=True)

        result = [{
            'id': inst['id'],
            'instanceId': inst['id'],  # id IS the instance_id
            'clientId': inst['client_id'],
            'clientName': inst['client_name'],
            'agentId': inst['agent_id'],
            'region': inst['region'],
            'az': inst['az'],
            'instanceType': inst['instance_type'],
            'currentMode': inst['current_mode'],
            'currentPoolId': inst['current_pool_id'],
            'spotPrice': float(inst['spot_price']) if inst['spot_price'] else None,
            'ondemandPrice': float(inst['ondemand_price']) if inst['ondemand_price'] else None,
            'isActive': bool(inst['is_active']),
            'installedAt': inst['installed_at'].isoformat() if inst['installed_at'] else None,
            'createdAt': inst['created_at'].isoformat() if inst['created_at'] else None,
            'logicalAgentId': inst['logical_agent_id'],
            'agentStatus': inst['agent_status']
        } for inst in (instances or [])]

        return jsonify({
            'instances': result,
            'total': len(result),
            'filters': {
                'status': status,
                'mode': mode,
                'region': region
            }
        })

    except Exception as e:
        logger.error(f"Get all instances error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/agents', methods=['GET'])
def get_all_agents_global():
    """Get all agents across all clients (global view)"""
    try:
        # Get filters from query params
        status = request.args.get('status')  # 'online', 'offline'

        query = """
            SELECT
                a.*,
                c.name as client_name,
                c.id as client_id,
                i.instance_type,
                i.region,
                i.az,
                i.current_mode
            FROM agents a
            LEFT JOIN clients c ON a.client_id = c.id
            LEFT JOIN instances i ON a.instance_id = i.id
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND a.status = %s"
            params.append(status)

        query += " ORDER BY a.last_heartbeat_at DESC LIMIT 500"

        agents = execute_query(query, tuple(params), fetch=True)

        result = [{
            'id': agent['id'],
            'logicalAgentId': agent['logical_agent_id'],
            'hostname': agent['hostname'],
            'clientId': agent['client_id'],
            'clientName': agent['client_name'],
            'instanceId': agent['instance_id'],
            'instanceType': agent['instance_type'],
            'region': agent['region'],
            'az': agent['az'],
            'currentMode': agent['current_mode'],
            'currentPoolId': agent['current_pool_id'],
            'status': agent['status'],
            'enabled': bool(agent['enabled']),
            'autoSwitchEnabled': bool(agent['auto_switch_enabled']),
            'version': agent['agent_version'],
            'lastHeartbeatAt': agent['last_heartbeat_at'].isoformat() if agent['last_heartbeat_at'] else None,
            'createdAt': agent['created_at'].isoformat() if agent['created_at'] else None
        } for agent in (agents or [])]

        return jsonify({
            'agents': result,
            'total': len(result),
            'filters': {
                'status': status
            }
        })

    except Exception as e:
        logger.error(f"Get all agents error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/validate', methods=['GET'])
def validate_client_token():
    """Validate client token for frontend authentication"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'valid': False, 'error': 'Missing or invalid Authorization header'}), 401

        token = auth_header.replace('Bearer ', '').strip()

        if not token:
            return jsonify({'valid': False, 'error': 'Token is empty'}), 401

        # Validate token against database
        client = execute_query("""
            SELECT id, name, email, is_active, status
            FROM clients
            WHERE client_token = %s
        """, (token,), fetch_one=True)

        if not client:
            return jsonify({'valid': False, 'error': 'Invalid token'}), 401

        if not client['is_active'] or client['status'] != 'active':
            return jsonify({'valid': False, 'error': 'Client account is not active'}), 403

        # Log validation attempt
        logger.info(f"Client token validated successfully for client {client['id']}")

        return jsonify({
            'valid': True,
            'client_id': client['id'],
            'name': client['name'],
            'email': client['email']
        })

    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return jsonify({'valid': False, 'error': 'Internal server error'}), 500

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
    """Get all active agents for client (excludes deleted agents)"""
    try:
        # Exclude deleted agents by default
        agents = execute_query("""
            SELECT a.*, ac.min_savings_percent, ac.risk_threshold,
                   ac.max_switches_per_week, ac.min_pool_duration_hours
            FROM agents a
            LEFT JOIN agent_configs ac ON ac.agent_id = a.id
            WHERE a.client_id = %s AND a.status != 'deleted'
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
            'manualReplicaEnabled': agent['manual_replica_enabled'],
            'autoTerminateEnabled': agent['auto_terminate_enabled'],
            'terminateWaitMinutes': (agent['terminate_wait_seconds'] or 1800) // 60,
            'agentVersion': agent['agent_version']
        } for agent in agents or []])
        
    except Exception as e:
        logger.error(f"Get agents error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/agents/decisions', methods=['GET'])
def get_agents_decisions(client_id: str):
    """Get agent decision history with comprehensive health status"""
    try:
        # Get all agents (including offline ones for complete view)
        agents_data = execute_query("""
            SELECT
                a.id,
                a.logical_agent_id,
                a.status,
                a.current_mode,
                a.current_pool_id,
                a.last_heartbeat_at,

                -- Last decision (subquery)
                (SELECT decision_type FROM agent_decision_history adh
                 WHERE adh.agent_id = a.id
                 ORDER BY decision_time DESC LIMIT 1) as last_decision,

                (SELECT decision_time FROM agent_decision_history adh
                 WHERE adh.agent_id = a.id
                 ORDER BY decision_time DESC LIMIT 1) as last_decision_time

            FROM agents a
            WHERE a.client_id = %s
            ORDER BY
                CASE WHEN a.status = 'online' THEN 0 ELSE 1 END,
                a.logical_agent_id
        """, (client_id,), fetch=True)

        result = []
        for agent in (agents_data or []):
            # Get last 5 decision history entries
            decision_history = execute_query("""
                SELECT
                    decision_type,
                    recommended_action,
                    risk_score,
                    expected_savings,
                    current_mode,
                    decision_time
                FROM agent_decision_history
                WHERE agent_id = %s
                ORDER BY decision_time DESC
                LIMIT 5
            """, (agent['id'],), fetch=True)

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

            # Get last 5 system events for this agent
            recent_events = execute_query("""
                SELECT
                    event_type,
                    severity,
                    message,
                    created_at
                FROM system_events
                WHERE agent_id = %s
                ORDER BY created_at DESC
                LIMIT 5
            """, (agent['id'],), fetch=True)

            # Enhanced health check
            heartbeat_healthy = False
            if agent.get('last_heartbeat_at'):
                try:
                    heartbeat_delta = datetime.utcnow() - agent['last_heartbeat_at']
                    heartbeat_minutes = int(heartbeat_delta.total_seconds() / 60)
                    heartbeat_healthy = heartbeat_minutes <= 5  # Healthy if heartbeat within 5 minutes
                except Exception:
                    heartbeat_healthy = False

            # Health criteria: heartbeat recent AND has recent activity
            activity_healthy = recent_reports_count >= 1 or len(decision_history or []) > 0
            is_healthy = heartbeat_healthy and activity_healthy and agent['status'] == 'online'

            # Calculate time elapsed since last decision
            time_elapsed = None
            if agent.get('last_decision_time'):
                try:
                    delta = datetime.utcnow() - agent['last_decision_time']
                    minutes_ago = int(delta.total_seconds() / 60)
                    if minutes_ago < 1:
                        time_elapsed = {"minutes": 0, "formatted": "Just now"}
                    elif minutes_ago < 60:
                        time_elapsed = {"minutes": minutes_ago, "formatted": f"{minutes_ago} min ago"}
                    else:
                        hours = minutes_ago // 60
                        time_elapsed = {"minutes": minutes_ago, "formatted": f"{hours}h ago"}
                except Exception as e:
                    logger.warning(f"Error calculating time elapsed: {e}")

            # Calculate heartbeat age
            heartbeat_elapsed = None
            if agent.get('last_heartbeat_at'):
                try:
                    delta = datetime.utcnow() - agent['last_heartbeat_at']
                    minutes_ago = int(delta.total_seconds() / 60)
                    if minutes_ago < 1:
                        heartbeat_elapsed = "< 1 min ago"
                    elif minutes_ago < 60:
                        heartbeat_elapsed = f"{minutes_ago} min ago"
                    else:
                        hours = minutes_ago // 60
                        heartbeat_elapsed = f"{hours}h ago"
                except Exception:
                    heartbeat_elapsed = "Unknown"

            result.append({
                'agentId': agent['id'],
                'agentName': agent['logical_agent_id'],
                'status': agent['status'],
                'currentMode': agent.get('current_mode'),
                'currentPoolId': agent.get('current_pool_id'),
                'isHealthy': is_healthy,
                'lastHeartbeat': heartbeat_elapsed,
                'lastDecision': {
                    'type': agent.get('last_decision'),
                    'time': agent['last_decision_time'].isoformat() if agent.get('last_decision_time') else None,
                    'elapsed': time_elapsed
                },
                'decisionHistory': [{
                    'type': d['decision_type'],
                    'action': d.get('recommended_action'),
                    'riskScore': float(d['risk_score']) if d.get('risk_score') else None,
                    'expectedSavings': float(d['expected_savings']) if d.get('expected_savings') else None,
                    'currentMode': d.get('current_mode'),
                    'time': d['decision_time'].isoformat() if d.get('decision_time') else None
                } for d in (decision_history or [])],
                'recentActivity': {
                    'pricingReports': [{
                        'time': r['received_at'].isoformat() if r.get('received_at') else None,
                        'onDemandPrice': float(r['ondemand_price']) if r.get('ondemand_price') else 0,
                        'spotPrice': float(r['current_spot_price']) if r.get('current_spot_price') else 0
                    } for r in (recent_reports or [])],
                    'systemEvents': [{
                        'type': e['event_type'],
                        'severity': e.get('severity'),
                        'message': e.get('message'),
                        'time': e['created_at'].isoformat() if e.get('created_at') else None
                    } for e in (recent_events or [])],
                    'healthStatus': {
                        'overall': 'healthy' if is_healthy else 'unhealthy',
                        'heartbeat': 'active' if heartbeat_healthy else 'stale',
                        'activity': 'active' if activity_healthy else 'inactive',
                        'recentReportsCount': recent_reports_count,
                        'decisionCount': len(decision_history or [])
                    }
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
    """
    Update agent configuration including switches and replica settings.

    IMPORTANT: auto_switch_enabled and manual_replica_enabled are MUTUALLY EXCLUSIVE
    - When auto_switch_enabled = ON: ML model auto-switches + emergency replicas on interruption
    - When manual_replica_enabled = ON: Manual replica maintained, no auto-switching
    """
    data = request.json or {}

    try:
        updates = []
        params = []

        # Get current agent state
        agent = execute_query("""
            SELECT auto_switch_enabled, manual_replica_enabled, replica_count, instance_id
            FROM agents WHERE id = %s
        """, (agent_id,), fetch_one=True)

        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        current_auto_switch = agent.get('auto_switch_enabled', False)
        current_manual_replica = agent.get('manual_replica_enabled', False)
        replica_count = agent.get('replica_count', 0)
        instance_id = agent.get('instance_id')

        # Handle terminate_wait_minutes (for backwards compatibility)
        if 'terminate_wait_minutes' in data:
            terminate_wait_seconds = int(data['terminate_wait_minutes']) * 60
            updates.append("terminate_wait_seconds = %s")
            params.append(terminate_wait_seconds)

        # Handle new config object format
        if 'terminateWaitMinutes' in data:
            terminate_wait_seconds = int(data['terminateWaitMinutes']) * 60
            updates.append("terminate_wait_seconds = %s")
            params.append(terminate_wait_seconds)

        # Handle auto_terminate_enabled
        if 'autoTerminateEnabled' in data:
            auto_terminate = bool(data['autoTerminateEnabled'])
            updates.append("auto_terminate_enabled = %s")
            params.append(auto_terminate)
            # Force config refresh on next heartbeat
            updates.append("config_version = config_version + 1")
            logger.info(f"Setting auto_terminate_enabled = {auto_terminate} for agent {agent_id}")

        # MUTUAL EXCLUSIVITY ENFORCEMENT
        # Case 1: User enables auto_switch_enabled
        if 'autoSwitchEnabled' in data and bool(data['autoSwitchEnabled']):
            updates.append("auto_switch_enabled = TRUE")
            updates.append("manual_replica_enabled = FALSE")  # Force off
            updates.append("config_version = config_version + 1")  # Force config refresh

            # If manual replicas exist, terminate them
            if current_manual_replica and replica_count > 0:
                logger.info(f"Auto-switch enabled for agent {agent_id}, terminating manual replicas")
                execute_query("""
                    UPDATE replica_instances
                    SET is_active = FALSE, status = 'terminated', terminated_at = NOW()
                    WHERE agent_id = %s AND is_active = TRUE AND replica_type = 'manual'
                """, (agent_id,))
                updates.append("replica_count = 0")
                updates.append("current_replica_id = NULL")

        # Case 2: User disables auto_switch_enabled
        elif 'autoSwitchEnabled' in data and not bool(data['autoSwitchEnabled']):
            updates.append("auto_switch_enabled = FALSE")
            updates.append("config_version = config_version + 1")  # Force config refresh

        # Case 3: User enables manual_replica_enabled
        if 'manualReplicaEnabled' in data and bool(data['manualReplicaEnabled']):
            updates.append("manual_replica_enabled = TRUE")
            updates.append("auto_switch_enabled = FALSE")  # Force off
            updates.append("config_version = config_version + 1")  # Force config refresh

            logger.info(f"Manual replica enabled for agent {agent_id} - creating replica immediately")

            # Check if replica already exists
            existing_replicas = execute_query("""
                SELECT COUNT(*) as count FROM replica_instances
                WHERE agent_id = %s AND is_active = TRUE AND status NOT IN ('terminated', 'promoted', 'failed')
            """, (agent_id,), fetch_one=True)

            # Trigger immediate replica creation if coordinator is available and no replica exists
            if existing_replicas and existing_replicas['count'] == 0:
                global replica_coordinator
                if replica_coordinator:
                    try:
                        # Get agent data for replica creation
                        agent_data = execute_query("""
                            SELECT id, instance_id FROM agents WHERE id = %s
                        """, (agent_id,), fetch_one=True)

                        if agent_data:
                            # Call coordinator's method to create replica immediately
                            import threading
                            threading.Thread(
                                target=replica_coordinator._create_manual_replica,
                                args=(agent_data,),
                                daemon=True
                            ).start()
                            logger.info(f"✓ Triggered immediate manual replica creation for agent {agent_id}")
                    except Exception as e:
                        logger.error(f"Failed to trigger immediate replica creation: {e}")
                        logger.info(f"ReplicaCoordinator will create replica in next monitoring cycle (2s)")
                else:
                    logger.info(f"ReplicaCoordinator not initialized - replica will be created in next cycle")
            else:
                logger.info(f"Manual replica already exists for agent {agent_id} - skipping creation")

        # Case 4: User disables manual_replica_enabled
        elif 'manualReplicaEnabled' in data and not bool(data['manualReplicaEnabled']):
            updates.append("manual_replica_enabled = FALSE")
            updates.append("config_version = config_version + 1")  # Force config refresh

            logger.info(f"Manual replica DISABLED for agent {agent_id} - terminating all active replicas IMMEDIATELY")

            # Terminate all active replicas (promoted ones are already converted to primary instances)
            if current_manual_replica or replica_count > 0:
                # Get replica IDs before terminating for logging
                replica_ids = execute_query("""
                    SELECT id, instance_id, status FROM replica_instances
                    WHERE agent_id = %s
                      AND is_active = TRUE
                      AND status != 'promoted'
                """, (agent_id,), fetch=True)

                # Terminate all active replicas for this agent
                terminated_count = execute_query("""
                    UPDATE replica_instances
                    SET is_active = FALSE, status = 'terminated', terminated_at = NOW()
                    WHERE agent_id = %s
                      AND is_active = TRUE
                      AND status != 'promoted'
                """, (agent_id,))

                logger.info(f"✓ TERMINATED {terminated_count} active replicas for agent {agent_id}")

                # Also terminate in instances table
                if replica_ids:
                    for rep in replica_ids:
                        if rep.get('instance_id'):
                            execute_query("""
                                UPDATE instances
                                SET instance_status = 'terminated', is_active = FALSE, terminated_at = NOW()
                                WHERE id = %s
                            """, (rep['instance_id'],))
                            logger.info(f"✓ Marked instance {rep['instance_id']} as TERMINATED")

                    # Log to system_events
                    execute_query("""
                        INSERT INTO system_events (event_type, severity, agent_id, message, metadata)
                        VALUES ('replicas_disabled', 'info', %s, %s, %s)
                    """, (agent_id,
                          f"Manual replica mode disabled - terminated {terminated_count} replicas",
                          json.dumps({'terminated_count': terminated_count, 'replica_ids': [r['id'] for r in replica_ids]})))

                updates.append("replica_count = 0")
                updates.append("current_replica_id = NULL")
            else:
                logger.info(f"Manual replica disabled for agent {agent_id} - no active replicas to terminate")

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(agent_id)

            query = f"""
                UPDATE agents
                SET {', '.join(updates)}
                WHERE id = %s
            """
            execute_query(query, tuple(params))

            logger.info(f"Updated agent {agent_id} configuration: {data}")

        return jsonify({
            'success': True,
            'auto_switch_enabled': bool(data.get('autoSwitchEnabled', current_auto_switch)),
            'manual_replica_enabled': bool(data.get('manualReplicaEnabled', current_manual_replica))
        })

    except Exception as e:
        logger.error(f"Update agent config error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/agents/<agent_id>', methods=['DELETE'])
def delete_agent(agent_id: str):
    """
    Delete agent and clean up all associated resources.

    This endpoint:
    1. Terminates all active replicas
    2. Marks agent as 'deleted' (soft delete)
    3. Marks agent instance as inactive
    4. Creates command for client to uninstall agent
    5. Preserves all history for analytics
    """
    try:
        # Verify agent exists and get details
        agent = execute_query("""
            SELECT id, client_id, instance_id, status, manual_replica_enabled, auto_switch_enabled
            FROM agents
            WHERE id = %s
        """, (agent_id,), fetch_one=True)

        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        # Terminate all active replicas for this agent
        execute_query("""
            UPDATE replica_instances
            SET is_active = FALSE, status = 'terminated', terminated_at = NOW()
            WHERE agent_id = %s AND is_active = TRUE
        """, (agent_id,))

        # Mark agent as deleted (soft delete - preserve history)
        execute_query("""
            UPDATE agents
            SET status = 'deleted',
                enabled = FALSE,
                auto_switch_enabled = FALSE,
                manual_replica_enabled = FALSE,
                replica_count = 0,
                current_replica_id = NULL,
                updated_at = NOW()
            WHERE id = %s
        """, (agent_id,))

        # Mark associated instance as inactive
        if agent['instance_id']:
            execute_query("""
                UPDATE instances
                SET is_active = FALSE, terminated_at = NOW()
                WHERE id = %s
            """, (agent['instance_id'],))

        # Log deletion event
        log_system_event(
            'agent_deleted',
            'info',
            f"Agent {agent_id} deleted by user",
            agent['client_id']
        )

        create_notification(
            f"Agent {agent_id} has been deleted",
            'info',
            agent['client_id']
        )

        logger.info(f"Agent {agent_id} deleted successfully")

        return jsonify({
            'success': True,
            'message': 'Agent deleted successfully',
            'agent_id': agent_id
        })

    except Exception as e:
        logger.error(f"Delete agent error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/agents/history', methods=['GET'])
def get_client_agent_history(client_id: str):
    """Get all agents including deleted ones for history view"""
    try:
        agents = execute_query("""
            SELECT
                a.id,
                a.logical_agent_id,
                a.instance_id,
                a.instance_type,
                a.region,
                a.az,
                a.current_mode,
                a.status,
                a.enabled,
                a.auto_switch_enabled,
                a.manual_replica_enabled,
                a.created_at,
                a.updated_at,
                a.last_heartbeat_at,
                i.installed_at,
                i.terminated_at as instance_terminated_at
            FROM agents a
            LEFT JOIN instances i ON a.instance_id = i.id
            WHERE a.client_id = %s
            ORDER BY
                CASE a.status
                    WHEN 'online' THEN 1
                    WHEN 'offline' THEN 2
                    WHEN 'deleted' THEN 3
                    ELSE 4
                END,
                a.last_heartbeat_at DESC
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
            'enabled': agent['enabled'],
            'autoSwitchEnabled': agent['auto_switch_enabled'],
            'manualReplicaEnabled': agent['manual_replica_enabled'],
            'createdAt': agent['created_at'].isoformat() if agent['created_at'] else None,
            'updatedAt': agent['updated_at'].isoformat() if agent['updated_at'] else None,
            'lastHeartbeat': agent['last_heartbeat_at'].isoformat() if agent['last_heartbeat_at'] else None,
            'installedAt': agent['installed_at'].isoformat() if agent.get('installed_at') else None,
            'terminatedAt': agent['instance_terminated_at'].isoformat() if agent.get('instance_terminated_at') else None
        } for agent in agents or []])

    except Exception as e:
        logger.error(f"Get agent history error: {e}", exc_info=True)
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

        # Filter by instance_status for proper active/terminated separation
        if status == 'active':
            # Active space: primary + replica instances only
            query += " AND instance_status IN ('running_primary', 'running_replica')"
        elif status == 'terminated':
            # Terminated space: zombie + terminated instances only
            query += " AND instance_status IN ('zombie', 'terminated')"

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
            'instanceStatus': inst.get('instance_status', 'running_primary'),
            'isPrimary': inst.get('is_primary', True),
            'lastSwitch': inst['last_switch_at'].isoformat() if inst['last_switch_at'] else None
        } for inst in instances or []])
        
    except Exception as e:
        logger.error(f"Get instances error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/replicas', methods=['GET'])
def get_client_replicas(client_id: str):
    """Get all instances with active replicas for a client"""
    try:
        # Check if replica_instances table exists
        table_exists = execute_query("""
            SELECT COUNT(*) as count
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'replica_instances'
        """, fetch_one=True)

        if not table_exists or table_exists.get('count', 0) == 0:
            logger.info("replica_instances table does not exist yet, returning empty list")
            return jsonify([])

        # Get all active replicas with their parent instance and agent info
        replicas = execute_query("""
            SELECT
                ri.id as replica_id,
                ri.instance_id as replica_instance_id,
                ri.replica_type,
                ri.pool_id,
                ri.status as replica_status,
                ri.sync_status,
                ri.sync_latency_ms,
                ri.state_transfer_progress,
                ri.hourly_cost,
                ri.total_cost,
                ri.created_by,
                ri.created_at as replica_created_at,
                ri.ready_at as replica_ready_at,
                ri.terminated_at as replica_terminated_at,
                ri.is_active as replica_is_active,
                sp.pool_name,
                sp.instance_type as pool_instance_type,
                sp.region as pool_region,
                sp.az as pool_az,
                a.id as agent_id,
                a.instance_id as primary_instance_id,
                i.instance_type as primary_instance_type,
                i.region as primary_region,
                i.az as primary_az,
                i.current_mode as primary_mode
            FROM replica_instances ri
            LEFT JOIN spot_pools sp ON ri.pool_id = sp.id
            JOIN agents a ON ri.agent_id = a.id
            LEFT JOIN instances i ON a.instance_id = i.id
            WHERE a.client_id = %s
              AND ri.is_active = TRUE
              AND ri.status NOT IN ('terminated', 'promoted')
            ORDER BY ri.created_at DESC
        """, (client_id,), fetch=True)

        result = []
        for r in (replicas or []):
            result.append({
                'agentId': r['agent_id'],
                'primary': {
                    'instanceId': r['primary_instance_id'],
                    'instanceType': r['primary_instance_type'],
                    'region': r['primary_region'],
                    'az': r['primary_az'],
                    'mode': r['primary_mode']
                },
                'replica': {
                    'id': r['replica_id'],
                    'instanceId': r['replica_instance_id'],
                    'type': r['replica_type'],
                    'status': r['replica_status'],
                    'sync_status': r['sync_status'],
                    'sync_latency_ms': r['sync_latency_ms'],
                    'state_transfer_progress': float(r['state_transfer_progress']) if r['state_transfer_progress'] else 0.0,
                    'pool': {
                        'id': r['pool_id'],
                        'name': r['pool_name'],
                        'instance_type': r['pool_instance_type'],
                        'region': r['pool_region'],
                        'az': r['pool_az']
                    } if r['pool_id'] else None,
                    'cost': {
                        'hourly': float(r['hourly_cost']) if r['hourly_cost'] else None,
                        'total': float(r['total_cost']) if r['total_cost'] else 0.0
                    },
                    'created_by': r['created_by'],
                    'created_at': r['replica_created_at'].isoformat() if r['replica_created_at'] else None,
                    'ready_at': r['replica_ready_at'].isoformat() if r['replica_ready_at'] else None,
                    'terminated_at': r['replica_terminated_at'].isoformat() if r['replica_terminated_at'] else None,
                    'is_active': bool(r['replica_is_active'])
                }
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"Get client replicas error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/instances/<instance_id>/pricing', methods=['GET'])
def get_instance_pricing(instance_id: str):
    """Get pricing details for instance with current mode and pool info"""
    try:
        # Get instance details including current state
        instance = execute_query("""
            SELECT i.instance_type, i.region, i.ondemand_price, i.current_pool_id, i.current_mode, i.client_id
            FROM instances i
            WHERE i.id = %s
        """, (instance_id,), fetch_one=True)

        if not instance:
            return jsonify({'error': 'Instance not found'}), 404

        # Get all available pools for this instance type with latest prices
        pools = execute_query("""
            SELECT
                sp.id as pool_id,
                sp.pool_name,
                sp.az,
                sps.price as price,
                sps.captured_at as captured_at
            FROM spot_pools sp
            LEFT JOIN (
                SELECT pool_id, price, captured_at,
                       ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
                FROM spot_price_snapshots
                WHERE captured_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            ) sps ON sps.pool_id = sp.id AND sps.rn = 1
            WHERE sp.instance_type = %s AND sp.region = %s
            ORDER BY COALESCE(sps.price, 999999) ASC
        """, (instance['instance_type'], instance['region']), fetch=True)

        ondemand_price = float(instance['ondemand_price'] or 0)

        # Get current pool details
        current_pool = None
        if instance['current_pool_id']:
            current_pool_data = execute_query("""
                SELECT id, pool_name, az FROM spot_pools WHERE id = %s
            """, (instance['current_pool_id'],), fetch_one=True)
            if current_pool_data:
                current_pool = {
                    'id': current_pool_data['id'],
                    'name': current_pool_data['pool_name'],
                    'az': current_pool_data['az']
                }

        return jsonify({
            'currentMode': instance['current_mode'] or 'ondemand',
            'currentPool': current_pool,
            'onDemand': {
                'name': 'On-Demand',
                'price': ondemand_price
            },
            'pools': [{
                'id': pool['pool_id'],
                'name': pool['pool_name'] or f"Pool {pool['pool_id']}",
                'az': pool['az'],
                'price': float(pool['price']) if pool['price'] else 0,
                'savings': ((ondemand_price - float(pool['price'])) / ondemand_price * 100) if (ondemand_price > 0 and pool['price']) else 0
            } for pool in pools or []]
        })

    except Exception as e:
        logger.error(f"Get instance pricing error: {e}", exc_info=True)
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

@app.route('/api/client/instances/<instance_id>/price-history', methods=['GET'])
def get_instance_price_history(instance_id: str):
    """Get historical pricing data for all pools (for multi-line chart)"""
    try:
        days = request.args.get('days', 7, type=int)
        interval = request.args.get('interval', 'hour')  # 'hour' or 'day'

        # Limit to reasonable range
        days = min(max(days, 1), 90)

        # Get instance info
        instance = execute_query("""
            SELECT i.id, i.instance_type, i.region, i.ondemand_price
            FROM instances i
            WHERE i.id = %s
        """, (instance_id,), fetch_one=True)

        if not instance:
            return jsonify({'error': 'Instance not found'}), 404

        # Get all pools for this instance type
        pools = execute_query("""
            SELECT id, pool_name, az
            FROM spot_pools
            WHERE instance_type = %s AND region = %s
        """, (instance['instance_type'], instance['region']), fetch=True)

        if not pools:
            return jsonify([])

        # Get pricing data for all pools
        time_format = '%%Y-%%m-%%d %%H:00' if interval == 'hour' else '%%Y-%%m-%%d'

        # Build IN clause with proper parameters
        pool_ids = [p['id'] for p in pools]
        placeholders = ','.join(['%s'] * len(pool_ids))

        # Query to get pricing for all pools from real-time snapshots
        query = f"""
            SELECT
                DATE_FORMAT(sps.captured_at, %s) as time,
                sps.pool_id,
                AVG(sps.price) as price
            FROM spot_price_snapshots sps
            WHERE sps.pool_id IN ({placeholders})
              AND sps.captured_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE_FORMAT(sps.captured_at, %s), sps.pool_id
            ORDER BY time ASC, sps.pool_id
        """

        params = [time_format] + pool_ids + [days, time_format]
        price_data = execute_query(query, tuple(params), fetch=True)

        # Get unique timestamps
        timestamps = sorted(set(row['time'] for row in (price_data or [])))

        # Build result with each timestamp having prices for all pools
        pool_map = {p['id']: {'name': p['pool_name'], 'az': p['az']} for p in pools}
        price_map = {}
        for row in (price_data or []):
            key = str(row['time'])
            if key not in price_map:
                price_map[key] = {}
            price_map[key][row['pool_id']] = float(row['price'])

        # Build final result
        result = []
        ondemand_price = float(instance['ondemand_price'] or 0)

        for timestamp in timestamps:
            data_point = {
                'time': timestamp,
                'onDemand': ondemand_price
            }
            # Add each pool's price
            for pool in pools:
                pool_id = pool['id']
                pool_key = f"pool_{pool_id}"
                data_point[pool_key] = price_map.get(timestamp, {}).get(pool_id, None)
            result.append(data_point)

        # Also return pool metadata for the frontend to know which lines to draw
        pool_metadata = [{
            'id': p['id'],
            'name': p['pool_name'] or f"Pool {p['id']}",
            'az': p['az'],
            'key': f"pool_{p['id']}"
        } for p in pools]

        return jsonify({
            'data': result,
            'pools': pool_metadata,
            'onDemandPrice': ondemand_price
        })

    except Exception as e:
        logger.error(f"Get price history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/pricing-history', methods=['GET'])
@require_client_token
def get_client_pricing_history():
    """
    Get pricing history for client (optionally filtered by agent_id)

    Query params:
    - days: Number of days (default 7, max 30)
    - agent_id: Optional agent ID to filter data
    - interval: 'hour' or 'day' (default 'hour')
    """
    try:
        client_id = request.client_id
        days = int(request.args.get('days', 7))
        agent_id = request.args.get('agent_id')
        interval = request.args.get('interval', 'hour')

        # Limit to reasonable range
        days = min(max(days, 1), 30)

        # Get agent's instance details
        if agent_id:
            agent = execute_query("""
                SELECT a.instance_id, a.instance_type, a.region
                FROM agents a
                WHERE a.id = %s AND a.client_id = %s
            """, (agent_id, client_id), fetch_one=True)

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            instance_id = agent['instance_id']
            instance_type = agent['instance_type']
            region = agent['region']
        else:
            # Get first active agent for this client
            agent = execute_query("""
                SELECT a.instance_id, a.instance_type, a.region
                FROM agents a
                WHERE a.client_id = %s AND a.status = 'online'
                ORDER BY a.last_heartbeat_at DESC
                LIMIT 1
            """, (client_id,), fetch_one=True)

            if not agent:
                return jsonify({'error': 'No active agents found'}), 404

            instance_id = agent['instance_id']
            instance_type = agent['instance_type']
            region = agent['region']

        # Get all pools for this instance type
        pools = execute_query("""
            SELECT id, pool_name, az
            FROM spot_pools
            WHERE instance_type = %s AND region = %s
        """, (instance_type, region), fetch=True)

        if not pools:
            return jsonify({
                'history': [],
                'days': days,
                'data_points': 0
            })

        # Get pricing data
        time_format = '%%Y-%%m-%%d %%H:00:00' if interval == 'hour' else '%%Y-%%m-%%d'
        pool_ids = [p['id'] for p in pools]
        placeholders = ','.join(['%s'] * len(pool_ids))

        query = f"""
            SELECT
                DATE_FORMAT(sps.captured_at, %s) as timestamp,
                sps.pool_id,
                AVG(sps.price) as price
            FROM spot_price_snapshots sps
            WHERE sps.pool_id IN ({placeholders})
              AND sps.captured_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE_FORMAT(sps.captured_at, %s), sps.pool_id
            ORDER BY timestamp ASC
        """

        params = [time_format] + pool_ids + [days, time_format]
        price_data = execute_query(query, tuple(params), fetch=True)

        # Get on-demand price
        ondemand_query = """
            SELECT AVG(price) as avg_price
            FROM ondemand_price_snapshots
            WHERE instance_type = %s AND region = %s
              AND captured_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        """
        ondemand_result = execute_query(ondemand_query, (instance_type, region, days), fetch_one=True)
        ondemand_price = float(ondemand_result['avg_price']) if ondemand_result and ondemand_result['avg_price'] else 0.0416

        # Transform into time series format expected by frontend
        time_buckets = {}
        for row in (price_data or []):
            timestamp = str(row['timestamp'])
            pool_id = row['pool_id']
            price = float(row['price'])

            if timestamp not in time_buckets:
                time_buckets[timestamp] = {
                    'timestamp': timestamp,
                    'ondemand_price': ondemand_price,
                    'spot_pools': []
                }

            # Extract AZ from pool_id
            az = pool_id.split('.')[-1] if '.' in pool_id else 'unknown'

            time_buckets[timestamp]['spot_pools'].append({
                'pool_id': pool_id,
                'az': az,
                'price': price
            })

        # Convert to array and sort by time
        history = sorted(time_buckets.values(), key=lambda x: x['timestamp'])

        return jsonify({
            'history': history,
            'days': days,
            'data_points': len(history),
            'agent_id': agent_id,
            'instance_type': instance_type,
            'region': region
        }), 200

    except Exception as e:
        logger.error(f"Get client pricing history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/instances/<instance_id>/available-options', methods=['GET'])
def get_instance_available_options(instance_id: str):
    """Get available pools and instance types for switching"""
    try:
        # Get current instance information from agents table (primary source)
        agent = execute_query("""
            SELECT instance_type, region, az FROM agents WHERE instance_id = %s
        """, (instance_id,), fetch_one=True)

        # Fallback: Check instances table if agent hasn't sent heartbeat yet
        if not agent:
            agent = execute_query("""
                SELECT instance_type, region, az FROM instances WHERE id = %s
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

        # Get agent's auto-terminate configuration
        agent_config = execute_query("""
            SELECT auto_terminate_enabled, terminate_wait_seconds
            FROM agents
            WHERE id = %s
        """, (instance['agent_id'],), fetch_one=True)

        # Determine terminate_wait_seconds based on auto_terminate setting
        if agent_config and agent_config['auto_terminate_enabled']:
            terminate_wait = agent_config['terminate_wait_seconds'] or 300
        else:
            terminate_wait = 0  # Signal: DO NOT terminate old instance

        # Build metadata for logging
        metadata = {
            'target': target_mode,
            'pool_id': target_pool_id
        }
        if new_instance_type:
            metadata['new_instance_type'] = new_instance_type
            # Note: Instance type changes require agent-side support
            logger.info(f"Instance type change requested: {new_instance_type}")

        # Insert pending command with manual priority (75) and terminate_wait_seconds
        command_id = generate_uuid()
        execute_query("""
            INSERT INTO commands
            (id, client_id, agent_id, instance_id, command_type, target_mode, target_pool_id, priority, terminate_wait_seconds, status, created_by)
            VALUES (%s, %s, %s, %s, 'switch', %s, %s, 75, %s, 'pending', 'manual')
        """, (
            command_id,
            instance['client_id'],
            instance['agent_id'],
            instance_id,
            target_mode if target_mode != 'pool' else 'spot',
            target_pool_id,
            terminate_wait
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
            'timestamp': (h['instance_launched_at'] or h['ami_created_at'] or h['initiated_at']).isoformat() if (h.get('instance_launched_at') or h.get('ami_created_at') or h.get('initiated_at')) else datetime.now().isoformat(),
            'fromMode': h['old_mode'],
            'toMode': h['new_mode'],
            'fromPool': h['old_pool_id'] or 'n/a',
            'toPool': h['new_pool_id'] or 'n/a',
            'trigger': h['event_trigger'] or 'manual',
            'price': float(h['new_spot_price'] or 0) if h['new_mode'] == 'spot' else float(h['on_demand_price'] or 0),
            'savingsImpact': float(h['savings_impact'] or 0)
        } for h in history or []])
        
    except Exception as e:
        logger.error(f"Get switch history error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/export/savings', methods=['GET'])
def export_client_savings(client_id: str):
    """Export savings data as CSV"""
    try:
        import io
        import csv

        # Get savings data
        savings = execute_query("""
            SELECT
                year,
                month,
                MONTHNAME(CONCAT(year, '-', LPAD(month, 2, '0'), '-01')) as month_name,
                baseline_cost,
                actual_cost,
                savings
            FROM client_savings_monthly
            WHERE client_id = %s
            ORDER BY year DESC, month DESC
        """, (client_id,), fetch=True)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Year', 'Month', 'Month Name', 'On-Demand Cost ($)', 'Actual Cost ($)', 'Savings ($)'])

        # Write data
        for s in (savings or []):
            writer.writerow([
                s['year'],
                s['month'],
                s['month_name'],
                f"{float(s['baseline_cost'] or 0):.2f}",
                f"{float(s['actual_cost'] or 0):.2f}",
                f"{float(s['savings'] or 0):.2f}"
            ])

        # Prepare response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=client_{client_id}_savings.csv'}
        )

    except Exception as e:
        logger.error(f"Export savings error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/<client_id>/export/switch-history', methods=['GET'])
def export_switch_history(client_id: str):
    """Export switch history as CSV"""
    try:
        import io
        import csv

        # Get switch history
        history = execute_query("""
            SELECT *
            FROM switches
            WHERE client_id = %s
            ORDER BY initiated_at DESC
        """, (client_id,), fetch=True)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Timestamp', 'Old Instance ID', 'New Instance ID', 'From Mode', 'To Mode',
                        'From Pool', 'To Pool', 'Trigger', 'Price ($)', 'Savings Impact ($/hr)'])

        # Write data
        for h in (history or []):
            timestamp = (h.get('instance_launched_at') or h.get('ami_created_at') or h.get('initiated_at')).isoformat() if (h.get('instance_launched_at') or h.get('ami_created_at') or h.get('initiated_at')) else ''
            price = float(h['new_spot_price'] or 0) if h['new_mode'] == 'spot' else float(h['on_demand_price'] or 0)

            writer.writerow([
                timestamp,
                h['old_instance_id'] or 'N/A',
                h['new_instance_id'] or 'N/A',
                h['old_mode'] or 'N/A',
                h['new_mode'] or 'N/A',
                h['old_pool_id'] or 'N/A',
                h['new_pool_id'] or 'N/A',
                h['event_trigger'] or 'manual',
                f"{price:.6f}",
                f"{float(h['savings_impact'] or 0):.6f}"
            ])

        # Prepare response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=client_{client_id}_switch_history.csv'}
        )

    except Exception as e:
        logger.error(f"Export switch history error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/export/global-stats', methods=['GET'])
def export_global_stats():
    """Export global statistics as CSV"""
    try:
        import io
        import csv

        # Get top clients by savings
        clients = execute_query("""
            SELECT
                c.id,
                c.name,
                c.email,
                c.total_savings,
                c.created_at,
                COUNT(DISTINCT i.id) as instance_count,
                COUNT(DISTINCT a.id) as agent_count
            FROM clients c
            LEFT JOIN instances i ON i.client_id = c.id AND i.is_active = TRUE
            LEFT JOIN agents a ON a.client_id = c.id AND a.enabled = TRUE
            WHERE c.is_active = TRUE
            GROUP BY c.id, c.name, c.email, c.total_savings, c.created_at
            ORDER BY c.total_savings DESC
        """, fetch=True)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Client ID', 'Name', 'Email', 'Total Savings ($)', 'Active Instances',
                        'Active Agents', 'Created At'])

        # Write data
        for client in (clients or []):
            writer.writerow([
                client['id'],
                client['name'],
                client['email'],
                f"{float(client['total_savings'] or 0):.2f}",
                client['instance_count'] or 0,
                client['agent_count'] or 0,
                client['created_at'].isoformat() if client.get('created_at') else ''
            ])

        # Prepare response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=global_stats.csv'}
        )

    except Exception as e:
        logger.error(f"Export global stats error: {e}")
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
        model_files = []
        try:
            if config.MODEL_DIR.exists():
                files = [f for f in config.MODEL_DIR.glob('*') if f.is_file()]
                model_files_count = len(files)
                model_files = [{
                    'name': f.name,
                    'size': f.stat().st_size,
                    'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                } for f in files[:10]]  # Limit to 10 most recent
        except Exception as e:
            logger.warning(f"Could not count model files: {e}")

        # Count decision engine files
        engine_files_count = 0
        engine_files = []
        try:
            if config.DECISION_ENGINE_DIR.exists():
                files = [f for f in config.DECISION_ENGINE_DIR.glob('*.py') if f.is_file()]
                engine_files_count = len(files)
                engine_files = [{
                    'name': f.name,
                    'size': f.stat().st_size,
                    'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                } for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]]
        except Exception as e:
            logger.warning(f"Could not count decision engine files: {e}")

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
                'activeModels': active_models,
                'files': model_files
            },
            'decisionEngineStatus': {
                'loaded': decision_engine_manager.models_loaded,
                'type': decision_engine_manager.engine_type or 'None',
                'version': decision_engine_manager.engine_version or 'N/A',
                'filesUploaded': engine_files_count,
                'files': engine_files
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

def restart_backend(delay_seconds: int = 3):
    """Restart the backend server after a delay

    Args:
        delay_seconds: Seconds to wait before restart (allows response to be sent)
    """
    def _restart():
        try:
            time.sleep(delay_seconds)
            logger.info("="*80)
            logger.info("RESTARTING BACKEND SERVER...")
            logger.info("="*80)

            # Check if running as systemd service (check for restart script)
            restart_script = Path('/home/ubuntu/spot-optimizer/backend/restart_backend.sh')
            if restart_script.exists():
                logger.info("Using restart script to restart systemd service")
                subprocess.Popen([str(restart_script)],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               start_new_session=True)
            # Check if running under gunicorn
            elif 'gunicorn' in os.environ.get('SERVER_SOFTWARE', ''):
                logger.info("Detected gunicorn - sending HUP signal to reload workers")
                # Send HUP signal to master process to reload workers
                os.kill(os.getppid(), signal.SIGHUP)
            else:
                logger.info("Restarting Python process...")
                # Restart the Python process
                python = sys.executable
                os.execv(python, [python] + sys.argv)
        except Exception as e:
            logger.error(f"Failed to restart backend: {e}")
            logger.info("Please manually restart: sudo systemctl restart spot-optimizer-backend")

    # Start restart in a background thread
    restart_thread = threading.Thread(target=_restart, daemon=True)
    restart_thread.start()
    logger.info(f"Backend restart scheduled in {delay_seconds} seconds...")

@app.route('/api/admin/decision-engine/upload', methods=['POST'])
def upload_decision_engine():
    """Upload decision engine files"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files selected'}), 400

        # Ensure decision engine directory exists
        config.DECISION_ENGINE_DIR.mkdir(parents=True, exist_ok=True)

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

            # Schedule backend restart
            restart_backend(delay_seconds=3)

            return jsonify({
                'success': True,
                'message': 'Decision engine files uploaded successfully. Backend will restart in 3 seconds.',
                'files': uploaded_files,
                'restarting': True,
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
    """Upload ML model files with versioning (keeps last 2 upload sessions)"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files selected'}), 400

        # Ensure model directory exists
        config.MODEL_DIR.mkdir(parents=True, exist_ok=True)

        # Step 1: Mark current live session as fallback
        execute_query("""
            UPDATE model_upload_sessions
            SET is_live = FALSE, is_fallback = TRUE
            WHERE is_live = TRUE AND session_type = 'models'
        """)

        # Step 2: Create new upload session
        session_id = str(uuid.uuid4())
        uploaded_files = []
        total_size = 0

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

                # Track file info
                file_size = file_path.stat().st_size
                uploaded_files.append(filename)
                total_size += file_size
                logger.info(f"✓ Uploaded ML model file: {filename} ({file_size} bytes)")

        # Step 3: Create upload session record
        execute_query("""
            INSERT INTO model_upload_sessions
            (id, session_type, status, is_live, is_fallback, file_count, file_names, total_size_bytes)
            VALUES (%s, 'models', 'uploaded', FALSE, FALSE, %s, %s, %s)
        """, (session_id, len(uploaded_files), json.dumps(uploaded_files), total_size))

        # Step 4: Clean up old sessions (keep only last 2)
        old_sessions = execute_query("""
            SELECT id, file_names
            FROM model_upload_sessions
            WHERE session_type = 'models'
              AND is_live = FALSE
              AND is_fallback = FALSE
            ORDER BY created_at DESC
            LIMIT 100 OFFSET 1
        """, fetch=True)

        if old_sessions:
            for old_session in old_sessions:
                # Delete old files
                try:
                    old_files = json.loads(old_session['file_names']) if old_session.get('file_names') else []
                    for old_file in old_files:
                        old_path = config.MODEL_DIR / old_file
                        if old_path.exists():
                            old_path.unlink()
                            logger.info(f"Deleted old model file: {old_file}")
                except Exception as e:
                    logger.warning(f"Error deleting old files: {e}")

                # Delete session record
                execute_query("DELETE FROM model_upload_sessions WHERE id = %s", (old_session['id'],))

        logger.info(f"✓ Created new upload session: {session_id} with {len(uploaded_files)} files")

        # Return success response (don't auto-reload yet)
        return jsonify({
            'success': True,
            'message': f'Uploaded {len(uploaded_files)} model files. Use the RESTART button to activate.',
            'files': uploaded_files,
            'sessionId': session_id,
            'requiresRestart': True,
            'model_status': {
                'filesUploaded': len(uploaded_files),
                'totalSize': total_size,
                'sessionType': 'pending_activation'
            }
        }), 200

    except Exception as e:
        logger.error(f"ML models upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/ml-models/activate', methods=['POST'])
def activate_ml_models():
    """Activate uploaded models and restart backend with new models"""
    try:
        data = request.get_json() or {}
        session_id = data.get('sessionId')

        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400

        # Mark session as live
        execute_query("""
            UPDATE model_upload_sessions
            SET is_live = TRUE, status = 'active', activated_at = NOW()
            WHERE id = %s AND session_type = 'models'
        """, (session_id,))

        # Reload decision engine to pick up new models
        logger.info("Activating new models and reloading decision engine...")
        success = decision_engine_manager.load_engine()

        if success:
            log_system_event('ml_models_activated', 'info',
                           f'New model session activated: {session_id}')

            # Schedule backend restart
            restart_backend(delay_seconds=3)

            return jsonify({
                'success': True,
                'message': 'Models activated successfully. Backend will restart in 3 seconds.',
                'sessionId': session_id,
                'restarting': True,
                'model_status': {
                    'loaded': decision_engine_manager.models_loaded,
                    'type': decision_engine_manager.engine_type
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to load new models',
                'sessionId': session_id
            }), 500

    except Exception as e:
        logger.error(f"Model activation error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/ml-models/fallback', methods=['POST'])
def fallback_ml_models():
    """Fallback to previous model version"""
    try:
        # Get current live and fallback sessions
        live_session = execute_query("""
            SELECT id, file_names FROM model_upload_sessions
            WHERE is_live = TRUE AND session_type = 'models'
            LIMIT 1
        """, fetch_one=True)

        fallback_session = execute_query("""
            SELECT id, file_names FROM model_upload_sessions
            WHERE is_fallback = TRUE AND session_type = 'models'
            ORDER BY created_at DESC LIMIT 1
        """, fetch_one=True)

        if not fallback_session:
            return jsonify({'error': 'No fallback version available'}), 404

        # Swap live and fallback
        if live_session:
            execute_query("""
                UPDATE model_upload_sessions
                SET is_live = FALSE, is_fallback = FALSE, status = 'archived'
                WHERE id = %s
            """, (live_session['id'],))

        execute_query("""
            UPDATE model_upload_sessions
            SET is_live = TRUE, is_fallback = FALSE, status = 'active', activated_at = NOW()
            WHERE id = %s
        """, (fallback_session['id'],))

        logger.info(f"✓ Rolled back to fallback session: {fallback_session['id']}")

        # Reload decision engine
        success = decision_engine_manager.load_engine()

        if success:
            log_system_event('ml_models_rollback', 'warning',
                           f'Rolled back to previous model version: {fallback_session["id"]}')

            # Schedule backend restart
            restart_backend(delay_seconds=3)

            return jsonify({
                'success': True,
                'message': 'Rolled back to previous model version. Backend will restart in 3 seconds.',
                'fallbackSessionId': fallback_session['id'],
                'restarting': True
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to load fallback models'
            }), 500

    except Exception as e:
        logger.error(f"Model fallback error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/ml-models/sessions', methods=['GET'])
def get_model_sessions():
    """Get model upload session history"""
    try:
        sessions = execute_query("""
            SELECT
                id, session_type, status, is_live, is_fallback,
                file_count, file_names, total_size_bytes,
                created_at, activated_at
            FROM model_upload_sessions
            WHERE session_type = 'models'
            ORDER BY created_at DESC
            LIMIT 10
        """, fetch=True)

        result = [{
            'id': s['id'],
            'status': s['status'],
            'isLive': bool(s['is_live']),
            'isFallback': bool(s['is_fallback']),
            'fileCount': s['file_count'],
            'files': json.loads(s['file_names']) if s.get('file_names') else [],
            'totalSize': s['total_size_bytes'],
            'createdAt': s['created_at'].isoformat() if s.get('created_at') else None,
            'activatedAt': s['activated_at'].isoformat() if s.get('activated_at') else None
        } for s in (sessions or [])]

        return jsonify(result)

    except Exception as e:
        logger.error(f"Get model sessions error: {e}")
        return jsonify({'error': str(e)}), 500

# ==============================================================================
# BACKGROUND JOBS
# ==============================================================================

def snapshot_clients_daily():
    """
    Take daily snapshot of client counts for growth analytics.

    This job runs daily at 12:05 AM to capture client growth metrics.
    It calculates:
    - total_clients: Total number of clients
    - new_clients_today: New clients since yesterday
    - active_clients: Currently active clients (same as total for now)
    """
    try:
        logger.info("Taking daily client snapshot...")

        # Get current counts (all clients, no is_active filter)
        today_count = execute_query(
            "SELECT COUNT(*) as cnt FROM clients",
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

def initialize_client_growth_data():
    """
    Initialize client growth data with historical backfill.

    Called at backend startup if clients_daily_snapshot table is empty.
    Creates 30 days of historical data based on current client count.
    """
    try:
        # Check if table has data
        existing = execute_query("""
            SELECT COUNT(*) as cnt FROM clients_daily_snapshot
        """, fetch_one=True)

        if existing and existing['cnt'] > 0:
            # Table already has data, skip initialization
            return

        logger.info("Initializing client growth data (empty table detected)...")

        # Get current client count
        current_count = execute_query(
            "SELECT COUNT(*) as cnt FROM clients",
            fetch_one=True
        )
        total_clients = current_count['cnt'] if current_count else 0

        if total_clients == 0:
            logger.info("No clients exist yet, skipping growth data initialization")
            return

        # Create 30 days of backfilled data
        # Simulate gradual growth: start from total_clients and work backwards
        for days_ago in range(30, -1, -1):
            # Calculate date
            snapshot_date = f"DATE_SUB(CURDATE(), INTERVAL {days_ago} DAY)"

            # Simulate client count (gradually decrease as we go back in time)
            # This is a rough estimate - adjust as needed
            simulated_count = max(1, total_clients - (days_ago * (total_clients // 60)))
            new_today = 1 if days_ago < 30 else simulated_count

            execute_query(f"""
                INSERT INTO clients_daily_snapshot
                (snapshot_date, total_clients, new_clients_today, active_clients)
                VALUES ({snapshot_date}, %s, %s, %s)
            """, (simulated_count, new_today, simulated_count))

        logger.info(f"✓ Initialized 30 days of growth data (current: {total_clients} clients)")

    except Exception as e:
        logger.error(f"Initialize growth data error: {e}")

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
            SELECT id, client_id, instance_id, hostname, last_heartbeat_at
            FROM agents
            WHERE status = 'online'
            AND last_heartbeat_at < DATE_SUB(NOW(), INTERVAL {timeout} SECOND)
        """, fetch=True)

        for agent in (stale_agents or []):
            execute_query("""
                UPDATE agents SET status = 'offline' WHERE id = %s
            """, (agent['id'],))

            # Create notification for client
            create_notification(
                f"Agent {agent['hostname'] or agent['id']} marked offline (heartbeat timeout)",
                'warning',
                agent['client_id']
            )

            # Log system event for tracking
            log_system_event(
                'agent_marked_offline',
                'warning',
                f"Agent {agent['hostname'] or agent['id']} marked offline due to heartbeat timeout ({timeout}s)",
                agent['client_id'],
                agent['id'],
                agent['instance_id'],
                metadata={
                    'timeout_seconds': timeout,
                    'last_heartbeat_at': agent['last_heartbeat_at'].isoformat() if agent['last_heartbeat_at'] else None
                }
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
    logger.info("AWS Spot Optimizer - Central Server v4.2")
    logger.info("="*80)

    # Create necessary directories
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    config.DECISION_ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"✓ Ensured directories exist: {config.MODEL_DIR}, {config.DECISION_ENGINE_DIR}")

    # Initialize database
    init_db_pool()

    # Initialize replica coordinator (defined later in file at line 4639)
    global replica_coordinator
    try:
        replica_coordinator = ReplicaCoordinator()
        logger.info("✓ Replica coordinator initialized")
    except Exception as e:
        logger.error(f"Failed to initialize replica coordinator: {e}")
        replica_coordinator = None

    # Load decision engine
    decision_engine_manager.load_engine()

    # Initialize client growth data if empty
    try:
        initialize_client_growth_data()
    except Exception as e:
        logger.error(f"Failed to initialize client growth data: {e}")

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

    # Start replica coordinator
    if replica_coordinator is not None:
        try:
            replica_coordinator.start()
            logger.info("✓ Replica coordinator started (monitoring emergency & manual replicas)")
        except Exception as e:
            logger.error(f"Failed to start replica coordinator: {e}")
    else:
        logger.warning("⚠ Replica coordinator not available")

    logger.info("="*80)
    logger.info(f"Server initialized successfully")
    logger.info(f"Decision Engine: {decision_engine_manager.engine_type or 'None'}")
    logger.info(f"Models Loaded: {decision_engine_manager.models_loaded}")
    logger.info(f"Listening on {config.HOST}:{config.PORT}")
    logger.info("="*80)

# Replica management endpoints and app initialization happen at end of file
# after all functions are defined (see bottom of file)

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG
    )
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

# execute_query is defined in this file at line 4566

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
"""
Database utilities for Spot Optimizer backend
Shared database connection pooling and query execution
"""

import os
import logging
from typing import Any
import mysql.connector
from mysql.connector import Error, pooling

logger = logging.getLogger(__name__)

# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================

class DatabaseConfig:
    """Database configuration with environment variable support"""
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'spotuser')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'SpotUser2024!')
    DB_NAME = os.getenv('DB_NAME', 'spot_optimizer')
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 50))  # Increased from 30 to 50 for better concurrency
    DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', 20))  # Allow 20 additional connections beyond pool_size
    DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', 3600))  # Recycle connections after 1 hour

db_config = DatabaseConfig()

# ==============================================================================
# DATABASE CONNECTION POOLING
# ==============================================================================

connection_pool = None

def init_db_pool():
    """Initialize database connection pool with overflow support"""
    global connection_pool
    try:
        logger.info(f"Initializing database pool: {db_config.DB_USER}@{db_config.DB_HOST}:{db_config.DB_PORT}/{db_config.DB_NAME}")
        logger.info(f"Pool config: size={db_config.DB_POOL_SIZE}, max_overflow={db_config.DB_MAX_OVERFLOW}, recycle={db_config.DB_POOL_RECYCLE}s")
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="spot_optimizer_pool",
            pool_size=db_config.DB_POOL_SIZE,
            pool_reset_session=True,
            host=db_config.DB_HOST,
            port=db_config.DB_PORT,
            user=db_config.DB_USER,
            password=db_config.DB_PASSWORD,
            database=db_config.DB_NAME,
            autocommit=False
        )

        # Test the connection
        test_conn = connection_pool.get_connection()
        test_conn.close()

        logger.info(f"✓ Database connection pool initialized (size: {db_config.DB_POOL_SIZE})")
        return True
    except Error as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        logger.error(f"Connection details: {db_config.DB_USER}@{db_config.DB_HOST}:{db_config.DB_PORT}/{db_config.DB_NAME}")
        return False

def get_db_connection():
    """Get connection from pool"""
    global connection_pool

    # Initialize pool if not already done
    if connection_pool is None:
        init_db_pool()

    try:
        return connection_pool.get_connection()
    except Error as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise

def execute_query(query: str, params: tuple = None, fetch: bool = False,
                 fetch_one: bool = False, commit: bool = True) -> Any:
    """
    Execute database query with error handling

    Args:
        query: SQL query string
        params: Query parameters (tuple)
        fetch: Whether to fetch all results
        fetch_one: Whether to fetch single result
        commit: Whether to commit transaction

    Returns:
        Query results or affected row count
    """
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
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
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

# execute_query is defined in this file at line 4566

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
                # Get all active agents (exclude deleted)
                agents = execute_query("""
                    SELECT id, client_id, instance_id, auto_switch_enabled,
                           manual_replica_enabled, replica_count, current_replica_id,
                           last_interruption_signal, last_heartbeat_at
                    FROM agents
                    WHERE enabled = TRUE AND status = 'online' AND status != 'deleted'
                """, fetch=True)

                for agent in (agents or []):
                    agent_id = agent['id']

                    # Handle auto-switch mode (emergency)
                    if agent['auto_switch_enabled']:
                        self._handle_auto_switch_mode(agent)

                    # Handle manual replica mode
                    elif agent['manual_replica_enabled']:
                        self._handle_manual_replica_mode(agent)

                time.sleep(2)  # Check every 2 seconds for more reactive behavior

            except Exception as e:
                logger.error(f"Monitor loop error: {e}", exc_info=True)
                time.sleep(5)  # Shorter retry delay for faster recovery

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

        # Get instance details from PRIMARY instance only
        instance = execute_query("""
            SELECT instance_type, region, current_pool_id, id as instance_id
            FROM instances
            WHERE agent_id = %s
              AND is_active = TRUE
              AND is_primary = TRUE
              AND instance_status = 'running_primary'
            ORDER BY created_at DESC
            LIMIT 1
        """, (agent_id,), fetch_one=True)

        if not instance:
            logger.error(f"Cannot create replica - no active primary instance for agent {agent_id}")
            return None

        logger.info(f"Creating emergency replica for agent {agent_id}: instance_type={instance['instance_type']}, region={instance['region']}")

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

        # Promote replica using its actual EC2 instance_id
        # Get replica's actual instance_id
        replica_instance = execute_query("""
            SELECT instance_id, instance_type, region, hourly_cost
            FROM replica_instances
            WHERE id = %s
        """, (replica_id,), fetch_one=True)

        if not replica_instance or not replica_instance['instance_id']:
            logger.error(f"Replica {replica_id} missing instance_id - cannot complete failover")
            return False

        new_instance_id = replica_instance['instance_id']  # Use actual EC2 instance ID

        # Get on-demand price
        ondemand_price_result = execute_query("""
            SELECT price FROM ondemand_prices
            WHERE instance_type = %s AND region = %s
            LIMIT 1
        """, (replica_instance['instance_type'], replica_instance['region']), fetch_one=True)

        ondemand_price = ondemand_price_result['price'] if ondemand_price_result else 0.0416

        execute_query("""
            INSERT INTO instances (
                id, client_id, instance_type, region, az,
                current_pool_id, current_mode, spot_price, ondemand_price, baseline_ondemand_price,
                is_active, installed_at
            )
            SELECT
                %s, a.client_id, ri.instance_type, ri.region, ri.az,
                ri.pool_id, 'spot', ri.hourly_cost, %s, %s, TRUE, NOW()
            FROM replica_instances ri
            JOIN agents a ON ri.agent_id = a.id
            WHERE ri.id = %s
            ON DUPLICATE KEY UPDATE
                is_active = TRUE,
                current_mode = 'spot',
                current_pool_id = VALUES(current_pool_id),
                spot_price = VALUES(spot_price)
        """, (new_instance_id, ondemand_price, ondemand_price, replica_id))

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

        # Check for active replicas (including launching status to prevent duplicates)
        active_replicas = execute_query("""
            SELECT id, status FROM replica_instances
            WHERE agent_id = %s
              AND is_active = TRUE
              AND status NOT IN ('terminated', 'promoted', 'failed')
        """, (agent_id,), fetch=True)

        active_count = len(active_replicas or [])

        if active_count == 0:
            # No active replica - create one
            logger.info(f"Manual mode: Creating replica for agent {agent_id}")
            self._create_manual_replica(agent)
        elif active_count == 1:
            # Exactly one replica - this is correct, do nothing
            replica = active_replicas[0]
            logger.debug(f"Manual mode: Agent {agent_id} has 1 replica (status: {replica['status']})")

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

        if recently_promoted and active_count == 0:
            # User just promoted a replica AND there's no replacement yet - create new one
            logger.info(f"Manual mode: Replica promoted for agent {agent_id}, creating new replica")
            time.sleep(2)  # Brief delay to let promotion complete
            self._create_manual_replica(agent)

    def _create_manual_replica(self, agent: Dict):
        """Create manual replica in cheapest available pool"""
        agent_id = agent['id']

        # Double-check manual replica is still enabled (prevent race conditions)
        agent_check = execute_query("""
            SELECT manual_replica_enabled FROM agents WHERE id = %s
        """, (agent_id,), fetch_one=True)

        if not agent_check or not agent_check['manual_replica_enabled']:
            logger.info(f"Manual replica disabled for agent {agent_id} - skipping creation")
            return None

        # Get instance details from PRIMARY instance only
        instance = execute_query("""
            SELECT instance_type, region, current_pool_id, id as instance_id
            FROM instances
            WHERE agent_id = %s
              AND is_active = TRUE
              AND is_primary = TRUE
              AND instance_status = 'running_primary'
            ORDER BY created_at DESC
            LIMIT 1
        """, (agent_id,), fetch_one=True)

        if not instance:
            logger.error(f"Cannot create manual replica - no active primary instance for agent {agent_id}")
            return None

        logger.info(f"Creating manual replica for agent {agent_id}: instance_type={instance['instance_type']}, region={instance['region']}, instance_id={instance['instance_id']}")

        # Find cheapest pool (different from current) using real-time pricing
        pools = execute_query("""
            SELECT sp.id, sp.az, COALESCE(sps.price, 0.05) as spot_price
            FROM spot_pools sp
            LEFT JOIN (
                SELECT pool_id, price,
                       ROW_NUMBER() OVER (PARTITION BY pool_id ORDER BY captured_at DESC) as rn
                FROM spot_price_snapshots
                WHERE captured_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            ) sps ON sps.pool_id = sp.id AND sps.rn = 1
            WHERE sp.instance_type = %s
              AND sp.region = %s
            ORDER BY COALESCE(sps.price, 999999) ASC
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
# execute_query is defined in this file at line 4566

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

            # Check current replica count - manual mode maintains exactly 1 replica
            if agent.get('replica_count', 0) >= 1:
                return jsonify({
                    'error': 'Replica already exists for this agent',
                    'current_count': agent['replica_count'],
                    'max_allowed': 1,
                    'note': 'Manual replica mode maintains exactly 1 replica. Delete existing replica first.'
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
            status_filter = request.args.get('status')  # Filter by status if provided

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
            params = [agent_id]

            if not include_terminated:
                query += " AND ri.is_active = TRUE"

            # Filter by status if provided (used by agent to get pending replicas)
            if status_filter:
                query += " AND ri.status = %s"
                params.append(status_filter)

            query += " ORDER BY ri.created_at DESC"

            replicas = execute_query(query, tuple(params), fetch=True)

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
            demote_old_primary = data.get('demote_old_primary', False)  # Default to FALSE - mark as zombie
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

            # Step 2: Create new instance record for the replica using its actual EC2 instance_id
            # Get replica's actual instance_id first
            replica_instance = execute_query("""
                SELECT instance_id, instance_type, region, hourly_cost
                FROM replica_instances
                WHERE id = %s
            """, (replica_id,), fetch_one=True)

            if not replica_instance or not replica_instance['instance_id']:
                return jsonify({'error': 'Replica instance_id not found'}), 404

            new_instance_id = replica_instance['instance_id']  # Use actual EC2 instance ID

            # Get on-demand price for this instance type
            ondemand_price_result = execute_query("""
                SELECT price FROM ondemand_prices
                WHERE instance_type = %s AND region = %s
                LIMIT 1
            """, (replica_instance['instance_type'], replica_instance['region']), fetch_one=True)

            ondemand_price = ondemand_price_result['price'] if ondemand_price_result else 0.0416

            execute_query("""
                INSERT INTO instances (
                    id, client_id, instance_type, region, az,
                    current_pool_id, current_mode, spot_price, ondemand_price, baseline_ondemand_price,
                    is_active, instance_status, is_primary, installed_at
                )
                SELECT
                    %s, a.client_id, ri.instance_type, ri.region, ri.az,
                    ri.pool_id, 'spot', ri.hourly_cost, %s, %s,
                    TRUE, 'running_primary', TRUE, NOW()
                FROM replica_instances ri
                JOIN agents a ON ri.agent_id = a.id
                WHERE ri.id = %s
                ON DUPLICATE KEY UPDATE
                    is_active = TRUE,
                    current_mode = 'spot',
                    current_pool_id = VALUES(current_pool_id),
                    spot_price = VALUES(spot_price),
                    instance_status = 'running_primary',
                    is_primary = TRUE
            """, (new_instance_id, ondemand_price, ondemand_price, replica_id))

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
                # Mark old primary as replica
                execute_query("""
                    UPDATE instances
                    SET instance_status = 'running_replica',
                        is_primary = FALSE
                    WHERE id = %s
                """, (old_instance_id,))
                logger.info(f"✓ Old primary {old_instance_id} demoted to replica for agent {agent_id}")
            else:
                # Mark old instance as zombie (will be terminated)
                execute_query("""
                    UPDATE instances
                    SET instance_status = 'zombie',
                        is_primary = FALSE,
                        is_active = FALSE
                    WHERE id = %s
                """, (old_instance_id,))
                logger.info(f"✓ Old primary {old_instance_id} marked as ZOMBIE for agent {agent_id}")

            # Log to system_events table
            execute_query("""
                INSERT INTO system_events (event_type, severity, agent_id, instance_id, message, metadata)
                VALUES ('replica_promoted', 'info', %s, %s, %s, %s)
            """, (agent_id, new_instance_id,
                  f"Replica {replica_id} promoted to primary, old primary {'demoted to replica' if demote_old_primary else 'marked as zombie'}",
                  json.dumps({'replica_id': replica_id, 'old_instance_id': old_instance_id, 'demoted': demote_old_primary})))

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

            # Mark as terminated in replica_instances table
            execute_query("""
                UPDATE replica_instances
                SET status = 'terminated',
                    is_active = FALSE,
                    terminated_at = NOW()
                WHERE id = %s
            """, (replica_id,))
            logger.info(f"✓ Marked replica {replica_id} as TERMINATED in replica_instances table")

            # Also mark in instances table if exists
            if replica.get('instance_id'):
                execute_query("""
                    UPDATE instances
                    SET instance_status = 'terminated',
                        is_active = FALSE,
                        terminated_at = NOW()
                    WHERE id = %s
                """, (replica['instance_id'],))
                logger.info(f"✓ Marked instance {replica['instance_id']} as TERMINATED in instances table")

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
            logger.info(f"✓ Decremented replica count for agent {agent_id}")

            # Log to system_events table
            execute_query("""
                INSERT INTO system_events (event_type, severity, agent_id, message, metadata)
                VALUES ('replica_terminated', 'info', %s, %s, %s)
            """, (agent_id,
                  f"Manual replica {replica_id} terminated",
                  json.dumps({'replica_id': replica_id, 'instance_id': replica.get('instance_id'), 'status': replica.get('status')})))

            logger.info(f"✓ Deleted replica {replica_id} for agent {agent_id}")

            return jsonify({
                'success': True,
                'message': 'Replica terminated',
                'replica_id': replica_id,
                'terminated_at': datetime.now().isoformat()
            }), 200

        except Exception as e:
            logger.error(f"Error deleting replica: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def update_replica_instance(app):
    """PUT /api/agents/<agent_id>/replicas/<replica_id> - Update replica with EC2 instance ID"""
    @app.route('/api/agents/<agent_id>/replicas/<replica_id>', methods=['PUT'])
    def update_replica_instance_endpoint(agent_id, replica_id):
        """
        Update replica with actual EC2 instance ID after launch.
        Called by agent after launching EC2 instance.

        Request body:
        {
            "instance_id": "i-1234567890abcdef0",
            "status": "syncing"  # optional, defaults to 'syncing'
        }
        """
        try:
            data = request.get_json() or {}
            instance_id = data.get('instance_id')
            status = data.get('status', 'syncing')

            if not instance_id:
                return jsonify({'error': 'instance_id is required'}), 400

            # Validate replica exists
            replica = execute_query("""
                SELECT * FROM replica_instances
                WHERE id = %s AND agent_id = %s
            """, (replica_id, agent_id), fetch=True)

            if not replica or len(replica) == 0:
                return jsonify({'error': 'Replica not found'}), 404

            # Update replica with instance ID
            execute_query("""
                UPDATE replica_instances
                SET instance_id = %s,
                    status = %s,
                    launched_at = CASE WHEN launched_at IS NULL THEN NOW() ELSE launched_at END
                WHERE id = %s
            """, (instance_id, status, replica_id))

            # Also register replica in instances table
            replica_data = replica[0] if replica else {}
            execute_query("""
                INSERT INTO instances (
                    id, client_id, agent_id, instance_type, region, az,
                    current_mode, current_pool_id, is_active, instance_status, is_primary,
                    installed_at
                ) VALUES (%s, (SELECT client_id FROM agents WHERE id = %s), %s, %s, %s, %s, 'spot', %s, TRUE, 'running_replica', FALSE, NOW())
                ON DUPLICATE KEY UPDATE
                    instance_status = 'running_replica',
                    is_primary = FALSE,
                    is_active = TRUE
            """, (
                instance_id, agent_id, agent_id,
                replica_data.get('instance_type'), replica_data.get('region'), replica_data.get('az'),
                replica_data.get('pool_id')
            ))

            logger.info(f"Updated replica {replica_id} with instance_id {instance_id}, status {status}")

            return jsonify({
                'success': True,
                'replica_id': replica_id,
                'instance_id': instance_id,
                'status': status
            }), 200

        except Exception as e:
            logger.error(f"Error updating replica instance: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500


def update_replica_status(app):
    """POST /api/agents/<agent_id>/replicas/<replica_id>/status - Update replica status"""
    @app.route('/api/agents/<agent_id>/replicas/<replica_id>/status', methods=['POST'])
    def update_replica_status_endpoint(agent_id, replica_id):
        """
        Update replica status and metadata.
        Called by agent during replica lifecycle.

        Request body:
        {
            "status": "launching" | "syncing" | "ready" | "failed",
            "sync_started_at": "2025-01-20T10:45:00Z",  # optional
            "sync_completed_at": "2025-01-20T10:46:00Z",  # optional
            "error_message": "Error details"  # optional, for failed status
        }
        """
        try:
            data = request.get_json() or {}
            status = data.get('status')

            if not status:
                return jsonify({'error': 'status is required'}), 400

            if status not in ('launching', 'syncing', 'ready', 'failed', 'terminated'):
                return jsonify({'error': 'Invalid status'}), 400

            # Validate replica exists
            replica = execute_query("""
                SELECT * FROM replica_instances
                WHERE id = %s AND agent_id = %s
            """, (replica_id, agent_id), fetch=True)

            if not replica or len(replica) == 0:
                return jsonify({'error': 'Replica not found'}), 404

            # Build update query dynamically based on provided fields
            updates = ["status = %s"]
            params = [status]

            if data.get('sync_started_at'):
                updates.append("sync_started_at = %s")
                params.append(data['sync_started_at'])

            if data.get('sync_completed_at'):
                updates.append("sync_completed_at = %s")
                params.append(data['sync_completed_at'])

            if data.get('error_message'):
                updates.append("error_message = %s")
                params.append(data['error_message'])

            # If status is ready, mark as ready_at
            if status == 'ready':
                updates.append("ready_at = CASE WHEN ready_at IS NULL THEN NOW() ELSE ready_at END")

            params.append(replica_id)

            query = f"""
                UPDATE replica_instances
                SET {', '.join(updates)}
                WHERE id = %s
            """

            execute_query(query, tuple(params))

            logger.info(f"Updated replica {replica_id} status to {status}")

            return jsonify({
                'success': True,
                'replica_id': replica_id,
                'status': status
            }), 200

        except Exception as e:
            logger.error(f"Error updating replica status: {e}", exc_info=True)
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

            # Collect ML training features
            now = datetime.utcnow()
            ml_features = _collect_interruption_ml_features(agent['current_pool_id'], agent_id, now)

            # Log interruption event with ML features
            execute_query("""
                INSERT INTO spot_interruption_events (
                    instance_id, agent_id, pool_id, signal_type,
                    detected_at, termination_time, response_action,
                    replica_id, instance_age_hours,
                    spot_price_at_interruption, price_trend_before, price_change_percent,
                    time_since_price_change_minutes, day_of_week, hour_of_day,
                    pool_historical_interruption_rate, region_interruption_rate,
                    competing_instances_count, previous_interruptions_count,
                    time_since_last_interruption_hours
                ) VALUES (
                    %s, %s, %s, %s, NOW(), %s, 'created-replica', %s,
                    TIMESTAMPDIFF(HOUR, %s, NOW()),
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                data.get('instance_id'),
                agent_id,
                agent['current_pool_id'],
                signal_type,
                data.get('termination_time'),
                replica_id,
                agent['instance_created_at'],
                ml_features.get('spot_price'),
                ml_features.get('price_trend'),
                ml_features.get('price_change_percent'),
                ml_features.get('time_since_price_change'),
                now.weekday(),  # 0=Monday in Python, convert if needed
                now.hour,
                ml_features.get('pool_interruption_rate'),
                ml_features.get('region_interruption_rate'),
                ml_features.get('competing_instances'),
                ml_features.get('previous_interruptions'),
                ml_features.get('hours_since_last_interruption')
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

            # Create new instance record for promoted replica using its actual EC2 instance_id
            # Get replica's actual instance_id
            replica_instance = execute_query("""
                SELECT instance_id, instance_type, region, hourly_cost
                FROM replica_instances
                WHERE id = %s
            """, (replica_id,), fetch_one=True)

            if not replica_instance or not replica_instance['instance_id']:
                logger.error(f"Replica {replica_id} missing instance_id - cannot complete failover")
                return jsonify({'error': 'Replica instance_id not found'}), 404

            new_instance_id = replica_instance['instance_id']  # Use actual EC2 instance ID

            # Get on-demand price
            ondemand_price_result = execute_query("""
                SELECT price FROM ondemand_prices
                WHERE instance_type = %s AND region = %s
                LIMIT 1
            """, (replica_instance['instance_type'], replica_instance['region']), fetch_one=True)

            ondemand_price = ondemand_price_result['price'] if ondemand_price_result else 0.0416

            execute_query("""
                INSERT INTO instances (
                    id, client_id, instance_type, region, az,
                    current_pool_id, current_mode, spot_price, ondemand_price, baseline_ondemand_price,
                    is_active, installed_at
                )
                SELECT
                    %s, a.client_id, ri.instance_type, ri.region, ri.az,
                    ri.pool_id, 'spot', ri.hourly_cost, %s, %s, TRUE, NOW()
                FROM replica_instances ri
                JOIN agents a ON ri.agent_id = a.id
                WHERE ri.id = %s
                ON DUPLICATE KEY UPDATE
                    is_active = TRUE,
                    current_mode = 'spot',
                    current_pool_id = VALUES(current_pool_id),
                    spot_price = VALUES(spot_price)
            """, (new_instance_id, ondemand_price, ondemand_price, replica_id))

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


def _collect_interruption_ml_features(pool_id: str, agent_id: str, now: datetime) -> dict:
    """
    Collect ML training features when an interruption occurs.
    These features help the model learn interruption patterns.
    """
    features = {}

    try:
        # Get current spot price
        current_price = execute_query("""
            SELECT spot_price, time_bucket
            FROM pricing_snapshots_clean
            WHERE pool_id = %s
            ORDER BY time_bucket DESC
            LIMIT 1
        """, (pool_id,), fetch=True)

        if current_price:
            features['spot_price'] = float(current_price[0]['spot_price'])

            # Get price history for trend analysis
            price_history = execute_query("""
                SELECT spot_price, time_bucket
                FROM pricing_snapshots_clean
                WHERE pool_id = %s
                AND time_bucket >= NOW() - INTERVAL 1 HOUR
                ORDER BY time_bucket ASC
            """, (pool_id,), fetch=True)

            if price_history and len(price_history) >= 2:
                prices = [float(p['spot_price']) for p in price_history]
                first_price = prices[0]
                last_price = prices[-1]

                # Calculate trend
                if last_price > first_price * 1.05:
                    features['price_trend'] = 'rising'
                elif last_price < first_price * 0.95:
                    features['price_trend'] = 'falling'
                else:
                    features['price_trend'] = 'stable'

                # Price change percentage
                if first_price > 0:
                    features['price_change_percent'] = ((last_price - first_price) / first_price) * 100

                # Time since last price change
                for i in range(len(prices) - 1, 0, -1):
                    if abs(prices[i] - prices[i-1]) / prices[i-1] > 0.01:  # 1% change
                        time_diff = now - price_history[i]['time_bucket']
                        features['time_since_price_change'] = int(time_diff.total_seconds() / 60)
                        break

        # Get pool historical interruption rate
        pool_stats = execute_query("""
            SELECT
                COUNT(*) as interruption_count,
                DATEDIFF(NOW(), MIN(detected_at)) as days_tracked
            FROM spot_interruption_events
            WHERE pool_id = %s
        """, (pool_id,), fetch=True)

        if pool_stats and pool_stats[0]['days_tracked'] > 0:
            count = pool_stats[0]['interruption_count']
            days = pool_stats[0]['days_tracked']
            features['pool_interruption_rate'] = count / max(days, 1)

        # Get region interruption rate
        region_stats = execute_query("""
            SELECT p.region, COUNT(sie.id) as interruptions
            FROM spot_pools p
            LEFT JOIN spot_interruption_events sie ON p.id = sie.pool_id
            WHERE p.id = %s
            GROUP BY p.region
        """, (pool_id,), fetch=True)

        if region_stats:
            features['region_interruption_rate'] = region_stats[0]['interruptions'] / 30.0  # Normalize to per-month

        # Count competing instances in same pool
        competing = execute_query("""
            SELECT COUNT(*) as count
            FROM agents
            WHERE current_pool_id = %s
            AND is_active = TRUE
        """, (pool_id,), fetch=True)

        if competing:
            features['competing_instances'] = competing[0]['count']

        # Get agent's previous interruption count
        prev_interruptions = execute_query("""
            SELECT COUNT(*) as count
            FROM spot_interruption_events
            WHERE agent_id = %s
        """, (agent_id,), fetch=True)

        if prev_interruptions:
            features['previous_interruptions'] = prev_interruptions[0]['count']

        # Time since last interruption for this agent
        last_interruption = execute_query("""
            SELECT detected_at
            FROM spot_interruption_events
            WHERE agent_id = %s
            ORDER BY detected_at DESC
            LIMIT 1
        """, (agent_id,), fetch=True)

        if last_interruption:
            time_diff = now - last_interruption[0]['detected_at']
            features['hours_since_last_interruption'] = time_diff.total_seconds() / 3600

    except Exception as e:
        logger.warning(f"Error collecting ML features for interruption: {e}")
        # Return partial features if some calculations failed

    return features


# ============================================================================
# REGISTER ALL ENDPOINTS
# ============================================================================

def register_replica_management_endpoints(app):
    """Register all replica management endpoints with Flask app"""
    create_manual_replica(app)
    list_replicas(app)
    promote_replica(app)
    delete_replica(app)
    update_replica_instance(app)  # PUT /api/agents/<agent_id>/replicas/<replica_id>
    update_replica_status(app)    # POST /api/agents/<agent_id>/replicas/<replica_id>/status
    create_emergency_replica(app)
    handle_termination_imminent(app)
    update_replica_sync_status(app)

    logger.info("Replica management endpoints registered")


# ============================================================================
# INITIALIZE REPLICA MANAGEMENT ENDPOINTS
# ============================================================================

# Call after all functions are defined
register_replica_management_endpoints(app)
logger.info("✓ All replica management endpoints registered")


# ============================================================================
# INITIALIZE APPLICATION
# ============================================================================

# Initialize app after all functions are defined
# This ensures init_db_pool(), ReplicaCoordinator, etc. are available
initialize_app()
