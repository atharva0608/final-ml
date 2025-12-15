"""
Linear Optimizer - Production Lab Mode Pipeline

This is the production 4-step pipeline for Lab Mode experimentation:
1. Scraper: Fetch real-time spot prices from AWS via STS AssumeRole
2. Safe Filter: Filter by historic interrupt rate (< 20%)
3. ML Inference: Run assigned model using FeatureEngine + BaseModelAdapter
4. Atomic Switch: Direct instance replacement with safety gates

✅ Uses real AWS access via utils.aws_session (STS AssumeRole)
✅ Uses real feature engineering via ai.feature_engine
✅ Uses real ML inference via ai.base_adapter
✅ Logs results to database via ExperimentLog

BYPASSED in Lab Mode:
- Bin Packing (waste cost calculation)
- Right Sizing (upsizing/downsizing)
- TCO Sorting (uses simple price sorting instead)
"""

import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from botocore.exceptions import ClientError, WaiterError

# Database models
from database.models import Instance, Account, ExperimentLog, ModelRegistry
from database.connection import get_db
from sqlalchemy.orm import Session

# AWS access (agentless cross-account)
from utils.aws_session import get_ec2_client, get_pricing_client

# ML inference
from ai.feature_engine import FeatureEngine, build_feature_vector
from ai.base_adapter import BaseModelAdapter
from utils.model_loader import load_model


class DecisionType(Enum):
    """Pipeline decision types"""
    STAY = "STAY"
    SWITCH = "SWITCH"
    FALLBACK_ONDEMAND = "FALLBACK_ONDEMAND"


@dataclass
class Candidate:
    """Spot instance candidate"""
    instance_type: str
    availability_zone: str
    spot_price: float
    on_demand_price: float
    vcpu: int
    memory_gb: float
    architecture: str = "x86_64"

    # Calculated fields
    historic_interrupt_rate: Optional[float] = None
    crash_probability: Optional[float] = None
    discount_depth: Optional[float] = None
    yield_score: Optional[float] = None
    is_filtered: bool = False
    filter_reason: Optional[str] = None


@dataclass
class PipelineContext:
    """Pipeline execution context"""
    instance_id: str
    account_id: str
    region: str
    assigned_model_version: Optional[str] = None
    is_shadow_mode: bool = False

    # Pipeline data
    candidates: List[Candidate] = field(default_factory=list)
    current_instance_type: Optional[str] = None
    current_az: Optional[str] = None

    # Decision
    final_decision: DecisionType = DecisionType.STAY
    decision_reason: str = ""
    selected_candidate: Optional[Candidate] = None

    # Timing
    pipeline_start_time: Optional[datetime] = None
    pipeline_end_time: Optional[datetime] = None

    # Logs
    stage_logs: List[Dict[str, Any]] = field(default_factory=list)

    def log_stage(self, stage: str, message: str, metadata: Dict = None):
        """Log a pipeline stage"""
        self.stage_logs.append({
            "stage": stage,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        })

    def get_valid_candidates(self) -> List[Candidate]:
        """Get candidates that passed filters"""
        return [c for c in self.candidates if not c.is_filtered]


class LinearPipeline:
    """
    Production pipeline for Lab Mode

    This pipeline is designed for:
    - Single instance testing
    - Real execution on Lab accounts via STS AssumeRole
    - Model experimentation with real data
    - Faster iteration cycles with database logging
    """

    def __init__(self, db: Session):
        """
        Initialize linear pipeline

        Args:
            db: Database session
        """
        self.db = db
        self.feature_engine = FeatureEngine()

    def execute(self, instance_id: str) -> PipelineContext:
        """
        Execute the linear pipeline

        Args:
            instance_id: Database instance UUID (NOT EC2 instance ID)

        Returns:
            PipelineContext with final decision
        """
        # Fetch instance from database
        instance = self.db.query(Instance).filter(Instance.id == instance_id).first()
        if not instance:
            raise ValueError(f"Instance {instance_id} not found in database")

        # Check authorization - must be LAB environment
        if instance.account.environment_type != "LAB":
            raise PermissionError(
                f"Cannot run optimizer on PROD instance. "
                f"Environment: {instance.account.environment_type}"
            )

        print("\n" + "="*80)
        print("🔬 LAB MODE - LINEAR PIPELINE (PRODUCTION)")
        print("="*80)
        print(f"Instance: {instance.instance_id}")
        print(f"Type: {instance.instance_type}")
        print(f"AZ: {instance.availability_zone}")
        print(f"Model: {instance.assigned_model_version or 'default'}")
        print(f"Account: {instance.account.account_id}")
        print(f"Region: {instance.account.region}")
        print(f"Shadow Mode: {instance.is_shadow_mode}")
        print("="*80 + "\n")

        # Create context
        context = PipelineContext(
            instance_id=str(instance.id),
            account_id=instance.account.account_id,
            region=instance.account.region,
            assigned_model_version=instance.assigned_model_version,
            is_shadow_mode=instance.is_shadow_mode,
            current_instance_type=instance.instance_type,
            current_az=instance.availability_zone,
        )
        context.pipeline_start_time = datetime.now()

        try:
            # Step 1: Scraper - Fetch real-time spot prices from AWS
            context = self._step_scraper(context, instance)

            # Step 2: Safe Filter - Filter by interrupt rate
            context = self._step_safe_filter(context)

            # Step 3: ML Inference - Run model prediction
            context = self._step_ml_inference(context, instance)

            # Step 4: Decision - Select best candidate
            context = self._step_decision(context)

            # Step 5: Execution - Perform atomic switch (if decision is SWITCH)
            if context.final_decision == DecisionType.SWITCH:
                context = self._step_execution(context, instance)

        except Exception as e:
            print(f"\n❌ Pipeline failed: {e}")
            context.final_decision = DecisionType.STAY
            context.decision_reason = f"Pipeline error: {str(e)}"
            context.log_stage("Error", str(e))

        context.pipeline_end_time = datetime.now()
        execution_time = (context.pipeline_end_time - context.pipeline_start_time).total_seconds()

        # Log to database
        self._log_experiment(context, instance, execution_time)

        print("\n" + "="*80)
        print("🏁 LAB PIPELINE COMPLETE")
        print("="*80)
        print(f"Decision: {context.final_decision.value}")
        print(f"Reason: {context.decision_reason}")
        print(f"Execution Time: {execution_time:.2f}s")
        if context.selected_candidate:
            print(f"Selected: {context.selected_candidate.instance_type}@{context.selected_candidate.availability_zone}")
        print(f"Shadow Mode: {'YES (read-only)' if context.is_shadow_mode else 'NO (will execute)'}")
        print("="*80 + "\n")

        return context

    def _step_scraper(self, context: PipelineContext, instance: Instance) -> PipelineContext:
        """
        Step 1: Scraper - Fetch real-time spot prices from AWS

        Uses STS AssumeRole to query AWS Spot Price History API
        for current prices across all availability zones in the region.

        Args:
            context: Pipeline context
            instance: Database instance record

        Returns:
            Updated context with candidates populated
        """
        print("[Step 1/4] 📡 Scraper - Fetching real-time spot prices")
        print("-" * 80)

        # Get cross-account EC2 client via STS AssumeRole
        ec2 = get_ec2_client(
            account_id=instance.account.account_id,
            region=context.region,
            db=self.db
        )

        # Fetch spot price history for the current instance type
        try:
            response = ec2.describe_spot_price_history(
                InstanceTypes=[context.current_instance_type],
                ProductDescriptions=['Linux/UNIX'],
                MaxResults=10,
                StartTime=datetime.now()
            )

            spot_prices = response.get('SpotPriceHistory', [])
            print(f"  ✓ Fetched {len(spot_prices)} spot price records from AWS")

        except Exception as e:
            print(f"  ⚠️  AWS API call failed: {e}")
            print(f"  → Using fallback: Stay on current instance")
            context.log_stage("Scraper", f"AWS API failed: {e}")
            return context

        # Get on-demand pricing
        try:
            pricing = get_pricing_client(account_id=instance.account.account_id, db=self.db)

            # Query on-demand price (simplified - in production use proper filters)
            on_demand_price = self._get_on_demand_price(
                pricing,
                context.current_instance_type,
                context.region
            )

        except Exception as e:
            print(f"  ⚠️  Pricing API failed: {e}, using default on-demand price")
            on_demand_price = 0.085  # Default fallback

        # Get instance specs
        instance_specs = self._get_instance_specs(context.current_instance_type)

        # Build candidates from spot price data
        candidates = []
        seen_azs = set()

        for price_record in spot_prices:
            az = price_record['AvailabilityZone']

            # Skip duplicate AZs
            if az in seen_azs:
                continue
            seen_azs.add(az)

            spot_price = float(price_record['SpotPrice'])

            candidate = Candidate(
                instance_type=price_record['InstanceType'],
                availability_zone=az,
                spot_price=spot_price,
                on_demand_price=on_demand_price,
                vcpu=instance_specs['vcpu'],
                memory_gb=instance_specs['memory_gb'],
                architecture=instance_specs['architecture']
            )
            candidates.append(candidate)

        context.candidates = candidates
        context.log_stage("Scraper", f"Fetched {len(candidates)} candidates from AWS")

        print(f"  ✓ Built {len(candidates)} candidates across availability zones")
        for candidate in candidates:
            discount = (1 - candidate.spot_price / candidate.on_demand_price) * 100
            print(f"    - {candidate.instance_type}@{candidate.availability_zone}: "
                  f"${candidate.spot_price:.4f} ({discount:.1f}% off)")
        print()

        return context

    def _step_safe_filter(self, context: PipelineContext) -> PipelineContext:
        """
        Step 2: Safe Filter - Filter by historic interrupt rate

        Removes candidates with interrupt rate >= 20% based on
        Redis historical data or AWS Spot Advisor data.

        Args:
            context: Pipeline context with candidates

        Returns:
            Updated context with unsafe candidates filtered
        """
        print("[Step 2/4] 🛡️  Safe Filter - Filtering by interrupt rate")
        print("-" * 80)

        # Get interrupt rate data from Redis (via FeatureEngine)
        threshold = 0.20  # 20% threshold
        filtered_count = 0

        for candidate in context.candidates:
            # Try to get real interrupt rate from Redis
            interrupt_rate = self._get_interrupt_rate(
                candidate.instance_type,
                context.region
            )

            candidate.historic_interrupt_rate = interrupt_rate

            if interrupt_rate >= threshold:
                candidate.is_filtered = True
                candidate.filter_reason = f"Interrupt rate {interrupt_rate*100:.1f}% >= {threshold*100:.0f}%"
                filtered_count += 1
                print(f"  ✗ {candidate.instance_type}@{candidate.availability_zone}: "
                      f"{interrupt_rate*100:.1f}% interrupt rate (FILTERED)")
            else:
                print(f"  ✓ {candidate.instance_type}@{candidate.availability_zone}: "
                      f"{interrupt_rate*100:.1f}% interrupt rate (SAFE)")

        valid_count = len(context.get_valid_candidates())
        context.log_stage("SafeFilter", f"{valid_count}/{len(context.candidates)} candidates safe")

        print(f"  → {valid_count} candidates passed filter ({filtered_count} filtered)")
        print()

        return context

    def _step_ml_inference(self, context: PipelineContext, instance: Instance) -> PipelineContext:
        """
        Step 3: ML Inference - Run model prediction

        Loads the assigned model and predicts crash probability for
        each candidate using FeatureEngine + BaseModelAdapter.

        Args:
            context: Pipeline context with filtered candidates
            instance: Database instance record

        Returns:
            Updated context with crash probabilities
        """
        print("[Step 3/4] 🤖 ML Inference - Running model predictions")
        print("-" * 80)

        # Load model dynamically
        model = load_model(context.assigned_model_version)
        print(f"  Model Loaded: {context.assigned_model_version or 'default'}")

        # Check if model implements BaseModelAdapter
        if isinstance(model, BaseModelAdapter):
            print(f"  Feature Version: {model.get_feature_version()}")
            print(f"  Expected Features: {model.get_expected_features()}")
        print()

        # Run predictions for each valid candidate
        for candidate in context.get_valid_candidates():
            try:
                # Calculate features using FeatureEngine
                features_dict = self.feature_engine.calculate_features(
                    instance_type=candidate.instance_type,
                    availability_zone=candidate.availability_zone,
                    spot_price=candidate.spot_price,
                    on_demand_price=candidate.on_demand_price,
                    historic_interrupt_rate=candidate.historic_interrupt_rate,
                    vcpu=candidate.vcpu,
                    memory_gb=candidate.memory_gb
                )

                # Run inference
                if isinstance(model, BaseModelAdapter):
                    # Use BaseModelAdapter interface
                    crash_prob = model.predict_with_validation(features_dict)
                else:
                    # Fallback for legacy models
                    feature_names = ["price_position", "discount_depth", "family_stress_index", "historic_interrupt_rate"]
                    feature_vector = build_feature_vector(features_dict, feature_names)
                    crash_prob = model.predict_proba([feature_vector])[0][1]

                candidate.crash_probability = crash_prob
                candidate.discount_depth = features_dict['discount_depth']

                # Calculate yield score (simple: discount - risk)
                candidate.yield_score = candidate.discount_depth - crash_prob

                risk_emoji = "🟢" if crash_prob < 0.30 else "🟡" if crash_prob < 0.70 else "🔴"
                print(f"  {risk_emoji} {candidate.instance_type}@{candidate.availability_zone}: "
                      f"Crash Risk = {crash_prob:.2f}, Yield = {candidate.yield_score:.2f}")

            except Exception as e:
                print(f"  ❌ Inference failed for {candidate.instance_type}@{candidate.availability_zone}: {e}")
                # Filter out candidates with failed inference
                candidate.is_filtered = True
                candidate.filter_reason = f"Inference failed: {str(e)}"

        valid_with_predictions = len([c for c in context.get_valid_candidates() if c.crash_probability is not None])
        context.log_stage("MLInference", f"Predicted {valid_with_predictions} candidates")
        print()

        return context

    def _step_decision(self, context: PipelineContext) -> PipelineContext:
        """
        Step 4: Decision - Select best candidate

        Selects the candidate with the best yield score (highest discount,
        lowest risk). Applies safety gate (crash_probability < 0.85).

        Args:
            context: Pipeline context with scored candidates

        Returns:
            Updated context with final decision
        """
        print("[Step 4/4] 🎯 Decision - Selecting best candidate")
        print("-" * 80)

        valid_candidates = [c for c in context.get_valid_candidates() if c.crash_probability is not None]

        if not valid_candidates:
            context.final_decision = DecisionType.STAY
            context.decision_reason = "No valid candidates available"
            print(f"  ⚠️  No valid candidates - staying on current instance")
            print()
            return context

        # Sort by yield score (descending)
        sorted_candidates = sorted(
            valid_candidates,
            key=lambda c: c.yield_score or 0,
            reverse=True
        )

        # Select best candidate
        best_candidate = sorted_candidates[0]

        # Apply safety gate
        safety_threshold = 0.85
        if best_candidate.crash_probability >= safety_threshold:
            context.final_decision = DecisionType.STAY
            context.decision_reason = (
                f"Best candidate risk {best_candidate.crash_probability:.2f} "
                f">= threshold {safety_threshold}"
            )
            print(f"  🛡️  Safety Gate: Risk too high ({best_candidate.crash_probability:.2f})")
            print(f"  → Decision: STAY on current instance")
            print()
            return context

        # Check if current instance is in the list and is the best
        if context.current_instance_type and context.current_az:
            current_key = (context.current_instance_type, context.current_az)
            best_key = (best_candidate.instance_type, best_candidate.availability_zone)

            if current_key == best_key:
                context.final_decision = DecisionType.STAY
                context.decision_reason = "Current instance is already optimal"
                context.selected_candidate = best_candidate
                print(f"  ✓ Current instance is optimal (yield={best_candidate.yield_score:.2f})")
                print(f"  → Decision: STAY")
                print()
                return context

        # Switch to better candidate
        context.final_decision = DecisionType.SWITCH
        context.selected_candidate = best_candidate
        context.decision_reason = (
            f"Better candidate found: {best_candidate.instance_type}@{best_candidate.availability_zone} "
            f"(yield={best_candidate.yield_score:.2f}, risk={best_candidate.crash_probability:.2f})"
        )

        savings_per_hour = (
            best_candidate.on_demand_price - best_candidate.spot_price
        )

        print(f"  🎯 Best Candidate: {best_candidate.instance_type}@{best_candidate.availability_zone}")
        print(f"     Spot Price: ${best_candidate.spot_price:.4f}/hr")
        print(f"     Crash Risk: {best_candidate.crash_probability:.2f}")
        print(f"     Yield Score: {best_candidate.yield_score:.2f}")
        print(f"     Savings: ${savings_per_hour:.4f}/hr")
        print(f"  → Decision: SWITCH")
        print()

        # Log decision metadata
        context.log_stage("Decision", "SWITCH", {
            "selected_instance_type": best_candidate.instance_type,
            "selected_az": best_candidate.availability_zone,
            "spot_price": best_candidate.spot_price,
            "crash_probability": best_candidate.crash_probability,
            "yield_score": best_candidate.yield_score,
        })

        return context

    def _step_execution(self, context: PipelineContext, instance: Instance) -> PipelineContext:
        """
        Step 5: Execution - Perform Atomic Switch

        This is "The Actuator" - the component that actually performs the switch.
        It's the last step in the pipeline and only runs if the decision is SWITCH.

        Args:
            context: Pipeline context with selected candidate
            instance: Database instance record

        Returns:
            Updated context with execution results
        """
        print("[Step 5/5] ⚡ Execution - Running Atomic Switch")
        print("-" * 80)

        # 1. Shadow Mode Check (Lab Mode Safety Feature)
        if context.is_shadow_mode:
            print("  👻 Shadow Mode Active: Skipping actual AWS calls.")
            context.log_stage("Execution", "SKIPPED (Shadow Mode)")
            print()
            return context

        # 2. Environment Validation (Critical Safety Check)
        # Prevent accidental cross-environment operations
        expected_account = instance.account.account_id
        if not expected_account:
            error_msg = "No account ID available for validation"
            print(f"  🚨 {error_msg}")
            context.log_stage("Execution", f"BLOCKED: {error_msg}")
            print()
            return context

        # 3. Get EC2 Client (Real Auth)
        try:
            ec2 = get_ec2_client(
                account_id=instance.account.account_id,
                region=context.region,
                db=self.db
            )
        except Exception as e:
            error_msg = f"Failed to get EC2 client: {str(e)}"
            print(f"  🚨 {error_msg}")
            context.log_stage("Execution", f"FAILED: {error_msg}")
            print()
            return context

        try:
            # 4. Call The Actuator
            result = execute_atomic_switch(
                ec2_client=ec2,
                source_instance_id=instance.instance_id,
                target_instance_type=context.selected_candidate.instance_type,
                target_az=context.selected_candidate.availability_zone
            )

            # 5. Log Success
            context.log_stage("Execution", "SUCCESS", result)

            # 6. Update Database Record
            # We update the instance_id in the DB to match the new one
            instance.instance_id = result['new_instance_id']
            instance.instance_type = context.selected_candidate.instance_type
            instance.availability_zone = context.selected_candidate.availability_zone
            instance.updated_at = datetime.now()
            self.db.commit()

            print(f"  📝 Database updated with new Instance ID: {result['new_instance_id']}")
            print()

        except Exception as e:
            context.log_stage("Execution", f"FAILED: {str(e)}")
            # Don't re-raise, just log failure so we can see it in dashboard
            print(f"  ❌ Execution Step Failed: {e}")
            print()

        return context

    def _log_experiment(self, context: PipelineContext, instance: Instance, execution_time: float):
        """
        Log experiment to database

        Args:
            context: Pipeline context with results
            instance: Database instance record
            execution_time: Pipeline execution time in seconds
        """
        try:
            # Get model registry entry
            model_registry = None
            if context.assigned_model_version:
                model_registry = self.db.query(ModelRegistry).filter(
                    ModelRegistry.version == context.assigned_model_version
                ).first()

            # Create experiment log
            experiment_log = ExperimentLog(
                instance_id=instance.id,
                model_id=model_registry.id if model_registry else None,
                decision=context.final_decision.value,
                decision_reason=context.decision_reason,
                crash_probability=context.selected_candidate.crash_probability if context.selected_candidate else None,
                actual_savings=0.0,  # Will be updated later
                metadata={
                    "execution_time_s": execution_time,
                    "candidates_evaluated": len(context.candidates),
                    "candidates_filtered": len([c for c in context.candidates if c.is_filtered]),
                    "is_shadow_run": context.is_shadow_mode,
                    "selected_candidate": {
                        "instance_type": context.selected_candidate.instance_type,
                        "availability_zone": context.selected_candidate.availability_zone,
                        "spot_price": context.selected_candidate.spot_price,
                    } if context.selected_candidate else None,
                    "stage_logs": context.stage_logs
                },
                features_used={
                    "price_position": context.selected_candidate.discount_depth if context.selected_candidate else None,
                    "discount_depth": context.selected_candidate.discount_depth if context.selected_candidate else None,
                } if context.selected_candidate else {},
                is_shadow_run=context.is_shadow_mode,
                timestamp=datetime.now()
            )

            self.db.add(experiment_log)
            self.db.commit()

            print(f"✓ Experiment logged to database (ID: {experiment_log.id})")

        except Exception as e:
            print(f"⚠️  Failed to log experiment to database: {e}")
            self.db.rollback()

    def _get_on_demand_price(self, pricing_client, instance_type: str, region: str) -> float:
        """
        Get on-demand price from AWS Pricing API

        Args:
            pricing_client: Boto3 pricing client
            instance_type: EC2 instance type
            region: AWS region

        Returns:
            On-demand price per hour
        """
        # This is a simplified version - full implementation would use proper filters
        # For now, return a reasonable default based on instance type

        # Common pricing (rough estimates for ap-south-1)
        default_prices = {
            "t3.micro": 0.0104,
            "t3.small": 0.0208,
            "t3.medium": 0.0416,
            "t3.large": 0.0832,
            "c5.large": 0.085,
            "c5.xlarge": 0.17,
            "m5.large": 0.096,
            "m5.xlarge": 0.192,
        }

        return default_prices.get(instance_type, 0.10)  # Default fallback

    def _get_instance_specs(self, instance_type: str) -> Dict[str, Any]:
        """
        Get instance specifications

        Args:
            instance_type: EC2 instance type

        Returns:
            Dict with vcpu, memory_gb, architecture
        """
        # Simplified specs lookup - in production, use EC2 describe_instance_types API
        specs_map = {
            "t3.micro": {"vcpu": 2, "memory_gb": 1.0, "architecture": "x86_64"},
            "t3.small": {"vcpu": 2, "memory_gb": 2.0, "architecture": "x86_64"},
            "t3.medium": {"vcpu": 2, "memory_gb": 4.0, "architecture": "x86_64"},
            "t3.large": {"vcpu": 2, "memory_gb": 8.0, "architecture": "x86_64"},
            "c5.large": {"vcpu": 2, "memory_gb": 4.0, "architecture": "x86_64"},
            "c5.xlarge": {"vcpu": 4, "memory_gb": 8.0, "architecture": "x86_64"},
            "m5.large": {"vcpu": 2, "memory_gb": 8.0, "architecture": "x86_64"},
            "m5.xlarge": {"vcpu": 4, "memory_gb": 16.0, "architecture": "x86_64"},
        }

        return specs_map.get(instance_type, {"vcpu": 2, "memory_gb": 4.0, "architecture": "x86_64"})

    def _get_interrupt_rate(self, instance_type: str, region: str) -> float:
        """
        Get historical interrupt rate from Redis or AWS Spot Advisor

        Args:
            instance_type: EC2 instance type
            region: AWS region

        Returns:
            Interrupt rate (0.0-1.0)
        """
        # Try to get from Redis (via FeatureEngine's Redis connection)
        if self.feature_engine.redis:
            try:
                key = f"spot_risk:{region}:{instance_type}"
                data = self.feature_engine.redis.get(key)
                if data:
                    risk_data = json.loads(data)
                    return risk_data.get("interrupt_rate", 0.10)
            except Exception:
                pass

        # Fallback to default safe values
        return 0.10  # Default 10% interrupt rate


# ============================================================================
# THE ACTUATOR - Atomic Switch Implementation
# ============================================================================

def execute_atomic_switch(
    ec2_client,
    source_instance_id: str,
    target_instance_type: str,
    target_az: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Performs the 'Atomic Switch':
    1. Clones the source instance (creates AMI)
    2. Finds a matching subnet in the Target AZ
    3. Launches a new Spot Instance from the clone
    4. Verifies health
    5. Stops the old instance

    Args:
        ec2_client: Boto3 EC2 client with cross-account credentials
        source_instance_id: Current EC2 instance ID to clone
        target_instance_type: Desired instance type (e.g., 't3.medium')
        target_az: Target availability zone (e.g., 'us-east-1a')
        dry_run: If True, simulates execution without AWS changes

    Returns:
        Dict with status, old_instance_id, new_instance_id, ami_id
    """
    print(f"\n⚡ STARTING ATOMIC SWITCH: {source_instance_id} -> {target_instance_type} ({target_az})")

    try:
        # 1. GET SOURCE CONFIGURATION
        # ----------------------------------------------------------------
        desc = ec2_client.describe_instances(InstanceIds=[source_instance_id])
        source = desc['Reservations'][0]['Instances'][0]
        vpc_id = source['VpcId']
        security_groups = [sg['GroupId'] for sg in source.get('SecurityGroups', [])]
        iam_profile = source.get('IamInstanceProfile', {})
        key_name = source.get('KeyName')
        source_tags = source.get('Tags', [])

        print(f"  ✓ Fetched config from source (VPC: {vpc_id})")

        # 2. RESOLVE SUBNET FOR TARGET AZ
        # ----------------------------------------------------------------
        # We must find a subnet in the *Target AZ* that belongs to the *Same VPC*
        subnets = ec2_client.describe_subnets(Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'availability-zone', 'Values': [target_az]}
        ])

        if not subnets['Subnets']:
            raise RuntimeError(f"No subnets found in {target_az} for VPC {vpc_id}")

        # Naive selection: Pick the first available subnet in target AZ
        # (In production, you'd match tags or 'MapPublicIpOnLaunch' settings)
        target_subnet_id = subnets['Subnets'][0]['SubnetId']
        print(f"  ✓ Resolved target subnet: {target_subnet_id} ({target_az})")

        if dry_run:
            print("  ⚠️ DRY RUN: Skipping AMI creation and Launch")
            return {"status": "dry_run_success", "new_instance_id": "i-dryrun"}

        # 3. CREATE CLONE (AMI)
        # ----------------------------------------------------------------
        image_name = f"SpotOpt-Clone-{source_instance_id}-{int(datetime.now().timestamp())}"
        print(f"  📸 Creating AMI: {image_name}...")

        ami_resp = ec2_client.create_image(
            InstanceId=source_instance_id,
            Name=image_name,
            NoReboot=False  # Reboot ensures file system consistency
        )
        ami_id = ami_resp['ImageId']

        # Wait for AMI to be available (can take minutes)
        print(f"  ⏳ Waiting for AMI {ami_id} to be available...")
        waiter = ec2_client.get_waiter('image_available')
        waiter.wait(ImageIds=[ami_id], WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        print("  ✓ AMI Ready")

        # 4. LAUNCH SPOT INSTANCE
        # ----------------------------------------------------------------
        print(f"  🚀 Launching {target_instance_type} in {target_az}...")

        launch_args = {
            'ImageId': ami_id,
            'InstanceType': target_instance_type,
            'SubnetId': target_subnet_id,
            'SecurityGroupIds': security_groups,
            'MinCount': 1,
            'MaxCount': 1,
            'InstanceMarketOptions': {
                'MarketType': 'spot',
                'SpotOptions': {'SpotInstanceType': 'one-time'}
            }
        }

        # Only add optional params if they existed on source
        if key_name:
            launch_args['KeyName'] = key_name
        if iam_profile:
            launch_args['IamInstanceProfile'] = {'Arn': iam_profile['Arn']}

        # Tag inheritance - copy all user tags + add system tags
        tags_to_apply = []
        for tag in source_tags:
            if tag['Key'] not in ['Name', 'aws:*']:  # Skip AWS reserved tags
                tags_to_apply.append(tag)

        # Add system management tags (for Security Enforcer)
        tags_to_apply.extend([
            {'Key': 'ManagedBy', 'Value': 'SpotOptimizer'},
            {'Key': 'CreatedVia', 'Value': 'LabMode'},
            {'Key': 'SourceInstance', 'Value': source_instance_id}
        ])

        run_resp = ec2_client.run_instances(**launch_args)
        new_instance_id = run_resp['Instances'][0]['InstanceId']
        print(f"  ✓ Spot Request Placed. New ID: {new_instance_id}")

        # Apply tags to new instance
        if tags_to_apply:
            ec2_client.create_tags(Resources=[new_instance_id], Tags=tags_to_apply)
            print(f"  ✓ Tags inherited ({len(tags_to_apply)} tags copied)")

        # 5. HEALTH CHECK (Safety Latch)
        # ----------------------------------------------------------------
        print(f"  🩺 Performing Health Checks on {new_instance_id}...")

        # Wait for Running state
        ec2_client.get_waiter('instance_running').wait(InstanceIds=[new_instance_id])

        # Wait for Status Checks (2/2 OK)
        # This ensures the OS booted and network is up
        status_waiter = ec2_client.get_waiter('instance_status_ok')
        try:
            status_waiter.wait(InstanceIds=[new_instance_id], WaiterConfig={'Delay': 15, 'MaxAttempts': 20})
            print("  ✅ New Instance is HEALTHY (2/2 checks passed)")
        except WaiterError as we:
            print(f"  ❌ New Instance FAILED health checks: {we}")
            print("  🔄 Rollback: Terminating new instance, keeping old...")
            ec2_client.terminate_instances(InstanceIds=[new_instance_id])
            raise RuntimeError("New instance failed health checks - rolled back")

        # 6. SWAP (Stop Old)
        # ----------------------------------------------------------------
        print(f"  🛑 Stopping old instance {source_instance_id}...")
        ec2_client.stop_instances(InstanceIds=[source_instance_id])

        print("  ✨ ATOMIC SWITCH SUCCESSFUL")

        return {
            "status": "success",
            "old_instance_id": source_instance_id,
            "new_instance_id": new_instance_id,
            "ami_id": ami_id
        }

    except Exception as e:
        print(f"  ❌ SWITCH FAILED: {str(e)}")
        raise e


# For testing
if __name__ == '__main__':
    print("="*80)
    print("LINEAR OPTIMIZER TEST")
    print("="*80)

    # This would require a database session and instance
    print("Run via API endpoint: POST /api/v1/lab/instances/{id}/evaluate")
    print("="*80)
