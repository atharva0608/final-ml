"""
AWS Spot Optimizer - Pricing Service
=====================================
Business logic for pricing report processing and management
"""

import json
import logging
from typing import Dict, Any

from backend.database_manager import execute_query
from backend.utils import generate_uuid

logger = logging.getLogger(__name__)


def store_pricing_report(agent_id: str, client_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store pricing report from agent

    Args:
        agent_id: Agent UUID
        client_id: Client ID for authorization
        data: Pricing report data containing instance and pricing info

    Returns:
        Success response or error dict
    """
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
            client_id
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

        return {'success': True}

    except Exception as e:
        logger.error(f"Pricing report error: {e}")
        raise


def get_pricing_history(agent_id: str, days: int = 7) -> Dict[str, Any]:
    """
    Get pricing history for an agent

    Args:
        agent_id: Agent UUID
        days: Number of days of history to retrieve

    Returns:
        Pricing history data
    """
    try:
        history = execute_query("""
            SELECT
                id, instance_id, instance_type, region, az,
                current_mode, on_demand_price, current_spot_price,
                cheapest_pool_price, collected_at
            FROM pricing_reports
            WHERE agent_id = %s
              AND collected_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            ORDER BY collected_at DESC
        """, (agent_id, days), fetch=True)

        return {
            'success': True,
            'history': history or [],
            'days': days
        }

    except Exception as e:
        logger.error(f"Get pricing history error: {e}")
        raise
