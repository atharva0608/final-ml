"""
Agent Service
=============

Service layer for multi-agent system integration.
Bridges the agent orchestrator with FastAPI backend.
"""

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.agents import AgentOrchestrator
from backend.models.cluster import Cluster
from backend.core.redis_client import get_redis_client


logger = logging.getLogger(__name__)


class AgentService:
    """
    Service layer for multi-agent system.

    Provides high-level methods for:
    - Running optimization pipelines
    - Handling spot interruption events
    - Generating rightsizing recommendations
    - Monitoring agent health
    """

    def __init__(self, db: Session, llm_client=None):
        """
        Initialize agent service.

        Args:
            db: Database session
            llm_client: Optional LLM client for AI-powered agents
        """
        self.db = db
        self.redis_client = get_redis_client()
        self.orchestrator = AgentOrchestrator(
            llm_client=llm_client,
            db_session=db,
            redis_client=self.redis_client
        )

        logger.info("AgentService initialized")

    async def run_optimization_for_cluster(
        self,
        cluster_id: str,
        mode: str = "auto",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Run complete optimization pipeline for a cluster.

        Args:
            cluster_id: Target cluster ID
            mode: 'manual' or 'auto'
            force_refresh: Force refresh of cached data

        Returns:
            Optimization results
        """
        try:
            # Get cluster from database
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")

            # Get region
            region = cluster.region or "us-east-1"

            # Gather input data
            input_data = await self._gather_optimization_input(
                cluster=cluster,
                force_refresh=force_refresh
            )

            # Execute pipeline
            results = self.orchestrator.execute_optimization_pipeline(
                cluster_id=cluster_id,
                mode=mode,
                region=region,
                input_data=input_data
            )

            # Cache results if successful
            if results['status'] == 'SUCCESS':
                self._cache_results(cluster_id, results)

            return results

        except Exception as e:
            logger.error(f"Optimization failed for cluster {cluster_id}: {str(e)}", exc_info=True)
            return {
                "cluster_id": cluster_id,
                "status": "FAILED",
                "error": str(e)
            }

    async def generate_rightsizing_recommendations(
        self,
        cluster_id: str,
        analysis_window_hours: int = 168
    ) -> Dict[str, Any]:
        """
        Generate rightsizing recommendations for a cluster.

        Args:
            cluster_id: Target cluster ID
            analysis_window_hours: Analysis window (default: 168 = 7 days)

        Returns:
            Rightsizing recommendations
        """
        try:
            # Get pod metrics
            pod_metrics = await self._fetch_pod_metrics(
                cluster_id=cluster_id,
                window_hours=analysis_window_hours
            )

            # Get global pools (cached or fresh)
            global_pools = await self._get_global_pools(cluster_id)

            # Run rightsizing analysis
            response = self.orchestrator.execute_rightsizing_analysis(
                cluster_id=cluster_id,
                pod_metrics=pod_metrics,
                global_pools=global_pools
            )

            return response.to_dict()

        except Exception as e:
            logger.error(f"Rightsizing analysis failed: {str(e)}", exc_info=True)
            return {
                "status": "FAILED",
                "error": str(e)
            }

    async def handle_interruption_event(
        self,
        cluster_id: str,
        event_type: str,
        instance_type: str,
        az: str
    ) -> Dict[str, Any]:
        """
        Handle spot interruption event.

        Args:
            cluster_id: Affected cluster
            event_type: 'rebalance_notice' or 'termination_notice'
            instance_type: Affected instance type
            az: Affected availability zone

        Returns:
            Event handling results
        """
        try:
            response = self.orchestrator.handle_spot_interruption_event(
                cluster_id=cluster_id,
                event_type=event_type,
                instance_type=instance_type,
                az=az
            )

            # Update blacklist in Redis if termination
            if event_type == 'termination_notice' and response.status == "SUCCESS":
                blacklist_entry = response.data.get('blacklist_entry')
                if blacklist_entry:
                    self._update_blacklist(blacklist_entry)

            return response.to_dict()

        except Exception as e:
            logger.error(f"Event handling failed: {str(e)}", exc_info=True)
            return {
                "status": "FAILED",
                "error": str(e)
            }

    async def get_agent_health_status(self) -> Dict[str, Any]:
        """
        Get health status of all agents.

        Returns:
            Agent health status
        """
        return self.orchestrator.get_agent_status()

    # Helper methods

    async def _gather_optimization_input(
        self,
        cluster: Cluster,
        force_refresh: bool
    ) -> Dict[str, Any]:
        """
        Gather all required input data for optimization pipeline.
        """
        # This would integrate with existing services
        # For now, return mock data structure

        return {
            "spot_price_data": await self._fetch_spot_prices(cluster.region),
            "ondemand_price_data": await self._fetch_ondemand_prices(cluster.region),
            "interruption_rates": await self._fetch_interruption_rates(cluster.region),
            "blacklist": self._get_blacklist(),
            "historical_features": [],
            "node_template": await self._get_node_template(cluster.id),
            "karpenter_constraints": await self._get_karpenter_constraints(cluster.id),
            "cluster_state": await self._get_cluster_state(cluster.id),
            "cooldown_records": self._get_cooldown_records(cluster.id),
            "recent_actions": await self._get_recent_actions(cluster.id)
        }

    async def _fetch_spot_prices(self, region: str) -> List[Dict]:
        """Fetch current spot prices for region"""
        # Integration point with existing pricing service
        return []

    async def _fetch_ondemand_prices(self, region: str) -> Dict:
        """Fetch on-demand prices for region"""
        # Integration point with existing pricing service
        return {}

    async def _fetch_interruption_rates(self, region: str) -> Dict:
        """Fetch interruption rates from Spot Advisor"""
        # Integration point with spot advisor scraper
        return {}

    def _get_blacklist(self) -> List[str]:
        """Get blacklisted pools from Redis"""
        try:
            blacklist = self.redis_client.smembers("risky_pools")
            return list(blacklist)
        except Exception as e:
            logger.error(f"Failed to get blacklist: {e}")
            return []

    async def _get_node_template(self, cluster_id: str) -> Dict:
        """Get node template for cluster"""
        # Integration point with template service
        return {}

    async def _get_karpenter_constraints(self, cluster_id: str) -> Dict:
        """Get Karpenter constraints for cluster"""
        # Integration point with cluster service
        return {}

    async def _get_cluster_state(self, cluster_id: str) -> Dict:
        """Get current cluster state"""
        # Integration point with cluster service
        return {"existing_instances": []}

    def _get_cooldown_records(self, cluster_id: str) -> Dict:
        """Get cooldown records from Redis"""
        try:
            key = f"cooldown:{cluster_id}"
            records = self.redis_client.hgetall(key)
            return records
        except Exception as e:
            logger.error(f"Failed to get cooldown records: {e}")
            return {}

    async def _get_recent_actions(self, cluster_id: str) -> List[Dict]:
        """Get recent optimization actions"""
        # Integration point with audit service
        return []

    async def _fetch_pod_metrics(self, cluster_id: str, window_hours: int) -> List[Dict]:
        """Fetch pod metrics for analysis"""
        # Integration point with pod metrics service
        return []

    async def _get_global_pools(self, cluster_id: str) -> List[Dict]:
        """Get global ranked pools (cached or fresh)"""
        # Check cache first
        cache_key = f"global_pools:{cluster_id}"
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        except Exception:
            pass

        return []

    def _cache_results(self, cluster_id: str, results: Dict):
        """Cache optimization results"""
        try:
            import json
            cache_key = f"optimization_results:{cluster_id}"
            self.redis_client.setex(
                cache_key,
                300,  # 5 minutes TTL
                json.dumps(results)
            )
        except Exception as e:
            logger.error(f"Failed to cache results: {e}")

    def _update_blacklist(self, blacklist_entry: Dict):
        """Update blacklist in Redis"""
        try:
            pool = blacklist_entry['pool']
            self.redis_client.sadd("risky_pools", pool)
            # Set expiration
            self.redis_client.expire("risky_pools", 86400)  # 24 hours
        except Exception as e:
            logger.error(f"Failed to update blacklist: {e}")
