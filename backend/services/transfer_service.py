"""
Data Transfer Analysis Service
Analyzes Data Transfer costs using AWS Cost Explorer
"""
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.transfer_analysis import DataTransferAnalysis
from backend.models.account import Account
from backend.models.user import User
from backend.core.exceptions import AWSError
from backend.core.config import settings


class DataTransferService:
    
    def __init__(self, db: Session):
        self.db = db

    def _get_ce_client(self, account: Account):
        # Using assume role logic
        try:
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
                region_name='us-east-1'
            )
            response = sts_client.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=f"TransferAnalysis-{account.id[:8]}",
                ExternalId=account.external_id
            )
            creds = {
                'aws_access_key_id': response['Credentials']['AccessKeyId'],
                'aws_secret_access_key': response['Credentials']['SecretAccessKey'],
                'aws_session_token': response['Credentials']['SessionToken']
            }
            return boto3.client('ce', **creds, region_name='us-east-1')
        except Exception as e:
            raise AWSError(f"Failed to assume role: {str(e)}")

    def analyze_all(self, user: User) -> Dict[str, Any]:
        accounts = self.db.query(Account).filter(
            Account.organization_id == user.organization_id
        ).all()
        
        results = []
        total_savings = 0.0
        
        for account in accounts:
            try:
                ce = self._get_ce_client(account)
                analysis_items = self.analyze_account_transfer(account, ce)
                for item in analysis_items:
                    results.append(item)
                    total_savings += item.estimated_savings
            except Exception as e:
                print(f"Error analyzing account {account.id}: {e}")
                
        return {
            'items_analyzed': len(results),
            'total_estimated_savings': total_savings,
            'details': results
        }

    def analyze_account_transfer(self, account: Account, ce_client) -> List[DataTransferAnalysis]:
        """Analyze last 30 days transfer costs"""
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        # 1. Get Cost and Usage filtered by Data Transfer
        # Filter: Service = AWS Data Transfer OR Service = AmazonEC2 and UsageType contains 'DataTransfer'
        # GroupBy: UsageType
        
        try:
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': str(start_date), 'End': str(end_date)},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost', 'UsageQuantity'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}],
                Filter={
                    'Dimensions': {
                        'Key': 'SERVICE',
                        'Values': ['AWS Data Transfer', 'Amazon Virtual Private Cloud', 'AmazonEC2']
                    }
                }
            )
        except Exception as e:
            print(f"CE Error: {e}")
            return []

        results = []
        
        # usage map to aggregate similar types
        # e.g. USW2-DataTransfer-Regional-Bytes -> Inter-AZ in USW2
        
        # Simplify for MVP: Look for known high cost patterns
        # NAT Gateway: 'NatGateway-Bytes'
        # Inter-AZ: 'DataTransfer-Regional-Bytes'
        
        for group in response.get('ResultsByTime', [])[0].get('Groups', []):
            usage_type = group['Keys'][0]
            amount = float(group['Metrics']['UnblendedCost']['Amount'])
            quantity = float(group['Metrics']['UsageQuantity']['Amount'])
            
            if amount < 5.0: # Ignore negligible costs
                continue
                
            item = self._interpret_usage(account, usage_type, amount, quantity)
            if item:
                results.append(item)
                
        return results

    def _interpret_usage(self, account, usage_type, cost, quantity) -> Optional[DataTransferAnalysis]:
        rec_type = 'none'
        savings = 0.0
        friendly_type = usage_type
        
        # 1. NAT Gateway Processing
        if 'NatGateway-Bytes' in usage_type:
            friendly_type = 'NAT Gateway Data Processing'
            # Recommendation: Use VPC Endpoints for S3/DynamoDB
            # Assume 40% of NAT traffic is S3/DynamoDB (common pattern)
            # VPC Endpoint is cheaper than NAT Gateway processing ($0.045/GB vs free/low cost)
            savings = cost * 0.4 
            rec_type = 'use_vpc_endpoint'
            
        # 2. Inter-AZ Transfer
        elif 'DataTransfer-Regional-Bytes' in usage_type or 'InterAZ' in usage_type:
            friendly_type = 'Inter-AZ Data Transfer'
            # Recommendation: Consolidate AZs or optimize architecture
            # Hard to estimate savings without deep dive, assume 20%
            savings = cost * 0.2
            rec_type = 'consolidate_az'

        # 3. Inter-Region Transfer
        elif 'DataTransfer-Region-Bytes' in usage_type:
            friendly_type = 'Inter-Region Data Transfer'
            
        else:
            return None # Skip other types for now
            
        # Upsert
        return self._upsert_record(
            account, friendly_type, quantity, cost, rec_type, savings
        )

    def _upsert_record(self, account, transfer_type, gb, cost, rec_type, savings):
        existing = self.db.query(DataTransferAnalysis).filter(
            and_(
                DataTransferAnalysis.account_id == account.id,
                DataTransferAnalysis.transfer_type == transfer_type
            )
        ).first()
        
        if existing:
            existing.total_bytes_gb = gb
            existing.monthly_cost = cost
            existing.recommendation_type = rec_type
            existing.estimated_savings = savings
            existing.last_analyzed_at = datetime.utcnow()
            self.db.commit()
            return existing
        else:
            new_rec = DataTransferAnalysis(
                organization_id=account.organization_id,
                account_id=account.id,
                region='us-east-1', # Default/Aggregated
                transfer_type=transfer_type,
                total_bytes_gb=gb,
                monthly_cost=cost,
                recommendation_type=rec_type,
                estimated_savings=savings
            )
            self.db.add(new_rec)
            self.db.commit()
            return new_rec

    def get_overview(self, user: User) -> Dict[str, Any]:
        items = self.db.query(DataTransferAnalysis).filter(
            DataTransferAnalysis.organization_id == user.organization_id
        ).all()
        
        total_cost = sum(i.monthly_cost for i in items)
        total_savings = sum(i.estimated_savings for i in items)
        
        return {
            'total_monthly_transfer_cost': total_cost,
            'total_estimated_savings': total_savings,
            'top_opportunities': [
                {
                   'id': i.id,
                   'type': i.transfer_type,
                   'cost': i.monthly_cost,
                   'savings': i.estimated_savings,
                   'recommendation': i.recommendation_type
                }
                for i in sorted(items, key=lambda x: x.estimated_savings, reverse=True)[:5]
                if i.estimated_savings > 0
            ]
        }

def get_transfer_service(db: Session) -> DataTransferService:
    return DataTransferService(db)
