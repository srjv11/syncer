# Server File Manager Documentation

## Overview

`server/file_manager.py` manages file storage, metadata tracking, and sync history for the file synchronization server. It provides persistent storage using SQLite and handles all file-related database operations.

## Key Components

### FileManager Class

Central class for managing file operations, metadata, and synchronization history.

#### Constructor

- **Parameters**: `sync_directory: str` - Root directory for file storage
- **Initializes**:
  - Sync directory path object
  - SQLite database path (metadata.db)
  - Directory creation if needed
  - Database initialization task

#### Database Schema

##### file_metadata Table

Stores comprehensive file information:

- **id**: Primary key (auto-increment)
- **path**: Unique file path (relative to sync root)
- **size**: File size in bytes
- **checksum**: SHA-256 hash for integrity verification
- **modified_time**: Last modification timestamp
- **is_directory**: Boolean flag for directory entries
- **created_at**: Record creation timestamp
- **updated_at**: Record last update timestamp

##### sync_history Table

Tracks all synchronization operations:

- **id**: Primary key (auto-increment)
- **file_path**: File path for the operation
- **operation**: Type of sync operation (create, update, delete, move)
- **client_id**: Client that performed the operation
- **timestamp**: Operation timestamp
- **checksum**: File checksum at time of operation
- **size**: File size at time of operation

#### Core Methods

##### `async _init_database()`

Initializes SQLite database with required tables:

- Creates file_metadata table with indexes
- Creates sync_history table for audit trail
- Sets up foreign key constraints
- Commits schema changes

### File Metadata Operations

##### `async update_file_metadata(file_info: FileInfo)`

Updates or inserts file metadata:

- **Input**: FileInfo object with complete file details
- **Process**:
  1. Normalizes file path for consistency
  2. Uses INSERT OR REPLACE for upsert operation
  3. Updates timestamp to current time
  4. Commits transaction
- **Use Cases**: After file upload, during initial sync

##### `async remove_file_metadata(file_path: str)`

Removes file metadata from database:

- **Input**: Relative file path string
- **Process**:
  1. Normalizes path for query
  2. Deletes matching record
  3. Commits transaction
- **Use Cases**: After file deletion, cleanup operations

##### `async get_file_metadata(file_path: str) -> Optional[FileInfo]`

Retrieves file metadata by path:

- **Input**: Relative file path string
- **Process**:
  1. Queries database with normalized path
  2. Converts database row to FileInfo object
  3. Handles datetime parsing
- **Returns**: FileInfo object or None if not found
- **Use Cases**: File existence checks, metadata validation

### File System Operations

##### `async get_file_list(base_path: str = "") -> List[FileInfo]`

Comprehensive file listing with metadata:

- **Input**: Optional base path for subdirectory listing
- **Process**:
  1. Walks filesystem from sync directory
  2. Excludes metadata.db from results
  3. Creates FileInfo objects for all files
  4. Includes directory entries with appropriate metadata
  5. Updates database with current file information
  6. Returns complete file list
- **Features**:
  - Recursive directory traversal
  - Real-time file info extraction
  - Database synchronization
  - Directory entry handling

##### `def get_full_path(relative_path: str) -> Path`

Converts relative path to absolute filesystem path:

- **Input**: Relative path string
- **Returns**: Full Path object
- **Use Cases**: File system operations, path validation

### Sync History Management

##### `async log_sync_operation(file_path, operation, client_id, checksum="", size=0)`

Records synchronization operations:

- **Parameters**:
  - `file_path`: File path for operation
  - `operation`: SyncOperation enum value
  - `client_id`: Client performing operation
  - `checksum`: File checksum (optional)
  - `size`: File size (optional)
- **Process**:
  1. Normalizes file path
  2. Inserts record with timestamp
  3. Commits transaction
- **Use Cases**: Audit trail, conflict detection, debugging

##### `async get_sync_history(file_path="", limit=100) -> List[dict]`

Retrieves synchronization history:

- **Parameters**:
  - `file_path`: Specific file path (optional)
  - `limit`: Maximum records to return
- **Process**:
  1. Constructs query based on parameters
  2. Orders by timestamp (most recent first)
  3. Converts rows to dictionary format
- **Returns**: List of sync operation records
- **Use Cases**: Debugging, conflict analysis, audit reports

### Conflict Detection

##### `async get_conflicts() -> List[dict]`

Identifies potential file conflicts:

- **Process**:
  1. Queries for files modified by multiple clients recently (1 hour window)
  2. Groups operations by file path
  3. Identifies files with multiple client modifications
  4. Retrieves detailed history for each conflict
- **Returns**: List of conflicts with recent change history
- **Logic**: Files modified by different clients within short timeframe
- **Use Cases**: Conflict resolution, user alerts, sync validation

### Maintenance Operations

##### `async cleanup_deleted_files()`

Removes metadata for non-existent files:

- **Process**:
  1. Queries all file paths in metadata table
  2. Checks filesystem existence for each path
  3. Removes metadata for missing files
  4. Maintains database consistency
- **Use Cases**: Regular maintenance, cleanup after bulk deletions

## Database Design Principles

### Performance Optimization

- **Indexes**: Unique index on file path for fast lookups
- **Prepared Statements**: All queries use parameter binding
- **Connection Pooling**: Async SQLite with connection reuse
- **Transaction Management**: Proper commit/rollback handling

### Data Integrity

- **Unique Constraints**: Prevents duplicate file entries
- **Foreign Keys**: Maintains referential integrity (when applicable)
- **Validation**: Input sanitization and path normalization
- **Atomic Operations**: Database transactions for consistency

### Scalability Considerations

- **Async Operations**: Non-blocking database access
- **Efficient Queries**: Optimized for common access patterns
- **Pagination Support**: Limit clauses for large result sets
- **Index Strategy**: Supports fast file path lookups

## Path Normalization Strategy

### Cross-Platform Compatibility

- Uses `normalize_path()` utility for consistency
- Converts all paths to POSIX format
- Handles Windows/Unix path differences
- Ensures reproducible path strings

### Security Benefits

- Prevents path traversal attacks
- Standardizes path representation
- Enables reliable path comparison
- Supports safe file operations

## Error Handling

### Database Errors

- SQLite connection failures logged and retried
- Transaction rollback on operation failure
- Detailed error messages for debugging
- Graceful degradation when database unavailable

### File System Errors

- Permission issues handled gracefully
- Missing files detected and cleaned up
- Path validation prevents invalid operations
- Disk space issues reported appropriately

### Data Consistency

- Database transactions ensure atomicity
- File system and database kept in sync
- Regular cleanup prevents orphaned records
- Validation ensures data integrity

## Integration Points

### Server Main Module

- Provides file listing for sync analysis
- Updates metadata after file operations
- Supplies conflict information for clients
- Handles cleanup and maintenance tasks

### WebSocket Manager

- Logs sync operations for audit trail
- Provides conflict data for client notifications
- Supports real-time sync status updates
- Tracks client activity patterns

### Shared Utilities

- Uses file info extraction functions
- Leverages path normalization utilities
- Integrates with checksum calculation
- Depends on directory management functions

## Performance Characteristics

### Read Operations

- File metadata queries: O(1) with index
- File listing: O(n) where n = file count
- History queries: O(log n) with timestamp index
- Conflict detection: O(n) for recent operations

### Write Operations

- Metadata updates: O(1) with unique constraint
- History logging: O(1) append operation
- Cleanup operations: O(n) for full scan
- Batch operations: O(n) with transaction batching

### Memory Usage

- Database connection pooling limits memory
- Result set streaming for large queries
- File info objects cached temporarily
- Minimal metadata storage overhead

### Disk Usage

- SQLite database grows with file count
- History table grows with sync operations
- Regular maintenance recommended for large deployments
- Compression available for archived data
