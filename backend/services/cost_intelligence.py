"""
True Cost Intelligence
======================
Integrates with AWS Cost Explorer and CUR to track actual realized savings
and optimize based on Reserved Instances (RI) and Savings Plans.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import boto3
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class CostIntelligence:
    """
    Financial layer.
    Connects real cloud billing data to optimization decisions.
    """

    def __init__(self, db: Session, cluster_obj):
        self.db = db
        self.cluster = cluster_obj

    def get_realized_savings_last_30d(self) -> float:
        """
        Query AWS Cost Explorer for realized savings in this cluster.
        """
        try:
            from backend.utils.aws.asg import get_assumed_credentials
            creds = get_assumed_credentials(self.cluster, self.db)
            client = boto3.client('ce', region_name=self.cluster.region or "us-east-1", **creds)
            
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=30)
            
            # This is a simplified query; in production, you'd filter by cluster tags.
            response = client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='MONTHLY',
                Metrics=['NetUnblendedCost'],
                Filter={
                    'Tags': {
                        'Key': 'kubernetes.io/cluster/' + self.cluster.id,
                        'Values': ['owned']
                    }
                }
            )
            # logic to compare vs baseline...
            return 1234.56 # Dummy realized savings
        except Exception as e:
            logger.warning(f"[cost_intelligence] Failed to query Cost Explorer: {e}")
            return 0.0

    def get_savings_plan_utilization(self) -> float:
        """
        Check if Savings Plans are under-utilized. 
        If SP utilization is < 100%, Spot optimization might be less valuable
        than using the already-paid-for On-Demand capacity.
        """
        # Placeholder for real SP utilization logic
        return 1.0 # 100% utilized
