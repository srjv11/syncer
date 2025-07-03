# Shared Protocols Documentation

## Overview

`shared/protocols.py` defines the WebSocket communication protocol and message structures for real-time communication between clients and the server. These models ensure consistent message formatting and type safety for live synchronization.

## Core Message Types

### MessageType Enumeration

Defines all supported WebSocket message types:

```python
class MessageType(str, Enum):
    CLIENT_CONNECT = "client_connect"        # Initial client connection
    CLIENT_DISCONNECT = "client_disconnect"  # Client disconnection
    FILE_CHANGED = "file_changed"           # File modification notification
    SYNC_REQUEST = "sync_request"           # Synchronization request
    SYNC_RESPONSE = "sync_response"         # Synchronization response
    HEARTBEAT = "heartbeat"                 # Connection health check
    ERROR = "error"                         # Error notification
```

**Purpose**: Type-safe message identification and routing
**String Inheritance**: Enables direct JSON serialization and comparison
**Extensibility**: Easy addition of new message types

### Message Categories

#### Connection Management

- **CLIENT_CONNECT**: Initial handshake when client connects
- **CLIENT_DISCONNECT**: Notification when client disconnects
- **HEARTBEAT**: Periodic connection health verification

#### File Operations

- **FILE_CHANGED**: Real-time file modification notifications
- **SYNC_REQUEST**: Request for synchronization analysis
- **SYNC_RESPONSE**: Server response with sync instructions

#### Error Handling

- **ERROR**: Error notifications and debugging information

## Base Message Structure

### WebSocketMessage

Universal container for all WebSocket communications:

```python
class WebSocketMessage(BaseModel):
    type: MessageType           # Message type identifier
    data: Dict[str, Any]        # Message payload data
    client_id: str              # Originating client
    timestamp: str              # Message creation time (ISO format)
```

**Design Principles**:

- **Uniform Structure**: All messages use same base format
- **Type Safety**: Message type clearly identified
- **Payload Flexibility**: Data field accommodates any message-specific content
- **Traceability**: Client ID and timestamp for debugging and routing
- **Serialization**: JSON-compatible for WebSocket transmission

**Message Flow**:

1. Create specific message content
2. Wrap in WebSocketMessage envelope
3. Serialize to JSON
4. Transmit via WebSocket
5. Deserialize and route based on type

## Connection Protocol Messages

### ConnectionRequest

Initial client connection handshake:

```python
class ConnectionRequest(BaseModel):
    client_id: str              # Unique client identifier
    client_name: str            # Human-readable client name
    sync_root: str              # Client's sync directory path
    api_key: str = ""           # Optional authentication token
```

**Purpose**: Establishes client identity and capabilities
**Process**:

1. Client generates unique ID (name + timestamp)
2. Sends connection request with credentials
3. Server validates and registers client
4. Connection established for ongoing communication

**Security**: API key field for optional authentication
**Identification**: Combination of ID and name for client tracking

### ConnectionResponse

Server response to connection request:

```python
class ConnectionResponse(BaseModel):
    success: bool               # Connection establishment status
    message: str                # Descriptive status message
    server_time: str            # Server timestamp (ISO format)
```

**Purpose**: Confirms successful connection establishment
**Contents**:

- **Success Flag**: Indicates connection acceptance/rejection
- **Status Message**: Human-readable connection status
- **Server Time**: Enables client-server time synchronization

**Error Handling**: Failed connections include error details in message

## Health Monitoring Messages

### HeartbeatMessage

Connection health verification:

```python
class HeartbeatMessage(BaseModel):
    client_id: str              # Client sending heartbeat
    timestamp: str              # Heartbeat generation time
```

**Purpose**: Maintains connection health and detects disconnections
**Frequency**: Typically sent every 30 seconds
**Bidirectional**: Both client and server can initiate heartbeats

**Connection Management**:

- **Client to Server**: "I'm still alive"
- **Server to Client**: "Please respond if alive"
- **Timeout Detection**: Missing heartbeats indicate connection issues
- **Reconnection**: Triggers reconnection attempts on timeout

## Error Communication

### ErrorMessage

Standardized error reporting:

```python
class ErrorMessage(BaseModel):
    error_code: str             # Machine-readable error identifier
    message: str                # Human-readable error description
    details: str = ""           # Additional error context
```

**Error Categories**:

- **Connection Errors**: Network and authentication issues
- **Protocol Errors**: Invalid message format or type
- **Operation Errors**: File operation failures
- **System Errors**: Server-side processing errors

**Usage Pattern**:

1. Error occurs during message processing
2. Error details wrapped in ErrorMessage
3. Sent to client with ERROR message type
4. Client handles error appropriately

## Message Flow Patterns

### Client Connection Flow

```
1. Client -> Server: WebSocketMessage{
     type: CLIENT_CONNECT,
     data: ConnectionRequest{...},
     client_id: "client-123",
     timestamp: "2023-..."
   }

2. Server -> Client: WebSocketMessage{
     type: CLIENT_CONNECT,
     data: ConnectionResponse{
       success: true,
       message: "Connected successfully"
     },
     client_id: "server",
     timestamp: "2023-..."
   }
```

### File Change Notification

```
1. Client A -> Server: WebSocketMessage{
     type: FILE_CHANGED,
     data: {
       operation: "update",
       file_path: "document.txt",
       client_id: "client-A"
     },
     client_id: "client-A",
     timestamp: "2023-..."
   }

2. Server -> Client B: WebSocketMessage{
     type: FILE_CHANGED,
     data: {
       operation: "update",
       file_path: "document.txt",
       client_id: "client-A"
     },
     client_id: "server",
     timestamp: "2023-..."
   }
```

### Heartbeat Exchange

```
1. Client -> Server: WebSocketMessage{
     type: HEARTBEAT,
     data: HeartbeatMessage{
       client_id: "client-123",
       timestamp: "2023-..."
     },
     client_id: "client-123",
     timestamp: "2023-..."
   }

2. Server -> Client: WebSocketMessage{
     type: HEARTBEAT,
     data: {
       timestamp: "2023-..."
     },
     client_id: "server",
     timestamp: "2023-..."
   }
```

## Protocol Design Principles

### Type Safety

- **Pydantic Models**: Automatic validation and type checking
- **Enum Types**: Prevents invalid message types
- **Field Validation**: Ensures required fields are present
- **Runtime Checks**: Validates message structure on receipt

### Extensibility

- **Flexible Data Field**: Accommodates message-specific payloads
- **Optional Fields**: Backward compatibility for protocol evolution
- **Versioning Ready**: Structure supports protocol versioning
- **Custom Messages**: Easy addition of new message types

### Reliability

- **Message Identification**: Every message has type and timestamp
- **Client Tracking**: Messages traced to originating client
- **Error Handling**: Structured error reporting and recovery
- **Connection Monitoring**: Heartbeat system for health checks

### Performance

- **JSON Serialization**: Efficient network transmission
- **Minimal Overhead**: Lightweight message structure
- **Batch Capable**: Protocol supports message batching
- **Compression Ready**: JSON format supports compression

## Integration Points

### WebSocket Manager

- Message parsing and validation
- Type-based message routing
- Error handling and reporting
- Connection lifecycle management

### Client Sync Engine

- Outbound message creation
- Inbound message processing
- Connection establishment
- Heartbeat management

### Server Components

- Message broadcasting
- Client registration
- Error reporting
- Connection monitoring

## Security Considerations

### Authentication

- **API Key Support**: Optional token-based authentication
- **Client Identification**: Unique client ID for tracking
- **Message Attribution**: All messages traced to source
- **Access Control**: Server can validate client permissions

### Validation

- **Message Structure**: All messages validated against schemas
- **Field Sanitization**: Input data cleaned and validated
- **Type Checking**: Prevents type confusion attacks
- **Size Limits**: Message size restrictions prevent abuse

### Privacy

- **Client Isolation**: Messages not shared inappropriately
- **Secure Transmission**: WebSocket over TLS in production
- **Audit Trail**: All messages logged for security analysis
- **Error Handling**: No sensitive data in error messages

## Development and Debugging

### Message Logging

- Structured logging of all messages
- Client identification in logs
- Timestamp correlation for debugging
- Error message preservation

### Testing Support

- Mock message creation
- Protocol validation testing
- Error condition simulation
- Performance testing capabilities

### Monitoring

- Message rate tracking
- Error frequency monitoring
- Connection health metrics
- Protocol compliance checking
