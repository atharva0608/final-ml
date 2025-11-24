"""
AWS Spot Optimizer - Agent API Routes
======================================
API endpoints for agent communication

Priority 1 (Agent Core) - CRITICAL endpoints agents depend on:
- ✅ POST /pricing-report: Store pricing data from agents
- ⏳ POST /switch-report: Record instance switch events
- ⏳ POST /termination: Handle instance termination
- ⏳ POST /cleanup-report: Report cleanup after switch
- ⏳ POST /rebalance-recommendation: Handle AWS rebalance notices
- ⏳ GET /replica-config: Get replica configuration
- ⏳ POST /decide: Request switching decision from ML model
- ⏳ GET /switch-recommendation: Get switch recommendation
- ⏳ POST /issue-switch-command: Issue switch command to agent
"""

import logging
from flask import Blueprint, request, jsonify

from backend.auth import require_client_token
from backend.services.pricing_service import store_pricing_report

logger = logging.getLogger(__name__)

# Create Blueprint
agent_bp = Blueprint('agent', __name__, url_prefix='/api/agents')


@agent_bp.route('/<agent_id>/pricing-report', methods=['POST'])
@require_client_token
def pricing_report(agent_id: str):
    """
    Receive pricing data from agent

    Agent sends pricing snapshots every 5 minutes containing:
    - Current instance pricing (spot & on-demand)
    - All available spot pools with prices
    - Cheapest pool identification

    This data is used for:
    - ML model decision making
    - Pricing history charts
    - Cost savings calculations
    """
    data = request.json

    try:
        result = store_pricing_report(agent_id, request.client_id, data)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Pricing report error: {e}")
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# TODO: Migrate remaining Priority 1 endpoints
# ==============================================================================
#
# @agent_bp.route('/<agent_id>/switch-report', methods=['POST'])
# @require_client_token
# def switch_report(agent_id: str):
#     """Record instance switch event"""
#     # TODO: Extract to services/switch_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/termination', methods=['POST'])
# @require_client_token
# def termination_report(agent_id: str):
#     """Handle instance termination"""
#     # TODO: Extract to services/instance_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/cleanup-report', methods=['POST'])
# @require_client_token
# def cleanup_report(agent_id: str):
#     """Report cleanup after switch"""
#     # TODO: Extract to services/switch_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/rebalance-recommendation', methods=['POST'])
# @require_client_token
# def rebalance_recommendation(agent_id: str):
#     """Handle AWS rebalance recommendation"""
#     # TODO: Extract to services/replica_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/replica-config', methods=['GET'])
# @require_client_token
# def get_replica_config(agent_id: str):
#     """Get replica configuration"""
#     # TODO: Extract to services/replica_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/decide', methods=['POST'])
# @require_client_token
# def decide(agent_id: str):
#     """Request switching decision from ML model"""
#     # TODO: Extract to services/decision_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/switch-recommendation', methods=['GET'])
# @require_client_token
# def switch_recommendation(agent_id: str):
#     """Get switch recommendation"""
#     # TODO: Extract to services/decision_service.py
#     pass
#
# @agent_bp.route('/<agent_id>/issue-switch-command', methods=['POST'])
# @require_client_token
# def issue_switch_command(agent_id: str):
#     """Issue switch command to agent"""
#     # TODO: Extract to services/switch_service.py
#     pass
