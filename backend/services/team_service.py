from sqlalchemy.orm import Session
from backend.models.team import Team
from backend.models.user import User, UserRole
from backend.core.exceptions import ForbiddenError, ResourceNotFoundError

class TeamService:
    def __init__(self, db: Session):
        self.db = db

    def get_teams_for_user(self, user: User):
        """
        Org Admin: Sees ALL teams.
        Team Lead: Sees THEIR team only.
        Member: Sees THEIR team only (read-only).
        """
        if user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT:
            return self.db.query(Team).filter(Team.organization_id == user.organization_id).all()
        elif user.role == UserRole.TEAM_LEAD or user.role == UserRole.MEMBER:
            if not user.team_id:
                return []
            return self.db.query(Team).filter(Team.id == user.team_id).all()
        return []

    def rename_team(self, user: User, team_id: str, new_name: str):
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise ResourceNotFoundError("Team", team_id)

        # Authorization: Org Admin OR The Team Lead of THIS team
        is_org_admin = user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT
        is_team_lead = user.role == UserRole.TEAM_LEAD and user.team_id == team_id

        if not (is_org_admin or is_team_lead):
            raise ForbiddenError("Not authorized to rename this team")

        team.name = new_name
        self.db.commit()
        return team

    def create_team(self, user: User, name: str):
        if user.role != UserRole.ORG_ADMIN and user.role != UserRole.CLIENT:
             raise ForbiddenError("Only Admins can create teams")
        
        new_team = Team(name=name, organization_id=user.organization_id)
        self.db.add(new_team)
        self.db.commit()
        return new_team

    def assign_member(self, user: User, member_id: str, team_id: str):
        """
        Assigns an existing user to a team.
        Allowed by: ORG_ADMIN (any team), TEAM_LEAD (their own team only)
        """
        is_org_admin = user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT
        is_team_lead_of_team = user.role == UserRole.TEAM_LEAD and user.team_id == team_id

        if not (is_org_admin or is_team_lead_of_team):
            raise ForbiddenError("Not authorized to assign members to this team")
            
        member = self.db.query(User).filter(User.id == member_id, User.organization_id == user.organization_id).first()
        if not member:
            raise ResourceNotFoundError("Member", member_id)
        
        member.team_id = team_id
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(self, user: User, member_id: str, team_id: str):
        """
        Removes a member from a team (sets team_id to None).
        Allowed by: ORG_ADMIN (any team), TEAM_LEAD (their own team only)
        """
        is_org_admin = user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT
        is_team_lead_of_team = user.role == UserRole.TEAM_LEAD and user.team_id == team_id

        if not (is_org_admin or is_team_lead_of_team):
            raise ForbiddenError("Not authorized to remove members from this team")
            
        member = self.db.query(User).filter(
            User.id == member_id, 
            User.organization_id == user.organization_id,
            User.team_id == team_id
        ).first()

        if not member:
            # Check if member exists at all
            exists = self.db.query(User).filter(User.id == member_id).first()
            if not exists:
                raise ResourceNotFoundError("Member", member_id)
            raise ForbiddenError("Member is not in this team")
        
        member.team_id = None
        self.db.commit()
        self.db.refresh(member)
        return member

    def invite_member(self, user: User, email: str, team_id: str, role: str = "MEMBER"):
        """
        Invites a NEW user to the platform AND assigns them to a team.
        Creates user with PENDING_INVITE status.
        Allowed by: ORG_ADMIN, TEAM_LEAD
        """
        from backend.core.crypto import hash_password
        import uuid
        
        is_org_admin = user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT
        is_team_lead = user.role == UserRole.TEAM_LEAD

        if not (is_org_admin or is_team_lead):
            raise ForbiddenError("Only Admins and Team Leads can invite members")

        # Team Leads can only invite to their own team
        if is_team_lead and user.team_id != team_id:
            raise ForbiddenError("Team Leads can only invite to their own team")

        # Team Leads can only invite MEMBER role, not TEAM_LEAD or higher
        if is_team_lead and role != "MEMBER":
            raise ForbiddenError("Team Leads can only invite members with MEMBER role")

        # Check if user already exists
        existing = self.db.query(User).filter(User.email == email).first()
        if existing:
            raise ForbiddenError(f"User with email {email} already exists")

        # Create new user
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password("demo1234"),  # Default password
            role=UserRole(role) if role in [r.value for r in UserRole] else UserRole.MEMBER,
            organization_id=user.organization_id,
            team_id=team_id,
            status="PENDING_INVITE",
            must_reset_password=True
        )
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user

    def get_team_stats(self, user: User, team_id: str):
        """Get stats for a specific team (Member count, Resources, Cost)"""
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise ResourceNotFoundError("Team", team_id)
            
        # Check permissions
        if user.role != UserRole.ORG_ADMIN and user.role != UserRole.CLIENT:
            if user.team_id != team_id:
                raise ForbiddenError("Not authorized to view stats for this team")

        member_count = self.db.query(User).filter(User.team_id == team_id).count()
        
        # Placeholder for Resources/Cost until resource tagging is implemented
        # In future: Query Instances/Volumes tagged with this team
        resource_count = 0 
        total_cost = 0.0
        
        return {
            "id": team.id,
            "name": team.name,
            "member_count": member_count,
            "resource_count": resource_count, # Mocked for now
            "total_cost": total_cost,         # Mocked for now
            "currency": "USD"
        }

def get_team_service(db: Session):
    return TeamService(db)
