from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel


class MessageType(str, Enum):
    CLIENT_CONNECT = "client_connect"
    CLIENT_DISCONNECT = "client_disconnect"
    FILE_CHANGED = "file_changed"
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


class WebSocketMessage(BaseModel):
    type: MessageType
    data: Dict[str, Any]
    client_id: str
    timestamp: str


class ConnectionRequest(BaseModel):
    client_id: str
    client_name: str
    sync_root: str
    api_key: str = ""


class ConnectionResponse(BaseModel):
    success: bool
    message: str
    server_time: str


class HeartbeatMessage(BaseModel):
    client_id: str
    timestamp: str


class ErrorMessage(BaseModel):
    error_code: str
    message: str
    details: str = ""
