"""
Reserved Instance Analysis Service
Integrates with AWS Cost Explorer to detect RI waste and provide recommendations
"""
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.ri_utilization import RIUtilization, RIOfferingClass, RIScope
from backend.models.account import Account
from backend.models.user import User
from backend.core.exceptions import ResourceNotFoundError, AWSError
from backend.core.config import settings


class RIAnalysisService:
    """Service for analyzing Reserved Instance utilization and waste"""
    
    # Utilization thresholds
    UNDERUTILIZATION_THRESHOLD = 70.0  # Below 70% = underutilized
    UNUSED_DAYS_THRESHOLD = 14  # 14+ days at 0% = completely unused
    
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
                RoleSessionName=f"RIAnalysis-{account.id[:8]}",
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
            region_name='us-east-1'  # CE is global, always us-east-1
        )

    def analyze_all_accounts(self, user: User) -> Dict[str, Any]:
        """Analyze RI utilization across all accounts in user's organization"""
        accounts = self.db.query(Account).filter(
            Account.organization_id == user.organization_id
        ).all()
        
        total_ris = 0
        total_waste = 0.0
        underutilized_count = 0
        results = []
        
        for account in accounts:
            try:
                account_analysis = self.analyze_account(account)
                results.append(account_analysis)
                total_ris += account_analysis['total_ris']
                total_waste += account_analysis['total_waste']
                underutilized_count += account_analysis['underutilized_count']
            except Exception as e:
                results.append({
                    'account_id': account.id,
                    'aws_account_id': account.aws_account_id,
                    'error': str(e)
                })
        
        return {
            'total_ris': total_ris,
            'underutilized_count': underutilized_count,
            'total_monthly_waste': total_waste,
            'total_annual_waste': total_waste * 12,
            'accounts_analyzed': len(results),
            'accounts': results
        }

    def analyze_account(self, account: Account, analysis_days: int = 30) -> Dict[str, Any]:
        """Analyze RI utilization for a specific account"""
        try:
            ce_client = self._get_ce_client(account)
            
            # Calculate date range
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=analysis_days)
            
            # Get RI utilization from Cost Explorer
            response = ce_client.get_reservation_utilization(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SUBSCRIPTION_ID'}
                ],
                Granularity='MONTHLY'
            )
            
            # Process results
            ris = []
            total_waste = 0.0
            underutilized_count = 0
            
            for group in response.get('UtilizationsByTime', []):
                for ri_group in group.get('Groups', []):
                    ri_data = self._process_ri_group(
                        ri_group, 
                        account, 
                        analysis_days
                    )
                    ris.append(ri_data)
                    
                    if ri_data['is_underutilized']:
                        underutilized_count += 1
                        total_waste += ri_data['monthly_waste']
                    
                    # Store in database
                    self._upsert_ri_utilization(ri_data, account)
            
            return {
                'account_id': account.id,
                'aws_account_id': account.aws_account_id,
                'total_ris': len(ris),
                'underutilized_count': underutilized_count,
                'total_waste': total_waste,
                'ris': ris
            }
            
        except Exception as e:
            raise AWSError(f"Failed to analyze account {account.aws_account_id}: {str(e)}")

    def _process_ri_group(self, ri_group: Dict, account: Account, analysis_days: int) -> Dict[str, Any]:
        """Process a single RI group from Cost Explorer response"""
        utilization = ri_group.get('Utilization', {})
        
        # Extract metrics
        utilized_hours = float(utilization.get('PurchasedHours', 0)) * float(utilization.get('UtilizationPercentage', 0)) / 100
        total_hours = float(utilization.get('PurchasedHours', 0))
        utilization_pct = float(utilization.get('UtilizationPercentage', 0))
        
        # Calculate costs
        total_actual_cost = float(utilization.get('TotalActualHours', 0)) * float(utilization.get('OnDemandCostOfRIHoursUsed', 0))
        amortized_cost = float(utilization.get('AmortizedRecurringFee', 0)) + float(utilization.get('AmortizedUpfrontFee', 0))
        
        # Calculate waste
        unused_percentage = 100 - utilization_pct
        monthly_commitment = amortized_cost / (analysis_days / 30)
        monthly_waste = monthly_commitment * (unused_percentage / 100)
        
        # Determine recommendation
        recommendation = self._generate_recommendation(utilization_pct, monthly_waste)
        
        return {
            'reservation_id': ri_group.get('Keys', ['unknown'])[0],
            'utilization_percentage': utilization_pct,
            'utilized_hours': utilized_hours,
            'total_hours': total_hours,
            'monthly_cost': monthly_commitment,
            'monthly_waste': monthly_waste,
            'annual_waste': monthly_waste * 12,
            'is_underutilized': utilization_pct < self.UNDERUTILIZATION_THRESHOLD,
            'is_unused': utilization_pct == 0,
            'recommendation': recommendation
        }

    def _generate_recommendation(self, utilization_pct: float, monthly_waste: float) -> Dict[str, Any]:
        """Generate actionable recommendation based on RI utilization"""
        if utilization_pct == 0:
            return {
                'type': 'sell',
                'priority': 'critical',
                'title': 'Reserved Instance Not Used',
                'description': 'This RI has 0% utilization. Sell on RI Marketplace to recover value.',
                'actions': [
                    {'action': 'sell_marketplace', 'label': 'Sell on RI Marketplace', 'recovery_estimate': 0.6},
                    {'action': 'modify', 'label': 'Modify Instance Type'},
                    {'action': 'share', 'label': 'Share with Linked Account'}
                ],
                'monthly_impact': monthly_waste
            }
        elif utilization_pct < 40:
            return {
                'type': 'review',
                'priority': 'high',
                'title': 'Severely Underutilized RI',
                'description': f'Only {utilization_pct:.1f}% utilized. Consider selling or consolidating workloads.',
                'actions': [
                    {'action': 'analyze_workload', 'label': 'Analyze Workload Pattern'},
                    {'action': 'modify', 'label': 'Modify to Match Usage'},
                    {'action': 'sell_marketplace', 'label': 'Sell on Marketplace'}
                ],
                'monthly_impact': monthly_waste
            }
        elif utilization_pct < 70:
            return {
                'type': 'optimize',
                'priority': 'medium',
                'title': 'Underutilized RI',
                'description': f'{utilization_pct:.1f}% utilized. Consider consolidating workloads or modifying RI.',
                'actions': [
                    {'action': 'consolidate', 'label': 'Consolidate Workloads'},
                    {'action': 'convert', 'label': 'Convert to Savings Plan'},
                    {'action': 'monitor', 'label': 'Continue Monitoring'}
                ],
                'monthly_impact': monthly_waste
            }
        else:
            return {
                'type': 'keep',
                'priority': 'low',
                'title': 'RI Well Utilized',
                'description': f'Good utilization at {utilization_pct:.1f}%. No action needed.',
                'actions': [
                    {'action': 'monitor', 'label': 'Continue Monitoring'}
                ],
                'monthly_impact': 0
            }

    def _upsert_ri_utilization(self, ri_data: Dict, account: Account) -> RIUtilization:
        """Create or update RI utilization record in database"""
        existing = self.db.query(RIUtilization).filter(
            and_(
                RIUtilization.account_id == account.id,
                RIUtilization.reservation_id == ri_data['reservation_id']
            )
        ).first()
        
        if existing:
            # Update existing record
            existing.utilization_percentage = ri_data['utilization_percentage']
            existing.utilized_hours = ri_data['utilized_hours']
            existing.total_hours = ri_data['total_hours']
            existing.monthly_cost = ri_data['monthly_cost']
            existing.monthly_waste = ri_data['monthly_waste']
            existing.annual_waste = ri_data['annual_waste']
            existing.recommendation_type = ri_data['recommendation']['type']
            existing.recommendation_detail = ri_data['recommendation']
            existing.last_analyzed_at = datetime.utcnow()
            self.db.commit()
            return existing
        else:
            # Create new record
            new_ri = RIUtilization(
                organization_id=account.organization_id,
                account_id=account.id,
                reservation_id=ri_data['reservation_id'],
                utilization_percentage=ri_data['utilization_percentage'],
                utilized_hours=ri_data['utilized_hours'],
                total_hours=ri_data['total_hours'],
                monthly_cost=ri_data['monthly_cost'],
                monthly_waste=ri_data['monthly_waste'],
                annual_waste=ri_data['annual_waste'],
                recommendation_type=ri_data['recommendation']['type'],
                recommendation_detail=ri_data['recommendation'],
                instance_type='unknown',  # Will be populated from detailed RI info
                region='us-east-1'  # Default, will be updated
            )
            self.db.add(new_ri)
            self.db.commit()
            self.db.refresh(new_ri)
            return new_ri

    def get_ri_overview(self, user: User) -> Dict[str, Any]:
        """Get RI health overview for dashboard"""
        ris = self.db.query(RIUtilization).filter(
            RIUtilization.organization_id == user.organization_id
        ).all()
        
        if not ris:
            return {
                'total_ris': 0,
                'underutilized_count': 0,
                'underutilized_percentage': 0,
                'wasted_spend_monthly': 0,
                'wasted_spend_annual': 0,
                'health_status': 'no_data'
            }
        
        total = len(ris)
        underutilized = [ri for ri in ris if ri.is_underutilized]
        unused = [ri for ri in ris if ri.is_unused]
        
        total_waste = sum(ri.monthly_waste for ri in ris)
        
        return {
            'total_ris': total,
            'underutilized_count': len(underutilized),
            'unused_count': len(unused),
            'underutilized_percentage': (len(underutilized) / total) * 100,
            'wasted_spend_monthly': total_waste,
            'wasted_spend_annual': total_waste * 12,
            'health_status': self._calculate_health_status(total, len(underutilized)),
            'top_opportunities': self._get_top_opportunities(ris)
        }

    def _calculate_health_status(self, total: int, underutilized: int) -> str:
        """Calculate overall RI health status"""
        if total == 0:
            return 'no_data'
        ratio = underutilized / total
        if ratio < 0.1:
            return 'healthy'
        elif ratio < 0.25:
            return 'warning'
        else:
            return 'critical'

    def _get_top_opportunities(self, ris: List[RIUtilization], limit: int = 5) -> List[Dict]:
        """Get top waste reduction opportunities"""
        sorted_ris = sorted(ris, key=lambda x: x.monthly_waste, reverse=True)
        return [
            {
                'id': ri.id,
                'reservation_id': ri.reservation_id,
                'instance_type': ri.instance_type,
                'utilization': ri.utilization_percentage,
                'monthly_waste': ri.monthly_waste,
                'recommendation': ri.recommendation_type
            }
            for ri in sorted_ris[:limit]
            if ri.monthly_waste > 0
        ]

    def get_ri_list(self, user: User, filters: Optional[Dict] = None) -> List[Dict]:
        """Get list of all RIs with utilization data"""
        query = self.db.query(RIUtilization).filter(
            RIUtilization.organization_id == user.organization_id
        )
        
        if filters:
            if filters.get('underutilized_only'):
                query = query.filter(RIUtilization.utilization_percentage < self.UNDERUTILIZATION_THRESHOLD)
            if filters.get('account_id'):
                query = query.filter(RIUtilization.account_id == filters['account_id'])
        
        ris = query.order_by(RIUtilization.monthly_waste.desc()).all()
        
        return [
            {
                'id': ri.id,
                'reservation_id': ri.reservation_id,
                'instance_type': ri.instance_type,
                'region': ri.region,
                'utilization_percentage': ri.utilization_percentage,
                'monthly_cost': ri.monthly_cost,
                'monthly_waste': ri.monthly_waste,
                'expires_at': ri.end_date.isoformat() if ri.end_date else None,
                'days_remaining': ri.days_remaining,
                'risk_level': ri.risk_level,
                'recommendation': ri.recommendation_detail,
                'last_analyzed': ri.last_analyzed_at.isoformat()
            }
            for ri in ris
        ]

    def get_ri_recommendations(self, user: User, ri_id: str) -> Dict[str, Any]:
        """Get detailed recommendations for a specific RI"""
        ri = self.db.query(RIUtilization).filter(
            and_(
                RIUtilization.id == ri_id,
                RIUtilization.organization_id == user.organization_id
            )
        ).first()
        
        if not ri:
            raise ResourceNotFoundError("RIUtilization", ri_id)
        
        return {
            'ri': {
                'id': ri.id,
                'reservation_id': ri.reservation_id,
                'instance_type': ri.instance_type,
                'region': ri.region,
                'utilization_percentage': ri.utilization_percentage,
                'monthly_cost': ri.monthly_cost,
                'monthly_waste': ri.monthly_waste
            },
            'recommendation': ri.recommendation_detail,
            'alternatives': self._generate_alternatives(ri)
        }

    def _generate_alternatives(self, ri: RIUtilization) -> List[Dict]:
        """Generate alternative options for underutilized RI"""
        alternatives = []
        
        if ri.offering_class == RIOfferingClass.CONVERTIBLE:
            alternatives.append({
                'type': 'convert_savings_plan',
                'title': 'Convert to Compute Savings Plan',
                'description': 'More flexible, covers all instance families and regions',
                'estimated_savings': ri.monthly_waste * 0.8
            })
        
        if ri.utilization_percentage == 0:
            alternatives.append({
                'type': 'sell_marketplace',
                'title': 'Sell on RI Marketplace',
                'description': 'Recover approximately 60% of remaining value',
                'estimated_recovery': ri.monthly_cost * ri.days_remaining / 30 * 0.6
            })
        
        alternatives.append({
            'type': 'on_demand',
            'title': 'Switch to On-Demand',
            'description': f'Only pay for {ri.utilization_percentage:.0f}% usage',
            'estimated_savings': ri.monthly_waste
        })
        
        return alternatives


def get_ri_analysis_service(db: Session) -> RIAnalysisService:
    return RIAnalysisService(db)
