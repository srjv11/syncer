"""Unit tests for shared utilities."""

import hashlib
from datetime import datetime
from unittest.mock import patch

import pytest

from shared.utils import (
    _compile_pattern,
    _compiled_patterns_cache,
    batch_get_file_info,
    calculate_file_checksum,
    calculate_file_checksum_fast,
    calculate_file_checksum_sync,
    copy_file_async,
    ensure_directory,
    ensure_directory_async,
    get_file_info_async,
    get_file_info_sync,
    get_relative_path,
    normalize_path,
    should_ignore_file,
)


class TestChecksumCalculation:
    """Test checksum calculation functions."""

    @pytest.mark.asyncio
    async def test_calculate_file_checksum(self, temp_dir):
        """Test async checksum calculation."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        # Create test file
        with open(test_file, "w") as f:
            f.write(content)

        # Calculate checksum
        checksum = await calculate_file_checksum(str(test_file))

        # Verify checksum
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert checksum == expected

    @pytest.mark.asyncio
    async def test_calculate_file_checksum_nonexistent(self):
        """Test checksum calculation for non-existent file."""
        checksum = await calculate_file_checksum("/non/existent/file.txt")
        assert checksum == ""

    def test_calculate_file_checksum_sync(self, temp_dir):
        """Test synchronous checksum calculation."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        with open(test_file, "w") as f:
            f.write(content)

        checksum = calculate_file_checksum_sync(str(test_file))
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert checksum == expected

    @pytest.mark.asyncio
    async def test_calculate_file_checksum_fast_with_xxhash(self, temp_dir):
        """Test fast checksum with xxhash if available."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        with open(test_file, "w") as f:
            f.write(content)

        with patch("shared.utils.xxhash") as mock_xxhash:
            mock_hasher = mock_xxhash.xxh64.return_value
            mock_hasher.hexdigest.return_value = "fast_hash_result"

            checksum = await calculate_file_checksum_fast(str(test_file))
            assert checksum == "fast_hash_result"

    @pytest.mark.asyncio
    async def test_calculate_file_checksum_fast_fallback(self, temp_dir):
        """Test fast checksum fallback to SHA-256."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        with open(test_file, "w") as f:
            f.write(content)

        with patch("shared.utils.xxhash", side_effect=ImportError):
            checksum = await calculate_file_checksum_fast(str(test_file))
            expected = hashlib.sha256(content.encode()).hexdigest()
            assert checksum == expected


class TestFileInfo:
    """Test file information functions."""

    def test_get_file_info_sync(self, temp_dir):
        """Test synchronous file info retrieval."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        with open(test_file, "w") as f:
            f.write(content)

        file_info = get_file_info_sync(str(test_file))

        assert file_info is not None
        assert file_info["path"] == str(test_file)
        assert file_info["size"] == len(content)
        assert file_info["is_directory"] is False
        assert isinstance(file_info["modified_time"], datetime)
        assert len(file_info["checksum"]) == 64  # SHA-256 hex length

    def test_get_file_info_sync_directory(self, temp_dir):
        """Test file info for directory."""
        test_dir = temp_dir / "subdir"
        test_dir.mkdir()

        file_info = get_file_info_sync(str(test_dir))

        assert file_info is not None
        assert file_info["is_directory"] is True
        assert file_info["checksum"] == ""

    def test_get_file_info_sync_nonexistent(self):
        """Test file info for non-existent file."""
        file_info = get_file_info_sync("/non/existent/file.txt")
        assert file_info is None

    @pytest.mark.asyncio
    async def test_get_file_info_async(self, temp_dir):
        """Test async file info retrieval."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        with open(test_file, "w") as f:
            f.write(content)

        file_info = await get_file_info_async(str(test_file))

        assert file_info is not None
        assert file_info["path"] == str(test_file)
        assert file_info["size"] == len(content)
        assert file_info["is_directory"] is False

    @pytest.mark.asyncio
    async def test_get_file_info_async_fast_checksum(self, temp_dir):
        """Test async file info with fast checksum."""
        test_file = temp_dir / "test.txt"
        content = "Hello, World!"

        with open(test_file, "w") as f:
            f.write(content)

        with patch("shared.utils.calculate_file_checksum_fast") as mock_fast:
            mock_fast.return_value = "fast_checksum"

            file_info = await get_file_info_async(str(test_file), fast_checksum=True)

            assert file_info is not None
            assert file_info["checksum"] == "fast_checksum"
            mock_fast.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_get_file_info(self, temp_dir):
        """Test batch file info retrieval."""
        files = []
        for i in range(3):
            test_file = temp_dir / f"test_{i}.txt"
            with open(test_file, "w") as f:
                f.write(f"Content {i}")
            files.append(str(test_file))

        results = await batch_get_file_info(files, max_workers=2)

        assert len(results) == 3
        for result in results:
            assert result is not None
            assert "path" in result
            assert "size" in result


class TestIgnorePatterns:
    """Test file ignore pattern functionality."""

    def test_should_ignore_file_simple(self):
        """Test simple ignore patterns."""
        patterns = ["*.tmp", ".git", "__pycache__"]

        assert should_ignore_file("test.tmp", patterns) is True
        assert should_ignore_file(".git", patterns) is True
        assert should_ignore_file("__pycache__", patterns) is True
        assert should_ignore_file("test.txt", patterns) is False

    def test_should_ignore_file_path(self):
        """Test ignore patterns with paths."""
        patterns = ["*.log", "build/*", ".git/*"]

        assert should_ignore_file("app.log", patterns) is True
        assert should_ignore_file("build/output.txt", patterns) is True
        assert should_ignore_file(".git/config", patterns) is True
        assert should_ignore_file("src/main.py", patterns) is False

    def test_compile_pattern_caching(self):
        """Test pattern compilation caching."""
        # Clear cache
        _compiled_patterns_cache.clear()

        pattern = "*.txt"
        compiled1 = _compile_pattern(pattern)
        compiled2 = _compile_pattern(pattern)

        # Should be the same object (cached)
        assert compiled1 is compiled2
        assert pattern in _compiled_patterns_cache

    def test_should_ignore_file_performance(self):
        """Test ignore performance with compiled patterns."""
        patterns = ["*.tmp", "*.log", "*.cache", ".git", "__pycache__"]
        test_files = [
            "app.py",
            "test.tmp",
            "debug.log",
            "cache.cache",
            ".git",
            "__pycache__",
            "main.cpp",
            "data.json",
        ]

        # Run multiple times to test caching
        for _ in range(100):
            for file_path in test_files:
                should_ignore_file(file_path, patterns)

        # Should not raise any errors and patterns should be cached
        assert len(_compiled_patterns_cache) >= len(patterns)


class TestPathUtilities:
    """Test path utility functions."""

    def test_normalize_path_unix(self):
        """Test path normalization for Unix-style paths."""
        assert normalize_path("path/to/file.txt") == "path/to/file.txt"
        assert normalize_path("path\\to\\file.txt") == "path/to/file.txt"
        assert normalize_path("./path/to/file.txt") == "path/to/file.txt"

    def test_normalize_path_windows(self):
        """Test path normalization for Windows-style paths."""
        with patch("shared.utils.Path") as mock_path:
            mock_instance = mock_path.return_value
            mock_instance.as_posix.return_value = "normalized/path"

            result = normalize_path("C:\\Windows\\Path")
            assert result == "normalized/path"

    def test_get_relative_path(self):
        """Test relative path calculation."""
        base = "/home/user/project"
        file_path = "/home/user/project/src/main.py"

        result = get_relative_path(file_path, base)
        assert result == "src/main.py"

    def test_get_relative_path_outside_base(self):
        """Test relative path for file outside base."""
        base = "/home/user/project"
        file_path = "/home/other/file.txt"

        result = get_relative_path(file_path, base)
        assert result == file_path  # Should return original path


class TestDirectoryOperations:
    """Test directory operation utilities."""

    def test_ensure_directory(self, temp_dir):
        """Test directory creation."""
        new_dir = temp_dir / "new" / "nested" / "directory"

        ensure_directory(str(new_dir))

        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_ensure_directory_existing(self, temp_dir):
        """Test ensuring existing directory."""
        existing_dir = temp_dir / "existing"
        existing_dir.mkdir()

        # Should not raise error
        ensure_directory(str(existing_dir))
        assert existing_dir.exists()

    @pytest.mark.asyncio
    async def test_ensure_directory_async(self, temp_dir):
        """Test async directory creation."""
        new_dir = temp_dir / "async" / "nested" / "directory"

        await ensure_directory_async(str(new_dir))

        assert new_dir.exists()
        assert new_dir.is_dir()


class TestFileCopy:
    """Test file copy operations."""

    @pytest.mark.asyncio
    async def test_copy_file_async(self, temp_dir):
        """Test async file copying."""
        src_file = temp_dir / "source.txt"
        dst_file = temp_dir / "dest" / "destination.txt"
        content = "Hello, World!"

        # Create source file
        with open(src_file, "w") as f:
            f.write(content)

        # Copy file
        await copy_file_async(str(src_file), str(dst_file))

        # Verify copy
        assert dst_file.exists()
        with open(dst_file) as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_copy_file_async_binary(self, temp_dir):
        """Test async binary file copying."""
        src_file = temp_dir / "source.bin"
        dst_file = temp_dir / "destination.bin"
        content = b"\\x00\\x01\\x02\\x03" * 100

        # Create source file
        with open(src_file, "wb") as f:
            f.write(content)

        # Copy file
        await copy_file_async(str(src_file), str(dst_file))

        # Verify copy
        assert dst_file.exists()
        with open(dst_file, "rb") as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_copy_file_async_large_file(self, temp_dir):
        """Test async copying of large file."""
        src_file = temp_dir / "large_source.txt"
        dst_file = temp_dir / "large_destination.txt"
        content = "x" * (1024 * 1024)  # 1MB

        # Create large source file
        with open(src_file, "w") as f:
            f.write(content)

        # Copy file with custom chunk size
        await copy_file_async(str(src_file), str(dst_file), chunk_size=8192)

        # Verify copy
        assert dst_file.exists()
        assert dst_file.stat().st_size == src_file.stat().st_size


class TestErrorHandling:
    """Test error handling in utilities."""

    @pytest.mark.asyncio
    async def test_calculate_checksum_permission_error(self):
        """Test checksum calculation with permission error."""
        with patch("aiofiles.open", side_effect=PermissionError):
            checksum = await calculate_file_checksum("/protected/file.txt")
            assert checksum == ""

    @pytest.mark.asyncio
    async def test_get_file_info_os_error(self):
        """Test file info with OS error."""
        with patch("pathlib.Path.stat", side_effect=OSError):
            file_info = await get_file_info_async("/some/file.txt")
            assert file_info is None

    @pytest.mark.asyncio
    async def test_copy_file_async_error(self, temp_dir):
        """Test file copy with error."""
        src_file = temp_dir / "nonexistent.txt"
        dst_file = temp_dir / "destination.txt"

        with pytest.raises(FileNotFoundError):
            await copy_file_async(str(src_file), str(dst_file))


class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_batch_processing_performance(self, temp_dir):
        """Test batch processing performance."""
        # Create many files
        files = []
        for i in range(50):
            test_file = temp_dir / f"perf_test_{i}.txt"
            with open(test_file, "w") as f:
                f.write(f"Content {i}")
            files.append(str(test_file))

        # Test batch processing
        import time

        start_time = time.time()

        results = await batch_get_file_info(files, max_workers=4)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should process all files
        assert len(results) == 50
        assert all(result is not None for result in results)

        # Should be reasonably fast (adjust threshold as needed)
        assert processing_time < 5.0  # 5 seconds for 50 files

    def test_ignore_pattern_performance(self):
        """Test ignore pattern performance with many patterns."""
        patterns = [f"*.{ext}" for ext in ["tmp", "log", "cache", "bak", "old"]]
        patterns.extend([f"build{i}/*" for i in range(10)])

        test_files = [f"file_{i}.py" for i in range(100)]
        test_files.extend([f"temp_{i}.tmp" for i in range(20)])

        import time

        start_time = time.time()

        for _ in range(10):  # Multiple iterations
            for file_path in test_files:
                should_ignore_file(file_path, patterns)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should be fast due to pattern caching
        assert processing_time < 1.0  # 1 second for all iterations
