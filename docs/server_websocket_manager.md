# Server WebSocket Manager Documentation

## Overview

`server/websocket_manager.py` manages real-time WebSocket connections between the server and clients. It handles connection lifecycle, message routing, and broadcasts for live file synchronization updates.

## Key Components

### WebSocketManager Class

Central manager for all WebSocket communications and client connection state.

#### Constructor

- **Initializes**:
  - Active connections dictionary (client_id -> WebSocket)
  - Client information dictionary (client_id -> client_data)
  - Connection state tracking

#### Core Data Structures

##### Active Connections

```python
active_connections: Dict[str, WebSocket]
```

- Maps client IDs to WebSocket objects
- Enables direct message sending to specific clients
- Automatically cleaned up on disconnection

##### Client Information

```python
client_info: Dict[str, dict]
```

- Stores client metadata (name, sync_root, connection time)
- Enables client tracking and status reporting
- Used for connection management and debugging

### Connection Management

##### `async connect(websocket: WebSocket, client_id: str)`

Establishes new WebSocket connection:

- **Process**:
  1. Accepts WebSocket connection
  2. Adds to active connections registry
  3. Logs successful connection
- **Parameters**:
  - `websocket`: FastAPI WebSocket object
  - `client_id`: Unique client identifier
- **Use Cases**: Initial client connection setup

##### `def disconnect(client_id: str)`

Cleanly removes client from all registries:

- **Process**:
  1. Removes from active connections
  2. Clears client information
  3. Logs disconnection event
- **Parameters**: `client_id` - Client to disconnect
- **Use Cases**: Normal disconnection, error cleanup, timeout handling

### Message Operations

##### `async send_message(client_id: str, message: dict)`

Sends message to specific client:

- **Process**:
  1. Validates client connection exists
  2. Serializes message to JSON
  3. Sends via WebSocket
  4. Handles connection errors gracefully
- **Error Handling**: Automatic disconnect on send failure
- **Use Cases**: Direct client communication, responses, notifications

##### `async broadcast_to_all(message: dict)`

Sends message to all connected clients:

- **Process**:
  1. Iterates through all active connections
  2. Sends message to each client
  3. Collects failed connections
  4. Cleans up disconnected clients
- **Features**: Automatic error recovery and cleanup
- **Use Cases**: Server announcements, global notifications

##### `async broadcast_to_others(sender_client_id: str, message: dict)`

Sends message to all clients except sender:

- **Process**:
  1. Iterates through active connections
  2. Skips sender client
  3. Sends to remaining clients
  4. Handles individual connection failures
- **Use Cases**: File change notifications, sync updates

### Message Processing

##### `async handle_message(client_id: str, message_data: dict)`

Processes incoming WebSocket messages:

- **Input**: Raw message dictionary from client
- **Process**:
  1. Validates message structure
  2. Routes based on message type
  3. Executes appropriate handler
  4. Sends responses when needed
  5. Handles errors gracefully

#### Message Type Handlers

##### Client Connection (`CLIENT_CONNECT`)

- **Input**: ConnectionRequest with client details
- **Process**:
  1. Extracts client information
  2. Stores in client registry
  3. Creates connection response
  4. Notifies other clients of new connection
- **Response**: ConnectionResponse with server time

##### Heartbeat (`HEARTBEAT`)

- **Input**: HeartbeatMessage with timestamp
- **Process**:
  1. Validates heartbeat data
  2. Updates client last-seen time
  3. Sends heartbeat response
- **Purpose**: Connection health monitoring

##### File Changed (`FILE_CHANGED`)

- **Input**: File change notification
- **Process**:
  1. Validates file change data
  2. Broadcasts to other clients
  3. Enables real-time sync updates
- **Use Cases**: Live file synchronization

### WebSocket Endpoint

##### `async websocket_endpoint(websocket: WebSocket, client_id: str)`

Main WebSocket endpoint handler for FastAPI:

- **Process**:
  1. Establishes connection
  2. Enters message receiving loop
  3. Processes incoming messages
  4. Handles disconnection gracefully
  5. Notifies other clients of disconnection

#### Connection Lifecycle

1. **Connection**: Accept WebSocket and register client
2. **Message Loop**: Continuously receive and process messages
3. **Disconnection**: Clean up on normal or error disconnect
4. **Notification**: Inform other clients of disconnection

### Error Handling

#### Connection Errors

- **WebSocket Send Failures**: Automatic client disconnection
- **JSON Parse Errors**: Error response to client
- **Invalid Message Format**: Logged and reported to client
- **Connection Drops**: Graceful cleanup and notification

#### Message Validation

- **Pydantic Model Validation**: Automatic message structure validation
- **Type Checking**: Ensures message types are valid
- **Data Sanitization**: Prevents malformed data processing
- **Error Responses**: Informative error messages to clients

#### Cleanup Operations

- **Failed Connection Removal**: Automatic cleanup of broken connections
- **Memory Management**: Regular cleanup of disconnected clients
- **Resource Cleanup**: Proper WebSocket resource management
- **State Consistency**: Maintains accurate connection state

### Real-Time Features

#### Live File Synchronization

- **File Updates**: Immediate notification of file changes
- **Multi-Client Sync**: Updates broadcast to all relevant clients
- **Change Tracking**: Maintains file change history
- **Conflict Prevention**: Enables real-time conflict detection

#### Connection Monitoring

- **Heartbeat System**: Regular health checks
- **Connection Status**: Real-time connection state tracking
- **Client Discovery**: Notification of client joins/leaves
- **Network Health**: Connection quality monitoring

### Performance Characteristics

#### Scalability

- **Concurrent Connections**: Supports multiple simultaneous clients
- **Async Operations**: Non-blocking message processing
- **Efficient Broadcasting**: Optimized for multiple recipients
- **Memory Efficient**: Minimal memory per connection

#### Network Efficiency

- **JSON Compression**: Efficient message serialization
- **Selective Broadcasting**: Targeted message delivery
- **Connection Reuse**: Persistent WebSocket connections
- **Bandwidth Optimization**: Minimal overhead per message

### Integration Points

#### Server Main Module

- **Endpoint Registration**: WebSocket route configuration
- **File Operation Notifications**: Integration with file upload/delete
- **Client Registration**: Coordination with HTTP registration
- **Status Reporting**: Connection status for health checks

#### Message Protocol

- **Shared Protocols**: Uses common message types and structures
- **Type Safety**: Pydantic models for message validation
- **Extensibility**: Easy addition of new message types
- **Backward Compatibility**: Version-aware message handling

### Configuration and Monitoring

#### Connection Limits

- Configurable maximum connections per server
- Rate limiting for message processing
- Timeout handling for inactive connections
- Resource usage monitoring

#### Debugging Support

- **Connection Logging**: Detailed connection event logs
- **Message Tracing**: Optional message content logging
- **Error Reporting**: Comprehensive error information
- **Performance Metrics**: Connection and message statistics

### Security Considerations

#### Connection Security

- **Client Authentication**: Integration with authentication system
- **Origin Validation**: WebSocket origin checking
- **Rate Limiting**: Protection against message flooding
- **Input Sanitization**: Safe message data handling

#### Message Security

- **Content Validation**: All messages validated against schemas
- **Injection Prevention**: Safe handling of client data
- **Authorization**: Client permission checking for operations
- **Audit Trail**: Logging of all client actions

### Client State Management

#### Connection Tracking

- **Active Sessions**: Real-time session monitoring
- **Client Metadata**: Storage of client information
- **Connection History**: Tracking of connection patterns
- **Status Reporting**: Client status for administrative interface

#### Graceful Degradation

- **Connection Loss**: Handling of unexpected disconnections
- **Partial Connectivity**: Operation with limited client connections
- **Recovery**: Automatic reconnection support
- **State Restoration**: Recovery of client state after reconnection
