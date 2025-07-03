"""Pytest configuration and shared fixtures."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

import aiofiles
import pytest

from shared.metrics import MetricsCollector
from shared.models import ClientConfig, FileInfo, ServerConfig


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def client_temp_dir():
    """Create a temporary directory for client testing."""
    temp_path = tempfile.mkdtemp(prefix="client_")
    yield Path(temp_path)
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def server_temp_dir():
    """Create a temporary directory for server testing."""
    temp_path = tempfile.mkdtemp(prefix="server_")
    yield Path(temp_path)
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_client_config(client_temp_dir):
    """Create a sample client configuration."""
    return ClientConfig(
        client_name="test_client",
        sync_directory=str(client_temp_dir),
        server_host="localhost",
        server_port=8000,
        ignore_patterns=[".git", "*.tmp", "__pycache__"],
    )


@pytest.fixture
def sample_server_config(server_temp_dir):
    """Create a sample server configuration."""
    return ServerConfig(
        host="localhost",
        port=8000,
        sync_directory=str(server_temp_dir),
        max_file_size=100 * 1024 * 1024,
    )


@pytest.fixture
async def sample_files(temp_dir):
    """Create sample files for testing."""
    files = {}

    # Text file
    text_file = temp_dir / "sample.txt"
    content = "This is a sample text file for testing.\nLine 2\nLine 3"
    async with aiofiles.open(text_file, "w") as f:
        await f.write(content)
    files["text"] = text_file

    # Binary file
    binary_file = temp_dir / "sample.bin"
    binary_content = b"\x00\x01\x02\x03\x04\x05" * 100
    async with aiofiles.open(binary_file, "wb") as f:
        await f.write(binary_content)
    files["binary"] = binary_file

    # JSON file
    json_file = temp_dir / "config.json"
    json_content = '{"test": true, "value": 42, "items": [1, 2, 3]}'
    async with aiofiles.open(json_file, "w") as f:
        await f.write(json_content)
    files["json"] = json_file

    # Large file
    large_file = temp_dir / "large.dat"
    large_content = "x" * (1024 * 1024)  # 1MB
    async with aiofiles.open(large_file, "w") as f:
        await f.write(large_content)
    files["large"] = large_file

    # Directory
    sub_dir = temp_dir / "subdir"
    sub_dir.mkdir()
    sub_file = sub_dir / "nested.txt"
    async with aiofiles.open(sub_file, "w") as f:
        await f.write("Nested file content")
    files["subdir"] = sub_dir
    files["nested"] = sub_file

    return files


@pytest.fixture
def sample_file_info():
    """Create sample FileInfo objects."""
    from datetime import datetime

    return [
        FileInfo(
            path="sample.txt",
            size=1024,
            checksum="abc123",
            modified_time=datetime.now(),
            is_directory=False,
        ),
        FileInfo(
            path="data/config.json",
            size=256,
            checksum="def456",
            modified_time=datetime.now(),
            is_directory=False,
        ),
        FileInfo(
            path="images",
            size=0,
            checksum="",
            modified_time=datetime.now(),
            is_directory=True,
        ),
    ]


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp session."""
    session = Mock()
    response = Mock()
    response.status = 200
    response.json = Mock(return_value={"success": True})
    response.text = Mock(return_value="OK")
    response.content.iter_chunked = Mock(return_value=[b"chunk1", b"chunk2"])

    session.post = Mock(return_value=response)
    session.get = Mock(return_value=response)
    session.delete = Mock(return_value=response)

    return session


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    websocket = Mock()
    websocket.send = Mock()
    websocket.recv = Mock(return_value='{"type": "heartbeat"}')
    websocket.close = Mock()
    websocket.ping = Mock()
    return websocket


@pytest.fixture
def metrics_collector():
    """Create a clean metrics collector for testing."""
    collector = MetricsCollector()
    yield collector
    collector.clear_metrics()


@pytest.fixture
async def database_file(temp_dir):
    """Create a temporary database file."""
    db_file = temp_dir / "test.db"
    yield db_file
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def ignore_patterns():
    """Common ignore patterns for testing."""
    return [".git", "__pycache__", "*.tmp", "*.log", ".pytest_cache", "node_modules"]


class MockFileSystemEvent:
    """Mock file system event for testing."""

    def __init__(
        self,
        event_type: str,
        src_path: str,
        is_directory: bool = False,
        dest_path: Optional[str] = None,
    ):
        self.event_type = event_type
        self.src_path = src_path
        self.is_directory = is_directory
        self.dest_path = dest_path


@pytest.fixture
def mock_file_events():
    """Create mock file system events."""
    return {
        "created": MockFileSystemEvent("created", "/test/new_file.txt"),
        "modified": MockFileSystemEvent("modified", "/test/existing_file.txt"),
        "deleted": MockFileSystemEvent("deleted", "/test/deleted_file.txt"),
        "moved": MockFileSystemEvent(
            "moved", "/test/old_name.txt", dest_path="/test/new_name.txt"
        ),
        "dir_created": MockFileSystemEvent(
            "created", "/test/new_dir", is_directory=True
        ),
    }


@pytest.fixture
def performance_test_data():
    """Generate data for performance testing."""
    return {
        "small_files": [f"file_{i}.txt" for i in range(100)],
        "medium_files": [f"data_{i}.json" for i in range(50)],
        "large_files": [f"archive_{i}.zip" for i in range(10)],
        "nested_structure": {
            "level1": {"level2": {"level3": ["deep_file_1.txt", "deep_file_2.txt"]}}
        },
    }


@pytest.fixture(scope="session")
def test_assets_dir():
    """Directory containing test assets."""
    assets_dir = Path(__file__).parent / "fixtures"
    assets_dir.mkdir(exist_ok=True)
    return assets_dir


# Async context manager helpers
class AsyncMock:
    """Helper class for async context managers in tests."""

    def __init__(self, return_value=None):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def async_mock():
    """Create an async mock context manager."""
    return AsyncMock


# Network testing helpers
@pytest.fixture
def free_port():
    """Find a free port for testing."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def test_server_url(free_port):
    """Create a test server URL."""
    return f"http://localhost:{free_port}"


# File operation helpers
async def create_test_file(
    path: Path, content: str = "test content", binary: bool = False
):
    """Helper to create test files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if binary else "w"
    data = content.encode() if binary else content

    async with aiofiles.open(path, mode) as f:
        await f.write(data)


async def read_test_file(path: Path, binary: bool = False) -> str | bytes:
    """Helper to read test files."""
    mode = "rb" if binary else "r"
    async with aiofiles.open(path, mode) as f:
        return await f.read()


@pytest.fixture
def file_helpers():
    """Provide file operation helpers."""
    return {"create": create_test_file, "read": read_test_file}
