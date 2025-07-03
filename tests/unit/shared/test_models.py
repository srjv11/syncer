"""Unit tests for shared models."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.models import (
    ClientConfig,
    ClientInfo,
    ConflictResolution,
    FileInfo,
    ServerConfig,
    SyncMessage,
    SyncOperation,
    SyncRequest,
    SyncResponse,
)


class TestSyncOperation:
    """Test SyncOperation enum."""

    def test_sync_operation_values(self):
        """Test SyncOperation enum values."""
        assert SyncOperation.CREATE == "create"
        assert SyncOperation.UPDATE == "update"
        assert SyncOperation.DELETE == "delete"
        assert SyncOperation.MOVE == "move"

    def test_sync_operation_membership(self):
        """Test SyncOperation membership."""
        assert "create" in SyncOperation
        assert "invalid" not in SyncOperation


class TestFileInfo:
    """Test FileInfo model."""

    def test_file_info_creation(self):
        """Test FileInfo creation with valid data."""
        now = datetime.now()
        file_info = FileInfo(
            path="test/file.txt",
            size=1024,
            checksum="abc123",
            modified_time=now,
            is_directory=False,
        )

        assert file_info.path == "test/file.txt"
        assert file_info.size == 1024
        assert file_info.checksum == "abc123"
        assert file_info.modified_time == now
        assert file_info.is_directory is False

    def test_file_info_directory(self):
        """Test FileInfo for directory."""
        now = datetime.now()
        file_info = FileInfo(
            path="test/directory",
            size=0,
            checksum="",
            modified_time=now,
            is_directory=True,
        )

        assert file_info.is_directory is True
        assert file_info.size == 0
        assert file_info.checksum == ""

    def test_file_info_default_directory(self):
        """Test FileInfo default is_directory value."""
        file_info = FileInfo(
            path="test.txt", size=100, checksum="hash", modified_time=datetime.now()
        )

        assert file_info.is_directory is False

    def test_file_info_validation_errors(self):
        """Test FileInfo validation errors."""
        now = datetime.now()

        # Missing required fields
        with pytest.raises(ValidationError):
            FileInfo()

        # Invalid size (negative)
        with pytest.raises(ValidationError):
            FileInfo(path="test.txt", size=-1, checksum="hash", modified_time=now)


class TestSyncMessage:
    """Test SyncMessage model."""

    def test_sync_message_creation(self):
        """Test SyncMessage creation."""
        file_info = FileInfo(
            path="test.txt", size=100, checksum="hash", modified_time=datetime.now()
        )

        message = SyncMessage(
            operation=SyncOperation.CREATE, file_info=file_info, client_id="client123"
        )

        assert message.operation == SyncOperation.CREATE
        assert message.file_info == file_info
        assert message.client_id == "client123"
        assert isinstance(message.timestamp, datetime)
        assert message.old_path is None

    def test_sync_message_with_move(self):
        """Test SyncMessage for move operation."""
        file_info = FileInfo(
            path="new/path.txt", size=100, checksum="hash", modified_time=datetime.now()
        )

        message = SyncMessage(
            operation=SyncOperation.MOVE,
            file_info=file_info,
            client_id="client123",
            old_path="old/path.txt",
        )

        assert message.operation == SyncOperation.MOVE
        assert message.old_path == "old/path.txt"

    def test_sync_message_default_timestamp(self):
        """Test SyncMessage default timestamp."""
        file_info = FileInfo(
            path="test.txt", size=100, checksum="hash", modified_time=datetime.now()
        )

        message = SyncMessage(
            operation=SyncOperation.UPDATE, file_info=file_info, client_id="client123"
        )

        # Timestamp should be recent
        time_diff = datetime.now() - message.timestamp
        assert time_diff.total_seconds() < 1


class TestClientInfo:
    """Test ClientInfo model."""

    def test_client_info_creation(self):
        """Test ClientInfo creation."""
        now = datetime.now()
        client_info = ClientInfo(
            client_id="client123",
            name="Test Client",
            sync_root="/home/user/sync",
            last_seen=now,
            is_online=True,
        )

        assert client_info.client_id == "client123"
        assert client_info.name == "Test Client"
        assert client_info.sync_root == "/home/user/sync"
        assert client_info.last_seen == now
        assert client_info.is_online is True

    def test_client_info_default_online(self):
        """Test ClientInfo default online status."""
        client_info = ClientInfo(
            client_id="client123",
            name="Test Client",
            sync_root="/home/user/sync",
            last_seen=datetime.now(),
        )

        assert client_info.is_online is True


class TestSyncRequest:
    """Test SyncRequest model."""

    def test_sync_request_creation(self):
        """Test SyncRequest creation."""
        files = [
            FileInfo(
                path="file1.txt",
                size=100,
                checksum="hash1",
                modified_time=datetime.now(),
            ),
            FileInfo(
                path="file2.txt",
                size=200,
                checksum="hash2",
                modified_time=datetime.now(),
            ),
        ]

        request = SyncRequest(
            client_id="client123", files=files, sync_root="/home/user/sync"
        )

        assert request.client_id == "client123"
        assert len(request.files) == 2
        assert request.sync_root == "/home/user/sync"

    def test_sync_request_empty_files(self):
        """Test SyncRequest with empty file list."""
        request = SyncRequest(
            client_id="client123", files=[], sync_root="/home/user/sync"
        )

        assert len(request.files) == 0


class TestSyncResponse:
    """Test SyncResponse model."""

    def test_sync_response_creation(self):
        """Test SyncResponse creation."""
        files_to_sync = [
            FileInfo(
                path="file1.txt",
                size=100,
                checksum="hash1",
                modified_time=datetime.now(),
            )
        ]

        response = SyncResponse(
            success=True,
            message="Sync completed",
            files_to_sync=files_to_sync,
            conflicts=["file2.txt"],
        )

        assert response.success is True
        assert response.message == "Sync completed"
        assert len(response.files_to_sync) == 1
        assert response.conflicts == ["file2.txt"]

    def test_sync_response_defaults(self):
        """Test SyncResponse default values."""
        response = SyncResponse(success=False, message="Error occurred")

        assert response.success is False
        assert response.message == "Error occurred"
        assert response.files_to_sync == []
        assert response.conflicts == []


class TestConflictResolution:
    """Test ConflictResolution model."""

    def test_conflict_resolution_creation(self):
        """Test ConflictResolution creation."""
        now = datetime.now()
        resolution = ConflictResolution(
            file_path="conflicted.txt", resolution="local", timestamp=now
        )

        assert resolution.file_path == "conflicted.txt"
        assert resolution.resolution == "local"
        assert resolution.timestamp == now

    def test_conflict_resolution_strategies(self):
        """Test different conflict resolution strategies."""
        strategies = ["local", "remote", "merge"]

        for strategy in strategies:
            resolution = ConflictResolution(
                file_path="test.txt", resolution=strategy, timestamp=datetime.now()
            )
            assert resolution.resolution == strategy


class TestServerConfig:
    """Test ServerConfig model."""

    def test_server_config_defaults(self):
        """Test ServerConfig default values."""
        config = ServerConfig()

        assert config.host == "localhost"
        assert config.port == 8000
        assert config.sync_directory == "./sync_data"
        assert config.max_file_size == 100 * 1024 * 1024
        assert config.allowed_extensions is None

    def test_server_config_custom_values(self):
        """Test ServerConfig with custom values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_sync_dir = os.path.join(temp_dir, "custom_sync")
            config = ServerConfig(
                host="0.0.0.0",
                port=9000,
                sync_directory=custom_sync_dir,
                max_file_size=50 * 1024 * 1024,
                allowed_extensions=[".txt", ".py"],
            )

            assert config.host == "0.0.0.0"
            assert config.port == 9000
            assert config.sync_directory == custom_sync_dir
            assert config.max_file_size == 50 * 1024 * 1024
            assert config.allowed_extensions == [".txt", ".py"]

    def test_server_config_validation_host(self):
        """Test ServerConfig host validation."""
        # Empty host
        with pytest.raises(ValidationError, match="Host cannot be empty"):
            ServerConfig(host="")

        # Whitespace only host
        with pytest.raises(ValidationError, match="Host cannot be empty"):
            ServerConfig(host="   ")

    def test_server_config_validation_port(self):
        """Test ServerConfig port validation."""
        # Port too low
        with pytest.raises(ValidationError, match="Port must be between 1 and 65535"):
            ServerConfig(port=0)

        # Port too high
        with pytest.raises(ValidationError, match="Port must be between 1 and 65535"):
            ServerConfig(port=65536)

    def test_server_config_validation_sync_directory(self):
        """Test ServerConfig sync directory validation."""
        # Empty directory
        with pytest.raises(ValidationError, match="Sync directory cannot be empty"):
            ServerConfig(sync_directory="")

        # Directory exists but is a file
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValidationError, match="not a directory"):
                ServerConfig(sync_directory=temp_file.name)

    def test_server_config_validation_max_file_size(self):
        """Test ServerConfig max file size validation."""
        # Negative size
        with pytest.raises(ValidationError, match="Max file size must be positive"):
            ServerConfig(max_file_size=-1)

        # Zero size
        with pytest.raises(ValidationError, match="Max file size must be positive"):
            ServerConfig(max_file_size=0)

        # Too large (>10GB)
        with pytest.raises(ValidationError, match="Max file size too large"):
            ServerConfig(max_file_size=11 * 1024 * 1024 * 1024)

    def test_server_config_validation_allowed_extensions(self):
        """Test ServerConfig allowed extensions validation."""
        # Extension without dot
        with pytest.raises(ValidationError, match="File extension must start with dot"):
            ServerConfig(allowed_extensions=["txt", ".py"])

    def test_server_config_directory_creation(self):
        """Test ServerConfig creates directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = Path(temp_dir) / "new_sync_dir"

            config = ServerConfig(sync_directory=str(new_dir))

            assert Path(config.sync_directory).exists()
            assert Path(config.sync_directory).is_dir()


class TestClientConfig:
    """Test ClientConfig model."""

    def test_client_config_creation(self):
        """Test ClientConfig creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ClientConfig(
                client_name="test_client",
                sync_directory=temp_dir,
                server_host="localhost",
                server_port=8000,
            )

            assert config.client_name == "test_client"
            assert config.sync_directory == str(Path(temp_dir).absolute())
            assert config.server_host == "localhost"
            assert config.server_port == 8000

    def test_client_config_defaults(self):
        """Test ClientConfig default values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ClientConfig(client_name="test_client", sync_directory=temp_dir)

            assert config.server_host == "localhost"
            assert config.server_port == 8000
            assert config.ignore_patterns == [".git", "__pycache__", "*.tmp"]
            assert config.api_key is None

    def test_client_config_validation_server_host(self):
        """Test ClientConfig server host validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Empty host
            with pytest.raises(ValidationError, match="Server host cannot be empty"):
                ClientConfig(
                    client_name="test", sync_directory=temp_dir, server_host=""
                )

    def test_client_config_validation_server_port(self):
        """Test ClientConfig server port validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Invalid port
            with pytest.raises(
                ValidationError, match="Server port must be between 1 and 65535"
            ):
                ClientConfig(client_name="test", sync_directory=temp_dir, server_port=0)

    def test_client_config_validation_client_name(self):
        """Test ClientConfig client name validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Empty name
            with pytest.raises(ValidationError, match="Client name cannot be empty"):
                ClientConfig(client_name="", sync_directory=temp_dir)

            # Name with invalid characters
            with pytest.raises(ValidationError, match="invalid characters"):
                ClientConfig(client_name="client<>name", sync_directory=temp_dir)

            # Name too long
            with pytest.raises(ValidationError, match="Client name too long"):
                ClientConfig(client_name="x" * 51, sync_directory=temp_dir)

    def test_client_config_validation_sync_directory(self):
        """Test ClientConfig sync directory validation."""
        # Empty directory
        with pytest.raises(ValidationError, match="Sync directory cannot be empty"):
            ClientConfig(client_name="test", sync_directory="")

        # Directory exists but is a file
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValidationError, match="not a directory"):
                ClientConfig(client_name="test", sync_directory=temp_file.name)

    def test_client_config_validation_ignore_patterns(self):
        """Test ClientConfig ignore patterns validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Non-list patterns
            with pytest.raises(ValidationError, match="Input should be a valid list"):
                ClientConfig(
                    client_name="test",
                    sync_directory=temp_dir,
                    ignore_patterns="*.tmp",  # type: ignore
                )

            # Empty pattern in list
            with pytest.raises(
                ValidationError, match="Ignore patterns cannot be empty"
            ):
                ClientConfig(
                    client_name="test",
                    sync_directory=temp_dir,
                    ignore_patterns=["*.tmp", ""],
                )

    def test_client_config_validation_api_key(self):
        """Test ClientConfig API key validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Too short API key
            with pytest.raises(ValidationError, match="API key too short"):
                ClientConfig(
                    client_name="test", sync_directory=temp_dir, api_key="short"
                )

            # Too long API key
            with pytest.raises(ValidationError, match="API key too long"):
                ClientConfig(
                    client_name="test", sync_directory=temp_dir, api_key="x" * 257
                )

    def test_client_config_directory_creation(self):
        """Test ClientConfig creates directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = Path(temp_dir) / "new_client_dir"

            config = ClientConfig(client_name="test", sync_directory=str(new_dir))

            assert Path(config.sync_directory).exists()
            assert Path(config.sync_directory).is_dir()


class TestModelSerialization:
    """Test model serialization/deserialization."""

    def test_file_info_dict_conversion(self):
        """Test FileInfo dict conversion."""
        now = datetime.now()
        file_info = FileInfo(
            path="test.txt",
            size=100,
            checksum="hash",
            modified_time=now,
            is_directory=False,
        )

        # Convert to dict
        data = file_info.model_dump()

        assert data["path"] == "test.txt"
        assert data["size"] == 100
        assert data["checksum"] == "hash"
        assert data["is_directory"] is False

        # Create from dict
        restored = FileInfo(**data)
        assert restored == file_info

    def test_sync_request_json_conversion(self):
        """Test SyncRequest JSON conversion."""
        files = [
            FileInfo(
                path="file1.txt",
                size=100,
                checksum="hash1",
                modified_time=datetime.now(),
            )
        ]

        request = SyncRequest(client_id="client123", files=files, sync_root="/sync")

        # Convert to JSON
        json_data = request.model_dump_json()
        assert isinstance(json_data, str)

        # Parse JSON
        import json

        parsed = json.loads(json_data)
        assert parsed["client_id"] == "client123"
        assert len(parsed["files"]) == 1

    def test_config_validation_with_real_paths(self):
        """Test config validation with real file system paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Server config
            server_config = ServerConfig(sync_directory=temp_dir)
            assert Path(server_config.sync_directory).exists()

            # Client config
            client_config = ClientConfig(client_name="test", sync_directory=temp_dir)
            assert Path(client_config.sync_directory).exists()
