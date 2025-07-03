# Client Main Module Documentation

## Overview

`client/main.py` serves as the entry point for the file synchronization client application. It provides a command-line interface (CLI) for managing and operating the sync client.

## Key Components

### SyncClient Class

The main synchronization client orchestrator that coordinates file watching and sync operations.

#### Constructor

- **Parameters**: `config: ClientConfig` - Client configuration object
- **Initializes**:
  - Sync engine for server communication
  - File watcher for monitoring local changes
  - Running state management

#### Methods

##### `async start()`

Initializes and starts all client components:

1. Creates and starts the sync engine with server connection
2. Initializes file watcher with change callback
3. Performs initial synchronization with server
4. Starts file monitoring
5. Sets running state to True

##### `async stop()`

Gracefully shuts down all client components:

1. Sets running state to False
2. Stops file watcher
3. Stops sync engine and closes connections
4. Logs shutdown completion

##### `async run()`

Main execution loop:

1. Starts the client
2. Runs until interrupted (Ctrl+C or SIGTERM)
3. Handles graceful shutdown

##### `async _on_file_changed()`

Callback handler for file system events:

- **Parameters**:
  - `operation: SyncOperation` - Type of file operation (CREATE, UPDATE, DELETE, MOVE)
  - `file_info: FileInfo` - File metadata
  - `old_path: str` - Previous path for move operations
- **Function**: Forwards file changes to sync engine for server synchronization

### Configuration Management

#### `load_config(config_path: str) -> ClientConfig`

Loads client configuration from YAML file:

- Creates default configuration if file doesn't exist
- Validates and parses existing configuration
- Returns ClientConfig object

### CLI Commands

#### `cli()`

Root command group for all client operations.

#### `start` Command

Starts the synchronization client:

- **Options**:
  - `--config, -c`: Configuration file path (default: config.yaml)
  - `--verbose, -v`: Enable debug logging
- **Function**: Loads config, creates client, handles signals, runs sync loop

#### `init` Command

Interactive configuration setup:

- **Options**:
  - `--name`: Client name (prompted if not provided)
  - `--sync-dir`: Directory to synchronize (prompted if not provided)
  - `--server-host`: Server hostname (default: localhost)
  - `--server-port`: Server port (default: 8000)
  - `--config, -c`: Output configuration file path
- **Function**: Creates and saves new client configuration

#### `status` Command

Displays current client configuration and status:

- **Options**:
  - `--config, -c`: Configuration file path to read
- **Function**: Shows client settings, sync directory status, and file count

## Signal Handling

The application handles SIGINT and SIGTERM signals for graceful shutdown:

- Logs shutdown signal reception
- Initiates client stop sequence
- Ensures clean resource cleanup

## Error Handling

- Configuration errors are caught and logged
- Network connection issues are handled gracefully
- File system errors are logged without crashing the application
- Exit codes are set appropriately for system integration

## Usage Examples

### Start client with default config

```bash
uv run syncer-client start
```

### Initialize new client configuration

```bash
uv run syncer-client init --name my-laptop --sync-dir ./documents
```

### Check client status

```bash
uv run syncer-client status
```

### Start with custom config and verbose logging

```bash
uv run syncer-client start --config custom.yaml --verbose
```

## Dependencies

- `asyncio`: Asynchronous operation support
- `click`: Command-line interface framework
- `yaml`: Configuration file parsing
- `signal`: System signal handling for graceful shutdown
- Custom modules: `SyncEngine`, `FileWatcher`, shared models

## Configuration File Format

```yaml
client_name: "my-client"
sync_directory: "./sync"
server_host: "localhost"
server_port: 8000
ignore_patterns:
  - ".git"
  - "__pycache__"
  - "*.tmp"
api_key: null
```
