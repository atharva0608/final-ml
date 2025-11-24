"""
AWS Spot Optimizer - Modular Backend Application
=================================================
New modular entry point replacing monolithic backend.py

Architecture:
- api/: Route blueprints organized by domain
- services/: Business logic layer
- jobs/: Background job definitions
- config.py: Centralized configuration
- database_manager.py: Database utilities
- utils.py: Common utilities
- auth.py: Authentication middleware

Migration Status: IN PROGRESS
- Priority 1: Agent Core (1/9 endpoints migrated)
- Priority 2: Replica Management (0/9 endpoints)
- Priority 3: Client Features (0/18 endpoints)
- Priority 4: Admin Operations (0/11 endpoints)
- Priority 5: Background Jobs (0/6 jobs)

Total: 1/63 endpoints (2% complete)
"""

import logging
import os
from flask import Flask
from flask_cors import CORS

from backend.config import config
from backend.database_manager import init_db_pool

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
# REGISTER BLUEPRINTS
# ==============================================================================

logger.info("Registering API blueprints...")

# Agent Routes (Priority 1 - Agent Core)
from backend.api.agent_routes import agent_bp
app.register_blueprint(agent_bp)
logger.info("✓ Registered agent routes: /api/agents")

# TODO: Register additional blueprints as they are created:
# from backend.api.replica_routes import replica_bp
# app.register_blueprint(replica_bp)
#
# from backend.api.client_routes import client_bp
# app.register_blueprint(client_bp)
#
# from backend.api.admin_routes import admin_bp
# app.register_blueprint(admin_bp)
#
# from backend.api.notification_routes import notification_bp
# app.register_blueprint(notification_bp)

# ==============================================================================
# HEALTH CHECK ENDPOINT
# ==============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Basic health check endpoint"""
    return {
        'status': 'ok',
        'service': 'AWS Spot Optimizer Backend',
        'architecture': 'modular',
        'migration_progress': '2%',
        'endpoints_migrated': 1,
        'endpoints_total': 63
    }, 200

# ==============================================================================
# BACKGROUND JOBS (TODO)
# ==============================================================================

# TODO: Initialize background jobs after all services are migrated
# from backend.jobs.health_monitor import start_health_monitor
# from backend.jobs.pricing_aggregator import start_pricing_jobs
# from backend.jobs.data_cleaner import start_cleanup_jobs
# from backend.jobs.snapshot_jobs import start_snapshot_jobs
#
# if config.ENABLE_BACKGROUND_JOBS:
#     logger.info("Starting background jobs...")
#     start_health_monitor()
#     start_pricing_jobs()
#     start_cleanup_jobs()
#     start_snapshot_jobs()
#     logger.info("✓ Background jobs started")

# ==============================================================================
# APPLICATION STARTUP
# ==============================================================================

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("AWS Spot Optimizer - Modular Backend")
    logger.info("=" * 80)
    logger.info(f"Host: {config.HOST}")
    logger.info(f"Port: {config.PORT}")
    logger.info(f"Debug: {config.DEBUG}")
    logger.info(f"Database: {config.DB_NAME}@{config.DB_HOST}")
    logger.info("=" * 80)

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG
    )
