
import boto3
import logging
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.account import Account
from backend.models.system_config import SystemConfig
from backend.models.user import User

logger = logging.getLogger(__name__)

class SmartTagService:
    def __init__(self, db: Session):
        self.db = db

    def _get_account_session(self, account: Account, region: str = 'us-east-1'):
        # Reusing logic from HygieneService or similar.
        # Ideally this should be a shared utility or mixin.
        # For now, quick duplication or importing from a common place if available.
        # HygieneService has it as a method. Let's try to import or duplicate for MVP.
        # Duplication for safety/speed in this task to avoid refactoring HygieneService.
        
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        
        if not account.role_arn:
             raise Exception("Account has no Role ARN configured")

        session_params = {}
        if access_key and secret_key and access_key.value:
            session_params['aws_access_key_id'] = access_key.value
            session_params['aws_secret_access_key'] = secret_key.value
        
        platform_session = boto3.Session(**session_params)
        sts = platform_session.client('sts')
        
        assumed = sts.assume_role(
            RoleArn=account.role_arn,
            RoleSessionName="SmartTagWorker",
            ExternalId=account.external_id
        )
        creds = assumed['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=region
        )

    def process_smart_tags(self, account_id: str, region: str, dry_run: bool = True):
        """
        Main entry point to scan and process smart tags for a specific account/region.
        """
        results = {
            "ttl_processed": 0,
            "ttl_actions": 0,
            "schedule_processed": 0,
            "schedule_actions": 0,
            "details": []
        }

        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError("Account not found")

        try:
            session = self._get_account_session(account, region)
            
            # 1. Process TTL
            self._process_ttl(session, results, dry_run)
            
            # 2. Process Schedules
            self._process_schedules(session, results, dry_run)

        except Exception as e:
            logger.error(f"Error processing smart tags for {account_id}/{region}: {e}")
            raise e

        return results

    def _process_ttl(self, session, results: Dict, dry_run: bool):
        ec2 = session.client('ec2')
        # Find instances with auto:ttl or auto:termination_date
        # Filter is tricky because generic tags. We scan all running instances with these keys?
        # Or just describe instances and check tags.
        # Using filters is better.
        
        filters = [
            {'Name': 'instance-state-name', 'Values': ['running', 'stopped']},
            {'Name': 'tag-key', 'Values': ['auto:ttl', 'auto:termination_date']}
        ]
        
        paginator = ec2.get_paginator('describe_instances')
        instances_to_terminate = []

        now = datetime.now(timezone.utc) if datetime.now().tzinfo else datetime.utcnow()

        for page in paginator.paginate(Filters=filters):
            for res in page['Reservations']:
                for inst in res['Instances']:
                    tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                    instance_id = inst['InstanceId']
                    launch_time = inst['LaunchTime'].replace(tzinfo=None) # Normalize to naive or ensure both aware.
                    # Boto3 returns aware datetime.
                    
                    terminate = False
                    reason = ""

                    # Check auto:termination_date (YYYY-MM-DD or ISO)
                    if 'auto:termination_date' in tags:
                        date_str = tags['auto:termination_date']
                        try:
                            term_date = datetime.strptime(date_str, "%Y-%m-%d")
                            # Assuming end of day? Or EXACT time? Usually YYYY-MM-DD implies 00:00 or end.
                            # Let's assume strict deadline: if NOW > term_date, kill.
                            if datetime.utcnow() > term_date: 
                                terminate = True
                                reason = f"Expired auto:termination_date ({date_str})"
                        except ValueError:
                            logger.warning(f"Invalid date format for {instance_id}: {date_str}")

                    # Check auto:ttl (e.g. "7d", "24h")
                    if not terminate and 'auto:ttl' in tags:
                        ttl_val = tags['auto:ttl'].lower()
                        delta = None
                        try:
                            if ttl_val.endswith('d'):
                                days = int(ttl_val[:-1])
                                delta = timedelta(days=days)
                            elif ttl_val.endswith('h'):
                                hours = int(ttl_val[:-1])
                                delta = timedelta(hours=hours)
                                
                            if delta:
                                # Compare LaunchTime + delta vs Now
                                # LaunchTime from boto3 is aware (UTC usually).
                                expire_time = inst['LaunchTime'] + delta
                                if datetime.now(pytz.utc) > expire_time:
                                    terminate = True
                                    reason = f"Expired auto:ttl ({ttl_val})"
                        except:
                            pass

                    if terminate:
                        results["ttl_processed"] += 1
                        results["details"].append({
                            "id": instance_id, "action": "TERMINATE", "reason": reason, "dry_run": dry_run
                        })
                        if not dry_run:
                            instances_to_terminate.append(instance_id)

        if instances_to_terminate and not dry_run:
            ec2.terminate_instances(InstanceIds=instances_to_terminate)
            results["ttl_actions"] += len(instances_to_terminate)


    def _process_schedules(self, session, results: Dict, dry_run: bool):
        ec2 = session.client('ec2')
        # Filter for auto:schedule
        filters = [
            {'Name': 'tag-key', 'Values': ['auto:schedule']}
        ]
        
        paginator = ec2.get_paginator('describe_instances')
        start_ids = []
        stop_ids = []
        
        # Current time (UTC default, tag might specify TZ)
        now_utc = datetime.now(pytz.utc)

        for page in paginator.paginate(Filters=filters):
            for res in page['Reservations']:
                for inst in res['Instances']:
                    tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                    schedule_str = tags.get('auto:schedule', '')
                    instance_id = inst['InstanceId']
                    state = inst['State']['Name']
                    
                    # Parse: start=08:00,stop=18:00,days=Mon-Fri,tz=UTC
                    try:
                        parsed = self._parse_schedule(schedule_str)
                        if not parsed: continue
                        
                        should_be_running = self._evaluate_schedule(parsed, now_utc)
                        
                        if should_be_running and state == 'stopped':
                            results["details"].append({"id": instance_id, "action": "START", "reason": "Schedule matched", "dry_run": dry_run})
                            if not dry_run: start_ids.append(instance_id)
                        elif not should_be_running and state == 'running':
                            results["details"].append({"id": instance_id, "action": "STOP", "reason": "Schedule matched", "dry_run": dry_run})
                            if not dry_run: stop_ids.append(instance_id)
                            
                        results["schedule_processed"] += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to process schedule for {instance_id}: {e}")

        if start_ids and not dry_run:
            ec2.start_instances(InstanceIds=start_ids)
            results["schedule_actions"] += len(start_ids)
            
        if stop_ids and not dry_run:
            ec2.stop_instances(InstanceIds=stop_ids)
            results["schedule_actions"] += len(stop_ids)

    def _parse_schedule(self, tag_value: str) -> Optional[Dict]:
        # Format: start=08:00,stop=18:00,days=Mon-Fri,tz=America/New_York
        try:
            parts = [p.strip() for p in tag_value.split(',')]
            data = {}
            for p in parts:
                if '=' in p:
                    k, v = p.split('=', 1)
                    data[k.lower()] = v
            
            if 'start' not in data or 'stop' not in data:
                return None
            return data
        except:
            return None

    def _evaluate_schedule(self, schedule: Dict, now_utc: datetime) -> bool:
        # 1. TZ Adjust
        tz_name = schedule.get('tz', 'UTC')
        try:
            tz = pytz.timezone(tz_name)
            current_time = now_utc.astimezone(tz)
        except:
            current_time = now_utc # Fallback
            
        # 2. Days check
        # days=Mon-Fri or 0-4
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        today_idx = current_time.weekday()
        today_str = weekdays[today_idx]
        
        days_config = schedule.get('days', 'Mon-Sun').lower()
        
        allowed_days = []
        if '-' in days_config:
            # Range logic (simplified)
            start_d, end_d = days_config.split('-')
            try:
                s_idx = weekdays.index(start_d[:3])
                e_idx = weekdays.index(end_d[:3])
                if s_idx <= e_idx:
                    allowed_days = range(s_idx, e_idx + 1)
                else:
                    # Wrap around not supported in simple logic yet (e.g. Fri-Mon)
                    allowed_days = [] 
            except:
                allowed_days = range(0, 7) # Default all
        else:
             # Comma list?
             allowed_days = range(0, 7)

        if today_idx not in allowed_days:
            return False # Outside allowed days -> Should be STOPPED? 
            # Implies "Running ONLY during schedule". So yes, stop.

        # 3. Time Check
        current_hm = current_time.hour * 60 + current_time.minute
        
        def parse_time(t_str):
            h, m = map(int, t_str.split(':'))
            return h * 60 + m
            
        start_min = parse_time(schedule['start'])
        stop_min = parse_time(schedule['stop'])
        
        if start_min < stop_min:
            return start_min <= current_hm < stop_min
        else:
            # Cross midnight (e.g. 22:00 to 06:00)
            return current_hm >= start_min or current_hm < stop_min
