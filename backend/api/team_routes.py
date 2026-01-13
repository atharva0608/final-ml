from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from typing import List
from backend.models.base import get_db
from backend.core.dependencies import get_current_user
from backend.services.team_service import TeamService
from backend.models.user import User

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
