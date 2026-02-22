from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
from backend.models.tag_compliance_score import TagComplianceScore
from backend.services.tag_scoring_service import TagScoringService
# We would import actual AWS resource models here:
# from backend.models.cluster import Cluster
# from backend.models.rds_analysis import RDSInstance
# from backend.models.s3_analysis import S3Bucket

class TagComplianceService:
    """
    Service for running organization-wide compliance scans,
    calculating scores for each resource, and persisting the results.
    """
    
    @staticmethod
    def scan_organization(db: Session, organization_id: str):
        """
        Scan all AWS resources in the organization and calculate 
        their tag compliance scores.
        """
        # In a real implementation we would query the actual resource models.
        # resources = []
        # for cluster in db.query(Cluster).filter_by(organization_id=organization_id).all():
        #     resources.append({
        #         "id": getattr(cluster, "cluster_arn", cluster.id),
        #         "name": cluster.name,
        #         "type": "EKS",
        #         "tags": cluster.tags or {},
        #         "cost": cluster.estimated_cost or 0
        #     })
        # For layout purposes, creating skeleton scanner
        
        pass

    @staticmethod
    def record_score(
        db: Session,
        organization_id: str,
        resource_id: str,
        resource_name: str,
        resource_type: str,
        tags: dict,
        monthly_cost: float = 0.0
    ) -> TagComplianceScore:
        """
        Calculate and persist the compliance score for a single resource.
        """
        score, status = TagScoringService.calculate_score(db, organization_id, resource_type, tags)
        
        # Check if a score record already exists for this resource
        record = db.query(TagComplianceScore).filter_by(
            organization_id=organization_id,
            resource_id=resource_id
        ).first()

        environment = tags.get('environment') or tags.get('Environment')
        team = tags.get('team') or tags.get('Team')

        if not record:
            record = TagComplianceScore(
                organization_id=organization_id,
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type=resource_type,
                environment=environment,
                team=team,
                score=score,
                status=status,
                tags_present=len(tags.keys()) if tags else 0,
                monthly_cost=monthly_cost
            )
            db.add(record)
        else:
            record.score = score
            record.status = status
            record.resource_name = resource_name
            record.environment = environment
            record.team = team
            record.tags_present = len(tags.keys()) if tags else 0
            record.monthly_cost = float(monthly_cost) if monthly_cost else 0.0
            record.scanned_at = datetime.utcnow()

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_compliance_dashboard(db: Session, organization_id: str) -> dict:
        """
        Returns stats for the Compliance Monitor dashboard.
        """
        records = db.query(TagComplianceScore).filter_by(organization_id=organization_id).all()
        
        total = len(records)
        compliant = sum(1 for r in records if r.status in ["compliant", "passing"])
        remediation = sum(1 for r in records if r.status in ["review", "critical", "deletion"])
        cost_at_risk = sum(r.monthly_cost for r in records if r.status in ["review", "critical", "deletion"])

        return {
            "total_analyzed": total,
            "compliant": compliant,
            "needs_remediation": remediation,
            "monthly_cost_at_risk": float(cost_at_risk)
        }
