"""Custom exceptions for the file synchronization system."""

from typing import Optional


class SyncError(Exception):
    """Base exception for sync-related errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "SYNC_ERROR"
        self.details = details or ""


class ConnectionError(SyncError):
    """Raised when connection to server fails."""

    def __init__(
        self, message: str, host: str, port: int, details: Optional[str] = None
    ):
        super().__init__(message, "CONNECTION_ERROR", details)
        self.host = host
        self.port = port


class WebSocketError(SyncError):
    """Raised when WebSocket operations fail."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, "WEBSOCKET_ERROR", details)


class FileOperationError(SyncError):
    """Raised when file operations fail."""

    def __init__(
        self,
        message: str,
        file_path: str,
        operation: str,
        details: Optional[str] = None,
    ):
        super().__init__(message, "FILE_OPERATION_ERROR", details)
        self.file_path = file_path
        self.operation = operation


class AuthenticationError(SyncError):
    """Raised when authentication fails."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, "AUTHENTICATION_ERROR", details)


class ConfigurationError(SyncError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_field: Optional[str] = None,
        details: Optional[str] = None,
    ):
        super().__init__(message, "CONFIGURATION_ERROR", details)
        self.config_field = config_field


class DatabaseError(SyncError):
    """Raised when database operations fail."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[str] = None,
    ):
        super().__init__(message, "DATABASE_ERROR", details)
        self.operation = operation


class ConflictError(SyncError):
    """Raised when file conflicts are detected."""

    def __init__(
        self,
        message: str,
        file_path: str,
        conflict_type: str,
        details: Optional[str] = None,
    ):
        super().__init__(message, "CONFLICT_ERROR", details)
        self.file_path = file_path
        self.conflict_type = conflict_type


class ValidationError(SyncError):
    """Raised when data validation fails."""

    def __init__(
        self, message: str, field: Optional[str] = None, details: Optional[str] = None
    ):
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field


class ServerError(SyncError):
    """Raised when server operations fail."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
    ):
        super().__init__(message, "SERVER_ERROR", details)
        self.status_code = status_code


class FileNotFoundError(FileOperationError):
    """Raised when a file is not found."""

    def __init__(self, file_path: str, details: Optional[str] = None):
        super().__init__(f"File not found: {file_path}", file_path, "read", details)
        self.error_code = "FILE_NOT_FOUND"


class PermissionError(FileOperationError):
    """Raised when file permissions are insufficient."""

    def __init__(self, file_path: str, operation: str, details: Optional[str] = None):
        super().__init__(
            f"Permission denied for {operation} on {file_path}",
            file_path,
            operation,
            details,
        )
        self.error_code = "PERMISSION_ERROR"


class DiskSpaceError(FileOperationError):
    """Raised when disk space is insufficient."""

    def __init__(self, file_path: str, details: Optional[str] = None):
        super().__init__(
            f"Insufficient disk space for {file_path}", file_path, "write", details
        )
        self.error_code = "DISK_SPACE_ERROR"
