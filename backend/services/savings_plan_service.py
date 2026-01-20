"""
Savings Plan Analysis Service
Analyzes AWS Savings Plans utilization and coverage
"""
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.savings_plan_utilization import SavingsPlanUtilization, SavingsPlanType
from backend.models.account import Account
from backend.models.user import User
from backend.core.exceptions import AWSError
from backend.core.config import settings


class SavingsPlanService:
    """Service for analyzing Savings Plans - Production Grade"""
    
    def __init__(self, db: Session):
        self.db = db

    def _get_sts_credentials(self, account: Account) -> Dict[str, str]:
        """Assume role to get credentials for target account"""
        try:
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
                region_name='us-east-1'
            )
            
            response = sts_client.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=f"SavingsPlanAnalysis-{account.id[:8]}",
                ExternalId=account.external_id
            )
            
            return {
                'aws_access_key_id': response['Credentials']['AccessKeyId'],
                'aws_secret_access_key': response['Credentials']['SecretAccessKey'],
                'aws_session_token': response['Credentials']['SessionToken']
            }
        except Exception as e:
            raise AWSError(f"Failed to assume role: {str(e)}")

    def _get_ce_client(self, account: Account):
        """Get Cost Explorer client for target account"""
        creds = self._get_sts_credentials(account)
        return boto3.client(
            'ce',
            **creds,
            region_name='us-east-1'  # CE is global
        )

    def analyze_all_accounts(self, user: User, lookback_days: int = 30) -> Dict[str, Any]:
        """Analyze Savings Plans across all accounts in organization"""
        accounts = self.db.query(Account).filter(
            Account.organization_id == user.organization_id
        ).all()
        
        total_plans = 0
        total_underutilized = 0
        total_waste = 0.0
        total_savings = 0.0
        results = []
        
        for account in accounts:
            try:
                account_analysis = self.analyze_account(account, lookback_days)
                results.append(account_analysis)
                total_plans += account_analysis['total_plans']
                total_underutilized += account_analysis['underutilized_count']
                total_waste += account_analysis['total_waste']
                total_savings += account_analysis['total_actual_savings']
            except Exception as e:
                results.append({
                    'account_id': account.id,
                    'aws_account_id': account.aws_account_id,
                    'error': str(e)
                })
        
        return {
            'total_plans': total_plans,
            'underutilized_count': total_underutilized,
            'total_monthly_waste': total_waste,
            'total_actual_savings': total_savings,
            'accounts_analyzed': len(results),
            'lookback_days': lookback_days,
            'accounts': results
        }

    def analyze_account(self, account: Account, lookback_days: int = 30) -> Dict[str, Any]:
        """Analyze Savings Plans for a specific account"""
        try:
            ce_client = self._get_ce_client(account)
            
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=lookback_days)
            
            # Get Savings Plans utilization
            utilization_response = ce_client.get_savings_plans_utilization(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY'
            )
            
            # Get Savings Plans coverage
            coverage_response = ce_client.get_savings_plans_coverage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY'
            )
            
            # Process Savings Plans
            plans = []
            total_waste = 0.0
            total_savings = 0.0
            underutilized_count = 0
            
            # Note: CE API returns aggregate data, not per-plan details
            # For per-plan details, you'd need to use SavingsPlans API
            aggregate_data = self._process_aggregate_data(
                utilization_response,
                coverage_response,
                account,
                lookback_days
            )
            
            if aggregate_data:
                plans.append(aggregate_data)
                total_waste = aggregate_data.get('monthly_waste', 0)
                total_savings = aggregate_data.get('actual_savings', 0)
                if aggregate_data.get('is_underutilized'):
                    underutilized_count += 1
            
            return {
                'account_id': account.id,
                'aws_account_id': account.aws_account_id,
                'total_plans': len(plans),
                'underutilized_count': underutilized_count,
                'total_waste': total_waste,
                'total_actual_savings': total_savings,
                'plans': plans
            }
            
        except Exception as e:
            raise AWSError(f"Failed to analyze Savings Plans for account {account.aws_account_id}: {str(e)}")

    def _process_aggregate_data(
        self,
        utilization_response: Dict,
        coverage_response: Dict,
        account: Account,
        lookback_days: int
    ) -> Optional[Dict]:
        """Process aggregate Savings Plans data from Cost Explorer"""
        try:
            if not utilization_response.get('Total'):
                return None
            
            util_data = utilization_response['Total']
            coverage_data = coverage_response['Total'] if coverage_response.get('Total') else {}
            
            # Extract utilization metrics
            utilization_pct = float(util_data.get('Utilization', {}).get('UtilizationPercentage', 0))
            total_commitment = float(util_data.get('TotalCommitment', 0))
            used_commitment = float(util_data.get('UsedCommitment', 0))
            unused_commitment = float(util_data.get('UnusedCommitment', 0))
            
            # Extract savings metrics
            net_savings = float(util_data.get('NetSavings', 0))
            on_demand_equiv = float(util_data.get('OnDemandCostEquivalent', 0))
            
            # Extract coverage metrics
            coverage_pct = float(coverage_data.get('CoverageHours', {}).get('CoverageHoursPercentage', 0))
            on_demand_hours = float(coverage_data.get('CoverageHours', {}).get('OnDemandHours', 0))
            
            # Calculate monthly values
            days_in_period = lookback_days
            monthly_commitment = (total_commitment / days_in_period) * 30
            monthly_waste = (unused_commitment / days_in_period) * 30
            monthly_savings = (net_savings / days_in_period) * 30
            
            # Determine if underutilized
            is_underutilized = utilization_pct < 70.0
            
            # Store in database
            self._upsert_savings_plan(
                account,
                monthly_commitment,
                utilization_pct,
                used_commitment,
                unused_commitment,
                monthly_waste,
                monthly_savings,
                coverage_pct,
                on_demand_hours * (1 - coverage_pct/100),
                is_underutilized,
                lookback_days
            )
            
            return {
                'utilization_percentage': utilization_pct,
                'monthly_commitment': monthly_commitment,
                'monthly_waste': monthly_waste,
                'actual_savings': monthly_savings,
                'coverage_percentage': coverage_pct,
                'is_underutilized': is_underutilized
            }
            
        except Exception as e:
            print(f"Error processing Savings Plans data: {e}")
            return None

    def _upsert_savings_plan(
        self,
        account: Account,
        monthly_commitment: float,
        utilization_pct: float,
        utilized: float,
        unused: float,
        monthly_waste: float,
        monthly_savings: float,
        coverage_pct: float,
        on_demand_spend: float,
        is_underutilized: bool,
        lookback_days: int
    ) -> SavingsPlanUtilization:
        """Create or update Savings Plan utilization record"""
        
        # For aggregate data, we use a pseudo ID
        sp_id = f"aggregate-{account.id}"
        
        existing = self.db.query(SavingsPlanUtilization).filter(
            SavingsPlanUtilization.savings_plan_id == sp_id
        ).first()
        
        if existing:
            existing.monthly_commitment = monthly_commitment
            existing.utilization_percentage = utilization_pct
            existing.utilized_commitment = utilized
            existing.unused_commitment = unused
            existing.actual_savings = monthly_savings
            existing.coverage_percentage = coverage_pct
            existing.on_demand_spend = on_demand_spend
            existing.is_underutilized = is_underutilized
            existing.lookback_days = lookback_days
            existing.last_analyzed_at = datetime.utcnow()
            self.db.commit()
            return existing
        else:
            new_plan = SavingsPlanUtilization(
                organization_id=account.organization_id,
                account_id=account.id,
                savings_plan_id=sp_id,
                plan_type=SavingsPlanType.COMPUTE,  # Assume Compute for aggregate
                hourly_commitment=monthly_commitment / 730,  # Approx hours/month
                monthly_commitment=monthly_commitment,
                utilization_percentage=utilization_pct,
                utilized_commitment=utilized,
                unused_commitment=unused,
                actual_savings=monthly_savings,
                coverage_percentage=coverage_pct,
                on_demand_spend=on_demand_spend,
                is_underutilized=is_underutilized,
                lookback_days=lookback_days
            )
            self.db.add(new_plan)
            self.db.commit()
            self.db.refresh(new_plan)
            return new_plan

    def get_overview(self, user: User) -> Dict[str, Any]:
        """Get Savings Plans health overview for dashboard"""
        plans = self.db.query(SavingsPlanUtilization).filter(
            SavingsPlanUtilization.organization_id == user.organization_id
        ).all()
        
        if not plans:
            return {
                'total_plans': 0,
                'underutilized_count': 0,
                'total_monthly_commitment': 0,
                'wasted_spend_monthly': 0,
                'actual_savings_monthly': 0,
                'avg_coverage_percentage': 0,
                'health_status': 'no_data'
            }
        
        total_commitment = sum(p.monthly_commitment for p in plans)
        total_waste = sum(p.monthly_waste for p in plans)
        total_savings = sum(p.actual_savings for p in plans)
        avg_coverage = sum(p.coverage_percentage for p in plans) / len(plans)
        underutilized = [p for p in plans if p.is_underutilized]
        
        return {
            'total_plans': len(plans),
            'underutilized_count': len(underutilized),
            'total_monthly_commitment': total_commitment,
            'wasted_spend_monthly': total_waste,
            'actual_savings_monthly': total_savings,
            'avg_coverage_percentage': avg_coverage,
            'health_status': self._calculate_health(len(plans), len(underutilized)),
            'top_opportunities': []  # Can be expanded later
        }

    def _calculate_health(self, total: int, underutilized: int) -> str:
        """Calculate overall Savings Plans health"""
        if total == 0:
            return 'no_data'
        ratio = underutilized / total
        if ratio < 0.1:
            return 'healthy'
        elif ratio < 0.25:
            return 'warning'
        else:
            return 'critical'


def get_savings_plan_service(db: Session) -> SavingsPlanService:
    return SavingsPlanService(db)
