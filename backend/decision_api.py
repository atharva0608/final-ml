"""
Decision Engine API Endpoints

REST API for interacting with the decision engine.

Main endpoint: POST /api/v1/decide-instance
"""

import logging
from flask import Blueprint, request, jsonify
from typing import Dict, Any
from dataclasses import asdict
from datetime import datetime

from decision_engine.engine_enhanced import EnhancedDecisionEngine, DecisionAction
from executor.aws_agentless import AWSAgentlessExecutor

logger = logging.getLogger(__name__)

# Create Blueprint
decision_api = Blueprint('decision_api', __name__, url_prefix='/api/v1')

# Initialize components (would be configured from environment in production)
decision_engine = EnhancedDecisionEngine()
executor = None  # Will be initialized when needed


def get_executor():
    """Get or create executor instance"""
    global executor
    if executor is None:
        # Initialize with config from environment
        # For now, using placeholder
        executor = AWSAgentlessExecutor(region='us-east-1')
    return executor


@decision_api.route('/decide-instance', methods=['POST'])
def decide_instance():
    """
    Main decision endpoint.

    Request body:
    {
        "current_instance_id": "i-1234567890abcdef0",
        "metrics_window_minutes": 60,
        "include_alternatives": true,
        "max_cost_increase_percent": 20
    }

    Response:
    {
        "decision": "MIGRATE | STAY | DEFER",
        "recommended_instance": "m5.large",
        "recommended_pool_id": "us-east-1a-standard",
        "confidence": 0.87,
        "score": 87.3,
        "estimated_savings_monthly": 45.50,
        "migration_plan": {...},
        "top_alternatives": [...]
    }
    """
    try:
        # Parse request
        data = request.get_json()
        instance_id = data.get('current_instance_id')
        metrics_window = data.get('metrics_window_minutes', 60)
        include_alternatives = data.get('include_alternatives', True)
        max_cost_increase = data.get('max_cost_increase_percent', 20)

        if not instance_id:
            return jsonify({'error': 'current_instance_id is required'}), 400

        logger.info(f"Received decision request for instance {instance_id}")

        # Step 1: Collect current instance state and metrics
        exec = get_executor()

        try:
            instance_state = exec.get_instance_state(instance_id)
            usage_metrics = exec.get_usage_metrics(instance_id, metrics_window)
        except Exception as e:
            logger.error(f"Failed to collect instance data: {e}")
            return jsonify({'error': f'Failed to collect instance data: {str(e)}'}), 500

        # Convert to dict format expected by decision engine
        current_instance = {
            'instance_id': instance_state.instance_id,
            'instance_type': instance_state.instance_type,
            'az': instance_state.az,
            'lifecycle': instance_state.lifecycle,
            'pool_id': f"{instance_state.az}-standard",  # Simplification
            'specifications': _get_instance_specs(instance_state.instance_type),
            'current_spot_price': 0.05  # Would get from pricing API
        }

        usage_metrics_dict = {
            'cpu_usage_percent': usage_metrics.cpu_p95,
            'ram_usage_percent': usage_metrics.memory_p95 or 50.0,  # Default if not available
            'cpu_credits_remaining': 500  # Placeholder
        }

        usage_patterns = {
            'peak_cpu_last_24h': usage_metrics.cpu_p95 * 1.1,
            'avg_cpu_last_24h': usage_metrics.cpu_avg,
            'peak_ram_last_24h': (usage_metrics.memory_p95 or 50.0) * 1.1,
            'avg_ram_last_24h': usage_metrics.memory_avg or 40.0,
            'burst_frequency': 5
        }

        # Step 2: Discover available pools
        # In production, this would query AWS for all available pools
        # For now, using mock data
        available_pools = _get_mock_pools(instance_state.az, current_instance['instance_type'])

        # Step 3: Define requirements
        app_requirements = data.get('app_requirements', {
            'min_cpu_cores': 1,
            'min_ram_gb': 2,
            'stateless': True,
            'migration_downtime_tolerance_seconds': 120
        })

        sla_requirements = data.get('sla_requirements', {
            'max_interruption_rate_percent': 5.0,
            'required_uptime_percent': 99.0
        })

        # Step 4: Run decision engine
        logger.info("Running decision engine pipeline...")
        recommendation = decision_engine.decide(
            current_instance=current_instance,
            usage_metrics=usage_metrics_dict,
            usage_patterns=usage_patterns,
            available_pools=available_pools,
            app_requirements=app_requirements,
            sla_requirements=sla_requirements,
            region='us-east-1'
        )

        # Step 5: Format response
        response = {
            'decision': recommendation.action.value,
            'recommended_instance': recommendation.recommended_instance_type,
            'recommended_pool_id': recommendation.recommended_pool_id,
            'confidence': recommendation.confidence,
            'expected_cost_savings_percent': recommendation.expected_cost_savings_percent,
            'expected_stability_improvement_percent': recommendation.expected_stability_improvement_percent,
            'estimated_savings_monthly': _calculate_monthly_savings(
                recommendation.expected_cost_savings_percent,
                current_instance['current_spot_price']
            ),
            'reasoning': {
                'primary_factors': recommendation.primary_factors,
                'filtered_out_count': recommendation.filtered_out_count,
                'considered_pools': recommendation.considered_pools
            },
            'migration_plan': recommendation.migration_plan,
            'monitoring_alerts': recommendation.monitoring_alerts,
            'decision_id': recommendation.decision_id,
            'timestamp': recommendation.decision_timestamp.isoformat()
        }

        if include_alternatives:
            response['top_alternatives'] = recommendation.top_3_alternatives

        logger.info(f"Decision complete: {recommendation.action.value}")
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error in decision endpoint: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@decision_api.route('/pipeline-info', methods=['GET'])
def get_pipeline_info():
    """
    Get information about the decision pipeline.

    Returns details about ML models, scoring weights, and pipeline stages.
    """
    try:
        info = decision_engine.get_pipeline_info()
        return jsonify(info), 200
    except Exception as e:
        logger.error(f"Error getting pipeline info: {e}")
        return jsonify({'error': str(e)}), 500


@decision_api.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'components': {
            'decision_engine': 'operational',
            'ml_models': {
                'stability_ranker': 'placeholder',
                'price_predictor': 'placeholder'
            }
        }
    }), 200


# Helper functions

def _get_instance_specs(instance_type: str) -> Dict[str, Any]:
    """
    Get instance specifications.

    In production, this would query AWS or use a database.
    For now, using a simple lookup table.
    """
    # Simplified specs - would be comprehensive in production
    specs = {
        't3.micro': {'cpu_cores': 2, 'ram_gb': 1, 'storage_type': 'EBS', 'network_bandwidth_gbps': 0.5},
        't3.small': {'cpu_cores': 2, 'ram_gb': 2, 'storage_type': 'EBS', 'network_bandwidth_gbps': 0.5},
        't3.medium': {'cpu_cores': 2, 'ram_gb': 4, 'storage_type': 'EBS', 'network_bandwidth_gbps': 1.0},
        't3.large': {'cpu_cores': 2, 'ram_gb': 8, 'storage_type': 'EBS', 'network_bandwidth_gbps': 1.25},
        'm5.large': {'cpu_cores': 2, 'ram_gb': 8, 'storage_type': 'EBS', 'network_bandwidth_gbps': 2.5},
        'm5.xlarge': {'cpu_cores': 4, 'ram_gb': 16, 'storage_type': 'EBS', 'network_bandwidth_gbps': 5.0},
        'm5.2xlarge': {'cpu_cores': 8, 'ram_gb': 32, 'storage_type': 'EBS', 'network_bandwidth_gbps': 10.0},
        'c5.large': {'cpu_cores': 2, 'ram_gb': 4, 'storage_type': 'EBS', 'network_bandwidth_gbps': 2.5},
        'c5.xlarge': {'cpu_cores': 4, 'ram_gb': 8, 'storage_type': 'EBS', 'network_bandwidth_gbps': 5.0},
    }

    return specs.get(instance_type, {'cpu_cores': 2, 'ram_gb': 4, 'storage_type': 'EBS', 'network_bandwidth_gbps': 1.0})


def _get_mock_pools(current_az: str, current_type: str) -> list:
    """
    Get mock pool data for testing.

    In production, this would query AWS for all available pools.
    """
    base_pools = [
        {
            'pool_id': f'{current_az}-standard',
            'az': current_az,
            'instance_type': current_type,
            'specifications': _get_instance_specs(current_type),
            'current_spot_price': 0.05
        },
        {
            'pool_id': f'{current_az}-standard',
            'az': current_az,
            'instance_type': 'm5.large',
            'specifications': _get_instance_specs('m5.large'),
            'current_spot_price': 0.04
        },
        {
            'pool_id': f'{current_az}-standard',
            'az': current_az,
            'instance_type': 'm5.xlarge',
            'specifications': _get_instance_specs('m5.xlarge'),
            'current_spot_price': 0.08
        },
        {
            'pool_id': f'{current_az}-standard',
            'az': current_az,
            'instance_type': 'c5.large',
            'specifications': _get_instance_specs('c5.large'),
            'current_spot_price': 0.045
        },
        {
            'pool_id': f'{current_az}-standard',
            'az': current_az,
            'instance_type': 't3.large',
            'specifications': _get_instance_specs('t3.large'),
            'current_spot_price': 0.03
        }
    ]

    return base_pools


def _calculate_monthly_savings(savings_percent: float, current_hourly_cost: float) -> float:
    """Calculate estimated monthly savings in dollars"""
    hours_per_month = 730  # Average
    monthly_current = current_hourly_cost * hours_per_month
    monthly_savings = monthly_current * (savings_percent / 100)
    return round(monthly_savings, 2)
