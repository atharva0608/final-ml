"""
Server-Sent Events (SSE) Manager
Broadcasts permission changes to connected clients in real-time
"""
import asyncio
import json
from typing import Dict, Set
from fastapi import Request
from datetime import datetime

class SSEManager:
    def __init__(self):
        # Store active SSE connections: {user_id: set of queue objects}
        self.connections: Dict[str, Set[asyncio.Queue]] = {}
    
    def add_client(self, user_id: str, queue: asyncio.Queue):
        """Add a new SSE client connection"""
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(queue)
        print(f"[SSE] Client connected: {user_id}, total: {len(self.connections[user_id])}")
    
    def remove_client(self, user_id: str, queue: asyncio.Queue):
        """Remove an SSE client connection"""
        if user_id in self.connections:
            self.connections[user_id].discard(queue)
            if not self.connections[user_id]:
                del self.connections[user_id]
            print(f"[SSE] Client disconnected: {user_id}")
    
    async def broadcast_to_user(self, user_id: str, event: str, data: dict):
        """Send event to all connections for a specific user"""
        if user_id not in self.connections:
            return
        
        message = {
            "event": event,
            "data": data,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Send to all connections for this user
        disconnected = set()
        for queue in self.connections[user_id]:
            try:
                await queue.put(json.dumps(message))
            except:
                disconnected.add(queue)
        
        # Clean up disconnected clients
        for queue in disconnected:
            self.remove_client(user_id, queue)
        
        print(f"[SSE] Broadcasted {event} to {user_id}: {data}")

# Global SSE manager instance
sse_manager = SSEManager()
