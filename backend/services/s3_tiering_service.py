"""
S3 Tiering Analysis Service
Analyzes S3 buckets for storage class optimization opportunities
"""
import boto3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.s3_analysis import S3BucketAnalysis
from backend.models.account import Account
from backend.models.user import User
from backend.core.exceptions import AWSError
from backend.core.config import settings


class S3TieringService:
    """Service for S3 intelligent tiering and cost analysis"""
    
    # Cost constants (us-east-1 approx)
    COST_STANDARD = 0.023
    COST_IA = 0.0125
    COST_GLACIER = 0.004
    COST_DEEP = 0.00099
    COST_INT_TIERING_MONITORING = 0.0025 / 1000  # Per object
    
    def __init__(self, db: Session):
        self.db = db

    def _get_sts_credentials(self, account: Account) -> Dict[str, str]:
        """Assume role to get credentials"""
        try:
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
                region_name='us-east-1'
            )
            
            response = sts_client.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=f"S3Audit-{account.id[:8]}",
                ExternalId=account.external_id
            )
            
            return {
                'aws_access_key_id': response['Credentials']['AccessKeyId'],
                'aws_secret_access_key': response['Credentials']['SecretAccessKey'],
                'aws_session_token': response['Credentials']['SessionToken']
            }
        except Exception as e:
            raise AWSError(f"Failed to assume role: {str(e)}")

    def _get_s3_client(self, account: Account, region: str = 'us-east-1'):
        creds = self._get_sts_credentials(account)
        return boto3.client('s3', **creds, region_name=region)

    def _get_cw_client(self, account: Account, region: str = 'us-east-1'):
        creds = self._get_sts_credentials(account)
        return boto3.client('cloudwatch', **creds, region_name=region)

    def analyze_all_buckets(self, user: User) -> Dict[str, Any]:
        """Analyze all buckets across all accounts"""
        accounts = self.db.query(Account).filter(
            Account.organization_id == user.organization_id
        ).all()
        
        results = []
        total_savings = 0.0
        buckets_analyzed = 0
        
        for account in accounts:
            try:
                # S3 is global, so one client is enough to list buckets
                s3 = self._get_s3_client(account)
                buckets = s3.list_buckets().get('Buckets', [])
                
                for bucket in buckets:
                    analysis = self.analyze_bucket(account, bucket['Name'], s3)
                    if analysis:
                        results.append(analysis)
                        total_savings += analysis.estimated_savings
                        buckets_analyzed += 1
                        
            except Exception as e:
                print(f"Error analyzing account {account.id}: {e}")
                
        return {
            'buckets_analyzed': buckets_analyzed,
            'total_estimated_savings': total_savings,
            'details': results
        }

    def analyze_bucket(self, account: Account, bucket_name: str, s3_client=None) -> Optional[S3BucketAnalysis]:
        """Analyze a single bucket"""
        if not s3_client:
            s3_client = self._get_s3_client(account)
            
        try:
            # 1. Get Bucket Region
            loc = s3_client.get_bucket_location(Bucket=bucket_name)
            region = loc['LocationConstraint'] or 'us-east-1'
            
            # 2. Get Lifecycle Policy
            has_lifecycle = False
            try:
                s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                has_lifecycle = True
            except:
                pass

            # 3. Get Storage Metrics from CloudWatch (Standard, IA, etc)
            cw = self._get_cw_client(account, region)
            storage_stats = self._get_storage_metrics(cw, bucket_name)
            
            # 4. Calculate Financials
            totals = self._calculate_costs(storage_stats)
            
            # 5. Generate Recommendation
            rec = self._generate_recommendation(
                totals, 
                has_lifecycle, 
                bucket_name
            )
            
            # 6. Upsert Database Record
            return self._upsert_analysis(
                account, 
                bucket_name, 
                region, 
                storage_stats, 
                totals, 
                rec, 
                has_lifecycle
            )
            
        except Exception as e:
            print(f"Failed to analyze bucket {bucket_name}: {e}")
            return None

    def _get_storage_metrics(self, cw_client, bucket_name: str) -> Dict[str, float]:
        """Get storage size by storage class from CloudWatch"""
        # Note: This is a simplified implementation. Real-world would loop through storage types.
        # CloudWatch metrics: BucketSizeBytes filtered by StorageType
        storage_types = [
            'StandardStorage', 'StandardIAStorage', 
            'GlacierStorage', 'DeepArchiveStorage', 
            'IntelligentTieringFAStorage'
        ]
        
        stats = {
            'size_standard': 0.0,
            'size_ia': 0.0,
            'size_glacier': 0.0,
            'size_deep': 0.0,
            'size_intelligent': 0.0,
            'object_count': 0
        }
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=2) # Metrics are daily
        
        # Helper to get metric
        def get_metric(metric_name, storage_type=None):
            dims = [{'Name': 'BucketName', 'Value': bucket_name}]
            if storage_type:
                dims.append({'Name': 'StorageType', 'Value': storage_type})
                
            res = cw_client.get_metric_statistics(
                Namespace='AWS/S3',
                MetricName=metric_name,
                Dimensions=dims,
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Average']
            )
            if res['Datapoints']:
                return res['Datapoints'][-1]['Average']
            return 0.0

        stats['size_standard'] = get_metric('BucketSizeBytes', 'StandardStorage')
        stats['size_ia'] = get_metric('BucketSizeBytes', 'StandardIAStorage')
        stats['size_glacier'] = get_metric('BucketSizeBytes', 'GlacierStorage')
        stats['size_deep'] = get_metric('BucketSizeBytes', 'DeepArchiveStorage')
        stats['size_intelligent'] = get_metric('BucketSizeBytes', 'IntelligentTieringFAStorage')
        stats['object_count'] = int(get_metric('NumberOfObjects', 'AllStorageTypes'))
        
        return stats

    def _calculate_costs(self, stats: Dict) -> Dict:
        """Calculate current cost and totals"""
        gb_standard = stats['size_standard'] / (1024**3)
        gb_ia = stats['size_ia'] / (1024**3)
        gb_glacier = stats['size_glacier'] / (1024**3)
        gb_deep = stats['size_deep'] / (1024**3)
        gb_int = stats['size_intelligent'] / (1024**3)
        
        total_cost = (
            gb_standard * self.COST_STANDARD +
            gb_ia * self.COST_IA +
            gb_glacier * self.COST_GLACIER +
            gb_deep * self.COST_DEEP +
            gb_int * self.COST_IA # Approx
        )
        
        total_bytes = sum([stats[k] for k in stats if k.startswith('size_')])
        
        return {
            'monthly_cost': total_cost,
            'total_size_bytes': total_bytes
        }

    def _generate_recommendation(
        self, 
        totals: Dict, 
        has_lifecycle: bool, 
        bucket_name: str
    ) -> Dict:
        """Generate savings recommendation"""
        monthly_cost = totals['monthly_cost']
        
        # Simple heuristic: If mostly Standard and no lifecycle -> Recommend Intelligent Tiering
        if not has_lifecycle and monthly_cost > 10: # Only optimize if spend > $10
            # Assume 80% savings with Int Tiering/Glacier
            savings = monthly_cost * 0.6 
            return {
                'type': 'enable_intelligent_tiering',
                'title': 'Enable Intelligent-Tiering',
                'description': 'Bucket has significant Standard storage with no lifecycle policy.',
                'estimated_savings': savings,
                'priority': 'high' if savings > 50 else 'medium'
            }
        
        return {
            'type': 'none',
            'title': 'Optimized',
            'description': 'No significant savings opportunities found.',
            'estimated_savings': 0,
            'priority': 'low'
        }

    def _upsert_analysis(
        self, 
        account: Account, 
        bucket_name: str, 
        region: str,
        stats: Dict, 
        totals: Dict, 
        rec: Dict,
        has_lifecycle: bool
    ) -> S3BucketAnalysis:
        
        existing = self.db.query(S3BucketAnalysis).filter(
            and_(
                S3BucketAnalysis.account_id == account.id,
                S3BucketAnalysis.bucket_name == bucket_name
            )
        ).first()
        
        if existing:
            existing.total_size_bytes = totals['total_size_bytes']
            existing.object_count = stats['object_count']
            existing.size_standard = stats['size_standard']
            existing.size_ia = stats['size_ia']
            existing.size_glacier = stats['size_glacier']
            existing.monthly_cost = totals['monthly_cost']
            existing.estimated_savings = rec['estimated_savings']
            existing.recommendation_type = rec['type']
            existing.recommendation_detail = rec
            existing.has_lifecycle_policy = has_lifecycle
            existing.last_analyzed_at = datetime.utcnow()
            self.db.commit()
            return existing
        else:
            new_record = S3BucketAnalysis(
                organization_id=account.organization_id,
                account_id=account.id,
                bucket_name=bucket_name,
                region=region,
                total_size_bytes=totals['total_size_bytes'],
                object_count=stats['object_count'],
                size_standard=stats['size_standard'],
                size_ia=stats['size_ia'],
                size_glacier=stats['size_glacier'],
                monthly_cost=totals['monthly_cost'],
                estimated_savings=rec['estimated_savings'],
                recommendation_type=rec['type'],
                recommendation_detail=rec,
                has_lifecycle_policy=has_lifecycle
            )
            self.db.add(new_record)
            self.db.commit()
            return new_record

    def get_overview(self, user: User) -> Dict[str, Any]:
        """Get S3 optimization overview"""
        buckets = self.db.query(S3BucketAnalysis).filter(
            S3BucketAnalysis.organization_id == user.organization_id
        ).all()
        
        total_buckets = len(buckets)
        buckets_with_savings = [b for b in buckets if b.estimated_savings > 1.0]
        total_savings = sum(b.estimated_savings for b in buckets)
        no_lifecycle_count = len([b for b in buckets if not b.has_lifecycle_policy])
        
        return {
            'total_buckets': total_buckets,
            'buckets_needs_optimization': len(buckets_with_savings),
            'total_estimated_savings': total_savings,
            'buckets_no_lifecycle': no_lifecycle_count,
            'top_opportunities': self._get_top_opportunities(buckets)
        }

    def _get_top_opportunities(self, buckets: List[S3BucketAnalysis], limit: int = 5) -> List[Dict]:
        sorted_buckets = sorted(buckets, key=lambda x: x.estimated_savings, reverse=True)
        return [
            {
                'id': b.id,
                'bucket_name': b.bucket_name,
                'monthly_cost': b.monthly_cost,
                'estimated_savings': b.estimated_savings,
                'recommendation': b.recommendation_type
            }
            for b in sorted_buckets[:limit]
            if b.estimated_savings > 0
        ]

def get_s3_tiering_service(db: Session) -> S3TieringService:
    return S3TieringService(db)
