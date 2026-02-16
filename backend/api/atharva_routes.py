from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.schemas.atharva_schemas import (
    AtharvaStatus, InstanceRanking, Recommendation, RiskEvent, AtharvaSettings,
    NodeTemplate, NodeTemplateCreate, NodeTemplateUpdate,
    PoolRankingsResponse, PoolDetailsResponse,
    BlacklistResponse, BlacklistAddRequest, BlacklistEntry,
    PoolSwitchRequest, PoolSwitchResponse,
    ActivityEvent
)
from backend.services.atharva_service import atharva_service

router = APIRouter(
    prefix="/atharva",
    tags=["atharva-ai"]
)


# ─── Existing Endpoints ──────────────────────────────────────────────────────

@router.get("/status", response_model=AtharvaStatus)
async def get_system_status():
    """Get the overall system status, risk score, and active optimizations."""
    return await atharva_service.get_system_status()

@router.get("/rankings", response_model=InstanceRanking)
async def get_instance_rankings():
    """Get the top ranked instance pools by safety and cost."""
    return await atharva_service.get_instance_rankings()

@router.get("/recommendations", response_model=List[Recommendation])
async def get_recommendations():
    """Get AI-driven recommendations for cost and risk optimization."""
    return await atharva_service.get_recommendations()

@router.get("/risk-history", response_model=List[RiskEvent])
async def get_risk_history():
    """Get a history of risk events and alerts."""
    return await atharva_service.get_risk_history()

@router.post("/settings", response_model=AtharvaSettings)
async def update_settings(settings: AtharvaSettings):
    """Update Atharva AI module settings."""
    return await atharva_service.update_settings(settings)


# ─── Node Templates ──────────────────────────────────────────────────────────

@router.get("/node-templates", response_model=List[NodeTemplate])
async def list_node_templates():
    """List all node templates."""
    return await atharva_service.list_node_templates()

@router.post("/node-templates", response_model=NodeTemplate)
async def create_node_template(data: NodeTemplateCreate):
    """Create a new node template."""
    return await atharva_service.create_node_template(data)

@router.put("/node-templates/{template_id}", response_model=NodeTemplate)
async def update_node_template(template_id: str, data: NodeTemplateUpdate):
    """Update an existing node template."""
    result = await atharva_service.update_node_template(template_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result

@router.delete("/node-templates/{template_id}")
async def delete_node_template(template_id: str):
    """Delete a node template."""
    success = await atharva_service.delete_node_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "deleted", "template_id": template_id}

@router.post("/node-templates/{template_id}/apply", response_model=NodeTemplate)
async def apply_node_template(template_id: str, cluster_id: str = Query(...)):
    """Apply a node template to a cluster."""
    result = await atharva_service.apply_node_template(template_id, cluster_id)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


# ─── Pool Rankings ────────────────────────────────────────────────────────────

@router.get("/pools/rankings", response_model=PoolRankingsResponse)
async def get_pool_rankings(
    cluster_id: str = Query(...),
    template_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50)
):
    """Get ranked pools filtered through the 5-stage pipeline."""
    return await atharva_service.get_pool_rankings(cluster_id, template_id, limit)


# ─── Pool Details ─────────────────────────────────────────────────────────────

@router.get("/pools/{pool_id}/details", response_model=PoolDetailsResponse)
async def get_pool_details(pool_id: str, cluster_id: str = Query(...)):
    """Get detailed information about a specific pool."""
    return await atharva_service.get_pool_details(pool_id, cluster_id)


# ─── Pool Switch ─────────────────────────────────────────────────────────────

@router.post("/pools/switch", response_model=PoolSwitchResponse)
async def switch_pool(req: PoolSwitchRequest):
    """Initiate a pool switch with safety checks."""
    return await atharva_service.switch_pool(req)


# ─── Blacklist ────────────────────────────────────────────────────────────────

@router.get("/blacklist", response_model=BlacklistResponse)
async def get_blacklist(region: Optional[str] = Query(None)):
    """Get currently blacklisted pools."""
    return await atharva_service.get_blacklist(region)

@router.post("/blacklist", response_model=BlacklistEntry)
async def add_to_blacklist(req: BlacklistAddRequest):
    """Add a pool to the global blacklist."""
    return await atharva_service.add_to_blacklist(req)

@router.delete("/blacklist/{pool_id}")
async def remove_from_blacklist(pool_id: str):
    """Remove a pool from the blacklist (admin only)."""
    success = await atharva_service.remove_from_blacklist(pool_id)
    if not success:
        raise HTTPException(status_code=404, detail="Blacklist entry not found")
    return {"status": "removed", "pool_id": pool_id}


# ─── Activity Feed ────────────────────────────────────────────────────────────

@router.get("/activity", response_model=List[ActivityEvent])
async def get_activity(limit: int = Query(5, ge=1, le=20)):
    """Get recent activity events."""
    return await atharva_service.get_activity(limit)
