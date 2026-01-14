from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from backend.models.base import get_db
from backend.core.dependencies import get_current_user
from backend.services.team_service import TeamService
from backend.models.user import User, UserRole
from backend.models.team import Team

from backend.schemas.team_schemas import TeamResponse, TeamMemberResponse

router = APIRouter(prefix="/teams", tags=["Teams"])

def get_service(db: Session = Depends(get_db)):
    return TeamService(db)

@router.get("/", response_model=List[TeamResponse])
def get_teams(service: TeamService = Depends(get_service), user: User = Depends(get_current_user)):
    return service.get_teams_for_user(user)

@router.post("/")
def create_team(name: str = Body(..., embed=True), service: TeamService = Depends(get_service), user: User = Depends(get_current_user)):
    return service.create_team(user, name)

@router.put("/{team_id}/rename")
def rename_team(team_id: str, name: str = Body(..., embed=True), service: TeamService = Depends(get_service), user: User = Depends(get_current_user)):
    return service.rename_team(user, team_id, name)

@router.post("/{team_id}/assign")
def assign_member(team_id: str, member_id: str = Body(..., embed=True), service: TeamService = Depends(get_service), user: User = Depends(get_current_user)):
    return service.assign_member(user, member_id, team_id)

@router.post("/{team_id}/invite")
def invite_member(team_id: str, email: str = Body(...), role: str = Body("MEMBER"), service: TeamService = Depends(get_service), user: User = Depends(get_current_user)):
    """Invite a new user to the platform and assign to this team"""
    return service.invite_member(user, email, team_id, role)

@router.get("/{team_id}")
def get_team(team_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get a specific team's details including governance config"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    
    # Authorization: Must be in same org
    if team.organization_id != user.organization_id:
        raise HTTPException(403, "Not authorized to view this team")
    
    return {
        "id": team.id,
        "name": team.name,
        "governance_config": team.governance_config or {},
        "created_at": team.created_at
    }

@router.put("/{team_id}/governance")
def update_team_governance(
    team_id: str,
    config: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Update team-specific governance rules.
    Team Leads can configure which actions require their approval for members.
    
    Example config: {"CONNECT_ACCOUNT": true, "TERMINATE_INSTANCE": true}
    """
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    
    # Authorization: Only Team Lead of THIS team or Org Admin can update
    is_authorized = (
        (user.role == UserRole.ORG_ADMIN and user.organization_id == team.organization_id) or
        (user.role == UserRole.TEAM_LEAD and user.team_id == team_id)
    )
    
    if not is_authorized:
        raise HTTPException(403, "Not authorized to change team governance rules")
    
    # Update the config
    team.governance_config = config
    db.commit()
    db.refresh(team)
    
    return {"status": "success", "governance_config": team.governance_config}


@router.get("/{team_id}/stats")
def get_team_stats(team_id: str, service: TeamService = Depends(get_service), user: User = Depends(get_current_user)):
    """Get statistics for a specific team (Member count, resources, cost)"""
    return service.get_team_stats(user, team_id)
