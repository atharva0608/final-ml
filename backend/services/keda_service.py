"""KEDA Integration Service — K1

Provides KEDA detection, ScaledObject management, and pause/restore
capabilities for the Smart Workload Engine.

Key responsibilities:
  - Detect KEDA installation (CRD presence + operator pod health)
  - List / lookup ScaledObjects across namespaces
  - Expose current metric values from ScaledObject status
  - Pause / restore ScaledObjects during rebalancing windows

Redis caching:
  - spot:keda_detection:{cid}       TTL 300s  — installation detection result
  - spot:keda_paused_state:{ns}/{name}  TTL 600s  — original paused state before freeze
"""

import base64
import json
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.signers import RequestSigner
from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException
from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.system_config import SystemConfig

# ── Redis key constants ────────────────────────────────────────────────────────
_KEDA_DETECTION_TTL = 300          # 5 minutes
_KEDA_PAUSED_STATE_TTL = 600       # 10 minutes

# Known KEDA CRD group / version
_KEDA_GROUP   = "keda.sh"
_KEDA_VERSION = "v1alpha1"
_SCALED_OBJECT_PLURAL = "scaledobjects"

# Operator pod label selector used by the official KEDA Helm chart
_OPERATOR_LABEL = "app.kubernetes.io/name=keda-operator"

# Maximum ScaledObjects to fetch per namespace without pagination
_MAX_SCALED_OBJECTS = 500


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class KedaDetectionResult:
    """Result from detect_installation()."""
    installed: bool = False
    crd_exists: bool = False
    operator_running: bool = False
    version: Optional[str] = None
    operator_namespace: Optional[str] = None
    operator_pod_count: int = 0
    error: Optional[str] = None


@dataclass
class ScaledObjectInfo:
    """Minimal ScaledObject representation."""
    name: str
    namespace: str
    scale_target_ref_name: str
    scale_target_ref_kind: str = "Deployment"
    min_replicas: Optional[int] = None
    max_replicas: Optional[int] = None
    trigger_types: List[str] = field(default_factory=list)
    paused: bool = False
    external_metric_names: List[str] = field(default_factory=list)
    ready: bool = False
    active: bool = False


# ── Service class ─────────────────────────────────────────────────────────────


class KedaService:
    """Manages KEDA detection and ScaledObject lifecycle operations."""

    def __init__(self, db: Session, redis=None):
        self.db = db
        self.redis = redis

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect_installation(self, cluster_id: str) -> KedaDetectionResult:
        """
        Detect whether KEDA is installed in the cluster.

        Result is cached in Redis at spot:keda_detection:{cluster_id} for
        _KEDA_DETECTION_TTL seconds to avoid hammering the K8s API.

        Returns:
            KedaDetectionResult with crd_exists, operator_running, version.
        """
        cache_key = f"spot:keda_detection:{cluster_id}"
        if self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return KedaDetectionResult(**data)
            except Exception as cache_err:
                logger.warning(f"[KEDA] Cache read failed for {cluster_id}: {cache_err}")

        result = KedaDetectionResult()
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                result.error = f"Cluster {cluster_id} not found"
                return result

            api = self._get_k8s_client(cluster)
            core_v1  = k8s_client.CoreV1Api(api)
            custom   = k8s_client.CustomObjectsApi(api)

            # Step 1 — CRD presence check (list ScaledObjects cluster-wide).
            # If the CRD doesn't exist the API server returns 404 / ApiException.
            try:
                custom.list_cluster_custom_object(
                    group=_KEDA_GROUP,
                    version=_KEDA_VERSION,
                    plural=_SCALED_OBJECT_PLURAL,
                    limit=1
                )
                result.crd_exists = True
            except ApiException as ae:
                if ae.status in (404, 403):
                    result.crd_exists = False
                else:
                    raise

            # Step 2 — Operator pod health check.
            try:
                pods = core_v1.list_pod_for_all_namespaces(
                    label_selector=_OPERATOR_LABEL,
                    timeout_seconds=10
                )
                running_pods = [
                    p for p in pods.items
                    if p.status and p.status.phase == "Running"
                ]
                result.operator_pod_count = len(running_pods)
                result.operator_running   = len(running_pods) > 0

                if running_pods:
                    # Extract namespace from the first running pod.
                    result.operator_namespace = running_pods[0].metadata.namespace
                    # Extract version from container image tag, e.g.
                    # "ghcr.io/kedacore/keda:2.13.0" → "2.13.0"
                    containers = running_pods[0].spec.containers or []
                    for container in containers:
                        image = container.image or ""
                        if "keda" in image.lower() and ":" in image:
                            result.version = image.split(":")[-1]
                            break
            except ApiException as ae:
                logger.warning(f"[KEDA] Operator pod query failed ({ae.status}): {ae.reason}")

            result.installed = result.crd_exists and result.operator_running

        except Exception as exc:
            logger.error(f"[KEDA] detect_installation failed for cluster {cluster_id}: {exc}")
            result.error = str(exc)

        # Cache the result.
        if self.redis:
            try:
                self.redis.setex(
                    cache_key,
                    _KEDA_DETECTION_TTL,
                    json.dumps({
                        "installed":          result.installed,
                        "crd_exists":         result.crd_exists,
                        "operator_running":   result.operator_running,
                        "version":            result.version,
                        "operator_namespace": result.operator_namespace,
                        "operator_pod_count": result.operator_pod_count,
                        "error":              result.error,
                    })
                )
            except Exception as cache_err:
                logger.warning(f"[KEDA] Cache write failed for {cluster_id}: {cache_err}")

        return result

    def get_all_scaled_objects(
        self,
        cluster_id: str,
        namespace: Optional[str] = None
    ) -> List[ScaledObjectInfo]:
        """
        Fetch all ScaledObjects from the cluster (or a specific namespace).

        Uses pagination via the `_continue` token to handle large clusters.

        Returns:
            List of ScaledObjectInfo (empty if KEDA not installed or error).
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                logger.error(f"[KEDA] Cluster {cluster_id} not found")
                return []

            api    = self._get_k8s_client(cluster)
            custom = k8s_client.CustomObjectsApi(api)

            results: List[ScaledObjectInfo] = []
            _continue: Optional[str] = None

            while True:
                kwargs: Dict[str, Any] = {
                    "group":   _KEDA_GROUP,
                    "version": _KEDA_VERSION,
                    "plural":  _SCALED_OBJECT_PLURAL,
                    "limit":   100,
                }
                if _continue:
                    kwargs["_continue"] = _continue

                try:
                    if namespace:
                        raw = custom.list_namespaced_custom_object(
                            namespace=namespace, **kwargs
                        )
                    else:
                        raw = custom.list_cluster_custom_object(**kwargs)
                except ApiException as ae:
                    if ae.status in (404, 403):
                        # KEDA not installed or no permission — return empty.
                        break
                    raise

                for item in raw.get("items", []):
                    results.append(self._parse_scaled_object(item))

                _continue = raw.get("metadata", {}).get("continue")
                if not _continue or len(results) >= _MAX_SCALED_OBJECTS:
                    break

            return results

        except Exception as exc:
            logger.error(f"[KEDA] get_all_scaled_objects failed for cluster {cluster_id}: {exc}")
            return []

    def get_scaled_object_for_workload(
        self,
        cluster_id: str,
        namespace: str,
        controller_name: str,
        controller_kind: str = "Deployment"
    ) -> Optional[ScaledObjectInfo]:
        """
        Find the ScaledObject targeting a specific workload controller.

        Matches by spec.scaleTargetRef.name == controller_name and
        spec.scaleTargetRef.kind == controller_kind (case-insensitive).

        Returns:
            ScaledObjectInfo or None if not found.
        """
        try:
            objects = self.get_all_scaled_objects(cluster_id, namespace=namespace)
            for obj in objects:
                if (
                    obj.scale_target_ref_name == controller_name
                    and obj.scale_target_ref_kind.lower() == controller_kind.lower()
                ):
                    return obj
            return None
        except Exception as exc:
            logger.error(
                f"[KEDA] get_scaled_object_for_workload failed "
                f"({cluster_id}/{namespace}/{controller_name}): {exc}"
            )
            return None

    def get_current_metric_value(
        self,
        cluster_id: str,
        namespace: str,
        scaled_object_name: str
    ) -> Optional[List[str]]:
        """
        Read the current external metric names from a ScaledObject's status.

        Returns:
            List of externalMetricNames, or None on error / KEDA not installed.
        """
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return None

            api    = self._get_k8s_client(cluster)
            custom = k8s_client.CustomObjectsApi(api)

            raw = custom.get_namespaced_custom_object(
                group=_KEDA_GROUP,
                version=_KEDA_VERSION,
                namespace=namespace,
                plural=_SCALED_OBJECT_PLURAL,
                name=scaled_object_name,
            )
            status = raw.get("status", {})
            return status.get("externalMetricNames", [])

        except ApiException as ae:
            if ae.status == 404:
                return None
            logger.error(f"[KEDA] get_current_metric_value ApiException ({ae.status}): {ae.reason}")
            return None
        except Exception as exc:
            logger.error(f"[KEDA] get_current_metric_value failed: {exc}")
            return None

    def pause_scaled_object(
        self,
        cluster_id: str,
        namespace: str,
        scaled_object_name: str
    ) -> bool:
        """
        Pause a ScaledObject by patching spec.paused = true.

        Saves the original paused state in Redis so restore_scaled_object()
        can return it to its pre-pause state.

        Returns:
            True on success, False otherwise.
        """
        cache_key = f"spot:keda_paused_state:{namespace}/{scaled_object_name}"
        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False

            api    = self._get_k8s_client(cluster)
            custom = k8s_client.CustomObjectsApi(api)

            # Read current state.
            raw = custom.get_namespaced_custom_object(
                group=_KEDA_GROUP,
                version=_KEDA_VERSION,
                namespace=namespace,
                plural=_SCALED_OBJECT_PLURAL,
                name=scaled_object_name,
            )
            original_paused = raw.get("spec", {}).get("paused", False)

            # Store original state in Redis before patching.
            if self.redis:
                self.redis.setex(
                    cache_key,
                    _KEDA_PAUSED_STATE_TTL,
                    json.dumps({"original_paused": original_paused})
                )

            # Patch paused = True.
            patch = {"spec": {"paused": True}}
            custom.patch_namespaced_custom_object(
                group=_KEDA_GROUP,
                version=_KEDA_VERSION,
                namespace=namespace,
                plural=_SCALED_OBJECT_PLURAL,
                name=scaled_object_name,
                body=patch,
            )
            logger.info(f"[KEDA] Paused ScaledObject {namespace}/{scaled_object_name}")
            return True

        except ApiException as ae:
            logger.error(
                f"[KEDA] pause_scaled_object ApiException ({ae.status}): {ae.reason}"
            )
            return False
        except Exception as exc:
            logger.error(f"[KEDA] pause_scaled_object failed: {exc}")
            return False

    # ── K2: KEDA Install / Uninstall ──────────────────────────────────────────

    def install_keda(
        self,
        cluster_id: str,
        version: str = "2.13.0",
        namespace: str = "keda",
        values_overrides: Optional[Dict] = None,
    ) -> Dict:
        """
        Queue an INSTALL_KEDA AgentAction to install KEDA via Helm inside the cluster.

        Sets the spot:keda_installing:{cluster_id} Redis flag (TTL=300s) so that
        detect_installation() can return install_in_progress=True while the agent runs.

        Returns:
            dict with action_id and message.
        """
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        from backend.models.cluster import Cluster as _Cluster

        cluster = self.db.query(_Cluster).filter(_Cluster.id == cluster_id).first()
        if not cluster:
            return {"success": False, "error": f"Cluster {cluster_id} not found"}

        # ── Already-installed guard ────────────────────────────────────────────
        detection = self.detect_installation(cluster_id)
        if detection.installed:
            logger.info(
                f"[KEDA] install_keda called but KEDA already installed "
                f"(v{detection.version}) on cluster {cluster_id} — skipping"
            )
            return {
                "success": True,
                "already_installed": True,
                "message": f"KEDA is already installed (version {detection.version or 'unknown'})",
                "version": detection.version,
                "operator_namespace": detection.operator_namespace,
            }

        # ── Duplicate in-progress guard ────────────────────────────────────────
        pending_action = (
            self.db.query(AgentAction)
            .filter(
                AgentAction.cluster_id == cluster_id,
                AgentAction.action_type == AgentActionType.INSTALL_KEDA,
                AgentAction.status.in_([
                    AgentActionStatus.PENDING,
                    AgentActionStatus.PICKED_UP,
                ]),
            )
            .first()
        )
        if pending_action:
            logger.info(
                f"[KEDA] INSTALL_KEDA action {pending_action.id} already in progress "
                f"for cluster {cluster_id} — skipping duplicate"
            )
            return {
                "success": True,
                "install_in_progress": True,
                "action_id": pending_action.id,
                "message": "KEDA installation is already in progress",
            }

        # Mark installation as in-progress in Redis (K2.10)
        _install_key = f"spot:keda_installing:{cluster_id}"
        if self.redis:
            try:
                self.redis.setex(_install_key, 300, "1")
                # Invalidate detection cache so next poll sees install_in_progress
                self.redis.delete(f"spot:keda_detection:{cluster_id}")
            except Exception as _re:
                logger.warning(f"[KEDA] install flag write failed: {_re}")

        payload = {
            "version":          version,
            "namespace":        namespace,
            "values_overrides": values_overrides or {},
        }
        try:
            action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.INSTALL_KEDA,
                status=AgentActionStatus.PENDING,
                payload=payload,
            )
            self.db.add(action)
            self.db.commit()
            self.db.refresh(action)
            logger.info(
                f"[KEDA] Queued INSTALL_KEDA action {action.id} "
                f"for cluster {cluster_id}, version={version}"
            )
            return {"success": True, "action_id": action.id, "message": "KEDA installation queued"}
        except Exception as exc:
            logger.error(f"[KEDA] install_keda failed for cluster {cluster_id}: {exc}")
            # Clear the installing flag on error so detection doesn't stay stuck
            if self.redis:
                try:
                    self.redis.delete(_install_key)
                except Exception:
                    pass
            return {"success": False, "error": str(exc)}

    def uninstall_keda(self, cluster_id: str, namespace: str = "keda") -> Dict:
        """
        Queue an UNINSTALL_KEDA AgentAction to remove KEDA via Helm.

        Returns:
            dict with action_id and message.
        """
        from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
        from backend.models.cluster import Cluster as _Cluster

        cluster = self.db.query(_Cluster).filter(_Cluster.id == cluster_id).first()
        if not cluster:
            return {"success": False, "error": f"Cluster {cluster_id} not found"}

        # Invalidate detection cache
        if self.redis:
            try:
                self.redis.delete(f"spot:keda_detection:{cluster_id}")
                self.redis.delete(f"spot:keda_installing:{cluster_id}")
            except Exception:
                pass

        payload = {"namespace": namespace}
        try:
            action = AgentAction(
                cluster_id=cluster_id,
                action_type=AgentActionType.UNINSTALL_KEDA,
                status=AgentActionStatus.PENDING,
                payload=payload,
            )
            self.db.add(action)
            self.db.commit()
            self.db.refresh(action)
            logger.info(
                f"[KEDA] Queued UNINSTALL_KEDA action {action.id} for cluster {cluster_id}"
            )
            return {"success": True, "action_id": action.id, "message": "KEDA uninstall queued"}
        except Exception as exc:
            logger.error(f"[KEDA] uninstall_keda failed for cluster {cluster_id}: {exc}")
            return {"success": False, "error": str(exc)}

    def get_install_status(self, cluster_id: str) -> Dict:
        """
        Return the current KEDA install status for the cluster.

        Combines:
          - detect_installation() for live health
          - spot:keda_installing:{cid} Redis flag for in-progress state
          - Latest INSTALL_KEDA / UNINSTALL_KEDA AgentAction status

        Returns:
            dict with installed, install_in_progress, action_status, action_id, error.
        """
        from backend.models.agent_action import AgentAction, AgentActionType

        # Check in-progress flag (K2.10)
        install_in_progress = False
        if self.redis:
            try:
                install_in_progress = bool(self.redis.exists(f"spot:keda_installing:{cluster_id}"))
            except Exception:
                pass

        # Get latest install/uninstall action status
        action_status = None
        action_id     = None
        try:
            latest_action = (
                self.db.query(AgentAction)
                .filter(
                    AgentAction.cluster_id == cluster_id,
                    AgentAction.action_type.in_([
                        AgentActionType.INSTALL_KEDA,
                        AgentActionType.UNINSTALL_KEDA,
                    ]),
                )
                .order_by(AgentAction.created_at.desc())
                .first()
            )
            if latest_action:
                action_status = (
                    latest_action.status.value
                    if hasattr(latest_action.status, "value")
                    else str(latest_action.status)
                )
                action_id = latest_action.id
                # If the action completed, clear the installing flag
                if (
                    install_in_progress
                    and action_status in ("COMPLETED", "FAILED", "completed", "failed")
                ):
                    if self.redis:
                        try:
                            self.redis.delete(f"spot:keda_installing:{cluster_id}")
                        except Exception:
                            pass
                    install_in_progress = False
        except Exception as exc:
            logger.warning(f"[KEDA] get_install_status action query failed: {exc}")

        # Live detection (uses cache when available)
        detection = self.detect_installation(cluster_id)

        return {
            "cluster_id":           cluster_id,
            "installed":            detection.installed,
            "crd_exists":           detection.crd_exists,
            "operator_running":     detection.operator_running,
            "version":              detection.version,
            "operator_namespace":   detection.operator_namespace,
            "install_in_progress":  install_in_progress,
            "action_status":        action_status,
            "action_id":            action_id,
            "error":                detection.error,
        }

    def restore_scaled_object(
        self,
        cluster_id: str,
        namespace: str,
        scaled_object_name: str
    ) -> bool:
        """
        Restore a ScaledObject's paused state to whatever it was before
        pause_scaled_object() was called.

        Returns:
            True on success, False otherwise.
        """
        cache_key = f"spot:keda_paused_state:{namespace}/{scaled_object_name}"
        original_paused = False

        if self.redis:
            try:
                stored = self.redis.get(cache_key)
                if stored:
                    original_paused = json.loads(stored).get("original_paused", False)
                    self.redis.delete(cache_key)
            except Exception as cache_err:
                logger.warning(f"[KEDA] Cache read failed on restore: {cache_err}")

        try:
            cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
            if not cluster:
                return False

            api    = self._get_k8s_client(cluster)
            custom = k8s_client.CustomObjectsApi(api)

            patch = {"spec": {"paused": original_paused}}
            custom.patch_namespaced_custom_object(
                group=_KEDA_GROUP,
                version=_KEDA_VERSION,
                namespace=namespace,
                plural=_SCALED_OBJECT_PLURAL,
                name=scaled_object_name,
                body=patch,
            )
            logger.info(
                f"[KEDA] Restored ScaledObject {namespace}/{scaled_object_name} "
                f"(paused={original_paused})"
            )
            return True

        except ApiException as ae:
            logger.error(
                f"[KEDA] restore_scaled_object ApiException ({ae.status}): {ae.reason}"
            )
            return False
        except Exception as exc:
            logger.error(f"[KEDA] restore_scaled_object failed: {exc}")
            return False

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _parse_scaled_object(self, raw: Dict) -> ScaledObjectInfo:
        """Convert a raw ScaledObject dict (from K8s API) to ScaledObjectInfo."""
        meta   = raw.get("metadata", {})
        spec   = raw.get("spec", {})
        status = raw.get("status", {})

        target_ref = spec.get("scaleTargetRef", {})
        triggers   = spec.get("triggers", [])

        trigger_types = [t.get("type", "unknown") for t in triggers if isinstance(t, dict)]

        # Replica bounds
        min_replicas = spec.get("minReplicaCount")
        max_replicas = spec.get("maxReplicaCount")

        # Status fields
        conditions = status.get("conditions", [])
        ready  = any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
        active = any(
            c.get("type") == "Active" and c.get("status") == "True"
            for c in conditions
        )

        return ScaledObjectInfo(
            name=meta.get("name", ""),
            namespace=meta.get("namespace", ""),
            scale_target_ref_name=target_ref.get("name", ""),
            scale_target_ref_kind=target_ref.get("kind", "Deployment"),
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            trigger_types=trigger_types,
            paused=spec.get("paused", False),
            external_metric_names=status.get("externalMetricNames", []),
            ready=ready,
            active=active,
        )

    def _get_k8s_client(self, cluster: Cluster):
        """Creates Kubernetes API client for an EKS cluster.

        Mirrors karpenter_service.py _get_k8s_client() exactly — same EKS
        STS token generation and CA cert handling.
        """
        try:
            account = self.db.query(Account).filter(Account.id == cluster.account_id).first()
            if not account:
                raise ValueError(f"Account {cluster.account_id} not found")

            credentials = self._get_backend_credentials(cluster.region)
            token = self._get_eks_token(
                cluster_name=cluster.name,
                credentials=credentials,
                region=cluster.region
            )

            configuration = k8s_client.Configuration()
            configuration.host = cluster.endpoint
            configuration.api_key = {"authorization": f"Bearer {token}"}

            if cluster.ca_data:
                try:
                    ca_bytes = base64.b64decode(cluster.ca_data)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".crt") as ca_file:
                        ca_file.write(ca_bytes)
                        ca_cert_path = ca_file.name
                    configuration.ssl_ca_cert = ca_cert_path
                    configuration.verify_ssl = True
                except Exception as ssl_ex:
                    logger.warning(
                        f"[KEDA] Failed to write CA cert for cluster {cluster.name} "
                        f"({ssl_ex}); disabling SSL verification."
                    )
                    configuration.verify_ssl = False
            else:
                logger.warning(
                    f"[KEDA] Cluster {cluster.name} has no ca_data; "
                    "disabling SSL verification."
                )
                configuration.verify_ssl = False

            api = k8s_client.ApiClient(configuration)
            return api

        except Exception as exc:
            logger.error(f"[KEDA] Failed to create K8s API client: {exc}")
            raise

    def _get_backend_credentials(self, region: str) -> Dict:
        """Fetch platform IAM credentials from SystemConfig."""
        access_key = (
            self.db.query(SystemConfig)
            .filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY")
            .first()
        )
        secret_key = (
            self.db.query(SystemConfig)
            .filter(SystemConfig.key == "PLATFORM_AWS_SECRET")
            .first()
        )

        if access_key and secret_key and access_key.value and secret_key.value:
            return {"access_key": access_key.value, "secret_key": secret_key.value}

        logger.warning("[KEDA] Platform credentials not found, using environment/instance profile")
        return {}

    def _get_eks_token(self, cluster_name: str, credentials: Dict, region: str) -> str:
        """Generate Kubernetes auth token for EKS via SigV4 presigned URL."""
        if credentials and "access_key" in credentials and "secret_key" in credentials:
            session = boto3.Session(
                aws_access_key_id=credentials["access_key"],
                aws_secret_access_key=credentials["secret_key"],
                aws_session_token=credentials.get("session_token"),
                region_name=region
            )
        else:
            session = boto3.Session(region_name=region)

        sts = session.client("sts", region_name=region, config=Config(signature_version="v4"))
        service_id = sts.meta.service_model.service_id
        signer = RequestSigner(
            service_id, region, "sts", "v4",
            session.get_credentials(), session.events
        )

        params = {
            "method":  "GET",
            "url":     f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
            "body":    {},
            "headers": {"x-k8s-aws-id": cluster_name},
            "context": {},
        }
        url = signer.generate_presigned_url(
            params, region_name=region, expires_in=60, operation_name=""
        )
        token = "k8s-aws-v1." + base64.urlsafe_b64encode(
            url.encode("utf-8")
        ).decode("utf-8").rstrip("=")
        return token
