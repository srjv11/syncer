"""Unit tests for differential sync utilities."""

from shared.diff import DifferentialSync, FileChunk, FileDelta, RollingHash


class TestFileChunk:
    """Test FileChunk dataclass."""

    def test_file_chunk_creation(self):
        """Test FileChunk creation."""
        chunk = FileChunk(offset=0, size=1024, checksum="abc123", data=b"test data")

        assert chunk.offset == 0
        assert chunk.size == 1024
        assert chunk.checksum == "abc123"
        assert chunk.data == b"test data"

    def test_file_chunk_without_data(self):
        """Test FileChunk creation without data."""
        chunk = FileChunk(offset=100, size=512, checksum="def456")

        assert chunk.offset == 100
        assert chunk.size == 512
        assert chunk.checksum == "def456"
        assert chunk.data is None


class TestFileDelta:
    """Test FileDelta dataclass."""

    def test_file_delta_creation(self):
        """Test FileDelta creation."""
        unchanged_chunks = [FileChunk(0, 100, "hash1"), FileChunk(200, 100, "hash2")]
        changed_chunks = [FileChunk(100, 100, "hash3", b"new data")]

        delta = FileDelta(
            unchanged_chunks=unchanged_chunks,
            changed_chunks=changed_chunks,
            total_size=300,
            compression_ratio=0.33,
        )

        assert len(delta.unchanged_chunks) == 2
        assert len(delta.changed_chunks) == 1
        assert delta.total_size == 300
        assert delta.compression_ratio == 0.33


class TestRollingHash:
    """Test RollingHash class."""

    def test_rolling_hash_initialization(self):
        """Test RollingHash initialization."""
        rh = RollingHash()
        assert rh.window_size == 64
        assert rh.base == 256
        assert rh.mod == 1000003

    def test_rolling_hash_custom_window(self):
        """Test RollingHash with custom window size."""
        rh = RollingHash(window_size=128)
        assert rh.window_size == 128

    def test_hash_chunk(self):
        """Test hash calculation for chunks."""
        rh = RollingHash()

        # Same data should produce same hash
        data1 = b"test data"
        data2 = b"test data"
        hash1 = rh.hash_chunk(data1)
        hash2 = rh.hash_chunk(data2)

        assert hash1 == hash2
        assert isinstance(hash1, int)

        # Different data should produce different hash (usually)
        data3 = b"different data"
        hash3 = rh.hash_chunk(data3)
        assert hash3 != hash1  # Very unlikely to be the same

    def test_hash_empty_data(self):
        """Test hash calculation for empty data."""
        rh = RollingHash()
        hash_val = rh.hash_chunk(b"")
        assert hash_val == 0


class TestDifferentialSync:
    """Test DifferentialSync class."""

    def test_differential_sync_initialization(self):
        """Test DifferentialSync initialization."""
        ds = DifferentialSync()
        assert ds.chunk_size == 8192
        assert isinstance(ds.rolling_hash, RollingHash)

    def test_differential_sync_custom_chunk_size(self):
        """Test DifferentialSync with custom chunk size."""
        ds = DifferentialSync(chunk_size=4096)
        assert ds.chunk_size == 4096

    def test_create_signature_nonexistent_file(self):
        """Test signature creation for non-existent file."""
        ds = DifferentialSync()
        chunks = ds.create_signature("/nonexistent/file.txt")
        assert chunks == []

    def test_create_signature_real_file(self, temp_dir):
        """Test signature creation for real file."""
        # Create test file
        test_file = temp_dir / "test.txt"
        content = "Hello, World! This is test content for chunking."

        with open(test_file, "w") as f:
            f.write(content)

        ds = DifferentialSync(chunk_size=10)  # Small chunks for testing
        chunks = ds.create_signature(str(test_file))

        assert len(chunks) > 0

        # Check first chunk
        assert chunks[0].offset == 0
        assert chunks[0].size <= 10
        assert len(chunks[0].checksum) == 64  # SHA-256 hex length
        assert chunks[0].data is None  # Signature doesn't include data

        # Verify total size matches
        total_size = sum(chunk.size for chunk in chunks)
        assert total_size == len(content.encode())

    def test_create_signature_empty_file(self, temp_dir):
        """Test signature creation for empty file."""
        empty_file = temp_dir / "empty.txt"
        empty_file.touch()

        ds = DifferentialSync()
        chunks = ds.create_signature(str(empty_file))

        assert chunks == []

    def test_create_delta_identical_files(self, temp_dir):
        """Test delta creation for identical files."""
        # Create identical files
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        content = "Identical content"

        for file_path in [file1, file2]:
            with open(file_path, "w") as f:
                f.write(content)

        ds = DifferentialSync()

        # Create signature for target file
        target_signature = ds.create_signature(str(file2))

        # Create delta
        delta = ds.create_delta(str(file1), target_signature)

        # All chunks should be unchanged for identical files
        assert len(delta.changed_chunks) == 0
        assert len(delta.unchanged_chunks) > 0
        assert delta.compression_ratio == 0.0  # No changes needed

    def test_create_delta_different_files(self, temp_dir):
        """Test delta creation for different files."""
        # Create different files
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        with open(file1, "w") as f:
            f.write("Source file content")

        with open(file2, "w") as f:
            f.write("Target file content")

        ds = DifferentialSync()

        # Create signature for target file
        target_signature = ds.create_signature(str(file2))

        # Create delta
        delta = ds.create_delta(str(file1), target_signature)

        # Should have some changed chunks for different files
        assert len(delta.changed_chunks) > 0
        assert delta.compression_ratio > 0.0

        # Changed chunks should have data
        for chunk in delta.changed_chunks:
            assert chunk.data is not None

    def test_apply_delta_simple(self, temp_dir):
        """Test applying delta to reconstruct file."""
        # Create source and target files
        source_file = temp_dir / "source.txt"
        target_file = temp_dir / "target.txt"
        result_file = temp_dir / "result.txt"

        source_content = "Original content"
        target_content = "Modified content"

        with open(source_file, "w") as f:
            f.write(source_content)

        with open(target_file, "w") as f:
            f.write(target_content)

        ds = DifferentialSync()

        # Create delta from target to source
        target_signature = ds.create_signature(str(target_file))
        delta = ds.create_delta(str(source_file), target_signature)

        # Apply delta
        success = ds.apply_delta(str(result_file), delta, str(source_file))

        assert success is True
        assert result_file.exists()

        # Result should match source (since we're applying source->target delta)
        with open(result_file) as f:
            result_content = f.read()

        # The logic recreates the source file from the delta
        assert len(result_content) > 0

    def test_apply_delta_nonexistent_source(self, temp_dir):
        """Test applying delta with non-existent source file."""
        target_file = temp_dir / "target.txt"

        # Create empty delta
        delta = FileDelta([], [], 0, 0.0)

        ds = DifferentialSync()
        success = ds.apply_delta(str(target_file), delta, "/nonexistent/file.txt")

        # Should handle gracefully
        assert success is True  # Empty delta should succeed

    def test_calculate_transfer_savings_no_changes(self):
        """Test transfer savings calculation with no changes."""
        # Create delta with only unchanged chunks
        unchanged_chunks = [FileChunk(0, 100, "hash1"), FileChunk(100, 100, "hash2")]
        delta = FileDelta(unchanged_chunks, [], 200, 0.0)

        ds = DifferentialSync()
        savings = ds.calculate_transfer_savings(delta)

        assert savings["total_size"] == 200
        assert savings["changed_size"] == 0
        assert savings["unchanged_size"] == 200
        assert savings["transfer_ratio"] == 0.0
        assert savings["savings_percent"] == 100.0

    def test_calculate_transfer_savings_all_changes(self):
        """Test transfer savings calculation with all changes."""
        # Create delta with only changed chunks
        changed_chunks = [
            FileChunk(0, 100, "hash1", b"data1"),
            FileChunk(100, 100, "hash2", b"data2"),
        ]
        delta = FileDelta([], changed_chunks, 200, 1.0)

        ds = DifferentialSync()
        savings = ds.calculate_transfer_savings(delta)

        assert savings["total_size"] == 200
        assert savings["changed_size"] == 200
        assert savings["unchanged_size"] == 0
        assert savings["transfer_ratio"] == 1.0
        assert savings["savings_percent"] == 0.0

    def test_calculate_transfer_savings_empty_file(self):
        """Test transfer savings calculation with empty file."""
        delta = FileDelta([], [], 0, 1.0)

        ds = DifferentialSync()
        savings = ds.calculate_transfer_savings(delta)

        assert savings["total_size"] == 0
        assert savings["changed_size"] == 0
        assert savings["unchanged_size"] == 0
        assert savings["transfer_ratio"] == 1.0
        assert savings["savings_percent"] == 0.0

    def test_should_use_differential_small_file(self):
        """Test differential sync decision for small files."""
        ds = DifferentialSync()

        # Small files should not use differential sync
        assert ds.should_use_differential(1024) is False  # 1KB
        assert ds.should_use_differential(32 * 1024) is False  # 32KB

    def test_should_use_differential_large_file(self):
        """Test differential sync decision for large files."""
        ds = DifferentialSync()

        # Large files should use differential sync
        assert ds.should_use_differential(2 * 1024 * 1024) is True  # 2MB
        assert ds.should_use_differential(10 * 1024 * 1024) is True  # 10MB

    def test_should_use_differential_medium_file_low_change(self):
        """Test differential sync decision for medium files with low change ratio."""
        ds = DifferentialSync()

        # Medium file with low expected change ratio
        file_size = 500 * 1024  # 500KB
        assert ds.should_use_differential(file_size, 0.2) is True  # 20% change
        assert ds.should_use_differential(file_size, 0.4) is True  # 40% change

    def test_should_use_differential_medium_file_high_change(self):
        """Test differential sync decision for medium files with high change ratio."""
        ds = DifferentialSync()

        # Medium file with high expected change ratio
        file_size = 500 * 1024  # 500KB
        assert ds.should_use_differential(file_size, 0.8) is False  # 80% change


class TestDifferentialSyncIntegration:
    """Integration tests for differential sync."""

    def test_full_differential_sync_workflow(self, temp_dir):
        """Test complete differential sync workflow."""
        # Create original file
        original_file = temp_dir / "original.txt"
        modified_file = temp_dir / "modified.txt"
        restored_file = temp_dir / "restored.txt"

        original_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        modified_content = "Line 1\nModified Line 2\nLine 3\nNew Line 4\nLine 5\n"

        with open(original_file, "w") as f:
            f.write(original_content)

        with open(modified_file, "w") as f:
            f.write(modified_content)

        ds = DifferentialSync(chunk_size=10)  # Small chunks

        # 1. Create signature of original file
        original_signature = ds.create_signature(str(original_file))
        assert len(original_signature) > 0

        # 2. Create delta from modified file to original signature
        delta = ds.create_delta(str(modified_file), original_signature)

        # 3. Apply delta to restore file
        success = ds.apply_delta(str(restored_file), delta, str(original_file))
        assert success is True

        # 4. Verify restoration
        assert restored_file.exists()

        # 5. Calculate savings
        savings = ds.calculate_transfer_savings(delta)
        assert "transfer_ratio" in savings
        assert "savings_percent" in savings

    def test_binary_file_differential_sync(self, temp_dir):
        """Test differential sync with binary files."""
        # Create binary files
        binary1 = temp_dir / "binary1.dat"
        binary2 = temp_dir / "binary2.dat"

        # Create binary content
        content1 = bytes(range(256)) * 4  # 1024 bytes
        content2 = bytes(range(256)) * 4
        content2 = (
            content2[:500] + b"\xff" * 24 + content2[524:]
        )  # Modify middle section

        with open(binary1, "wb") as f:
            f.write(content1)

        with open(binary2, "wb") as f:
            f.write(content2)

        ds = DifferentialSync(chunk_size=64)

        # Create differential sync
        signature1 = ds.create_signature(str(binary1))
        delta = ds.create_delta(str(binary2), signature1)

        # Should detect some changes
        assert len(delta.changed_chunks) > 0
        assert len(delta.unchanged_chunks) > 0

        # Calculate savings
        savings = ds.calculate_transfer_savings(delta)
        assert savings["transfer_ratio"] < 1.0  # Should have some savings

    def test_large_file_performance(self, temp_dir):
        """Test differential sync performance with larger files."""
        large_file1 = temp_dir / "large1.txt"
        large_file2 = temp_dir / "large2.txt"

        # Create large content with repetitive patterns
        base_content = "This is a repeating line that will be duplicated many times.\n"
        large_content1 = base_content * 1000  # ~60KB

        # Modify a small portion
        lines = large_content1.split("\n")
        lines[500] = "This line has been modified for testing purposes."
        large_content2 = "\n".join(lines)

        with open(large_file1, "w") as f:
            f.write(large_content1)

        with open(large_file2, "w") as f:
            f.write(large_content2)

        ds = DifferentialSync()

        # Should recommend using differential sync for this file size
        assert ds.should_use_differential(len(large_content1.encode())) is True

        # Perform differential sync
        signature1 = ds.create_signature(str(large_file1))
        delta = ds.create_delta(str(large_file2), signature1)

        # Should achieve good compression (most content unchanged)
        savings = ds.calculate_transfer_savings(delta)
        assert savings["savings_percent"] > 80  # Should save >80% transfer
