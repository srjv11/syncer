import asyncio
import functools
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from pydantic import ValidationError

from shared.models import ClientConfig, FileInfo, SyncOperation

from .sync_engine import SyncEngine
from .watcher import FileWatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SyncClient:
    """Main synchronization client."""

    def __init__(self, config: ClientConfig):
        self.config = config
        self.sync_engine: Optional[SyncEngine] = None
        self.file_watcher: Optional[FileWatcher] = None
        self.running = False

    async def start(self) -> None:
        """Start the sync client."""
        logger.info(f"Starting sync client: {self.config.client_name}")
        logger.info(f"Sync directory: {self.config.sync_directory}")
        logger.info(f"Server: {self.config.server_host}:{self.config.server_port}")

        # Initialize sync engine
        self.sync_engine = SyncEngine(self.config)
        await self.sync_engine.start()

        # Initialize file watcher
        self.file_watcher = FileWatcher(
            self.config.sync_directory,
            self._on_file_changed,
            self.config.ignore_patterns,
        )

        # Perform initial sync
        logger.info("Performing initial sync...")
        initial_files = await self.file_watcher.scan_initial_files()
        await self.sync_engine.perform_initial_sync(initial_files)

        # Start file watcher
        await self.file_watcher.start()

        self.running = True
        logger.info("Sync client started successfully")

    async def stop(self) -> None:
        """Stop the sync client."""
        logger.info("Stopping sync client...")
        self.running = False

        if self.file_watcher:
            await self.file_watcher.stop()

        if self.sync_engine:
            await self.sync_engine.stop()

        logger.info("Sync client stopped")

    async def _on_file_changed(
        self,
        operation: SyncOperation,
        file_info: FileInfo,
        old_path: Optional[str] = None,
    ) -> None:
        """Handle file change events from watcher."""
        logger.info(f"File {operation.value}: {file_info.path}")

        if self.sync_engine:
            await self.sync_engine.sync_file(operation, file_info, old_path)

    async def run(self) -> None:
        """Run the sync client until interrupted."""
        try:
            # Set up signal handlers in the async context
            loop = asyncio.get_running_loop()

            def signal_handler(sig: int) -> None:
                logger.info(f"Received shutdown signal {sig}")
                self.running = False
                # Cancel all tasks
                for task in asyncio.all_tasks(loop):
                    if not task.done() and task != asyncio.current_task():
                        task.cancel()

            # Set up signal handlers for graceful shutdown
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, functools.partial(signal_handler, sig))

            await self.start()

            # Keep running until explicitly stopped
            while self.running:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    logger.info("Run loop cancelled")
                    break

        except (KeyboardInterrupt, asyncio.CancelledError) as e:
            logger.info(f"Client interrupted: {type(e).__name__}")
        except Exception:
            logger.exception("Unexpected error in client run")
            raise
        finally:
            await self.stop()


def load_config(config_path: str) -> ClientConfig:
    """Load client configuration from file."""
    config_file = Path(config_path)

    if not config_file.exists():
        # Create default config
        default_config = ClientConfig(
            client_name="default-client",
            sync_directory="./sync",
        )

        config_file.parent.mkdir(parents=True, exist_ok=True)
        with config_file.open("w") as f:
            yaml.dump(
                default_config.model_dump(mode="json"), f, default_flow_style=False
            )

        logger.info(f"Created default config at: {config_file}")
        return default_config

    with config_file.open() as f:
        config_data = yaml.safe_load(f)

    return ClientConfig(**config_data)


@click.group()
def cli() -> None:
    """File sync client CLI."""
    pass


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def start(config: str, verbose: bool) -> None:
    """Start the sync client."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        try:
            client_config = load_config(config)
            client = SyncClient(client_config)
        except ValidationError as e:
            logger.exception("Configuration validation error")
            for error in e.errors():
                logger.exception(f"  {error['loc'][0]}: {error['msg']}")
            sys.exit(1)

        # Run the client with proper exception handling
        try:
            asyncio.run(client.run())
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except asyncio.CancelledError:
            logger.info("Client cancelled gracefully")
        finally:
            logger.info("Client shutdown complete")

    except Exception:
        logger.exception("Error starting client")
        sys.exit(1)


@cli.command()
@click.option("--name", prompt="Client name", help="Name for this client")
@click.option("--sync-dir", prompt="Sync directory", help="Directory to synchronize")
@click.option("--server-host", default="localhost", help="Server hostname")
@click.option("--server-port", default=8000, help="Server port")
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def init(
    name: str, sync_dir: str, server_host: str, server_port: int, config: str
) -> None:
    """Initialize client configuration."""
    try:
        config_data = ClientConfig(
            client_name=name,
            sync_directory=sync_dir,
            server_host=server_host,
            server_port=server_port,
        )

        config_file = Path(config)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with config_file.open("w") as f:
            yaml.dump(config_data.model_dump(mode="json"), f, default_flow_style=False)

        click.echo(f"Configuration saved to: {config_file}")
    except ValidationError as e:
        click.echo("Configuration validation error:", err=True)
        for error in e.errors():
            click.echo(f"  {error['loc'][0]}: {error['msg']}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def status(config: str) -> None:
    """Show client status and configuration."""
    try:
        client_config = load_config(config)

        click.echo("Client Configuration:")
        click.echo(f"  Name: {client_config.client_name}")
        click.echo(f"  Sync Directory: {client_config.sync_directory}")
        click.echo(f"  Server: {client_config.server_host}:{client_config.server_port}")
        click.echo(f"  Ignore Patterns: {client_config.ignore_patterns}")

        # Check if sync directory exists
        sync_path = Path(client_config.sync_directory)
        if sync_path.exists():
            file_count = len(list(sync_path.rglob("*")))
            click.echo(f"  Files in sync directory: {file_count}")
        else:
            click.echo("  Sync directory does not exist")

    except ValidationError as e:
        click.echo("Configuration validation error:", err=True)
        for error in e.errors():
            click.echo(f"  {error['loc'][0]}: {error['msg']}", err=True)
    except Exception as e:
        click.echo(f"Error reading configuration: {e}", err=True)


if __name__ == "__main__":
    cli()
