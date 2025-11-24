"""
AWS Spot Optimizer - Notification API Routes
=============================================
API endpoints for notification management
"""

import logging
from flask import Blueprint, request, jsonify

from backend.auth import require_client_token
from backend.services import notification_service

logger = logging.getLogger(__name__)

# Create Blueprint
notification_bp = Blueprint('notification', __name__, url_prefix='/api/notifications')


@notification_bp.route('', methods=['GET'])
@require_client_token
def get_notifications():
    """Get notifications for client"""
    try:
        limit = int(request.args.get('limit', 50))
        result = notification_service.get_notifications(request.client_id, limit)
        return jsonify({'notifications': result}), 200
    except Exception as e:
        logger.error(f"Get notifications error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@notification_bp.route('/<notif_id>/mark-read', methods=['POST'])
@require_client_token
def mark_read(notif_id: str):
    """Mark notification as read"""
    try:
        result = notification_service.mark_notification_read(notif_id, request.client_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Mark notification read error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@notification_bp.route('/mark-all-read', methods=['POST'])
@require_client_token
def mark_all_read():
    """Mark all notifications as read for client"""
    try:
        result = notification_service.mark_all_notifications_read(request.client_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Mark all notifications read error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
