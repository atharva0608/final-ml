"""
WebSocket API Routes

Real-time log streaming for Sandbox Mode.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db
# from database.models import SandboxSession  # Not yet implemented
from websocket.manager import manager

router = APIRouter()


@router.websocket("/ws/sandbox/{session_id}")
async def websocket_sandbox_logs(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time sandbox session logs

    Streams logs and status updates for a specific sandbox session.

    Args:
        websocket: WebSocket connection
        session_id: Sandbox session ID to subscribe to
        db: Database session

    Example (JavaScript):
        const ws = new WebSocket('ws://localhost:8000/api/v1/ws/sandbox/{session_id}');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log(data.type, data.message);
        };
    """
    # Verify session exists
    # TODO: Implement SandboxSession model
    # session = db.query(SandboxSession).filter(
    #     SandboxSession.session_id == session_id
    # ).first()
    #
    # if not session:
    #     await websocket.close(code=4004, reason="Session not found")
    #     return

    # Connect to WebSocket manager
    await manager.connect(websocket, session_id)

    # Send welcome message
    await manager.send_personal_message({
        "type": "connected",
        "message": f"Connected to sandbox session {session_id}",
        "session_id": session_id
    }, websocket)

    try:
        # Keep connection alive and listen for client messages
        while True:
            data = await websocket.receive_text()

            # Echo received data (for ping/pong)
            if data == "ping":
                await manager.send_personal_message({"type": "pong"}, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        print(f"Client disconnected from session {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, session_id)
