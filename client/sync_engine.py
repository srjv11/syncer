import asyncio
import contextlib
import errno
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from shared.compression import CompressionUtil
from shared.diff import DifferentialSync
from shared.exceptions import ConnectionError as SyncConnectionError
from shared.exceptions import DiskSpaceError
from shared.exceptions import FileNotFoundError as SyncFileNotFoundError
from shared.exceptions import FileOperationError
from shared.exceptions import PermissionError as SyncPermissionError
from shared.exceptions import ServerError, WebSocketError
from shared.metrics import (
    increment_counter,
    record_histogram,
    start_global_collection,
    timer,
)
from shared.models import (
    ClientConfig,
    ClientInfo,
    FileInfo,
    SyncOperation,
    SyncRequest,
    SyncResponse,
)
from shared.protocols import (
    ConnectionRequest,
    HeartbeatMessage,
    MessageType,
    WebSocketMessage,
)
from shared.utils import ensure_directory, get_file_info, normalize_path

# Constants
HTTP_OK = 200
CLEANUP_TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)


class SyncEngine:
    """Client synchronization engine."""

    def __init__(self, config: ClientConfig):
        self.config = config
        self.client_id = (
            f"{config.client_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        self.sync_root = Path(config.sync_directory)
        self.websocket: Optional[Any] = None
        self.session: Optional[Any] = None
        self.is_connected = False
        self.heartbeat_task: Optional[asyncio.Task[None]] = None
        self._reconnect_task: Optional[asyncio.Task[None]] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._base_reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._should_reconnect = True
        self.compression_util = CompressionUtil()
        self.differential_sync = DifferentialSync()
        self._enable_compression = True
        self._enable_differential = True

        ensure_directory(str(self.sync_root))

    async def start(self) -> None:
        """Start the sync engine."""
        # Start metrics collection
        start_global_collection()

        # Configure connection pooling and timeouts for better performance
        timeout = aiohttp.ClientTimeout(total=300, sock_read=60, sock_connect=10)
        connector = aiohttp.TCPConnector(
            limit=20,  # Total connection pool size
            limit_per_host=10,  # Connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
            keepalive_timeout=120,  # Keep connections alive
            enable_cleanup_closed=True,
        )
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

        with timer("sync_engine_startup"):
            await self._connect_websocket()
            await self._register_client()
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        increment_counter("sync_engine_starts")
        logger.info(f"Sync engine started for client: {self.client_id}")

    async def stop(self) -> None:
        """Stop the sync engine."""
        self.is_connected = False
        self._should_reconnect = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.heartbeat_task

        if self.websocket:
            await self.websocket.close()

        if self.session:
            await self.session.close()

        logger.info("Sync engine stopped")

    async def _connect_websocket(self) -> None:
        """Connect to server WebSocket with retry logic."""
        ws_url = f"ws://{self.config.server_host}:{self.config.server_port}/ws/{self.client_id}"

        try:
            self.websocket = await websockets.connect(ws_url)
            self.is_connected = True
            self._reconnect_attempts = 0  # Reset on successful connection

            # Send connection request
            connection_req = ConnectionRequest(
                client_id=self.client_id,
                client_name=self.config.client_name,
                sync_root=str(self.sync_root),
                api_key=self.config.api_key or "",
            )

            message = WebSocketMessage(
                type=MessageType.CLIENT_CONNECT,
                data=connection_req.dict(),
                client_id=self.client_id,
                timestamp=datetime.now().isoformat(),
            )

            await self.websocket.send(json.dumps(message.dict()))

            # Start listening for messages
            self._listen_task = asyncio.create_task(self._listen_websocket())

            logger.info(f"Connected to WebSocket: {ws_url}")
        except (ConnectionError, OSError):
            logger.exception("Failed to connect WebSocket")
            self.is_connected = False
            await self._schedule_reconnect()
        except Exception as e:
            logger.exception("Unexpected error connecting WebSocket")
            self.is_connected = False
            raise WebSocketError(f"Failed to connect to WebSocket: {e}", str(e)) from e

    async def _listen_websocket(self) -> None:
        """Listen for WebSocket messages from server."""
        try:
            if self.websocket:
                async for message in self.websocket:
                    try:
                        data = json.loads(message)
                        await self._handle_websocket_message(data)
                    except json.JSONDecodeError:
                        logger.exception("Invalid JSON received")
        except (ConnectionClosed, InvalidStatusCode) as e:
            logger.warning(f"WebSocket connection lost: {e}")
            self.is_connected = False
            if self._should_reconnect:
                await self._schedule_reconnect()
        except json.JSONDecodeError:
            logger.exception("Invalid JSON received")
        except Exception as e:
            logger.exception("WebSocket listen error")
            self.is_connected = False
            if self._should_reconnect:
                await self._schedule_reconnect()
            raise WebSocketError(f"WebSocket listener failed: {e}", str(e)) from e

    async def _handle_websocket_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        try:
            message_type = data.get("type")
            message_data = data.get("data", {})

            if message_type == "file_updated":
                await self._handle_remote_file_update(message_data)
            elif message_type == "file_deleted":
                await self._handle_remote_file_delete(message_data)
            elif message_type == "client_joined":
                logger.info(f"Client joined: {message_data.get('name')}")
            elif message_type == "client_left":
                logger.info(f"Client left: {message_data.get('client_id')}")
            elif message_type == MessageType.HEARTBEAT:
                # Heartbeat response, no action needed
                pass
            else:
                logger.debug(f"Unknown message type: {message_type}")
        except Exception:
            logger.exception("Error handling WebSocket message")

    async def _handle_remote_file_update(self, data: Dict[str, Any]) -> None:
        """Handle file update notification from another client."""
        try:
            file_path = data.get("file_path")
            client_id = data.get("client_id")

            if client_id == self.client_id:
                return  # Ignore own updates

            if not file_path:
                return

            logger.info(f"Remote file updated: {file_path} by {client_id}")
            await self.download_file(str(file_path))
        except Exception:
            logger.exception("Error handling remote file update")

    async def _handle_remote_file_delete(self, data: Dict[str, Any]) -> None:
        """Handle file deletion notification from another client."""
        try:
            file_path = data.get("file_path")
            client_id = data.get("client_id")

            if client_id == self.client_id:
                return  # Ignore own deletions

            if not file_path:
                return

            logger.info(f"Remote file deleted: {file_path} by {client_id}")
            local_path = self.sync_root / str(file_path)
            if local_path.exists():
                if local_path.is_file():
                    local_path.unlink()
                else:
                    local_path.rmdir()
                logger.info(f"Deleted local file: {local_path}")
        except Exception:
            logger.exception("Error handling remote file delete")

    async def _register_client(self) -> None:
        """Register client with server."""
        client_info = ClientInfo(
            client_id=self.client_id,
            name=self.config.client_name,
            sync_root=str(self.sync_root),
            last_seen=datetime.now(),
            is_online=True,
        )

        url = f"http://{self.config.server_host}:{self.config.server_port}/register"
        try:
            if self.session:
                async with self.session.post(url, json=client_info.dict()) as response:
                    if response.status == HTTP_OK:
                        logger.info("Client registered successfully")
                    else:
                        logger.error(f"Failed to register client: {response.status}")
        except aiohttp.ClientConnectionError as e:
            logger.exception("Connection error registering client")
            raise SyncConnectionError(
                "Cannot connect to server",
                self.config.server_host,
                self.config.server_port,
                str(e),
            ) from e
        except aiohttp.ClientResponseError as e:
            logger.exception("Server error registering client")
            raise ServerError(
                f"Server rejected registration: {e}", e.status, str(e)
            ) from e
        except Exception:
            logger.exception("Unexpected error registering client")
            raise

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while self.is_connected:
            try:
                if self.websocket:
                    heartbeat = HeartbeatMessage(
                        client_id=self.client_id, timestamp=datetime.now().isoformat()
                    )

                    message = WebSocketMessage(
                        type=MessageType.HEARTBEAT,
                        data=heartbeat.dict(),
                        client_id=self.client_id,
                        timestamp=datetime.now().isoformat(),
                    )

                    await self.websocket.send(json.dumps(message.dict()))

                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
            except Exception:
                logger.exception("Heartbeat error")
                break

    async def sync_file(
        self,
        operation: SyncOperation,
        file_info: FileInfo,
        old_path: Optional[str] = None,
    ) -> None:
        """Sync file operation with server."""
        try:
            if operation in (SyncOperation.CREATE, SyncOperation.UPDATE):
                await self.upload_file(file_info)
            elif operation == SyncOperation.DELETE:
                await self.delete_file(file_info.path)
            elif operation == SyncOperation.MOVE and old_path:
                await self.move_file(old_path, file_info.path)

            # Notify other clients via WebSocket
            if self.websocket and self.is_connected:
                try:
                    message = WebSocketMessage(
                        type=MessageType.FILE_CHANGED,
                        data={
                            "operation": operation.value,
                            "file_path": file_info.path,
                            "old_path": old_path,
                        },
                        client_id=self.client_id,
                        timestamp=datetime.now().isoformat(),
                    )
                    await self.websocket.send(json.dumps(message.dict()))
                except (ConnectionClosed, InvalidStatusCode):
                    logger.exception("WebSocket connection lost while sending")
                    self.is_connected = False
                    if self._should_reconnect:
                        await self._schedule_reconnect()
                except Exception as e:
                    logger.exception("Failed to send WebSocket message")
                    self.is_connected = False
                    if self._should_reconnect:
                        await self._schedule_reconnect()
                    raise WebSocketError(f"Failed to send message: {e}", str(e)) from e

        except (WebSocketError, FileOperationError, ServerError, SyncConnectionError):
            raise
        except Exception as e:
            logger.exception(f"Unexpected error syncing file {file_info.path}")
            raise FileOperationError(
                f"Sync failed for {file_info.path}", file_info.path, "sync", str(e)
            ) from e

    async def upload_file(self, file_info: FileInfo) -> None:
        """Upload file to server with streaming."""
        with timer("file_upload", {"file_size": str(file_info.size)}):
            local_path = self.sync_root / file_info.path

            if not local_path.exists() or local_path.is_dir():
                logger.warning(f"Cannot upload non-existent or directory: {local_path}")
                increment_counter("upload_skipped", tags={"reason": "not_found"})
                return

            url = f"http://{self.config.server_host}:{self.config.server_port}/upload"

            # Calculate adaptive chunk size based on file size
            chunk_size = self._get_adaptive_chunk_size(file_info.size)
            record_histogram("upload_chunk_size", chunk_size)

            try:
                # Create a streaming upload
                async def file_generator():
                    async with aiofiles.open(local_path, "rb") as f:
                        while chunk := await f.read(chunk_size):
                            yield chunk

                data = aiohttp.FormData()
                data.add_field(
                    "file",
                    file_generator(),
                    filename=local_path.name,
                    content_type="application/octet-stream",
                )
                data.add_field("relative_path", file_info.path)
                data.add_field("client_id", self.client_id)

                if self.session:
                    async with self.session.post(url, data=data) as response:
                        if response.status == HTTP_OK:
                            logger.info(f"Uploaded file: {file_info.path}")
                            increment_counter("files_uploaded")
                            record_histogram("upload_file_size", file_info.size)
                        else:
                            error_msg = f"Failed to upload {file_info.path}: HTTP {response.status}"
                            logger.error(error_msg)
                            increment_counter(
                                "upload_errors", tags={"status": str(response.status)}
                            )
                            raise ServerError(error_msg, response.status)
            except SyncFileNotFoundError:
                raise
            except PermissionError as e:
                raise SyncPermissionError(str(local_path), "read", str(e)) from e
            except OSError as e:
                if e.errno == errno.ENOSPC:  # No space left on device
                    raise DiskSpaceError(file_info.path, str(e)) from e
                raise FileOperationError(
                    f"OS error uploading {file_info.path}",
                    file_info.path,
                    "upload",
                    str(e),
                ) from e
            except aiohttp.ClientConnectionError as e:
                raise SyncConnectionError(
                    "Cannot connect to server for upload",
                    self.config.server_host,
                    self.config.server_port,
                    str(e),
                ) from e
            except Exception as e:
                logger.exception(
                    f"Unexpected error uploading file {file_info.path}: {e}"
                )
                raise FileOperationError(
                    f"Upload failed for {file_info.path}",
                    file_info.path,
                    "upload",
                    str(e),
                ) from e

    async def download_file(self, file_path: str, resume: bool = True) -> None:
        """Download file from server with resumable downloads."""
        url = f"http://{self.config.server_host}:{self.config.server_port}/download/{file_path}"
        local_path = self.sync_root / file_path

        try:
            # Ensure parent directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists and get current size for resume
            headers = {}
            if resume and local_path.exists():
                current_size = local_path.stat().st_size
                headers["Range"] = f"bytes={current_size}-"
                mode = "ab"  # Append mode
            else:
                mode = "wb"  # Write mode

            if self.session:
                async with self.session.get(url, headers=headers) as response:
                    if response.status in (200, 206):  # 206 for partial content
                        async with aiofiles.open(str(local_path), mode) as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        logger.info(f"Downloaded file: {file_path}")
                    elif response.status == 404:
                        logger.warning(f"File not found on server: {file_path}")
                    elif response.status == 416 and resume:
                        # Range not satisfiable, download full file
                        logger.info(
                            f"Resuming download failed, downloading full file: {file_path}"
                        )
                        await self.download_file(file_path, resume=False)
                    else:
                        error_msg = (
                            f"Failed to download {file_path}: HTTP {response.status}"
                        )
                        logger.error(error_msg)
                        if response.status == 404:
                            raise SyncFileNotFoundError(file_path)
                        else:
                            raise ServerError(error_msg, response.status)
        except SyncFileNotFoundError:
            raise
        except PermissionError as e:
            raise SyncPermissionError(str(local_path), "write", str(e)) from e
        except OSError as e:
            if e.errno == errno.ENOSPC:  # No space left on device
                raise DiskSpaceError(file_path, str(e)) from e
            raise FileOperationError(
                f"OS error downloading {file_path}", file_path, "download", str(e)
            ) from e
        except aiohttp.ClientConnectionError as e:
            raise SyncConnectionError(
                "Cannot connect to server for download",
                self.config.server_host,
                self.config.server_port,
                str(e),
            ) from e
        except Exception as e:
            logger.exception(f"Unexpected error downloading file {file_path}")
            raise FileOperationError(
                f"Download failed for {file_path}", file_path, "download", str(e)
            ) from e

    async def delete_file(self, file_path: str) -> None:
        """Delete file on server."""
        url = f"http://{self.config.server_host}:{self.config.server_port}/files/{file_path}"

        try:
            params = {"client_id": self.client_id}
            if self.session:
                async with self.session.delete(url, params=params) as response:
                    if response.status == HTTP_OK:
                        logger.info(f"Deleted file on server: {file_path}")
                    else:
                        error_msg = (
                            f"Failed to delete {file_path}: HTTP {response.status}"
                        )
                        logger.error(error_msg)
                        raise ServerError(error_msg, response.status)
        except aiohttp.ClientConnectionError as e:
            raise SyncConnectionError(
                "Cannot connect to server for delete",
                self.config.server_host,
                self.config.server_port,
                str(e),
            ) from e
        except Exception as e:
            logger.exception(f"Unexpected error deleting file {file_path}")
            raise FileOperationError(
                f"Delete failed for {file_path}", file_path, "delete", str(e)
            ) from e

    async def move_file(self, old_path: str, new_path: str) -> None:
        """Handle file move operation."""
        # For now, implement as delete + upload
        await self.delete_file(old_path)

        local_new_path = self.sync_root / new_path
        if local_new_path.exists():
            file_info_dict = get_file_info(str(local_new_path))
            if file_info_dict:
                file_info_dict["path"] = normalize_path(new_path)
                file_info = FileInfo(**file_info_dict)  # type: ignore[arg-type]
                await self.upload_file(file_info)

    async def perform_initial_sync(self, local_files: List[FileInfo]) -> None:
        """Perform initial synchronization with server."""
        sync_request = SyncRequest(
            client_id=self.client_id, files=local_files, sync_root=str(self.sync_root)
        )

        url = f"http://{self.config.server_host}:{self.config.server_port}/sync"

        try:
            if self.session:
                async with self.session.post(url, json=sync_request.dict()) as response:
                    if response.status == HTTP_OK:
                        sync_response = SyncResponse(**(await response.json()))

                        logger.info(
                            f"Initial sync: {len(sync_response.files_to_sync)} files to sync"
                        )
                        logger.info(
                            f"Conflicts detected: {len(sync_response.conflicts)}"
                        )

                        # Create concurrent download tasks
                        download_tasks = []
                        for file_info in sync_response.files_to_sync:
                            if not (self.sync_root / file_info.path).exists():
                                download_tasks.append(
                                    self.download_file(file_info.path)
                                )

                        # Execute downloads concurrently (max 3 concurrent)
                        if download_tasks:
                            semaphore = asyncio.Semaphore(3)

                            async def download_with_semaphore(task):
                                async with semaphore:
                                    await task

                            await asyncio.gather(
                                *[
                                    download_with_semaphore(task)
                                    for task in download_tasks
                                ]
                            )

                        # Create concurrent upload tasks
                        upload_tasks = []
                        server_paths = {f.path for f in sync_response.files_to_sync}
                        for local_file in local_files:
                            if local_file.path not in server_paths:
                                upload_tasks.append(self.upload_file(local_file))

                        # Execute uploads concurrently (max 3 concurrent)
                        if upload_tasks:
                            semaphore = asyncio.Semaphore(3)

                            async def upload_with_semaphore(task):
                                async with semaphore:
                                    await task

                            await asyncio.gather(
                                *[upload_with_semaphore(task) for task in upload_tasks]
                            )

                        if sync_response.conflicts:
                            logger.warning(
                                f"Conflicts detected in files: {sync_response.conflicts}"
                            )

                    else:
                        error_msg = f"Initial sync failed: HTTP {response.status}"
                        logger.error(error_msg)
                        raise ServerError(error_msg, response.status)
        except aiohttp.ClientConnectionError as e:
            raise SyncConnectionError(
                "Cannot connect to server for sync",
                self.config.server_host,
                self.config.server_port,
                str(e),
            ) from e
        except Exception:
            logger.exception("Unexpected error during initial sync")
            raise

    async def _schedule_reconnect(self) -> None:
        """Schedule WebSocket reconnection with exponential backoff."""
        if not self._should_reconnect:
            return

        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(
                f"Max reconnection attempts ({self._max_reconnect_attempts}) reached"
            )
            return

        # Cancel existing reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        self._reconnect_task = asyncio.create_task(self._reconnect_websocket())

    async def _reconnect_websocket(self) -> None:
        """Reconnect to WebSocket with exponential backoff."""
        self._reconnect_attempts += 1

        # Calculate delay with exponential backoff and jitter
        delay = min(
            self._max_reconnect_delay,
            self._base_reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
        )
        # Add jitter to prevent thundering herd
        jittered_delay = delay + random.uniform(0, delay * 0.1)

        logger.info(
            f"Reconnecting to WebSocket in {jittered_delay:.1f}s (attempt {self._reconnect_attempts})"
        )

        try:
            await asyncio.sleep(jittered_delay)

            if not self._should_reconnect:
                return

            # Close existing websocket if any
            if self.websocket:
                with contextlib.suppress(Exception):
                    await self.websocket.close()
                self.websocket = None

            # Attempt to reconnect
            await self._connect_websocket()

        except asyncio.CancelledError:
            logger.info("Reconnection cancelled")
        except Exception:
            logger.exception(f"Reconnection attempt {self._reconnect_attempts} failed")
            if self._should_reconnect:
                await self._schedule_reconnect()

    def _get_adaptive_chunk_size(self, file_size: int) -> int:
        """Calculate adaptive chunk size based on file size."""
        if file_size < 1024 * 1024:  # < 1MB
            return 8192  # 8KB
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return 32768  # 32KB
        elif file_size < 100 * 1024 * 1024:  # < 100MB
            return 65536  # 64KB
        else:  # >= 100MB
            return 131072  # 128KB

    def get_connection_status(self) -> Dict[str, Any]:
        """Get connection status information."""
        return {
            "is_connected": self.is_connected,
            "reconnect_attempts": self._reconnect_attempts,
            "max_reconnect_attempts": self._max_reconnect_attempts,
            "should_reconnect": self._should_reconnect,
            "client_id": self.client_id,
            "compression_enabled": self._enable_compression,
            "differential_enabled": self._enable_differential,
        }

    def configure_optimization(
        self, enable_compression: bool = True, enable_differential: bool = True
    ) -> None:
        """Configure compression and differential sync settings."""
        self._enable_compression = enable_compression
        self._enable_differential = enable_differential
        logger.info(
            f"Optimization configured: compression={enable_compression}, differential={enable_differential}"
        )

    async def get_file_signature(
        self, file_path: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get file signature for differential sync."""
        local_path = self.sync_root / file_path

        if not local_path.exists() or local_path.is_dir():
            return None

        try:
            chunks = self.differential_sync.create_signature(str(local_path))
            return [
                {"offset": chunk.offset, "size": chunk.size, "checksum": chunk.checksum}
                for chunk in chunks
            ]
        except Exception:
            logger.exception(f"Error creating file signature for {file_path}")
            return None

    async def force_reconnect(self) -> None:
        """Force immediate reconnection."""
        logger.info("Forcing WebSocket reconnection")
        self.is_connected = False
        self._reconnect_attempts = 0  # Reset attempts

        if self.websocket:
            with contextlib.suppress(Exception):
                await self.websocket.close()
            self.websocket = None

        await self._connect_websocket()
