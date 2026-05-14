"""
websocket_manager.py - Real-time WebSocket connections.

Provides:
- Live session updates
- Real-time transform progress
- Collaborative editing awareness
- Notification delivery
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from utils.logger import logger


class EventType(str, Enum):
    SESSION_UPDATE = "session_update"
    TRANSFORM_PROGRESS = "transform_progress"
    TRANSFORM_COMPLETE = "transform_complete"
    VERSION_CREATED = "version_created"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    PIPELINE_STATUS = "pipeline_status"
    NOTIFICATION = "notification"
    PRESENCE = "presence"


@dataclass
class ConnectionInfo:
    websocket: WebSocket
    user_id: str
    session_id: Optional[str] = None
    connected_at: float = field(default_factory=time.time)
    is_active: bool = True


class WebSocketManager:
    """
    Manages WebSocket connections for real-time features.

    Usage:
        ws_manager = WebSocketManager()

        # In connection handler:
        await ws_manager.connect(websocket, user_id, session_id)

        # Broadcast to session:
        await ws_manager.broadcast_to_session(session_id, event)

        # Send to specific user:
        await ws_manager.send_to_user(user_id, event)
    """

    def __init__(self):
        self._connections: Dict[
            str, List[ConnectionInfo]
        ] = {}  # user_id -> [connections]
        self._session_connections: Dict[str, Set[str]] = {}  # session_id -> {user_ids}
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, user_id: str, session_id: Optional[str] = None
    ) -> None:
        """Accept a WebSocket connection."""
        await websocket.accept()

        conn = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
        )

        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(conn)

            if session_id:
                if session_id not in self._session_connections:
                    self._session_connections[session_id] = set()
                self._session_connections[session_id].add(user_id)

        await self._broadcast_user_joined(user_id, session_id)

        logger.info(f"WebSocket connected: user={user_id} session={session_id}")

    async def disconnect(
        self, websocket: WebSocket, user_id: str, session_id: Optional[str] = None
    ) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id] = [
                    c for c in self._connections[user_id] if c.websocket != websocket
                ]
                if not self._connections[user_id]:
                    del self._connections[user_id]

            if session_id and session_id in self._session_connections:
                self._session_connections[session_id].discard(user_id)
                if not self._session_connections[session_id]:
                    del self._session_connections[session_id]

        await self._broadcast_user_left(user_id, session_id)

        logger.info(f"WebSocket disconnected: user={user_id} session={session_id}")

    async def broadcast_to_session(
        self, session_id: str, event: Dict[str, Any], exclude_user: Optional[str] = None
    ) -> None:
        """Broadcast an event to all users viewing a session."""
        user_ids = self._session_connections.get(session_id, set())

        for user_id in user_ids:
            if exclude_user and user_id == exclude_user:
                continue
            await self.send_to_user(user_id, event)

    async def send_to_user(self, user_id: str, event: Dict[str, Any]) -> None:
        """Send an event to a specific user."""
        connections = self._connections.get(user_id, [])

        disconnected = []

        for conn in connections:
            if conn.is_active:
                try:
                    await conn.websocket.send_json(event)
                except Exception as e:
                    logger.warning(f"Failed to send to {user_id}: {e}")
                    conn.is_active = False
                    disconnected.append(conn)

        for conn in disconnected:
            await self.disconnect(conn.websocket, user_id, conn.session_id)

    async def _broadcast_user_joined(
        self, user_id: str, session_id: Optional[str]
    ) -> None:
        """Notify others when a user joins a session."""
        if not session_id:
            return

        await self.broadcast_to_session(
            session_id,
            {
                "type": EventType.USER_JOINED.value,
                "user_id": user_id,
                "timestamp": time.time(),
            },
            exclude_user=user_id,
        )

    async def _broadcast_user_left(
        self, user_id: str, session_id: Optional[str]
    ) -> None:
        """Notify others when a user leaves a session."""
        if not session_id:
            return

        await self.broadcast_to_session(
            session_id,
            {
                "type": EventType.USER_LEFT.value,
                "user_id": user_id,
                "timestamp": time.time(),
            },
        )

    async def notify_transform_progress(
        self,
        session_id: str,
        action: str,
        progress: float,
        rows_done: int,
        total_rows: int,
    ) -> None:
        """Send transform progress update."""
        event = {
            "type": EventType.TRANSFORM_PROGRESS.value,
            "session_id": session_id,
            "action": action,
            "progress": progress,
            "rows_done": rows_done,
            "total_rows": total_rows,
            "timestamp": time.time(),
        }
        await self.broadcast_to_session(session_id, event)

    async def notify_transform_complete(
        self,
        session_id: str,
        action: str,
        new_version: int,
        rows: int,
        columns: List[str],
    ) -> None:
        """Send transform completion event."""
        event = {
            "type": EventType.TRANSFORM_COMPLETE.value,
            "session_id": session_id,
            "action": action,
            "new_version": new_version,
            "rows": rows,
            "columns": columns,
            "timestamp": time.time(),
        }
        await self.broadcast_to_session(session_id, event)

    async def notify_session_update(
        self, session_id: str, update_type: str, data: Dict[str, Any]
    ) -> None:
        """Send general session update."""
        event = {
            "type": EventType.SESSION_UPDATE.value,
            "session_id": session_id,
            "update_type": update_type,
            "data": data,
            "timestamp": time.time(),
        }
        await self.broadcast_to_session(session_id, event)

    async def send_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        notification_type: str = "info",
        action_url: Optional[str] = None,
    ) -> None:
        """Send a notification to a user."""
        event = {
            "type": EventType.NOTIFICATION.value,
            "title": title,
            "message": message,
            "notification_type": notification_type,
            "action_url": action_url,
            "timestamp": time.time(),
        }
        await self.send_to_user(user_id, event)

    def get_active_users(self, session_id: str) -> List[str]:
        """Get list of active users in a session."""
        return list(self._session_connections.get(session_id, set()))

    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return sum(len(conns) for conns in self._connections.values())


ws_manager = WebSocketManager()
