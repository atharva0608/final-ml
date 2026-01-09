"""
Kubernetes Agent Configuration (AGENT-CFG-01)
Load and validate agent configuration from environment variables

Required env vars:
- API_URL: Backend API base URL
- CLUSTER_ID: Unique cluster identifier
- API_TOKEN: Authentication token

Optional env vars:
- LOG_LEVEL: Logging level (default: INFO)
- COLLECTION_INTERVAL: Metrics collection interval in seconds (default: 30)
- HEARTBEAT_INTERVAL: Heartbeat interval in seconds (default: 30)
- NAMESPACE: Agent namespace (default: spot-optimizer)
- DRY_RUN: Dry-run mode, log actions without executing (default: false)
- WEBSOCKET_ENABLED: Enable WebSocket client (default: true)
"""

import os
import logging
import signal
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class Config:
    """Agent configuration with validation"""

    def __init__(self):
        """Load configuration from environment variables"""
        self.load_config()
        self.validate()

    def load_config(self):
        """Load configuration from environment"""
        # Required configuration
        self.api_url = os.getenv('API_URL', '').strip()
        self.cluster_id = os.getenv('CLUSTER_ID', '').strip()
        self.api_token = os.getenv('API_TOKEN', '').strip()

        # Optional configuration with defaults
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.collection_interval = int(os.getenv('COLLECTION_INTERVAL', '30'))
        self.heartbeat_interval = int(os.getenv('HEARTBEAT_INTERVAL', '30'))
        self.namespace = os.getenv('NAMESPACE', 'spot-optimizer')
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
        self.websocket_enabled = os.getenv('WEBSOCKET_ENABLED', 'true').lower() == 'true'

        # Derived configuration
        self.agent_id = f"{self.cluster_id}-agent"
        self.version = "1.0.0"

        logger.info(f"[AGENT-CFG-01] Configuration loaded")
        logger.info(f"[AGENT-CFG-01]   API URL: {self.api_url}")
        logger.info(f"[AGENT-CFG-01]   Cluster ID: {self.cluster_id}")
        logger.info(f"[AGENT-CFG-01]   Namespace: {self.namespace}")
        logger.info(f"[AGENT-CFG-01]   Collection Interval: {self.collection_interval}s")
        logger.info(f"[AGENT-CFG-01]   Heartbeat Interval: {self.heartbeat_interval}s")
        logger.info(f"[AGENT-CFG-01]   Dry Run: {self.dry_run}")
        logger.info(f"[AGENT-CFG-01]   WebSocket: {self.websocket_enabled}")

    def validate(self):
        """Validate configuration"""
        errors = []

        # Validate API_URL
        if not self.api_url:
            errors.append("API_URL is required")
        else:
            parsed = urlparse(self.api_url)
            if not parsed.scheme or not parsed.netloc:
                errors.append(f"API_URL is invalid: {self.api_url}")
            if parsed.scheme not in ['http', 'https']:
                errors.append(f"API_URL must use http or https: {self.api_url}")

        # Validate CLUSTER_ID
        if not self.cluster_id:
            errors.append("CLUSTER_ID is required")

        # Validate API_TOKEN
        if not self.api_token:
            errors.append("API_TOKEN is required")

        # Validate LOG_LEVEL
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level not in valid_log_levels:
            errors.append(f"LOG_LEVEL must be one of {valid_log_levels}, got {self.log_level}")

        # Validate intervals
        if self.collection_interval < 5:
            errors.append(f"COLLECTION_INTERVAL must be >= 5 seconds, got {self.collection_interval}")
        if self.heartbeat_interval < 5:
            errors.append(f"HEARTBEAT_INTERVAL must be >= 5 seconds, got {self.heartbeat_interval}")

        if errors:
            error_msg = "\n".join(f"  - {err}" for err in errors)
            raise ValueError(f"Configuration validation failed:\n{error_msg}")

        logger.info(f"[AGENT-CFG-01] Configuration validated successfully")

    def reload(self):
        """Reload configuration (for SIGHUP handler)"""
        logger.info(f"[AGENT-CFG-01] Reloading configuration...")
        old_log_level = self.log_level
        old_collection_interval = self.collection_interval
        old_heartbeat_interval = self.heartbeat_interval

        self.load_config()
        self.validate()

        # Log changes
        if old_log_level != self.log_level:
            logger.info(f"[AGENT-CFG-01]   Log level changed: {old_log_level} -> {self.log_level}")
            logging.getLogger().setLevel(self.log_level)
        if old_collection_interval != self.collection_interval:
            logger.info(f"[AGENT-CFG-01]   Collection interval changed: {old_collection_interval}s -> {self.collection_interval}s")
        if old_heartbeat_interval != self.heartbeat_interval:
            logger.info(f"[AGENT-CFG-01]   Heartbeat interval changed: {old_heartbeat_interval}s -> {self.heartbeat_interval}s")

        logger.info(f"[AGENT-CFG-01] Configuration reloaded successfully")

    def get_headers(self) -> dict:
        """Get HTTP headers with authentication"""
        return {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'User-Agent': f'SpotOptimizer-Agent/{self.version}'
        }

    def get_metrics_url(self) -> str:
        """Get metrics endpoint URL"""
        return f"{self.api_url}/clusters/{self.cluster_id}/metrics"

    def get_heartbeat_url(self) -> str:
        """Get heartbeat endpoint URL"""
        return f"{self.api_url}/clusters/{self.cluster_id}/heartbeat"

    def get_actions_url(self) -> str:
        """Get actions endpoint URL"""
        return f"{self.api_url}/clusters/{self.cluster_id}/actions/pending"

    def get_action_result_url(self, action_id: str) -> str:
        """Get action result endpoint URL"""
        return f"{self.api_url}/clusters/{self.cluster_id}/actions/{action_id}/result"

    def get_register_url(self) -> str:
        """Get agent registration endpoint URL"""
        return f"{self.api_url}/clusters/{self.cluster_id}/agent/register"

    def get_websocket_url(self) -> str:
        """Get WebSocket URL"""
        ws_scheme = 'wss' if self.api_url.startswith('https') else 'ws'
        base_url = self.api_url.replace('https://', '').replace('http://', '')
        return f"{ws_scheme}://{base_url}/clusters/{self.cluster_id}/stream"


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def setup_signal_handlers(config: Config):
    """Setup signal handlers for config reload"""
    def handle_sighup(signum, frame):
        logger.info(f"[AGENT-CFG-01] Received SIGHUP, reloading configuration...")
        try:
            config.reload()
        except Exception as e:
            logger.error(f"[AGENT-CFG-01] Config reload failed: {e}")

    signal.signal(signal.SIGHUP, handle_sighup)
    logger.info(f"[AGENT-CFG-01] Signal handlers registered")
