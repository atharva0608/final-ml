from celery import shared_task
import logging
from backend.models.base import get_db
from backend.services.cluster_service import ClusterService
from backend.services.agent_injector import AgentInjectorService
from backend.models.cluster import Cluster
from backend.models.account import Account
from backend.workers import app

logger = logging.getLogger(__name__)

@app.task(bind=True, name="workers.agent.inject_agent")
def inject_agent_task(self, cluster_id: str):
    """
    Background task to inject agent into a cluster.
    """
    logger.info(f"[WORK-AGENT] Starting background agent injection for cluster {cluster_id}")
    
    db = next(get_db())
    try:
        # Get cluster
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(f"[WORK-AGENT] Cluster {cluster_id} not found")
            return {"status": "error", "message": "Cluster not found"}
            
        # Get account
        account = db.query(Account).filter(Account.id == cluster.account_id).first()
        if not account:
            logger.error(f"[WORK-AGENT] Account for cluster {cluster_id} not found")
            return {"status": "error", "message": "Account not found"}
            
        # Inject agent
        injector = AgentInjectorService(db)
        
        result = injector.inject_agent(
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            cluster_arn=cluster.arn or "",
            cluster_endpoint=cluster.endpoint or str(cluster.endpoint),
            cluster_ca_data=cluster.ca_data or "",
            role_arn=account.role_arn,
            external_id=account.external_id or "",
            region=cluster.region,
            api_key=cluster.api_key
        )
        
        if result["status"] == "success":
            logger.info(f"[WORK-AGENT] Successfully injected agent into {cluster.name}")
            cluster.agent_installed = "Y" # Correcting from True to "Y" based on model definition
            cluster.status = "ACTIVE" # Using string enum value or ClusterStatus.ACTIVE
            db.commit()
        else:
            logger.error(f"[WORK-AGENT] Failed to inject agent: {result['message']}")
            
        return result
        
    except Exception as e:
        logger.error(f"[WORK-AGENT] Exception during agent injection: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
