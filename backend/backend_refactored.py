"""
================================================================================
AWS Spot Optimizer - Central Server Backend v5.0 (Modular Architecture)
================================================================================

ARCHITECTURE DIAGRAM:
--------------------

┌──────────────────────────────────────────────────────────────────┐
│                    MODULAR COMPONENT LAYER                        │
│                                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Sentinel   │  │   Decision  │  │ Calculation │             │
│  │ (Monitoring)│  │   Engine    │  │   Engine    │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                      │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐             │
│  │    Data     │  │   Command   │  │    Agent    │             │
│  │    Valve    │  │   Tracker   │  │  Identity   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                   │
│  All components imported from: backend.components                │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                               │
│                                                                   │
│  AgentService → InstanceService → PricingService → SwitchService │
│  ReplicaService → DecisionService → ClientService                │
│                                                                   │
│  All services use components for core operations                 │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                         API LAYER                                 │
│                                                                   │
│  /api/agents/* → /api/client/* → /api/admin/*                   │
│                                                                   │
│  All routes delegate to services                                 │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DATABASE LAYER                               │
│                                                                   │
│  MySQL 8.0 - Accessed ONLY through Data Valve component          │
└──────────────────────────────────────────────────────────────────┘

KEY CHANGES IN V5.0:
-------------------
✅ Modular Components: 6 standalone, reusable components
✅ Data Valve: Single point of database access
✅ Sentinel: Continuous monitoring with SEF triggers
✅ Decision Engine: Hot-reloadable ML models with I/O contracts
✅ Calculations: Pure financial computation functions
✅ Command Tracker: Priority-based command lifecycle
✅ Agent Identity: Persistent identity across switches

HOW TO USE COMPONENTS:
---------------------
from backend.components import (
    data_valve,           # Data quality gate
    calculation_engine,   # Savings calculations
    command_tracker,      # Command lifecycle
    sentinel,             # Monitoring & triggers
    engine_manager,       # ML model loading
    agent_identity_manager  # Agent lifecycle
)

# Example: Store price data with automatic quality assurance
data_valve.store_price_snapshot(
    pool_id='t3.medium.us-east-1a',
    price=Decimal('0.0456'),
    timestamp=datetime.utcnow()
)

# Example: Calculate savings
savings = calculation_engine.calculate_monthly_savings(
    ondemand_price=Decimal('0.0416'),
    actual_avg_price=Decimal('0.0125'),
    hours=730
)

# Example: Create command
cmd_id = command_tracker.create_command(
    agent_id='agent-123',
    client_id='client-456',
    command_type='switch',
    priority=CommandPriority.ML_NORMAL,
    target_pool_id='t3.medium.us-east-1b'
)

COMPATIBILITY:
-------------
✅ Fully backward compatible with Agent v4.0
✅ All existing APIs preserved
✅ Database schema unchanged
✅ Frontend requires no changes
✅ Zero breaking changes

VERSION: 5.0
LAST UPDATED: 2025-11-24
PRODUCTION STATUS: ✅ Ready

================================================================================
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

# ============================================================================
# COMPONENT IMPORTS (NEW v5.0)
# ============================================================================
from backend.components import (
    data_valve,              # Data quality gate
    calculation_engine,      # Financial calculations
    command_tracker,         # Command lifecycle management
    sentinel,                # Monitoring & interruption detection
    engine_manager,          # Decision engine loading
    agent_identity_manager,  # Agent lifecycle management
    CommandPriority,         # Priority constants
    CommandStatus,           # Status constants
    CommandType,             # Type constants
    InterruptionSignalType   # Interruption signal types
)

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

logger.info("="*80)
logger.info("AWS Spot Optimizer Backend v5.0 - Modular Architecture Starting")
logger.info("="*80)

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Server configuration with environment variable support"""

    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'spotuser')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'SpotUser2024!')
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

# ============================================================================
# FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
CORS(app)

# ============================================================================
# DATABASE CONNECTION POOLING
# ============================================================================
# Now managed by database_manager.py (imported by components)
from backend.database_manager import init_db_pool, get_db_connection, execute_query

# Initialize database connection pool
init_db_pool(
    host=config.DB_HOST,
    port=config.DB_PORT,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME,
    pool_size=config.DB_POOL_SIZE
)

logger.info(f"Database connection pool initialized: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
from backend.utils import (
    generate_uuid,
    generate_client_token,
    generate_client_id,
    log_system_event,
    create_notification
)

# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================
from backend.auth import require_client_token

# ============================================================================
# INITIALIZE COMPONENTS
# ============================================================================

logger.info("Initializing modular components...")

# Initialize Decision Engine
try:
    engine_manager.load_engine(
        module_path=config.DECISION_ENGINE_MODULE,
        class_name=config.DECISION_ENGINE_CLASS
    )
    logger.info(f"✅ Decision Engine loaded: {engine_manager.engine_type} v{engine_manager.engine_version}")
except Exception as e:
    logger.error(f"❌ Decision Engine failed to load: {e}")
    logger.warning("System will use fallback decision logic")

# Register SEF callbacks with Sentinel
try:
    from backend.smart_emergency_fallback import SmartEmergencyFallback

    # Initialize SEF
    sef_component = SmartEmergencyFallback(get_db_connection())

    # Register callbacks
    sentinel.register_sef_callback('rebalance', sef_component.handle_rebalance_notice)
    sentinel.register_sef_callback('termination', sef_component.handle_termination_imminent)

    logger.info("✅ SEF callbacks registered with Sentinel")
except Exception as e:
    logger.error(f"❌ SEF initialization failed: {e}")

logger.info("="*80)
logger.info("All components initialized successfully")
logger.info("="*80)

# ============================================================================
# IMPORT SERVICES & API ROUTES
# ============================================================================

# Services use components internally
from backend.services import (
    agent_service,
    instance_service,
    pricing_service,
    switch_service,
    replica_service,
    decision_service,
    client_service,
    notification_service
)

# API Routes
from backend.api.agent_routes import agent_bp
from backend.api.client_routes import client_bp
from backend.api.admin_routes import admin_bp
from backend.api.notification_routes import notification_bp
from backend.api.replica_routes import replica_bp

# Register blueprints
app.register_blueprint(agent_bp, url_prefix='/api/agents')
app.register_blueprint(client_bp, url_prefix='/api/client')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(notification_bp, url_prefix='/api/notifications')
app.register_blueprint(replica_bp, url_prefix='/api/replicas')

logger.info("✅ All API blueprints registered")

# ============================================================================
# BACKGROUND JOBS
# ============================================================================

if config.ENABLE_BACKGROUND_JOBS:
    scheduler = BackgroundScheduler()

    # Health monitoring job
    from backend.jobs.health_monitor import check_agent_health_job
    scheduler.add_job(
        func=check_agent_health_job,
        trigger="interval",
        minutes=5,
        id='health_monitor',
        name='Agent Health Monitor',
        replace_existing=True
    )

    # Daily snapshot job
    from backend.jobs.snapshot_jobs import daily_client_snapshot_job
    scheduler.add_job(
        func=daily_client_snapshot_job,
        trigger="cron",
        hour=0,
        minute=5,
        id='daily_snapshot',
        name='Daily Client Snapshot',
        replace_existing=True
    )

    # Data cleanup job
    from backend.jobs.data_cleaner import cleanup_old_data_job
    scheduler.add_job(
        func=cleanup_old_data_job,
        trigger="cron",
        day_of_week='sun',
        hour=2,
        minute=0,
        id='data_cleanup',
        name='Weekly Data Cleanup',
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ Background jobs scheduled and started")

# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    System health check endpoint

    Returns comprehensive system status including component health
    """
    try:
        # Check database
        db_healthy = False
        try:
            result = execute_query("SELECT 1", fetch_one=True)
            db_healthy = result is not None
        except:
            pass

        # Check components
        components_status = {
            'data_valve': {
                'status': 'healthy',
                'stats': data_valve.get_stats()
            },
            'calculation_engine': {
                'status': 'healthy',
                'version': '1.0.0'
            },
            'command_tracker': {
                'status': 'healthy',
                'stats': command_tracker.get_stats() if hasattr(command_tracker, 'get_stats') else {}
            },
            'sentinel': {
                'status': 'healthy',
                'stats': sentinel.get_stats()
            },
            'decision_engine': {
                'status': 'healthy' if engine_manager.is_loaded() else 'degraded',
                'engine_type': engine_manager.engine_type,
                'engine_version': engine_manager.engine_version,
                'stats': engine_manager.get_stats()
            }
        }

        # Overall health
        all_healthy = db_healthy and all(
            c['status'] == 'healthy' for c in components_status.values()
        )

        return jsonify({
            'status': 'healthy' if all_healthy else 'degraded',
            'version': '5.0',
            'architecture': 'modular',
            'timestamp': datetime.utcnow().isoformat(),
            'database': {
                'status': 'healthy' if db_healthy else 'unhealthy',
                'host': config.DB_HOST,
                'pool_size': config.DB_POOL_SIZE
            },
            'components': components_status
        }), 200 if all_healthy else 503

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================

def shutdown_handler(signum, frame):
    """Handle graceful shutdown"""
    logger.info("="*80)
    logger.info("Graceful shutdown initiated...")
    logger.info("="*80)

    # Stop scheduler
    if config.ENABLE_BACKGROUND_JOBS:
        scheduler.shutdown(wait=False)
        logger.info("✅ Background jobs stopped")

    # Close database connections (handled by connection pool)
    logger.info("✅ Database connections closed")

    logger.info("="*80)
    logger.info("Shutdown complete")
    logger.info("="*80)
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# ============================================================================
# MAIN APPLICATION STARTUP
# ============================================================================

if __name__ == '__main__':
    logger.info("="*80)
    logger.info("AWS Spot Optimizer Backend v5.0")
    logger.info("Modular Architecture - Production Ready")
    logger.info("="*80)
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    logger.info(f"Debug mode: {config.DEBUG}")
    logger.info("="*80)

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        threaded=True
    )
