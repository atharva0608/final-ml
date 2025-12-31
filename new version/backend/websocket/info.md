# Backend WebSocket Module

## Purpose

Real-time communication layer for live updates and notifications.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM

---

## Files

### manager.py
**Purpose**: WebSocket connection management and message broadcasting
**Lines**: ~130
**Key Classes**:
- `ConnectionManager` - Manages active WebSocket connections
- Handles connection lifecycle (connect, disconnect, broadcast)

**Capabilities**:
- **Connection Management**: Track active client connections
- **Broadcasting**: Send messages to all connected clients
- **Targeted Messaging**: Send to specific users/sessions
- **Connection Pooling**: Efficient connection handling

**Key Methods**:
- `connect(websocket, client_id)` - Accept new connection
- `disconnect(client_id)` - Remove connection
- `broadcast(message)` - Send to all clients
- `send_to_client(client_id, message)` - Send to specific client

**Use Cases**:
- Real-time dashboard updates (instance status changes)
- Discovery progress notifications
- Live cost updates
- Alert notifications

**Dependencies**:
- FastAPI WebSocket support
- asyncio (for async operations)

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: ConnectionManager

---

## WebSocket Flow

```
Client Connects
   ↓
[Authenticate] (JWT token)
   ↓
[Register Connection] (manager.py)
   ↓
[Keep Connection Alive]
   ↓
   ├─ Receive Messages from Client
   │    ↓
   │  [Process & Respond]
   │
   └─ Server-Side Events
        ↓
      [Broadcast to Client(s)]
```

---

## Message Format

### Client → Server
```json
{
  "type": "subscribe",
  "channel": "instance_status",
  "filters": {
    "account_id": "12345"
  }
}
```

### Server → Client
```json
{
  "type": "update",
  "channel": "instance_status",
  "data": {
    "instance_id": "i-1234567890abcdef0",
    "status": "running",
    "timestamp": "2025-12-25T10:30:00Z"
  }
}
```

---

## Real-Time Events

### Instance Events
- Instance state changes (pending → running → stopped)
- Discovery completion
- Health check updates

### Account Events
- Account connection status
- Discovery progress
- AWS credential validation

### Notification Events
- Cost alerts
- Security findings
- Optimization recommendations

---

## Dependencies

### Depends On:
- FastAPI WebSocket
- asyncio
- backend/auth/ (for authentication)
- backend/database/models.py

### Depended By:
- Frontend real-time components
- Dashboard live updates
- Notification system

**Impact Radius**: MEDIUM (affects real-time UX)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing WebSocket functionality
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Server-Side (FastAPI)
```python
from backend.websocket.manager import ConnectionManager
from fastapi import WebSocket

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Client {client_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(client_id)
```

### Client-Side (Frontend)
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/user123');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};

ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'instance_status'
}));
```

---

## Connection Management

### Connection Limits
- Max connections per user: Configurable (default: 5)
- Connection timeout: 5 minutes of inactivity
- Reconnection: Client auto-reconnect with exponential backoff

### Authentication
- Connections authenticated via JWT token
- Token passed in query parameter or header
- Invalid/expired tokens rejected

---

## Known Issues

### None

WebSocket module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM - Real-time communication_
