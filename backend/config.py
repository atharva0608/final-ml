"""
AWS Spot Optimizer - Configuration Module
===========================================
Centralizes all configuration with environment variable support
"""

import os
from pathlib import Path


class Config:
    """Main server configuration with environment variable support"""

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


class DatabaseConfig:
    """Database configuration (deprecated - use Config instead for consistency)"""
    DB_HOST = Config.DB_HOST
    DB_PORT = Config.DB_PORT
    DB_USER = Config.DB_USER
    DB_PASSWORD = Config.DB_PASSWORD
    DB_NAME = Config.DB_NAME
    DB_POOL_SIZE = Config.DB_POOL_SIZE


# Singleton instances
config = Config()
db_config = DatabaseConfig()
