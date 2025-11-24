"""
AWS Spot Optimizer - Production Backend Application
====================================================
Complete modular architecture with all 63 endpoints migrated

Architecture:
- api/: 5 route blueprints (agent, replica, client, admin, notification)
- services/: 9 service modules (business logic layer)
- jobs/: 4 background job modules
- Centralized config, database, auth, and utilities

Migration Status: 100% COMPLETE
- Agent Core: 14/14 endpoints ✓
- Replica Management: 9/9 endpoints ✓
- Client Features: 23/23 endpoints ✓
- Admin Operations: 14/14 endpoints ✓
- Notifications: 3/3 endpoints ✓
- Background Jobs: 4/4 jobs ✓

Total: 63/63 endpoints (100% complete)
"""

import logging
import os
import signal
import sys
from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import config
from backend.database_manager import init_db_pool
from backend.decision_engine_manager import decision_engine_manager

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
# FLASK APP INITIALIZATION
# ==============================================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
CORS(app)

# ==============================================================================
# DATABASE INITIALIZATION
# ==============================================================================

logger.info("Initializing database connection pool...")
if init_db_pool():
    logger.info("✓ Database connection pool ready")
else:
    logger.error("✗ Failed to initialize database pool")
    # Continue anyway - connection will retry on first query

# ==============================================================================
# DECISION ENGINE INITIALIZATION
# ==============================================================================

logger.info("Loading decision engine...")
if decision_engine_manager.load_engine():
    logger.info("✓ Decision engine loaded")
else:
    logger.warning("⚠ Decision engine not loaded - using safe defaults")

# ==============================================================================
# REGISTER BLUEPRINTS
# ==============================================================================

logger.info("Registering API blueprints...")

# Agent Routes (Priority 1 - Agent Core)
from backend.api.agent_routes import agent_bp
app.register_blueprint(agent_bp)
logger.info("✓ Registered agent routes: /api/agents")

# Replica Routes (Priority 2 - Replica Management)
from backend.api.replica_routes import replica_bp
app.register_blueprint(replica_bp)
logger.info("✓ Registered replica routes: /api/agents (replica endpoints)")

# Client Routes (Priority 3 - Client Features)
from backend.api.client_routes import client_bp
app.register_blueprint(client_bp)
logger.info("✓ Registered client routes: /api/client")

# Admin Routes (Priority 4 - Admin Operations)
from backend.api.admin_routes import admin_bp
app.register_blueprint(admin_bp)
logger.info("✓ Registered admin routes: /api/admin")

# Notification Routes
from backend.api.notification_routes import notification_bp
app.register_blueprint(notification_bp)
logger.info("✓ Registered notification routes: /api/notifications")

# ==============================================================================
# HEALTH CHECK ENDPOINT
# ==============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    from backend.database_manager import execute_query

    # Check database
    db_status = 'ok'
    try:
        execute_query("SELECT 1", fetch_one=True)
    except Exception as e:
        db_status = f'error: {str(e)}'
        logger.error(f"Health check DB error: {e}")

    # Check decision engine
    engine_status = 'loaded' if decision_engine_manager.models_loaded else 'not loaded'

    return {
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'service': 'AWS Spot Optimizer Backend',
        'version': '5.0.0',
        'architecture': 'modular',
        'migration_progress': '100%',
        'components': {
            'database': db_status,
            'decision_engine': engine_status,
            'endpoints_total': 63,
            'endpoints_active': 63,
            'blueprints_registered': 5,
            'background_jobs': 'running' if config.ENABLE_BACKGROUND_JOBS else 'disabled'
        }
    }, 200 if db_status == 'ok' else 503

# ==============================================================================
# BACKGROUND JOBS
# ==============================================================================

scheduler = None

if config.ENABLE_BACKGROUND_JOBS:
    logger.info("Initializing background jobs...")

    scheduler = BackgroundScheduler(daemon=True)

    # Register all job modules
    from backend.jobs.health_monitor import register_jobs as register_health_jobs
    from backend.jobs.pricing_aggregator import register_jobs as register_pricing_jobs
    from backend.jobs.data_cleaner import register_jobs as register_cleaner_jobs
    from backend.jobs.snapshot_jobs import register_jobs as register_snapshot_jobs

    register_health_jobs(scheduler)
    register_pricing_jobs(scheduler)
    register_cleaner_jobs(scheduler)
    register_snapshot_jobs(scheduler)

    scheduler.start()
    logger.info("✓ Background jobs started")
    logger.info(f"  - Health monitor: Every 5 minutes")
    logger.info(f"  - Pricing aggregator: Hourly + Daily")
    logger.info(f"  - Data cleaner: Daily at 2:00 AM")
    logger.info(f"  - Snapshot jobs: Daily")
else:
    logger.warning("⚠ Background jobs disabled")

# ==============================================================================
# GRACEFUL SHUTDOWN
# ==============================================================================

def shutdown_handler(signum, frame):
    """Handle graceful shutdown"""
    logger.info("Shutdown signal received, cleaning up...")

    if scheduler and scheduler.running:
        logger.info("Stopping background jobs...")
        scheduler.shutdown(wait=False)
        logger.info("✓ Background jobs stopped")

    logger.info("✓ Shutdown complete")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ==============================================================================
# APPLICATION STARTUP
# ==============================================================================

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("AWS Spot Optimizer - Production Backend v5.0.0")
    logger.info("=" * 80)
    logger.info(f"Environment: {'Production' if not config.DEBUG else 'Development'}")
    logger.info(f"Host: {config.HOST}")
    logger.info(f"Port: {config.PORT}")
    logger.info(f"Debug: {config.DEBUG}")
    logger.info(f"Database: {config.DB_NAME}@{config.DB_HOST}:{config.DB_PORT}")
    logger.info(f"Decision Engine: {decision_engine_manager.engine_type or 'Not loaded'}")
    logger.info(f"Background Jobs: {'Enabled' if config.ENABLE_BACKGROUND_JOBS else 'Disabled'}")
    logger.info("=" * 80)
    logger.info("Blueprints registered:")
    logger.info("  ✓ Agent routes (14 endpoints)")
    logger.info("  ✓ Replica routes (9 endpoints)")
    logger.info("  ✓ Client routes (23 endpoints)")
    logger.info("  ✓ Admin routes (14 endpoints)")
    logger.info("  ✓ Notification routes (3 endpoints)")
    logger.info("=" * 80)
    logger.info("🚀 Server starting...")
    logger.info("=" * 80)

    # Run Flask app
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        threaded=True
    )
