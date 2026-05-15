#!/usr/bin/env python3
"""
Pod Metrics Collector Module for Right-Sizing

Collects pod-level resource usage metrics for the right-sizing engine.
Sends metrics to /api/v1/pod-metrics/batch every 5 minutes.

Key features:
- Extracts controller owner references (Deployment, StatefulSet, etc.)
- Collects CPU/memory usage from metrics.k8s.io API
- Collects CPU/memory requests/limits from pod specs
- Batches metrics by node for efficient submission
- Handles DaemonSet-specific logic (only sends pods on local node)
"""

import os
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

# W1.1a — Sidecar container names to exclude from container_images classification.
# These containers provide infrastructure cross-cutting concerns and must not
# influence workload type detection.
_SIDECAR_NAMES = frozenset({
    # Service mesh
    "istio-proxy", "envoy", "linkerd-proxy", "consul-connect-inject-init",
    "consul-dataplane",
    # Observability
    "datadog-agent", "datadog-init", "newrelic-infra", "splunk-otelcol",
    "elastic-apm-agent", "otel-collector", "jaeger-agent", "zipkin-reporter",
    "fluentd", "fluent-bit", "filebeat", "promtail", "vector",
    # Security
    "vault-agent", "vault-agent-init", "aws-secrets-init",
    # Cloud / infra
    "cloud-sql-proxy", "aws-xray-daemon",
    # Karpenter / spot-optimizer
    "spot-optimizer-agent",
})

# W1.2 — Allowlist of env var name patterns that are safe to forward to the
# backend for classification.  ONLY keys that appear in this set (case-
# insensitive prefix match) are included.  This prevents credential leakage.
_CLASSIFICATION_SAFE_ENV_PREFIXES = (
    "spring_", "quarkus_", "micronaut_",   # JVM framework hints
    "rails_", "rack_",                      # Ruby hints
    "django_", "flask_", "fastapi_",        # Python hints
    "database_", "db_", "redis_", "mongo_", # DB connection hints (key only, no values)
    "kafka_", "rabbitmq_", "amqp_",         # Queue hints
    "celery_", "sidekiq_", "resque_",       # Worker hints
    "leader_election", "ha_enabled",        # HA / leader-election hints
    "replicas_",                            # Replica hints
)


class PodMetricsCollector:
    """
    Collects pod-level metrics for right-sizing analysis.
    """

    def __init__(self, backend_url: str, api_key: str, cluster_id: str):
        """
        Initialize the pod metrics collector.

        Args:
            backend_url: URL of the backend API
            api_key: API key for authentication
            cluster_id: Unique identifier for this cluster
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.node_name = os.getenv('NODE_NAME')  # DaemonSet provides this
        self.collection_interval = int(os.getenv('POD_METRICS_INTERVAL', '60'))  # 1 minute default
        self.running = False

        # Initialize Kubernetes clients
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig from local environment")
            except config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes configuration: {e}")
                raise

        self.core_v1 = client.CoreV1Api()
        self.policy_v1 = client.PolicyV1Api()
        self.custom_objects = client.CustomObjectsApi()
        try:
            self.autoscaling_v2 = client.AutoscalingV2Api()
        except AttributeError:
            self.autoscaling_v2 = None  # fallback for older python-kubernetes

        # Phase 2e State (Task 5.1/5.2) - To be accessed by heartbeat.py
        self.latest_hpa_pdb_data = {}
        self.latest_cluster_spot_summary = {
            'total_spot_pods': 0, 'total_od_pods': 0, 
            'in_flight_spot_pods': 0, 'unhealthy_pending_pods': 0
        }
        self.pod_metrics_per_workload = {}

        logger.info(f"PodMetricsCollector initialized for cluster: {cluster_id}, node: {self.node_name}")

    def parse_cpu_value(self, cpu_string: str) -> int:
        """
        Parse CPU value from Kubernetes format to millicores.

        Args:
            cpu_string: CPU value (e.g., "100m", "1", "2.5")

        Returns:
            CPU in millicores (int)
        """
        if not cpu_string:
            return 0

        cpu_string = str(cpu_string).strip()
        if cpu_string.endswith('m'):
            return int(float(cpu_string[:-1]))
        elif cpu_string.endswith('n'):
            return int(float(cpu_string[:-1]) / 1000000)
        else:
            return int(float(cpu_string) * 1000)

    def parse_memory_value(self, memory_string: str) -> int:
        """
        Parse memory value from Kubernetes format to bytes.

        Args:
            memory_string: Memory value (e.g., "128Mi", "1Gi", "1024Ki")

        Returns:
            Memory in bytes (int)
        """
        if not memory_string:
            return 0

        memory_string = str(memory_string).strip()
        multipliers = {
            'Ki': 1024,
            'Mi': 1024 ** 2,
            'Gi': 1024 ** 3,
            'Ti': 1024 ** 4,
            'K': 1000,
            'M': 1000 ** 2,
            'G': 1000 ** 3,
            'T': 1000 ** 4,
        }

        for suffix, multiplier in multipliers.items():
            if memory_string.endswith(suffix):
                return int(float(memory_string[:-len(suffix)]) * multiplier)

        return int(float(memory_string))

    def get_controller_info(self, pod) -> tuple:
        """
        Extract controller information from pod owner references.

        Args:
            pod: Kubernetes pod object

        Returns:
            Tuple of (controller_kind, controller_name)
        """
        if not pod.metadata.owner_references:
            return None, None

        # Get first owner reference (usually the direct controller)
        owner = pod.metadata.owner_references[0]
        controller_kind = owner.kind
        controller_name = owner.name

        # If owner is a ReplicaSet, try to find parent Deployment
        if controller_kind == 'ReplicaSet':
            try:
                apps_v1 = client.AppsV1Api()
                rs = apps_v1.read_namespaced_replica_set(
                    controller_name,
                    pod.metadata.namespace
                )
                if rs.metadata.owner_references:
                    parent_owner = rs.metadata.owner_references[0]
                    controller_kind = parent_owner.kind
                    controller_name = parent_owner.name
            except Exception as e:
                logger.debug(f"Could not resolve ReplicaSet parent: {e}")

        return controller_kind, controller_name

    def _build_pdb_selector_map(self) -> dict:
        """
        Query all PodDisruptionBudgets across the cluster and build a lookup
        structure: { namespace: [ {match_labels: dict}, ... ] }
        so we can check each pod against PDB selectors.
        """
        pdb_map: dict = {}
        try:
            pdbs = self.policy_v1.list_pod_disruption_budget_for_all_namespaces()
            for pdb in pdbs.items:
                ns = pdb.metadata.namespace
                selector = pdb.spec.selector
                if not selector or not selector.match_labels:
                    continue
                pdb_map.setdefault(ns, []).append(selector.match_labels)
            logger.debug(f"PDB map built: {sum(len(v) for v in pdb_map.values())} selectors across {len(pdb_map)} namespaces")
        except Exception as e:
            logger.warning(f"Failed to list PDBs (needs policy/v1 RBAC): {e}")
        return pdb_map

    @staticmethod
    def _pod_has_pdb(pod_labels: dict, namespace: str, pdb_map: dict) -> bool:
        """Check if a pod's labels match any PDB selector in its namespace."""
        selectors = pdb_map.get(namespace, [])
        for match_labels in selectors:
            if all(pod_labels.get(k) == v for k, v in match_labels.items()):
                return True
        return False

    def aggregate_cluster_metrics(self, pods_list, metrics):
        """
        Phase 2e (Task 5.1): Aggregate cluster-level metrics for heartbeat submission.
        This calculates hpa_pdb_data, cluster_spot_summary, and pod_metrics_per_workload.
        """
        try:
            # 1. Fetch Node capacity types
            nodes = self.core_v1.list_node(watch=False).items
            node_capacity = {}
            for n in nodes:
                labels = n.metadata.labels or {}
                # Handle standard Karpenter/EKS labels
                cap = labels.get("karpenter.sh/capacity-type") or labels.get("eks.amazonaws.com/capacityType")
                if cap:
                    node_capacity[n.metadata.name] = cap.lower()

            # 2. Extract HPA and PDB
            hpa_pdb_data = {}
            if self.autoscaling_v2:
                try:
                    hpas = self.autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces().items
                    for hpa in hpas:
                        ref = hpa.spec.scale_target_ref
                        wid = f"{hpa.metadata.namespace}/{ref.name}"
                        hpa_pdb_data.setdefault(wid, {})['hpa_min'] = hpa.spec.min_replicas
                        hpa_pdb_data.setdefault(wid, {})['hpa_max'] = hpa.spec.max_replicas
                except Exception as e:
                    logger.debug(f"HPA collection failed (might lack RBAC or api_version): {e}")

            # PDB exact minimums
            try:
                pdbs = self.policy_v1.list_pod_disruption_budget_for_all_namespaces().items
                pdb_list = []
                for pdb in pdbs:
                    ns = pdb.metadata.namespace
                    sel = pdb.spec.selector.match_labels if pdb.spec.selector else {}
                    min_a = None
                    if pdb.spec.min_available is not None:
                        try:
                            if isinstance(pdb.spec.min_available, str) and pdb.spec.min_available.endswith('%'):
                                pass 
                            else:
                                min_a = int(pdb.spec.min_available)
                        except:
                            pass
                    pdb_list.append({'ns': ns, 'sel': sel, 'min': min_a})
            except Exception as e:
                logger.debug(f"PDB collection failed: {e}")
                pdb_list = []

            # 3. Process Pods
            spot_pods = 0
            od_pods = 0
            in_flight = 0
            unhealthy_pending = 0
            
            workload_data = {}
            metrics_map = {f"{item['metadata']['namespace']}/{item['metadata']['name']}": item for item in metrics.get('items', [])}

            for p in pods_list.items:
                ns = p.metadata.namespace
                if ns in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue
                    
                kind, name = self.get_controller_info(p)
                if not name:
                    continue
                wid = f"{ns}/{name}"
                
                # Check PDB
                if 'pdb_min_available' not in hpa_pdb_data.get(wid, {}):
                    p_labels = p.metadata.labels or {}
                    for pdb in pdb_list:
                        if pdb['ns'] == ns and all(p_labels.get(k) == v for k, v in pdb['sel'].items()):
                            if pdb['min'] is not None:
                                hpa_pdb_data.setdefault(wid, {})['pdb_min_available'] = pdb['min']
                            break

                # Capacity
                cap_type = "on-demand"
                assigned_node = p.spec.node_name
                if assigned_node and assigned_node in node_capacity:
                    cap_type = node_capacity[assigned_node]
                else:
                    node_sel = p.spec.node_selector or {}
                    if node_sel.get("karpenter.sh/capacity-type") == "spot" or node_sel.get("eks.amazonaws.com/capacityType") == "spot":
                        cap_type = "spot"
                    elif p.spec.affinity and p.spec.affinity.node_affinity:
                        aff_str = str(p.spec.affinity.node_affinity.to_dict()).lower()
                        if 'spot' in aff_str:
                            cap_type = "spot"
                            
                # Phase
                phase = (p.status.phase or "").lower()
                is_running = (phase == "running")
                
                if phase in ["failed", "unknown"] or (p.status.reason == "Evicted"):
                    unhealthy_pending += 1
                elif phase == "pending":
                    unschedulable = False
                    if p.status.conditions:
                        for c in p.status.conditions:
                            if c.type == "PodScheduled" and c.reason == "Unschedulable":
                                unschedulable = True
                    if unschedulable:
                        unhealthy_pending += 1
                    elif not assigned_node:
                        start = p.metadata.creation_timestamp
                        if start and (datetime.utcnow().replace(tzinfo=start.tzinfo) - start).total_seconds() > 300:
                            unhealthy_pending += 1
                        elif cap_type == "spot":
                            in_flight += 1

                if is_running:
                    if cap_type == "spot": spot_pods += 1
                    else: od_pods += 1
                    
                w_dat = workload_data.setdefault(wid, {'spot_pods': 0, 'od_pods': 0, 'cpu_sum': 0, 'cpu_count': 0})
                if is_running:
                    if cap_type == 'spot': w_dat['spot_pods'] += 1
                    else: w_dat['od_pods'] += 1
                    
                pod_met = metrics_map.get(f"{ns}/{p.metadata.name}")
                if pod_met:
                    cpu_us = 0
                    for c in pod_met.get('containers', []):
                        cpu_us += self.parse_cpu_value(c['usage'].get('cpu', '0'))
                    w_dat['cpu_sum'] += cpu_us
                    w_dat['cpu_count'] += 1
                    
            # Finalize
            final_wds = {}
            for wid, wd in workload_data.items():
                avg_cpu = int(wd['cpu_sum'] / wd['cpu_count']) if wd['cpu_count'] > 0 else 0
                final_wds[wid] = {
                    'cpu_per_pod': avg_cpu,
                    'request_rate_per_pod': None,
                    'spot_pods': wd['spot_pods'],
                    'od_pods': wd['od_pods']
                }

            self.latest_cluster_spot_summary = {
                'total_spot_pods': spot_pods,
                'total_od_pods': od_pods,
                'in_flight_spot_pods': in_flight,
                'unhealthy_pending_pods': unhealthy_pending
            }
            self.latest_hpa_pdb_data = hpa_pdb_data
            self.pod_metrics_per_workload = final_wds

            logger.info("Phase 2e cluster aggregation completed.")
            
        except Exception as e:
            logger.error(f"Error aggregating cluster metrics: {e}", exc_info=True)

    def collect_pod_metrics(self) -> List[Dict[str, Any]]:
        """
        Collect pod-level metrics for right-sizing analysis.

        Returns:
            List of pod metric dictionaries ready for API submission
        """
        pod_metrics = []

        try:
            # Build PDB map: (namespace, label_key, label_value) -> True
            # so we can tag each pod with has_pdb=True/False.
            pdb_selector_map = self._build_pdb_selector_map()

            # Get pod metrics from metrics.k8s.io API
            metrics = self.custom_objects.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="pods"
            )

            # Get all pod details from core API
            pods_list = self.core_v1.list_pod_for_all_namespaces(watch=False)
            pod_details = {f"{p.metadata.namespace}/{p.metadata.name}": p for p in pods_list.items}

            # Phase 2e Cluster Aggregation (Task 5.1/5.2)
            self.aggregate_cluster_metrics(pods_list, metrics)

            for item in metrics.get('items', []):
                namespace = item['metadata']['namespace']
                pod_name = item['metadata']['name']
                pod_key = f"{namespace}/{pod_name}"

                pod = pod_details.get(pod_key)
                if not pod:
                    continue

                # Skip system namespaces (optional - can be configured)
                if namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                # If running as DaemonSet, only collect metrics for pods on this node
                if self.node_name and pod.spec.node_name != self.node_name:
                    continue

                # Get controller information
                controller_kind, controller_name = self.get_controller_info(pod)

                # Aggregate container metrics
                total_cpu_usage = 0
                total_memory_usage = 0
                container_count = 0

                for container in item.get('containers', []):
                    cpu_usage = self.parse_cpu_value(container['usage'].get('cpu', '0'))
                    memory_usage = self.parse_memory_value(container['usage'].get('memory', '0'))
                    total_cpu_usage += cpu_usage
                    total_memory_usage += memory_usage
                    container_count += 1

                # Calculate requests and limits from pod spec
                total_cpu_request = 0
                total_memory_request = 0
                total_cpu_limit = 0
                total_memory_limit = 0

                for container in pod.spec.containers:
                    if container.resources and container.resources.requests:
                        total_cpu_request += self.parse_cpu_value(
                            container.resources.requests.get('cpu', '0')
                        )
                        total_memory_request += self.parse_memory_value(
                            container.resources.requests.get('memory', '0')
                        )

                    if container.resources and container.resources.limits:
                        total_cpu_limit += self.parse_cpu_value(
                            container.resources.limits.get('cpu', '0')
                        )
                        total_memory_limit += self.parse_memory_value(
                            container.resources.limits.get('memory', '0')
                        )

                # Build metric object matching PodMetricCreate schema
                # Extract scheduling constraints for simulation accuracy
                _node_sel = None
                if pod.spec.node_selector:
                    _node_sel = dict(pod.spec.node_selector)

                _tolerations = None
                if pod.spec.tolerations:
                    _tolerations = []
                    for t in pod.spec.tolerations:
                        _tol = {}
                        if t.key: _tol['key'] = t.key
                        if t.operator: _tol['operator'] = t.operator
                        if t.value: _tol['value'] = t.value
                        if t.effect: _tol['effect'] = t.effect
                        if _tol.get('key'):  # skip empty default tolerations
                            _tolerations.append(_tol)

                _affinity = None
                if pod.spec.affinity:
                    _aff = {}
                    if pod.spec.affinity.pod_anti_affinity:
                        _pa = pod.spec.affinity.pod_anti_affinity
                        if _pa.required_during_scheduling_ignored_during_execution:
                            _aff['pod_anti_affinity_required'] = True
                    if pod.spec.affinity.pod_affinity:
                        _pa2 = pod.spec.affinity.pod_affinity
                        if _pa2.required_during_scheduling_ignored_during_execution:
                            _aff['pod_affinity_required'] = True
                    if pod.spec.affinity.node_affinity:
                        _na = pod.spec.affinity.node_affinity
                        if _na.required_during_scheduling_ignored_during_execution:
                            _aff['node_affinity_required'] = True
                    if _aff:
                        _affinity = _aff

                _topo_spread = None
                if pod.spec.topology_spread_constraints:
                    _topo_spread = []
                    for tsc in pod.spec.topology_spread_constraints:
                        _topo_spread.append({
                            'max_skew': tsc.max_skew,
                            'topology_key': tsc.topology_key,
                            'when_unsatisfiable': tsc.when_unsatisfiable,
                            'label_selector_match_labels': (tsc.label_selector.match_labels or {}) if tsc.label_selector else {},
                        })

                # Detect PVC volumes — persistent storage means pod is stateful.
                _has_pvc = any(
                    v.persistent_volume_claim is not None
                    for v in (pod.spec.volumes or [])
                )

                # W1.1 — Collect container images for workload classification.
                # W1.1a — Exclude init containers and known sidecar container names.
                _container_images = [
                    c.image for c in pod.spec.containers
                    if c.image and c.name not in _SIDECAR_NAMES
                ][:20]  # cap at 20 to limit payload size

                # Task 1.11 — Collect init container metadata for DB migration detection.
                # These are used by the backend classifier (Task 1.6) to detect
                # DB migration tools like Flyway, Liquibase, Alembic, etc.
                _init_containers = []
                for ic in (pod.spec.init_containers or []):
                    ic_entry = {"name": ic.name, "image": ic.image or ""}
                    if ic.ports:
                        ic_entry["ports"] = [
                            {"container_port": p.container_port}
                            for p in ic.ports
                        ]
                    _init_containers.append(ic_entry)

                # W1.1 — Collect container ports (excluding sidecar containers).
                _container_ports = []
                for c in pod.spec.containers:
                    if c.name in _SIDECAR_NAMES:
                        continue
                    if c.ports:
                        for p in c.ports:
                            _container_ports.append({
                                'container_port': p.container_port,
                                'protocol': p.protocol or 'TCP',
                                'name': p.name,
                            })
                _container_ports = _container_ports[:50]  # cap at 50

                # W1.2 — Collect env var KEYS only (never values) filtered to
                # classification-relevant patterns to prevent credential leakage.
                _env_var_keys = []
                for c in pod.spec.containers:
                    if c.name in _SIDECAR_NAMES:
                        continue
                    for ev in (c.env or []):
                        if not ev.name:
                            continue
                        lower = ev.name.lower()
                        if any(lower.startswith(prefix) for prefix in _CLASSIFICATION_SAFE_ENV_PREFIXES):
                            _env_var_keys.append(ev.name)
                _env_var_keys = list(dict.fromkeys(_env_var_keys))[:100]  # dedupe + cap at 100

                _pod_start_time = None
                if pod.status.start_time:
                    try:
                        _pod_start_time = pod.status.start_time.isoformat()
                    except Exception:
                        pass

                pod_metric = {
                    'namespace': namespace,
                    'pod_name': pod_name,
                    'node_name': pod.spec.node_name or 'unknown',
                    'controller_kind': controller_kind,
                    'controller_name': controller_name,
                    'cpu_usage_millicores': total_cpu_usage,
                    'cpu_request_millicores': total_cpu_request if total_cpu_request > 0 else None,
                    'cpu_limit_millicores': total_cpu_limit if total_cpu_limit > 0 else None,
                    'memory_usage_bytes': total_memory_usage,
                    'memory_request_bytes': total_memory_request if total_memory_request > 0 else None,
                    'memory_limit_bytes': total_memory_limit if total_memory_limit > 0 else None,
                    'container_count': container_count,
                    'phase': pod.status.phase,
                    'start_time': _pod_start_time,
                    'metadata': {
                        'labels': pod.metadata.labels or {},
                        'phase': pod.status.phase,
                        'qos_class': pod.status.qos_class,
                        'node_selector': _node_sel,
                        'tolerations': _tolerations,
                        'affinity': _affinity,
                        'topology_spread_constraints': _topo_spread,
                        'termination_grace_period_s': pod.spec.termination_grace_period_seconds,
                        'readiness_initial_delay_s': max(
                            (c.readiness_probe.initial_delay_seconds or 0)
                            for c in pod.spec.containers
                            if c.readiness_probe
                        ) if any(c.readiness_probe for c in pod.spec.containers) else None,
                        'host_network': bool(pod.spec.host_network),
                        # PVC detection — needed for stateful pod classification in the backend
                        'has_pvc': _has_pvc,
                        # PDB detection — needed for spot-friendliness classification
                        'has_pdb': self._pod_has_pdb(
                            pod.metadata.labels or {}, namespace, pdb_selector_map
                        ),
                        # W1.1 — images + ports for workload type classification
                        'container_images': _container_images,
                        'container_ports': _container_ports,
                        # W1.2 — env var keys (filtered, no values)
                        'env_var_keys': _env_var_keys,
                        # Task 1.11 — init container data for DB migration detection
                        'init_containers': _init_containers,
                    }
                }

                pod_metrics.append(pod_metric)

            logger.info(f"Collected metrics for {len(pod_metrics)} pods on node {self.node_name}")

        except ApiException as e:
            logger.error(f"Failed to collect pod metrics from metrics API: {e}")
        except Exception as e:
            logger.error(f"Unexpected error collecting pod metrics: {e}", exc_info=True)

        return pod_metrics

    def send_pod_metrics_batch(self, metrics: List[Dict[str, Any]]) -> bool:
        """
        Send pod metrics batch to backend.

        Args:
            metrics: List of pod metric dictionaries

        Returns:
            True if successful, False otherwise
        """
        if not metrics:
            logger.info("No pod metrics to send")
            return True

        url = f"{self.backend_url}/api/v1/pod-metrics/batch"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }

        payload = {
            'cluster_id': self.cluster_id,
            'node_name': self.node_name or 'unknown',
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': metrics
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()

                result = response.json()
                logger.info(f"Successfully sent {result.get('metrics_inserted', 0)} pod metrics to backend")

                if result.get('errors'):
                    logger.warning(f"Some errors occurred: {result['errors']}")

                return True

            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 10)
                    logger.warning(f"Pod metrics send attempt {attempt}/{max_retries} failed: {e}. Retrying in {backoff}s...")
                    import time
                    time.sleep(backoff)
                else:
                    logger.error(f"Failed to send pod metrics after {max_retries} attempts: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        logger.error(f"Response status: {e.response.status_code}")
                    return False

    def collect_hpa_configs(self) -> List[Dict[str, Any]]:
        """
        T-13: Collect per-HPA config and runtime status for DB persistence.
        Returns list of HPA dicts compatible with HpaConfigItem schema.
        Skips gracefully if no HPAs exist (KEDA-only cluster).
        """
        hpa_list = []
        if not self.autoscaling_v2:
            return hpa_list
        try:
            hpas = self.autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces().items
            for hpa in hpas:
                spec = hpa.spec
                status = hpa.status
                ref = spec.scale_target_ref
                ns = hpa.metadata.namespace

                target_cpu_pct = None
                if spec.metrics:
                    for m in spec.metrics:
                        if (m.type == 'Resource'
                                and m.resource
                                and getattr(m.resource, 'name', None) == 'cpu'
                                and m.resource.target):
                            target_cpu_pct = getattr(m.resource.target, 'average_utilization', None)
                            break

                cpu_util_pct = None
                if status.current_metrics:
                    for cm in status.current_metrics:
                        if (cm.type == 'Resource'
                                and cm.resource
                                and getattr(cm.resource, 'name', None) == 'cpu'
                                and cm.resource.current):
                            cpu_util_pct = getattr(cm.resource.current, 'average_utilization', None)
                            break

                scale_up_s = None
                scale_down_s = None
                if spec.behavior:
                    if spec.behavior.scale_up and spec.behavior.scale_up.stabilization_window_seconds:
                        scale_up_s = spec.behavior.scale_up.stabilization_window_seconds
                    if spec.behavior.scale_down and spec.behavior.scale_down.stabilization_window_seconds:
                        scale_down_s = spec.behavior.scale_down.stabilization_window_seconds

                hpa_list.append({
                    'namespace': ns,
                    'workload_name': ref.name,
                    'hpa_name': hpa.metadata.name,
                    'min_replicas': spec.min_replicas,
                    'max_replicas': spec.max_replicas,
                    'target_cpu_pct': target_cpu_pct,
                    'current_replicas': status.current_replicas,
                    'desired_replicas': status.desired_replicas,
                    'scale_up_stabilization_seconds': scale_up_s,
                    'scale_down_stabilization_seconds': scale_down_s,
                    'cpu_utilization_pct': cpu_util_pct,
                })
        except Exception as exc:
            logger.debug(f"HPA config collection failed (no HPAs or RBAC missing): {exc}")
        return hpa_list

    def send_hpa_configs_batch(self, hpas: List[Dict[str, Any]]) -> bool:
        """
        T-13: Push HPA configs to /api/v1/agents/hpa-configs/batch.
        """
        if not hpas:
            return True
        url = f"{self.backend_url}/api/v1/agents/hpa-configs/batch"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true',
        }
        try:
            resp = requests.post(
                url,
                json={'cluster_id': self.cluster_id, 'hpas': hpas},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            logger.debug(f"HPA configs pushed: {len(hpas)}")
            return True
        except Exception as exc:
            logger.warning(f"HPA configs batch push failed: {exc}")
            return False

    def collect_and_send(self):
        """
        Main collection loop: collect pod metrics and send to backend.
        """
        logger.info("Starting pod metrics collection cycle")

        try:
            # Collect pod metrics
            pod_metrics = self.collect_pod_metrics()

            # Send to backend
            if pod_metrics:
                self.send_pod_metrics_batch(pod_metrics)
            else:
                logger.info("No pod metrics collected (this is normal for nodes with no pods)")

            # T-13: Collect and push HPA configs
            import os as _os
            if _os.getenv('FEATURE_HPA_CONFIG_PUSH', 'true').lower() == 'true':
                try:
                    hpa_data = self.collect_hpa_configs()
                    if hpa_data:
                        self.send_hpa_configs_batch(hpa_data)
                except Exception as exc:
                    logger.warning(f"HPA configs collection skipped: {exc}")

        except Exception as e:
            logger.error(f"Error in pod metrics collection cycle: {e}", exc_info=True)

        logger.info("Pod metrics collection cycle complete")

    def run(self):
        """
        Run the pod metrics collector in a loop.
        """
        self.running = True
        logger.info(f"Starting pod metrics collector with {self.collection_interval}s interval")

        while self.running:
            try:
                self.collect_and_send()
            except Exception as e:
                logger.error(f"Error in collection cycle: {e}", exc_info=True)

            # Wait for next collection interval
            time.sleep(self.collection_interval)

        logger.info("Pod metrics collector stopped")

    def stop(self):
        """
        Stop the pod metrics collector.
        """
        logger.info("Stopping pod metrics collector...")
        self.running = False
