"""
Sandbox API Endpoints

FastAPI router for sandbox session management, providing safe testing
environment with real AWS operations but isolated data.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from uuid import UUID
import secrets
import bcrypt

# NOTE: Database integration would go here
# For now, using in-memory store for demo purposes
SANDBOX_SESSIONS = {}

router = APIRouter()


# Request/Response Models
class CreateSessionRequest(BaseModel):
    instance_id: str = Field(..., description="Target EC2 instance ID")
    instance_type: str = Field(..., description="Instance type (e.g., c5.large)")
    availability_zone: str = Field(..., description="Availability zone")
    aws_access_key: str = Field(..., description="AWS Access Key ID")
    aws_secret_key: str = Field(..., description="AWS Secret Access Key")
    aws_region: str = Field(default="ap-south-1", description="AWS Region")
    ttl_hours: int = Field(default=2, description="Session TTL in hours")


class CreateSessionResponse(BaseModel):
    session_id: str
    temp_username: str
    temp_password: str
    expires_at: datetime
    dashboard_url: str


class SessionDetailsResponse(BaseModel):
    session_id: str
    is_active: bool
    expires_at: datetime
    target_instance_id: str
    target_instance_type: str
    target_availability_zone: str
    created_at: datetime
    time_remaining_minutes: int


class EvaluateResponse(BaseModel):
    decision: str
    reason: str
    crash_probability: Optional[float]
    aws_signal: str
    projected_hourly_savings: Optional[float]
    action_taken: Optional[str]


class ActionLog(BaseModel):
    timestamp: datetime
    action_type: str
    status: str
    details: dict


class SavingsReport(BaseModel):
    cumulative_savings: float
    hourly_breakdown: List[dict]


# Endpoints
@router.post("/sessions", response_model=CreateSessionResponse)
async def create_sandbox_session(request: CreateSessionRequest):
    """
    Create new sandbox session with temporary credentials

    This endpoint:
    1. Generates temporary username/password
    2. Encrypts AWS credentials
    3. Creates session with 2-hour TTL
    4. Returns access credentials
    """
    # Generate temporary credentials
    session_id = secrets.token_urlsafe(16)
    temp_username = f"sandbox_user_{secrets.randbelow(9999):04d}"
    temp_password = secrets.token_urlsafe(16)
    temp_password_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

    # Calculate expiration
    expires_at = datetime.now() + timedelta(hours=request.ttl_hours)

    # Store session (in-memory for demo, should use database)
    from backend.utils.crypto import encrypt_credential

    SANDBOX_SESSIONS[session_id] = {
        "session_id": session_id,
        "temp_username": temp_username,
        "temp_password_hash": temp_password_hash,
        "aws_access_key_encrypted": encrypt_credential(request.aws_access_key),
        "aws_secret_key_encrypted": encrypt_credential(request.aws_secret_key),
        "aws_region": request.aws_region,
        "target_instance_id": request.instance_id,
        "target_instance_type": request.instance_type,
        "target_availability_zone": request.availability_zone,
        "created_at": datetime.now(),
        "expires_at": expires_at,
        "is_active": True,
    }

    return CreateSessionResponse(
        session_id=session_id,
        temp_username=temp_username,
        temp_password=temp_password,  # Only returned once!
        expires_at=expires_at,
        dashboard_url=f"/sandbox/{session_id}"
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailsResponse)
async def get_sandbox_session(session_id: str):
    """Get sandbox session details"""
    if session_id not in SANDBOX_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    session = SANDBOX_SESSIONS[session_id]

    # Calculate time remaining
    time_remaining = (session["expires_at"] - datetime.now()).total_seconds() / 60

    return SessionDetailsResponse(
        session_id=session["session_id"],
        is_active=session["is_active"],
        expires_at=session["expires_at"],
        target_instance_id=session["target_instance_id"],
        target_instance_type=session["target_instance_type"],
        target_availability_zone=session["target_availability_zone"],
        created_at=session["created_at"],
        time_remaining_minutes=int(time_remaining)
    )


@router.post("/sessions/{session_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_instance_sandbox(session_id: str):
    """
    Evaluate instance in sandbox mode

    This uses SandboxActuator for blue/green switching with real AWS calls
    """
    if session_id not in SANDBOX_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    session = SANDBOX_SESSIONS[session_id]

    # Check if session is expired
    if datetime.now() > session["expires_at"]:
        raise HTTPException(status_code=410, detail="Session expired")

    # TODO: Execute decision pipeline with SandboxActuator
    # For now, return mock response
    return EvaluateResponse(
        decision="SWITCH",
        reason="Better spot pool found with lower crash probability",
        crash_probability=0.28,
        aws_signal="NONE",
        projected_hourly_savings=0.06,
        action_taken="Blue/Green switch initiated"
    )


@router.get("/sessions/{session_id}/actions", response_model=List[ActionLog])
async def get_session_actions(session_id: str):
    """Get action log for sandbox session"""
    if session_id not in SANDBOX_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    # TODO: Query sandbox_actions table
    # For now, return mock data
    return [
        ActionLog(
            timestamp=datetime.now(),
            action_type="MONITORING",
            status="SUCCESS",
            details={"message": "Monitoring started"}
        )
    ]


@router.get("/sessions/{session_id}/savings", response_model=SavingsReport)
async def get_session_savings(session_id: str):
    """Get savings report for sandbox session"""
    if session_id not in SANDBOX_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    # TODO: Query sandbox_savings table
    # For now, return mock data
    return SavingsReport(
        cumulative_savings=0.24,
        hourly_breakdown=[
            {
                "timestamp": datetime.now().isoformat(),
                "spot_price": 0.04,
                "on_demand_price": 0.10,
                "savings": 0.06
            }
        ]
    )


@router.delete("/sessions/{session_id}")
async def end_sandbox_session(session_id: str):
    """Manually end sandbox session (triggers cleanup)"""
    if session_id not in SANDBOX_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    session = SANDBOX_SESSIONS[session_id]
    session["is_active"] = False

    # TODO: Trigger cleanup (stop spot instances, restart original)

    return {
        "message": "Session ended, cleanup initiated",
        "original_instance_id": session["target_instance_id"]
    }
