import logging
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, status

from config.config_setting import settings
from config.database_config import db
from repositories.claim_repo import ClaimRepository
from repositories.policy_repo import PolicyRepository
from repositories.user_repo import UserRepository
from ws_manager.connection_manager import socket_manager

ws_router = APIRouter(prefix="/ws", tags=["Real-time Notification Architecture"])
logger = logging.getLogger("uvicorn.error")


async def _user_owns_tracking_id(tracking_id: str, user_id: uuid.UUID) -> bool:
    try:
        resource_id = uuid.UUID(tracking_id)
    except ValueError:
        return False

    async with db.session_factory() as session:
        claim_repo = ClaimRepository(session)
        policy_repo = PolicyRepository(session)

        if await claim_repo.get_claim_by_id(resource_id, user_id):
            return True
        if await policy_repo.get_policy_by_id(resource_id, user_id):
            return True
    return False


async def _authenticate_websocket(websocket: WebSocket) -> uuid.UUID:
    token = websocket.query_params.get("token")
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid auth token")
    except jwt.InvalidTokenError as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid auth token") from exc

    async with db.session_factory() as session:
        user = await UserRepository(session).get_by_username(username)
        if not user:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown user")
        return user.id


@ws_router.websocket("/{claim_id}")
async def websocket_audit_stream_endpoint(websocket: WebSocket, claim_id: str):
    """
    Streams ingestion progress for a claim or policy owned by the authenticated user.
    Pass the JWT as a query parameter: /ws/{id}?token=...
    """
    user_id = await _authenticate_websocket(websocket)
    if not await _user_owns_tracking_id(claim_id, user_id):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Resource not found")

    await socket_manager.connect(claim_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        socket_manager.disconnect(claim_id, websocket)
    except Exception as exc:
        logger.error(f"WebSocket transport channel hit an unhandled exception state: {exc}")
        socket_manager.disconnect(claim_id, websocket)
