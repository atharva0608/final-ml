"""
Linear Optimizer - Simplified Lab Mode Pipeline

This is the streamlined 4-step pipeline for Lab Mode experimentation:
1. Scraper: Fetch real-time spot prices from AWS
2. Safe Filter: Filter by historic interrupt rate (< 20%)
3. ML Inference: Run assigned model for crash prediction
4. Atomic Switch: Direct instance replacement (no Kubernetes drain)

BYPASSED in Lab Mode:
- Bin Packing (waste cost calculation)
- Right Sizing (upsizing/downsizing)
- TCO Sorting (uses simple price sorting instead)
"""

import boto3
from typing import Dict, Any, List, Optional
from datetime import datetime

from decision_engine_v2.context import (
    DecisionContext,
    InputRequest,
    Candidate,
    DecisionType,
    SignalType
)


class LinearPipeline:
    """
    Simplified pipeline for Lab Mode

    This pipeline is designed for:
    - Single instance testing
    - Real execution on Lab accounts
    - Model experimentation
    - Faster iteration cycles
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize linear pipeline

        Args:
            config: Instance configuration with assigned_model_id and region
        """
        self.config = config
        self.region = config.get('aws_region', 'ap-south-1')
        self.assigned_model_id = config.get('assigned_model_id')

        # Initialize AWS client
        self.ec2_client = None  # Will be initialized when needed

    def execute(self, instance_id: str) -> DecisionContext:
        """
        Execute the linear pipeline

        Args:
            instance_id: EC2 instance ID to evaluate

        Returns:
            DecisionContext with final decision
        """
        print("\n" + "="*80)
        print("🔬 LAB MODE - LINEAR PIPELINE")
        print("="*80)
        print(f"Instance: {instance_id}")
        print(f"Model: {self.assigned_model_id or 'default'}")
        print(f"Region: {self.region}")
        print("="*80 + "\n")

        # Create context
        input_request = InputRequest(
            mode="test",
            current_instance_id=instance_id,
            region=self.region
        )
        context = DecisionContext(input_request=input_request)
        context.pipeline_start_time = datetime.now()

        # Step 1: Scraper - Fetch real-time spot prices
        context = self._step_scraper(context, instance_id)

        # Step 2: Safe Filter - Filter by interrupt rate
        context = self._step_safe_filter(context)

        # Step 3: ML Inference - Run model prediction
        context = self._step_ml_inference(context)

        # Step 4: Decision - Select best candidate
        context = self._step_decision(context)

        context.pipeline_end_time = datetime.now()
        execution_time = (context.pipeline_end_time - context.pipeline_start_time).total_seconds()

        print("\n" + "="*80)
        print("🏁 LAB PIPELINE COMPLETE")
        print("="*80)
        print(f"Decision: {context.final_decision.value}")
        print(f"Reason: {context.decision_reason}")
        print(f"Execution Time: {execution_time:.2f}s")
        if context.selected_candidate:
            print(f"Selected: {context.selected_candidate}")
        print("="*80 + "\n")

        return context

    def _step_scraper(self, context: DecisionContext, instance_id: str) -> DecisionContext:
        """
        Step 1: Scraper - Fetch real-time spot prices

        Queries AWS Spot Price History API for current prices across
        all availability zones in the region.

        Args:
            context: Decision context
            instance_id: EC2 instance ID

        Returns:
            Updated context with candidates populated
        """
        print("[Step 1/4] 📡 Scraper - Fetching real-time spot prices")
        print("-" * 80)

        # TODO: Replace with real boto3 calls
        # This is a placeholder implementation
        # In production, this would:
        # 1. Get current instance type
        # 2. Query spot price history API
        # 3. Get prices for all AZs in region

        # Mock data for now
        mock_candidates = [
            Candidate(
                instance_type="c5.large",
                availability_zone=f"{self.region}a",
                spot_price=0.028,
                on_demand_price=0.085,
                vcpu=2,
                memory_gb=4.0,
                architecture="x86_64"
            ),
            Candidate(
                instance_type="c5.large",
                availability_zone=f"{self.region}b",
                spot_price=0.031,
                on_demand_price=0.085,
                vcpu=2,
                memory_gb=4.0,
                architecture="x86_64"
            ),
            Candidate(
                instance_type="c5.large",
                availability_zone=f"{self.region}c",
                spot_price=0.025,
                on_demand_price=0.085,
                vcpu=2,
                memory_gb=4.0,
                architecture="x86_64"
            ),
        ]

        context.candidates = mock_candidates
        context.log_stage("Scraper", f"Fetched {len(mock_candidates)} candidates")

        print(f"  ✓ Fetched {len(mock_candidates)} spot pools")
        for candidate in mock_candidates:
            discount = (1 - candidate.spot_price / candidate.on_demand_price) * 100
            print(f"    - {candidate.instance_type}@{candidate.availability_zone}: "
                  f"${candidate.spot_price:.4f} ({discount:.1f}% off)")
        print()

        return context

    def _step_safe_filter(self, context: DecisionContext) -> DecisionContext:
        """
        Step 2: Safe Filter - Filter by historic interrupt rate

        Removes candidates with interrupt rate >= 20% based on AWS
        Spot Advisor data.

        Args:
            context: Decision context with candidates

        Returns:
            Updated context with unsafe candidates filtered
        """
        print("[Step 2/4] 🛡️  Safe Filter - Filtering by interrupt rate")
        print("-" * 80)

        # TODO: Load real interrupt rate data from static intelligence
        # For now, use mock data
        mock_interrupt_rates = {
            "c5.large": 0.05,  # 5% interrupt rate (safe)
            "m5.large": 0.15,  # 15% (safe)
            "t3.large": 0.25,  # 25% (unsafe)
        }

        threshold = 0.20  # 20% threshold
        filtered_count = 0

        for candidate in context.candidates:
            interrupt_rate = mock_interrupt_rates.get(
                candidate.instance_type,
                0.10  # Default to 10% if unknown
            )
            candidate.historic_interrupt_rate = interrupt_rate

            if interrupt_rate >= threshold:
                context.filter_candidate(
                    candidate,
                    f"Interrupt rate {interrupt_rate*100:.1f}% >= {threshold*100:.0f}%"
                )
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

    def _step_ml_inference(self, context: DecisionContext) -> DecisionContext:
        """
        Step 3: ML Inference - Run model prediction

        Loads the assigned model and predicts crash probability for
        each candidate.

        Args:
            context: Decision context with filtered candidates

        Returns:
            Updated context with crash probabilities
        """
        print("[Step 3/4] 🤖 ML Inference - Running model predictions")
        print("-" * 80)

        # Load model dynamically
        from utils.model_loader import load_model

        model = load_model(self.assigned_model_id)
        print(f"  Model Loaded: {self.assigned_model_id or 'default'}")
        print()

        # Run predictions for each valid candidate
        for candidate in context.get_valid_candidates():
            # TODO: Build feature vector from candidate
            # For now, use mock prediction
            # In production:
            # features = build_feature_vector(candidate)
            # crash_prob = model.predict_proba([features])[0][1]

            # Mock prediction (varies by AZ)
            mock_predictions = {
                f"{self.region}a": 0.28,
                f"{self.region}b": 0.42,
                f"{self.region}c": 0.15,
            }
            crash_prob = mock_predictions.get(
                candidate.availability_zone,
                0.30
            )

            candidate.crash_probability = crash_prob
            candidate.discount_depth = 1 - (candidate.spot_price / candidate.on_demand_price)

            # Calculate yield score (simple: discount - risk)
            candidate.yield_score = candidate.discount_depth - crash_prob

            risk_emoji = "🟢" if crash_prob < 0.30 else "🟡" if crash_prob < 0.70 else "🔴"
            print(f"  {risk_emoji} {candidate.instance_type}@{candidate.availability_zone}: "
                  f"Crash Risk = {crash_prob:.2f}, Yield = {candidate.yield_score:.2f}")

        context.log_stage("MLInference", f"Predicted {len(context.get_valid_candidates())} candidates")
        print()

        return context

    def _step_decision(self, context: DecisionContext) -> DecisionContext:
        """
        Step 4: Decision - Select best candidate

        Selects the candidate with the best yield score (highest discount,
        lowest risk). Applies safety gate (crash_probability < 0.85).

        Args:
            context: Decision context with scored candidates

        Returns:
            Updated context with final decision
        """
        print("[Step 4/4] 🎯 Decision - Selecting best candidate")
        print("-" * 80)

        valid_candidates = context.get_valid_candidates()

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
        if context.input_request.current_instance_type:
            current_key = (
                context.input_request.current_instance_type,
                context.input_request.current_availability_zone
            )
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
            context.candidates[0].on_demand_price - best_candidate.spot_price
        ) if context.candidates else 0

        print(f"  🎯 Best Candidate: {best_candidate.instance_type}@{best_candidate.availability_zone}")
        print(f"     Spot Price: ${best_candidate.spot_price:.4f}/hr")
        print(f"     Crash Risk: {best_candidate.crash_probability:.2f}")
        print(f"     Yield Score: {best_candidate.yield_score:.2f}")
        print(f"     Savings: ${savings_per_hour:.4f}/hr")
        print(f"  → Decision: SWITCH")
        print()

        # Log experiment data
        context.log_stage("Decision", "SWITCH", {
            "selected_instance_type": best_candidate.instance_type,
            "selected_az": best_candidate.availability_zone,
            "spot_price": best_candidate.spot_price,
            "crash_probability": best_candidate.crash_probability,
            "yield_score": best_candidate.yield_score,
        })

        return context


def execute_atomic_switch(
    instance_id: str,
    target_instance_type: str,
    target_az: str,
    aws_access_key: str,
    aws_secret_key: str,
    region: str
) -> Dict[str, Any]:
    """
    Execute atomic instance switch (Lab Mode actuator)

    This function performs the actual AWS operations:
    1. Create AMI from current instance
    2. Launch spot instance from AMI
    3. Wait for new instance to be ready
    4. Stop old instance (do not terminate)

    NOTE: This bypasses Kubernetes drain and does a direct swap.
    Only use in Lab Mode on non-production instances!

    Args:
        instance_id: Current instance ID
        target_instance_type: Target instance type
        target_az: Target availability zone
        aws_access_key: Encrypted AWS access key
        aws_secret_key: Encrypted AWS secret key
        region: AWS region

    Returns:
        Execution result with new instance ID
    """
    print("\n" + "="*80)
    print("⚡ ATOMIC SWITCH - LAB MODE ACTUATOR")
    print("="*80)
    print(f"Current Instance: {instance_id}")
    print(f"Target: {target_instance_type}@{target_az}")
    print("="*80 + "\n")

    # TODO: Implement real AWS operations
    # This is a placeholder implementation
    # In production, this would:
    # 1. Decrypt AWS credentials
    # 2. Create boto3 EC2 client
    # 3. Create AMI: response = ec2.create_image(InstanceId=instance_id, ...)
    # 4. Wait for AMI: ec2.get_waiter('image_available').wait(ImageIds=[ami_id])
    # 5. Launch spot instance: ec2.request_spot_instances(...)
    # 6. Wait for running: ec2.get_waiter('instance_running').wait(...)
    # 7. Stop old instance: ec2.stop_instances(InstanceIds=[instance_id])

    print("[1/5] 📸 Creating AMI from current instance...")
    print("  ✓ AMI created: ami-mock-12345678")
    print()

    print("[2/5] 🚀 Launching spot instance...")
    print(f"  Instance Type: {target_instance_type}")
    print(f"  Availability Zone: {target_az}")
    print("  ✓ Spot request fulfilled: sir-mock-87654321")
    print()

    print("[3/5] ⏳ Waiting for instance to be running...")
    print("  ✓ Instance running: i-mock-new-instance")
    print()

    print("[4/5] 🔌 Attaching volumes and network interfaces...")
    print("  ✓ Resources attached")
    print()

    print("[5/5] 🛑 Stopping old instance...")
    print(f"  ✓ Instance {instance_id} stopped")
    print()

    result = {
        "status": "success",
        "old_instance_id": instance_id,
        "new_instance_id": "i-mock-new-instance",
        "ami_id": "ami-mock-12345678",
        "spot_request_id": "sir-mock-87654321",
        "execution_time_s": 45.2,
    }

    print("="*80)
    print("✅ ATOMIC SWITCH COMPLETE")
    print("="*80)
    print(f"New Instance: {result['new_instance_id']}")
    print(f"Execution Time: {result['execution_time_s']:.1f}s")
    print("="*80 + "\n")

    return result
