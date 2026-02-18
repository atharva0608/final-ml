"""
Namespace Sleep Strategy (NAMESPACE_SLEEP)

Gentle hibernation by scaling workloads to 0 replicas and letting
Cluster Autoscaler naturally drain nodes.

Characteristics:
- Wake Time: ~2 minutes
- Cost Savings: ~80%
- Safety: HIGH (preserves PVCs, gentle shutdown)
- Best For: Stateless dev/test workloads

Configuration Parameters (editable):
- SYSTEM_NAMESPACES: List of namespaces to exclude from hibernation
- GRACE_PERIOD_SECONDS: Pod termination grace period
- WAIT_FOR_READINESS: Enable/disable waiting for pod readiness on wake
- MAX_WAIT_SECONDS: Maximum time to wait for pod readiness
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - Edit these parameters to change strategy behavior
# =============================================================================

# Namespaces to exclude from hibernation (system namespaces)
SYSTEM_NAMESPACES = [
    'kube-system',
    'kube-public',
    'kube-node-lease',
    'default',
    'monitoring',
    'logging',
    'cert-manager',
    'ingress-nginx',
    'istio-system',
    'knative-serving',
]

# Pod termination grace period (seconds)
GRACE_PERIOD_SECONDS = 30

# Wait for pod readiness on wake
WAIT_FOR_READINESS = True

# Maximum wait time for pod readiness (seconds)
MAX_WAIT_SECONDS = 300

# Resource scaling order (sleep)
SLEEP_ORDER = [
    'hpas',           # Horizontal Pod Autoscalers (disable first)
    'deployments',    # Deployments (scale to 0)
    'statefulsets',   # StatefulSets (scale to 0, preserve PVCs)
]

# Resource restoration order (wake) - REVERSE of sleep order
WAKE_ORDER = [
    'statefulsets',   # StatefulSets first (allow PVC reattachment)
    'deployments',    # Deployments second
    'hpas',           # HPAs last (re-enable autoscaling)
]

# Hibernation metadata tags
HIBERNATION_TAGS = {
    'hibernation.io/managed': 'true',
    'hibernation.io/strategy': 'NAMESPACE_SLEEP',
    'hibernation.io/timestamp': None,  # Set dynamically
}

# =============================================================================
# NAMESPACE SLEEP STRATEGY CLASS
# =============================================================================

class NamespaceSleepStrategy:
    """
    Namespace Sleep Strategy Implementation

    This class encapsulates all logic for the NAMESPACE_SLEEP hibernation strategy.
    All configuration parameters are defined above and can be edited.
    """

    def __init__(self):
        self.system_namespaces = SYSTEM_NAMESPACES
        self.grace_period = GRACE_PERIOD_SECONDS
        self.wait_for_readiness = WAIT_FOR_READINESS
        self.max_wait_seconds = MAX_WAIT_SECONDS
        self.sleep_order = SLEEP_ORDER
        self.wake_order = WAKE_ORDER
        self.hibernation_tags = HIBERNATION_TAGS.copy()
        self.hibernation_tags['hibernation.io/timestamp'] = datetime.utcnow().isoformat()

    def execute_sleep(self, cluster, schedule, db: Session, k8s_clients: Dict) -> Dict[str, Any]:
        """
        Execute Namespace Sleep hibernation

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            k8s_clients: Dict with 'core_v1', 'apps_v1', 'autoscaling_v1' K8s clients

        Returns:
            Dict with sleep results including namespaces affected and resource counts
        """
        logger.info(f"[NAMESPACE_SLEEP] Starting sleep for cluster: {cluster.name}")

        core_v1 = k8s_clients['core_v1']
        apps_v1 = k8s_clients['apps_v1']
        autoscaling_v1 = k8s_clients['autoscaling_v1']

        # Build state snapshot
        saved_state = {
            'timestamp': datetime.utcnow().isoformat(),
            'strategy': 'NAMESPACE_SLEEP',
            'namespaces': {}
        }

        # Get all namespaces
        namespaces = core_v1.list_namespace()

        for ns in namespaces.items:
            ns_name = ns.metadata.name

            # Skip system namespaces
            if ns_name in self.system_namespaces:
                logger.debug(f"[NAMESPACE_SLEEP] Skipping system namespace: {ns_name}")
                continue

            logger.info(f"[NAMESPACE_SLEEP] Processing namespace: {ns_name}")

            ns_state = {
                'hpas': [],
                'deployments': [],
                'statefulsets': [],
                'daemonsets': [],  # Track but don't scale
                'pvcs': []
            }

            # === STEP 1: Store PVC information (for state tracking) ===
            ns_state['pvcs'] = self._save_pvc_state(core_v1, ns_name)

            # === STEP 2: Store DaemonSet information (don't scale) ===
            ns_state['daemonsets'] = self._save_daemonset_state(apps_v1, ns_name)

            # === STEP 3: Scale resources in configured order ===
            for resource_type in self.sleep_order:
                if resource_type == 'hpas':
                    ns_state['hpas'] = self._scale_hpas(autoscaling_v1, ns_name)
                elif resource_type == 'deployments':
                    ns_state['deployments'] = self._scale_deployments(apps_v1, ns_name)
                elif resource_type == 'statefulsets':
                    ns_state['statefulsets'] = self._scale_statefulsets(apps_v1, ns_name)

            # Save namespace state if it has resources
            if any(ns_state.values()):
                saved_state['namespaces'][ns_name] = ns_state

        # Save state to schedule
        schedule.saved_state = saved_state
        schedule.last_action = 'SLEEP'
        schedule.last_action_at = datetime.utcnow()
        db.commit()

        # Calculate summary
        namespaces_affected = list(saved_state.get('namespaces', {}).keys())
        total_resources = sum(
            len(ns.get('hpas', [])) + len(ns.get('deployments', [])) + len(ns.get('statefulsets', []))
            for ns in saved_state.get('namespaces', {}).values()
        )

        result = {
            'status': 'success',
            'strategy': 'NAMESPACE_SLEEP',
            'namespaces_affected': namespaces_affected,
            'total_resources_hibernated': total_resources,
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"[NAMESPACE_SLEEP] Sleep completed - {total_resources} resources in {len(namespaces_affected)} namespaces")
        return result

    def execute_wake(self, cluster, schedule, db: Session, k8s_clients: Dict) -> Dict[str, Any]:
        """
        Execute Namespace Wake (restore resources)

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            k8s_clients: Dict with 'core_v1', 'apps_v1', 'autoscaling_v1' K8s clients

        Returns:
            Dict with wake results including namespaces restored and resource counts
        """
        logger.info(f"[NAMESPACE_SLEEP] Starting wake for cluster: {cluster.name}")

        apps_v1 = k8s_clients['apps_v1']
        autoscaling_v1 = k8s_clients['autoscaling_v1']

        saved_state = schedule.saved_state or {}
        namespaces_state = saved_state.get('namespaces', {})

        if not namespaces_state:
            logger.warning(f"[NAMESPACE_SLEEP] No saved state found for cluster {cluster.name}")
            return {'status': 'error', 'message': 'No saved state found'}

        resources_restored = 0

        # === Restore resources in REVERSE order (wake order) ===
        for ns_name, ns_state in namespaces_state.items():
            logger.info(f"[NAMESPACE_SLEEP] Restoring namespace: {ns_name}")

            for resource_type in self.wake_order:
                if resource_type == 'statefulsets':
                    resources_restored += self._restore_statefulsets(apps_v1, ns_name, ns_state.get('statefulsets', []))
                elif resource_type == 'deployments':
                    resources_restored += self._restore_deployments(apps_v1, ns_name, ns_state.get('deployments', []))
                elif resource_type == 'hpas':
                    resources_restored += self._restore_hpas(autoscaling_v1, ns_name, ns_state.get('hpas', []))

        # Update schedule
        schedule.last_action = 'WAKE'
        schedule.last_action_at = datetime.utcnow()
        db.commit()

        result = {
            'status': 'success',
            'strategy': 'NAMESPACE_SLEEP',
            'namespaces_restored': list(namespaces_state.keys()),
            'total_resources_restored': resources_restored,
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"[NAMESPACE_SLEEP] Wake completed - {resources_restored} resources restored")
        return result

    # =========================================================================
    # HELPER METHODS - Sleep Operations
    # =========================================================================

    def _save_pvc_state(self, core_v1, ns_name: str) -> List[Dict]:
        """Save PVC state for tracking (not modified during sleep)"""
        pvcs_state = []
        try:
            pvcs = core_v1.list_namespaced_persistent_volume_claim(ns_name)
            for pvc in pvcs.items:
                pvcs_state.append({
                    'name': pvc.metadata.name,
                    'storage_class': pvc.spec.storage_class_name,
                    'volume_name': pvc.spec.volume_name,
                    'size': str(pvc.spec.resources.requests.get('storage', '')) if pvc.spec.resources else None
                })
            if pvcs.items:
                logger.info(f"[NAMESPACE_SLEEP] Found {len(pvcs.items)} PVCs in {ns_name}")
        except Exception as e:
            logger.warning(f"[NAMESPACE_SLEEP] PVC listing error in {ns_name}: {e}")
        return pvcs_state

    def _save_daemonset_state(self, apps_v1, ns_name: str) -> List[Dict]:
        """Save DaemonSet state for tracking (not scaled during sleep)"""
        ds_state = []
        try:
            daemonsets = apps_v1.list_namespaced_daemon_set(ns_name)
            for ds in daemonsets.items:
                ds_state.append({'name': ds.metadata.name})
            if daemonsets.items:
                logger.info(f"[NAMESPACE_SLEEP] Found {len(daemonsets.items)} DaemonSets in {ns_name} (keeping active)")
        except Exception as e:
            logger.warning(f"[NAMESPACE_SLEEP] DaemonSet listing error in {ns_name}: {e}")
        return ds_state

    def _scale_hpas(self, autoscaling_v1, ns_name: str) -> List[Dict]:
        """Scale HPAs to 0 (disable autoscaling)"""
        hpas_state = []
        try:
            hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(ns_name)
            for hpa in hpas.items:
                original_min = hpa.spec.min_replicas or 1
                original_max = hpa.spec.max_replicas or 1

                hpas_state.append({
                    'name': hpa.metadata.name,
                    'original_min_replicas': original_min,
                    'original_max_replicas': original_max,
                    'target_cpu': hpa.spec.target_cpu_utilization_percentage
                })

                # Add hibernation annotations
                if not hpa.metadata.annotations:
                    hpa.metadata.annotations = {}
                hpa.metadata.annotations.update(self.hibernation_tags)
                hpa.metadata.annotations['hibernation.io/original-min-replicas'] = str(original_min)
                hpa.metadata.annotations['hibernation.io/original-max-replicas'] = str(original_max)

                # Disable HPA
                hpa.spec.min_replicas = 0
                autoscaling_v1.patch_namespaced_horizontal_pod_autoscaler(hpa.metadata.name, ns_name, hpa)

                logger.info(f"[NAMESPACE_SLEEP] Disabled HPA: {hpa.metadata.name} (was min={original_min})")
        except Exception as e:
            logger.warning(f"[NAMESPACE_SLEEP] HPA scaling error in {ns_name}: {e}")
        return hpas_state

    def _scale_deployments(self, apps_v1, ns_name: str) -> List[Dict]:
        """Scale Deployments to 0 replicas"""
        deployments_state = []
        try:
            deployments = apps_v1.list_namespaced_deployment(ns_name)
            for dep in deployments.items:
                original_replicas = dep.spec.replicas or 0

                deployments_state.append({
                    'name': dep.metadata.name,
                    'original_replicas': original_replicas,
                    'selector': dep.spec.selector.match_labels if dep.spec.selector else {}
                })

                # Add hibernation annotations
                if not dep.metadata.annotations:
                    dep.metadata.annotations = {}
                dep.metadata.annotations.update(self.hibernation_tags)
                dep.metadata.annotations['hibernation.io/original-replicas'] = str(original_replicas)

                # Scale to 0
                dep.spec.replicas = 0
                apps_v1.patch_namespaced_deployment(dep.metadata.name, ns_name, dep)

                logger.info(f"[NAMESPACE_SLEEP] Scaled Deployment: {dep.metadata.name} ({original_replicas} → 0)")
        except Exception as e:
            logger.warning(f"[NAMESPACE_SLEEP] Deployment scaling error in {ns_name}: {e}")
        return deployments_state

    def _scale_statefulsets(self, apps_v1, ns_name: str) -> List[Dict]:
        """Scale StatefulSets to 0 replicas (preserves PVCs)"""
        statefulsets_state = []
        try:
            statefulsets = apps_v1.list_namespaced_stateful_set(ns_name)
            for ss in statefulsets.items:
                original_replicas = ss.spec.replicas or 0
                volume_claim_templates = []

                if ss.spec.volume_claim_templates:
                    volume_claim_templates = [
                        {
                            'name': vct.metadata.name,
                            'storage_class': vct.spec.storage_class_name,
                            'size': str(vct.spec.resources.requests.get('storage', '')) if vct.spec.resources else None
                        }
                        for vct in ss.spec.volume_claim_templates
                    ]

                statefulsets_state.append({
                    'name': ss.metadata.name,
                    'original_replicas': original_replicas,
                    'volume_claim_templates': volume_claim_templates
                })

                # Add hibernation annotations
                if not ss.metadata.annotations:
                    ss.metadata.annotations = {}
                ss.metadata.annotations.update(self.hibernation_tags)
                ss.metadata.annotations['hibernation.io/original-replicas'] = str(original_replicas)

                # Scale to 0 (PVCs preserved automatically)
                ss.spec.replicas = 0
                apps_v1.patch_namespaced_stateful_set(ss.metadata.name, ns_name, ss)

                logger.info(f"[NAMESPACE_SLEEP] Scaled StatefulSet: {ss.metadata.name} ({original_replicas} → 0, PVCs preserved)")
        except Exception as e:
            logger.warning(f"[NAMESPACE_SLEEP] StatefulSet scaling error in {ns_name}: {e}")
        return statefulsets_state

    # =========================================================================
    # HELPER METHODS - Wake Operations
    # =========================================================================

    def _restore_statefulsets(self, apps_v1, ns_name: str, statefulsets: List[Dict]) -> int:
        """Restore StatefulSets to original replica count"""
        restored = 0
        for ss_state in statefulsets:
            try:
                ss_name = ss_state['name']
                original_replicas = ss_state['original_replicas']

                ss = apps_v1.read_namespaced_stateful_set(ss_name, ns_name)
                ss.spec.replicas = original_replicas

                # Remove hibernation annotations
                if ss.metadata.annotations:
                    ss.metadata.annotations.pop('hibernation.io/original-replicas', None)
                    for key in list(ss.metadata.annotations.keys()):
                        if key.startswith('hibernation.io/'):
                            ss.metadata.annotations.pop(key, None)

                apps_v1.patch_namespaced_stateful_set(ss_name, ns_name, ss)
                logger.info(f"[NAMESPACE_SLEEP] Restored StatefulSet: {ss_name} (0 → {original_replicas})")
                restored += 1
            except Exception as e:
                logger.error(f"[NAMESPACE_SLEEP] Failed to restore StatefulSet {ss_state.get('name')}: {e}")
        return restored

    def _restore_deployments(self, apps_v1, ns_name: str, deployments: List[Dict]) -> int:
        """Restore Deployments to original replica count"""
        restored = 0
        for dep_state in deployments:
            try:
                dep_name = dep_state['name']
                original_replicas = dep_state['original_replicas']

                dep = apps_v1.read_namespaced_deployment(dep_name, ns_name)
                dep.spec.replicas = original_replicas

                # Remove hibernation annotations
                if dep.metadata.annotations:
                    dep.metadata.annotations.pop('hibernation.io/original-replicas', None)
                    for key in list(dep.metadata.annotations.keys()):
                        if key.startswith('hibernation.io/'):
                            dep.metadata.annotations.pop(key, None)

                apps_v1.patch_namespaced_deployment(dep_name, ns_name, dep)
                logger.info(f"[NAMESPACE_SLEEP] Restored Deployment: {dep_name} (0 → {original_replicas})")
                restored += 1
            except Exception as e:
                logger.error(f"[NAMESPACE_SLEEP] Failed to restore Deployment {dep_state.get('name')}: {e}")
        return restored

    def _restore_hpas(self, autoscaling_v1, ns_name: str, hpas: List[Dict]) -> int:
        """Restore HPAs to original min/max replicas"""
        restored = 0
        for hpa_state in hpas:
            try:
                hpa_name = hpa_state['name']
                original_min = hpa_state['original_min_replicas']
                original_max = hpa_state['original_max_replicas']

                hpa = autoscaling_v1.read_namespaced_horizontal_pod_autoscaler(hpa_name, ns_name)
                hpa.spec.min_replicas = original_min
                hpa.spec.max_replicas = original_max

                # Remove hibernation annotations
                if hpa.metadata.annotations:
                    hpa.metadata.annotations.pop('hibernation.io/original-min-replicas', None)
                    hpa.metadata.annotations.pop('hibernation.io/original-max-replicas', None)
                    for key in list(hpa.metadata.annotations.keys()):
                        if key.startswith('hibernation.io/'):
                            hpa.metadata.annotations.pop(key, None)

                autoscaling_v1.patch_namespaced_horizontal_pod_autoscaler(hpa_name, ns_name, hpa)
                logger.info(f"[NAMESPACE_SLEEP] Restored HPA: {hpa_name} (min: 0 → {original_min})")
                restored += 1
            except Exception as e:
                logger.error(f"[NAMESPACE_SLEEP] Failed to restore HPA {hpa_state.get('name')}: {e}")
        return restored


# =============================================================================
# STRATEGY RULES - Edit these to change behavior
# =============================================================================

STRATEGY_RULES = {
    'name': 'Namespace Sleep',
    'code': 'NAMESPACE_SLEEP',
    'wake_time_minutes': 2,
    'cost_savings_percent': 80,
    'safety_level': 'HIGH',
    'best_for': 'Stateless dev/test workloads',
    'description': 'Scales workloads to 0 replicas. Cluster Autoscaler drains idle nodes naturally.',

    # Editable rules
    'system_namespaces': SYSTEM_NAMESPACES,
    'grace_period_seconds': GRACE_PERIOD_SECONDS,
    'wait_for_readiness': WAIT_FOR_READINESS,
    'max_wait_seconds': MAX_WAIT_SECONDS,
    'sleep_order': SLEEP_ORDER,
    'wake_order': WAKE_ORDER,
    'hibernation_tags': HIBERNATION_TAGS,
}
