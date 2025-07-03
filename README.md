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
- **File compression**: Smart compression with gzip, zlib, and lz4 support
- **Differential sync**: Efficient large file synchronization
- **Performance metrics**: Built-in monitoring and statistics
- **Type safety**: Full Pydantic and MyPy integration
- **Comprehensive testing**: Unit, integration, and end-to-end test suites

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
2. Install dependencies using UV:

```bash
# Install UV if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

Or using pip with the traditional requirements file:

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Start the Server

```bash
# Using UV
uv run python -m server.main

# Or using python directly
python -m server.main
```

The server will start on `http://localhost:8000` by default.

### 2. Initialize a Client

```bash
# Using UV
uv run python -m client.main init --name "my-client" --sync-dir "./my-sync-folder"

# Or using python directly
python -m client.main init --name "my-client" --sync-dir "./my-sync-folder"
```

### 3. Start the Client

```bash
# Using UV
uv run python -m client.main start

# Or using python directly
python -m client.main start
```

## Usage

### Server Commands

Start the server:

```bash
# Using UV
uv run python -m server.main

# Or using python directly
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
# Using UV
uv run python -m client.main init

# Or using python directly
python -m client.main init
```

Start the sync client:

```bash
# Using UV
uv run python -m client.main start [--config config.yaml] [--verbose]

# Or using python directly
python -m client.main start [--config config.yaml] [--verbose]
```

Check client status:

```bash
# Using UV
uv run python -m client.main status [--config config.yaml]

# Or using python directly
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
│   ├── protocols.py    # WebSocket protocols
│   ├── compression.py  # File compression utilities
│   ├── diff.py         # Differential sync algorithms
│   ├── metrics.py      # Performance monitoring
│   └── exceptions.py   # Custom exception classes
├── tests/              # Test suite
│   ├── unit/           # Unit tests
│   ├── integration/    # Integration tests
│   ├── e2e/            # End-to-end tests
│   └── conftest.py     # Test configuration
├── docs/               # Documentation
├── pyproject.toml      # Project configuration (UV)
├── requirements.txt    # Python dependencies (pip)
└── .pre-commit-config.yaml  # Code quality hooks
```

### Running Tests

The project includes comprehensive unit, integration, and end-to-end tests:

```bash
# Using UV
uv run pytest

# Run only unit tests
uv run pytest tests/unit/

# Run with coverage
uv run pytest --cov=shared --cov=client --cov=server

# Or using python directly
pytest
```

### Development Tools

Install pre-commit hooks for code quality:

```bash
# Using UV
uv run pre-commit install

# Run all pre-commit checks
uv run pre-commit run --all-files
```

The project uses:
- **Ruff**: Linting and formatting
- **MyPy**: Type checking
- **Bandit**: Security scanning
- **Pytest**: Testing framework

### Logging

Enable verbose logging for debugging:

```bash
# Using UV
uv run python -m client.main start --verbose

# Or using python directly
python -m client.main start --verbose
```

## Limitations

- Basic conflict resolution (timestamp-based only)
- No authentication/authorization (planned feature)
- No incremental sync for large files (planned feature)
- No file versioning/history (beyond sync logs)

## Current Features

✅ **Implemented:**
- File compression (gzip, zlib, lz4) with smart compression decisions
- Comprehensive test suite (unit, integration, e2e)
- Type safety with Pydantic models and MyPy
- Development tools (pre-commit hooks, linting, formatting)
- Performance monitoring and metrics collection
- Cross-platform path handling
- Differential sync capabilities for large files

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
