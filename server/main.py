import asyncio
import functools
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import aiofiles
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from shared.compression import CompressionType, CompressionUtil
from shared.exceptions import DatabaseError, FileNotFoundError
from shared.models import (
    ClientInfo,
    FileInfo,
    ServerConfig,
    SyncOperation,
    SyncRequest,
    SyncResponse,
)
from shared.utils import ensure_directory, get_file_info

from .file_manager import FileManager
from .websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class SyncServer:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.app = FastAPI(title="File Sync Server")
        self.websocket_manager: WebSocketManager = WebSocketManager()
        self.file_manager = FileManager(config.sync_directory)
        self.clients: Dict[str, ClientInfo] = {}

        ensure_directory(config.sync_directory)
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.app.get("/health")
        async def health_check() -> Dict[str, Any]:
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        @self.app.post("/register")
        async def register_client(client_info: ClientInfo) -> Dict[str, Any]:
            self.clients[client_info.client_id] = client_info
            await self.websocket_manager.broadcast_to_others(
                client_info.client_id,
                {"type": "client_joined", "client": client_info.dict()},
            )
            return {"success": True, "message": "Client registered successfully"}

        @self.app.post("/sync")
        async def sync_files(sync_request: SyncRequest) -> SyncResponse:
            try:
                # Get server file list
                server_files = await self.file_manager.get_file_list(
                    sync_request.sync_root
                )

                # Compare with client files
                files_to_sync = []
                conflicts = []

                for client_file in sync_request.files:
                    server_file = next(
                        (f for f in server_files if f.path == client_file.path), None
                    )

                    if not server_file:
                        # File doesn't exist on server, client should upload
                        files_to_sync.append(client_file)
                    elif server_file.checksum != client_file.checksum:
                        # File differs, check timestamps for conflict resolution
                        if server_file.modified_time > client_file.modified_time:
                            conflicts.append(client_file.path)
                        else:
                            files_to_sync.append(client_file)

                # Check for files that exist on server but not on client
                client_paths = {f.path for f in sync_request.files}
                for server_file in server_files:
                    if server_file.path not in client_paths:
                        files_to_sync.append(server_file)

                return SyncResponse(
                    success=True,
                    message="Sync analysis complete",
                    files_to_sync=files_to_sync,
                    conflicts=conflicts,
                )
            except DatabaseError as e:
                logger.exception(f"Database error during sync: {e}")
                raise HTTPException(status_code=500, detail=f"Database error: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error during sync: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/upload")
        async def upload_file(
            file: UploadFile = File(...),
            relative_path: str = Form(...),
            client_id: str = Form(...),
            compression_type: str = Form(CompressionType.NONE.value),
            original_size: int = Form(0),
        ) -> Dict[str, Any]:
            try:
                full_path = Path(self.config.sync_directory) / relative_path
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Read file content
                file_content = await file.read()

                # Decompress if needed
                try:
                    comp_type = CompressionType(compression_type)
                    if comp_type != CompressionType.NONE:
                        file_content = CompressionUtil.decompress_data(
                            file_content, comp_type
                        )
                        logger.debug(
                            f"Decompressed {relative_path}: {len(file_content)} bytes"
                        )
                except Exception as e:
                    logger.exception(f"Error decompressing {relative_path}: {e}")
                    raise HTTPException(
                        status_code=400, detail=f"Decompression failed: {e}"
                    )

                # Write decompressed content to file
                async with aiofiles.open(full_path, "wb") as f:
                    await f.write(file_content)

                # Update file metadata
                file_info = get_file_info(str(full_path))
                if file_info:
                    await self.file_manager.update_file_metadata(FileInfo(**file_info))  # type: ignore[arg-type]

                # Notify other clients
                await self.websocket_manager.broadcast_to_others(
                    client_id,
                    {
                        "type": "file_updated",
                        "operation": SyncOperation.UPDATE,
                        "file_path": relative_path,
                        "client_id": client_id,
                    },
                )

                return {"success": True, "message": "File uploaded successfully"}
            except PermissionError as e:
                logger.exception(f"Permission error uploading {relative_path}: {e}")
                raise HTTPException(status_code=403, detail=f"Permission denied: {e}")
            except OSError as e:
                if e.errno == 28:  # No space left on device
                    logger.exception(f"Disk space error uploading {relative_path}: {e}")
                    raise HTTPException(
                        status_code=507, detail=f"Insufficient storage: {e}"
                    )
                logger.exception(f"OS error uploading {relative_path}: {e}")
                raise HTTPException(status_code=500, detail=f"File system error: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error uploading {relative_path}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/download/{file_path:path}")
        async def download_file(file_path: str, request: Request) -> StreamingResponse:
            full_path = Path(self.config.sync_directory) / file_path
            if not full_path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            # Support range requests for partial downloads
            file_size = full_path.stat().st_size
            range_header = request.headers.get("range")

            if range_header:
                # Parse range header
                range_match = range_header.replace("bytes=", "").split("-")
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if range_match[1] else file_size - 1

                # Validate range
                if start >= file_size or end >= file_size or start > end:
                    raise HTTPException(status_code=416, detail="Range not satisfiable")

                chunk_size = end - start + 1

                async def stream_file_range():
                    async with aiofiles.open(full_path, "rb") as f:
                        await f.seek(start)
                        bytes_read = 0
                        while bytes_read < chunk_size:
                            remaining = min(8192, chunk_size - bytes_read)
                            chunk = await f.read(remaining)
                            if not chunk:
                                break
                            bytes_read += len(chunk)
                            yield chunk

                headers = {
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(chunk_size),
                }

                return StreamingResponse(
                    stream_file_range(),
                    status_code=206,
                    headers=headers,
                    media_type="application/octet-stream",
                )
            else:
                # Full file download
                async def stream_file():
                    async with aiofiles.open(full_path, "rb") as f:
                        while chunk := await f.read(8192):
                            yield chunk

                headers = {"Content-Length": str(file_size), "Accept-Ranges": "bytes"}

                return StreamingResponse(
                    stream_file(),
                    headers=headers,
                    media_type="application/octet-stream",
                )

        @self.app.delete("/files/{file_path:path}")
        async def delete_file(file_path: str, client_id: str) -> Dict[str, Any]:
            try:
                full_path = Path(self.config.sync_directory) / file_path
                if full_path.exists():
                    if full_path.is_file():
                        full_path.unlink()
                    else:
                        full_path.rmdir()

                await self.file_manager.remove_file_metadata(file_path)

                # Notify other clients
                await self.websocket_manager.broadcast_to_others(
                    client_id,
                    {
                        "type": "file_deleted",
                        "operation": SyncOperation.DELETE,
                        "file_path": file_path,
                        "client_id": client_id,
                    },
                )

                return {"success": True, "message": "File deleted successfully"}
            except PermissionError as e:
                logger.exception(f"Permission error deleting {file_path}: {e}")
                raise HTTPException(status_code=403, detail=f"Permission denied: {e}")
            except FileNotFoundError as e:
                logger.warning(f"File not found for deletion {file_path}: {e}")
                # Return success for idempotent delete operation
                return {"success": True, "message": "File already deleted"}
            except OSError as e:
                logger.exception(f"OS error deleting {file_path}: {e}")
                raise HTTPException(status_code=500, detail=f"File system error: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error deleting {file_path}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # WebSocket endpoint
        self.app.websocket_route("/ws/{client_id}")(
            self.websocket_manager.websocket_endpoint
        )

    async def start(self) -> None:
        # Initialize database
        await self.file_manager._init_database()

        config = uvicorn.Config(
            self.app, host=self.config.host, port=self.config.port, log_level="info"
        )
        server = uvicorn.Server(config)

        # Set up graceful shutdown
        def signal_handler(sig: int) -> None:
            logging.info(f"Received shutdown signal {sig}")
            server.should_exit = True

        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, functools.partial(signal_handler, sig))

        try:
            await server.serve()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        await self.file_manager.close()
        # Close any other resources


def main() -> None:
    config = ServerConfig()
    server = SyncServer(config)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logging.info("Server interrupted by user")
    except Exception as e:
        logging.exception(f"Server error: {e}")
        raise
    finally:
        logging.info("Server shutdown complete")


if __name__ == "__main__":
    main()
