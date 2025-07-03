# Server Main Module Documentation

## Overview

`server/main.py` implements the central file synchronization server using FastAPI. It provides REST API endpoints for file operations and WebSocket support for real-time client communication.

## Key Components

### SyncServer Class

The main server class that orchestrates all synchronization operations and client management.

#### Constructor

- **Parameters**: `config: ServerConfig` - Server configuration object
- **Initializes**:
  - FastAPI application instance
  - WebSocket manager for real-time communication
  - File manager for storage operations
  - Client registry dictionary
  - Sync directory creation

#### Core Methods

##### `async start()`

Starts the server with uvicorn:

- Creates uvicorn configuration with host and port
- Initializes uvicorn server instance
- Runs server asynchronously
- Handles server lifecycle

### API Endpoints

#### Health Check

**`GET /health`**

- **Purpose**: Server health monitoring
- **Response**: Status and timestamp
- **Use Case**: Load balancer health checks, monitoring systems

#### Client Registration

**`POST /register`**

- **Purpose**: Register new client with server
- **Input**: `ClientInfo` object with client details
- **Process**:
  1. Stores client information in registry
  2. Broadcasts client join notification to other clients
  3. Returns success confirmation
- **Response**: Success status and message

#### File Synchronization Analysis

**`POST /sync`**

- **Purpose**: Analyze differences between client and server files
- **Input**: `SyncRequest` with client file list
- **Process**:
  1. Retrieves current server file list
  2. Compares client files with server files
  3. Identifies files needing sync based on checksums
  4. Detects conflicts using modification timestamps
  5. Finds server files missing on client
- **Response**: `SyncResponse` with sync plan and conflicts
- **Logic**:
  - **Missing on server**: Client should upload
  - **Checksum mismatch**: Compare timestamps for conflict detection
  - **Server newer**: Mark as conflict
  - **Client newer**: Include in sync list
  - **Missing on client**: Include server file in sync list

#### File Upload

**`POST /upload`**

- **Purpose**: Receive file uploads from clients
- **Input**:
  - `file`: Binary file content (multipart)
  - `relative_path`: Target file path
  - `client_id`: Uploading client identifier
- **Process**:
  1. Creates directory structure if needed
  2. Writes file content to sync directory
  3. Updates file metadata in database
  4. Notifies other clients via WebSocket
- **Response**: Upload success confirmation

#### File Download

**`GET /download/{file_path:path}`**

- **Purpose**: Serve files to clients
- **Input**: File path as URL parameter
- **Process**:
  1. Validates file exists in sync directory
  2. Returns file content with appropriate headers
- **Response**: File content or 404 error
- **Features**: FastAPI FileResponse for efficient file serving

#### File Deletion

**`DELETE /files/{file_path:path}`**

- **Purpose**: Remove files from server
- **Input**:
  - `file_path`: File to delete (URL parameter)
  - `client_id`: Requesting client (query parameter)
- **Process**:
  1. Removes file/directory from filesystem
  2. Cleans up metadata from database
  3. Notifies other clients via WebSocket
- **Response**: Deletion success confirmation

#### WebSocket Endpoint

**`WebSocket /ws/{client_id}`**

- **Purpose**: Real-time communication with clients
- **Management**: Delegated to WebSocketManager
- **Features**:
  - Client connection management
  - Message routing and broadcasting
  - Heartbeat monitoring

### Integration Components

#### WebSocket Manager Integration

- Handles all real-time client communication
- Manages client connection lifecycle
- Broadcasts file change notifications
- Processes heartbeat messages

#### File Manager Integration

- Manages file metadata and storage
- Provides file listing and comparison
- Handles database operations
- Tracks sync history

#### Client Registry

- Maintains active client information
- Tracks client connection status
- Enables client-specific operations
- Supports multi-client coordination

## Request/Response Flow

### Initial Client Connection

1. Client sends connection request via WebSocket
2. WebSocket manager processes connection
3. Client sends registration POST request
4. Server stores client info and notifies others
5. Client performs initial sync analysis

### File Upload Process

1. Client detects local file change
2. Client uploads file via POST /upload
3. Server stores file and updates metadata
4. Server broadcasts change to other clients via WebSocket
5. Other clients download updated file

### File Download Process

1. Client receives change notification via WebSocket
2. Client requests file via GET /download/{path}
3. Server serves file content
4. Client updates local file

### Sync Analysis Process

1. Client sends local file list via POST /sync
2. Server compares with its file list
3. Server identifies differences and conflicts
4. Server returns sync plan
5. Client executes sync operations

## Error Handling

### HTTP Errors

- **404**: File not found during download
- **500**: Internal server errors with detailed messages
- **400**: Invalid request data (automatic Pydantic validation)

### Exception Management

- All endpoints wrapped with try-catch blocks
- Detailed error logging for debugging
- Graceful error responses to clients
- No sensitive information in error messages

### File System Errors

- Permission issues handled gracefully
- Disk space problems reported appropriately
- Path traversal prevented by design
- Invalid file operations logged and rejected

## Security Considerations

### Path Validation

- Relative paths only within sync directory
- No path traversal attacks possible
- Directory creation sanitized
- File operations contained to sync root

### Client Authentication

- Client ID tracking for all operations
- Optional API key support in configuration
- WebSocket connection validation
- Request origin tracking

### File Access Control

- All files served from designated sync directory
- No access to system files
- Upload size limits (configurable)
- File type restrictions (optional)

## Performance Features

### Asynchronous Operations

- All file I/O operations are async
- Non-blocking request handling
- Concurrent client support
- Efficient resource utilization

### File Serving Optimization

- FastAPI FileResponse for efficient serving
- Streaming support for large files
- Proper HTTP headers for caching
- Content-Type detection

### Database Integration

- Async SQLite operations
- Connection pooling via aiosqlite
- Efficient metadata queries
- Transaction support for consistency

## Configuration Options

### ServerConfig Parameters

- **host**: Server bind address (default: localhost)
- **port**: Server port (default: 8000)
- **sync_directory**: File storage location (default: ./sync_data)
- **max_file_size**: Upload size limit (default: 100MB)
- **allowed_extensions**: File type restrictions (optional)

### Runtime Configuration

- Environment variable support
- Configuration file loading
- Command-line parameter override
- Hot-reload capability (development)

## Monitoring and Logging

### Access Logging

- All HTTP requests logged
- WebSocket connection events
- File operation tracking
- Error event logging

### Health Monitoring

- Health check endpoint for monitoring
- Server status reporting
- Resource usage tracking
- Performance metrics collection

### Debug Support

- Detailed error messages in development
- Request/response logging
- WebSocket message tracing
- File operation debugging

## Deployment Considerations

### Production Setup

- ASGI server compatibility (uvicorn, gunicorn)
- Reverse proxy support (nginx, Apache)
- SSL/TLS termination
- Load balancing ready

### Scalability

- Horizontal scaling with shared storage
- Database connection pooling
- WebSocket connection management
- File storage optimization

### Reliability

- Graceful shutdown handling
- Connection cleanup on termination
- Data consistency guarantees
- Recovery from failures
