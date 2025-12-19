"""
[ARCH-001] Kubernetes Event Stream Watcher

Real-time Kubernetes event monitoring replacing 5-minute polling.
Watches pod events continuously and pushes to Redis queue for processing.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional
import redis
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class K8sEventWatcher:
    """
    Watches Kubernetes events in real-time and pushes to Redis queue

    Monitors:
    - Pod creations
    - Pod deletions
    - Pod status changes
    - Spot interruption notices (via events)
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", namespace: str = "default"):
        """
        Initialize Kubernetes event watcher

        Args:
            redis_url: Redis connection URL
            namespace: Kubernetes namespace to watch (use 'all' for all namespaces)
        """
        self.redis_url = redis_url
        self.namespace = namespace
        self.redis_client = None
        self.k8s_client = None
        self.running = False

        # Event queue names
        self.QUEUE_POD_EVENTS = "k8s:events:pods"
        self.QUEUE_SPOT_INTERRUPTIONS = "k8s:events:spot-interruptions"
        self.QUEUE_OPTIMIZATION_TRIGGERS = "optimization:triggers"

    def connect(self):
        """Establish connections to Kubernetes and Redis"""
        try:
            # Load Kubernetes config (in-cluster or from kubeconfig)
            try:
                config.load_incluster_config()
                logger.info("✓ Loaded in-cluster Kubernetes config")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("✓ Loaded kubeconfig from local")

            # Initialize Kubernetes client
            self.k8s_client = client.CoreV1Api()

            # Initialize Redis connection
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )

            # Test Redis connection
            self.redis_client.ping()
            logger.info(f"✓ Connected to Redis at {self.redis_url}")

            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    def watch_pod_events(self):
        """
        Watch pod events in real-time

        Events monitored:
        - ADDED: New pod created
        - MODIFIED: Pod status changed
        - DELETED: Pod removed
        """
        logger.info(f"🔍 Starting pod event watcher for namespace: {self.namespace}")

        w = watch.Watch()

        try:
            # Watch pods in namespace (or all namespaces)
            if self.namespace == "all":
                stream = w.stream(self.k8s_client.list_pod_for_all_namespaces)
            else:
                stream = w.stream(self.k8s_client.list_namespaced_pod, self.namespace)

            for event in stream:
                if not self.running:
                    break

                event_type = event['type']  # ADDED, MODIFIED, DELETED
                pod = event['object']

                # Extract pod information
                pod_event = {
                    'event_type': event_type,
                    'timestamp': datetime.utcnow().isoformat(),
                    'pod_name': pod.metadata.name,
                    'namespace': pod.metadata.namespace,
                    'node_name': pod.spec.node_name,
                    'phase': pod.status.phase,
                    'labels': dict(pod.metadata.labels or {}),
                    'annotations': dict(pod.metadata.annotations or {}),
                }

                # Check for spot interruption notice
                if self._is_spot_interruption_event(pod):
                    pod_event['spot_interruption'] = True
                    pod_event['interruption_time'] = pod.metadata.annotations.get('spot-interruption-time')

                    # Push to spot interruption queue (high priority)
                    self.redis_client.rpush(
                        self.QUEUE_SPOT_INTERRUPTIONS,
                        json.dumps(pod_event)
                    )
                    logger.warning(f"⚠️ SPOT INTERRUPTION: {pod_event['pod_name']} on {pod_event['node_name']}")

                # Push to general pod events queue
                self.redis_client.rpush(
                    self.QUEUE_POD_EVENTS,
                    json.dumps(pod_event)
                )

                # Trigger optimization if needed
                if self._should_trigger_optimization(event_type, pod):
                    self._trigger_optimization(pod_event)

                logger.info(f"📨 Event: {event_type} - {pod_event['pod_name']} ({pod_event['phase']})")

        except ApiException as e:
            logger.error(f"Kubernetes API error: {e}")
        except Exception as e:
            logger.error(f"Event watcher error: {e}")
        finally:
            w.stop()

    def watch_node_events(self):
        """
        Watch node events for spot instance interruptions

        Monitors:
        - Node status changes
        - Spot interruption warnings
        - Node taints (NoSchedule, NoExecute)
        """
        logger.info("🔍 Starting node event watcher")

        w = watch.Watch()

        try:
            stream = w.stream(self.k8s_client.list_node)

            for event in stream:
                if not self.running:
                    break

                event_type = event['type']
                node = event['object']

                node_event = {
                    'event_type': event_type,
                    'timestamp': datetime.utcnow().isoformat(),
                    'node_name': node.metadata.name,
                    'labels': dict(node.metadata.labels or {}),
                    'taints': [
                        {
                            'key': taint.key,
                            'effect': taint.effect,
                            'value': taint.value
                        }
                        for taint in (node.spec.taints or [])
                    ],
                    'conditions': [
                        {
                            'type': cond.type,
                            'status': cond.status,
                            'reason': cond.reason
                        }
                        for cond in (node.status.conditions or [])
                    ]
                }

                # Check for spot interruption taints
                if self._is_node_spot_interruption(node):
                    node_event['spot_interruption'] = True

                    # Push to spot interruption queue
                    self.redis_client.rpush(
                        self.QUEUE_SPOT_INTERRUPTIONS,
                        json.dumps(node_event)
                    )
                    logger.warning(f"⚠️ NODE INTERRUPTION: {node_event['node_name']}")

                logger.info(f"📨 Node Event: {event_type} - {node_event['node_name']}")

        except ApiException as e:
            logger.error(f"Kubernetes API error: {e}")
        except Exception as e:
            logger.error(f"Node event watcher error: {e}")
        finally:
            w.stop()

    def _is_spot_interruption_event(self, pod) -> bool:
        """Check if pod event indicates spot interruption"""
        annotations = pod.metadata.annotations or {}

        # Check for spot interruption annotations
        if 'spot-interruption-time' in annotations:
            return True

        # Check pod conditions for spot termination
        for condition in (pod.status.conditions or []):
            if condition.reason in ['SpotInterruption', 'TerminationNotice']:
                return True

        return False

    def _is_node_spot_interruption(self, node) -> bool:
        """Check if node has spot interruption taint"""
        taints = node.spec.taints or []

        for taint in taints:
            if taint.key in ['node.kubernetes.io/spot-interruption', 'cloud.google.com/impending-node-termination']:
                return True

        return False

    def _should_trigger_optimization(self, event_type: str, pod) -> bool:
        """Determine if event should trigger optimization cycle"""
        # Trigger on new pods or spot interruptions
        if event_type == 'ADDED':
            return True

        # Trigger on pod failures
        if pod.status.phase in ['Failed', 'Unknown']:
            return True

        return False

    def _trigger_optimization(self, pod_event: Dict):
        """Push optimization trigger to queue"""
        trigger = {
            'trigger_type': 'pod_event',
            'timestamp': datetime.utcnow().isoformat(),
            'pod_name': pod_event['pod_name'],
            'namespace': pod_event['namespace'],
            'node_name': pod_event['node_name'],
            'event_type': pod_event['event_type']
        }

        self.redis_client.rpush(
            self.QUEUE_OPTIMIZATION_TRIGGERS,
            json.dumps(trigger)
        )

        logger.info(f"🔄 Optimization triggered for {pod_event['pod_name']}")

    async def start(self):
        """Start watching events"""
        if not self.connect():
            logger.error("Failed to connect, cannot start watcher")
            return

        self.running = True
        logger.info("🚀 K8s Event Watcher started")

        # Run both watchers concurrently
        await asyncio.gather(
            asyncio.to_thread(self.watch_pod_events),
            asyncio.to_thread(self.watch_node_events)
        )

    def stop(self):
        """Stop watching events"""
        self.running = False
        logger.info("🛑 K8s Event Watcher stopped")


# Standalone runner
if __name__ == "__main__":
    import os

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    namespace = os.getenv('K8S_NAMESPACE', 'default')

    watcher = K8sEventWatcher(redis_url=redis_url, namespace=namespace)

    try:
        asyncio.run(watcher.start())
    except KeyboardInterrupt:
        watcher.stop()
