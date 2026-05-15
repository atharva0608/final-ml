#!/usr/bin/env python3
"""
Karpenter Event Watcher

Watches the Kubernetes event stream for Karpenter-originated events
(NodeClaimCreated, NodeClaimDeleted, Consolidated, etc.) and POSTs them
to the backend so the ML rebalancer has visibility into independent
Karpenter activity.

Why this exists:
  When Karpenter provisions or consolidates nodes independently (e.g.
  provisioning a t4g.micro that wasn't ML-selected), the backend has no
  visibility.  This watcher closes that gap: the backend can log the event,
  update risk scores, or pause the rebalancer if Karpenter is acting
  aggressively enough to destabilize the cluster.

Thread lifecycle:
  run() — blocking loop, designed to be started in a daemon thread.
  stop() — signals the loop to exit cleanly.

K8s events watched:
  source.component == 'karpenter' OR
  involvedObject.kind in ('NodeClaim', 'NodePool') OR
  reason in ('NodeClaimCreated', 'NodeClaimDeleted', 'Consolidated',
             'DisruptionBlocked', 'DisruptionLaunched', 'Drifted',
             'WaitingOnReadiness', 'TerminatingNodeClaim',
             'InsufficientCapacity', 'NotYetSchedulable')
"""

import os
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Karpenter event reasons we care about
_KARPENTER_REASONS = frozenset({
    'NodeClaimCreated',
    'NodeClaimDeleted',
    'Consolidated',
    'DisruptionBlocked',
    'DisruptionLaunched',
    'Drifted',
    'WaitingOnReadiness',
    'TerminatingNodeClaim',
    'InsufficientCapacity',
    'NotYetSchedulable',
    'NodeClaimTerminating',
    'LaunchFailed',
})

_KARPENTER_OBJECT_KINDS = frozenset({'NodeClaim', 'NodePool'})

# How long to sleep between full re-list cycles when the watch stream ends
_REWATCH_INTERVAL_S = 30


class KarpenterWatcher:
    """
    Daemon thread that watches K8s events for Karpenter activity and
    reports them to the backend.
    """

    def __init__(
        self,
        backend_url: str,
        api_key: str,
        cluster_id: str,
        poll_interval: int = 60,
    ):
        self.backend_url = backend_url
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.poll_interval = poll_interval

        self._stop_event = threading.Event()
        # Track the last resourceVersion so we only forward new events
        self._last_resource_version: Optional[str] = None
        # Deduplicate: track event UIDs already sent in this session
        self._sent_uids: set = set()
        # NodeClaims CRD API version — detected at first poll
        self._nodeclaim_api_version: Optional[str] = None

        logger.info(
            f"[karpenter_watcher] Initialized for cluster={cluster_id}"
        )

    def stop(self):
        """Signal the watcher loop to exit."""
        self._stop_event.set()

    def run(self):
        """
        Main blocking loop.  Connects to the K8s watch API and streams
        events.  Re-connects automatically on stream end or errors.
        Also starts a NodeClaims polling thread (T-11).
        Use _stop_event to break the loop cleanly.
        """
        logger.info("[karpenter_watcher] Starting K8s event watch loop")

        nodeclaims_thread = threading.Thread(
            target=self._nodeclaims_poll_loop,
            daemon=True,
            name="karpenter-nodeclaims-poller",
        )
        nodeclaims_thread.start()

        while not self._stop_event.is_set():
            try:
                self._watch_events_stream()
            except Exception as exc:
                logger.warning(
                    f"[karpenter_watcher] Watch stream error: {exc} — "
                    f"retrying in {_REWATCH_INTERVAL_S}s"
                )
            if not self._stop_event.is_set():
                self._stop_event.wait(_REWATCH_INTERVAL_S)

        logger.info("[karpenter_watcher] Stopped")

    def _nodeclaims_poll_loop(self):
        """Polls NodeClaim CRDs every 60s and pushes to backend (T-11)."""
        while not self._stop_event.is_set():
            try:
                self._poll_nodeclaims()
            except Exception as exc:
                logger.debug(f"[karpenter_watcher] NodeClaims poll error: {exc}")
            self._stop_event.wait(60)

    def _detect_crd_version(self) -> str:
        """Try v1, fall back to v1beta1 if CRD not found."""
        from kubernetes import client as k8s_client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()
        co = k8s_client.CustomObjectsApi()
        for version in ("v1", "v1beta1"):
            try:
                co.list_cluster_custom_object(
                    group="karpenter.sh", version=version, plural="nodeclaims", limit=1
                )
                logger.info(f"[karpenter_watcher] NodeClaim CRD version: {version}")
                return version
            except Exception:
                pass
        return "v1"

    def _poll_nodeclaims(self):
        """Collect all NodeClaim CRDs and push to backend."""
        from kubernetes import client as k8s_client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        if not self._nodeclaim_api_version:
            self._nodeclaim_api_version = self._detect_crd_version()

        co = k8s_client.CustomObjectsApi()
        try:
            result = co.list_cluster_custom_object(
                group="karpenter.sh",
                version=self._nodeclaim_api_version,
                plural="nodeclaims",
            )
        except Exception as exc:
            logger.debug(f"[karpenter_watcher] NodeClaims list error: {exc}")
            return

        claims = []
        for item in result.get("items", []):
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})
            labels = meta.get("labels", {})
            claims.append({
                "node_name": status.get("nodeName") or meta.get("name"),
                "instance_type": (labels.get("node.kubernetes.io/instance-type")
                                   or spec.get("requirements", [{}])[0].get("values", [None])[0]),
                "capacity_type": (labels.get("karpenter.sh/capacity-type")
                                   or labels.get("eks.amazonaws.com/capacityType")),
                "az": labels.get("topology.kubernetes.io/zone"),
                "nodepool_name": (labels.get("karpenter.sh/nodepool")
                                   or labels.get("karpenter.k8s.aws/nodepool")),
                "state": status.get("conditions", [{}])[0].get("type") if status.get("conditions") else None,
                "provisioned_at": meta.get("creationTimestamp"),
            })

        if not claims:
            return

        url = f"{self.backend_url}/api/v1/agents/nodeclaims/batch"
        try:
            resp = requests.post(
                url,
                json={"cluster_id": self.cluster_id, "claims": claims},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "ngrok-skip-browser-warning": "true",
                },
                timeout=15,
            )
            logger.debug(f"[karpenter_watcher] NodeClaims pushed: {len(claims)}, status={resp.status_code}")
        except Exception as exc:
            logger.debug(f"[karpenter_watcher] NodeClaims POST failed: {exc}")

    # ── internal ──────────────────────────────────────────────────────────

    def _load_k8s_client(self):
        """
        Build a kubernetes CoreV1Api client using in-cluster config
        (pod service account), falling back to local kubeconfig for
        development.
        """
        from kubernetes import client as k8s_client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()
        return k8s_client.CoreV1Api()

    def _is_karpenter_event(self, event) -> bool:
        """
        Return True if this K8s Event object originated from Karpenter.
        Checks:
          1. source.component starts with 'karpenter'
          2. event.reason is in the known Karpenter reason set
          3. involvedObject.kind is NodeClaim or NodePool
        """
        reason = getattr(event, 'reason', '') or ''
        source = getattr(event, 'source', None)
        source_component = (
            getattr(source, 'component', '') or ''
            if source else ''
        )
        involved = getattr(event, 'involved_object', None)
        involved_kind = (
            getattr(involved, 'kind', '') or ''
            if involved else ''
        )

        return (
            'karpenter' in source_component.lower()
            or reason in _KARPENTER_REASONS
            or involved_kind in _KARPENTER_OBJECT_KINDS
        )

    def _event_to_payload(self, k8s_event) -> dict:
        """Serialize a K8s event to the backend POST payload."""
        involved = getattr(k8s_event, 'involved_object', None)
        source = getattr(k8s_event, 'source', None)

        # Prefer eventTime (microsecond) over firstTimestamp (second)
        event_time = (
            getattr(k8s_event, 'event_time', None)
            or getattr(k8s_event, 'first_timestamp', None)
        )
        event_time_iso = (
            event_time.isoformat()
            if event_time and hasattr(event_time, 'isoformat')
            else datetime.now(timezone.utc).isoformat()
        )

        return {
            'cluster_id': self.cluster_id,
            'event_reason': getattr(k8s_event, 'reason', '') or '',
            'event_source': getattr(source, 'component', '') if source else '',
            'involved_object_kind': getattr(involved, 'kind', '') if involved else '',
            'involved_object_name': getattr(involved, 'name', '') if involved else '',
            'message': getattr(k8s_event, 'message', '') or '',
            'event_time': event_time_iso,
            'event_payload': {
                'uid': getattr(k8s_event.metadata, 'uid', '') if k8s_event.metadata else '',
                'namespace': getattr(k8s_event, 'namespace', '') or
                             (getattr(involved, 'namespace', '') if involved else ''),
                'count': getattr(k8s_event, 'count', 1) or 1,
                'type': getattr(k8s_event, 'type', 'Normal') or 'Normal',
                'reporting_component': getattr(k8s_event, 'reporting_component', '') or '',
            },
        }

    def _post_to_backend(self, payload: dict):
        """POST a single Karpenter event to the backend."""
        url = f"{self.backend_url}/api/v1/karpenter/clusters/{self.cluster_id}/events"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'ngrok-skip-browser-warning': 'true',
                },
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                logger.debug(
                    f"[karpenter_watcher] Backend POST returned "
                    f"{resp.status_code}: {resp.text[:200]}"
                )
        except requests.exceptions.RequestException as exc:
            logger.debug(f"[karpenter_watcher] POST failed: {exc}")

    def _watch_events_stream(self):
        """
        Open a K8s watch stream on Events (all namespaces) and
        forward Karpenter-originated events to the backend.
        Exits when the stream ends or _stop_event is set.
        """
        from kubernetes import watch as k8s_watch

        v1 = self._load_k8s_client()
        watcher = k8s_watch.Watch()

        kwargs: dict = {'timeout_seconds': self.poll_interval * 2}
        if self._last_resource_version:
            kwargs['resource_version'] = self._last_resource_version

        logger.debug(
            f"[karpenter_watcher] Opening watch stream "
            f"(resourceVersion={self._last_resource_version or 'latest'})"
        )

        try:
            for event_obj in watcher.stream(
                v1.list_event_for_all_namespaces, **kwargs
            ):
                if self._stop_event.is_set():
                    watcher.stop()
                    break

                # Update bookmark
                _raw_event = event_obj.get('raw_object', {})
                _rv = (
                    _raw_event.get('metadata', {}).get('resourceVersion')
                    or _raw_event.get('resourceVersion')
                )
                if _rv:
                    self._last_resource_version = _rv

                event_type = event_obj.get('type', '')  # ADDED / MODIFIED / DELETED
                k8s_event = event_obj.get('object')

                if event_type == 'ERROR' or k8s_event is None:
                    continue

                # Only forward new events (ADDED), not MODIFIED/DELETED
                if event_type != 'ADDED':
                    continue

                if not self._is_karpenter_event(k8s_event):
                    continue

                # Deduplicate within the session
                uid = (
                    getattr(k8s_event.metadata, 'uid', '')
                    if k8s_event.metadata else ''
                )
                if uid and uid in self._sent_uids:
                    continue
                if uid:
                    self._sent_uids.add(uid)
                    # Bound memory: keep last 1000 UIDs only
                    if len(self._sent_uids) > 1000:
                        self._sent_uids.pop()

                payload = self._event_to_payload(k8s_event)
                logger.info(
                    f"[karpenter_watcher] Karpenter event: "
                    f"{payload['event_reason']} / "
                    f"{payload['involved_object_kind']}/{payload['involved_object_name']}"
                )
                self._post_to_backend(payload)

        except StopIteration:
            # Stream ended normally — outer loop will reconnect
            pass
        finally:
            try:
                watcher.stop()
            except Exception:
                pass
