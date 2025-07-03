# File Synchronization System Documentation

## Overview

This is a comprehensive Python-based file synchronization system that enables real-time file syncing across multiple clients through a central server. The system uses WebSocket connections for live updates and HTTP APIs for file transfers.

## Architecture

### System Components

- **Client**: Monitors local file changes and syncs with server
- **Server**: Central hub managing file storage and client coordination
- **Shared**: Common utilities and data models used by both components

### Communication Patterns

- **HTTP REST API**: File uploads, downloads, and sync analysis
- **WebSocket**: Real-time notifications and connection management
- **File System Events**: Local file change detection and monitoring

## Documentation Structure

### Client Components

1. **[Client Main Module](client_main.md)** - CLI interface and application orchestration
2. **[Client Sync Engine](client_sync_engine.md)** - Core synchronization logic and server communication
3. **[Client File Watcher](client_watcher.md)** - Real-time file system monitoring

### Server Components

4. **[Server Main Module](server_main.md)** - FastAPI server with REST endpoints
5. **[Server File Manager](server_file_manager.md)** - File storage and metadata management
6. **[Server WebSocket Manager](server_websocket_manager.md)** - Real-time client communication

### Shared Libraries

7. **[Shared Models](shared_models.md)** - Data models and type definitions
8. **[Shared Protocols](shared_protocols.md)** - WebSocket message protocols
9. **[Shared Utilities](shared_utils.md)** - Common utility functions

## Key Features

### Real-Time Synchronization

- **Live Updates**: WebSocket-based instant notifications
- **Change Detection**: File system monitoring with event batching
- **Multi-Client**: Supports multiple simultaneous clients
- **Conflict Resolution**: Timestamp-based conflict detection

### File Operations

- **Upload/Download**: Efficient file transfer mechanisms
- **Move/Rename**: Handles file relocation operations
- **Delete**: Synchronized file deletion across clients
- **Integrity**: SHA-256 checksums for data verification

### Configuration Management

- **Client Config**: YAML-based client configuration
- **Server Config**: Flexible server deployment options
- **Ignore Patterns**: Shell-style file filtering
- **Authentication**: Optional API key support

### Cross-Platform Support

- **Path Normalization**: Consistent path handling
- **Unicode Support**: International filename compatibility
- **Platform Abstractions**: OS-agnostic file operations
- **Error Handling**: Graceful platform-specific error management

## Quick Start

### Installation

```bash
# Install dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

### Server Setup

```bash
# Start the server
uv run syncer-server

# Server runs on localhost:8000 by default
```

### Client Setup

```bash
# Initialize client configuration
uv run syncer-client init --name my-laptop --sync-dir ./documents

# Start client synchronization
uv run syncer-client start

# Check client status
uv run syncer-client status
```

## Configuration Examples

### Client Configuration (config.yaml)

```yaml
client_name: "my-laptop"
sync_directory: "./documents"
server_host: "localhost"
server_port: 8000
ignore_patterns:
  - ".git"
  - "__pycache__"
  - "*.tmp"
  - "*.log"
api_key: null
```

### Server Configuration

```python
config = ServerConfig(
    host="0.0.0.0",
    port=8000,
    sync_directory="./sync_data",
    max_file_size=100 * 1024 * 1024,  # 100MB
    allowed_extensions=None
)
```

## API Endpoints

### REST API

- `GET /health` - Server health check
- `POST /register` - Client registration
- `POST /sync` - Synchronization analysis
- `POST /upload` - File upload
- `GET /download/{path}` - File download
- `DELETE /files/{path}` - File deletion

### WebSocket

- `WS /ws/{client_id}` - Real-time communication

## Data Models

### Core Models

- **FileInfo**: File metadata and properties
- **SyncOperation**: Operation types (CREATE, UPDATE, DELETE, MOVE)
- **ClientInfo**: Client registration and status
- **SyncRequest/Response**: Synchronization protocol

### Message Types

- **CLIENT_CONNECT**: Connection establishment
- **FILE_CHANGED**: File modification notifications
- **HEARTBEAT**: Connection health monitoring
- **ERROR**: Error reporting

## Security Features

### Data Integrity

- **Checksums**: SHA-256 file verification
- **Path Validation**: Prevents directory traversal
- **Input Sanitization**: Safe handling of user data
- **Error Handling**: No sensitive data in error messages

### Authentication

- **API Keys**: Optional token-based authentication
- **Client IDs**: Unique client identification
- **Connection Tracking**: Audit trail for all operations
- **Access Control**: File access within sync boundaries

## Performance Characteristics

### Scalability

- **Async Operations**: Non-blocking I/O throughout
- **Connection Pooling**: Efficient resource utilization
- **Memory Efficiency**: Streaming file operations
- **Database Optimization**: Indexed metadata queries

### Network Efficiency

- **Change Detection**: Only sync modified files
- **Compression**: JSON message compression
- **Batching**: Event batching for rapid changes
- **Chunked Transfer**: Efficient large file handling

## Development Tools

### Code Quality

- **Ruff**: Linting and formatting
- **Pre-commit**: Git hooks for code quality
- **Type Hints**: Full type annotation
- **Pydantic**: Runtime type validation

### Testing

- **Unit Tests**: Comprehensive test coverage
- **Integration Tests**: End-to-end testing
- **Mock Support**: Isolated component testing
- **Performance Tests**: Load and stress testing

## Deployment

### Development

```bash
# Run server in development mode
uv run syncer-server

# Run client with verbose logging
uv run syncer-client start --verbose
```

### Production

```bash
# Production server with uvicorn
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Systemd service configuration
# Docker container deployment
# Reverse proxy configuration
```

## Troubleshooting

### Common Issues

- **Connection Problems**: Check server address and port
- **Permission Errors**: Verify sync directory permissions
- **File Conflicts**: Review conflict resolution strategies
- **Network Issues**: Check firewall and network connectivity

### Logging

- **Debug Mode**: Enable verbose logging with `--verbose`
- **Log Files**: Check application logs for detailed errors
- **WebSocket**: Monitor real-time connection status
- **Database**: SQLite database for operation history

### Performance Tuning

- **Ignore Patterns**: Exclude unnecessary files
- **File Size Limits**: Configure appropriate size restrictions
- **Heartbeat Interval**: Adjust connection monitoring frequency
- **Database Cleanup**: Regular maintenance operations

## Contributing

### Code Standards

- Follow PEP 8 style guidelines
- Use type hints throughout
- Write comprehensive docstrings
- Add unit tests for new features

### Development Workflow

1. Fork repository
2. Create feature branch
3. Write code with tests
4. Run linting and formatting
5. Submit pull request

### Documentation

- Update relevant documentation files
- Include code examples
- Explain design decisions
- Add troubleshooting information

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions, issues, or contributions, please refer to the project repository and documentation.
