import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from shared.protocols import (
    ConnectionRequest,
    ConnectionResponse,
    HeartbeatMessage,
    MessageType,
    WebSocketMessage,
)

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_info: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept WebSocket connection and add to active connections."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected via WebSocket")

    def disconnect(self, client_id: str) -> None:
        """Remove client from active connections."""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.client_info:
            del self.client_info[client_id]
        logger.info(f"Client {client_id} disconnected")

    async def _send_message_safe(
        self, client_id: str, websocket: WebSocket, message: Dict[str, Any]
    ) -> None:
        """Send message to websocket with error handling."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.exception(f"Error sending message to {client_id}: {e}")
            raise

    async def send_message(self, client_id: str, message: Dict[str, Any]) -> None:
        """Send message to specific client."""
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                await self._send_message_safe(client_id, websocket, message)
            except Exception:
                self.disconnect(client_id)

    async def broadcast_to_all(self, message: Dict[str, Any]) -> None:
        """Send message to all connected clients concurrently."""
        if not self.active_connections:
            return

        # Create concurrent tasks for all broadcasts
        tasks = [
            self._send_message_safe(client_id, websocket, message)
            for client_id, websocket in self.active_connections.items()
        ]

        # Execute all broadcasts concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Clean up disconnected clients
        disconnected_clients = []
        for (client_id, _), result in zip(self.active_connections.items(), results):
            if isinstance(result, Exception):
                logger.error(f"Error broadcasting to {client_id}: {result}")
                disconnected_clients.append(client_id)

        for client_id in disconnected_clients:
            self.disconnect(client_id)

    async def broadcast_to_others(
        self, sender_client_id: str, message: Dict[str, Any]
    ) -> None:
        """Send message to all clients except the sender concurrently."""
        # Create concurrent tasks for all broadcasts except sender
        tasks = [
            self._send_message_safe(client_id, websocket, message)
            for client_id, websocket in self.active_connections.items()
            if client_id != sender_client_id
        ]

        if not tasks:
            return

        # Execute all broadcasts concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Clean up disconnected clients
        disconnected_clients = []
        task_index = 0
        for client_id, _websocket in self.active_connections.items():
            if client_id != sender_client_id:
                if isinstance(results[task_index], Exception):
                    logger.error(
                        f"Error broadcasting to {client_id}: {results[task_index]}"
                    )
                    disconnected_clients.append(client_id)
                task_index += 1

        for client_id in disconnected_clients:
            self.disconnect(client_id)

    async def handle_message(
        self, client_id: str, message_data: Dict[str, Any]
    ) -> None:
        """Handle incoming WebSocket message from client."""
        try:
            message = WebSocketMessage(**message_data)

            if message.type == MessageType.CLIENT_CONNECT:
                connection_req = ConnectionRequest(**message.data)
                self.client_info[client_id] = {
                    "name": connection_req.client_name,
                    "sync_root": connection_req.sync_root,
                    "connected_at": datetime.now().isoformat(),
                }

                response = ConnectionResponse(
                    success=True,
                    message="Connected successfully",
                    server_time=datetime.now().isoformat(),
                )
                await self.send_message(
                    client_id,
                    {
                        "type": MessageType.CLIENT_CONNECT,
                        "data": response.model_dump(mode="json"),
                    },
                )

                # Notify other clients
                await self.broadcast_to_others(
                    client_id,
                    {
                        "type": "client_joined",
                        "data": {
                            "client_id": client_id,
                            "name": connection_req.client_name,
                        },
                    },
                )

            elif message.type == MessageType.HEARTBEAT:
                HeartbeatMessage(**message.data)
                await self.send_message(
                    client_id,
                    {
                        "type": MessageType.HEARTBEAT,
                        "data": {"timestamp": datetime.now().isoformat()},
                    },
                )

            elif message.type == MessageType.FILE_CHANGED:
                # Broadcast file change to other clients
                await self.broadcast_to_others(client_id, message_data)

            else:
                logger.warning(f"Unknown message type: {message.type}")

        except Exception as e:
            logger.exception(f"Error handling message from {client_id}: {e}")
            await self.send_message(
                client_id, {"type": MessageType.ERROR, "data": {"error": str(e)}}
            )

    async def websocket_endpoint(self, websocket: WebSocket, client_id: str) -> None:
        """WebSocket endpoint handler."""
        await self.connect(websocket, client_id)

        try:
            while True:
                # Receive message from client
                data = await websocket.receive_text()
                message_data = json.loads(data)
                await self.handle_message(client_id, message_data)

        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected normally")
        except Exception as e:
            logger.exception(f"WebSocket error for client {client_id}: {e}")
        finally:
            self.disconnect(client_id)
            # Notify other clients about disconnection
            await self.broadcast_to_others(
                client_id, {"type": "client_left", "data": {"client_id": client_id}}
            )

    def get_connected_clients(self) -> Dict[str, Dict[str, Any]]:
        """Get list of currently connected clients."""
        return self.client_info.copy()

    def is_client_connected(self, client_id: str) -> bool:
        """Check if client is currently connected."""
        return client_id in self.active_connections

    async def broadcast_to_group(
        self, client_ids: List[str], message: Dict[str, Any]
    ) -> None:
        """Send message to specific group of clients concurrently."""
        tasks = [
            self._send_message_safe(
                client_id, self.active_connections[client_id], message
            )
            for client_id in client_ids
            if client_id in self.active_connections
        ]

        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Clean up disconnected clients
        disconnected_clients = []
        task_index = 0
        for client_id in client_ids:
            if client_id in self.active_connections:
                if isinstance(results[task_index], Exception):
                    logger.error(
                        f"Error broadcasting to {client_id}: {results[task_index]}"
                    )
                    disconnected_clients.append(client_id)
                task_index += 1

        for client_id in disconnected_clients:
            self.disconnect(client_id)

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)

    async def ping_all_clients(self) -> Dict[str, bool]:
        """Ping all clients to check connection health."""
        ping_results = {}

        tasks = [
            self._ping_client(client_id, websocket)
            for client_id, websocket in self.active_connections.items()
        ]

        if not tasks:
            return ping_results

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (client_id, _), result in zip(self.active_connections.items(), results):
            ping_results[client_id] = not isinstance(result, Exception)
            if isinstance(result, Exception):
                logger.warning(f"Client {client_id} failed ping: {result}")
                self.disconnect(client_id)

        return ping_results

    async def _ping_client(self, client_id: str, websocket: WebSocket) -> None:
        """Ping individual client."""
        try:
            await websocket.ping()
        except Exception as e:
            logger.exception(f"Error pinging client {client_id}: {e}")
            raise
