import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple, Union

import aiosqlite

from shared.models import FileInfo, SyncOperation
from shared.utils import batch_get_file_info, normalize_path

logger = logging.getLogger(__name__)


class FileManager:
    def __init__(self, sync_directory: str):
        self.sync_directory = Path(sync_directory)
        self.db_path = self.sync_directory / "metadata.db"
        self.sync_directory.mkdir(parents=True, exist_ok=True)
        self._db_pool_size = 10
        self._db_connections: List[aiosqlite.Connection] = []
        self._db_lock = asyncio.Lock()
        self._initialized = False

        # File metadata cache with TTL
        self._metadata_cache: Dict[str, Tuple[FileInfo, float]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_lock = asyncio.Lock()

        # Performance tracking
        self._operation_times: Dict[str, List[float]] = {
            "get_file_metadata": [],
            "update_file_metadata": [],
            "get_file_list": [],
            "batch_update": [],
        }

    async def _init_database(self) -> None:
        """Initialize SQLite database with connection pool and indexes."""
        if self._initialized:
            return

        # Initialize connection pool
        for _ in range(self._db_pool_size):
            conn = await aiosqlite.connect(self.db_path)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA cache_size=10000")
            await conn.execute("PRAGMA temp_store=MEMORY")
            self._db_connections.append(conn)

        # Create tables and indexes
        async with self._get_db_connection() as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS file_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    size INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    modified_time TIMESTAMP NOT NULL,
                    is_directory BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    checksum TEXT,
                    size INTEGER
                )
            """
            )

            # Create performance indexes
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_metadata_path ON file_metadata(path)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_metadata_modified_time ON file_metadata(modified_time)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sync_history_file_path ON sync_history(file_path)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sync_history_client_id ON sync_history(client_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sync_history_timestamp ON sync_history(timestamp)"
            )

            await db.commit()

        self._initialized = True

    @asynccontextmanager
    async def _get_db_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get database connection from pool."""
        async with self._db_lock:
            if not self._db_connections:
                # Create new connection if pool is empty
                conn = await aiosqlite.connect(self.db_path)
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
            else:
                conn = self._db_connections.pop()

        try:
            yield conn
        finally:
            async with self._db_lock:
                if len(self._db_connections) < self._db_pool_size:
                    self._db_connections.append(conn)
                else:
                    await conn.close()

    async def update_file_metadata(self, file_info: FileInfo) -> None:
        """Update or insert file metadata in database."""
        async with self._get_db_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO file_metadata
                (path, size, checksum, modified_time, is_directory, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    normalize_path(file_info.path),
                    file_info.size,
                    file_info.checksum,
                    file_info.modified_time,
                    file_info.is_directory,
                    datetime.now(),
                ),
            )
            await db.commit()

    async def batch_update_file_metadata(self, file_infos: List[FileInfo]) -> None:
        """Batch update multiple file metadata entries."""
        if not file_infos:
            return

        async with self._get_db_connection() as db:
            data = [
                (
                    normalize_path(file_info.path),
                    file_info.size,
                    file_info.checksum,
                    file_info.modified_time,
                    file_info.is_directory,
                    datetime.now(),
                )
                for file_info in file_infos
            ]

            await db.executemany(
                """
                INSERT OR REPLACE INTO file_metadata
                (path, size, checksum, modified_time, is_directory, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                data,
            )
            await db.commit()

    async def remove_file_metadata(self, file_path: str) -> None:
        """Remove file metadata from database."""
        async with self._get_db_connection() as db:
            await db.execute(
                "DELETE FROM file_metadata WHERE path = ?", (normalize_path(file_path),)
            )
            await db.commit()

    async def get_file_metadata(self, file_path: str) -> Optional[FileInfo]:
        """Get file metadata from cache or database."""
        start_time = time.time()

        normalized_path = normalize_path(file_path)

        # Check cache first
        async with self._cache_lock:
            if normalized_path in self._metadata_cache:
                file_info, cache_time = self._metadata_cache[normalized_path]
                if time.time() - cache_time < self._cache_ttl:
                    self._track_operation_time("get_file_metadata", start_time)
                    return file_info
                else:
                    # Remove expired entry
                    del self._metadata_cache[normalized_path]

        # Fetch from database
        async with self._get_db_connection() as db:
            async with db.execute(
                "SELECT path, size, checksum, modified_time, is_directory FROM file_metadata WHERE path = ?",
                (normalized_path,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    file_info = FileInfo(
                        path=row[0],
                        size=row[1],
                        checksum=row[2],
                        modified_time=datetime.fromisoformat(row[3]),
                        is_directory=bool(row[4]),
                    )

                    # Cache the result
                    async with self._cache_lock:
                        self._metadata_cache[normalized_path] = (file_info, time.time())

                    self._track_operation_time("get_file_metadata", start_time)
                    return file_info

        self._track_operation_time("get_file_metadata", start_time)
        return None

    async def get_file_list(
        self, base_path: str = "", use_cache: bool = True
    ) -> List[FileInfo]:
        """Get list of all files in sync directory with metadata."""
        if use_cache:
            # Try to get from database first
            async with self._get_db_connection() as db:
                async with db.execute(
                    "SELECT path, size, checksum, modified_time, is_directory FROM file_metadata ORDER BY path"
                ) as cursor:
                    rows = await cursor.fetchall()
                    if rows:
                        return [
                            FileInfo(
                                path=row[0],
                                size=row[1],
                                checksum=row[2],
                                modified_time=datetime.fromisoformat(row[3]),
                                is_directory=bool(row[4]),
                            )
                            for row in rows
                        ]

        # Fallback to filesystem scan
        files = []
        sync_path = self.sync_directory
        if base_path:
            sync_path = sync_path / base_path

        if sync_path.exists():
            for root, dirs, filenames in os.walk(sync_path):
                # Skip metadata database
                if "metadata.db" in filenames:
                    filenames.remove("metadata.db")
                if "metadata.db-wal" in filenames:
                    filenames.remove("metadata.db-wal")
                if "metadata.db-shm" in filenames:
                    filenames.remove("metadata.db-shm")

                # Collect all file paths first
                file_paths = []
                relative_paths = []

                for filename in filenames:
                    file_path = Path(root) / filename
                    relative_path = file_path.relative_to(self.sync_directory)
                    file_paths.append(str(file_path))
                    relative_paths.append(str(relative_path))

                # Get file info in batches for better performance
                if file_paths:
                    file_infos = await batch_get_file_info(
                        file_paths, fast_checksum=True
                    )
                    for file_info_dict, relative_path in zip(
                        file_infos, relative_paths
                    ):
                        if file_info_dict:
                            file_info_dict["path"] = relative_path
                            files.append(FileInfo(**file_info_dict))  # type: ignore[arg-type]

                for dirname in dirs:
                    dir_path = Path(root) / dirname
                    relative_path = dir_path.relative_to(self.sync_directory)

                    files.append(
                        FileInfo(
                            path=str(relative_path),
                            size=0,
                            checksum="",
                            modified_time=datetime.fromtimestamp(
                                dir_path.stat().st_mtime
                            ),
                            is_directory=True,
                        )
                    )

        # Batch update database with current file information
        if files:
            await self.batch_update_file_metadata(files)

        return files

    async def log_sync_operation(
        self,
        file_path: str,
        operation: SyncOperation,
        client_id: str,
        checksum: str = "",
        size: int = 0,
    ) -> None:
        """Log sync operation to history."""
        async with self._get_db_connection() as db:
            await db.execute(
                """
                INSERT INTO sync_history (file_path, operation, client_id, checksum, size)
                VALUES (?, ?, ?, ?, ?)
            """,
                (normalize_path(file_path), operation.value, client_id, checksum, size),
            )
            await db.commit()

    async def get_sync_history(
        self, file_path: str = "", limit: int = 100
    ) -> List[Dict[str, object]]:
        """Get sync history for a file or all files."""
        async with self._get_db_connection() as db:
            if file_path:
                query = """
                    SELECT file_path, operation, client_id, timestamp, checksum, size
                    FROM sync_history
                    WHERE file_path = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params: Tuple[Union[str, int], ...] = (normalize_path(file_path), limit)
            else:
                query = """
                    SELECT file_path, operation, client_id, timestamp, checksum, size
                    FROM sync_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params = (limit,)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "file_path": row[0],
                        "operation": row[1],
                        "client_id": row[2],
                        "timestamp": row[3],
                        "checksum": row[4],
                        "size": row[5],
                    }
                    for row in rows
                ]

    async def get_conflicts(self) -> List[Dict[str, object]]:
        """Get list of files with potential conflicts."""
        conflicts = []
        async with self._get_db_connection() as db:
            # Find files that were modified by different clients around the same time
            query = """
                SELECT file_path, COUNT(DISTINCT client_id) as client_count
                FROM sync_history
                WHERE operation IN ('create', 'update')
                AND timestamp > datetime('now', '-1 hour')
                GROUP BY file_path
                HAVING client_count > 1
            """

            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    file_path = row[0]
                    history = await self.get_sync_history(file_path, 10)
                    conflicts.append(
                        {"file_path": file_path, "recent_changes": history}
                    )

        return conflicts

    def get_full_path(self, relative_path: str) -> Path:
        """Get full filesystem path from relative path."""
        return self.sync_directory / relative_path

    async def cleanup_deleted_files(self) -> None:
        """Remove metadata for files that no longer exist."""
        async with self._get_db_connection() as db:
            async with db.execute("SELECT path FROM file_metadata") as cursor:
                rows = await cursor.fetchall()

                # Batch delete non-existent files
                paths_to_delete = []
                for row in rows:
                    file_path = self.get_full_path(row[0])
                    if not file_path.exists():
                        paths_to_delete.append(row[0])

                if paths_to_delete:
                    placeholders = ",".join(["?"] * len(paths_to_delete))
                    await db.execute(
                        f"DELETE FROM file_metadata WHERE path IN ({placeholders})",
                        paths_to_delete,
                    )
                    await db.commit()

    def _track_operation_time(self, operation: str, start_time: float) -> None:
        """Track operation performance."""
        duration = time.time() - start_time
        if operation in self._operation_times:
            self._operation_times[operation].append(duration)
            # Keep only last 100 measurements
            if len(self._operation_times[operation]) > 100:
                self._operation_times[operation] = self._operation_times[operation][
                    -100:
                ]

    async def invalidate_cache(self, file_path: str) -> None:
        """Invalidate cache entry for a specific file."""
        normalized_path = normalize_path(file_path)
        async with self._cache_lock:
            self._metadata_cache.pop(normalized_path, None)

    async def clear_cache(self) -> None:
        """Clear entire metadata cache."""
        async with self._cache_lock:
            self._metadata_cache.clear()

    def get_performance_stats(self) -> Dict[str, Dict[str, float]]:
        """Get performance statistics."""
        stats = {}
        for operation, times in self._operation_times.items():
            if times:
                stats[operation] = {
                    "avg_time": sum(times) / len(times),
                    "min_time": min(times),
                    "max_time": max(times),
                    "count": len(times),
                }
            else:
                stats[operation] = {
                    "avg_time": 0,
                    "min_time": 0,
                    "max_time": 0,
                    "count": 0,
                }
        return stats

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        current_time = time.time()
        expired_count = 0

        for _, (_, cache_time) in self._metadata_cache.items():
            if current_time - cache_time >= self._cache_ttl:
                expired_count += 1

        return {
            "total_entries": len(self._metadata_cache),
            "expired_entries": expired_count,
            "active_entries": len(self._metadata_cache) - expired_count,
        }

    async def close(self) -> None:
        """Close all database connections."""
        async with self._db_lock:
            for conn in self._db_connections:
                await conn.close()
            self._db_connections.clear()
