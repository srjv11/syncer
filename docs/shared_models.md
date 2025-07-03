# Shared Models Documentation

## Overview

`shared/models.py` defines the core data models used throughout the file synchronization system. These Pydantic models ensure type safety, validation, and consistent data structures between client and server components.

## Core Enumerations

### SyncOperation

Enumeration defining types of file synchronization operations:

```python
class SyncOperation(str, Enum):
    CREATE = "create"    # New file creation
    UPDATE = "update"    # File content modification
    DELETE = "delete"    # File removal
    MOVE = "move"        # File relocation/rename
```

**Usage**: Identifies the type of file change operation
**String Inheritance**: Allows direct string comparison and JSON serialization
**Applications**: Event handling, sync logic, history tracking

## File and Operation Models

### FileInfo

Central model representing file metadata and properties:

```python
class FileInfo(BaseModel):
    path: str                    # Relative file path
    size: int                    # File size in bytes
    checksum: str                # SHA-256 hash for integrity
    modified_time: datetime      # Last modification timestamp
    is_directory: bool = False   # Directory flag (default: file)
```

**Purpose**: Complete file representation for sync operations
**Key Features**:

- **Path**: Normalized relative path for cross-platform compatibility
- **Checksum**: Enables conflict detection and integrity verification
- **Timestamp**: Used for conflict resolution and change tracking
- **Directory Support**: Handles both files and directories

**Validation**: Automatic via Pydantic (type checking, required fields)
**Serialization**: JSON-compatible for network transmission

### SyncMessage

Comprehensive message for file operation communication:

```python
class SyncMessage(BaseModel):
    operation: SyncOperation            # Type of sync operation
    file_info: FileInfo                # File details
    client_id: str                     # Originating client
    timestamp: datetime = Field(default_factory=datetime.now)  # Operation time
    old_path: Optional[str] = None     # Previous path for moves
```

**Purpose**: Complete context for file synchronization events
**Components**:

- **Operation**: What happened to the file
- **File Info**: Current file state and metadata
- **Client ID**: Source of the change for loop prevention
- **Timestamp**: Precise timing for conflict resolution
- **Old Path**: Original location for move/rename operations

**Use Cases**: Event broadcasting, history logging, conflict analysis

## Client Management Models

### ClientInfo

Model representing connected client information:

```python
class ClientInfo(BaseModel):
    client_id: str              # Unique client identifier
    name: str                   # Human-readable client name
    sync_root: str              # Client's sync directory path
    last_seen: datetime         # Last activity timestamp
    is_online: bool = True      # Connection status
```

**Purpose**: Client registry and status tracking
**Features**:

- **Unique ID**: Generated with timestamp for uniqueness
- **Friendly Name**: User-defined identifier for recognition
- **Sync Root**: Client's base synchronization directory
- **Activity Tracking**: Connection health monitoring
- **Status Flag**: Online/offline state management

**Applications**: Client management, status reporting, connection monitoring

## Synchronization Protocol Models

### SyncRequest

Request model for initial synchronization analysis:

```python
class SyncRequest(BaseModel):
    client_id: str              # Requesting client identifier
    files: list[FileInfo]       # Client's current file list
    sync_root: str              # Client's sync directory
```

**Purpose**: Initial sync negotiation between client and server
**Process**:

1. Client sends complete file inventory
2. Server compares with its file state
3. Server determines sync requirements
4. Response provides sync plan

**Benefits**: Efficient bulk synchronization, conflict prevention

### SyncResponse

Response model containing synchronization plan:

```python
class SyncResponse(BaseModel):
    success: bool                     # Operation success status
    message: str                      # Descriptive message
    files_to_sync: list[FileInfo] = []  # Files needing sync
    conflicts: list[str] = []         # Conflicted file paths
```

**Purpose**: Server's sync analysis and instructions for client
**Components**:

- **Success**: Whether analysis completed successfully
- **Message**: Human-readable status or error description
- **Files to Sync**: Files client should download from server
- **Conflicts**: Files requiring manual resolution

**Sync Logic**:

- **Download**: Files newer on server than client
- **Upload**: Files newer on client than server (handled separately)
- **Conflicts**: Files modified on both sides simultaneously

### ConflictResolution

Model for handling file conflicts:

```python
class ConflictResolution(BaseModel):
    file_path: str              # Conflicted file path
    resolution: str             # Resolution strategy
    timestamp: datetime         # Resolution time
```

**Resolution Strategies**:

- **"local"**: Keep client version
- **"remote"**: Use server version
- **"merge"**: Manual merge required

**Purpose**: Conflict resolution tracking and implementation
**Future Enhancement**: Support for automatic merge strategies

## Configuration Models

### ServerConfig

Server configuration and operational parameters:

```python
class ServerConfig(BaseModel):
    host: str = "localhost"                           # Bind address
    port: int = 8000                                  # Listen port
    sync_directory: str = "./sync_data"               # Storage location
    max_file_size: int = 100 * 1024 * 1024          # 100MB limit
    allowed_extensions: Optional[list[str]] = None    # File type filter
```

**Configuration Options**:

- **Network**: Host and port for server binding
- **Storage**: Local directory for file storage
- **Limits**: File size restrictions for uploads
- **Security**: Optional file type restrictions

**Defaults**: Sensible defaults for development and testing
**Production**: Customizable for deployment requirements

### ClientConfig

Client configuration and behavior settings:

```python
class ClientConfig(BaseModel):
    server_host: str = "localhost"                    # Server address
    server_port: int = 8000                          # Server port
    client_name: str                                 # Required client name
    sync_directory: str                              # Required sync path
    ignore_patterns: list[str] = [".git", "__pycache__", "*.tmp"]  # File filters
    api_key: Optional[str] = None                    # Authentication token
```

**Configuration Categories**:

- **Connection**: Server location and authentication
- **Identity**: Client name and sync directory
- **Filtering**: Ignore patterns for file exclusion
- **Security**: Optional API key for server authentication

**Ignore Patterns**: Shell-style patterns for excluding files
**Required Fields**: Client name and sync directory must be specified

## Design Principles

### Type Safety

- **Pydantic Validation**: Automatic type checking and conversion
- **Runtime Validation**: Input validation at model creation
- **IDE Support**: Full type hints for development assistance
- **Error Prevention**: Catch type mismatches early

### Serialization

- **JSON Compatibility**: All models serialize to JSON
- **Network Transfer**: Efficient over HTTP and WebSocket
- **Cross-Platform**: Language-agnostic data exchange
- **Human Readable**: JSON format for debugging

### Extensibility

- **Optional Fields**: Backward compatibility for new features
- **Inheritance**: Models can be extended for specialized use
- **Validation**: Custom validators for complex requirements
- **Defaults**: Sensible defaults reduce configuration burden

### Consistency

- **Shared Models**: Same structures used by client and server
- **Validation Rules**: Consistent data validation across components
- **Field Names**: Standardized naming conventions
- **Documentation**: Comprehensive field descriptions

## Usage Patterns

### Model Creation

```python
# Create file info from filesystem
file_info = FileInfo(
    path="documents/report.pdf",
    size=1024000,
    checksum="abc123...",
    modified_time=datetime.now(),
    is_directory=False
)

# Create sync message
sync_msg = SyncMessage(
    operation=SyncOperation.UPDATE,
    file_info=file_info,
    client_id="client-001"
)
```

### JSON Serialization

```python
# Serialize to JSON
json_data = file_info.dict()
json_string = file_info.json()

# Deserialize from JSON
file_info = FileInfo(**json_data)
file_info = FileInfo.parse_raw(json_string)
```

### Validation

```python
# Automatic validation
try:
    file_info = FileInfo(path="test", size="invalid")
except ValidationError as e:
    print(f"Validation error: {e}")
```

## Integration Points

### Network Layer

- HTTP API request/response bodies
- WebSocket message payloads
- Configuration file structures
- Database record mapping

### Business Logic

- File operation processing
- Conflict detection algorithms
- Sync state management
- Client relationship tracking

### Persistence Layer

- Database model mapping
- Configuration file parsing
- Cache serialization
- Backup data structures
