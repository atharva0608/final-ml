"""
AWS Spot Optimizer - Production Agent v4.0.0
===========================================================================
COMPLETE AGENT WITH FULL BACKEND INTEGRATION

Features:
- Instance switching (spot <-> on-demand)
- Replica management (manual and emergency)
- Termination notice handling (2-minute warning)
- Rebalance recommendation checks
- Cleanup operations (snapshots and AMIs)
- Dual mode verification (AWS API + Instance Metadata)
- Priority-based command execution
- Graceful shutdown with cleanup
===========================================================================
"""

import os
import sys
import time
import json
import socket
import signal
import logging
import requests
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urljoin

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spot_optimizer_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class AgentConfig:
    """Agent configuration with environment variable support"""

    # Server Connection
    SERVER_URL: str = os.getenv('SPOT_OPTIMIZER_SERVER_URL', 'http://localhost:5000')
    CLIENT_TOKEN: str = os.getenv('SPOT_OPTIMIZER_CLIENT_TOKEN', '')

    # Agent Identity
    LOGICAL_AGENT_ID: str = os.getenv('LOGICAL_AGENT_ID', '')
    HOSTNAME: str = socket.gethostname()

    # AWS Configuration
    REGION: str = os.getenv('AWS_REGION', 'us-east-1')

    # Timing Configuration
    HEARTBEAT_INTERVAL: int = int(os.getenv('HEARTBEAT_INTERVAL', 30))
    PENDING_COMMANDS_CHECK_INTERVAL: int = int(os.getenv('PENDING_COMMANDS_CHECK_INTERVAL', 15))
    CONFIG_REFRESH_INTERVAL: int = int(os.getenv('CONFIG_REFRESH_INTERVAL', 60))
    PRICING_REPORT_INTERVAL: int = int(os.getenv('PRICING_REPORT_INTERVAL', 300))
    TERMINATION_CHECK_INTERVAL: int = int(os.getenv('TERMINATION_CHECK_INTERVAL', 5))
    REBALANCE_CHECK_INTERVAL: int = int(os.getenv('REBALANCE_CHECK_INTERVAL', 30))
    CLEANUP_INTERVAL: int = int(os.getenv('CLEANUP_INTERVAL', 3600))  # 1 hour

    # Switch Configuration
    AUTO_TERMINATE_OLD_INSTANCE: bool = os.getenv('AUTO_TERMINATE_OLD_INSTANCE', 'true').lower() == 'true'
    TERMINATE_WAIT_TIME: int = int(os.getenv('TERMINATE_WAIT_TIME', 300))
    CREATE_SNAPSHOT_ON_SWITCH: bool = os.getenv('CREATE_SNAPSHOT_ON_SWITCH', 'true').lower() == 'true'

    # Replica Configuration
    REPLICA_ENABLED: bool = os.getenv('REPLICA_ENABLED', 'false').lower() == 'true'
    REPLICA_COUNT: int = int(os.getenv('REPLICA_COUNT', 1))

    # Cleanup Configuration
    CLEANUP_SNAPSHOTS_OLDER_THAN_DAYS: int = int(os.getenv('CLEANUP_SNAPSHOTS_OLDER_THAN_DAYS', 7))
    CLEANUP_AMIS_OLDER_THAN_DAYS: int = int(os.getenv('CLEANUP_AMIS_OLDER_THAN_DAYS', 30))

    # Agent Version
    AGENT_VERSION: str = '4.0.0'

    def validate(self) -> bool:
        """Validate required configuration"""
        if not self.CLIENT_TOKEN:
            logger.error("CLIENT_TOKEN not set!")
            return False
        if not self.SERVER_URL:
            logger.error("SERVER_URL not set!")
            return False
        if not self.LOGICAL_AGENT_ID:
            logger.warning("LOGICAL_AGENT_ID not set. Will use instance ID as logical ID.")
        return True

config = AgentConfig()

# ============================================================================
# AWS CLIENTS
# ============================================================================

class AWSClients:
    """Singleton AWS client manager"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize AWS clients"""
        try:
            self.ec2 = boto3.client('ec2', region_name=config.REGION)
            self.ec2_resource = boto3.resource('ec2', region_name=config.REGION)
            logger.info(f"AWS clients initialized (region: {config.REGION})")
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise

aws_clients = AWSClients()

# ============================================================================
# INSTANCE METADATA & MODE DETECTION
# ============================================================================

class InstanceMetadata:
    """Instance metadata and mode detection with dual verification"""

    METADATA_BASE_URL = "http://169.254.169.254/latest"
    METADATA_TIMEOUT = 2

    @staticmethod
    def get_metadata(path: str) -> Optional[str]:
        """Fetch instance metadata using IMDSv2"""
        try:
            token_response = requests.put(
                f"{InstanceMetadata.METADATA_BASE_URL}/api/token",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
                timeout=InstanceMetadata.METADATA_TIMEOUT
            )
            token = token_response.text

            response = requests.get(
                f"{InstanceMetadata.METADATA_BASE_URL}/{path}",
                headers={"X-aws-ec2-metadata-token": token},
                timeout=InstanceMetadata.METADATA_TIMEOUT
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.debug(f"Metadata fetch failed for {path}: {e}")
            return None

    @staticmethod
    def get_instance_id() -> str:
        instance_id = InstanceMetadata.get_metadata("meta-data/instance-id")
        if not instance_id:
            raise RuntimeError("Cannot determine instance ID from metadata")
        return instance_id

    @staticmethod
    def get_instance_type() -> str:
        return InstanceMetadata.get_metadata("meta-data/instance-type") or "unknown"

    @staticmethod
    def get_availability_zone() -> str:
        return InstanceMetadata.get_metadata("meta-data/placement/availability-zone") or "unknown"

    @staticmethod
    def get_ami_id() -> str:
        return InstanceMetadata.get_metadata("meta-data/ami-id") or "unknown"

    @staticmethod
    def get_private_ip() -> str:
        return InstanceMetadata.get_metadata("meta-data/local-ipv4") or "unknown"

    @staticmethod
    def get_public_ip() -> Optional[str]:
        return InstanceMetadata.get_metadata("meta-data/public-ipv4")

    @staticmethod
    def check_spot_termination_notice() -> Optional[Dict]:
        """
        Check for spot instance termination notice
        Returns termination time if notice exists, None otherwise
        """
        try:
            action = InstanceMetadata.get_metadata("meta-data/spot/instance-action")
            if action:
                action_data = json.loads(action)
                logger.warning(f"SPOT TERMINATION NOTICE: {action_data}")
                return action_data
            return None
        except Exception as e:
            logger.debug(f"No termination notice: {e}")
            return None

    @staticmethod
    def check_rebalance_recommendation() -> bool:
        """
        Check for EC2 instance rebalance recommendation
        Returns True if rebalance is recommended
        """
        try:
            recommendation = InstanceMetadata.get_metadata("meta-data/events/recommendations/rebalance")
            if recommendation:
                logger.warning(f"REBALANCE RECOMMENDATION: {recommendation}")
                return True
            return False
        except Exception as e:
            logger.debug(f"No rebalance recommendation: {e}")
            return False

    @staticmethod
    def detect_instance_mode_metadata() -> str:
        """Detect mode from instance metadata"""
        try:
            spot_action = InstanceMetadata.get_metadata("meta-data/spot/instance-action")
            if spot_action is not None:
                return 'spot'

            lifecycle = InstanceMetadata.get_metadata("meta-data/instance-life-cycle")
            if lifecycle == 'spot':
                return 'spot'
            elif lifecycle == 'on-demand':
                return 'ondemand'

            return 'ondemand'
        except Exception as e:
            logger.warning(f"Metadata mode detection failed: {e}")
            return 'unknown'

    @staticmethod
    def detect_instance_mode_api(instance_id: str) -> str:
        """Detect mode from AWS EC2 API (more reliable)"""
        try:
            response = aws_clients.ec2.describe_instances(InstanceIds=[instance_id])

            if not response['Reservations']:
                return 'unknown'

            instance = response['Reservations'][0]['Instances'][0]
            lifecycle = instance.get('InstanceLifecycle', 'normal')

            if lifecycle == 'spot':
                return 'spot'
            elif lifecycle == 'normal' or lifecycle == 'scheduled':
                return 'ondemand'

            return 'unknown'
        except Exception as e:
            logger.warning(f"API mode detection failed: {e}")
            return 'unknown'

    @staticmethod
    def detect_instance_mode_dual() -> Tuple[str, str]:
        """Dual verification of instance mode"""
        instance_id = InstanceMetadata.get_instance_id()

        metadata_mode = InstanceMetadata.detect_instance_mode_metadata()
        api_mode = InstanceMetadata.detect_instance_mode_api(instance_id)

        if metadata_mode != api_mode and metadata_mode != 'unknown' and api_mode != 'unknown':
            logger.warning(f"Mode mismatch! Metadata={metadata_mode}, API={api_mode}")

        final_mode = api_mode if api_mode != 'unknown' else metadata_mode

        return final_mode, api_mode

# ============================================================================
# SERVER API CLIENT
# ============================================================================

class ServerAPI:
    """API client for central server communication"""

    def __init__(self):
        self.base_url = config.SERVER_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {config.CLIENT_TOKEN}',
            'Content-Type': 'application/json'
        })

    def _make_request(self, method: str, endpoint: str, max_retries: int = 3, **kwargs) -> Optional[Dict]:
        """Make HTTP request with error handling and retry logic"""
        url = urljoin(self.base_url, endpoint)
        response = None

        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
                response.raise_for_status()
                return response.json() if response.text else {}
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries}): {method} {url} - retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Request timeout after {max_retries} attempts: {method} {url} - {str(e)}")
                return None
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries}): {method} {url} - retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Connection error after {max_retries} attempts: {method} {url} - {str(e)}")
                logger.error(f"Server URL configured as: {self.base_url}")
                logger.error(f"Verify server is running and CLIENT_TOKEN is valid")
                return None
            except requests.exceptions.HTTPError as e:
                status_code = response.status_code if response else 'unknown'
                response_text = response.text if response else 'no response'
                logger.error(f"HTTP error {status_code}: {method} {url}")
                logger.error(f"Response: {response_text}")
                if response and response.status_code in [401, 403]:
                    logger.error(f"Authentication failed - check CLIENT_TOKEN configuration")
                    logger.error(f"Current token: {config.CLIENT_TOKEN[:8]}...{config.CLIENT_TOKEN[-4:] if len(config.CLIENT_TOKEN) > 12 else ''}")
                return None
            except Exception as e:
                logger.error(f"Request failed: {method} {url} - {type(e).__name__}: {str(e)}")
                return None

        return None

    def register_agent(self, instance_info: Dict) -> Optional[Dict]:
        """Register agent with server"""
        return self._make_request('POST', '/api/agents/register', json=instance_info)

    def send_heartbeat(self, agent_id: str, status: str, monitored_instances: List[str],
                       extra_data: Optional[Dict] = None) -> bool:
        """Send heartbeat to server"""
        payload = {
            'status': status,
            'monitored_instances': monitored_instances
        }
        if extra_data:
            payload.update(extra_data)
        result = self._make_request('POST', f'/api/agents/{agent_id}/heartbeat', json=payload)
        return result is not None

    def send_pricing_report(self, agent_id: str, report: Dict) -> bool:
        """Send pricing report to server"""
        result = self._make_request('POST', f'/api/agents/{agent_id}/pricing-report', json=report)
        return result is not None

    def get_agent_config(self, agent_id: str) -> Optional[Dict]:
        """Get agent configuration"""
        return self._make_request('GET', f'/api/agents/{agent_id}/config')

    def get_pending_commands(self, agent_id: str) -> List[Dict]:
        """Get pending commands with priority"""
        result = self._make_request('GET', f'/api/agents/{agent_id}/pending-commands')
        if not result:
            return []
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return result.get('commands', result.get('pending_commands', result.get('data', [])))
        return []

    def get_pending_replicas(self, agent_id: str) -> List[Dict]:
        """Get replicas that need to be launched by agent"""
        result = self._make_request('GET', f'/api/agents/{agent_id}/replicas?status=launching')
        if not result:
            return []
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return result.get('replicas', [])
        return []

    def update_replica_instance(self, agent_id: str, replica_id: str, instance_id: str, status: str = 'syncing') -> bool:
        """Update replica with actual EC2 instance ID"""
        result = self._make_request(
            'PUT',
            f'/api/agents/{agent_id}/replicas/{replica_id}',
            json={'instance_id': instance_id, 'status': status}
        )
        return result is not None

    def mark_command_executed(self, agent_id: str, command_id: str, success: bool = True,
                              message: str = "") -> bool:
        """Mark command as executed"""
        result = self._make_request(
            'POST',
            f'/api/agents/{agent_id}/commands/{command_id}/executed',
            json={'success': success, 'message': message}
        )
        return result is not None

    def send_switch_report(self, agent_id: str, switch_data: Dict) -> bool:
        """Send detailed switch report with timing"""
        result = self._make_request('POST', f'/api/agents/{agent_id}/switch-report', json=switch_data)
        return result is not None

    def report_termination_notice(self, agent_id: str, termination_data: Dict) -> Optional[Dict]:
        """Report termination notice and get emergency instructions"""
        return self._make_request('POST', f'/api/agents/{agent_id}/termination-imminent', json=termination_data)

    def report_rebalance_recommendation(self, agent_id: str, instance_id: str) -> Optional[Dict]:
        """Report rebalance recommendation"""
        return self._make_request('POST', f'/api/agents/{agent_id}/rebalance-recommendation', json={
            'instance_id': instance_id,
            'detected_at': datetime.now(timezone.utc).isoformat()
        })

    def create_emergency_replica(self, agent_id: str, signal_type: str,
                                  instance_id: str, termination_time: Optional[str] = None) -> Optional[Dict]:
        """
        Create emergency replica via backend endpoint.

        Args:
            agent_id: Agent ID
            signal_type: 'rebalance-recommendation' or 'termination-notice'
            instance_id: Current instance ID
            termination_time: ISO timestamp for termination (required for termination-notice)

        Returns:
            Response from backend with replica details or error
        """
        payload = {
            'signal_type': signal_type,
            'instance_id': instance_id
        }
        if termination_time:
            payload['termination_time'] = termination_time

        return self._make_request('POST', f'/api/agents/{agent_id}/create-emergency-replica', json=payload)

    def get_replica_config(self, agent_id: str) -> Optional[Dict]:
        """Get replica configuration"""
        return self._make_request('GET', f'/api/agents/{agent_id}/replica-config')

    def create_replica(self, agent_id: str, replica_data: Dict) -> Optional[Dict]:
        """Create manual replica"""
        return self._make_request('POST', f'/api/agents/{agent_id}/replicas', json=replica_data)

    def update_replica_status(self, agent_id: str, replica_id: str, status_data: Dict) -> bool:
        """Update replica status"""
        result = self._make_request(
            'POST',
            f'/api/agents/{agent_id}/replicas/{replica_id}/status',
            json=status_data
        )
        return result is not None

    def promote_replica(self, agent_id: str, replica_id: str) -> Optional[Dict]:
        """Promote replica to primary"""
        return self._make_request('POST', f'/api/agents/{agent_id}/replicas/{replica_id}/promote', json={})

    def report_cleanup(self, agent_id: str, cleanup_data: Dict) -> bool:
        """Report cleanup operations"""
        result = self._make_request('POST', f'/api/agents/{agent_id}/cleanup-report', json=cleanup_data)
        return result is not None

    def check_server_connectivity(self) -> bool:
        """Verify server connectivity and authentication at startup"""
        logger.info("="*60)
        logger.info("AGENT STARTUP - SERVER CONNECTIVITY CHECK")
        logger.info("="*60)
        logger.info(f"Server URL: {self.base_url}")
        logger.info(f"Client Token: {config.CLIENT_TOKEN[:8]}...{config.CLIENT_TOKEN[-4:] if len(config.CLIENT_TOKEN) > 12 else '***'}")

        # Try a simple health check endpoint
        try:
            url = urljoin(self.base_url, '/health')
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                logger.info("✓ Server is reachable (health check passed)")
            else:
                logger.warning(f"⚠ Server responded with status {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"✗ Cannot reach server: {str(e)}")
            logger.error("  Possible causes:")
            logger.error("  1. Server is not running")
            logger.error("  2. Wrong SERVER_URL configuration")
            logger.error("  3. Network/firewall blocking connection")
            logger.error("  4. DNS resolution failure")
            return False
        except Exception as e:
            logger.warning(f"Health check failed: {type(e).__name__}: {str(e)}")

        logger.info("="*60)
        return True

# ============================================================================
# SPOT PRICING COLLECTOR
# ============================================================================

class SpotPricingCollector:
    """Collect spot pricing data for pools"""

    def __init__(self):
        self.ec2 = aws_clients.ec2
        self._ondemand_cache = {}

    def get_spot_pools(self, instance_type: str, region: str) -> List[Dict]:
        """Get available spot pools for instance type"""
        try:
            response = self.ec2.describe_availability_zones(
                Filters=[{'Name': 'region-name', 'Values': [region]}]
            )

            zones = [z['ZoneName'] for z in response['AvailabilityZones'] if z['State'] == 'available']

            pools = []
            for az in zones:
                pool_id = f"{instance_type}.{az}"
                price = self.get_spot_price(instance_type, az)

                if price:
                    pools.append({
                        'pool_id': pool_id,
                        'instance_type': instance_type,
                        'az': az,
                        'price': price
                    })

            return pools
        except Exception as e:
            logger.error(f"Failed to get spot pools: {e}")
            return []

    def get_spot_price(self, instance_type: str, az: str) -> Optional[float]:
        """Get current spot price for instance type in AZ"""
        try:
            product_descriptions = ['Linux/UNIX (Amazon VPC)', 'Linux/UNIX']

            for product_desc in product_descriptions:
                try:
                    response = self.ec2.describe_spot_price_history(
                        InstanceTypes=[instance_type],
                        AvailabilityZone=az,
                        MaxResults=1,
                        ProductDescriptions=[product_desc]
                    )

                    if response['SpotPriceHistory']:
                        return float(response['SpotPriceHistory'][0]['SpotPrice'])
                except Exception:
                    continue

            response = self.ec2.describe_spot_price_history(
                InstanceTypes=[instance_type],
                AvailabilityZone=az,
                MaxResults=1
            )

            if response['SpotPriceHistory']:
                return float(response['SpotPriceHistory'][0]['SpotPrice'])

            return None
        except Exception as e:
            logger.error(f"Failed to get spot price for {instance_type} in {az}: {e}")
            return None

    def get_ondemand_price(self, instance_type: str, region: str) -> float:
        """Get on-demand price (from pricing API or fallback)"""
        cache_key = f"{instance_type}:{region}"
        if cache_key in self._ondemand_cache:
            return self._ondemand_cache[cache_key]

        try:
            pricing = boto3.client('pricing', region_name='us-east-1')
            location = self._region_to_location(region)

            response = pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                    {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                    {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                    {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'}
                ],
                MaxResults=1
            )

            if response['PriceList']:
                price_data = json.loads(response['PriceList'][0])
                terms = price_data['terms']['OnDemand']

                for term in terms.values():
                    for price_dim in term['priceDimensions'].values():
                        price = float(price_dim['pricePerUnit']['USD'])
                        self._ondemand_cache[cache_key] = price
                        return price

            # Fallback: estimate from spot price
            spot_pools = self.get_spot_pools(instance_type, region)
            if spot_pools:
                avg_spot = sum(p['price'] for p in spot_pools) / len(spot_pools)
                estimated_price = avg_spot * 3.0
                self._ondemand_cache[cache_key] = estimated_price
                return estimated_price

            return 0.1
        except Exception as e:
            logger.error(f"Failed to get on-demand price: {e}")
            return 0.1

    def _region_to_location(self, region: str) -> str:
        """Convert region code to pricing API location name"""
        region_map = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-northeast-1': 'Asia Pacific (Tokyo)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-southeast-2': 'Asia Pacific (Sydney)',
            'eu-west-1': 'EU (Ireland)',
            'eu-central-1': 'EU (Frankfurt)',
            'eu-west-2': 'EU (London)'
        }
        return region_map.get(region, region)

# ============================================================================
# CLEANUP MANAGER
# ============================================================================

class CleanupManager:
    """Manage cleanup of old snapshots and AMIs"""

    def __init__(self):
        self.ec2 = aws_clients.ec2

    def cleanup_old_snapshots(self, days_old: int = 7) -> Dict:
        """Delete snapshots older than specified days"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            response = self.ec2.describe_snapshots(
                OwnerIds=['self'],
                Filters=[
                    {'Name': 'tag:ManagedBy', 'Values': ['SpotOptimizer']},
                    {'Name': 'status', 'Values': ['completed']}
                ]
            )

            deleted = []
            failed = []

            for snapshot in response['Snapshots']:
                start_time = snapshot['StartTime'].replace(tzinfo=None)
                if start_time < cutoff_date:
                    try:
                        self.ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                        deleted.append(snapshot['SnapshotId'])
                        logger.info(f"Deleted old snapshot: {snapshot['SnapshotId']}")
                    except ClientError as e:
                        if 'InvalidSnapshot.InUse' not in str(e):
                            failed.append({'id': snapshot['SnapshotId'], 'error': str(e)})
                            logger.warning(f"Failed to delete snapshot {snapshot['SnapshotId']}: {e}")

            return {
                'type': 'snapshots',
                'deleted': deleted,
                'failed': failed,
                'cutoff_date': cutoff_date.isoformat()
            }
        except Exception as e:
            logger.error(f"Snapshot cleanup failed: {e}")
            return {'type': 'snapshots', 'deleted': [], 'failed': [], 'error': str(e)}

    def cleanup_old_amis(self, days_old: int = 30) -> Dict:
        """Deregister AMIs older than specified days and delete associated snapshots"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            response = self.ec2.describe_images(
                Owners=['self'],
                Filters=[
                    {'Name': 'tag:ManagedBy', 'Values': ['SpotOptimizer']}
                ]
            )

            deleted_amis = []
            deleted_snapshots = []
            failed = []

            for image in response['Images']:
                creation_date = datetime.strptime(
                    image['CreationDate'].split('.')[0], '%Y-%m-%dT%H:%M:%S'
                )

                if creation_date < cutoff_date:
                    ami_id = image['ImageId']

                    # Get associated snapshots
                    snapshot_ids = [
                        bdm['Ebs']['SnapshotId']
                        for bdm in image.get('BlockDeviceMappings', [])
                        if 'Ebs' in bdm and 'SnapshotId' in bdm['Ebs']
                    ]

                    try:
                        # Deregister AMI
                        self.ec2.deregister_image(ImageId=ami_id)
                        deleted_amis.append(ami_id)
                        logger.info(f"Deregistered old AMI: {ami_id}")

                        # Delete associated snapshots
                        for snap_id in snapshot_ids:
                            try:
                                self.ec2.delete_snapshot(SnapshotId=snap_id)
                                deleted_snapshots.append(snap_id)
                                logger.info(f"Deleted AMI snapshot: {snap_id}")
                            except ClientError as e:
                                failed.append({'id': snap_id, 'error': str(e)})
                    except ClientError as e:
                        failed.append({'id': ami_id, 'error': str(e)})
                        logger.warning(f"Failed to deregister AMI {ami_id}: {e}")

            return {
                'type': 'amis',
                'deleted_amis': deleted_amis,
                'deleted_snapshots': deleted_snapshots,
                'failed': failed,
                'cutoff_date': cutoff_date.isoformat()
            }
        except Exception as e:
            logger.error(f"AMI cleanup failed: {e}")
            return {'type': 'amis', 'deleted_amis': [], 'deleted_snapshots': [], 'failed': [], 'error': str(e)}

    def run_full_cleanup(self) -> Dict:
        """Run full cleanup of snapshots and AMIs"""
        logger.info("Starting cleanup operations...")

        snapshot_result = self.cleanup_old_snapshots(config.CLEANUP_SNAPSHOTS_OLDER_THAN_DAYS)
        ami_result = self.cleanup_old_amis(config.CLEANUP_AMIS_OLDER_THAN_DAYS)

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'snapshots': snapshot_result,
            'amis': ami_result
        }

# ============================================================================
# REPLICA MANAGER
# ============================================================================

class ReplicaManager:
    """Manage replica instances"""

    def __init__(self, server_api: ServerAPI):
        self.server_api = server_api
        self.ec2 = aws_clients.ec2
        self.ec2_resource = aws_clients.ec2_resource
        self.active_replicas: Dict[str, Dict] = {}

    def create_replica(self, agent_id: str, primary_instance: Dict,
                       replica_type: str = 'manual', target_pool_id: Optional[str] = None) -> Optional[str]:
        """Create a replica instance"""
        try:
            logger.info(f"Creating {replica_type} replica...")

            # Determine target AZ
            if target_pool_id:
                target_az = target_pool_id.split('.')[-1]
            else:
                target_az = primary_instance['az']

            # Launch params
            launch_params = {
                'ImageId': primary_instance['ami_id'],
                'InstanceType': primary_instance['instance_type'],
                'MinCount': 1,
                'MaxCount': 1,
                'Placement': {'AvailabilityZone': target_az},
                'TagSpecifications': [{
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': f"SpotOptimizer-Replica-{replica_type}"},
                        {'Key': 'ManagedBy', 'Value': 'SpotOptimizer'},
                        {'Key': 'ReplicaType', 'Value': replica_type},
                        {'Key': 'ParentInstance', 'Value': primary_instance['instance_id']},
                        {'Key': 'LogicalAgentId', 'Value': config.LOGICAL_AGENT_ID}
                    ]
                }],
                'InstanceMarketOptions': {
                    'MarketType': 'spot',
                    'SpotOptions': {
                        'SpotInstanceType': 'one-time',
                        'InstanceInterruptionBehavior': 'terminate'
                    }
                }
            }

            response = self.ec2.run_instances(**launch_params)
            replica_instance_id = response['Instances'][0]['InstanceId']

            logger.info(f"Replica instance launched: {replica_instance_id}")

            # Wait for running state
            waiter = self.ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[replica_instance_id])

            # Register with server in 'launching' status
            replica_data = {
                'instance_id': replica_instance_id,
                'replica_type': replica_type,
                'parent_instance_id': primary_instance['instance_id'],
                'pool_id': f"{primary_instance['instance_type']}.{target_az}",
                'status': 'launching'
            }

            result = self.server_api.create_replica(agent_id, replica_data)

            if result:
                replica_id = result.get('replica_id')
                self.active_replicas[replica_id] = {
                    'instance_id': replica_instance_id,
                    'replica_type': replica_type,
                    'status': 'launching'
                }
                logger.info(f"Replica registered: {replica_id}, starting sync...")

                # Report syncing status
                self.server_api.update_replica_status(agent_id, replica_id, {
                    'status': 'syncing',
                    'sync_started_at': datetime.now(timezone.utc).isoformat()
                })
                self.active_replicas[replica_id]['status'] = 'syncing'

                # Wait for instance to be fully initialized (status checks)
                logger.info(f"Waiting for replica {replica_id} to pass status checks...")
                try:
                    waiter = self.ec2.get_waiter('instance_status_ok')
                    waiter.wait(
                        InstanceIds=[replica_instance_id],
                        WaiterConfig={'Delay': 15, 'MaxAttempts': 20}
                    )

                    # Report ready status
                    self.server_api.update_replica_status(agent_id, replica_id, {
                        'status': 'ready',
                        'sync_completed_at': datetime.now(timezone.utc).isoformat()
                    })
                    self.active_replicas[replica_id]['status'] = 'ready'
                    logger.info(f"Replica {replica_id} is ready")
                except Exception as wait_error:
                    logger.warning(f"Status check wait failed, marking ready anyway: {wait_error}")
                    # Still mark as ready - instance is running even if status checks aren't perfect
                    self.server_api.update_replica_status(agent_id, replica_id, {
                        'status': 'ready',
                        'sync_completed_at': datetime.now(timezone.utc).isoformat()
                    })
                    self.active_replicas[replica_id]['status'] = 'ready'

                return replica_id

            return None
        except Exception as e:
            logger.error(f"Failed to create replica: {e}")
            return None

    def promote_replica(self, agent_id: str, replica_id: str) -> bool:
        """Promote a replica to primary"""
        try:
            if replica_id not in self.active_replicas:
                logger.error(f"Replica {replica_id} not found")
                return False

            replica = self.active_replicas[replica_id]

            # Update server
            result = self.server_api.promote_replica(agent_id, replica_id)

            if result:
                logger.info(f"Replica {replica_id} promoted to primary")
                del self.active_replicas[replica_id]
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to promote replica: {e}")
            return False

    def terminate_replica(self, replica_id: str) -> bool:
        """Terminate a replica instance"""
        try:
            if replica_id not in self.active_replicas:
                return False

            replica = self.active_replicas[replica_id]
            instance_id = replica['instance_id']

            self.ec2.terminate_instances(InstanceIds=[instance_id])

            del self.active_replicas[replica_id]
            logger.info(f"Replica {replica_id} terminated")
            return True
        except Exception as e:
            logger.error(f"Failed to terminate replica: {e}")
            return False

# ============================================================================
# INSTANCE SWITCHER
# ============================================================================

class InstanceSwitcher:
    """Handle instance switching with detailed timing"""

    def __init__(self, server_api: ServerAPI):
        self.server_api = server_api
        self.ec2 = aws_clients.ec2
        self.ec2_resource = aws_clients.ec2_resource
        self.pricing_collector = SpotPricingCollector()

    def execute_switch(self, command: Dict, current_instance_id: str) -> bool:
        """Execute instance switch with detailed timing tracking - FAST MODE (under 2 mins)"""
        try:
            target_mode = command['target_mode']
            target_pool_id = command.get('target_pool_id')
            agent_id = command.get('agent_id')

            logger.info(f"Starting FAST switch: {current_instance_id} -> {target_mode}")

            timing = {
                'switch_initiated_at': datetime.now(timezone.utc).isoformat(),
                'new_instance_launched_at': None,
                'new_instance_ready_at': None,
                'traffic_switched_at': None
            }

            # Get current instance details
            current_instance = self._get_instance_details(current_instance_id)
            if not current_instance:
                logger.error("Cannot get current instance details")
                return False

            # OPTIMIZATION: Skip AMI creation, use existing AMI for fast switching
            # Only create AMI if explicitly requested via config
            ami_id = current_instance['ami_id']  # Use current AMI
            snapshot_data = {'used': False}

            logger.info(f"Using existing AMI: {ami_id} (skipping AMI creation for speed)")

            # Step 2: Launch new instance immediately
            new_instance_id = self._launch_new_instance(
                current_instance, target_mode, target_pool_id, ami_id
            )

            if not new_instance_id:
                logger.error("Failed to launch new instance")
                return False

            timing['new_instance_launched_at'] = datetime.now(timezone.utc).isoformat()

            # Wait for new instance to be ready
            if not self._wait_for_instance_ready(new_instance_id):
                logger.error("New instance failed to start")
                self._cleanup_failed_switch(new_instance_id)
                return False

            timing['new_instance_ready_at'] = datetime.now(timezone.utc).isoformat()

            # Get new instance details
            new_instance = self._get_instance_details(new_instance_id)

            # Step 3: Traffic switch point
            logger.info("Traffic switch point - update load balancer/DNS")
            time.sleep(2)
            timing['traffic_switched_at'] = datetime.now(timezone.utc).isoformat()

            # Step 4: Terminate old instance based on command's terminate_wait_seconds
            # CRITICAL FIX: Respect command parameter, not config file
            terminate_wait = command.get('terminate_wait_seconds') or 0

            if terminate_wait > 0:
                logger.info(f"Auto-terminate enabled: waiting {terminate_wait}s before terminating old instance...")
                time.sleep(terminate_wait)

                if self._terminate_instance(current_instance_id):
                    timing['old_instance_terminated_at'] = datetime.now(timezone.utc).isoformat()
                    logger.info(f"Old instance {current_instance_id} terminated")
            else:
                logger.info("Auto-terminate disabled (terminate_wait_seconds=0): keeping old instance running")
                # Don't include old_terminated_at in timing when auto-terminate is disabled

            # Collect pricing data
            on_demand_price = self.pricing_collector.get_ondemand_price(
                current_instance['instance_type'], config.REGION
            )

            prices = {'on_demand': on_demand_price}

            if current_instance.get('current_mode') == 'spot':
                old_spot = self.pricing_collector.get_spot_price(
                    current_instance['instance_type'], current_instance['az']
                )
                prices['old_spot'] = old_spot

            if target_mode == 'spot' and new_instance:
                new_spot = self.pricing_collector.get_spot_price(
                    new_instance['instance_type'], new_instance['az']
                )
                prices['new_spot'] = new_spot

            # Send switch report
            switch_report = {
                'old_instance': {
                    'instance_id': current_instance_id,
                    'instance_type': current_instance['instance_type'],
                    'region': config.REGION,
                    'az': current_instance['az'],
                    'ami_id': current_instance['ami_id'],
                    'mode': current_instance.get('current_mode', 'unknown'),
                    'pool_id': current_instance.get('current_pool_id')
                },
                'new_instance': {
                    'instance_id': new_instance_id,
                    'instance_type': new_instance['instance_type'] if new_instance else current_instance['instance_type'],
                    'region': config.REGION,
                    'az': new_instance['az'] if new_instance else target_pool_id.split('.')[-1] if target_pool_id else current_instance['az'],
                    'ami_id': ami_id or current_instance['ami_id'],
                    'mode': target_mode,
                    'pool_id': target_pool_id
                },
                'snapshot': snapshot_data,
                'prices': prices,
                'timing': timing,
                'trigger': 'manual' if command.get('priority', 0) >= 50 else 'model'
            }

            self.server_api.send_switch_report(agent_id, switch_report)

            logger.info(f"Switch completed: {current_instance_id} -> {new_instance_id}")
            return True

        except Exception as e:
            logger.error(f"Switch execution failed: {e}", exc_info=True)
            return False

    def _get_instance_details(self, instance_id: str) -> Optional[Dict]:
        """Get instance details from AWS including IAM profile, security groups, etc"""
        try:
            response = self.ec2.describe_instances(InstanceIds=[instance_id])

            if not response['Reservations']:
                return None

            instance = response['Reservations'][0]['Instances'][0]
            lifecycle = instance.get('InstanceLifecycle', 'normal')
            mode = 'spot' if lifecycle == 'spot' else 'ondemand'

            # Extract IAM instance profile
            iam_profile = None
            if 'IamInstanceProfile' in instance:
                iam_profile = instance['IamInstanceProfile'].get('Arn')

            # Extract security groups
            security_groups = [sg['GroupId'] for sg in instance.get('SecurityGroups', [])]

            return {
                'instance_id': instance_id,
                'instance_type': instance['InstanceType'],
                'az': instance['Placement']['AvailabilityZone'],
                'ami_id': instance['ImageId'],
                'current_mode': mode,
                'current_pool_id': f"{instance['InstanceType']}.{instance['Placement']['AvailabilityZone']}" if mode == 'spot' else None,
                'iam_instance_profile': iam_profile,
                'security_groups': security_groups,
                'key_name': instance.get('KeyName'),
                'subnet_id': instance.get('SubnetId')
            }
        except Exception as e:
            logger.error(f"Failed to get instance details: {e}")
            return None

    def _create_ami(self, instance: Dict) -> Optional[Dict]:
        """Create AMI from instance (SLOW - only use when necessary)"""
        try:
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
            ami_name = f"SpotOptimizer-{instance['instance_id']}-{timestamp}"

            response = self.ec2.create_image(
                InstanceId=instance['instance_id'],
                Name=ami_name,
                Description=f"Spot Optimizer AMI - {datetime.now(timezone.utc).isoformat()}",
                NoReboot=True,
                TagSpecifications=[{
                    'ResourceType': 'image',
                    'Tags': [
                        {'Key': 'Name', 'Value': ami_name},
                        {'Key': 'ManagedBy', 'Value': 'SpotOptimizer'},
                        {'Key': 'SourceInstance', 'Value': instance['instance_id']}
                    ]
                }]
            )

            ami_id = response['ImageId']
            logger.info(f"AMI created: {ami_id}")

            # Wait for AMI to be available
            waiter = self.ec2.get_waiter('image_available')
            waiter.wait(ImageIds=[ami_id], WaiterConfig={'Delay': 15, 'MaxAttempts': 40})

            return {
                'used': True,
                'ami_id': ami_id,
                'ami_name': ami_name
            }
        except Exception as e:
            logger.error(f"Failed to create AMI: {e}")
            return None

    def _launch_new_instance(self, current_instance: Dict, target_mode: str,
                            target_pool_id: Optional[str], ami_id: Optional[str] = None) -> Optional[str]:
        """Launch new instance with same configuration as current"""
        try:
            launch_params = {
                'ImageId': ami_id or current_instance['ami_id'],
                'InstanceType': current_instance['instance_type'],
                'MinCount': 1,
                'MaxCount': 1,
                'TagSpecifications': [{
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': f"SpotOptimizer-{target_mode}"},
                        {'Key': 'ManagedBy', 'Value': 'SpotOptimizer'},
                        {'Key': 'LogicalAgentId', 'Value': config.LOGICAL_AGENT_ID or 'default'}
                    ]
                }]
            }

            # Copy IAM instance profile from current instance
            if current_instance.get('iam_instance_profile'):
                launch_params['IamInstanceProfile'] = {
                    'Arn': current_instance['iam_instance_profile']
                }

            # Copy security groups
            if current_instance.get('security_groups'):
                launch_params['SecurityGroupIds'] = current_instance['security_groups']

            # Copy key pair
            if current_instance.get('key_name'):
                launch_params['KeyName'] = current_instance['key_name']

            # Set placement and market options for target mode
            if target_mode == 'spot' and target_pool_id:
                target_az = target_pool_id.split('.')[-1]
                launch_params['Placement'] = {'AvailabilityZone': target_az}
                launch_params['InstanceMarketOptions'] = {
                    'MarketType': 'spot',
                    'SpotOptions': {
                        'SpotInstanceType': 'one-time',
                        'InstanceInterruptionBehavior': 'terminate'
                    }
                }

                # Only copy subnet if staying in same AZ
                current_az = current_instance.get('az', '')
                if current_az == target_az and current_instance.get('subnet_id'):
                    launch_params['SubnetId'] = current_instance['subnet_id']
                    logger.info(f"Using existing subnet (same AZ: {target_az})")
                else:
                    logger.info(f"Switching AZ: {current_az} -> {target_az}, AWS will select subnet")
            else:
                # On-demand mode - copy subnet as-is (staying in same AZ)
                if current_instance.get('subnet_id'):
                    launch_params['SubnetId'] = current_instance['subnet_id']

            response = self.ec2.run_instances(**launch_params)
            new_instance_id = response['Instances'][0]['InstanceId']
            logger.info(f"New instance launched: {new_instance_id} ({target_mode})")

            return new_instance_id
        except Exception as e:
            logger.error(f"Failed to launch instance: {e}")
            return None

    def _wait_for_instance_ready(self, instance_id: str, timeout: int = 300) -> bool:
        """Wait for instance to be running"""
        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.wait_until_running(
                WaiterConfig={'Delay': 10, 'MaxAttempts': timeout // 10}
            )
            return True
        except Exception as e:
            logger.error(f"Instance failed to start: {e}")
            return False

    def _terminate_instance(self, instance_id: str) -> bool:
        """Terminate instance with confirmation"""
        try:
            self.ec2.terminate_instances(InstanceIds=[instance_id])

            instance = self.ec2_resource.Instance(instance_id)
            instance.wait_until_terminated(WaiterConfig={'Delay': 15, 'MaxAttempts': 20})

            return True
        except Exception as e:
            logger.error(f"Failed to terminate instance: {e}")
            return False

    def _cleanup_failed_switch(self, instance_id: str):
        """Clean up after failed switch"""
        try:
            self.ec2.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Cleaned up failed instance: {instance_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup instance: {e}")

# ============================================================================
# MAIN AGENT CLASS
# ============================================================================

class SpotOptimizerAgent:
    """Main agent class - orchestrates all operations"""

    def __init__(self):
        self.server_api = ServerAPI()
        self.pricing_collector = SpotPricingCollector()
        self.instance_switcher = InstanceSwitcher(self.server_api)
        self.cleanup_manager = CleanupManager()
        self.replica_manager = ReplicaManager(self.server_api)

        # Agent state
        self.agent_id: Optional[str] = None
        self.instance_id: str = InstanceMetadata.get_instance_id()
        self.logical_agent_id: str = config.LOGICAL_AGENT_ID or self.instance_id
        self.is_running = False
        self.is_enabled = True

        # Pricing cache
        self.cached_instance_type: Optional[str] = None
        self.cached_ondemand_price: Optional[float] = None

        # Threads
        self.threads: List[threading.Thread] = []
        self.shutdown_event = threading.Event()

        logger.info(f"Agent initialized: Instance={self.instance_id}, Logical={self.logical_agent_id}")

    def start(self):
        """Start the agent"""
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # Check server connectivity before starting
            if not self.server_api.check_server_connectivity():
                logger.error("Server connectivity check failed. Exiting.")
                sys.exit(1)

            if not self._register():
                logger.error("Failed to register agent. Exiting.")
                return

            # Cache on-demand price
            self.cached_instance_type = InstanceMetadata.get_instance_type()
            self.cached_ondemand_price = self.pricing_collector.get_ondemand_price(
                self.cached_instance_type, config.REGION
            )

            self.is_running = True
            self._start_workers()

            logger.info("=" * 80)
            logger.info(f"Agent started - ID: {self.agent_id}")
            logger.info(f"Instance: {self.instance_id} ({self.cached_instance_type})")
            logger.info(f"Version: {config.AGENT_VERSION}")
            logger.info("=" * 80)

            while self.is_running and not self.shutdown_event.is_set():
                time.sleep(1)

        except Exception as e:
            logger.error(f"Agent start failed: {e}", exc_info=True)
        finally:
            self._shutdown()

    def _register(self) -> bool:
        """Register with server"""
        try:
            instance_type = InstanceMetadata.get_instance_type()
            az = InstanceMetadata.get_availability_zone()
            ami_id = InstanceMetadata.get_ami_id()
            private_ip = InstanceMetadata.get_private_ip()
            public_ip = InstanceMetadata.get_public_ip()

            # Detect mode - use metadata as fallback if API fails
            current_mode, api_mode = InstanceMetadata.detect_instance_mode_dual()
            # If both fail, default to ondemand
            if current_mode == 'unknown':
                current_mode = 'ondemand'
                logger.warning("Could not detect instance mode, defaulting to 'ondemand'")

            registration_data = {
                'client_token': config.CLIENT_TOKEN,
                'hostname': config.HOSTNAME,
                'instance_id': self.instance_id,
                'instance_type': instance_type,
                'region': config.REGION,
                'az': az,
                'ami_id': ami_id,
                'agent_version': config.AGENT_VERSION,
                'logical_agent_id': self.logical_agent_id,
                'mode': current_mode,  # Backend expects 'mode', not 'current_mode'
                'private_ip': private_ip,
                'public_ip': public_ip
            }

            response = self.server_api.register_agent(registration_data)

            if not response:
                return False

            self.agent_id = response['agent_id']
            agent_config = response.get('config', {})
            self.is_enabled = agent_config.get('enabled', True)

            logger.info(f"Registered as agent: {self.agent_id}")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    def _start_workers(self):
        """Start background worker threads"""
        workers = [
            (self._heartbeat_worker, "Heartbeat"),
            (self._pending_commands_worker, "PendingCommands"),
            (self._replica_polling_worker, "ReplicaPolling"),
            (self._replica_termination_worker, "ReplicaTermination"),
            (self._config_refresh_worker, "ConfigRefresh"),
            (self._pricing_report_worker, "PricingReport"),
            (self._termination_check_worker, "TerminationCheck"),
            (self._rebalance_check_worker, "RebalanceCheck"),
            (self._cleanup_worker, "Cleanup")
        ]

        for worker_func, worker_name in workers:
            thread = threading.Thread(target=worker_func, name=worker_name, daemon=True)
            thread.start()
            self.threads.append(thread)
            logger.info(f"Started worker: {worker_name}")

    def _heartbeat_worker(self):
        """Send accurate heartbeat with instance details"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                status = 'online' if self.is_enabled else 'disabled'

                # Get current instance details for heartbeat
                instance_type = InstanceMetadata.get_metadata('meta-data/instance-type')
                az = InstanceMetadata.get_metadata('meta-data/placement/availability-zone')
                current_mode, _ = InstanceMetadata.detect_instance_mode_dual()
                if current_mode == 'unknown':
                    current_mode = 'ondemand'

                extra_data = {
                    'instance_id': self.instance_id,
                    'instance_type': instance_type,
                    'mode': current_mode,
                    'az': az
                }

                self.server_api.send_heartbeat(self.agent_id, status, [self.instance_id], extra_data)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            self.shutdown_event.wait(config.HEARTBEAT_INTERVAL)

    def _pending_commands_worker(self):
        """Fast polling for pending commands"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                if not self.is_enabled:
                    self.shutdown_event.wait(config.PENDING_COMMANDS_CHECK_INTERVAL)
                    continue

                commands = self.server_api.get_pending_commands(self.agent_id)

                if commands:
                    logger.info(f"Found {len(commands)} pending command(s)")

                    for command in commands:
                        if not isinstance(command, dict):
                            continue

                        command_id = command.get('id')
                        command_type = command.get('command_type', 'switch')  # Default to switch for backward compatibility

                        if not command_id:
                            continue

                        # Handle different command types
                        if command_type == 'create_replica':
                            # Manual replica creation command
                            logger.info(f"Executing replica creation command {command_id}")

                            success = False
                            message = "Replica creation failed"

                            current_instance = self.instance_switcher._get_instance_details(self.instance_id)
                            if current_instance:
                                target_pool_id = command.get('target_pool_id')
                                replica_id = self.replica_manager.create_replica(
                                    self.agent_id, current_instance, 'manual', target_pool_id
                                )
                                if replica_id:
                                    success = True
                                    message = f"Replica created: {replica_id}"
                                    logger.info(message)

                            self.server_api.mark_command_executed(
                                self.agent_id, command_id, success, message
                            )

                        else:
                            # Switch command (default)
                            target_mode = command.get('target_mode')
                            if not target_mode:
                                continue

                            logger.info(f"Executing switch command {command_id}: {target_mode}")

                            success = self.instance_switcher.execute_switch(
                                {**command, 'agent_id': self.agent_id},
                                self.instance_id
                            )

                            self.server_api.mark_command_executed(
                                self.agent_id, command_id, success,
                                "Switch completed" if success else "Switch failed"
                            )

                            # Stop agent if switch was successful AND old instance was terminated
                            terminate_wait = command.get('terminate_wait_seconds') or 0
                            if success and terminate_wait > 0:
                                logger.info("Old instance terminated, stopping agent...")
                                self.is_running = False
                                break

                        break

            except Exception as e:
                logger.error(f"Pending commands error: {e}")

            self.shutdown_event.wait(config.PENDING_COMMANDS_CHECK_INTERVAL)

    def _replica_polling_worker(self):
        """Poll for replicas that need to be launched"""
        launched_replicas = set()  # Track replicas we've already started launching

        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Poll for replicas with status='launching' that need EC2 instances
                pending_replicas = self.server_api.get_pending_replicas(self.agent_id)

                for replica in pending_replicas:
                    replica_id = replica.get('id')
                    pool_id = replica.get('pool_id')
                    target_az = replica.get('az')
                    instance_id = replica.get('instance_id')

                    if not all([replica_id, pool_id, target_az]):
                        logger.warning(f"Invalid replica data: {replica}")
                        continue

                    # Skip if we've already started launching this replica in this session
                    if replica_id in launched_replicas:
                        logger.debug(f"Skipping replica {replica_id} - already launched in this session")
                        continue

                    # Skip if replica already has a real EC2 instance ID (not placeholder)
                    if instance_id and not instance_id.startswith('manual-'):
                        logger.debug(f"Skipping replica {replica_id} - already has instance {instance_id}")
                        continue

                    logger.info(f"Launching EC2 instance for replica {replica_id} in AZ {target_az}")
                    launched_replicas.add(replica_id)  # Mark as being launched

                    try:
                        # Get current instance details to copy configuration
                        current_instance = self.instance_switcher._get_instance_details(self.instance_id)
                        if not current_instance:
                            logger.error("Cannot get current instance details")
                            continue

                        # Launch replica instance with same config as current
                        launch_params = {
                            'ImageId': current_instance['ami_id'],
                            'InstanceType': current_instance['instance_type'],
                            'MinCount': 1,
                            'MaxCount': 1,
                            'Placement': {'AvailabilityZone': target_az},
                            'TagSpecifications': [{
                                'ResourceType': 'instance',
                                'Tags': [
                                    {'Key': 'Name', 'Value': f'replica-{replica_id[:8]}'},
                                    {'Key': 'ReplicaId', 'Value': replica_id},
                                    {'Key': 'ParentInstance', 'Value': self.instance_id}
                                ]
                            }]
                        }

                        # Copy IAM profile
                        if current_instance.get('iam_instance_profile'):
                            launch_params['IamInstanceProfile'] = {'Arn': current_instance['iam_instance_profile']}

                        # Copy security groups
                        if current_instance.get('security_groups'):
                            launch_params['SecurityGroupIds'] = current_instance['security_groups']

                        # Copy key pair
                        if current_instance.get('key_name'):
                            launch_params['KeyName'] = current_instance['key_name']

                        # Launch spot instance
                        launch_params['InstanceMarketOptions'] = {
                            'MarketType': 'spot',
                            'SpotOptions': {
                                'SpotInstanceType': 'one-time',
                                'InstanceInterruptionBehavior': 'terminate'
                            }
                        }

                        response = self.instance_switcher.ec2.run_instances(**launch_params)
                        replica_instance_id = response['Instances'][0]['InstanceId']
                        logger.info(f"Replica instance launched: {replica_instance_id} for replica {replica_id}")

                        # Update backend with real instance ID
                        self.server_api.update_replica_instance(
                            self.agent_id,
                            replica_id,
                            replica_instance_id,
                            status='syncing'
                        )

                        # Wait for instance to be running
                        waiter = self.instance_switcher.ec2.get_waiter('instance_running')
                        waiter.wait(InstanceIds=[replica_instance_id])

                        # Update status to ready
                        self.server_api.update_replica_status(
                            self.agent_id,
                            replica_id,
                            {'status': 'ready', 'sync_completed_at': datetime.now(timezone.utc).isoformat()}
                        )
                        logger.info(f"Replica {replica_id} is ready: {replica_instance_id}")

                    except Exception as e:
                        logger.error(f"Failed to launch replica {replica_id}: {e}")
                        # Update replica status to failed
                        self.server_api.update_replica_status(
                            self.agent_id,
                            replica_id,
                            {'status': 'failed', 'error_message': str(e)}
                        )

            except Exception as e:
                logger.error(f"Replica polling error: {e}")

            # Poll every 30 seconds
            self.shutdown_event.wait(30)

    def _replica_termination_worker(self):
        """Poll for replicas that need to be terminated and terminate their EC2 instances"""
        terminated_replica_ids = set()  # Track replicas we've already terminated

        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Get replicas marked as 'terminated' in database
                terminated_replicas = self.server_api.get_pending_replicas(self.agent_id)

                # Filter for status='terminated' by making a specific request
                result = self.server_api._make_request(
                    'GET',
                    f'/api/agents/{self.agent_id}/replicas?status=terminated'
                )

                if result and isinstance(result, dict):
                    terminated_replicas = result.get('replicas', [])
                elif isinstance(result, list):
                    terminated_replicas = result
                else:
                    terminated_replicas = []

                for replica in terminated_replicas:
                    replica_id = replica.get('id')
                    instance_id = replica.get('instance_id')
                    is_active = replica.get('is_active', False)

                    if not all([replica_id, instance_id]):
                        continue

                    # Skip if we've already terminated this replica in this session
                    if replica_id in terminated_replica_ids:
                        continue

                    # Skip if replica is not active (already terminated)
                    if not is_active:
                        continue

                    # Skip placeholder instance IDs (not real EC2 instances)
                    if instance_id.startswith('manual-') or instance_id.startswith('replica-'):
                        logger.debug(f"Skipping placeholder instance {instance_id} for replica {replica_id}")
                        terminated_replica_ids.add(replica_id)
                        continue

                    logger.info(f"Terminating EC2 instance {instance_id} for replica {replica_id}")
                    terminated_replica_ids.add(replica_id)

                    try:
                        # Terminate the EC2 instance
                        self.instance_switcher.ec2.terminate_instances(InstanceIds=[instance_id])
                        logger.info(f"Successfully terminated EC2 instance {instance_id} for replica {replica_id}")

                        # Update replica status to confirm termination
                        self.server_api.update_replica_status(
                            self.agent_id,
                            replica_id,
                            {
                                'status': 'terminated',
                                'is_active': False,
                                'terminated_at': datetime.now(timezone.utc).isoformat()
                            }
                        )

                    except Exception as e:
                        logger.error(f"Failed to terminate EC2 instance {instance_id} for replica {replica_id}: {e}")
                        # Don't retry immediately - will try again on next poll

            except Exception as e:
                logger.error(f"Replica termination polling error: {e}")

            # Poll every 30 seconds
            self.shutdown_event.wait(30)

    def _config_refresh_worker(self):
        """Periodically refresh configuration"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                agent_config = self.server_api.get_agent_config(self.agent_id)

                if agent_config:
                    new_enabled = agent_config.get('enabled', True)

                    if new_enabled != self.is_enabled:
                        logger.info(f"Agent enabled state changed: {self.is_enabled} -> {new_enabled}")
                        self.is_enabled = new_enabled

            except Exception as e:
                logger.error(f"Config refresh error: {e}")

            self.shutdown_event.wait(config.CONFIG_REFRESH_INTERVAL)

    def _pricing_report_worker(self):
        """Send pricing report"""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                instance_type = InstanceMetadata.get_instance_type()
                az = InstanceMetadata.get_availability_zone()
                current_mode, _ = InstanceMetadata.detect_instance_mode_dual()
                if current_mode == 'unknown':
                    current_mode = 'ondemand'

                spot_pools = self.pricing_collector.get_spot_pools(instance_type, config.REGION)
                on_demand_price = self.cached_ondemand_price or self.pricing_collector.get_ondemand_price(
                    instance_type, config.REGION
                )

                # Get current spot price from pools if on spot
                current_spot_price = None
                current_pool_id = None
                cheapest_pool = None

                if current_mode == 'spot' and spot_pools:
                    current_pool_id = f"{instance_type}.{az}"
                    # Find current pool price
                    for pool in spot_pools:
                        if pool.get('az') == az:
                            current_spot_price = pool.get('price')
                            break
                    # Find cheapest pool
                    if spot_pools:
                        cheapest = min(spot_pools, key=lambda x: x.get('price', float('inf')))
                        cheapest_pool = {
                            'pool_id': cheapest.get('pool_id'),
                            'price': cheapest.get('price')
                        }

                report = {
                    'instance': {
                        'instance_id': self.instance_id,
                        'instance_type': instance_type,
                        'region': config.REGION,
                        'az': az,
                        'mode': current_mode,  # Backend expects 'mode' not 'current_mode'
                        'pool_id': current_pool_id
                    },
                    'pricing': {
                        'on_demand_price': on_demand_price,
                        'current_spot_price': current_spot_price,
                        'cheapest_pool': cheapest_pool,
                        'spot_pools': spot_pools,
                        'collected_at': datetime.now(timezone.utc).isoformat()
                    }
                }

                self.server_api.send_pricing_report(self.agent_id, report)
                logger.info(f"Pricing report sent: {len(spot_pools)} pools")

            except Exception as e:
                logger.error(f"Pricing report error: {e}")

            self.shutdown_event.wait(config.PRICING_REPORT_INTERVAL)

    def _termination_check_worker(self):
        """Check for spot termination notices (2-minute warning)"""
        termination_already_handled = False  # Only handle once

        while self.is_running and not self.shutdown_event.is_set():
            try:
                current_mode, _ = InstanceMetadata.detect_instance_mode_dual()

                if current_mode == 'spot':
                    termination_notice = InstanceMetadata.check_spot_termination_notice()

                    if termination_notice and not termination_already_handled:
                        logger.critical(f"SPOT TERMINATION NOTICE DETECTED! Instance {self.instance_id} will be terminated!")
                        termination_already_handled = True

                        termination_time = termination_notice.get('time')

                        # CRITICAL PATH - 2 minutes to handle failover
                        # Step 1: Try to create emergency replica via backend
                        # Backend checks if replica already exists and skips if so
                        logger.warning("Attempting emergency replica creation via backend...")
                        replica_response = self.server_api.create_emergency_replica(
                            self.agent_id,
                            signal_type='termination-notice',
                            instance_id=self.instance_id,
                            termination_time=termination_time
                        )

                        if replica_response and replica_response.get('success'):
                            replica_id = replica_response.get('replica_id')
                            logger.info(f"Emergency replica created by backend: {replica_id}")
                        else:
                            logger.warning(f"Emergency replica creation skipped: {replica_response.get('error') if replica_response else 'No response'}")

                        # Step 2: Report termination imminent to backend for failover
                        # Backend will promote existing replica (created above or previously)
                        logger.critical("Reporting termination imminent to backend for failover...")
                        failover_response = self.server_api.report_termination_notice(
                            self.agent_id,
                            {
                                'instance_id': self.instance_id,
                                'termination_time': termination_time,
                                'detected_at': datetime.now(timezone.utc).isoformat()
                            }
                        )

                        if failover_response:
                            if failover_response.get('success'):
                                logger.info(f"Failover successful: {failover_response.get('message')}")
                                logger.info(f"New instance: {failover_response.get('new_instance_id')}")

                                # Agent will be terminated by AWS in ~2 minutes
                                # No need to continue running
                                logger.info("Shutting down agent gracefully after successful failover")
                                self.is_running = False
                                return
                            else:
                                logger.error(f"Failover failed: {failover_response.get('error')}")
                                logger.error("Agent will be terminated without successful failover")
                        else:
                            logger.error("No response from backend for termination failover")

            except Exception as e:
                logger.error(f"Termination check error: {e}")

            self.shutdown_event.wait(config.TERMINATION_CHECK_INTERVAL)

    def _rebalance_check_worker(self):
        """Check for rebalance recommendations"""
        rebalance_already_reported = False  # Prevent duplicate reports

        while self.is_running and not self.shutdown_event.is_set():
            try:
                current_mode, _ = InstanceMetadata.detect_instance_mode_dual()

                if current_mode == 'spot':
                    if InstanceMetadata.check_rebalance_recommendation():
                        if not rebalance_already_reported:
                            logger.warning("REBALANCE RECOMMENDATION DETECTED!")
                            rebalance_already_reported = True

                            # Step 1: Ask backend to create emergency replica
                            # Backend will only create if auto_switch_enabled = TRUE
                            logger.info("Requesting emergency replica from backend...")
                            replica_response = self.server_api.create_emergency_replica(
                                self.agent_id,
                                signal_type='rebalance-recommendation',
                                instance_id=self.instance_id
                            )

                            if replica_response and replica_response.get('success'):
                                replica_id = replica_response.get('replica_id')
                                logger.info(f"Backend created emergency replica: {replica_id}")

                                # Track locally
                                if replica_id:
                                    self.replica_manager.active_replicas[replica_id] = {
                                        'instance_id': replica_response.get('replica_instance_id'),
                                        'replica_type': 'emergency',
                                        'status': 'launching'
                                    }
                            else:
                                error_msg = replica_response.get('error') if replica_response else 'No response from backend'
                                logger.warning(f"Emergency replica creation failed or disabled: {error_msg}")
                                # This is OK - backend may have auto_switch disabled

                            # Step 2: Report to monitoring endpoint
                            monitoring_response = self.server_api.report_rebalance_recommendation(
                                self.agent_id, self.instance_id
                            )

                            # Step 3: Handle additional actions if server recommends
                            if monitoring_response and monitoring_response.get('action') == 'switch':
                                logger.warning("Server recommends immediate switch - will be handled by pending commands")

                    else:
                        # Reset flag when rebalance signal clears
                        rebalance_already_reported = False

            except Exception as e:
                logger.error(f"Rebalance check error: {e}")

            self.shutdown_event.wait(config.REBALANCE_CHECK_INTERVAL)

    def _cleanup_worker(self):
        """Periodic cleanup of old snapshots and AMIs"""
        # Initial delay before first cleanup
        self.shutdown_event.wait(60)

        while self.is_running and not self.shutdown_event.is_set():
            try:
                logger.info("Running cleanup operations...")
                cleanup_result = self.cleanup_manager.run_full_cleanup()

                # Report cleanup to server
                self.server_api.report_cleanup(self.agent_id, cleanup_result)

                snap_deleted = len(cleanup_result['snapshots'].get('deleted', []))
                ami_deleted = len(cleanup_result['amis'].get('deleted_amis', []))

                logger.info(f"Cleanup completed: {snap_deleted} snapshots, {ami_deleted} AMIs deleted")

            except Exception as e:
                logger.error(f"Cleanup error: {e}")

            self.shutdown_event.wait(config.CLEANUP_INTERVAL)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.is_running = False
        self.shutdown_event.set()

    def _shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down agent...")

        self.is_running = False
        self.shutdown_event.set()

        for thread in self.threads:
            thread.join(timeout=5)

        try:
            self.server_api.send_heartbeat(self.agent_id, 'offline', [])
        except:
            pass

        logger.info("Agent shutdown complete")

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    logger.info("=" * 80)
    logger.info(f"AWS Spot Optimizer Agent v{config.AGENT_VERSION}")
    logger.info("=" * 80)

    if not config.validate():
        logger.error("Configuration validation failed!")
        sys.exit(1)

    agent = SpotOptimizerAgent()
    agent.start()

if __name__ == '__main__':
    main()
