import json
from collections.abc import Iterable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth import resolve_user_from_token
from backend.database.config import SessionLocal

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: list[tuple[WebSocket, int, bool]] = []

    async def connect(self, websocket: WebSocket, user_id: int, is_admin: bool):
        await websocket.accept()
        self._connections.append((websocket, user_id, is_admin))

    def disconnect(self, websocket: WebSocket):
        self._connections = [entry for entry in self._connections if entry[0] is not websocket]

    async def broadcast(self, payload: dict, audience_user_ids: Iterable[int] | None = None):
        stale_connections: list[WebSocket] = []
        audience = set(audience_user_ids or [])
        message = json.dumps(payload, default=str)
        for connection, user_id, is_admin in self._connections:
            if audience and not is_admin and user_id not in audience:
                continue
            try:
                await connection.send_text(message)
            except Exception:
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection)


manager = ConnectionManager()


@router.websocket("/ws/whatsapp")
async def whatsapp_socket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    db = SessionLocal()
    try:
        user = resolve_user_from_token(token, db)
    finally:
        db.close()

    if user is None:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, user.id, (user.role or "user") == "admin")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
