"""
Namespace Sleep Strategy

Scales all Kubernetes workloads to 0 replicas, letting the cluster
autoscaler drain nodes naturally. Fastest and safest hibernation method.
"""
from typing import Dict, List, Any
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import logging
import time

logger = logging.getLogger(__name__)


# Editable Configuration Parameters
class NamespaceSleepConfig:
    """Configuration for Namespace Sleep Strategy"""
    
    # Namespaces to exclude from hibernation
    SYSTEM_NAMESPACES = [
        "kube-system",
        "kube-public",
        "kube-node-lease",
        "spot-optimizer"  # Don't sleep our own system
    ]
    
    # Grace period for pod termination (seconds)
    GRACE_PERIOD_SECONDS = 30
    
    # Sleep order: which resources to scale down first
    SLEEP_ORDER = [
        "Deployment",
        "StatefulSet",
        "DaemonSet",  # Note: DaemonSets usually shouldn't be scaled
        "CronJob",
        "Job"
    ]
    
    # Wake order: which resources to restore first
    WAKE_ORDER = [
        "StatefulSet",  # Stateful apps first for data consistency
        "Deployment",
        "CronJob",
        "Job"
    ]
    
    # Maximum concurrent operations
    MAX_CONCURRENT_OPERATIONS = 10
    
    # Wait time between operations (seconds)
    OPERATION_DELAY_SECONDS = 0.5
    
    # Timeout for waiting for pods to terminate (seconds)
    POD_TERMINATION_TIMEOUT = 300
    
    # Whether to handle PodDisruptionBudgets
    RESPECT_PDB = True


class NamespaceSleepStrategy:
    """
    Namespace Sleep Hibernation Strategy
    
    Scales all deployments and statefulsets to 0 replicas.
    Saves original replica counts for restoration.
    """
    
    def __init__(self, cluster_config: Dict[str, Any]):
        """
        Initialize strategy with cluster configuration
        
        Args:
            cluster_config: Dict containing kubeconfig or cluster connection info
        """
        self.cluster_config = cluster_config
        self.config = NamespaceSleepConfig()
        self.api_client = None
        self.apps_v1 = None
        self.core_v1 = None
        
    def _init_kubernetes_client(self):
        """Initialize Kubernetes API clients"""
        try:
            # Load from kubeconfig or in-cluster config
            if "kubeconfig" in self.cluster_config:
                config.load_kube_config_from_dict(self.cluster_config["kubeconfig"])
            else:
                config.load_incluster_config()
            
            self.apps_v1 = client.AppsV1Api()
            self.core_v1 = client.CoreV1Api()
            self.batch_v1 = client.BatchV1Api()
            
            logger.info("Kubernetes client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            raise
    
    def sleep(self, saved_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute sleep action: scale all workloads to 0
        
        Args:
            saved_state: Optional existing saved state to restore from
            
        Returns:
            Dict containing saved state with original replica counts
        """
        logger.info("Starting Namespace Sleep hibernation")
        self._init_kubernetes_client()
        
        state = saved_state or {"deployments": {}, "statefulsets": {}, "jobs": {}}
        errors = []
        
        try:
            # Get all namespaces except system ones
            namespaces = self._get_target_namespaces()
            logger.info(f"Targeting {len(namespaces)} namespaces for hibernation")
            
            # Process each resource type in sleep order
            for resource_type in self.config.SLEEP_ORDER:
                if resource_type == "Deployment":
                    self._sleep_deployments(namespaces, state, errors)
                elif resource_type == "StatefulSet":
                    self._sleep_statefulsets(namespaces, state, errors)
                elif resource_type == "CronJob":
                    self._sleep_cronjobs(namespaces, state, errors)
            
            # Wait for pods to terminate
            self._wait_for_pod_termination(namespaces)
            
            logger.info(f"Namespace Sleep completed. Scaled down {len(state.get('deployments', {}))} deployments, {len(state.get('statefulsets', {}))} statefulsets")
            
            if errors:
                logger.warning(f"Completed with {len(errors)} errors: {errors}")
                
            return {"state": state, "errors": errors}
            
        except Exception as e:
            logger.error(f"Critical error during Namespace Sleep: {e}")
            raise
    
    def wake(self, saved_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute wake action: restore original replica counts
        
        Args:
            saved_state: Saved state from sleep operation
            
        Returns:
            Dict containing wake operation results
        """
        logger.info("Starting Namespace Sleep wake operation")
        self._init_kubernetes_client()
        
        errors = []
        
        try:
            # Restore resources in wake order
            for resource_type in self.config.WAKE_ORDER:
                if resource_type == "StatefulSet":
                    self._wake_statefulsets(saved_state.get("statefulsets", {}), errors)
                elif resource_type == "Deployment":
                    self._wake_deployments(saved_state.get("deployments", {}), errors)
                elif resource_type == "CronJob":
                    self._wake_cronjobs(saved_state.get("cronjobs", {}), errors)
            
            logger.info("Namespace Sleep wake completed")
            
            if errors:
                logger.warning(f"Completed with {len(errors)} errors: {errors}")
                
            return {"status": "success", "errors": errors}
            
        except Exception as e:
            logger.error(f"Critical error during wake: {e}")
            raise
    
    def _get_target_namespaces(self) -> List[str]:
        """Get list of namespaces to target"""
        all_namespaces = self.core_v1.list_namespace()
        target_namespaces = [
            ns.metadata.name for ns in all_namespaces.items
            if ns.metadata.name not in self.config.SYSTEM_NAMESPACES
        ]
        return target_namespaces
    
    def _sleep_deployments(self, namespaces: List[str], state: Dict, errors: List):
        """Scale all deployments to 0"""
        for namespace in namespaces:
            try:
                deployments = self.apps_v1.list_namespaced_deployment(namespace)
                
                for deployment in deployments.items:
                    dep_name = deployment.metadata.name
                    current_replicas = deployment.spec.replicas
                    
                    # Save original replica count
                    key = f"{namespace}/{dep_name}"
                    state["deployments"][key] = current_replicas
                    
                    # Scale to 0
                    if current_replicas > 0:
                        deployment.spec.replicas = 0
                        self.apps_v1.patch_namespaced_deployment(
                            name=dep_name,
                            namespace=namespace,
                            body=deployment
                        )
                        logger.debug(f"Scaled deployment {key} from {current_replicas} to 0")
                        time.sleep(self.config.OPERATION_DELAY_SECONDS)
                        
            except ApiException as e:
                error_msg = f"Error scaling deployments in {namespace}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    def _sleep_statefulsets(self, namespaces: List[str], state: Dict, errors: List):
        """Scale all statefulsets to 0"""
        for namespace in namespaces:
            try:
                statefulsets = self.apps_v1.list_namespaced_stateful_set(namespace)
                
                for sts in statefulsets.items:
                    sts_name = sts.metadata.name
                    current_replicas = sts.spec.replicas
                    
                    # Save original replica count
                    key = f"{namespace}/{sts_name}"
                    state["statefulsets"][key] = current_replicas
                    
                    # Scale to 0
                    if current_replicas > 0:
                        sts.spec.replicas = 0
                        self.apps_v1.patch_namespaced_stateful_set(
                            name=sts_name,
                            namespace=namespace,
                            body=sts
                        )
                        logger.debug(f"Scaled statefulset {key} from {current_replicas} to 0")
                        time.sleep(self.config.OPERATION_DELAY_SECONDS)
                        
            except ApiException as e:
                error_msg = f"Error scaling statefulsets in {namespace}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    def _sleep_cronjobs(self, namespaces: List[str], state: Dict, errors: List):
        """Suspend all cronjobs"""
        state.setdefault("cronjobs", {})
        
        for namespace in namespaces:
            try:
                cronjobs = self.batch_v1.list_namespaced_cron_job(namespace)
                
                for cron in cronjobs.items:
                    cron_name = cron.metadata.name
                    was_suspended = cron.spec.suspend or False
                    
                    key = f"{namespace}/{cron_name}"
                    state["cronjobs"][key] = was_suspended
                    
                    # Suspend if not already
                    if not was_suspended:
                        cron.spec.suspend = True
                        self.batch_v1.patch_namespaced_cron_job(
                            name=cron_name,
                            namespace=namespace,
                            body=cron
                        )
                        logger.debug(f"Suspended cronjob {key}")
                        
            except ApiException as e:
                error_msg = f"Error suspending cronjobs in {namespace}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    def _wake_deployments(self, deployment_state: Dict, errors: List):
        """Restore deployments to original replica counts"""
        for key, replicas in deployment_state.items():
            namespace, name = key.split("/")
            
            try:
                deployment = self.apps_v1.read_namespaced_deployment(name, namespace)
                deployment.spec.replicas = replicas
                
                self.apps_v1.patch_namespaced_deployment(
                    name=name,
                    namespace=namespace,
                    body=deployment
                )
                logger.debug(f"Restored deployment {key} to {replicas} replicas")
                time.sleep(self.config.OPERATION_DELAY_SECONDS)
                
            except ApiException as e:
                error_msg = f"Error restoring deployment {key}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    def _wake_statefulsets(self, sts_state: Dict, errors: List):
        """Restore statefulsets to original replica counts"""
        for key, replicas in sts_state.items():
            namespace, name = key.split("/")
            
            try:
                sts = self.apps_v1.read_namespaced_stateful_set(name, namespace)
                sts.spec.replicas = replicas
                
                self.apps_v1.patch_namespaced_stateful_set(
                    name=name,
                    namespace=namespace,
                    body=sts
                )
                logger.debug(f"Restored statefulset {key} to {replicas} replicas")
                time.sleep(self.config.OPERATION_DELAY_SECONDS)
                
            except ApiException as e:
                error_msg = f"Error restoring statefulset {key}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    def _wake_cronjobs(self, cron_state: Dict, errors: List):
        """Restore cronjobs to original suspended state"""
        for key, was_suspended in cron_state.items():
            namespace, name = key.split("/")
            
            try:
                cron = self.batch_v1.read_namespaced_cron_job(name, namespace)
                cron.spec.suspend = was_suspended
                
                self.batch_v1.patch_namespaced_cron_job(
                    name=name,
                    namespace=namespace,
                    body=cron
                )
                logger.debug(f"Restored cronjob {key} suspend={was_suspended}")
                
            except ApiException as e:
                error_msg = f"Error restoring cronjob {key}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    def _wait_for_pod_termination(self, namespaces: List[str]):
        """Wait for pods to terminate after scaling down"""
        logger.info("Waiting for pods to terminate...")
        start_time = time.time()
        
        while True:
            if time.time() - start_time > self.config.POD_TERMINATION_TIMEOUT:
                logger.warning("Pod termination timeout reached")
                break
            
            total_pods = 0
            for namespace in namespaces:
                try:
                    pods = self.core_v1.list_namespaced_pod(namespace)
                    # Count non-completed pods
                    active_pods = [p for p in pods.items if p.status.phase not in ["Succeeded", "Failed"]]
                    total_pods += len(active_pods)
                except:
                    pass
            
            if total_pods == 0:
                logger.info("All pods terminated successfully")
                break
            
            logger.debug(f"Waiting for {total_pods} pods to terminate...")
            time.sleep(5)
