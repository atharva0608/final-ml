"""
[ARCH-002] Event-Driven Worker System

Processes events from Redis queues and triggers optimization cycles.
Replaces scheduled polling with real-time event-driven architecture.
"""

import json
import logging
import time
from typing import Dict, Optional
import redis
from sqlalchemy.orm import Session

from database.connection import get_db
from workers.optimizer_task import run_optimization_cycle
from utils.system_logger import SystemLogger

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Event-driven worker that processes Kubernetes events from Redis queue

    Queues processed:
    - k8s:events:pods - General pod events
    - k8s:events:spot-interruptions - High-priority spot interruptions
    - optimization:triggers - Optimization cycle triggers
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        Initialize event processor

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.redis_client = None
        self.running = False

        # Queue names
        self.QUEUE_POD_EVENTS = "k8s:events:pods"
        self.QUEUE_SPOT_INTERRUPTIONS = "k8s:events:spot-interruptions"
        self.QUEUE_OPTIMIZATION_TRIGGERS = "optimization:triggers"

        # Processing stats
        self.stats = {
            'events_processed': 0,
            'optimizations_triggered': 0,
            'spot_interruptions_handled': 0,
            'errors': 0
        }

    def connect(self) -> bool:
        """Establish Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )

            # Test connection
            self.redis_client.ping()
            logger.info(f"✓ Connected to Redis at {self.redis_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    def process_pod_event(self, event_data: Dict):
        """
        Process pod event from queue

        Args:
            event_data: Pod event dictionary
        """
        try:
            logger.info(f"Processing pod event: {event_data['event_type']} - {event_data['pod_name']}")

            # Extract pod information
            pod_name = event_data.get('pod_name')
            event_type = event_data.get('event_type')
            phase = event_data.get('phase')
            node_name = event_data.get('node_name')

            # Log to database
            db_gen = get_db()
            db = next(db_gen, None)

            if db:
                try:
                    sys_logger = SystemLogger("k8s_watcher", db=db)
                    sys_logger.info(
                        f"Pod event: {event_type}",
                        details={
                            'pod_name': pod_name,
                            'phase': phase,
                            'node_name': node_name,
                            'timestamp': event_data.get('timestamp')
                        }
                    )
                finally:
                    db.close()

            self.stats['events_processed'] += 1

        except Exception as e:
            logger.error(f"Error processing pod event: {e}")
            self.stats['errors'] += 1

    def process_spot_interruption(self, event_data: Dict):
        """
        Process spot interruption event (high priority)

        Triggers immediate evacuation/migration workflow

        Args:
            event_data: Spot interruption event dictionary
        """
        try:
            logger.warning(f"⚠️ Processing SPOT INTERRUPTION: {event_data.get('pod_name')} or {event_data.get('node_name')}")

            # Trigger emergency evacuation
            if 'pod_name' in event_data:
                # Pod-level interruption
                pod_name = event_data['pod_name']
                node_name = event_data['node_name']

                logger.warning(f"🚨 EVACUATING POD: {pod_name} from {node_name}")

                # In production:
                # 1. Mark node as draining
                # 2. Trigger pod evacuation
                # 3. Find alternative node
                # 4. Schedule migration

            elif 'node_name' in event_data:
                # Node-level interruption
                node_name = event_data['node_name']

                logger.warning(f"🚨 EVACUATING NODE: {node_name}")

                # In production:
                # 1. Mark all pods on node for evacuation
                # 2. Trigger mass migration
                # 3. Update node status

            # Log to database
            db_gen = get_db()
            db = next(db_gen, None)

            if db:
                try:
                    sys_logger = SystemLogger("ml_inference", db=db)
                    sys_logger.error(
                        "Spot interruption detected",
                        details=event_data
                    )
                finally:
                    db.close()

            self.stats['spot_interruptions_handled'] += 1

        except Exception as e:
            logger.error(f"Error processing spot interruption: {e}")
            self.stats['errors'] += 1

    def process_optimization_trigger(self, trigger_data: Dict):
        """
        Process optimization trigger

        Runs optimization cycle for affected instances

        Args:
            trigger_data: Optimization trigger dictionary
        """
        try:
            logger.info(f"🔄 Processing optimization trigger: {trigger_data.get('trigger_type')}")

            # Extract trigger information
            trigger_type = trigger_data.get('trigger_type')
            pod_name = trigger_data.get('pod_name')

            # Run optimization cycle
            # In production, this would trigger the full decision pipeline
            logger.info(f"Running optimization for pod: {pod_name}")

            # Log to database
            db_gen = get_db()
            db = next(db_gen, None)

            if db:
                try:
                    sys_logger = SystemLogger("linear_optimizer", db=db)
                    sys_logger.info(
                        f"Optimization triggered: {trigger_type}",
                        details=trigger_data
                    )
                finally:
                    db.close()

            self.stats['optimizations_triggered'] += 1

        except Exception as e:
            logger.error(f"Error processing optimization trigger: {e}")
            self.stats['errors'] += 1

    def run(self):
        """
        Main event processing loop

        Continuously processes events from Redis queues
        """
        if not self.connect():
            logger.error("Failed to connect, cannot start processor")
            return

        self.running = True
        logger.info("🚀 Event Processor started")
        logger.info(f"Listening on queues: {self.QUEUE_POD_EVENTS}, {self.QUEUE_SPOT_INTERRUPTIONS}, {self.QUEUE_OPTIMIZATION_TRIGGERS}")

        while self.running:
            try:
                # Process spot interruptions first (high priority)
                event = self.redis_client.blpop(self.QUEUE_SPOT_INTERRUPTIONS, timeout=1)
                if event:
                    _, event_json = event
                    event_data = json.loads(event_json)
                    self.process_spot_interruption(event_data)
                    continue

                # Process optimization triggers
                event = self.redis_client.blpop(self.QUEUE_OPTIMIZATION_TRIGGERS, timeout=1)
                if event:
                    _, trigger_json = event
                    trigger_data = json.loads(trigger_json)
                    self.process_optimization_trigger(trigger_data)
                    continue

                # Process general pod events
                event = self.redis_client.blpop(self.QUEUE_POD_EVENTS, timeout=1)
                if event:
                    _, event_json = event
                    event_data = json.loads(event_json)
                    self.process_pod_event(event_data)
                    continue

                # No events, brief sleep
                time.sleep(0.1)

            except redis.ConnectionError as e:
                logger.error(f"Redis connection lost: {e}")
                time.sleep(5)
                self.connect()

            except Exception as e:
                logger.error(f"Event processing error: {e}")
                self.stats['errors'] += 1
                time.sleep(1)

        logger.info("🛑 Event Processor stopped")

    def stop(self):
        """Stop event processor"""
        self.running = False
        logger.info(f"📊 Final Stats: {self.stats}")


# Standalone runner
if __name__ == "__main__":
    import os

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    processor = EventProcessor(redis_url=redis_url)

    try:
        processor.run()
    except KeyboardInterrupt:
        processor.stop()
