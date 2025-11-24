"""
AWS Spot Optimizer - Admin API Routes
======================================
API endpoints for administrative operations
"""

import logging
from flask import Blueprint, request, jsonify

from backend.services import admin_service

logger = logging.getLogger(__name__)

# Create Blueprint - NO auth required for admin routes (add your own auth if needed)
admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


# ==============================================================================
# CLIENT MANAGEMENT
# ==============================================================================

@admin_bp.route('/clients/create', methods=['POST'])
def create_client():
    """Create new client"""
    try:
        result = admin_service.create_client(request.json or {})
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Create client error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/clients/<client_id>', methods=['DELETE'])
def delete_client(client_id: str):
    """Delete client"""
    try:
        result = admin_service.delete_client(client_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Delete client error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/clients/<client_id>/regenerate-token', methods=['POST'])
def regenerate_token(client_id: str):
    """Regenerate client token"""
    try:
        result = admin_service.regenerate_client_token(client_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Regenerate token error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/clients/<client_id>/token', methods=['GET'])
def get_token(client_id: str):
    """Get client token"""
    try:
        result = admin_service.get_client_token(client_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Get token error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/clients', methods=['GET'])
def get_clients():
    """Get all clients"""
    try:
        result = admin_service.get_all_clients()
        return jsonify({'clients': result}), 200
    except Exception as e:
        logger.error(f"Get clients error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/clients/growth', methods=['GET'])
def get_growth():
    """Get client growth statistics"""
    try:
        days = int(request.args.get('days', 30))
        result = admin_service.get_client_growth(days)
        return jsonify({'growth': result}), 200
    except Exception as e:
        logger.error(f"Get growth error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# SYSTEM OVERVIEW
# ==============================================================================

@admin_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get admin dashboard statistics"""
    try:
        result = admin_service.get_admin_stats()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get stats error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/instances', methods=['GET'])
def get_instances():
    """Get all instances across all clients"""
    try:
        result = admin_service.get_all_instances()
        return jsonify({'instances': result}), 200
    except Exception as e:
        logger.error(f"Get instances error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/agents', methods=['GET'])
def get_agents():
    """Get all agents across all clients"""
    try:
        result = admin_service.get_all_agents()
        return jsonify({'agents': result}), 200
    except Exception as e:
        logger.error(f"Get agents error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/activity', methods=['GET'])
def get_activity():
    """Get system activity log"""
    try:
        days = int(request.args.get('days', 7))
        result = admin_service.get_system_activity(days)
        return jsonify({'activity': result}), 200
    except Exception as e:
        logger.error(f"Get activity error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/system-health', methods=['GET'])
def get_health():
    """Get system health metrics"""
    try:
        result = admin_service.get_system_health()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Get health error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
