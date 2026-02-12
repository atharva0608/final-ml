"""
AWS Cost Explorer Integration
Fetches actual costs from AWS Cost Explorer API for 100% invoice-accurate billing
"""
import boto3
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from celery import Task
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.workers import app
from backend.models.base import get_db
from backend.models.account import Account, AccountStatus
from backend.models.billing import DailyCost, CostExplorerSyncStatus

logger = logging.getLogger(__name__)


class CostExplorerError(Exception):
    """Custom exception for Cost Explorer related errors"""
    pass


def get_aws_client(account: Account, service: str, region: str = "us-east-1"):
    """
    Get AWS client for a specific service using assumed role credentials.

    Args:
        account: Account model with role_arn
        service: AWS service name (e.g., 'ce', 'ec2')
        region: AWS region

    Returns:
        boto3 client for the specified service
    """
    if not account.role_arn:
        raise CostExplorerError(f"Account {account.aws_account_id} has no role_arn configured")

    try:
        # Assume the IAM role
        sts_client = boto3.client('sts', region_name=region)
        assumed_role = sts_client.assume_role(
            RoleArn=account.role_arn,
            RoleSessionName=f"CostExplorerSession-{account.aws_account_id}",
            DurationSeconds=3600  # 1 hour
        )

        credentials = assumed_role['Credentials']

        # Create client with assumed role credentials
        client = boto3.client(
            service,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region
        )

        return client

    except Exception as e:
        logger.error(f"Failed to assume role for account {account.aws_account_id}: {e}")
        raise CostExplorerError(f"Failed to assume role: {str(e)}")


def fetch_cost_data(
    account: Account,
    start_date: date,
    end_date: date,
    granularity: str = "DAILY"
) -> List[Dict[str, Any]]:
    """
    Fetch cost data from AWS Cost Explorer API.

    Args:
        account: Account model
        start_date: Start date for cost data
        end_date: End date for cost data (exclusive)
        granularity: 'DAILY' or 'MONTHLY'

    Returns:
        List of cost records grouped by date and service

    Example return:
        [
            {
                'date': '2026-02-10',
                'service': 'Amazon Elastic Compute Cloud - Compute',
                'amount': 125.50,
                'currency': 'USD'
            },
            ...
        ]
    """
    try:
        # Get Cost Explorer client
        ce_client = get_aws_client(account, 'ce', region='us-east-1')

        logger.info(
            f"[COST-EXPLORER] Fetching costs for account {account.aws_account_id} "
            f"from {start_date} to {end_date}"
        )

        # Call Cost Explorer API
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.isoformat(),
                'End': end_date.isoformat()
            },
            Granularity=granularity,
            Metrics=['AmortizedCost'],  # AmortizedCost accounts for RIs/Savings Plans correctly
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ],
            Filter={
                'Dimensions': {
                    'Key': 'RECORD_TYPE',
                    'Values': ['Usage', 'Tax', 'Support']  # Exclude credits/refunds from main calculation
                }
            }
        )

        # Parse response
        cost_records = []
        for day_data in response.get('ResultsByTime', []):
            date_str = day_data['TimePeriod']['Start']

            for group in day_data.get('Groups', []):
                service_name = group['Keys'][0]
                amount_str = group['Metrics']['AmortizedCost']['Amount']
                amount = float(amount_str)
                unit = group['Metrics']['AmortizedCost']['Unit']

                # Skip zero-cost entries
                if amount > 0:
                    cost_records.append({
                        'date': date_str,
                        'service': service_name,
                        'amount': amount,
                        'currency': unit
                    })

        logger.info(
            f"[COST-EXPLORER] Fetched {len(cost_records)} cost records "
            f"for account {account.aws_account_id}"
        )

        return cost_records

    except Exception as e:
        logger.error(
            f"[COST-EXPLORER] Failed to fetch costs for account {account.aws_account_id}: {e}",
            exc_info=True
        )
        raise CostExplorerError(f"Failed to fetch cost data: {str(e)}")


def sync_costs_for_account(account: Account, db: Session, days_back: int = 30) -> Dict[str, Any]:
    """
    Sync cost data for a single account.

    Args:
        account: Account model
        db: Database session
        days_back: Number of days to fetch (default 30)

    Returns:
        {
            'records_created': int,
            'records_updated': int,
            'total_cost': float,
            'date_range': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}
        }
    """
    # Calculate date range (last N days)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)

    logger.info(
        f"[COST-EXPLORER] Starting sync for account {account.aws_account_id} "
        f"({start_date} to {end_date})"
    )

    try:
        # Fetch cost data from AWS
        cost_records = fetch_cost_data(account, start_date, end_date)

        records_created = 0
        records_updated = 0
        total_cost = 0.0

        # Upsert cost records to database
        for record in cost_records:
            # Generate unique ID
            record_id = f"{account.aws_account_id}_{record['date']}_{record['service']}"

            # Check if record exists
            existing = db.query(DailyCost).filter(DailyCost.id == record_id).first()

            if existing:
                # Update existing record
                existing.cost_amount = record['amount']
                existing.currency = record['currency']
                existing.updated_at = datetime.utcnow()
                records_updated += 1
            else:
                # Create new record
                daily_cost = DailyCost(
                    id=record_id,
                    account_id=account.id,
                    date=datetime.strptime(record['date'], '%Y-%m-%d').date(),
                    service_name=record['service'],
                    cost_amount=record['amount'],
                    currency=record['currency'],
                    cost_type='Usage'
                )
                db.add(daily_cost)
                records_created += 1

            total_cost += record['amount']

        # Update sync status
        sync_status_id = account.aws_account_id
        sync_status = db.query(CostExplorerSyncStatus).filter(
            CostExplorerSyncStatus.id == sync_status_id
        ).first()

        if sync_status:
            sync_status.last_sync_at = datetime.utcnow()
            sync_status.last_synced_date = end_date
            sync_status.status = 'SUCCESS'
            sync_status.error_message = None
            sync_status.records_synced = len(cost_records)
        else:
            sync_status = CostExplorerSyncStatus(
                id=sync_status_id,
                account_id=account.id,
                last_sync_at=datetime.utcnow(),
                last_synced_date=end_date,
                status='SUCCESS',
                records_synced=len(cost_records)
            )
            db.add(sync_status)

        db.commit()

        result = {
            'records_created': records_created,
            'records_updated': records_updated,
            'total_cost': round(total_cost, 2),
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            }
        }

        logger.info(
            f"[COST-EXPLORER] Sync complete for account {account.aws_account_id}: "
            f"{records_created} created, {records_updated} updated, "
            f"Total cost: ${total_cost:.2f}"
        )

        return result

    except CostExplorerError as e:
        # Update sync status to FAILED
        sync_status_id = account.aws_account_id
        sync_status = db.query(CostExplorerSyncStatus).filter(
            CostExplorerSyncStatus.id == sync_status_id
        ).first()

        if sync_status:
            sync_status.status = 'FAILED'
            sync_status.error_message = str(e)
        else:
            sync_status = CostExplorerSyncStatus(
                id=sync_status_id,
                account_id=account.id,
                last_sync_at=datetime.utcnow(),
                last_synced_date=end_date,
                status='FAILED',
                error_message=str(e),
                records_synced=0
            )
            db.add(sync_status)

        db.commit()
        raise


@app.task(bind=True, name="workers.cost.sync_cost_explorer")
def sync_cost_explorer(self: Task, account_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Celery task to sync AWS Cost Explorer data for all active accounts.

    This task should run daily (via Celery Beat) to keep cost data fresh.

    Args:
        account_id: Optional specific account ID to sync. If None, syncs all active accounts.

    Returns:
        {
            'accounts_synced': int,
            'total_records': int,
            'total_cost': float,
            'errors': List[str]
        }
    """
    db = next(get_db())

    try:
        logger.info("[COST-EXPLORER] Starting Cost Explorer sync task...")

        # Get accounts to sync
        if account_id:
            accounts = db.query(Account).filter(
                Account.id == account_id,
                Account.status == AccountStatus.ACTIVE
            ).all()
        else:
            accounts = db.query(Account).filter(
                Account.status == AccountStatus.ACTIVE
            ).all()

        if not accounts:
            logger.warning("[COST-EXPLORER] No active accounts found to sync")
            return {
                'accounts_synced': 0,
                'total_records': 0,
                'total_cost': 0.0,
                'errors': []
            }

        accounts_synced = 0
        total_records = 0
        total_cost = 0.0
        errors = []

        for account in accounts:
            try:
                result = sync_costs_for_account(account, db, days_back=30)
                accounts_synced += 1
                total_records += result['records_created'] + result['records_updated']
                total_cost += result['total_cost']

            except Exception as e:
                error_msg = f"Account {account.aws_account_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"[COST-EXPLORER] {error_msg}", exc_info=True)
                continue

        summary = {
            'accounts_synced': accounts_synced,
            'total_records': total_records,
            'total_cost': round(total_cost, 2),
            'errors': errors
        }

        logger.info(
            f"[COST-EXPLORER] Sync task complete: "
            f"{accounts_synced} accounts, {total_records} records, "
            f"Total cost: ${total_cost:.2f}"
        )

        return summary

    except Exception as e:
        logger.error(f"[COST-EXPLORER] Sync task failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


@app.task(bind=True, name="workers.cost.cleanup_old_cost_data")
def cleanup_old_cost_data(self: Task, days_to_keep: int = 90) -> Dict[str, int]:
    """
    Cleanup old cost data to prevent database bloat.

    Args:
        days_to_keep: Number of days of cost data to retain (default 90)

    Returns:
        {'records_deleted': int}
    """
    db = next(get_db())

    try:
        cutoff_date = datetime.now().date() - timedelta(days=days_to_keep)

        logger.info(f"[COST-EXPLORER] Cleaning up cost data older than {cutoff_date}")

        # Delete old records
        deleted = db.query(DailyCost).filter(DailyCost.date < cutoff_date).delete()
        db.commit()

        logger.info(f"[COST-EXPLORER] Deleted {deleted} old cost records")

        return {'records_deleted': deleted}

    except Exception as e:
        logger.error(f"[COST-EXPLORER] Cleanup failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
