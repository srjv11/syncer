# Shared Utilities Documentation

## Overview

`shared/utils.py` provides essential utility functions used throughout the file synchronization system. These functions handle file operations, path management, checksums, and file filtering with cross-platform compatibility.

## File Information and Checksums

### calculate_file_checksum(file_path: str) -> str

Calculates SHA-256 checksum for file integrity verification:

```python
def calculate_file_checksum(file_path: str) -> str:
    """Calculate SHA-256 checksum of a file."""
```

**Purpose**: File integrity verification and change detection
**Algorithm**: SHA-256 for cryptographic strength and collision resistance
**Implementation**:

- **Streaming**: Reads file in 4KB chunks to handle large files
- **Memory Efficient**: Constant memory usage regardless of file size
- **Error Handling**: Returns empty string on I/O errors

**Process**:

1. Initialize SHA-256 hash object
2. Read file in 4KB chunks
3. Update hash with each chunk
4. Return hexadecimal digest

**Performance**: O(n) where n = file size, optimized for large files
**Security**: Cryptographically secure hash for tamper detection

### get_file_info(file_path: str) -> Optional[dict]

Extracts comprehensive file metadata:

```python
def get_file_info(file_path: str) -> Optional[dict]:
    """Get file information including size, modified time, and checksum."""
```

**Purpose**: Complete file metadata extraction for synchronization
**Returns**: Dictionary with file information or None on error

**Metadata Extracted**:

- **Path**: Absolute file path as string
- **Size**: File size in bytes
- **Modified Time**: Last modification timestamp as datetime
- **Is Directory**: Boolean flag for directory identification
- **Checksum**: SHA-256 hash (empty for directories)

**Error Handling**:

- **File Not Found**: Returns None for non-existent files
- **Permission Errors**: Returns None for inaccessible files
- **System Errors**: Graceful handling of OS-level failures

**Use Cases**:

- Initial file scanning
- Change detection
- Sync operation preparation
- Metadata comparison

## File Filtering and Patterns

### should_ignore_file(file_path: str, ignore_patterns: list[str]) -> bool

Determines if file should be excluded from synchronization:

```python
def should_ignore_file(file_path: str, ignore_patterns: list[str]) -> bool:
    """Check if a file should be ignored based on patterns."""
```

**Purpose**: File filtering based on configurable patterns
**Pattern Types**: Shell-style wildcards using fnmatch module

**Pattern Matching**:

- **Filename Patterns**: Matches against basename (e.g., `*.tmp`)
- **Path Patterns**: Matches against full relative path (e.g., `build/**`)
- **Directory Patterns**: Matches directory names (e.g., `.git`)

**Common Patterns**:

```python
ignore_patterns = [
    ".git",              # Git repository
    "__pycache__",       # Python bytecode cache
    "*.tmp",             # Temporary files
    "*.log",             # Log files
    ".DS_Store",         # macOS system files
    "node_modules",      # Node.js dependencies
    "build/**",          # Build outputs
    "*.pyc",             # Python compiled files
]
```

**Algorithm**:

1. Extract filename from path
2. Test filename against each pattern
3. Test full relative path against each pattern
4. Return True if any pattern matches

**Performance**: O(p) where p = number of patterns
**Flexibility**: Supports complex inclusion/exclusion rules

## Path Management

### normalize_path(path: str) -> str

Normalizes file paths for cross-platform compatibility:

```python
def normalize_path(path: str) -> str:
    """Normalize file path for cross-platform compatibility."""
```

**Purpose**: Consistent path representation across operating systems
**Implementation**: Converts to POSIX format using pathlib

**Normalization Features**:

- **Separator Standardization**: Uses forward slashes (/)
- **Case Preservation**: Maintains original case
- **Relative Path Support**: Handles both absolute and relative paths
- **Unicode Support**: Proper handling of international characters

**Benefits**:

- **Database Consistency**: Same path representation in database
- **Network Transfer**: Consistent paths over network
- **Comparison**: Reliable path equality checks
- **Security**: Prevents path traversal variations

**Examples**:

```python
# Windows input
normalize_path("Documents\\file.txt")  # -> "Documents/file.txt"

# Unix input (unchanged)
normalize_path("Documents/file.txt")   # -> "Documents/file.txt"

# Complex path
normalize_path("a\\b/../c/./file.txt") # -> "a/c/file.txt"
```

### get_relative_path(file_path: str, base_path: str) -> str

Calculates relative path from base directory:

```python
def get_relative_path(file_path: str, base_path: str) -> str:
    """Get relative path from base directory."""
```

**Purpose**: Convert absolute paths to relative paths for storage and transmission
**Error Handling**: Returns original path if not relative to base

**Use Cases**:

- **Database Storage**: Store paths relative to sync root
- **Network Transfer**: Send relative paths between clients
- **File Operations**: Reference files within sync directory
- **Security**: Ensure files are within sync boundary

**Algorithm**:

1. Convert both paths to Path objects
2. Use pathlib relative_to() method
3. Handle ValueError for non-relative paths
4. Return string representation

**Security Benefit**: Prevents path traversal attacks by validating relationships

### ensure_directory(directory: str) -> None

Creates directory structure if it doesn't exist:

```python
def ensure_directory(directory: str) -> None:
    """Ensure directory exists, create if it doesn't."""
```

**Purpose**: Safe directory creation with parent directory support
**Features**:

- **Parent Creation**: Creates intermediate directories as needed
- **Exists OK**: No error if directory already exists
- **Atomic**: Uses pathlib mkdir with appropriate flags

**Use Cases**:

- **Sync Root Setup**: Create client sync directories
- **File Upload**: Ensure destination directory exists
- **Initialization**: Set up server storage directories
- **Organization**: Create subdirectory structure

**Safety**: Idempotent operation (safe to call multiple times)

## Cross-Platform Considerations

### Path Handling

- **Separator Normalization**: Consistent forward slash usage
- **Case Sensitivity**: Handles Windows/macOS case-insensitive filesystems
- **Unicode Support**: Proper encoding for international filenames
- **Length Limits**: Respects filesystem path length restrictions

### File Operations

- **Permission Handling**: Graceful handling of permission differences
- **File Locking**: Compatible with platform-specific locking mechanisms
- **Timestamp Precision**: Handles different timestamp resolutions
- **Special Files**: Proper handling of symlinks, device files, etc.

### Pattern Matching

- **Case Sensitivity**: Respects platform conventions
- **Hidden Files**: Handles Unix dot-files and Windows hidden attributes
- **Reserved Names**: Avoids platform-specific reserved filenames
- **Encoding**: Proper handling of filename encoding differences

## Performance Optimizations

### File Checksum Calculation

- **Chunked Reading**: 4KB chunks for memory efficiency
- **Streaming**: Constant memory usage for any file size
- **Early Exit**: Fast return for I/O errors
- **Hash Reuse**: Single hash object per file

### Path Operations

- **Path Caching**: Reuse of Path objects where beneficial
- **Lazy Evaluation**: Path operations only when needed
- **String Optimization**: Minimal string manipulation
- **Unicode Efficiency**: Efficient Unicode handling

### Pattern Matching

- **Short-Circuit**: Early exit on first pattern match
- **Compiled Patterns**: Regex compilation for complex patterns
- **Pattern Ordering**: Most common patterns first
- **Cache Optimization**: Pattern matching result caching

## Error Handling Strategies

### File System Errors

- **Permission Denied**: Graceful handling and logging
- **File Not Found**: Return None rather than exception
- **Disk Full**: Proper error propagation
- **Network Drives**: Handle network filesystem issues

### Path Validation

- **Invalid Characters**: Handle platform-specific restrictions
- **Path Length**: Respect filesystem limits
- **Reserved Names**: Avoid system-reserved filenames
- **Encoding Issues**: Handle filename encoding problems

### Security Considerations

- **Path Traversal**: Prevent directory traversal attacks
- **Symlink Attacks**: Safe handling of symbolic links
- **Permission Escalation**: Prevent privilege escalation
- **Input Validation**: Sanitize all path inputs

## Integration Points

### File Synchronization

- **Change Detection**: Checksum comparison for file changes
- **Path Management**: Consistent path handling across components
- **Filtering**: Ignore pattern application during sync
- **Metadata**: File information extraction for sync decisions

### Database Operations

- **Path Normalization**: Consistent database key format
- **Metadata Storage**: File information for database records
- **Query Optimization**: Normalized paths for efficient queries
- **Index Support**: Consistent path format for indexing

### Network Communication

- **Path Transmission**: Normalized paths for network transfer
- **Metadata Exchange**: File information in network messages
- **Security**: Validated paths prevent network attacks
- **Compatibility**: Cross-platform path handling

### Configuration Management

- **Pattern Validation**: Validate ignore patterns
- **Path Resolution**: Resolve relative configuration paths
- **Directory Setup**: Create configured directories
- **Validation**: Ensure configuration paths are valid

## Testing and Validation

### Unit Testing

- **Mock Filesystem**: Test with various filesystem conditions
- **Pattern Testing**: Comprehensive ignore pattern validation
- **Path Testing**: Cross-platform path handling verification
- **Error Testing**: Validation of error handling paths

### Performance Testing

- **Large Files**: Checksum calculation performance
- **Many Files**: Pattern matching performance
- **Deep Paths**: Path operation performance
- **Unicode Paths**: International character handling

### Security Testing

- **Path Traversal**: Validation of security controls
- **Symlink Handling**: Safe symbolic link processing
- **Permission Testing**: Proper permission error handling
- **Input Fuzzing**: Robustness against invalid inputs
