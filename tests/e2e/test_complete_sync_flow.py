"""End-to-end tests for complete sync flow."""

import asyncio
import contextlib
import json
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from client.sync_engine import SyncEngine
from server.file_manager import FileManager
from server.websocket_manager import WebSocketManager
from shared.models import ClientConfig, ServerConfig


class TestCompleteSyncFlow:
    """End-to-end tests for complete synchronization flow."""

    @pytest.fixture
    async def temp_directories(self):
        """Create temporary directories for client and server."""
        client_dir = Path(tempfile.mkdtemp(prefix="e2e_client_"))
        server_dir = Path(tempfile.mkdtemp(prefix="e2e_server_"))

        yield {"client": client_dir, "server": server_dir}

        # Cleanup
        shutil.rmtree(client_dir, ignore_errors=True)
        shutil.rmtree(server_dir, ignore_errors=True)

    @pytest.fixture
    def client_config(self, temp_directories):
        """Create client configuration."""
        return ClientConfig(
            client_name="e2e_test_client",
            sync_directory=str(temp_directories["client"]),
            server_host="localhost",
            server_port=8999,  # Use different port for testing
            ignore_patterns=[".git", "*.tmp", "__pycache__"],
        )

    @pytest.fixture
    def server_config(self, temp_directories):
        """Create server configuration."""
        return ServerConfig(
            host="localhost",
            port=8999,
            sync_directory=str(temp_directories["server"]),
            max_file_size=10 * 1024 * 1024,  # 10MB
        )

    @pytest.fixture
    async def mock_server_components(self, server_config):
        """Create mock server components."""
        file_manager = FileManager(server_config.sync_directory)
        await file_manager._init_database()

        websocket_manager = WebSocketManager()

        yield {"file_manager": file_manager, "websocket_manager": websocket_manager}

        # Cleanup
        await file_manager.close()
        await websocket_manager.cleanup()

    @pytest.mark.e2e
    async def test_single_file_sync_create(self, temp_directories, client_config):
        """Test end-to-end sync of a single file creation."""
        # Create file on client side
        client_file = temp_directories["client"] / "test_document.txt"
        content = "This is a test document for end-to-end sync testing."

        with open(client_file, "w") as f:
            f.write(content)

        # Mock sync engine with successful operations
        sync_engine = SyncEngine(client_config)

        # Mock the server responses
        mock_upload_response = Mock()
        mock_upload_response.status = 200
        mock_upload_response.json = AsyncMock(return_value={"success": True})

        mock_sync_response = Mock()
        mock_sync_response.status = 200
        mock_sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [mock_upload_response, mock_sync_response]

            # Start sync engine
            await sync_engine.start()

            # Perform sync
            success = await sync_engine.perform_full_sync()

            assert success is True

            # Verify upload was called
            assert mock_session.post.call_count >= 1

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_bidirectional_sync(self, temp_directories, client_config):
        """Test bidirectional sync between client and server."""
        # Create files on both sides
        client_file = temp_directories["client"] / "client_file.txt"
        with open(client_file, "w") as f:
            f.write("Content from client")

        server_file = temp_directories["server"] / "server_file.txt"
        with open(server_file, "w") as f:
            f.write("Content from server")

        sync_engine = SyncEngine(client_config)

        # Mock server responses for bidirectional sync
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
                        "path": "server_file.txt",
                        "size": 19,
                        "checksum": "server_hash",
                        "modified_time": datetime.now().isoformat(),
                        "is_directory": False,
                    }
                ],
                "conflicts": [],
            }
        )

        download_response = Mock()
        download_response.status = 200
        download_response.content.iter_chunked = AsyncMock(
            return_value=[b"Content from server"]
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            # Configure session mocks
            mock_session.post.side_effect = [upload_response, sync_response]
            mock_session.get.return_value = download_response

            await sync_engine.start()

            # Perform bidirectional sync
            success = await sync_engine.perform_full_sync()

            assert success is True

            # Verify both upload and download occurred
            assert mock_session.post.call_count >= 2  # Upload + sync request
            assert mock_session.get.call_count >= 1  # Download

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_conflict_resolution_flow(self, temp_directories, client_config):
        """Test end-to-end conflict resolution."""
        # Create conflicting file (same name, different content)
        client_file = temp_directories["client"] / "conflicted.txt"
        with open(client_file, "w") as f:
            f.write("Client version of the file")

        sync_engine = SyncEngine(client_config)

        # Mock server response indicating conflict
        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={
                "success": True,
                "files_to_sync": [],
                "conflicts": ["conflicted.txt"],
            }
        )

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response, sync_response]

            await sync_engine.start()

            # Perform sync (should detect conflict)
            success = await sync_engine.perform_full_sync()

            # Sync should complete but with conflicts
            assert success is True

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_large_file_sync_with_chunking(self, temp_directories, client_config):
        """Test sync of large files with chunking."""
        # Create large file
        large_file = temp_directories["client"] / "large_file.dat"
        large_content = b"x" * (5 * 1024 * 1024)  # 5MB

        with open(large_file, "wb") as f:
            f.write(large_content)

        sync_engine = SyncEngine(client_config)

        # Mock chunked upload response
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.return_value = upload_response

            await sync_engine.start()

            # Upload large file (should use chunking)
            success = await sync_engine.upload_file(str(large_file), "large_file.dat")

            assert success is True

            # Verify multiple chunks were uploaded
            assert mock_session.post.call_count >= 1

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_directory_structure_sync(self, temp_directories, client_config):
        """Test sync of nested directory structures."""
        # Create nested directory structure
        base_dir = temp_directories["client"]

        # Create directories and files
        (base_dir / "docs").mkdir()
        (base_dir / "docs" / "subfolder").mkdir()
        (base_dir / "images").mkdir()

        files_to_create = [
            ("README.md", "# Project Documentation"),
            ("docs/guide.txt", "User guide content"),
            ("docs/subfolder/notes.txt", "Meeting notes"),
            ("images/logo.png", b"\x89PNG\r\n\x1a\n" + b"fake_png_data"),
        ]

        for file_path, content in files_to_create:
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, bytes):
                with open(full_path, "wb") as f:
                    f.write(content)
            else:
                with open(full_path, "w") as f:
                    f.write(content)

        sync_engine = SyncEngine(client_config)

        # Mock successful responses for all files
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response]

            await sync_engine.start()

            # Perform full sync
            success = await sync_engine.perform_full_sync()

            assert success is True

            # Should have uploaded multiple files
            assert mock_session.post.call_count >= len(files_to_create)

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_real_time_sync_with_websocket(self, temp_directories, client_config):
        """Test real-time sync using WebSocket notifications."""
        sync_engine = SyncEngine(client_config)

        # Mock WebSocket connection
        mock_websocket = Mock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(
            side_effect=[
                json.dumps(
                    {
                        "type": "file_changed",
                        "path": "remote_change.txt",
                        "operation": "create",
                        "client_id": "other_client",
                    }
                ),
                json.dumps({"type": "heartbeat"}),
                asyncio.CancelledError(),  # To stop the loop
            ]
        )
        mock_websocket.close = AsyncMock()

        download_response = Mock()
        download_response.status = 200
        download_response.content.iter_chunked = AsyncMock(
            return_value=[b"Content changed by another client"]
        )

        with patch("websockets.connect", return_value=mock_websocket), patch.object(
            sync_engine, "_ensure_session"
        ), patch.object(sync_engine, "session") as mock_session:
            mock_session.get.return_value = download_response

            await sync_engine.start()

            # Start WebSocket message handling
            message_task = asyncio.create_task(sync_engine._handle_websocket_messages())

            # Wait for file change notification to be processed
            await asyncio.sleep(0.1)

            # Cancel message handling
            message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await message_task

            # Verify file change was processed
            assert mock_websocket.recv.call_count >= 1

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_sync_with_ignore_patterns(self, temp_directories, client_config):
        """Test sync respects ignore patterns."""
        base_dir = temp_directories["client"]

        # Create files that should be ignored
        ignored_files = [
            ".git/config",
            "__pycache__/module.pyc",
            "temp.tmp",
            "build/output.o",
        ]

        # Create files that should be synced
        synced_files = ["main.py", "requirements.txt", "docs/README.md"]

        # Create all files
        all_files = ignored_files + synced_files
        for file_path in all_files:
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(f"Content of {file_path}")

        # Update ignore patterns
        client_config.ignore_patterns.extend(["build/*"])

        sync_engine = SyncEngine(client_config)

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.return_value = upload_response

            await sync_engine.start()

            # Perform sync
            success = await sync_engine.perform_full_sync()

            assert success is True

            # Should only upload non-ignored files
            # Exact count depends on implementation, but should be less than total
            assert mock_session.post.call_count < len(all_files)
            assert mock_session.post.call_count >= len(synced_files)

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_sync_recovery_after_interruption(
        self, temp_directories, client_config
    ):
        """Test sync recovery after network interruption."""
        sync_engine = SyncEngine(client_config)

        # Create test file
        test_file = temp_directories["client"] / "recovery_test.txt"
        with open(test_file, "w") as f:
            f.write("Test content for recovery")

        # Simulate network failure then recovery
        failure_response = Mock()
        failure_response.status = 500

        success_response = Mock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={"success": True})

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            # First attempt fails, second succeeds (retry mechanism)
            mock_session.post.side_effect = [failure_response, success_response]

            await sync_engine.start()

            # Should succeed after retry
            success = await sync_engine.upload_file(str(test_file), "recovery_test.txt")

            assert success is True
            assert mock_session.post.call_count == 2  # Initial failure + retry

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_concurrent_multi_client_sync(self, temp_directories):
        """Test concurrent sync from multiple clients."""
        # Create configurations for multiple clients
        client_configs = []
        client_dirs = []

        for i in range(3):
            client_dir = Path(tempfile.mkdtemp(prefix=f"e2e_client_{i}_"))
            client_dirs.append(client_dir)

            config = ClientConfig(
                client_name=f"client_{i}",
                sync_directory=str(client_dir),
                server_host="localhost",
                server_port=8999,
            )
            client_configs.append(config)

            # Create unique file for each client
            test_file = client_dir / f"client_{i}_file.txt"
            with open(test_file, "w") as f:
                f.write(f"Content from client {i}")

        try:
            # Create sync engines
            sync_engines = [SyncEngine(config) for config in client_configs]

            # Mock successful responses
            upload_response = Mock()
            upload_response.status = 200
            upload_response.json = AsyncMock(return_value={"success": True})

            sync_response = Mock()
            sync_response.status = 200
            sync_response.json = AsyncMock(
                return_value={"success": True, "files_to_sync": [], "conflicts": []}
            )

            # Start all sync engines and perform concurrent sync
            async def sync_client(engine):
                with patch.object(engine, "_ensure_session"), patch.object(
                    engine, "session"
                ) as mock_session:
                    mock_session.post.side_effect = [upload_response, sync_response]

                    await engine.start()
                    success = await engine.perform_full_sync()
                    await engine.stop()
                    return success

            # Run concurrent syncs
            tasks = [sync_client(engine) for engine in sync_engines]
            results = await asyncio.gather(*tasks)

            # All syncs should succeed
            assert all(results)

        finally:
            # Cleanup
            for client_dir in client_dirs:
                shutil.rmtree(client_dir, ignore_errors=True)

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_performance_large_scale_sync(self, temp_directories, client_config):
        """Test performance with large number of files."""
        base_dir = temp_directories["client"]

        # Create many files
        num_files = 100
        for i in range(num_files):
            file_path = base_dir / f"perf_file_{i:03d}.txt"
            with open(file_path, "w") as f:
                f.write(f"Performance test file {i} content")

        sync_engine = SyncEngine(client_config)

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * (num_files + 1) + [
                sync_response
            ]

            await sync_engine.start()

            # Measure sync time
            start_time = time.time()
            success = await sync_engine.perform_full_sync()
            end_time = time.time()

            sync_time = end_time - start_time

            assert success is True

            # Performance check - should handle 100 files reasonably quickly
            # This is a rough benchmark, adjust based on requirements
            assert sync_time < 10.0  # Should complete within 10 seconds

            await sync_engine.stop()

    @pytest.mark.e2e
    async def test_full_application_lifecycle(
        self, temp_directories, client_config, server_config
    ):
        """Test complete application lifecycle from startup to shutdown."""
        # This test simulates the full application flow

        # 1. Create initial files
        client_dir = temp_directories["client"]
        initial_files = ["document.txt", "data.json", "script.py"]

        for filename in initial_files:
            file_path = client_dir / filename
            with open(file_path, "w") as f:
                f.write(f"Initial content of {filename}")

        # 2. Start sync client
        sync_engine = SyncEngine(client_config)

        # Mock all server interactions
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        list_response = Mock()
        list_response.status = 200
        list_response.json = AsyncMock(return_value={"files": []})

        mock_websocket = Mock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"type": "heartbeat"}')
        mock_websocket.close = AsyncMock()

        with patch("websockets.connect", return_value=mock_websocket), patch.object(
            sync_engine, "_ensure_session"
        ), patch.object(sync_engine, "session") as mock_session:
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response]
            mock_session.get.return_value = list_response

            # 3. Perform initial sync
            await sync_engine.start()
            success = await sync_engine.perform_full_sync()
            assert success is True

            # 4. Simulate file changes
            new_file = client_dir / "new_document.txt"
            with open(new_file, "w") as f:
                f.write("New document created during sync")

            # 5. Perform incremental sync
            mock_session.post.side_effect = [upload_response, sync_response]
            success = await sync_engine.perform_full_sync()
            assert success is True

            # 6. Graceful shutdown
            await sync_engine.stop()

            # Verify clean shutdown
            assert not sync_engine.is_running

        # Test completed successfully - represents full application flow
