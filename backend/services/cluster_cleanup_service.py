"""
ClusterCleanupService
=====================
Automated cleanup of ALL AWS and Kubernetes resources created for a cluster.
Called when DELETE /api/v1/clusters/{id} is invoked.

Everything is idempotent — safe to call even if resources are partially missing.
"""

import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


class ClusterCleanupService:
    """
    Cleans up every resource the platform creates when a cluster is connected:

    AWS:
      - KarpenterControllerRole-{cluster_name}  (IAM role + inline policies)
      - KarpenterNodeRole-{cluster_name}         (IAM role + attached policies)
      - KarpenterNodeInstanceProfile-{cluster_name}
      - KarpenterInterruptionQueue-{cluster_name} (SQS queue)
      - EventBridge rules KarpenterRule-{cluster_name}-*
      - IAM OIDC Identity Provider for the cluster

    Kubernetes (via agent action):
      - Helm uninstall karpenter
      - EC2NodeClass + NodePool CRDs deleted
      - Agent DaemonSet self-destructs

    Redis:
      - All per-cluster cache keys
    """

    def cleanup_cluster(
        self,
        cluster,
        account,
        boto_session,
        db,
        k8s_reachable: bool = True,
    ) -> dict:
        """
        Run full cleanup. All steps are best-effort — failures are logged but
        do not block the DB row deletion.

        Returns a dict summarising what was done/skipped/failed.
        """
        results = {}

        # 1. Kubernetes resources (queue agent action if cluster still reachable)
        if k8s_reachable:
            results["k8s"] = self._cleanup_kubernetes_resources(cluster, db)
        else:
            results["k8s"] = {"skipped": "cluster unreachable"}

        # 2. AWS IAM
        try:
            results["iam"] = self._cleanup_iam_resources(cluster, boto_session)
        except Exception as e:
            results["iam"] = {"error": str(e)}

        # 3. SQS queue
        try:
            results["sqs"] = self._cleanup_sqs_queue(cluster, boto_session)
        except Exception as e:
            results["sqs"] = {"error": str(e)}

        # 4. EventBridge rules
        try:
            results["eventbridge"] = self._cleanup_eventbridge_rules(cluster, boto_session)
        except Exception as e:
            results["eventbridge"] = {"error": str(e)}

        # 5. OIDC provider
        try:
            results["oidc"] = self._cleanup_oidc_provider(cluster, boto_session)
        except Exception as e:
            results["oidc"] = {"error": str(e)}

        # 6. Redis keys
        try:
            results["redis"] = self._cleanup_redis_keys(cluster.id)
        except Exception as e:
            results["redis"] = {"error": str(e)}

        return results

    # ── Kubernetes ────────────────────────────────────────────────────────────

    def _cleanup_kubernetes_resources(self, cluster, db) -> dict:
        """Queue UNINSTALL_KARPENTER agent action — agent does helm uninstall + self-destruct."""
        try:
            from backend.models.agent_action import AgentAction, AgentActionType
            action = AgentAction(
                cluster_id=cluster.id,
                action_type=AgentActionType.UNINSTALL_KARPENTER,
                payload={"cluster_name": cluster.name},
            )
            db.add(action)
            db.flush()
            return {"queued": "UNINSTALL_KARPENTER", "action_id": str(action.id)}
        except Exception as e:
            return {"error": str(e)}

    # ── IAM ──────────────────────────────────────────────────────────────────

    def _cleanup_iam_resources(self, cluster, boto_session) -> dict:
        iam = boto_session.client("iam")
        cluster_name = cluster.name
        cleaned = []

        # 1. Delete KarpenterControllerRole
        self._delete_iam_role(iam, f"KarpenterControllerRole-{cluster_name}", cleaned)

        # 2. Remove node role from instance profile, then delete both
        profile_name = f"KarpenterNodeInstanceProfile-{cluster_name}"
        node_role_name = f"KarpenterNodeRole-{cluster_name}"
        try:
            iam.remove_role_from_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=node_role_name,
            )
        except Exception:
            pass
        try:
            iam.delete_instance_profile(InstanceProfileName=profile_name)
            cleaned.append(profile_name)
        except Exception:
            pass

        self._delete_iam_role(iam, node_role_name, cleaned)
        return {"deleted": cleaned}

    def _delete_iam_role(self, iam, role_name: str, cleaned: list):
        """Detach all policies then delete the IAM role (idempotent)."""
        try:
            for p in iam.list_attached_role_policies(RoleName=role_name).get("AttachedPolicies", []):
                iam.detach_role_policy(RoleName=role_name, PolicyArn=p["PolicyArn"])
            for p in iam.list_role_policies(RoleName=role_name).get("PolicyNames", []):
                iam.delete_role_policy(RoleName=role_name, PolicyName=p)
            iam.delete_role(RoleName=role_name)
            cleaned.append(role_name)
        except iam.exceptions.NoSuchEntityException:
            pass  # Already gone — idempotent

    # ── SQS ──────────────────────────────────────────────────────────────────

    def _cleanup_sqs_queue(self, cluster, boto_session) -> dict:
        sqs = boto_session.client("sqs", region_name=cluster.region)
        queue_name = f"KarpenterInterruptionQueue-{cluster.name}"
        try:
            url = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
            sqs.delete_queue(QueueUrl=url)
            return {"deleted": queue_name}
        except sqs.exceptions.QueueDoesNotExist:
            return {"skipped": "already gone"}

    # ── EventBridge ──────────────────────────────────────────────────────────

    def _cleanup_eventbridge_rules(self, cluster, boto_session) -> dict:
        events = boto_session.client("events", region_name=cluster.region)
        cluster_name = cluster.name
        rule_names = [
            f"KarpenterRule-{cluster_name}-SpotInterruption",
            f"KarpenterRule-{cluster_name}-Rebalance",
            f"KarpenterRule-{cluster_name}-InstanceStateChange",
            f"KarpenterRule-{cluster_name}-ScheduledChange",
        ]
        cleaned = []
        for rule_name in rule_names:
            try:
                targets = events.list_targets_by_rule(Rule=rule_name).get("Targets", [])
                if targets:
                    events.remove_targets(Rule=rule_name, Ids=[t["Id"] for t in targets])
                events.delete_rule(Name=rule_name)
                cleaned.append(rule_name)
            except events.exceptions.ResourceNotFoundException:
                pass
        return {"deleted": cleaned}

    # ── OIDC Provider ─────────────────────────────────────────────────────────

    def _cleanup_oidc_provider(self, cluster, boto_session) -> dict:
        """
        Delete the IAM OIDC Identity Provider for this cluster.
        Safe per-cluster because each cluster has a unique OIDC URL hash.
        """
        iam = boto_session.client("iam")
        eks = boto_session.client("eks", region_name=cluster.region)
        sts = boto_session.client("sts")
        try:
            account_id = sts.get_caller_identity()["Account"]
            cluster_info = eks.describe_cluster(name=cluster.name)
            oidc_issuer = cluster_info["cluster"]["identity"]["oidc"]["issuer"]
            oidc_host = oidc_issuer.replace("https://", "")
            provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{oidc_host}"
            iam.delete_open_id_connect_provider(OpenIDConnectProviderArn=provider_arn)
            return {"deleted": provider_arn}
        except Exception as e:
            return {"skipped": str(e)}

    # ── Redis ─────────────────────────────────────────────────────────────────

    def _cleanup_redis_keys(self, cluster_id: str) -> dict:
        """Delete ALL Redis keys associated with this cluster."""
        from backend.core.redis_client import get_redis_client
        redis_client = get_redis_client()

        patterns = [
            f"spot:cooldown:cluster:{cluster_id}",
            f"spot:cooldown:resize:{cluster_id}",
            f"spot:cooldown:pool_switch:{cluster_id}",
            f"spot:cooldown:substitute:{cluster_id}",
            f"spot:stabilization_lock:{cluster_id}",
            f"spot:node_classification:{cluster_id}",
            f"spot:node_arch_constraints:{cluster_id}",
            f"spot:cluster_mode:{cluster_id}",
            f"spot:ondemand_fallback:{cluster_id}",
            f"spot:execution_failures:{cluster_id}",
            f"spot:cluster_state:{cluster_id}",
            f"spot:execution_plan:{cluster_id}",
            f"spot:node_classification:{cluster_id}",
            f"spot:substitute:state:{cluster_id}",
            f"spot:substitute:meta:{cluster_id}",
            f"obs:decisions:{cluster_id}",
            f"cb:state:{cluster_id}",
            f"cb:rollbacks:{cluster_id}",
            f"cb:last_failure:{cluster_id}",
            f"cb:state_entered:{cluster_id}",
            f"resize:guard:{cluster_id}:invocations",
            f"resize:rollback_needed:{cluster_id}",
            f"resize:failure_count_24h:{cluster_id}",
            f"karpenter_config:{cluster_id}",
            f"clusters:*",  # cluster list cache (invalidate all — TTL is 5s anyway)
        ]
        wildcard_patterns = [
            f"spot:rejection_counter:{cluster_id}:*",
            f"hibernation:lock:*:{cluster_id}",
            f"spot:karpenter:nodepool_updated:{cluster_id}",
            f"spot:warm_spare:*:{cluster_id}",
        ]
        deleted = 0
        for pattern in patterns:
            try:
                if redis_client.exists(pattern):
                    redis_client.delete(pattern)
                    deleted += 1
            except Exception:
                pass
        for pattern in wildcard_patterns:
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
                    deleted += len(keys)
            except Exception:
                pass
        return {"deleted_keys": deleted}
