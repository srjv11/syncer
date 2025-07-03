import asyncio
import contextlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from shared.models import FileInfo, SyncOperation
from shared.utils import (
    get_file_info,
    get_relative_path,
    normalize_path,
    should_ignore_file,
)

# Constants
CLEANUP_TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)


class SyncEventHandler(FileSystemEventHandler):
    """Handle file system events for synchronization."""

    def __init__(
        self,
        sync_callback: Callable[..., object],
        sync_root: str,
        ignore_patterns: List[str],
    ):
        super().__init__()
        self.sync_callback = sync_callback
        self.sync_root = Path(sync_root)
        self.ignore_patterns = ignore_patterns
        self.pending_events: Dict[str, Dict[str, Any]] = {}  # file_path -> event info
        self.last_event_time: Dict[str, float] = {}  # file_path -> timestamp
        self.base_delay = 0.1  # Minimum delay
        self.max_delay = 2.0  # Maximum delay
        self.adaptive_factor = 1.5  # Multiplier for rapid changes

    def _should_process_event(self, event: FileSystemEvent) -> bool:
        """Check if event should be processed based on ignore patterns."""
        if event.is_directory and event.event_type in ["moved", "deleted"]:
            return True

        file_path = Path(event.src_path)
        relative_path = get_relative_path(str(file_path), str(self.sync_root))

        return not should_ignore_file(relative_path, self.ignore_patterns)

    def _get_file_info(self, file_path: str) -> Optional[FileInfo]:
        """Get file information for sync."""
        file_info_dict = get_file_info(file_path)
        if file_info_dict:
            relative_path = get_relative_path(file_path, str(self.sync_root))
            file_info_dict["path"] = normalize_path(relative_path)
            return FileInfo(**file_info_dict)  # type: ignore[arg-type]
        return None

    async def _delayed_sync(
        self, file_path: str, operation: SyncOperation, old_path: Optional[str] = None
    ) -> None:
        """Adaptively delay sync operation to batch rapid changes."""
        current_time = time.time()

        # Calculate adaptive delay based on recent activity
        if file_path in self.last_event_time:
            time_since_last = current_time - self.last_event_time[file_path]
            if time_since_last < 1.0:  # Rapid changes
                delay = min(self.max_delay, self.base_delay * self.adaptive_factor)
            else:
                delay = self.base_delay
        else:
            delay = self.base_delay

        # Store event info
        self.pending_events[file_path] = {
            "operation": operation,
            "old_path": old_path,
            "timestamp": current_time,
        }
        self.last_event_time[file_path] = current_time

        await asyncio.sleep(delay)

        # Check if this is still the latest event for this file
        if (
            file_path in self.pending_events
            and self.pending_events[file_path]["timestamp"] == current_time
        ):
            event_info = self.pending_events.pop(file_path)
            operation = event_info["operation"]
            old_path = event_info["old_path"]

            # Get current file info if file still exists
            file_info = None
            if operation != SyncOperation.DELETE:
                file_info = self._get_file_info(file_path)
                if not file_info:
                    operation = SyncOperation.DELETE

            if operation == SyncOperation.DELETE:
                # Create minimal file info for deletion
                relative_path = get_relative_path(file_path, str(self.sync_root))
                file_info = FileInfo(
                    path=normalize_path(relative_path),
                    size=0,
                    checksum="",
                    modified_time=datetime.now(),
                    is_directory=Path(file_path).is_dir()
                    if Path(file_path).exists()
                    else False,
                )

            if file_info:
                await self.sync_callback(operation, file_info, old_path)  # type: ignore

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file/directory creation."""
        if not self._should_process_event(event):
            return

        file_path = event.src_path
        asyncio.create_task(self._delayed_sync(file_path, SyncOperation.CREATE))
        logger.debug(f"File created: {file_path}")

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file/directory modification."""
        if event.is_directory or not self._should_process_event(event):
            return

        file_path = event.src_path
        asyncio.create_task(self._delayed_sync(file_path, SyncOperation.UPDATE))
        logger.debug(f"File modified: {file_path}")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file/directory deletion."""
        if not self._should_process_event(event):
            return

        file_path = event.src_path
        asyncio.create_task(self._delayed_sync(file_path, SyncOperation.DELETE))
        logger.debug(f"File deleted: {file_path}")

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file/directory move/rename."""
        if not self._should_process_event(event):
            return

        if not isinstance(event, FileMovedEvent):
            return

        src_path = event.src_path
        dest_path = event.dest_path

        # Check if destination should also be ignored
        dest_file = Path(dest_path)
        dest_relative = get_relative_path(str(dest_file), str(self.sync_root))

        if should_ignore_file(dest_relative, self.ignore_patterns):
            # Moving to ignored location = deletion
            asyncio.create_task(self._delayed_sync(src_path, SyncOperation.DELETE))
        else:
            # Normal move operation
            old_relative_path = get_relative_path(src_path, str(self.sync_root))
            asyncio.create_task(
                self._delayed_sync(dest_path, SyncOperation.MOVE, old_relative_path)
            )

        logger.debug(f"File moved: {src_path} -> {dest_path}")


class FileWatcher:
    """File system watcher for automatic synchronization."""

    def __init__(
        self,
        sync_root: str,
        sync_callback: Callable[..., object],
        ignore_patterns: Optional[List[str]] = None,
    ):
        self.sync_root = Path(sync_root)
        self.sync_callback = sync_callback
        self.ignore_patterns = ignore_patterns or []
        self.observer: Optional[Any] = None
        self.event_handler: Optional[SyncEventHandler] = None
        self.is_running = False
        self._cleanup_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start watching the sync directory."""
        if self.is_running:
            logger.warning("File watcher is already running")
            return

        if not self.sync_root.exists():
            logger.error(f"Sync directory does not exist: {self.sync_root}")
            return

        self.event_handler = SyncEventHandler(
            self.sync_callback, str(self.sync_root), self.ignore_patterns
        )

        self.observer = Observer()
        self.observer.schedule(self.event_handler, str(self.sync_root), recursive=True)  # type: ignore[no-untyped-call]

        self.observer.start()  # type: ignore[no-untyped-call]
        self.is_running = True

        # Start cleanup task for old event timestamps
        self._cleanup_task = asyncio.create_task(self._cleanup_old_events())

        logger.info(f"Started watching directory: {self.sync_root}")

    async def stop(self) -> None:
        """Stop watching the sync directory."""
        if not self.is_running or not self.observer:
            return

        self.observer.stop()
        self.observer.join()
        self.is_running = False

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        logger.info("Stopped file watcher")

    def is_watching(self) -> bool:
        """Check if watcher is currently active."""
        return (
            self.is_running and self.observer is not None and self.observer.is_alive()
        )

    async def scan_initial_files(self) -> List[FileInfo]:
        """Scan directory for initial file list."""
        files: List[FileInfo] = []

        if not self.sync_root.exists():
            return files

        for file_path in self.sync_root.rglob("*"):
            if file_path.is_file():
                relative_path = get_relative_path(str(file_path), str(self.sync_root))

                if not should_ignore_file(relative_path, self.ignore_patterns):
                    file_info = self._get_file_info(str(file_path))
                    if file_info:
                        files.append(file_info)

        logger.info(f"Found {len(files)} files in sync directory")
        return files

    def _get_file_info(self, file_path: str) -> Optional[FileInfo]:
        """Get file information for sync."""
        file_info_dict = get_file_info(file_path)
        if file_info_dict:
            relative_path = get_relative_path(file_path, str(self.sync_root))
            file_info_dict["path"] = normalize_path(relative_path)
            return FileInfo(**file_info_dict)  # type: ignore[arg-type]
        return None

    async def _cleanup_old_events(self) -> None:
        """Clean up old event timestamps periodically."""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Clean up every minute
                current_time = time.time()

                # Remove timestamps older than 5 minutes
                if self.event_handler:
                    old_keys = [
                        key
                        for key, timestamp in self.event_handler.last_event_time.items()
                        if current_time - timestamp > CLEANUP_TIMEOUT_SECONDS
                    ]
                    for key in old_keys:
                        self.event_handler.last_event_time.pop(key, None)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in cleanup task")

    def get_pending_events_count(self) -> int:
        """Get number of pending events."""
        if self.event_handler:
            return len(self.event_handler.pending_events)
        return 0

    def get_event_stats(self) -> Dict[str, Any]:
        """Get statistics about file events."""
        if self.event_handler:
            return {
                "pending_events": len(self.event_handler.pending_events),
                "tracked_files": len(self.event_handler.last_event_time),
                "base_delay": self.event_handler.base_delay,
                "max_delay": self.event_handler.max_delay,
            }
        return {}
