"""
Optimizer Task - Pipeline Router for Production Lab Mode

This module contains the main optimization cycle that routes to the
appropriate pipeline based on instance configuration:
- LINEAR: Single-instance atomic switch (Lab Mode)
- CLUSTER: Multi-instance batch optimization
- KUBERNETES: Kubernetes-aware node optimization

This is the "fork in the road" that enables different execution modes.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

# Database imports
from database.models import Instance, Account
from database.connection import get_db


def get_instance_config(instance_id: str, db: Session) -> Optional[Instance]:
    """
    Fetch instance configuration from database

    Args:
        instance_id: Database instance UUID (NOT EC2 instance ID)
        db: Database session

    Returns:
        Instance model object or None if not found
    """
    instance = db.query(Instance).filter(Instance.id == instance_id).first()
    return instance


def run_cluster_pipeline(instance: Instance, db: Session) -> Dict[str, Any]:
    """
    Run the cluster batch optimization pipeline (CLUSTER mode)

    This pipeline optimizes multiple instances in batch:
    1. Fetch all eligible instances in the cluster
    2. Run optimization analysis across the cluster
    3. Apply batch optimizations with parallelization
    4. Track global risk contagion

    Args:
        instance: Database instance model
        db: Database session

    Returns:
        Execution result dict
    """
    print(f"🏭 Running CLUSTER Pipeline for instance {instance.instance_id}")
    print(f"   Account: {instance.account.account_id}")
    print(f"   Region: {instance.account.region}")
    print()

    # TODO: Import ClusterPipeline when implemented
    # from pipelines.cluster_optimizer import ClusterPipeline
    # cluster_pipeline = ClusterPipeline(db=db)
    # result = cluster_pipeline.execute(instance_id=str(instance.id))

    print("⚠️  ClusterPipeline not yet implemented")
    print("   This will be implemented to support batch optimization")
    print()

    return {
        "status": "not_implemented",
        "pipeline": "CLUSTER",
        "message": "ClusterPipeline is planned for future implementation"
    }


def run_linear_pipeline(instance: Instance, db: Session):
    """
    Run the simplified Lab Mode pipeline (LINEAR mode)

    This is a streamlined pipeline for single-instance optimization:
    1. Scraper (fetch real-time spot prices)
    2. Safe Filter (historic interrupt rate < 20%)
    3. ML Inference (with assigned model)
    4. Decision (select best candidate)
    5. Atomic Switch (direct instance replacement)

    BYPASSED in Linear Mode:
    - Bin Packing (no waste cost calculation)
    - Right Sizing (no upsizing/downsizing)
    - Global risk contagion (Lab Mode only)

    Args:
        instance: Database instance model
        db: Database session

    Returns:
        PipelineContext with final decision
    """
    print(f"🔬 Running LINEAR Pipeline for {instance.instance_id}")
    print(f"   Model: {instance.assigned_model_version or 'default'}")
    print(f"   Region: {instance.account.region}")
    print(f"   Shadow Mode: {instance.is_shadow_mode}")
    print()

    # Import lab-specific pipeline
    from pipelines.linear_optimizer import LinearPipeline

    # Create and execute linear pipeline
    linear_pipeline = LinearPipeline(db=db)
    context = linear_pipeline.execute(instance_id=str(instance.id))

    print(f"✓ Linear pipeline completed")
    return context


def run_kubernetes_pipeline(instance: Instance, db: Session) -> Dict[str, Any]:
    """
    Run Kubernetes-aware node optimization pipeline

    This pipeline is specifically designed for K8s worker node optimization:
    1. Check cluster membership and health
    2. Cordon the node (mark unschedulable)
    3. Drain pods respecting PodDisruptionBudgets
    4. Perform atomic EC2 switch
    5. Wait for new node to join cluster
    6. Uncordon and verify pod rescheduling

    Args:
        instance: Database instance model (must have cluster_membership)
        db: Database session

    Returns:
        Execution result dict
    """
    print(f"☸️  Running KUBERNETES Pipeline for {instance.instance_id}")
    print(f"   Cluster: {instance.cluster_membership.get('cluster_name') if instance.cluster_membership else 'unknown'}")
    print(f"   Region: {instance.account.region}")
    print()

    # TODO: Import KubernetesPipeline when implemented
    # from pipelines.kubernetes_optimizer import KubernetesPipeline
    # k8s_pipeline = KubernetesPipeline(db=db)
    # result = k8s_pipeline.execute(instance_id=str(instance.id))

    print("⚠️  KubernetesPipeline not yet implemented")
    print("   This will be implemented to support K8s node optimization")
    print()

    return {
        "status": "not_implemented",
        "pipeline": "KUBERNETES",
        "message": "KubernetesPipeline is planned for future implementation"
    }


def run_optimization_cycle(instance_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Main optimization task - THE ROUTER

    This is the entry point that determines which pipeline to run
    based on instance configuration from the database.

    Decision Flow:
    1. Fetch instance from database
    2. Check pipeline_mode field
    3. Route to appropriate pipeline:
       - LINEAR → Single-instance atomic switch (Lab Mode)
       - CLUSTER → Batch cluster optimization (Production)
       - KUBERNETES → Kubernetes-aware node optimization

    Args:
        instance_id: Database instance UUID (NOT EC2 instance ID)
        db: Database session (optional, will create if not provided)

    Returns:
        Execution summary with decision, timing, and metadata
    """
    print("\n" + "="*80)
    print("🎯 OPTIMIZATION CYCLE STARTED")
    print("="*80)
    print(f"Instance UUID: {instance_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*80 + "\n")

    # Get database session
    if db is None:
        db = next(get_db())

    # Step 1: Fetch instance from database
    instance = get_instance_config(instance_id, db)

    if not instance:
        error_msg = f"Instance {instance_id} not found in database"
        print(f"❌ {error_msg}")
        return {
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }

    pipeline_mode = instance.pipeline_mode or "LINEAR"

    print(f"📋 Configuration Loaded:")
    print(f"   Pipeline Mode: {pipeline_mode}")
    print(f"   Instance ID (EC2): {instance.instance_id}")
    print(f"   Instance Type: {instance.instance_type}")
    print(f"   Availability Zone: {instance.availability_zone}")
    print(f"   Assigned Model: {instance.assigned_model_version or 'default'}")
    print(f"   Account: {instance.account.account_id}")
    print(f"   Region: {instance.account.region}")
    print(f"   Shadow Mode: {instance.is_shadow_mode}")
    print()

    # Step 2: THE FORK - Choose which pipeline to run
    start_time = datetime.now()
    result = None

    try:
        if pipeline_mode == 'LINEAR':
            # Linear Mode: Single-instance atomic switch
            result = run_linear_pipeline(instance, db)
        elif pipeline_mode == 'CLUSTER':
            # Cluster Mode: Batch optimization
            result = run_cluster_pipeline(instance, db)
        elif pipeline_mode == 'KUBERNETES':
            # Kubernetes Mode: K8s-aware optimization
            result = run_kubernetes_pipeline(instance, db)
        else:
            # Default to LINEAR for unknown modes
            print(f"⚠️  Unknown pipeline mode '{pipeline_mode}', defaulting to LINEAR")
            result = run_linear_pipeline(instance, db)

    except Exception as e:
        print(f"\n❌ Pipeline execution failed: {e}")
        result = {
            "status": "error",
            "error": str(e),
            "pipeline_mode": pipeline_mode
        }

    end_time = datetime.now()
    execution_time_ms = (end_time - start_time).total_seconds() * 1000

    # Step 3: Build execution summary
    summary = {
        "instance_id": instance_id,
        "ec2_instance_id": instance.instance_id,
        "pipeline_mode": pipeline_mode,
        "execution_time_ms": execution_time_ms,
        "timestamp": end_time.isoformat(),
        "result": result
    }

    # Add decision details if available (for LINEAR pipeline)
    if hasattr(result, 'final_decision'):
        summary["decision"] = result.final_decision.value
        summary["reason"] = result.decision_reason
        if result.selected_candidate:
            summary["selected_candidate"] = {
                "instance_type": result.selected_candidate.instance_type,
                "availability_zone": result.selected_candidate.availability_zone,
                "spot_price": result.selected_candidate.spot_price,
                "crash_probability": result.selected_candidate.crash_probability,
            }

    print("\n" + "="*80)
    print("🏁 OPTIMIZATION CYCLE COMPLETE")
    print("="*80)
    print(f"Pipeline: {pipeline_mode}")
    if hasattr(result, 'final_decision'):
        print(f"Decision: {result.final_decision.value}")
    print(f"Execution Time: {execution_time_ms:.2f}ms")
    print("="*80 + "\n")

    return summary


# For testing/debugging
if __name__ == '__main__':
    print("="*80)
    print("OPTIMIZER TASK TEST")
    print("="*80)
    print("\nThis module routes optimization requests to the appropriate pipeline:")
    print("  - LINEAR: Single-instance atomic switch (Lab Mode)")
    print("  - CLUSTER: Batch cluster optimization (Production)")
    print("  - KUBERNETES: Kubernetes-aware node optimization")
    print("\nUsage:")
    print("  from workers.optimizer_task import run_optimization_cycle")
    print("  result = run_optimization_cycle(instance_uuid, db)")
    print("\nOr via API endpoint:")
    print("  POST /api/v1/lab/instances/{instance_id}/evaluate")
    print("="*80)
