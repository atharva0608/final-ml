"""
Agent Registration Router

Handles agent registration, heartbeats, and deregistration.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import os

from ..models.base import get_db
from ..models.cluster import Cluster, ClusterStatus
from ..models.account import Account
import uuid

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
logger = logging.getLogger(__name__)

# N3 fix: Expected agent version — log warning on mismatch during registration.
EXPECTED_AGENT_VERSION = "1.1.6"

# BUG-10 fix: Agent endpoint authentication.
# AGENT_API_KEY is the same value as the agent's API_KEY env var.
# The agent already sends Authorization: Bearer {API_KEY} on all HTTP calls.
AGENT_API_KEY = os.getenv("AGENT_API_KEY")


def verify_agent_token(authorization: Optional[str] = Header(None)):
    """Validate the agent's Bearer token against AGENT_API_KEY."""
    if not AGENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AGENT_API_KEY not configured on backend",
        )
    if authorization != f"Bearer {AGENT_API_KEY}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent token",
        )


@router.get("/discover-url")
async def discover_url():
    """
    Return the current backend public URL.
    
    No authentication required — agents call this on startup and periodically
    to discover the correct backend URL when tunnel URLs change (ngrok,
    Cloudflare Tunnel, etc.).  Returns the live URL from Redis (set by
    the CORS middleware on every incoming request) with fallback to env var.
    """
    from backend.core.redis_client import get_backend_public_url
    url = get_backend_public_url()
    ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
    return {"backend_url": url, "ws_base_url": ws_url}


@router.post("/register")
async def register_agent(
    payload: Dict[str, Any],
    _: None = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """
    Register an agent with the backend.

    Called by agents when they start up to announce their presence.
    Updates cluster heartbeat timestamp.
    """
    try:
        cluster_id = payload.get("cluster_id")
        agent_id = payload.get("agent_id")
        capabilities = payload.get("capabilities", [])
        version = payload.get("version")

        # N3 fix: Warn on agent version mismatch (don't reject — just flag)
        if version and version != EXPECTED_AGENT_VERSION:
            logger.warning(
                f"Agent {agent_id} on cluster {cluster_id} registered with version "
                f"{version}, expected {EXPECTED_AGENT_VERSION} — protocol mismatch possible"
            )

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Get or create cluster
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

        if not cluster:
            # Auto-create cluster when agent registers
            cluster_name = payload.get("cluster_name", f"cluster-{cluster_id[:8]}")
            region = payload.get("region", "unknown")

            # Try to find an existing account to associate with, or create a default one
            # Get the first account or create a default one
            account = db.query(Account).first()
            if not account:
                # Create a default account if none exists
                from ..models.organization import Organization
                org = db.query(Organization).first()
                if not org:
                    logger.error("No organization found to create cluster")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="No organization configured. Please set up your organization first."
                    )

                account = Account(
                    id=str(uuid.uuid4()),
                    account_name=f"Auto-discovered account for {cluster_id[:8]}",
                    organization_id=org.id,
                    role_arn=None,  # P-C19 fix: no placeholder ARN — operator must configure real credentials
                    external_id=None,
                    is_validated="N",  # Not validated — requires operator to set up proper IAM role
                    created_at=datetime.utcnow()
                )
                db.add(account)
                db.flush()

            # Create the cluster
            cluster = Cluster(
                id=cluster_id,
                account_id=account.id,
                name=cluster_name,
                region=region,
                status=ClusterStatus.ACTIVE,
                agent_installed="Y",
                last_heartbeat=datetime.utcnow(),
                created_at=datetime.utcnow()
            )
            db.add(cluster)
            logger.info(f"Auto-created cluster: {cluster_id} ({cluster_name}) in {region}")
        else:
            # Update existing cluster heartbeat
            cluster.last_heartbeat = datetime.utcnow()
            cluster.agent_installed = "Y"
            cluster.status = ClusterStatus.ACTIVE

        db.commit()

        logger.info(f"Agent registered: cluster={cluster_id}, agent={agent_id}, version={version}")

        # Include the current backend public URL so the agent can self-correct
        from backend.core.redis_client import get_backend_public_url
        _current_url = get_backend_public_url()

        return {
            "success": True,
            "message": "Agent registered successfully",
            "cluster_id": cluster_id,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "backend_url": _current_url,
            "ws_url": _current_url.replace("https://", "wss://").replace("http://", "ws://"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering agent: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register agent: {str(e)}"
        )


# N5 fix: Agent-side action heartbeat endpoint.
# The agent calls this every 30s while executing an action so the backend
# knows the action is still alive even if the Celery worker's heartbeat loop
# is lagging or dead. Prevents false mass-rollbacks on Celery stall.
@router.post("/actions/{action_id}/heartbeat")
async def action_heartbeat(action_id: str, _: None = Depends(verify_agent_token)):
    """Refresh action_heartbeat:{id} in Redis. Called by agent every 30s during execution."""
    try:
        from backend.core.redis_client import get_redis_client
        import time
        _redis = get_redis_client()
        _redis.setex(f"action_heartbeat:{action_id}", 120, str(time.time()))
        return {"ok": True}
    except Exception as e:
        logger.warning(f"action_heartbeat update failed for {action_id}: {e}")
        return {"ok": False}


# BUG-1 fix: HTTP fallback endpoint for action results.
# When WebSocket is down, the agent POSTs action results here directly.
@router.post("/actions/{action_id}/result")
async def action_result(action_id: str, payload: Dict[str, Any], _: None = Depends(verify_agent_token), db: Session = Depends(get_db)):
    """Receive action result via HTTP fallback when WebSocket is unavailable."""
    try:
        from backend.models.agent_action import AgentAction, AgentActionStatus
        agent_action = db.query(AgentAction).filter(AgentAction.id == action_id).first()
        if not agent_action:
            raise HTTPException(status_code=404, detail=f"AgentAction {action_id} not found")
        # Derive status: prefer explicit 'status' field, fall back to 'success' boolean
        if "status" in payload:
            _raw_status = payload["status"].upper()
        else:
            _raw_status = "COMPLETED" if payload.get("success", False) else "FAILED"
        _status_map = {s.value: s for s in AgentActionStatus}
        _status = _status_map.get(_raw_status, AgentActionStatus.COMPLETED)
        agent_action.status = _status
        agent_action.result = payload.get("result")
        agent_action.error_message = payload.get("error")
        agent_action.completed_at = datetime.utcnow()

        # Post-processing: update cluster state based on action type
        from backend.models.agent_action import AgentActionType
        if _status == AgentActionStatus.COMPLETED:
            if agent_action.action_type == AgentActionType.INSTALL_KARPENTER:
                from backend.models.cluster import Cluster, KarpenterMode
                _cluster = db.query(Cluster).filter(Cluster.id == agent_action.cluster_id).first()
                if _cluster and _cluster.karpenter_mode is None:
                    _cluster.karpenter_mode = KarpenterMode.AUTO
                    logger.info(f"Set karpenter_mode=AUTO for cluster {agent_action.cluster_id}")
            elif agent_action.action_type == AgentActionType.UNINSTALL_KARPENTER:
                from backend.models.cluster import Cluster, KarpenterMode
                _cluster = db.query(Cluster).filter(Cluster.id == agent_action.cluster_id).first()
                if _cluster:
                    _cluster.karpenter_mode = None
                    logger.info(f"Cleared karpenter_mode for cluster {agent_action.cluster_id}")

        db.commit()
        # Clear heartbeat key so the rebalancer picks it up immediately
        try:
            from backend.core.redis_client import get_redis_client
            get_redis_client().delete(f"action_heartbeat:{action_id}")
        except Exception:
            pass
        logger.info(f"Action {action_id} result received via HTTP fallback: {_status}")
        return {"ok": True, "action_id": action_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"action_result HTTP fallback failed for {action_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deregister")
async def deregister_agent(
    payload: Dict[str, Any],
    _: None = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """
    Deregister an agent from the backend.

    Called by agents when they shut down gracefully.
    """
    try:
        cluster_id = payload.get("cluster_id")
        agent_id = payload.get("agent_id")

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        logger.info(f"Agent deregistered: cluster={cluster_id}, agent={agent_id}")

        return {
            "success": True,
            "message": "Agent deregistered successfully",
            "cluster_id": cluster_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deregistering agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deregister agent: {str(e)}"
        )


@router.post("/heartbeat")
async def agent_heartbeat(
    payload: Dict[str, Any],
    _: None = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """
    Receive heartbeat from an agent.

    Agents send periodic heartbeats to indicate they're still alive.
    """
    try:
        cluster_id = payload.get("cluster_id")
        agent_id = payload.get("agent_id")
        health = payload.get("health", {})

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Update cluster heartbeat
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if cluster:
            cluster.last_heartbeat = datetime.utcnow()
            # Always ensure ACTIVE + agent_installed=Y on every heartbeat.
            # Previous conditional logic left clusters stuck in DISCOVERED state.
            cluster.agent_installed = 'Y'
            cluster.status = ClusterStatus.ACTIVE

            # ── Live Karpenter detection from agent ──
            # The agent checks for actual Karpenter pods on every heartbeat
            # and reports the status. We update Redis + DB accordingly.
            karpenter_status = payload.get("karpenter_status")
            _karp_live_detected = False
            _karp_was_installed = cluster.karpenter_mode is not None
            if karpenter_status and isinstance(karpenter_status, dict):
                _karp_live_detected = karpenter_status.get("detected", False)
                try:
                    from backend.core.redis_client import get_redis_client
                    import json as _hb_json
                    _hb_redis = get_redis_client()
                    if _hb_redis:
                        # Store live karpenter status from agent (5 min TTL — survives missed heartbeat cycles)
                        _live_key = f"karpenter:live_status:{cluster_id}"
                        _hb_redis.setex(_live_key, 300, _hb_json.dumps(karpenter_status))

                        # Update the detection cache to reflect live state
                        _det_key = f"karpenter:detected:{cluster_id}"
                        _inst_key = f"spot:karpenter:installed:{cluster_id}"

                        if _karp_live_detected:
                            # Karpenter is running — refresh installed keys
                            _mode = cluster.karpenter_mode.value if cluster.karpenter_mode else 'auto'
                            _det_result = {
                                'detected': True,
                                'cluster_id': cluster_id,
                                'karpenter_mode': _mode,
                                'source': 'agent_heartbeat',
                            }
                            _hb_redis.setex(_det_key, 600, _hb_json.dumps(_det_result))
                            _hb_redis.setex(_inst_key, 3600, _mode)
                            # Auto-set karpenter_mode if not already set
                            if cluster.karpenter_mode is None:
                                from backend.models.cluster import KarpenterMode
                                cluster.karpenter_mode = KarpenterMode.AUTO
                                logger.info(f"Auto-detected Karpenter on cluster {cluster_id}, set mode=AUTO")
                        else:
                            # Karpenter NOT running — if it was previously installed,
                            # mark as missing so UI can show reinstall prompt
                            if _karp_was_installed:
                                _det_result = {
                                    'detected': False,
                                    'cluster_id': cluster_id,
                                    'karpenter_mode': 'missing',
                                    'previously_installed': True,
                                    'source': 'agent_heartbeat',
                                    'error': karpenter_status.get('error'),
                                }
                                _hb_redis.setex(_det_key, 600, _hb_json.dumps(_det_result))
                                _hb_redis.delete(_inst_key)
                except Exception as _karp_err:
                    logger.debug(f"Karpenter heartbeat status update error: {_karp_err}")

            db.commit()

        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
        # Best-effort: try to commit just the heartbeat timestamp even if Karpenter logic failed
        try:
            db.rollback()
            cluster = db.query(Cluster).filter(Cluster.id == payload.get("cluster_id")).first()
            if cluster:
                cluster.last_heartbeat = datetime.utcnow()
                cluster.agent_installed = 'Y'
                cluster.status = ClusterStatus.ACTIVE
                db.commit()
                logger.info(f"Heartbeat fallback commit succeeded for {payload.get('cluster_id')}")
                return {"success": True, "timestamp": datetime.utcnow().isoformat(), "partial": True}
        except Exception as fallback_err:
            logger.error(f"Heartbeat fallback commit also failed: {fallback_err}")
            try:
                db.rollback()
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process heartbeat: {str(e)}"
        )
