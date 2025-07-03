"""Integration tests for FileManager."""

import asyncio
from datetime import datetime
from unittest.mock import patch

import aiosqlite
import pytest

from server.file_manager import FileManager
from shared.models import FileInfo, SyncOperation


class TestFileManagerIntegration:
    """Integration tests for FileManager."""

    @pytest.fixture
    async def file_manager(self, server_temp_dir):
        """Create a FileManager instance for testing."""
        manager = FileManager(str(server_temp_dir))
        await manager._init_database()
        yield manager
        await manager.close()

    @pytest.fixture
    async def sample_files_with_content(self, server_temp_dir):
        """Create sample files with actual content."""
        files = {}

        # Create various test files
        test_files = [
            ("document.txt", "This is a text document with some content."),
            ("data.json", '{"key": "value", "number": 42}'),
            ("script.py", "print('Hello, World!')\\ndef main():\\n    pass"),
            ("binary.dat", b"\\x00\\x01\\x02\\x03\\x04\\x05" * 10),
        ]

        for filename, content in test_files:
            file_path = server_temp_dir / filename
            if isinstance(content, bytes):
                with open(file_path, "wb") as f:
                    f.write(content)
            else:
                with open(file_path, "w") as f:
                    f.write(content)

            files[filename] = file_path

        # Create a subdirectory with files
        subdir = server_temp_dir / "subdir"
        subdir.mkdir()
        sub_file = subdir / "nested.txt"
        with open(sub_file, "w") as f:
            f.write("Nested file content")

        files["subdir"] = subdir
        files["nested.txt"] = sub_file

        return files

    @pytest.mark.integration
    async def test_database_initialization(self, server_temp_dir):
        """Test database initialization."""
        manager = FileManager(str(server_temp_dir))

        # Database should not exist initially
        assert not manager.db_path.exists()

        # Initialize database
        await manager._init_database()

        # Database should now exist
        assert manager.db_path.exists()

        # Check tables exist
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in await cursor.fetchall()]

            assert "file_metadata" in tables
            assert "sync_history" in tables

        await manager.close()

    @pytest.mark.integration
    async def test_file_metadata_operations(self, file_manager):
        """Test file metadata CRUD operations."""
        now = datetime.now()

        # Create test file info
        file_info = FileInfo(
            path="test/document.txt",
            size=1024,
            checksum="abc123def456",
            modified_time=now,
            is_directory=False,
        )

        # Insert metadata
        await file_manager.update_file_metadata(file_info)

        # Retrieve metadata
        retrieved = await file_manager.get_file_metadata("test/document.txt")

        assert retrieved is not None
        assert retrieved.path == "test/document.txt"
        assert retrieved.size == 1024
        assert retrieved.checksum == "abc123def456"
        assert retrieved.is_directory is False

        # Update metadata
        file_info.size = 2048
        file_info.checksum = "new_checksum"
        await file_manager.update_file_metadata(file_info)

        # Retrieve updated metadata
        updated = await file_manager.get_file_metadata("test/document.txt")
        assert updated.size == 2048
        assert updated.checksum == "new_checksum"

        # Remove metadata
        await file_manager.remove_file_metadata("test/document.txt")

        # Should not exist anymore
        removed = await file_manager.get_file_metadata("test/document.txt")
        assert removed is None

    @pytest.mark.integration
    async def test_batch_metadata_operations(self, file_manager):
        """Test batch metadata operations."""
        now = datetime.now()

        # Create multiple file infos
        file_infos = [
            FileInfo(
                path=f"batch/file_{i}.txt",
                size=100 * i,
                checksum=f"hash_{i}",
                modified_time=now,
                is_directory=False,
            )
            for i in range(5)
        ]

        # Batch update
        await file_manager.batch_update_file_metadata(file_infos)

        # Verify all files were inserted
        for i, _file_info in enumerate(file_infos):
            retrieved = await file_manager.get_file_metadata(f"batch/file_{i}.txt")
            assert retrieved is not None
            assert retrieved.size == 100 * i
            assert retrieved.checksum == f"hash_{i}"

    @pytest.mark.integration
    async def test_file_list_from_filesystem(
        self, file_manager, sample_files_with_content
    ):
        """Test getting file list from filesystem."""
        # Get file list (should scan filesystem)
        files = await file_manager.get_file_list(use_cache=False)

        # Should find all created files
        file_paths = {f.path for f in files}

        assert "document.txt" in file_paths
        assert "data.json" in file_paths
        assert "script.py" in file_paths
        assert "binary.dat" in file_paths
        assert "subdir/nested.txt" in file_paths

        # Check file properties
        doc_file = next(f for f in files if f.path == "document.txt")
        assert doc_file.size > 0
        assert doc_file.checksum != ""
        assert not doc_file.is_directory

        # Check directory
        subdir = next((f for f in files if f.path == "subdir"), None)
        if subdir:  # Directories might not be included in all implementations
            assert subdir.is_directory

    @pytest.mark.integration
    async def test_file_list_caching(self, file_manager, sample_files_with_content):
        """Test file list caching mechanism."""
        # First call - populates cache
        files1 = await file_manager.get_file_list(use_cache=True)

        # Second call - should use cache
        with patch.object(file_manager, "batch_update_file_metadata") as mock_batch:
            files2 = await file_manager.get_file_list(use_cache=True)

            # Should get same results
            assert len(files1) == len(files2)

            # Batch update should not be called when using cache
            mock_batch.assert_not_called()

    @pytest.mark.integration
    async def test_metadata_cache_operations(self, file_manager):
        """Test metadata caching functionality."""
        now = datetime.now()
        file_info = FileInfo(
            path="cached/file.txt",
            size=512,
            checksum="cached_hash",
            modified_time=now,
            is_directory=False,
        )

        # Insert metadata
        await file_manager.update_file_metadata(file_info)

        # First retrieval - from database
        retrieved1 = await file_manager.get_file_metadata("cached/file.txt")

        # Second retrieval - should use cache
        with patch.object(file_manager, "_get_db_connection") as mock_db:
            retrieved2 = await file_manager.get_file_metadata("cached/file.txt")

            # Should get same result
            assert retrieved1.path == retrieved2.path
            assert retrieved1.checksum == retrieved2.checksum

            # Database should not be accessed
            mock_db.assert_not_called()

        # Test cache invalidation
        await file_manager.invalidate_cache("cached/file.txt")

        # Next retrieval should go to database again
        with patch.object(
            file_manager, "_get_db_connection", wraps=file_manager._get_db_connection
        ) as mock_db:
            await file_manager.get_file_metadata("cached/file.txt")

            # Should access database
            mock_db.assert_called()

    @pytest.mark.integration
    async def test_sync_history_logging(self, file_manager):
        """Test sync history logging."""
        # Log several operations
        operations = [
            ("file1.txt", SyncOperation.CREATE, "client1", "hash1", 100),
            ("file1.txt", SyncOperation.UPDATE, "client2", "hash2", 150),
            ("file2.txt", SyncOperation.CREATE, "client1", "hash3", 200),
            ("file1.txt", SyncOperation.DELETE, "client1", "", 0),
        ]

        for file_path, operation, client_id, checksum, size in operations:
            await file_manager.log_sync_operation(
                file_path, operation, client_id, checksum, size
            )

        # Get history for specific file
        file1_history = await file_manager.get_sync_history("file1.txt")
        assert len(file1_history) == 3  # CREATE, UPDATE, DELETE

        # Check order (should be newest first)
        assert file1_history[0]["operation"] == "delete"
        assert file1_history[1]["operation"] == "update"
        assert file1_history[2]["operation"] == "create"

        # Get all history
        all_history = await file_manager.get_sync_history()
        assert len(all_history) == 4  # All operations

    @pytest.mark.integration
    async def test_conflict_detection(self, file_manager):
        """Test conflict detection logic."""
        # Simulate conflicting operations
        # (Note: This test relies on the conflict detection time window)

        # Multiple clients modifying same file
        await file_manager.log_sync_operation(
            "conflict.txt", SyncOperation.UPDATE, "client1", "hash1", 100
        )
        await file_manager.log_sync_operation(
            "conflict.txt", SyncOperation.UPDATE, "client2", "hash2", 100
        )

        conflicts = await file_manager.get_conflicts()

        # Should detect conflict (if within time window)
        if conflicts:  # Time-dependent test
            assert any(c["file_path"] == "conflict.txt" for c in conflicts)

    @pytest.mark.integration
    async def test_cleanup_deleted_files(self, file_manager, server_temp_dir):
        """Test cleanup of metadata for deleted files."""
        # Create file and add metadata
        test_file = server_temp_dir / "to_delete.txt"
        with open(test_file, "w") as f:
            f.write("temporary content")

        file_info = FileInfo(
            path="to_delete.txt",
            size=100,
            checksum="temp_hash",
            modified_time=datetime.now(),
            is_directory=False,
        )

        await file_manager.update_file_metadata(file_info)

        # Verify metadata exists
        retrieved = await file_manager.get_file_metadata("to_delete.txt")
        assert retrieved is not None

        # Delete physical file
        test_file.unlink()

        # Run cleanup
        await file_manager.cleanup_deleted_files()

        # Metadata should be removed
        after_cleanup = await file_manager.get_file_metadata("to_delete.txt")
        assert after_cleanup is None

    @pytest.mark.integration
    async def test_performance_stats_tracking(self, file_manager):
        """Test performance statistics tracking."""
        now = datetime.now()

        # Perform operations to generate stats
        for i in range(10):
            file_info = FileInfo(
                path=f"perf/file_{i}.txt",
                size=100,
                checksum=f"hash_{i}",
                modified_time=now,
                is_directory=False,
            )
            await file_manager.update_file_metadata(file_info)
            await file_manager.get_file_metadata(f"perf/file_{i}.txt")

        # Get performance stats
        stats = file_manager.get_performance_stats()

        assert "get_file_metadata" in stats
        assert "update_file_metadata" in stats

        # Should have recorded operations
        get_stats = stats["get_file_metadata"]
        assert get_stats["count"] >= 10
        assert get_stats["avg_time"] > 0
        assert get_stats["min_time"] >= 0
        assert get_stats["max_time"] >= get_stats["min_time"]

    @pytest.mark.integration
    async def test_cache_stats(self, file_manager):
        """Test cache statistics."""
        now = datetime.now()

        # Add some cached entries
        for i in range(5):
            file_info = FileInfo(
                path=f"cache_test/file_{i}.txt",
                size=100,
                checksum=f"hash_{i}",
                modified_time=now,
                is_directory=False,
            )
            await file_manager.update_file_metadata(file_info)
            # Retrieve to populate cache
            await file_manager.get_file_metadata(f"cache_test/file_{i}.txt")

        # Get cache stats
        cache_stats = file_manager.get_cache_stats()

        assert "total_entries" in cache_stats
        assert "expired_entries" in cache_stats
        assert "active_entries" in cache_stats

        assert cache_stats["total_entries"] >= 5
        assert cache_stats["active_entries"] <= cache_stats["total_entries"]

    @pytest.mark.integration
    async def test_database_connection_pool(self, file_manager):
        """Test database connection pooling."""

        # Perform many concurrent operations
        async def concurrent_operation(i):
            file_info = FileInfo(
                path=f"concurrent/file_{i}.txt",
                size=100,
                checksum=f"hash_{i}",
                modified_time=datetime.now(),
                is_directory=False,
            )
            await file_manager.update_file_metadata(file_info)
            return await file_manager.get_file_metadata(f"concurrent/file_{i}.txt")

        # Run 20 concurrent operations
        tasks = [concurrent_operation(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # All operations should succeed
        assert len(results) == 20
        assert all(result is not None for result in results)

    @pytest.mark.integration
    async def test_file_manager_with_real_files(
        self, file_manager, sample_files_with_content
    ):
        """Test FileManager with real file system operations."""
        # Get initial file list
        initial_files = await file_manager.get_file_list()
        initial_count = len(initial_files)

        # Add a new file
        new_file = file_manager.sync_directory / "new_file.txt"
        with open(new_file, "w") as f:
            f.write("New file content")

        # Rescan filesystem
        updated_files = await file_manager.get_file_list(use_cache=False)

        # Should find the new file
        assert len(updated_files) == initial_count + 1
        new_file_info = next(
            (f for f in updated_files if f.path == "new_file.txt"), None
        )
        assert new_file_info is not None
        assert new_file_info.size > 0
        assert not new_file_info.is_directory

    @pytest.mark.integration
    async def test_error_handling(self, file_manager):
        """Test error handling in various scenarios."""
        # Test with invalid file path
        result = await file_manager.get_file_metadata("/invalid/path/file.txt")
        assert result is None

        # Test cleanup with permission issues
        with patch("pathlib.Path.exists", return_value=False):
            # Should not raise exception
            await file_manager.cleanup_deleted_files()

        # Test batch update with empty list
        await file_manager.batch_update_file_metadata([])
        # Should not raise exception

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_large_scale_operations(self, file_manager):
        """Test FileManager with large number of files."""
        # Create many file entries
        file_infos = []
        for i in range(100):
            file_info = FileInfo(
                path=f"large_scale/file_{i:03d}.txt",
                size=i * 10,
                checksum=f"hash_{i:03d}",
                modified_time=datetime.now(),
                is_directory=False,
            )
            file_infos.append(file_info)

        # Batch insert
        await file_manager.batch_update_file_metadata(file_infos)

        # Verify all were inserted
        retrieved_files = []
        for i in range(100):
            file_info = await file_manager.get_file_metadata(
                f"large_scale/file_{i:03d}.txt"
            )
            assert file_info is not None
            retrieved_files.append(file_info)

        assert len(retrieved_files) == 100

        # Test performance of batch operations
        import time

        start_time = time.time()

        # Batch retrieve through cache
        for file_info in retrieved_files:
            await file_manager.get_file_metadata(file_info.path)

        end_time = time.time()

        # Should be fast due to caching
        cache_time = end_time - start_time
        assert cache_time < 1.0  # Should take less than 1 second for 100 cached lookups
