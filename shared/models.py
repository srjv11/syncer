from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SyncOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"


class FileInfo(BaseModel):
    path: str
    size: int
    checksum: str
    modified_time: datetime
    is_directory: bool = False


class SyncMessage(BaseModel):
    operation: SyncOperation
    file_info: FileInfo
    client_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    old_path: Optional[str] = None  # For move operations


class ClientInfo(BaseModel):
    client_id: str
    name: str
    sync_root: str
    last_seen: datetime
    is_online: bool = True


class SyncRequest(BaseModel):
    client_id: str
    files: List[FileInfo]
    sync_root: str


class SyncResponse(BaseModel):
    success: bool
    message: str
    files_to_sync: List[FileInfo] = []
    conflicts: List[str] = []


class ConflictResolution(BaseModel):
    file_path: str
    resolution: str  # "local", "remote", "merge"
    timestamp: datetime


class ServerConfig(BaseModel):
    host: str = "localhost"
    port: int = 8000
    sync_directory: str = "./sync_data"
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    allowed_extensions: Optional[List[str]] = None

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("sync_directory")
    @classmethod
    def validate_sync_directory(cls, v):
        if not v or not v.strip():
            raise ValueError("Sync directory cannot be empty")

        path = Path(v)
        if path.exists() and not path.is_dir():
            raise ValueError(f"Sync directory path exists but is not a directory: {v}")

        # Try to create directory to check permissions
        try:
            path.mkdir(parents=True, exist_ok=True)
            # Test write permissions
            test_file = path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except PermissionError:
            raise ValueError(f"No write permission for sync directory: {v}")
        except OSError as e:
            raise ValueError(f"Cannot create sync directory: {v} - {e}")

        return str(path.absolute())

    @field_validator("max_file_size")
    @classmethod
    def validate_max_file_size(cls, v):
        if v <= 0:
            raise ValueError("Max file size must be positive")
        if v > 10 * 1024 * 1024 * 1024:  # 10GB
            raise ValueError("Max file size too large (max 10GB)")
        return v

    @field_validator("allowed_extensions")
    @classmethod
    def validate_allowed_extensions(cls, v):
        if v is not None:
            for ext in v:
                if not ext.startswith("."):
                    raise ValueError(f"File extension must start with dot: {ext}")
        return v


class ClientConfig(BaseModel):
    server_host: str = "localhost"
    server_port: int = 8000
    client_name: str
    sync_directory: str
    ignore_patterns: List[str] = [".git", "__pycache__", "*.tmp"]
    api_key: Optional[str] = None

    @field_validator("server_host")
    @classmethod
    def validate_server_host(cls, v):
        if not v or not v.strip():
            raise ValueError("Server host cannot be empty")
        return v.strip()

    @field_validator("server_port")
    @classmethod
    def validate_server_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError("Server port must be between 1 and 65535")
        return v

    @field_validator("client_name")
    @classmethod
    def validate_client_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Client name cannot be empty")

        # Check for invalid characters
        invalid_chars = '<>:"/\\|?*'
        if any(char in v for char in invalid_chars):
            raise ValueError(
                f"Client name contains invalid characters: {invalid_chars}"
            )

        if len(v.strip()) > 50:
            raise ValueError("Client name too long (max 50 characters)")

        return v.strip()

    @field_validator("sync_directory")
    @classmethod
    def validate_sync_directory(cls, v):
        if not v or not v.strip():
            raise ValueError("Sync directory cannot be empty")

        path = Path(v)
        if path.exists() and not path.is_dir():
            raise ValueError(f"Sync directory path exists but is not a directory: {v}")

        # Try to create directory to check permissions
        try:
            path.mkdir(parents=True, exist_ok=True)
            # Test write permissions
            test_file = path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except PermissionError:
            raise ValueError(f"No write permission for sync directory: {v}")
        except OSError as e:
            raise ValueError(f"Cannot create sync directory: {v} - {e}")

        return str(path.absolute())

    @field_validator("ignore_patterns")
    @classmethod
    def validate_ignore_patterns(cls, v):
        if not isinstance(v, list):
            raise ValueError("Ignore patterns must be a list")

        for pattern in v:
            if not isinstance(pattern, str):
                raise ValueError("All ignore patterns must be strings")
            if not pattern.strip():
                raise ValueError("Ignore patterns cannot be empty")

        return v

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v):
        if v is not None:
            if len(v) < 8:
                raise ValueError("API key too short (minimum 8 characters)")
            if len(v) > 256:
                raise ValueError("API key too long (maximum 256 characters)")
        return v
