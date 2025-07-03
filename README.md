# Local Network File Syncer

A Python-based file synchronization system for local networks with real-time bidirectional sync, WebSocket communication, and conflict resolution.

## Features

- **Real-time synchronization**: Files are synced instantly across all connected clients
- **Bidirectional sync**: Changes from any client are propagated to all others
- **WebSocket communication**: Real-time notifications for file changes
- **File system monitoring**: Automatic detection of file changes using Watchdog
- **Conflict detection**: Basic timestamp-based conflict resolution
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Configurable ignore patterns**: Exclude files and directories from sync
- **SQLite metadata tracking**: File versioning and sync history
- **CLI interface**: Easy-to-use command-line tools

## Architecture

### Server

- **FastAPI**: RESTful API for file operations and client management
- **WebSocket Manager**: Real-time client communication and notifications
- **File Manager**: Metadata tracking with SQLite database
- **Sync coordination**: Handles conflict resolution and file distribution

### Client

- **File Watcher**: Monitors directory changes using Watchdog
- **Sync Engine**: Handles upload/download operations and server communication
- **CLI Interface**: User-friendly command-line interface with Click

### Shared

- **Data Models**: Pydantic models for type validation
- **Utilities**: Common file operations and checksums
- **Protocols**: WebSocket message definitions

## Installation

1. Clone or download the project
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Start the Server

```bash
python -m server.main
```

The server will start on `http://localhost:8000` by default.

### 2. Initialize a Client

```bash
python -m client.main init --name "my-client" --sync-dir "./my-sync-folder"
```

### 3. Start the Client

```bash
python -m client.main start
```

## Usage

### Server Commands

Start the server:

```bash
python -m server.main
```

The server provides the following endpoints:

- `GET /health` - Health check
- `POST /register` - Register a new client
- `POST /sync` - Synchronize file lists
- `POST /upload` - Upload a file
- `GET /download/{file_path}` - Download a file
- `DELETE /files/{file_path}` - Delete a file
- `WS /ws/{client_id}` - WebSocket connection

### Client Commands

Initialize client configuration:

```bash
python -m client.main init
```

Start the sync client:

```bash
python -m client.main start [--config config.yaml] [--verbose]
```

Check client status:

```bash
python -m client.main status [--config config.yaml]
```

### Configuration

Client configuration is stored in `config.yaml`:

```yaml
client_name: my-client
sync_directory: ./sync
server_host: localhost
server_port: 8000
ignore_patterns:
  - ".git"
  - "__pycache__"
  - "*.tmp"
  - "*.log"
api_key: null # Optional API key for authentication
```

### Ignore Patterns

Create a `.syncignore` file in your sync directory to exclude files:

```
*.tmp
*.log
.git/
__pycache__/
node_modules/
```

## How It Works

1. **Client Registration**: Clients register with the server and establish WebSocket connections
2. **Initial Sync**: Clients compare their file lists with the server and sync differences
3. **Real-time Monitoring**: File system changes are detected and queued for sync
4. **Conflict Resolution**: Timestamp-based resolution favors the most recently modified file
5. **WebSocket Notifications**: All clients are notified of changes in real-time

## File Operations

### Upload Process

1. File change detected by Watchdog
2. File metadata calculated (checksum, size, timestamp)
3. File uploaded to server via HTTP POST
4. Server stores file and updates metadata
5. Other clients notified via WebSocket
6. Clients download updated file

### Download Process

1. WebSocket notification received
2. Client requests file from server
3. Server streams file content
4. Client saves file to sync directory
5. File watcher temporarily ignores the change

### Conflict Resolution

- Files with different checksums trigger conflict detection
- Timestamp comparison determines the winner
- Conflicted files are logged for manual review
- Future versions will support merge strategies

## Development

### Project Structure

```
/
├── server/              # Server implementation
│   ├── main.py         # FastAPI application
│   ├── websocket_manager.py  # WebSocket handling
│   └── file_manager.py # File metadata and operations
├── client/             # Client implementation
│   ├── main.py         # CLI interface
│   ├── watcher.py      # File system monitoring
│   └── sync_engine.py  # Sync operations
├── shared/             # Shared components
│   ├── models.py       # Data models
│   ├── utils.py        # Common utilities
│   └── protocols.py    # WebSocket protocols
└── requirements.txt    # Python dependencies
```

### Running Tests

(Tests would be implemented in a `tests/` directory)

```bash
pytest tests/
```

### Logging

Enable verbose logging for debugging:

```bash
python -m client.main start --verbose
```

## Limitations

- Basic conflict resolution (timestamp-based only)
- No authentication/authorization (planned feature)
- No file compression (planned feature)
- No incremental sync for large files (planned feature)
- No file versioning/history (beyond sync logs)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is open source. Please check the license file for details.

## Troubleshooting

### Common Issues

**Client can't connect to server:**

- Check if server is running on the correct host/port
- Verify firewall settings
- Check network connectivity

**Files not syncing:**

- Check file permissions
- Verify ignore patterns
- Check client logs for errors
- Ensure sufficient disk space

**High CPU usage:**

- Check for rapid file changes causing sync loops
- Review ignore patterns to exclude temporary files
- Consider reducing file watcher sensitivity

### Logs

Server logs are printed to console. Client logs can be enabled with `--verbose` flag.

For production use, configure proper logging with file rotation and log levels.
