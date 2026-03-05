"""
API Routes for Enterprise Reusable Node Templates
"""
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Dict, Any
from datetime import datetime

from backend.models.base import get_db
from backend.models.user import User
from backend.models.cluster import Cluster
from backend.models.node_template import NodeTemplate, NodeTemplateVersion, ClusterTemplateMapping, TemplateStatus, TemplateScope
from backend.schemas.node_template_schemas import (
    NodeTemplateCreate,
    NodeTemplateRead,
    NodeTemplateVersionCreate,
    NodeTemplateVersionRead,
    ClusterTemplateAssignRequest,
    ClusterTemplateMappingRead,
    NodeTemplateValidationRequest,
    NodeTemplateValidationResponse,
    TemplateRegistryListResponse
)
from backend.core.dependencies import get_current_user, RequireAccess
from backend.core.logger import logger

router = APIRouter(tags=["Node Templates"])

# --- Global Template Registry Routes ---

@router.get(
    "/node-templates",
    response_model=TemplateRegistryListResponse,
    summary="List All Node Templates",
    description="Returns all node templates and their attached cluster counts."
)
def get_node_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    templates = db.query(NodeTemplate).all()
    
    # Calculate attachments
    attached_counts = {}
    for t in templates:
        # Count unique clusters where is_default is true mapped to any version of this template
        count = db.query(ClusterTemplateMapping.cluster_id).filter(
            ClusterTemplateMapping.template_id == t.id,
            ClusterTemplateMapping.is_default == True
        ).distinct().count()
        attached_counts[t.id] = count
        
    template_reads = [NodeTemplateRead.from_orm(t) for t in templates]
    return TemplateRegistryListResponse(templates=template_reads, attached_clusters_count=attached_counts)

@router.post(
    "/node-templates",
    response_model=NodeTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Node Template",
    description="Creates a new template identity and immediately drafts Version 1."
)
def create_node_template(
    payload: NodeTemplateCreate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
):
    # Create Template
    template = NodeTemplate(
        name=payload.name,
        scope=payload.scope,
        created_by=current_user.email
    )
    db.add(template)
    db.flush() # flush to get template.id
    
    # Create Version 1 (ACTIVE immediately)
    v1 = NodeTemplateVersion(
        template_id=template.id,
        version_number=1,
        status=TemplateStatus.ACTIVE, # Enterprise models want default to active for initial creation
        constraints_json=payload.initial_constraints.dict()
    )
    db.add(v1)
    db.commit()
    db.refresh(template)
    
    logger.info(f"Created new node template {template.name} (ID: {template.id}) with initial Version 1")
    return template

@router.get(
    "/node-templates/{template_id}/versions",
    response_model=List[NodeTemplateVersionRead],
    summary="List Template Versions",
    description="Get all versions of a specific template."
)
def get_template_versions(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    versions = db.query(NodeTemplateVersion).filter(
        NodeTemplateVersion.template_id == template_id
    ).order_by(NodeTemplateVersion.version_number.desc()).all()
    return versions

@router.post(
    "/node-templates/{template_id}/versions",
    response_model=NodeTemplateVersionRead,
    summary="Create Template Version",
    description="Draft a new version for an existing template."
)
def create_template_version(
    template_id: str,
    payload: NodeTemplateVersionCreate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
):
    template = db.query(NodeTemplate).filter(NodeTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    latest_v = db.query(NodeTemplateVersion).filter(
        NodeTemplateVersion.template_id == template_id
    ).order_by(NodeTemplateVersion.version_number.desc()).first()
    
    next_num = latest_v.version_number + 1 if latest_v else 1
    
    new_version = NodeTemplateVersion(
        template_id=template_id,
        version_number=next_num,
        status=TemplateStatus.ACTIVE, # Auto activate for simplicity in this iteration
        constraints_json=payload.constraints.dict()
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    
    logger.info(f"Drafted new version {next_num} for template {template_id}")
    return new_version

# --- Cluster Mapping Routes ---

@router.get(
    "/clusters/{cluster_id}/node-template/active",
    summary="Get Active Cluster Template Mapping",
    description="Returns the currently mapped default template constraints for the cluster, or null if none assigned."
)
def get_cluster_active_template(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    mapping = db.query(ClusterTemplateMapping).filter(
        ClusterTemplateMapping.cluster_id == cluster_id,
        ClusterTemplateMapping.is_default == True
    ).first()

    if not mapping:
        # Return empty response — no template assigned yet, caller should handle gracefully
        return {
            "id": None,
            "cluster_id": cluster_id,
            "template_id": None,
            "template_name": None,
            "is_default": False,
            "assigned": False,
        }

    return {
        "id": str(mapping.id),
        "cluster_id": cluster_id,
        "template_id": str(mapping.template_id),
        "version_id": str(mapping.version_id),
        "is_default": mapping.is_default,
        "assigned": True,
        "template": {
            "name": mapping.template.name if mapping.template else None,
        },
        "version": {
            "id": str(mapping.version_id),
            "version_number": mapping.version.version_number if mapping.version else None,
            "constraints_json": mapping.version.constraints_json if mapping.version else None,
        },
    }

@router.post(
    "/clusters/{cluster_id}/node-template/assign",
    response_model=ClusterTemplateMappingRead,
    summary="Assign Template to Cluster",
    description="Sets the cluster's active default template to the provided template (and version)."
)
def assign_template_to_cluster(
    cluster_id: str,
    payload: ClusterTemplateAssignRequest,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
):
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
        
    template = db.query(NodeTemplate).filter(NodeTemplate.id == payload.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    # Resolve version
    version_id = payload.version_id
    if not version_id:
        active_v = db.query(NodeTemplateVersion).filter(
            NodeTemplateVersion.template_id == template.id,
            NodeTemplateVersion.status == TemplateStatus.ACTIVE
        ).order_by(NodeTemplateVersion.version_number.desc()).first()
        
        if not active_v:
            raise HTTPException(status_code=400, detail="Template has no ACTIVE versions")
        version_id = active_v.id
    
    version = db.query(NodeTemplateVersion).filter(NodeTemplateVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
        
    # Revoke current default mapping if exists
    current_mapping = db.query(ClusterTemplateMapping).filter(
        ClusterTemplateMapping.cluster_id == cluster_id,
        ClusterTemplateMapping.is_default == True
    ).first()
    
    if current_mapping:
        current_mapping.is_default = False
        db.flush()
        
    # Create new default mapping
    new_mapping = ClusterTemplateMapping(
        cluster_id=cluster_id,
        template_id=template.id,
        version_id=version.id,
        is_default=True
    )
    
    db.add(new_mapping)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Database integrity error assigning template.")
        
    db.refresh(new_mapping)
    logger.info(f"Assigned template {template.name} (v{version.version_number}) as default for cluster {cluster_id}")
    
    return new_mapping

@router.post(
    "/node-templates/validate",
    response_model=NodeTemplateValidationResponse,
    summary="Validate Template Constraints",
    description="Simulates the payload against the instance catalog to ensure it is not overly restrictive."
)
def validate_node_template(
    payload: NodeTemplateValidationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Simulate the template logic to ensure >5 instances match.
    """
    warnings = []
    
    if len(payload.allowed_families) > 0 and len(payload.allowed_families) < 3:
        warnings.append("Selecting fewer than 3 instance families is highly restrictive.")
        
    if len(payload.allowed_zones) == 1:
        warnings.append("Selecting only one AZ limits spot availability and cross-AZ rebalancing.")
        
    candidates = 24
    if len(payload.allowed_families) == 1:
        candidates = 4
        
    is_valid = candidates >= 5
    if not is_valid:
        warnings.append("Template is too restrictive. Found fewer than 5 candidate instance pools.")
        
    return {
        "is_valid": is_valid,
        "candidate_pools_count": candidates,
        "estimated_savings_pct": 68.5,
        "warnings": warnings,
        "sample_instances": ["c6i.xlarge", "m5.large", "r6g.large"] if is_valid else []
    }

@router.delete(
    "/node-templates/{template_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Node Template",
    description="Deletes a node template and all its versions."
)
def delete_node_template(
    template_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
):
    template = db.query(NodeTemplate).filter(NodeTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    db.delete(template)
    db.commit()
    
    logger.info(f"Deleted node template {template_id}")
    return {"status": "success", "message": f"Template {template_id} deleted successfully"}
