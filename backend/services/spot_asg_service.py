"""
SpotASGService — No-Karpenter Spot Instance Mode
=================================================
EXEC-08 / EXEC-09: Enables spot instances on EKS managed nodegroups WITHOUT
Karpenter by updating the ASG's MixedInstancesPolicy.

USE CASE
--------
Some clusters cannot or should not use Karpenter:
  - Managed nodegroups with strict company policy against custom node provisioners
  - Clusters on EKS versions < 1.21 (Karpenter unsupported)
  - Clusters where the customer already has complex ASG lifecycle hooks
  - Clusters where Karpenter installation is blocked by SCPs

STRATEGY
---------
Instead of Karpenter, this service updates the existing EKS managed nodegroup's
Auto Scaling Group to use a MixedInstancesPolicy:

  BEFORE:
    - 100% on-demand instances
    - Single instance type (e.g. m5.large)

  AFTER:
    - 1 on-demand base (always guaranteed)
    - 70% spot above the base (configurable)
    - Multiple compatible instance types (diversity → interruption resilience)
    - AllocationStrategy: price-capacity-optimized (AWS picks safest cheapest spot)

COST vs KARPENTER COMPARISON
------------------------------
  Karpenter:
    + Bin-packs pods optimally (fewest nodes, smallest sizes)
    + Provisions spot in seconds (not minutes like ASG scale-out)
    + Supports full node lifecycle (cordon, drain, terminate, replace)
    - Requires IAM roles, OIDC, SQS, EventBridge setup

  ASG MixedInstancesPolicy (this service):
    + Zero infrastructure changes (no new IAM roles, SQS, OIDC)
    + Works on ANY EKS version (managed nodegroups ≥ EKS 1.14)
    + Idempotent: update ASG, revert ASG — no cleanup needed
    - No bin-packing (existing node sizes stay as-is)
    - Spot allocation is AWS-controlled (not ML-optimized)
    - ASG scale-out takes 2–5 minutes (not seconds like Karpenter)

INSTANCE TYPE DIVERSITY
------------------------
AWS recommends 3–5 compatible instance types per spot pool to reduce
simultaneous interruption risk. This service auto-selects compatible
types from a mapping of instance families with similar vCPU/memory.
Example: if cluster uses m5.large, we add m5a.large, m4.large (same
vCPU/memory ratio, different generation/family = different spot pools).

ROLLBACK
---------
revert_to_on_demand() restores the ASG to 100% on-demand by setting
OnDemandPercentageAboveBaseCapacity=100. Existing spot instances are
not immediately terminated — AWS scales down naturally as on-demand
replaces them.
"""

import logging
from typing import Optional

import boto3

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compatible instance type families for spot diversification
# Maps primary instance type → list of compatible alternatives (same size class)
# ---------------------------------------------------------------------------

COMPATIBLE_SPOT_FAMILIES = {
    # General purpose
    "m5.large":    ["m5.large",  "m5a.large",  "m4.large",  "m6i.large",  "m6a.large"],
    "m5.xlarge":   ["m5.xlarge", "m5a.xlarge", "m4.xlarge", "m6i.xlarge", "m6a.xlarge"],
    "m5.2xlarge":  ["m5.2xlarge","m5a.2xlarge","m4.2xlarge","m6i.2xlarge","m6a.2xlarge"],
    "m6i.large":   ["m6i.large", "m6a.large",  "m5.large",  "m5a.large",  "m4.large"],
    "m6i.xlarge":  ["m6i.xlarge","m6a.xlarge", "m5.xlarge", "m5a.xlarge", "m4.xlarge"],
    # Compute optimized
    "c5.large":    ["c5.large",  "c5a.large",  "c4.large",  "c6i.large",  "c6a.large"],
    "c5.xlarge":   ["c5.xlarge", "c5a.xlarge", "c4.xlarge", "c6i.xlarge", "c6a.xlarge"],
    "c6i.large":   ["c6i.large", "c6a.large",  "c5.large",  "c5a.large",  "c5d.large"],
    # Memory optimized
    "r5.large":    ["r5.large",  "r5a.large",  "r4.large",  "r6i.large",  "r6a.large"],
    "r5.xlarge":   ["r5.xlarge", "r5a.xlarge", "r4.xlarge", "r6i.xlarge", "r6a.xlarge"],
    # Burstable (t-series — only if workload allows)
    "t3.medium":   ["t3.medium", "t3a.medium", "t3.large",  "t3a.large"],
    "t3.large":    ["t3.large",  "t3a.large",  "t3.xlarge", "t3a.xlarge"],
    "t3.xlarge":   ["t3.xlarge", "t3a.xlarge", "t3.2xlarge"],
    "t4g.medium":  ["t4g.medium","t4g.large"],
    "t4g.large":   ["t4g.large", "t4g.xlarge"],
}


class SpotASGService:
    """
    Enables spot instances on EKS managed nodegroups WITHOUT Karpenter.

    Works by updating the underlying Auto Scaling Group to use a
    MixedInstancesPolicy with multiple compatible instance types.
    """

    def __init__(self, db_session=None):
        self.db = db_session

    def _build_boto_clients(self, boto_session, region: str) -> tuple:
        """Return (eks_client, asg_client, ec2_client) from a boto session."""
        eks = boto_session.client("eks", region_name=region)
        asg = boto_session.client("autoscaling", region_name=region)
        ec2 = boto_session.client("ec2", region_name=region)
        return eks, asg, ec2

    def _get_asg_name(self, eks_client, asg_client, cluster_name: str, nodegroup_name: str) -> str:
        """Resolve the ASG name from an EKS managed nodegroup."""
        ng = eks_client.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name,
        )
        asg_names = ng["nodegroup"]["resources"]["autoScalingGroups"]
        if not asg_names:
            raise ValueError(f"No ASG found for nodegroup {nodegroup_name}")
        return asg_names[0]["name"]

    def _get_launch_template(self, asg_client, asg_name: str) -> dict:
        """
        Return the Launch Template spec from an existing ASG.
        Handles both plain LaunchTemplate and MixedInstancesPolicy ASGs.
        """
        resp = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        current = resp["AutoScalingGroups"][0]

        # Case 1: already using MixedInstancesPolicy
        if "MixedInstancesPolicy" in current:
            lt_spec = (
                current["MixedInstancesPolicy"]
                .get("LaunchTemplate", {})
                .get("LaunchTemplateSpecification", {})
            )
            return {"LaunchTemplateId": lt_spec["LaunchTemplateId"],
                    "Version": lt_spec.get("Version", "$Latest")}

        # Case 2: plain LaunchTemplate
        if "LaunchTemplate" in current:
            lt = current["LaunchTemplate"]
            return {"LaunchTemplateId": lt["LaunchTemplateId"],
                    "Version": lt.get("Version", "$Latest")}

        raise ValueError(
            f"ASG {asg_name} uses a LaunchConfiguration (not a LaunchTemplate). "
            "MixedInstancesPolicy requires a LaunchTemplate. "
            "Upgrade the nodegroup to use a launch template first."
        )

    def _pick_compatible_types(self, primary_type: str, max_types: int = 5) -> list:
        """
        Return a list of spot-diverse instance types compatible with the primary type.
        Falls back to just the primary type if no mapping found.
        """
        family_key = primary_type
        # Try exact match first, then size-agnostic (strip size suffix)
        alternatives = COMPATIBLE_SPOT_FAMILIES.get(family_key)
        if not alternatives:
            parts = primary_type.rsplit(".", 1)
            if len(parts) == 2:
                for key, vals in COMPATIBLE_SPOT_FAMILIES.items():
                    if key.endswith(f".{parts[1]}"):
                        alternatives = [v for v in vals]
                        break
        if not alternatives:
            alternatives = [primary_type]
        return alternatives[:max_types]

    def enable_spot_on_nodegroup(
        self,
        boto_session,
        cluster_name: str,
        nodegroup_name: str,
        region: str,
        spot_instance_types: Optional[list] = None,
        on_demand_base_capacity: int = 1,
        spot_percentage: int = 70,
    ) -> dict:
        """
        Enable spot instances on an EKS managed nodegroup ASG.

        Args:
            boto_session:           Authenticated boto3 session (assumed cross-account role)
            cluster_name:           EKS cluster name (e.g. "prod-cluster")
            nodegroup_name:         EKS managed nodegroup name (e.g. "workers")
            region:                 AWS region (e.g. "ap-south-1")
            spot_instance_types:    Override list of instance types; if None, auto-selects
                                    compatible types from COMPATIBLE_SPOT_FAMILIES
            on_demand_base_capacity: Minimum on-demand nodes always kept (default: 1)
                                    Set to 0 for maximum spot coverage
            spot_percentage:        Percentage of nodes ABOVE the base that are spot (default: 70)
                                    70 = 70% spot, 30% on-demand above the base capacity

        Returns:
            {
                "success": bool,
                "asg_name": str,
                "spot_types": list,
                "on_demand_base": int,
                "spot_percentage": int,
                "message": str
            }
        """
        eks, asg, ec2 = self._build_boto_clients(boto_session, region)

        try:
            asg_name = self._get_asg_name(eks, asg, cluster_name, nodegroup_name)
            logger.info(f"Found ASG: {asg_name} for nodegroup {nodegroup_name}")
        except Exception as e:
            return {"success": False, "message": f"Could not resolve ASG: {e}"}

        try:
            lt = self._get_launch_template(asg, asg_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

        # Auto-select compatible instance types if not provided
        if not spot_instance_types:
            resp = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            current = resp["AutoScalingGroups"][0]
            # Try to get current instance type from LaunchTemplate
            primary_type = "m5.large"  # safe default
            try:
                lt_versions = ec2.describe_launch_template_versions(
                    LaunchTemplateId=lt["LaunchTemplateId"],
                    Versions=[lt["Version"]]
                )
                primary_type = (
                    lt_versions["LaunchTemplateVersions"][0]
                    .get("LaunchTemplateData", {})
                    .get("InstanceType", "m5.large")
                )
            except Exception:
                pass
            spot_instance_types = self._pick_compatible_types(primary_type)
            logger.info(f"Auto-selected spot types: {spot_instance_types}")

        overrides = [{"InstanceType": t} for t in spot_instance_types]

        try:
            asg.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MixedInstancesPolicy={
                    "LaunchTemplate": {
                        "LaunchTemplateSpecification": {
                            "LaunchTemplateId": lt["LaunchTemplateId"],
                            "Version":          lt["Version"],
                        },
                        "Overrides": overrides,
                    },
                    "InstancesDistribution": {
                        "OnDemandBaseCapacity":                on_demand_base_capacity,
                        "OnDemandPercentageAboveBaseCapacity": 100 - spot_percentage,
                        "SpotAllocationStrategy":              "price-capacity-optimized",
                    },
                },
            )
        except Exception as e:
            return {"success": False, "message": f"ASG update failed: {e}"}

        # Tag ASG so we can track which were modified by Spot Optimizer
        try:
            asg.create_or_update_tags(Tags=[
                {"ResourceId": asg_name, "ResourceType": "auto-scaling-group",
                 "Key": "spot-optimizer/managed", "Value": "true", "PropagateAtLaunch": False},
                {"ResourceId": asg_name, "ResourceType": "auto-scaling-group",
                 "Key": "spot-optimizer/mode", "Value": "mixed-instances", "PropagateAtLaunch": False},
            ])
        except Exception:
            pass  # Tagging failure must not block the main operation

        msg = (
            f"Enabled spot on nodegroup {nodegroup_name}: "
            f"{on_demand_base_capacity} on-demand base + {spot_percentage}% spot "
            f"using types {spot_instance_types}"
        )
        logger.info(msg)
        return {
            "success":         True,
            "asg_name":        asg_name,
            "spot_types":      spot_instance_types,
            "on_demand_base":  on_demand_base_capacity,
            "spot_percentage": spot_percentage,
            "message":         msg,
        }

    def revert_to_on_demand(
        self,
        boto_session,
        cluster_name: str,
        nodegroup_name: str,
        region: str,
    ) -> dict:
        """
        Rollback: restore ASG to 100% on-demand.

        Sets OnDemandPercentageAboveBaseCapacity=100 so new nodes launched
        by the ASG will be on-demand. Existing spot instances are NOT immediately
        terminated — they drain naturally as the ASG replaces them.

        Args:
            boto_session:   Authenticated boto3 session
            cluster_name:   EKS cluster name
            nodegroup_name: EKS managed nodegroup name
            region:         AWS region

        Returns:
            {"success": bool, "asg_name": str, "message": str}
        """
        eks, asg, _ = self._build_boto_clients(boto_session, region)

        try:
            asg_name = self._get_asg_name(eks, asg, cluster_name, nodegroup_name)
        except Exception as e:
            return {"success": False, "message": f"Could not resolve ASG: {e}"}

        try:
            lt = self._get_launch_template(asg, asg_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

        try:
            asg.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MixedInstancesPolicy={
                    "LaunchTemplate": {
                        "LaunchTemplateSpecification": {
                            "LaunchTemplateId": lt["LaunchTemplateId"],
                            "Version":          lt["Version"],
                        },
                        "Overrides": [],
                    },
                    "InstancesDistribution": {
                        "OnDemandBaseCapacity":                0,
                        "OnDemandPercentageAboveBaseCapacity": 100,  # 100% on-demand
                        "SpotAllocationStrategy":              "lowest-price",
                    },
                },
            )
        except Exception as e:
            return {"success": False, "message": f"ASG revert failed: {e}"}

        # Remove our management tags
        try:
            asg.delete_tags(Tags=[
                {"ResourceId": asg_name, "ResourceType": "auto-scaling-group",
                 "Key": "spot-optimizer/managed"},
                {"ResourceId": asg_name, "ResourceType": "auto-scaling-group",
                 "Key": "spot-optimizer/mode"},
            ])
        except Exception:
            pass

        msg = f"Reverted nodegroup {nodegroup_name} (ASG: {asg_name}) to 100% on-demand"
        logger.info(msg)
        return {"success": True, "asg_name": asg_name, "message": msg}

    def get_nodegroup_spot_status(
        self,
        boto_session,
        cluster_name: str,
        nodegroup_name: str,
        region: str,
    ) -> dict:
        """
        Return the current spot/on-demand configuration for a nodegroup's ASG.

        Returns:
            {
                "spot_enabled": bool,
                "asg_name": str,
                "on_demand_base": int,
                "spot_percentage": int,
                "instance_types": list,
                "allocation_strategy": str,
            }
        """
        eks, asg, _ = self._build_boto_clients(boto_session, region)

        try:
            asg_name = self._get_asg_name(eks, asg, cluster_name, nodegroup_name)
            resp = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            current = resp["AutoScalingGroups"][0]
        except Exception as e:
            return {"spot_enabled": False, "error": str(e)}

        if "MixedInstancesPolicy" not in current:
            return {"spot_enabled": False, "asg_name": asg_name,
                    "on_demand_base": None, "spot_percentage": 0,
                    "instance_types": [], "allocation_strategy": "on-demand-only"}

        dist = current["MixedInstancesPolicy"].get("InstancesDistribution", {})
        od_pct = dist.get("OnDemandPercentageAboveBaseCapacity", 100)
        spot_pct = 100 - od_pct
        overrides = (
            current["MixedInstancesPolicy"]
            .get("LaunchTemplate", {})
            .get("Overrides", [])
        )
        instance_types = [o.get("InstanceType", "") for o in overrides]

        return {
            "spot_enabled":       spot_pct > 0,
            "asg_name":           asg_name,
            "on_demand_base":     dist.get("OnDemandBaseCapacity", 0),
            "spot_percentage":    spot_pct,
            "instance_types":     instance_types,
            "allocation_strategy": dist.get("SpotAllocationStrategy", "unknown"),
        }
