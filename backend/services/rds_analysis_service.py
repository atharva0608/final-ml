"""
RDS Analysis Service
Analyzes RDS instances for Multi-AZ waste in non-production environments
"""
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.rds_analysis import RDSInstanceAnalysis
from backend.models.account import Account
from backend.models.user import User
from backend.core.exceptions import AWSError
from backend.core.config import settings


class RDSAnalysisService:
    
    NON_PROD_KEYWORDS = ['dev', 'test', 'staging', 'uat', 'qa', 'sandbox', 'demo']
    
    def __init__(self, db: Session):
        self.db = db

    def _get_sts_credentials(self, account: Account) -> Dict[str, str]:
        # Reuse credential logic (should be in a shared utility actually)
        try:
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
                region_name='us-east-1'
            )
            response = sts_client.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=f"RDSAnalysis-{account.id[:8]}",
                ExternalId=account.external_id
            )
            return {
                'aws_access_key_id': response['Credentials']['AccessKeyId'],
                'aws_secret_access_key': response['Credentials']['SecretAccessKey'],
                'aws_session_token': response['Credentials']['SessionToken']
            }
        except Exception as e:
            raise AWSError(f"Failed to assume role: {str(e)}")

    def _get_rds_client(self, account: Account, region: str = 'us-east-1'):
        creds = self._get_sts_credentials(account)
        return boto3.client('rds', **creds, region_name=region)

    def analyze_all(self, user: User) -> Dict[str, Any]:
        accounts = self.db.query(Account).filter(
            Account.organization_id == user.organization_id
        ).all()
        
        results = []
        total_savings = 0.0
        instances_analyzed = 0
        
        for account in accounts:
            try:
                # Need to check all regions or just default? RDS is regional. 
                # For now, default region 'us-east-1'. In prod, loop regions.
                rds = self._get_rds_client(account)
                paginator = rds.get_paginator('describe_db_instances')
                
                for page in paginator.paginate():
                    for db_instance in page['DBInstances']:
                        analysis = self.analyze_instance(account, db_instance)
                        if analysis:
                            results.append(analysis)
                            total_savings += analysis.estimated_savings
                            instances_analyzed += 1
            except Exception as e:
                print(f"Error analyzing account {account.id}: {e}")
                
        return {
            'instances_analyzed': instances_analyzed,
            'total_estimated_savings': total_savings,
            'details': results
        }

    def analyze_instance(self, account: Account, instance: Dict) -> RDSInstanceAnalysis:
        identifier = instance['DBInstanceIdentifier']
        engine = instance['Engine']
        instance_class = instance['DBInstanceClass']
        multi_az = instance['MultiAZ']
        status = instance['DBInstanceStatus']
        az = instance.get('AvailabilityZone', 'us-east-1a')
        region = az[:-1] # approximate
        
        # 1. Detect Environment
        tags = instance.get('TagList', []) # Need separate call usually? describe_db_instances returns it?
        # describe_db_instances usually DOES NOT return tags unless separate call list_tags_for_resource
        # BUT newer API versions might. 
        # Actually, let's assume we might interpret name too.
        
        is_prod = True
        env_tag = 'unknown'
        
        # Check name
        if any(k in identifier.lower() for k in self.NON_PROD_KEYWORDS):
            is_prod = False
            env_tag = 'inferred-name'
            
        # 2. Recommendation Logic
        rec_type = 'none'
        rec_impact = 'none'
        estimated_savings = 0.0
        monthly_cost = self._estimate_cost(engine, instance_class, multi_az, region)
        
        if multi_az and not is_prod:
            rec_type = 'convert_to_single_az'
            rec_impact = 'high'
            # Convert to Single-AZ saves ~50% of instance cost (usually exactly 50% of the Multi-AZ premium)
            # Actually Multi-AZ is 2x Single-AZ. So switching to Single-AZ cuts cost by 50%.
            estimated_savings = monthly_cost * 0.5 
            
        # 3. Upsert
        return self._upsert_record(
            account, identifier, engine, instance_class, multi_az, 
            status, is_prod, env_tag, monthly_cost, estimated_savings, 
            rec_type, rec_impact
        )

    def _estimate_cost(self, engine, instance_class, multi_az, region) -> float:
        # Very rough estimation. Real world would use Pricing API.
        # Mock base rates per hour
        base_rates = {
            'db.t3.micro': 0.017,
            'db.t3.small': 0.034,
            'db.t3.medium': 0.068,
            'db.m5.large': 0.192,
            'db.m5.xlarge': 0.384,
            'db.r5.large': 0.24,
            'db.r5.xlarge': 0.48
        }
        hourly = base_rates.get(instance_class, 0.1) # Default fallback
        if multi_az:
            hourly *= 2
        
        return hourly * 730 # Monthly hours

    def _upsert_record(self, account, identifier, engine, instance_class, multi_az, status, is_prod, env_tag, monthly_cost, savings, rec_type, rec_impact):
        
        existing = self.db.query(RDSInstanceAnalysis).filter(
            and_(
                RDSInstanceAnalysis.account_id == account.id,
                RDSInstanceAnalysis.db_instance_identifier == identifier
            )
        ).first()
        
        if existing:
            existing.engine = engine
            existing.instance_class = instance_class
            existing.multi_az = multi_az
            existing.status = status
            existing.is_production = is_prod
            existing.environment_tag = env_tag
            existing.current_monthly_cost = monthly_cost
            existing.estimated_savings = savings
            existing.recommendation_type = rec_type
            existing.recommendation_impact = rec_impact
            existing.last_analyzed_at = datetime.utcnow()
            self.db.commit()
            return existing
        else:
            new_rec = RDSInstanceAnalysis(
                organization_id=account.organization_id,
                account_id=account.id,
                db_instance_identifier=identifier,
                engine=engine,
                instance_class=instance_class,
                multi_az=multi_az,
                status=status,
                is_production=is_prod,
                environment_tag=env_tag,
                current_monthly_cost=monthly_cost,
                estimated_savings=savings,
                recommendation_type=rec_type,
                recommendation_impact=rec_impact
            )
            self.db.add(new_rec)
            self.db.commit()
            return new_rec

    def get_overview(self, user: User) -> Dict[str, Any]:
        instances = self.db.query(RDSInstanceAnalysis).filter(
            RDSInstanceAnalysis.organization_id == user.organization_id
        ).all()
        
        total_instances = len(instances)
        multi_az_non_prod = len([i for i in instances if i.recommendation_type == 'convert_to_single_az'])
        total_savings = sum(i.estimated_savings for i in instances)
        
        return {
            'total_instances': total_instances,
            'multi_az_non_prod_count': multi_az_non_prod,
            'total_estimated_savings': total_savings,
            'top_opportunities': [
                {
                   'id': i.id,
                   'identifier': i.db_instance_identifier,
                   'savings': i.estimated_savings,
                   'engine': i.engine
                }
                for i in sorted(instances, key=lambda x: x.estimated_savings, reverse=True)[:5]
                if i.estimated_savings > 0
            ]
        }

def get_rds_analysis_service(db: Session) -> RDSAnalysisService:
    return RDSAnalysisService(db)
