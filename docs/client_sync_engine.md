# Client Sync Engine Documentation

## Overview

`client/sync_engine.py` implements the core synchronization logic for the file sync client. It handles server communication, file transfers, and real-time synchronization via WebSocket connections.

## Key Components

### SyncEngine Class

The primary class responsible for client-server synchronization operations.

#### Constructor

- **Parameters**: `config: ClientConfig` - Client configuration
- **Initializes**:
  - Unique client ID with timestamp
  - Sync root directory path
  - HTTP session for file transfers
  - WebSocket connection for real-time updates
  - Heartbeat mechanism

#### Core Methods

##### `async start()`

Initializes the sync engine:

1. Creates HTTP client session
2. Establishes WebSocket connection
3. Registers client with server
4. Starts heartbeat loop for connection monitoring

##### `async stop()`

Gracefully shuts down the engine:

1. Sets connection state to False
2. Cancels heartbeat task
3. Closes WebSocket connection
4. Closes HTTP session

### WebSocket Communication

#### `async _connect_websocket()`

Establishes WebSocket connection to server:

- Constructs WebSocket URL with client ID
- Sends connection request with client information
- Starts message listening task
- Handles connection failures gracefully

#### `async _listen_websocket()`

Continuously listens for WebSocket messages:

- Parses incoming JSON messages
- Routes messages to appropriate handlers
- Handles connection drops and errors
- Maintains connection state

#### `async _handle_websocket_message(data: dict)`

Processes incoming WebSocket messages:

- **file_updated**: Triggers download of updated files
- **file_deleted**: Removes locally deleted files
- **client_joined/left**: Logs client connection events
- **heartbeat**: Acknowledges server heartbeat

### File Synchronization Operations

#### `async sync_file(operation, file_info, old_path=None)`

Main file synchronization method:

- **CREATE/UPDATE**: Uploads file to server
- **DELETE**: Removes file from server
- **MOVE**: Handles file move/rename operations
- Notifies other clients via WebSocket broadcast

#### `async upload_file(file_info: FileInfo)`

Uploads file to server via HTTP:

1. Reads file content asynchronously
2. Creates multipart form data
3. Sends POST request to server upload endpoint
4. Handles upload success/failure responses

#### `async download_file(file_path: str)`

Downloads file from server:

1. Creates HTTP GET request to download endpoint
2. Ensures local directory structure exists
3. Streams file content to local filesystem
4. Handles chunked transfer for large files

#### `async delete_file(file_path: str)`

Removes file from server:

- Sends DELETE request to server
- Includes client ID for tracking
- Handles deletion confirmation

#### `async move_file(old_path: str, new_path: str)`

Handles file move operations:

1. Deletes file at old location
2. Uploads file at new location
3. Maintains file content integrity

### Initial Synchronization

#### `async perform_initial_sync(local_files: list[FileInfo])`

Performs comprehensive sync when client starts:

1. Sends local file list to server
2. Receives sync analysis from server
3. Downloads files missing locally
4. Uploads files missing on server
5. Reports conflicts for manual resolution

### Client Registration

#### `async _register_client()`

Registers client with server:

- Sends client information via HTTP POST
- Establishes client identity on server
- Enables server to track client state

### Heartbeat Mechanism

#### `async _heartbeat_loop()`

Maintains connection health:

- Sends periodic heartbeat messages (every 30 seconds)
- Monitors connection status
- Enables server to detect disconnected clients
- Breaks loop on connection failure

### Remote Change Handlers

#### `async _handle_remote_file_update(data: dict)`

Processes file update notifications:

- Ignores updates from same client (prevents loops)
- Downloads updated files from other clients
- Maintains file consistency across clients

#### `async _handle_remote_file_delete(data: dict)`

Processes file deletion notifications:

- Ignores deletions from same client
- Removes locally deleted files
- Handles both files and directories

## Error Handling

- Network connection failures are logged and handled gracefully
- File I/O errors don't crash the application
- WebSocket disconnections trigger reconnection attempts
- HTTP errors are logged with appropriate context

## Message Flow

### Client to Server

1. **Connection Request**: Initial handshake with client info
2. **File Upload**: Multipart form data for file content
3. **File Deletion**: DELETE request with file path
4. **Heartbeat**: Periodic connection health check
5. **File Change Notifications**: WebSocket messages for real-time updates

### Server to Client

1. **Connection Response**: Confirms successful connection
2. **File Update Notifications**: Alerts about changes from other clients
3. **File Deletion Notifications**: Alerts about deletions from other clients
4. **Heartbeat Response**: Acknowledges client heartbeat

## Configuration Requirements

- `server_host`: Server hostname or IP address
- `server_port`: Server port number
- `client_name`: Human-readable client identifier
- `sync_directory`: Local directory to synchronize
- `api_key`: Optional authentication token

## Thread Safety

- Uses asyncio for concurrent operations
- WebSocket and HTTP operations run in separate tasks
- File operations are serialized to prevent conflicts
- Connection state is managed atomically

## Performance Considerations

- Chunked file transfer for large files (8KB chunks)
- Asynchronous I/O prevents blocking operations
- Heartbeat interval balances responsiveness and network usage
- Connection pooling via aiohttp session reuse
