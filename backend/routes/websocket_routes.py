"""
websocket_routes.py - WebSocket endpoints for real-time features.

WS /ws/{session_id}  - Real-time session updates
WS /ws/notifications   - User notifications
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import HTMLResponse

from services.websocket_manager import ws_manager, EventType
from utils.auth import verify_token
from utils.logger import logger

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_session(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time session collaboration.

    Client connects with: ws://host/ws/{session_id}?token={jwt}

    Events sent by server:
      - user_joined: User started viewing the session
      - user_left: User stopped viewing the session
      - transform_progress: Transform operation progress
      - transform_complete: Transform operation finished
      - session_update: General session update
    """
    user = await verify_token(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket, user["user_id"], session_id)

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "user_id": user["user_id"],
                "active_users": ws_manager.get_active_users(session_id),
            }
        )

        while True:
            data = await websocket.receive_json()

            event_type = data.get("type")

            if event_type == "ping":
                await websocket.send_json(
                    {"type": "pong", "timestamp": data.get("timestamp")}
                )

            elif event_type == "subscribe":
                new_session = data.get("session_id")
                if new_session != session_id:
                    await ws_manager.disconnect(websocket, user["user_id"], session_id)
                    await ws_manager.connect(websocket, user["user_id"], new_session)

            elif event_type == "cursor_position":
                await ws_manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "cursor_position",
                        "user_id": user["user_id"],
                        "position": data.get("position"),
                    },
                    exclude_user=user["user_id"],
                )

            elif event_type == "selection":
                await ws_manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "selection",
                        "user_id": user["user_id"],
                        "selection": data.get("selection"),
                    },
                    exclude_user=user["user_id"],
                )

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, user["user_id"], session_id)


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint for user notifications.

    Client connects with: ws://host/ws/notifications?token={jwt}

    Events received:
      - notification: User notification
    """
    user = await verify_token(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket, user["user_id"])

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "user_id": user["user_id"],
            }
        )

        while True:
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, user["user_id"])


async def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token and return user info."""
    try:
        from utils.auth import _verify_token

        return _verify_token(token)
    except Exception:
        return None
