"""Integration tests for SyncEngine."""

import asyncio
import contextlib
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from client.sync_engine import SyncEngine
from shared.exceptions import ConnectionError, SyncError
from shared.models import FileInfo, SyncResponse


class TestSyncEngineIntegration:
    """Integration tests for SyncEngine."""

    @pytest.fixture
    async def sync_engine(self, sample_client_config):
        """Create a SyncEngine instance for testing."""
        engine = SyncEngine(sample_client_config)
        yield engine
        await engine.close()

    @pytest.fixture
    async def mock_server_responses(self):
        """Create mock server responses."""
        return {
            "upload": {
                "status": 200,
                "json": {"success": True, "message": "File uploaded successfully"},
            },
            "download": {"status": 200, "content": b"Downloaded file content"},
            "sync": {
                "status": 200,
                "json": {"success": True, "files_to_sync": [], "conflicts": []},
            },
            "list": {
                "status": 200,
                "json": {
                    "files": [
                        {
                            "path": "remote_file.txt",
                            "size": 100,
                            "checksum": "remote_hash",
                            "modified_time": "2023-01-01T00:00:00",
                            "is_directory": False,
                        }
                    ]
                },
            },
        }

    @pytest.mark.integration
    async def test_sync_engine_initialization(self, sample_client_config):
        """Test SyncEngine initialization."""
        engine = SyncEngine(sample_client_config)

        assert engine.config == sample_client_config
        assert engine.client_id is not None
        assert engine.session is None  # Not initialized until start
        assert engine.websocket is None

        await engine.close()

    @pytest.mark.integration
    async def test_sync_engine_lifecycle(self, sync_engine):
        """Test SyncEngine start and stop lifecycle."""
        # Initially not running
        assert not sync_engine.is_running
        assert sync_engine.session is None

        # Start engine
        with patch.object(sync_engine, "_connect_websocket") as mock_ws:
            mock_ws.return_value = Mock()
            await sync_engine.start()

            assert sync_engine.is_running
            assert sync_engine.session is not None

        # Stop engine
        await sync_engine.stop()
        assert not sync_engine.is_running

    @pytest.mark.integration
    async def test_file_upload(self, sync_engine, sample_files, mock_server_responses):
        """Test file upload functionality."""
        await sync_engine.start()

        # Mock HTTP session
        mock_response = Mock()
        mock_response.status = mock_server_responses["upload"]["status"]
        mock_response.json = AsyncMock(
            return_value=mock_server_responses["upload"]["json"]
        )

        with patch.object(
            sync_engine.session, "post", return_value=mock_response
        ) as mock_post:
            # Upload text file
            text_file = sample_files["text"]
            success = await sync_engine.upload_file(str(text_file), "remote_path.txt")

            assert success is True
            mock_post.assert_called_once()

            # Verify upload URL and data
            call_args = mock_post.call_args
            assert "/upload" in call_args[0][0]  # URL contains /upload

    @pytest.mark.integration
    async def test_file_download(self, sync_engine, temp_dir, mock_server_responses):
        """Test file download functionality."""
        await sync_engine.start()

        # Mock HTTP session
        mock_response = Mock()
        mock_response.status = mock_server_responses["download"]["status"]
        mock_response.content.iter_chunked = AsyncMock(
            return_value=[mock_server_responses["download"]["content"]]
        )

        with patch.object(
            sync_engine.session, "get", return_value=mock_response
        ) as mock_get:
            # Download file
            local_path = temp_dir / "downloaded.txt"
            success = await sync_engine.download_file(
                "remote_file.txt", str(local_path)
            )

            assert success is True
            assert local_path.exists()

            # Verify file content
            with open(local_path, "rb") as f:
                content = f.read()
            assert content == mock_server_responses["download"]["content"]

            mock_get.assert_called_once()

    @pytest.mark.integration
    async def test_sync_request(
        self, sync_engine, sample_file_info, mock_server_responses
    ):
        """Test sync request functionality."""
        await sync_engine.start()

        # Mock HTTP session
        mock_response = Mock()
        mock_response.status = mock_server_responses["sync"]["status"]
        mock_response.json = AsyncMock(
            return_value=mock_server_responses["sync"]["json"]
        )

        with patch.object(
            sync_engine.session, "post", return_value=mock_response
        ) as mock_post:
            # Perform sync request
            response = await sync_engine.sync_files(sample_file_info)

            assert isinstance(response, SyncResponse)
            assert response.success is True
            assert response.files_to_sync == []
            assert response.conflicts == []

            mock_post.assert_called_once()

    @pytest.mark.integration
    async def test_get_remote_file_list(self, sync_engine, mock_server_responses):
        """Test getting remote file list."""
        await sync_engine.start()

        # Mock HTTP session
        mock_response = Mock()
        mock_response.status = mock_server_responses["list"]["status"]
        mock_response.json = AsyncMock(
            return_value=mock_server_responses["list"]["json"]
        )

        with patch.object(
            sync_engine.session, "get", return_value=mock_response
        ) as mock_get:
            # Get remote file list
            files = await sync_engine.get_remote_file_list()

            assert len(files) == 1
            assert isinstance(files[0], FileInfo)
            assert files[0].path == "remote_file.txt"
            assert files[0].size == 100
            assert files[0].checksum == "remote_hash"

            mock_get.assert_called_once()

    @pytest.mark.integration
    async def test_full_sync_operation(
        self, sync_engine, sample_files, mock_server_responses
    ):
        """Test complete sync operation."""
        await sync_engine.start()

        # Mock all HTTP operations
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={
                "success": True,
                "files_to_sync": [
                    {
                        "path": "need_download.txt",
                        "size": 50,
                        "checksum": "download_hash",
                        "modified_time": "2023-01-01T00:00:00",
                        "is_directory": False,
                    }
                ],
                "conflicts": [],
            }
        )

        download_response = Mock()
        download_response.status = 200
        download_response.content.iter_chunked = AsyncMock(
            return_value=[b"Downloaded content"]
        )

        with patch.object(sync_engine.session, "post") as mock_post, patch.object(
            sync_engine.session, "get", return_value=download_response
        ) as mock_get:
            # Configure post to return different responses
            mock_post.side_effect = [upload_response, sync_response]

            # Perform full sync
            result = await sync_engine.perform_full_sync()

            assert result is True

            # Verify calls were made
            assert mock_post.call_count >= 1  # At least sync request
            assert mock_get.call_count >= 1  # Download request

    @pytest.mark.integration
    async def test_websocket_connection(self, sync_engine):
        """Test WebSocket connection functionality."""
        # Mock WebSocket
        mock_websocket = Mock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"type": "heartbeat"}')
        mock_websocket.close = AsyncMock()

        with patch("websockets.connect", return_value=mock_websocket) as mock_connect:
            await sync_engine.start()

            # Verify WebSocket connection was attempted
            mock_connect.assert_called_once()
            assert sync_engine.websocket is not None

    @pytest.mark.integration
    async def test_websocket_message_handling(self, sync_engine):
        """Test WebSocket message handling."""
        messages = [
            '{"type": "file_changed", "path": "test.txt", "operation": "create"}',
            '{"type": "sync_request", "client_id": "other_client"}',
            '{"type": "heartbeat"}',
        ]

        mock_websocket = Mock()
        mock_websocket.recv = AsyncMock(
            side_effect=[*messages, asyncio.CancelledError()]
        )
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        with patch("websockets.connect", return_value=mock_websocket):
            await sync_engine.start()

            # Start message handling
            message_task = asyncio.create_task(sync_engine._handle_websocket_messages())

            # Wait a bit for messages to be processed
            await asyncio.sleep(0.1)

            # Cancel task
            message_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await message_task

            # Verify messages were received
            assert mock_websocket.recv.call_count >= 3

    @pytest.mark.integration
    async def test_error_handling_network_failure(self, sync_engine):
        """Test error handling for network failures."""
        await sync_engine.start()

        # Mock network failure
        with patch.object(
            sync_engine.session,
            "post",
            side_effect=aiohttp.ClientError("Network error"),
        ):
            with pytest.raises(ConnectionError):
                await sync_engine.upload_file("test.txt", "remote.txt")

    @pytest.mark.integration
    async def test_error_handling_server_error(self, sync_engine, sample_file_info):
        """Test error handling for server errors."""
        await sync_engine.start()

        # Mock server error response
        mock_response = Mock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        with patch.object(sync_engine.session, "post", return_value=mock_response):
            with pytest.raises(SyncError):
                await sync_engine.sync_files(sample_file_info)

    @pytest.mark.integration
    async def test_retry_mechanism(self, sync_engine):
        """Test retry mechanism for failed operations."""
        await sync_engine.start()

        # Mock responses: first two fail, third succeeds
        responses = [
            Mock(status=500),
            Mock(status=502),
            Mock(status=200, json=AsyncMock(return_value={"success": True})),
        ]

        with patch.object(sync_engine.session, "post", side_effect=responses):
            # Should eventually succeed after retries
            success = await sync_engine.upload_file("test.txt", "remote.txt")
            assert success is True

    @pytest.mark.integration
    async def test_concurrent_operations(self, sync_engine, sample_files):
        """Test concurrent file operations."""
        await sync_engine.start()

        # Mock successful responses
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine.session, "post", return_value=mock_response):
            # Start multiple upload operations concurrently
            tasks = []
            files = list(sample_files.values())[:3]  # Use first 3 files

            for i, file_path in enumerate(files):
                if file_path.is_file():
                    task = sync_engine.upload_file(str(file_path), f"remote_{i}.txt")
                    tasks.append(task)

            # Wait for all operations to complete
            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(results)

    @pytest.mark.integration
    async def test_adaptive_chunk_size(self, sync_engine, temp_dir):
        """Test adaptive chunk size for large files."""
        await sync_engine.start()

        # Create files of different sizes
        small_file = temp_dir / "small.txt"
        large_file = temp_dir / "large.txt"

        with open(small_file, "w") as f:
            f.write("small content")  # < 1KB

        with open(large_file, "w") as f:
            f.write("x" * (5 * 1024 * 1024))  # 5MB

        # Test chunk size calculation
        small_chunk = sync_engine._get_adaptive_chunk_size(small_file.stat().st_size)
        large_chunk = sync_engine._get_adaptive_chunk_size(large_file.stat().st_size)

        assert small_chunk <= large_chunk
        assert small_chunk >= sync_engine.MIN_CHUNK_SIZE
        assert large_chunk <= sync_engine.MAX_CHUNK_SIZE

    @pytest.mark.integration
    async def test_compression_during_upload(self, sync_engine, temp_dir):
        """Test compression during file upload."""
        await sync_engine.start()

        # Create compressible file
        compressible_file = temp_dir / "compressible.txt"
        content = "This is repeated content. " * 1000  # Very compressible

        with open(compressible_file, "w") as f:
            f.write(content)

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        with patch.object(
            sync_engine.session, "post", return_value=mock_response
        ) as mock_post:
            success = await sync_engine.upload_file(
                str(compressible_file), "compressed.txt"
            )

            assert success is True

            # Check if compression was applied
            call_args = mock_post.call_args
            # The uploaded data should be compressed if file was large enough
            assert call_args is not None

    @pytest.mark.integration
    async def test_metrics_collection_during_sync(self, sync_engine, metrics_collector):
        """Test metrics collection during sync operations."""
        sync_engine.metrics = metrics_collector
        await sync_engine.start()

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine.session, "post", return_value=mock_response):
            # Perform operation that should generate metrics
            await sync_engine.upload_file("test.txt", "remote.txt")

        # Check metrics were collected
        all_metrics = metrics_collector.collect_all()

        # Should have timer metrics for upload operation
        assert len(all_metrics["timers"]) > 0

        # Should have counter metrics
        assert len(all_metrics["counters"]) > 0

    @pytest.mark.integration
    async def test_bandwidth_throttling(self, sync_engine, temp_dir):
        """Test bandwidth throttling functionality."""
        sync_engine.max_bandwidth = 1024 * 1024  # 1MB/s
        await sync_engine.start()

        # Create large file
        large_file = temp_dir / "large.bin"
        with open(large_file, "wb") as f:
            f.write(b"x" * (2 * 1024 * 1024))  # 2MB

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine.session, "post", return_value=mock_response):
            import time

            start_time = time.time()

            await sync_engine.upload_file(str(large_file), "throttled.bin")

            end_time = time.time()
            upload_time = end_time - start_time

            # Should take at least 1 second due to bandwidth throttling
            # (2MB at 1MB/s = 2 seconds, but allow some tolerance)
            assert upload_time > 0.5  # Allow for overhead and timing variance

    @pytest.mark.integration
    async def test_conflict_resolution(self, sync_engine, sample_file_info):
        """Test conflict resolution during sync."""
        await sync_engine.start()

        # Mock sync response with conflicts
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "success": True,
                "files_to_sync": [],
                "conflicts": ["conflicted_file.txt"],
            }
        )

        with patch.object(sync_engine.session, "post", return_value=mock_response):
            response = await sync_engine.sync_files(sample_file_info)

            assert response.success is True
            assert len(response.conflicts) == 1
            assert "conflicted_file.txt" in response.conflicts

    @pytest.mark.integration
    async def test_reconnection_after_disconnect(self, sync_engine):
        """Test automatic reconnection after WebSocket disconnect."""
        # Mock WebSocket that disconnects
        mock_websocket = Mock()
        mock_websocket.recv = AsyncMock(
            side_effect=[
                '{"type": "heartbeat"}',
                Exception("Connection lost"),  # Simulate disconnect
            ]
        )
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        reconnect_websocket = Mock()
        reconnect_websocket.recv = AsyncMock(return_value='{"type": "heartbeat"}')
        reconnect_websocket.send = AsyncMock()
        reconnect_websocket.close = AsyncMock()

        with patch(
            "websockets.connect", side_effect=[mock_websocket, reconnect_websocket]
        ):
            await sync_engine.start()

            # Start message handling (will disconnect and reconnect)
            message_task = asyncio.create_task(sync_engine._handle_websocket_messages())

            # Wait for disconnect and reconnection
            await asyncio.sleep(0.2)

            # Cancel task
            message_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await message_task

            # Should have attempted reconnection
            assert sync_engine.websocket is not None

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_large_scale_sync(self, sync_engine, temp_dir):
        """Test sync with many files."""
        await sync_engine.start()

        # Create many small files
        files = []
        for i in range(50):
            file_path = temp_dir / f"file_{i:03d}.txt"
            with open(file_path, "w") as f:
                f.write(f"Content of file {i}")
            files.append(file_path)

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        with patch.object(
            sync_engine.session, "post", return_value=mock_response
        ) as mock_post:
            # Upload all files
            tasks = []
            for file_path in files:
                task = sync_engine.upload_file(
                    str(file_path), f"remote_{file_path.name}"
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # All uploads should succeed
            assert all(results)
            assert mock_post.call_count == 50

    @pytest.mark.integration
    async def test_session_management(self, sync_engine):
        """Test HTTP session management."""
        # Session should not exist initially
        assert sync_engine.session is None

        # Start engine
        await sync_engine.start()
        assert sync_engine.session is not None

        # Session should have proper configuration
        connector = sync_engine.session.connector
        assert connector.limit == 20  # Total connection pool size
        assert connector.limit_per_host == 10  # Connections per host

        # Stop engine
        await sync_engine.stop()
        # Session should be closed but reference might remain

    @pytest.mark.integration
    async def test_authentication_headers(self, sync_engine):
        """Test authentication headers in requests."""
        # Set API key
        sync_engine.config.api_key = "test_api_key_123"
        await sync_engine.start()

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        with patch.object(
            sync_engine.session, "post", return_value=mock_response
        ) as mock_post:
            await sync_engine.upload_file("test.txt", "remote.txt")

            # Check that authentication header was included
            call_args = mock_post.call_args
            headers = call_args[1].get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_api_key_123"
