"""
Agent Orchestrator
==================

Coordinates the execution of all 8 agents in the correct order.

Orchestration Order:
1. GlobalIntelligenceAgent (scheduled)
2. CapacityValidator
3. DecisionEngine
4. RightsizingAgent (if needed)
5. CooldownController
6. SubstituteManager (if triggered)
7. ClusterExecutionAgent
8. EventMonitoringAgent (continuous)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .global_intelligence_agent import GlobalIntelligenceAgent
from .capacity_validator_agent import CapacityValidatorAgent
from .decision_engine_agent import DecisionEngineAgent
from .rightsizing_agent import RightsizingAgent
from .cooldown_controller_agent import CooldownControllerAgent
from .substitute_manager_agent import SubstituteManagerAgent
from .cluster_execution_agent import ClusterExecutionAgent
from .event_monitoring_agent import EventMonitoringAgent
from .base import AgentResponse


logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates the multi-agent system for spot optimization.

    Manages the pipeline of agents and handles data flow between them.
    """

    def __init__(self, llm_client=None, db_session=None, redis_client=None):
        """
        Initialize orchestrator with required dependencies.

        Args:
            llm_client: Optional LLM client for agents requiring AI
            db_session: Database session for persistence
            redis_client: Redis client for caching and blacklists
        """
        self.llm_client = llm_client
        self.db_session = db_session
        self.redis_client = redis_client

        # Initialize all agents
        self.global_intelligence = GlobalIntelligenceAgent(
            name="GlobalIntelligence",
            llm_client=llm_client
        )
        self.capacity_validator = CapacityValidatorAgent(
            name="CapacityValidator",
            llm_client=llm_client
        )
        self.decision_engine = DecisionEngineAgent(
            name="DecisionEngine",
            llm_client=llm_client
        )
        self.rightsizing = RightsizingAgent(
            name="Rightsizing",
            llm_client=llm_client
        )
        self.cooldown_controller = CooldownControllerAgent(
            name="CooldownController",
            llm_client=llm_client
        )
        self.substitute_manager = SubstituteManagerAgent(
            name="SubstituteManager",
            llm_client=llm_client
        )
        self.cluster_execution = ClusterExecutionAgent(
            name="ClusterExecution",
            llm_client=llm_client
        )
        self.event_monitoring = EventMonitoringAgent(
            name="EventMonitoring",
            llm_client=llm_client
        )

        logger.info("AgentOrchestrator initialized with all 8 agents")

    def execute_optimization_pipeline(
        self,
        cluster_id: str,
        mode: str,
        region: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the complete optimization pipeline.

        Pipeline Order:
        1. Global Intelligence (rank pools)
        2. Capacity Validation (filter available)
        3. Decision Engine (select pool)
        4. Cooldown Check (prevent flapping)
        5. Cluster Execution (apply decision)

        Args:
            cluster_id: Target cluster ID
            mode: 'manual' or 'auto'
            region: AWS region
            input_data: Complete input data for pipeline

        Returns:
            Pipeline execution results
        """
        logger.info(f"Starting optimization pipeline for cluster {cluster_id} in {mode} mode")

        pipeline_results = {
            "cluster_id": cluster_id,
            "mode": mode,
            "started_at": datetime.utcnow().isoformat(),
            "stages": {}
        }

        try:
            # STAGE 1: Global Intelligence
            logger.info("Stage 1: Running Global Intelligence Agent")
            global_input = {
                "region": region,
                "spot_price_data": input_data.get('spot_price_data', []),
                "ondemand_price_data": input_data.get('ondemand_price_data', {}),
                "interruption_rates": input_data.get('interruption_rates', {}),
                "blacklist": input_data.get('blacklist', []),
                "historical_features": input_data.get('historical_features', [])
            }

            global_response = self.global_intelligence.execute(global_input)
            pipeline_results['stages']['global_intelligence'] = global_response.to_dict()

            if global_response.status != "SUCCESS":
                logger.error("Global Intelligence failed")
                return pipeline_results

            ranked_pools = global_response.data['pools']

            # STAGE 2: Capacity Validation
            logger.info("Stage 2: Running Capacity Validator Agent")
            capacity_input = {
                "region": region,
                "candidate_pools": ranked_pools
            }

            capacity_response = self.capacity_validator.execute(capacity_input)
            pipeline_results['stages']['capacity_validation'] = capacity_response.to_dict()

            if capacity_response.status != "SUCCESS":
                logger.error("Capacity Validation failed")
                return pipeline_results

            validated_pools = capacity_response.data['validated_pools']

            # STAGE 3: Decision Engine
            logger.info("Stage 3: Running Decision Engine Agent")
            decision_input = {
                "cluster_id": cluster_id,
                "mode": mode,
                "global_ranked_pools": validated_pools,
                "node_template": input_data.get('node_template', {}),
                "karpenter_constraints": input_data.get('karpenter_constraints', {}),
                "cluster_state": input_data.get('cluster_state', {}),
                "cooldown_records": input_data.get('cooldown_records', {}),
                "recent_actions": input_data.get('recent_actions', [])
            }

            decision_response = self.decision_engine.execute(decision_input)
            pipeline_results['stages']['decision_engine'] = decision_response.to_dict()

            if decision_response.status != "SUCCESS":
                logger.error("Decision Engine failed")
                return pipeline_results

            # STAGE 4: Cooldown Check (if auto mode)
            if mode == 'auto' and decision_response.data.get('action') == 'ALLOW':
                logger.info("Stage 4: Running Cooldown Controller Agent")

                cooldown_input = {
                    "cluster_id": cluster_id,
                    "recent_actions": input_data.get('recent_actions', []),
                    "proposed_pool": decision_response.data.get('selected_pool')
                }

                cooldown_response = self.cooldown_controller.execute(cooldown_input)
                pipeline_results['stages']['cooldown_check'] = cooldown_response.to_dict()

                if cooldown_response.data.get('cooldown_active'):
                    logger.warning("Cooldown active, skipping execution")
                    return pipeline_results

                # STAGE 5: Cluster Execution
                logger.info("Stage 5: Running Cluster Execution Agent")

                execution_input = {
                    "cluster_id": cluster_id,
                    "action": "patch_nodepool",
                    "selected_pool": decision_response.data['selected_pool']
                }

                execution_response = self.cluster_execution.execute(execution_input)
                pipeline_results['stages']['cluster_execution'] = execution_response.to_dict()

            pipeline_results['completed_at'] = datetime.utcnow().isoformat()
            pipeline_results['status'] = 'SUCCESS'

            logger.info("Optimization pipeline completed successfully")
            return pipeline_results

        except Exception as e:
            logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
            pipeline_results['status'] = 'FAILED'
            pipeline_results['error'] = str(e)
            return pipeline_results

    def execute_rightsizing_analysis(
        self,
        cluster_id: str,
        pod_metrics: List[Dict],
        global_pools: List[Dict]
    ) -> AgentResponse:
        """
        Execute rightsizing analysis pipeline.

        Args:
            cluster_id: Target cluster
            pod_metrics: Pod-level metrics
            global_pools: Ranked pool list from global intelligence

        Returns:
            Rightsizing recommendations
        """
        logger.info(f"Running rightsizing analysis for cluster {cluster_id}")

        rightsizing_input = {
            "cluster_id": cluster_id,
            "analysis_window_hours": 168,  # 7 days
            "pod_metrics": pod_metrics,
            "instance_cost_data": {},  # Would be populated from pricing service
            "global_ranked_pools": global_pools
        }

        return self.rightsizing.execute(rightsizing_input)

    def handle_spot_interruption_event(
        self,
        cluster_id: str,
        event_type: str,
        instance_type: str,
        az: str
    ) -> AgentResponse:
        """
        Handle spot interruption events.

        Args:
            cluster_id: Affected cluster
            event_type: 'rebalance_notice' or 'termination_notice'
            instance_type: Affected instance type
            az: Affected availability zone

        Returns:
            Event handling results
        """
        logger.info(f"Handling {event_type} for {instance_type} in {az}")

        event_input = {
            "event_type": event_type,
            "cluster_id": cluster_id,
            "instance_type": instance_type,
            "az": az
        }

        event_response = self.event_monitoring.execute(event_input)

        # If termination notice, activate substitute with fresh pool rankings
        if event_type == 'termination_notice' and event_response.status == "SUCCESS":
            logger.info("Activating substitute manager — fetching fresh pool rankings")

            # Fetch fresh rankings AFTER the interruption so the blacklist already
            # includes the pool that just got interrupted.  Pass the interrupted
            # pool as an explicit exclude so the substitute never targets the same
            # pool that just failed.
            interrupted_pool_id = f"{instance_type}:{az}"
            candidate_pools = []
            try:
                global_result = self.global_intelligence.execute({
                    "cluster_id": cluster_id,
                    "exclude_pool": interrupted_pool_id,
                    "is_emergency": True,
                })
                candidate_pools = global_result.data.get("ranked_pools", [])
                logger.info(
                    f"Emergency pool fetch: {len(candidate_pools)} candidates "
                    f"(excluded {interrupted_pool_id})"
                )
            except Exception as pool_err:
                logger.warning(
                    f"Could not fetch fresh rankings for substitute on interruption: {pool_err}. "
                    "SubstituteManager will fall back to its own PoolRankingService call."
                )

            substitute_input = {
                "cluster_state": {"failed_instance": instance_type},
                "stress_level": "elevated",
                "candidate_pools": candidate_pools,
            }

            substitute_response = self.substitute_manager.execute(substitute_input)
            event_response.data['substitute'] = substitute_response.data

        return event_response

    def get_agent_status(self) -> Dict[str, Any]:
        """
        Get status of all agents in the orchestrator.

        Returns:
            Status dictionary
        """
        return {
            "orchestrator": "AgentOrchestrator",
            "version": "1.0.0",
            "agents": {
                "global_intelligence": {"name": self.global_intelligence.name, "status": "active"},
                "capacity_validator": {"name": self.capacity_validator.name, "status": "active"},
                "decision_engine": {"name": self.decision_engine.name, "status": "active"},
                "rightsizing": {"name": self.rightsizing.name, "status": "active"},
                "cooldown_controller": {"name": self.cooldown_controller.name, "status": "active"},
                "substitute_manager": {"name": self.substitute_manager.name, "status": "active"},
                "cluster_execution": {"name": self.cluster_execution.name, "status": "active"},
                "event_monitoring": {"name": self.event_monitoring.name, "status": "active"}
            },
            "timestamp": datetime.utcnow().isoformat()
        }
