"""
Replay Simulator
================
Offline validation tool to replay historical cluster snapshots and test
optimizer decisions against them before production deployment.
"""

import logging
import argparse
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.models.cluster import Cluster
from backend.api.optimize_routes import _generate_optimization_plan

logger = logging.getLogger(__name__)

class ReplaySimulator:
    """
    Offline "Digital Twin" simulator.
    """

    def __init__(self, db: Session, cluster_id: str):
        self.db = db
        self.cluster_id = cluster_id

    def run_replay(self, snapshot_file: str):
        """
        Replays optimization logic against a JSON snapshot.
        """
        logger.info(f"[replay] Loading snapshot: {snapshot_file}")
        with open(snapshot_file, 'r') as f:
            snapshot = json.load(f)

        # Mock the context for the optimizer
        # snapshot should contain: pods, nodes, wie_data, targets
        pods = snapshot.get("pods", [])
        nodes = snapshot.get("nodes", [])
        
        logger.info(f"[replay] Replaying optimizer for {len(pods)} pods on {len(nodes)} nodes")
        
        # Call the core optimizer logic (dry-run)
        plan = _generate_optimization_plan(
            db=self.db,
            cluster_id=self.cluster_id,
            pods=pods,
            nodes=nodes,
            dry_run=True
        )
        
        self._analyze_plan(plan)

    def _analyze_plan(self, plan: Dict[str, Any]):
        """
        Analyze the generated plan for risk and ROI.
        """
        node_plan = plan.get("node_plan", [])
        drain_count = len([n for n in node_plan if n["action"] == "drain"])
        provision_count = len([n for n in node_plan if n["action"] == "provision"])
        
        logger.info(f"[replay] Result: Drain {drain_count} nodes, Provision {provision_count} nodes")
        logger.info(f"[replay] Monthly Savings: ${plan.get('cost_projection', {}).get('monthly_savings', 0):.2f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay Simulator")
    parser.add_argument("--cluster-id", required=True)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    
    db = next(get_db())
    simulator = ReplaySimulator(db, args.cluster_id)
    simulator.run_replay(args.snapshot)
