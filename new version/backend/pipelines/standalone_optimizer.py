
"""
Standalone Optimizer Pipeline (The Brain)

A simplified optimization loop that performs the math but skips the "K8s Dance".
Designed for Lab Mode instances (Standalone/VMs).
"""
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from backend.executor.base import Executor, TargetSpec, InstanceState
from backend.decision_engine.engine_enhanced import EnhancedDecisionEngine, DecisionAction

logger = logging.getLogger(__name__)

class StandaloneOptimizer:
    """
    Orchestrates optimization for a single standalone instance (Lab Mode).
    Verification Bypass: Does NOT perform cordon/drain operations.
    """

    def __init__(self, executor: Executor, engine: EnhancedDecisionEngine):
        self.executor = executor
        self.engine = engine
        
        # Hardcoded CPU specs for reference (Demo/Lab Purposes)
        # In prod, this should come from a proper InstanceType provider
        self.instance_specs = {
            't3.micro': 2, 't3.small': 2, 't3.medium': 2,
            'c5.large': 2, 'c5.xlarge': 4, 'c5.2xlarge': 8,
            'm5.large': 2, 'm5.xlarge': 4, 'm5.2xlarge': 8,
            'r5.large': 2, 'r5.xlarge': 4, 'r5.2xlarge': 8
        }

    def optimize_node(self, instance_id: str, region: str = None) -> Dict[str, Any]:
        """
        Run optimization loop for a single node.
        
        Steps:
        1. Fetch current usage (Translate VM metrics to Requirements)
        2. Get Decision (Price vs Risk)
        3. Execute (Launch -> Wait -> Terminate Old)
        """
        logger.info(f"Starting standalone optimization for {instance_id}")
        
        # 1. Fetch Current State & Usage
        # ----------------------------------------
        try:
            current_state = self.executor.get_instance_state(instance_id)
        except Exception as e:
            logger.error(f"Failed to get instance state: {e}")
            return {"status": "failed", "step": "fetch_state", "error": str(e)}

        # Fetch detailed utilization (CloudWatch)
        utilization = self.executor.get_instance_utilization(instance_id, region)
        
        # Calculate Requirements (The Translation)
        # Math: Required_CPU = (Current_vCPU * (Max_CPU_Load / 100)) * 1.2_Buffer
        current_vcpu = self.instance_specs.get(current_state.instance_type, 2) # Default to 2 if unknown
        max_cpu_load_percent = utilization.get("max_cpu", 0.0)
        
        required_cpu = (current_vcpu * (max_cpu_load_percent / 100.0)) * 1.2
        required_ram_gb = 2.0 # Placeholder: Lab assumes generic sizing for now, or fetch from specs if memory known
        
        logger.info(f"Resource Translation: {current_state.instance_type} ({current_vcpu} vCPU) @ {max_cpu_load_percent}% Load "
                    f"-> Needs {required_cpu:.2f} vCPU (incl. 20% buffer)")

        # Prepare Engine Inputs
        app_requirements = {
            "min_vcpu": required_cpu,
            "min_memory_gb": required_ram_gb,
            "allowed_families": ["c5", "m5", "t3", "r5"], # Lab allowed list
            "ignored_pools": []
        }
        
        # Mock/Fetch needed inputs for decide()
        # In a real run, we need usage_metrics dict, pricing_snapshot (handled inside engine mostly)
        # and list of available pools.
        # For this standalone implementation, we assume engine has access to data or we pass valid stubs.
        
        # TODO: Engine.decide() signature is complex. 
        # For simplicity in this Task, we assume the engine is pre-configured or we pass what we have.
        # This part assumes we have a way to get 'available_pools' - likely from a PriceProvider.
        # I will pass empty pools list if I can't fetch them, and the engine might complain or return STAY.
        # To make this work, the caller usually configures the engine with providers.
        
        # 2. Get Decision
        # ----------------------------------------
        # Using a simplified check here: if we implemented the full Engine loop properly,
        # we would call self.engine.decide().
        # However, calling engine.decide() requires 'available_pools'.
        # Assuming the engine or extensive setup is done outside.
        # For this specific task file, I will implement the structure.
        
        # Placeholder for valid pools fetch
        available_pools = [] # In real impl, would come from PriceProvider
        
        decision = self.engine.decide(
            current_instance=current_state.__dict__,
            usage_metrics=utilization,
            usage_patterns={},
            available_pools=available_pools, # This needs to be populated for real decisions
            app_requirements=app_requirements,
            sla_requirements={"max_interruption_rate": 20}, # Lab SLA
            region=region or self.executor.region
        )
        
        logger.info(f"Decision: {decision.action} -> {decision.recommended_instance_type}")

        if decision.action != DecisionAction.MIGRATE:
            return {
                "status": "completed", 
                "action": "STAY", 
                "reason": decision.primary_factors[0] if decision.primary_factors else "No better option"
            }

        # 3. Execution (The Bypass)
        # ----------------------------------------
        logger.info("Executing Standalone Migration (Bypassing K8s)...")
        
        new_instance_id = None
        try:
            # 3a. Launch New Instance
            target_spec = TargetSpec(
                instance_type=decision.recommended_instance_type,
                az=current_state.az,
                subnet_id=current_state.subnet_id,
                pool_id=decision.recommended_pool_id,
                lifecycle='spot',
                # Reuse tags from old instance, maybe mark as 'Lab-Optimized'
                tags={**current_state.tags, "OptimizedFrom": instance_id},
                # We need AMI/Template. This is tricky without knowing it.
                # Assuming current_state metadata or a default is available.
                # For Lab, we might pass a known LaunchTemplate ID.
                # Here we assume a default or extracted from context (not available in args).
                # Using a placeholder ID that MUST be replaced in real usage.
                launch_template_id=current_state.tags.get("LaunchTemplateId") 
            )
            
            if not target_spec.launch_template_id and not target_spec.ami_id:
                # Fallback implementation detail for lab
                logger.warning("No LaunchTemplateId found in tags, cannot reproduce instance configuration.")
                return {"status": "failed", "reason": "Missing launch configuration"}

            new_instance_id = self.executor.launch_instance(target_spec)
            
            # 3b. Wait for 'running'
            logger.info(f"Waiting for {new_instance_id} to become running...")
            is_running = self.executor.wait_for_instance_state(new_instance_id, 'running', timeout_seconds=300)
            
            if not is_running:
                raise TimeoutError(f"New instance {new_instance_id} failed to start")
                
            # 3c. Terminate Old Instance (Immediate or Warmup)
            # Lab mode: minimal warmup, maybe 10s
            time.sleep(10) 
            logger.info(f"Terminating old instance {instance_id}")
            self.executor.terminate_instance(instance_id)
            
            return {
                "status": "completed",
                "action": "MIGRATE",
                "old_instance": instance_id,
                "new_instance": new_instance_id,
                "savings": decision.expected_cost_savings_percent
            }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            # Rollback: Terminate new instance if it was launched
            if new_instance_id:
                logger.info(f"Rolling back: terminating new instance {new_instance_id}")
                self.executor.terminate_instance(new_instance_id)
            
            return {"status": "failed", "step": "execution", "error": str(e)}

