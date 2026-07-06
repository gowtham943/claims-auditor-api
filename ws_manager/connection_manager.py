import json
import logging
from typing import Dict, List

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, claim_id: str, websocket: WebSocket):
        await websocket.accept()
        if claim_id not in self.active_connections:
            self.active_connections[claim_id] = []
        self.active_connections[claim_id].append(websocket)
        logger.info(f"UI Client connected to monitoring pipeline for Claim: {claim_id}")

    def disconnect(self, claim_id: str, websocket: WebSocket):
        if claim_id in self.active_connections:
            if websocket in self.active_connections[claim_id]:
                self.active_connections[claim_id].remove(websocket)
            if not self.active_connections[claim_id]:
                del self.active_connections[claim_id]
        logger.info(f"UI Client disconnected from track channel for Claim: {claim_id}")

    async def stream_status(
        self,
        claim_id: str,
        step: str,
        message: str,
        payload: dict | None = None,
    ):
        if claim_id not in self.active_connections:
            return

        event_data = {
            "claim_id": claim_id,
            "step": step,
            "message": message,
            "payload": payload or {},
        }
        json_message = json.dumps(event_data)

        for connection in self.active_connections[claim_id]:
            try:
                await connection.send_text(json_message)
            except Exception as send_err:
                logger.error(f"Failed to push network packet to connection frame: {send_err}")


socket_manager = ConnectionManager()
