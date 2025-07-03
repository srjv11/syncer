"""Integration tests for WebSocketManager."""

import asyncio
import contextlib
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from server.websocket_manager import WebSocketManager
from shared.models import FileInfo, SyncMessage, SyncOperation


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self, client_id="test_client"):
        self.client_id = client_id
        self.messages = []
        self.closed = False
        self.send = AsyncMock(side_effect=self._mock_send)
        self.close = AsyncMock(side_effect=self._mock_close)

    async def _mock_send(self, message):
        if not self.closed:
            self.messages.append(message)

    async def _mock_close(self):
        self.closed = True


class TestWebSocketManagerIntegration:
    """Integration tests for WebSocketManager."""

    @pytest.fixture
    def websocket_manager(self):
        """Create a WebSocketManager instance for testing."""
        manager = WebSocketManager()
        yield manager
        # Cleanup
        asyncio.create_task(manager.cleanup())

    @pytest.fixture
    def mock_websockets(self):
        """Create mock WebSocket connections."""
        return {
            "client1": MockWebSocket("client1"),
            "client2": MockWebSocket("client2"),
            "client3": MockWebSocket("client3"),
        }

    @pytest.mark.integration
    async def test_websocket_manager_initialization(self, websocket_manager):
        """Test WebSocketManager initialization."""
        assert len(websocket_manager.connections) == 0
        assert len(websocket_manager.client_info) == 0
        assert websocket_manager.is_running is False

    @pytest.mark.integration
    async def test_client_connection_registration(
        self, websocket_manager, mock_websockets
    ):
        """Test client connection and registration."""
        client_ws = mock_websockets["client1"]

        # Register client
        await websocket_manager.register_client("client1", client_ws, "Test Client")

        assert len(websocket_manager.connections) == 1
        assert "client1" in websocket_manager.connections
        assert websocket_manager.connections["client1"] == client_ws

        # Check client info
        assert "client1" in websocket_manager.client_info
        client_info = websocket_manager.client_info["client1"]
        assert client_info["name"] == "Test Client"
        assert client_info["connected_at"] is not None
        assert client_info["last_seen"] is not None

    @pytest.mark.integration
    async def test_client_disconnection(self, websocket_manager, mock_websockets):
        """Test client disconnection."""
        client_ws = mock_websockets["client1"]

        # Register client
        await websocket_manager.register_client("client1", client_ws, "Test Client")
        assert len(websocket_manager.connections) == 1

        # Disconnect client
        await websocket_manager.unregister_client("client1")

        assert len(websocket_manager.connections) == 0
        assert "client1" not in websocket_manager.connections
        assert client_ws.close.called

    @pytest.mark.integration
    async def test_broadcast_message_to_all(self, websocket_manager, mock_websockets):
        """Test broadcasting message to all connected clients."""
        # Register multiple clients
        for client_id, ws in mock_websockets.items():
            await websocket_manager.register_client(
                client_id, ws, f"Client {client_id}"
            )

        # Broadcast message
        message = {
            "type": "announcement",
            "content": "Server maintenance in 10 minutes",
        }

        await websocket_manager.broadcast_to_all(message)

        # Verify all clients received the message
        for ws in mock_websockets.values():
            assert len(ws.messages) == 1
            sent_message = json.loads(ws.messages[0])
            assert sent_message["type"] == "announcement"
            assert sent_message["content"] == "Server maintenance in 10 minutes"

    @pytest.mark.integration
    async def test_send_to_specific_client(self, websocket_manager, mock_websockets):
        """Test sending message to specific client."""
        # Register clients
        for client_id, ws in mock_websockets.items():
            await websocket_manager.register_client(
                client_id, ws, f"Client {client_id}"
            )

        # Send message to specific client
        message = {"type": "personal_message", "content": "Hello client1"}

        success = await websocket_manager.send_to_client("client1", message)

        assert success is True

        # Verify only client1 received the message
        client1_ws = mock_websockets["client1"]
        assert len(client1_ws.messages) == 1

        # Other clients should not have received it
        for client_id, ws in mock_websockets.items():
            if client_id != "client1":
                assert len(ws.messages) == 0

    @pytest.mark.integration
    async def test_send_to_nonexistent_client(self, websocket_manager):
        """Test sending message to non-existent client."""
        message = {"type": "test", "content": "test"}
        success = await websocket_manager.send_to_client("nonexistent", message)
        assert success is False

    @pytest.mark.integration
    async def test_sync_message_broadcasting(self, websocket_manager, mock_websockets):
        """Test broadcasting sync messages."""
        # Register clients
        for client_id, ws in mock_websockets.items():
            await websocket_manager.register_client(
                client_id, ws, f"Client {client_id}"
            )

        # Create sync message
        file_info = FileInfo(
            path="test.txt",
            size=1024,
            checksum="abc123",
            modified_time=datetime.now(),
            is_directory=False,
        )

        sync_message = SyncMessage(
            operation=SyncOperation.CREATE, file_info=file_info, client_id="client1"
        )

        # Broadcast sync message (should exclude sender)
        await websocket_manager.broadcast_sync_message(
            sync_message, exclude_client="client1"
        )

        # Verify client1 (sender) did not receive the message
        client1_ws = mock_websockets["client1"]
        assert len(client1_ws.messages) == 0

        # Verify other clients received the message
        for client_id, ws in mock_websockets.items():
            if client_id != "client1":
                assert len(ws.messages) == 1
                sent_message = json.loads(ws.messages[0])
                assert sent_message["type"] == "sync_message"
                assert sent_message["operation"] == "create"
                assert sent_message["file_info"]["path"] == "test.txt"

    @pytest.mark.integration
    async def test_heartbeat_mechanism(self, websocket_manager, mock_websockets):
        """Test heartbeat mechanism."""
        # Register client
        client_ws = mock_websockets["client1"]
        await websocket_manager.register_client("client1", client_ws, "Test Client")

        # Start heartbeat (with short interval for testing)
        websocket_manager.heartbeat_interval = 0.1  # 100ms
        heartbeat_task = asyncio.create_task(websocket_manager._heartbeat_loop())

        # Wait for a few heartbeats
        await asyncio.sleep(0.25)

        # Stop heartbeat
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task

        # Verify heartbeat messages were sent
        assert len(client_ws.messages) >= 2

        # Check heartbeat message format
        heartbeat_message = json.loads(client_ws.messages[0])
        assert heartbeat_message["type"] == "heartbeat"
        assert "timestamp" in heartbeat_message

    @pytest.mark.integration
    async def test_client_timeout_detection(self, websocket_manager, mock_websockets):
        """Test client timeout detection and cleanup."""
        # Register client
        client_ws = mock_websockets["client1"]
        await websocket_manager.register_client("client1", client_ws, "Test Client")

        # Simulate client timeout by not updating last_seen
        websocket_manager.client_timeout = 0.1  # 100ms timeout
        websocket_manager.client_info["client1"]["last_seen"] = datetime.now()

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Run cleanup
        await websocket_manager._cleanup_inactive_clients()

        # Client should be disconnected
        assert len(websocket_manager.connections) == 0
        assert client_ws.close.called

    @pytest.mark.integration
    async def test_message_queuing_for_disconnected_client(self, websocket_manager):
        """Test message queuing when client is temporarily disconnected."""
        # Enable message queuing
        websocket_manager.queue_messages = True
        websocket_manager.max_queue_size = 10

        # Send messages to non-connected client
        messages = [{"type": "queued_message", "id": i} for i in range(5)]

        for message in messages:
            await websocket_manager.send_to_client("offline_client", message)

        # Check messages are queued
        assert "offline_client" in websocket_manager.message_queues
        assert len(websocket_manager.message_queues["offline_client"]) == 5

        # Connect the client
        mock_ws = MockWebSocket("offline_client")
        await websocket_manager.register_client(
            "offline_client", mock_ws, "Offline Client"
        )

        # Wait for queued messages to be sent
        await asyncio.sleep(0.1)

        # Verify queued messages were delivered
        assert len(mock_ws.messages) == 5

        # Queue should be empty now
        assert len(websocket_manager.message_queues.get("offline_client", [])) == 0

    @pytest.mark.integration
    async def test_concurrent_client_operations(self, websocket_manager):
        """Test concurrent client registration and messaging."""
        # Create multiple mock clients
        clients = {}
        for i in range(10):
            client_id = f"client_{i}"
            clients[client_id] = MockWebSocket(client_id)

        # Concurrently register all clients
        registration_tasks = [
            websocket_manager.register_client(client_id, ws, f"Client {client_id}")
            for client_id, ws in clients.items()
        ]
        await asyncio.gather(*registration_tasks)

        # Verify all clients are registered
        assert len(websocket_manager.connections) == 10

        # Concurrently send messages to all clients
        message_tasks = [
            websocket_manager.send_to_client(
                client_id, {"type": "test", "client": client_id}
            )
            for client_id in clients
        ]
        results = await asyncio.gather(*message_tasks)

        # All sends should succeed
        assert all(results)

        # Each client should have received their message
        for client_id, ws in clients.items():
            assert len(ws.messages) == 1
            message = json.loads(ws.messages[0])
            assert message["client"] == client_id

    @pytest.mark.integration
    async def test_error_handling_broken_websocket(self, websocket_manager):
        """Test error handling when WebSocket connection is broken."""
        # Create a mock WebSocket that raises exception on send
        broken_ws = Mock()
        broken_ws.send = AsyncMock(side_effect=Exception("Connection broken"))
        broken_ws.close = AsyncMock()

        # Register client with broken WebSocket
        await websocket_manager.register_client(
            "broken_client", broken_ws, "Broken Client"
        )

        # Try to send message (should handle error gracefully)
        success = await websocket_manager.send_to_client(
            "broken_client", {"type": "test"}
        )

        assert success is False

        # Client should be automatically unregistered
        assert "broken_client" not in websocket_manager.connections

    @pytest.mark.integration
    async def test_statistics_collection(self, websocket_manager, mock_websockets):
        """Test WebSocket statistics collection."""
        # Register clients and send messages
        for client_id, ws in mock_websockets.items():
            await websocket_manager.register_client(
                client_id, ws, f"Client {client_id}"
            )

        # Send various messages
        await websocket_manager.broadcast_to_all({"type": "broadcast"})
        await websocket_manager.send_to_client("client1", {"type": "personal"})

        # Get statistics
        stats = websocket_manager.get_statistics()

        assert stats["active_connections"] == 3
        assert stats["total_messages_sent"] >= 4  # 3 broadcast + 1 personal
        assert stats["total_broadcasts"] >= 1
        assert "uptime_seconds" in stats
        assert "clients" in stats
        assert len(stats["clients"]) == 3

    @pytest.mark.integration
    async def test_room_based_messaging(self, websocket_manager, mock_websockets):
        """Test room-based messaging functionality."""
        # Register clients and assign to rooms
        await websocket_manager.register_client(
            "client1", mock_websockets["client1"], "Client 1"
        )
        await websocket_manager.register_client(
            "client2", mock_websockets["client2"], "Client 2"
        )
        await websocket_manager.register_client(
            "client3", mock_websockets["client3"], "Client 3"
        )

        # Add clients to rooms
        websocket_manager.add_client_to_room("client1", "room_a")
        websocket_manager.add_client_to_room("client2", "room_a")
        websocket_manager.add_client_to_room("client3", "room_b")

        # Send message to room_a
        message = {"type": "room_message", "content": "Hello room A"}
        await websocket_manager.broadcast_to_room("room_a", message)

        # Verify only room_a members received the message
        assert len(mock_websockets["client1"].messages) == 1
        assert len(mock_websockets["client2"].messages) == 1
        assert len(mock_websockets["client3"].messages) == 0

        # Verify message content
        for client_id in ["client1", "client2"]:
            message_data = json.loads(mock_websockets[client_id].messages[0])
            assert message_data["content"] == "Hello room A"

    @pytest.mark.integration
    async def test_rate_limiting(self, websocket_manager, mock_websockets):
        """Test rate limiting functionality."""
        # Enable rate limiting
        websocket_manager.enable_rate_limiting = True
        websocket_manager.rate_limit_messages = 5  # 5 messages per window
        websocket_manager.rate_limit_window = 1.0  # 1 second window

        # Register client
        await websocket_manager.register_client(
            "client1", mock_websockets["client1"], "Client 1"
        )

        # Send messages rapidly (should hit rate limit)
        messages_sent = 0
        for i in range(10):
            success = await websocket_manager.send_to_client("client1", {"id": i})
            if success:
                messages_sent += 1

        # Should have sent only up to the rate limit
        assert messages_sent <= 5

        # Wait for rate limit window to reset
        await asyncio.sleep(1.1)

        # Should be able to send again
        success = await websocket_manager.send_to_client(
            "client1", {"after_reset": True}
        )
        assert success is True

    @pytest.mark.integration
    async def test_message_persistence(self, websocket_manager, temp_dir):
        """Test message persistence functionality."""
        # Enable message persistence
        websocket_manager.persist_messages = True
        websocket_manager.message_log_file = temp_dir / "messages.log"

        # Register client and send messages
        await websocket_manager.register_client(
            "client1", MockWebSocket("client1"), "Client 1"
        )

        messages = [
            {"type": "test", "id": 1},
            {"type": "test", "id": 2},
            {"type": "test", "id": 3},
        ]

        for message in messages:
            await websocket_manager.send_to_client("client1", message)

        # Wait for persistence
        await asyncio.sleep(0.1)

        # Check message log file
        assert websocket_manager.message_log_file.exists()

        with open(websocket_manager.message_log_file) as f:
            log_content = f.read()
            assert "client1" in log_content
            assert '"type": "test"' in log_content

    @pytest.mark.integration
    async def test_websocket_manager_shutdown(self, websocket_manager, mock_websockets):
        """Test graceful shutdown of WebSocket manager."""
        # Register multiple clients
        for client_id, ws in mock_websockets.items():
            await websocket_manager.register_client(
                client_id, ws, f"Client {client_id}"
            )

        assert len(websocket_manager.connections) == 3

        # Shutdown manager
        await websocket_manager.shutdown()

        # All clients should be disconnected
        assert len(websocket_manager.connections) == 0

        # All WebSocket connections should be closed
        for ws in mock_websockets.values():
            assert ws.close.called

    @pytest.mark.integration
    async def test_websocket_message_compression(
        self, websocket_manager, mock_websockets
    ):
        """Test WebSocket message compression for large messages."""
        # Enable compression
        websocket_manager.enable_compression = True
        websocket_manager.compression_threshold = 100  # Compress messages > 100 bytes

        # Register client
        await websocket_manager.register_client(
            "client1", mock_websockets["client1"], "Client 1"
        )

        # Send large message
        large_message = {
            "type": "large_data",
            "data": "x" * 1000,  # 1000 characters
        }

        success = await websocket_manager.send_to_client("client1", large_message)
        assert success is True

        # Message should have been sent (compression is handled internally)
        assert len(mock_websockets["client1"].messages) == 1

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_high_throughput_messaging(self, websocket_manager):
        """Test high-throughput messaging scenario."""
        # Create many clients
        clients = {}
        for i in range(20):
            client_id = f"client_{i}"
            clients[client_id] = MockWebSocket(client_id)
            await websocket_manager.register_client(
                client_id, clients[client_id], f"Client {i}"
            )

        # Send many messages concurrently
        async def send_messages(client_id, count):
            for i in range(count):
                await websocket_manager.send_to_client(client_id, {"msg_id": i})

        # Start concurrent message sending
        tasks = [send_messages(client_id, 50) for client_id in clients]
        await asyncio.gather(*tasks)

        # Verify all messages were delivered
        total_messages = sum(len(ws.messages) for ws in clients.values())
        assert total_messages == 20 * 50  # 20 clients * 50 messages each

        # Check statistics
        stats = websocket_manager.get_statistics()
        assert stats["active_connections"] == 20
        assert stats["total_messages_sent"] >= 1000
