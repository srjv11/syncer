# Client File Watcher Documentation

## Overview

`client/watcher.py` implements real-time file system monitoring using the watchdog library. It detects file changes and triggers synchronization operations automatically.

## Key Components

### SyncEventHandler Class

File system event handler that processes watchdog events and converts them to sync operations.

#### Constructor

- **Parameters**:
  - `sync_callback: Callable` - Function to call when files change
  - `sync_root: str` - Root directory being watched
  - `ignore_patterns: list[str]` - Patterns for files to ignore
- **Initializes**:
  - Event processing configuration
  - Pending events set for batching
  - Event delay timer (0.5 seconds default)

#### Event Processing Methods

##### `def _should_process_event(event: FileSystemEvent) -> bool`

Determines if a file system event should trigger synchronization:

- Processes directory move/delete events
- Filters events based on ignore patterns
- Converts absolute paths to relative paths
- Returns True if event should be processed

##### `def _get_file_info(file_path: str) -> Optional[FileInfo]`

Extracts file metadata for synchronization:

- Calls utility function to get file stats
- Converts absolute path to relative path
- Creates FileInfo object with normalized path
- Returns None if file info cannot be obtained

##### `async _delayed_sync(file_path, operation, old_path=None)`

Implements event batching and delayed processing:

1. Waits for event delay period (0.5 seconds)
2. Removes file from pending events set
3. Gets current file information
4. Handles case where file no longer exists (converts to DELETE)
5. Creates FileInfo for DELETE operations
6. Calls sync callback with operation details

#### File System Event Handlers

##### `def on_created(event: FileSystemEvent)`

Handles file/directory creation:

- Filters events using ignore patterns
- Adds file to pending events set
- Schedules delayed sync with CREATE operation
- Logs creation event for debugging

##### `def on_modified(event: FileSystemEvent)`

Handles file/directory modification:

- Ignores directory modification events
- Filters events using ignore patterns
- Adds file to pending events set
- Schedules delayed sync with UPDATE operation
- Logs modification event for debugging

##### `def on_deleted(event: FileSystemEvent)`

Handles file/directory deletion:

- Filters events using ignore patterns
- Adds file to pending events set
- Schedules delayed sync with DELETE operation
- Logs deletion event for debugging

##### `def on_moved(event: FileSystemEvent)`

Handles file/directory move/rename operations:

- Filters source path using ignore patterns
- Checks if destination is also filtered
- If destination is ignored: treats as DELETE operation
- If destination is valid: treats as MOVE operation
- Schedules appropriate delayed sync operation
- Logs move event with source and destination

### FileWatcher Class

High-level file watcher that manages the watchdog Observer and event handling.

#### Constructor

- **Parameters**:
  - `sync_root: str` - Directory to watch
  - `sync_callback: Callable` - Function to call for file changes
  - `ignore_patterns: list[str]` - Optional ignore patterns
- **Initializes**:
  - Sync root path object
  - Observer and event handler (None initially)
  - Running state tracking

#### Core Methods

##### `async start()`

Starts file system monitoring:

1. Checks if already running (prevents double-start)
2. Validates sync directory exists
3. Creates SyncEventHandler instance
4. Configures watchdog Observer
5. Schedules recursive directory watching
6. Starts observer thread
7. Sets running state and logs startup

##### `async stop()`

Stops file system monitoring:

1. Checks if currently running
2. Stops observer thread
3. Waits for observer to finish
4. Resets running state
5. Logs shutdown completion

##### `def is_watching() -> bool`

Returns current watching status:

- Checks running state
- Verifies observer exists and is alive
- Returns combined boolean status

##### `async scan_initial_files() -> list[FileInfo]`

Scans directory for existing files during startup:

1. Returns empty list if directory doesn't exist
2. Recursively walks directory tree
3. Processes only regular files (not directories)
4. Filters files using ignore patterns
5. Creates FileInfo objects for each file
6. Returns complete file list for initial sync

##### `def _get_file_info(file_path: str) -> Optional[FileInfo]`

Helper method to create FileInfo objects:

- Gets file metadata using utility function
- Converts to relative path
- Creates FileInfo with normalized path
- Returns None on error

## Event Batching Strategy

### Purpose

Prevents excessive sync operations during rapid file changes:

- Text editors often create multiple modification events
- File operations may trigger creation followed by modification
- Network efficiency improved by batching related changes

### Implementation

1. Events are added to pending set immediately
2. Delayed sync task waits 0.5 seconds
3. Only processes event if still in pending set
4. Latest file state is checked before sync
5. Handles case where file was deleted during delay

### Benefits

- Reduces network traffic
- Prevents duplicate operations
- Handles editor temporary files correctly
- Improves overall sync performance

## Ignore Pattern Support

### Pattern Types

- **Filename patterns**: `*.tmp`, `*.log`
- **Directory patterns**: `.git`, `__pycache__`
- **Path patterns**: `build/**`, `*/node_modules`

### Implementation

- Uses `fnmatch` for pattern matching
- Checks both filename and relative path
- Supports shell-style wildcards
- Case-sensitive matching

### Common Patterns

```python
ignore_patterns = [
    ".git",           # Git repository
    "__pycache__",    # Python cache
    "*.tmp",          # Temporary files
    "*.log",          # Log files
    ".DS_Store",      # macOS system files
    "node_modules",   # Node.js dependencies
    "build/**",       # Build outputs
]
```

## Error Handling

- File system errors during event processing are logged but don't crash watcher
- Missing files during delayed sync are converted to DELETE operations
- Observer thread failures are contained and logged
- Invalid file paths are handled gracefully

## Performance Considerations

- Uses separate thread for file system monitoring (watchdog Observer)
- Async tasks for sync operations prevent blocking
- Event batching reduces network overhead
- Recursive watching limited to configured sync directory
- Memory usage scales with pending events count

## Integration Points

- **SyncEngine**: Receives file change notifications
- **Shared utilities**: Uses file info extraction and path normalization
- **Configuration**: Respects ignore patterns from client config
- **Logging**: Provides debug information for troubleshooting

## Thread Model

- **Main Thread**: Async event loop and sync operations
- **Observer Thread**: File system monitoring (watchdog)
- **Task Pool**: Async tasks for delayed sync operations
- **Communication**: Thread-safe event passing via asyncio
