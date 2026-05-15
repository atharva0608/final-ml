import logging
from celery_app import celery_app
from sqlalchemy.orm import Session
from backend.core.database import SessionLocal
from backend.models.organization import Organization
from backend.services.tag_compliance_service import TagComplianceService
from backend.services.tag_automation_service import TagAutomationService

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.tag_automation.run_cycle")
def run_tag_automation_cycle():
    """
    Periodic task to run the tag automation cycle for all organizations.
    This will scan resources and compute compliance scores, and then
    evaluate and execute automation rules.
    """
    logger.info("Starting tag automation cycle for all organizations.")
    db: Session = SessionLocal()
    try:
        orgs = db.query(Organization).all()
        for org in orgs:
            logger.info(f"Running tag automation for org: {org.id}")
            # 1. Scan and compute scores for this org's resources
            TagComplianceService.scan_organization(db, org.id)
            
            # 2. Evaluate rules and execute actions on non-compliant resources
            TagAutomationService.evaluate_rules(db, org.id)
            
        logger.info("Completed tag automation cycle.")
    except Exception as e:
        logger.error(f"Error during tag automation cycle: {e}")
        db.rollback()
    finally:
        db.close()
