"""Differential sync utilities for efficient file transfers."""

import contextlib
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FileChunk:
    """Represents a chunk of a file with its metadata."""

    offset: int
    size: int
    checksum: str
    data: Optional[bytes] = None


@dataclass
class FileDelta:
    """Represents the difference between two file versions."""

    unchanged_chunks: List[FileChunk]
    changed_chunks: List[FileChunk]
    total_size: int
    compression_ratio: float = 1.0


class RollingHash:
    """Simple rolling hash implementation for chunking."""

    def __init__(self, window_size: int = 64):
        self.window_size = window_size
        self.base = 256
        self.mod = 1000003  # Large prime

    def hash_chunk(self, data: bytes) -> int:
        """Calculate hash for a chunk of data."""
        hash_val = 0
        for byte in data:
            hash_val = (hash_val * self.base + byte) % self.mod
        return hash_val


class DifferentialSync:
    """Implements differential synchronization for efficient file transfers."""

    def __init__(self, chunk_size: int = 8192):
        self.chunk_size = chunk_size
        self.rolling_hash = RollingHash()

    def create_signature(self, file_path: str) -> List[FileChunk]:
        """Create a signature (list of chunk checksums) for a file."""
        chunks = []

        try:
            file_obj = Path(file_path)
            with file_obj.open("rb") as f:
                offset = 0
                while True:
                    chunk_data = f.read(self.chunk_size)
                    if not chunk_data:
                        break

                    checksum = hashlib.sha256(chunk_data).hexdigest()
                    chunks.append(
                        FileChunk(
                            offset=offset, size=len(chunk_data), checksum=checksum
                        )
                    )
                    offset += len(chunk_data)

        except OSError:
            return []

        return chunks

    def create_delta(
        self, source_file: str, target_signature: List[FileChunk]
    ) -> FileDelta:
        """Create a delta between source file and target signature."""
        source_chunks = self.create_signature(source_file)
        target_checksums = {chunk.checksum: chunk for chunk in target_signature}

        unchanged_chunks = []
        changed_chunks = []

        for source_chunk in source_chunks:
            if source_chunk.checksum in target_checksums:
                unchanged_chunks.append(source_chunk)
            else:
                # Load actual data for changed chunks
                try:
                    source_obj = Path(source_file)
                    with source_obj.open("rb") as f:
                        f.seek(source_chunk.offset)
                        chunk_data = f.read(source_chunk.size)
                        source_chunk.data = chunk_data
                        changed_chunks.append(source_chunk)
                except OSError:
                    # If we can't read the chunk, treat it as unchanged
                    unchanged_chunks.append(source_chunk)

        total_size = sum(chunk.size for chunk in source_chunks)
        changed_size = sum(chunk.size for chunk in changed_chunks)
        compression_ratio = changed_size / total_size if total_size > 0 else 1.0

        return FileDelta(
            unchanged_chunks=unchanged_chunks,
            changed_chunks=changed_chunks,
            total_size=total_size,
            compression_ratio=compression_ratio,
        )

    def apply_delta(self, target_file: str, delta: FileDelta, source_file: str) -> bool:
        """Apply a delta to reconstruct the target file."""
        try:
            # Create a temporary file for the result
            temp_file = target_file + ".tmp"

            temp_obj = Path(temp_file)
            with temp_obj.open("wb") as output_file:
                # Process chunks in order
                all_chunks = delta.unchanged_chunks + delta.changed_chunks
                all_chunks.sort(key=lambda x: x.offset)

                for chunk in all_chunks:
                    if chunk.data is not None:
                        # This is a changed chunk with new data
                        output_file.write(chunk.data)
                    else:
                        # This is an unchanged chunk, copy from source
                        try:
                            source_obj = Path(source_file)
                            with source_obj.open("rb") as source:
                                source.seek(chunk.offset)
                                chunk_data = source.read(chunk.size)
                                output_file.write(chunk_data)
                        except OSError:
                            return False

            # Replace target file with reconstructed file
            Path(temp_file).replace(target_file)
            return True

        except OSError:
            # Clean up temp file if it exists
            with contextlib.suppress(FileNotFoundError):
                Path(temp_file).unlink()
            return False

    def calculate_transfer_savings(self, delta: FileDelta) -> Dict[str, Any]:
        """Calculate the savings from using differential sync."""
        if delta.total_size == 0:
            return {
                "total_size": 0,
                "changed_size": 0,
                "unchanged_size": 0,
                "transfer_ratio": 1.0,
                "savings_percent": 0.0,
            }

        changed_size = sum(chunk.size for chunk in delta.changed_chunks)
        unchanged_size = sum(chunk.size for chunk in delta.unchanged_chunks)

        transfer_ratio = changed_size / delta.total_size
        savings_percent = (1 - transfer_ratio) * 100

        return {
            "total_size": delta.total_size,
            "changed_size": changed_size,
            "unchanged_size": unchanged_size,
            "transfer_ratio": transfer_ratio,
            "savings_percent": savings_percent,
        }

    def should_use_differential(
        self, file_size: int, estimated_change_ratio: float = 0.3
    ) -> bool:
        """Determine if differential sync should be used based on file characteristics."""
        # Don't use differential sync for small files
        if file_size < 64 * 1024:  # 64KB
            return False

        # Use differential sync for large files or when expecting small changes
        if (
            file_size > 1024 * 1024 or estimated_change_ratio < 0.5
        ):  # 1MB or <50% change
            return True

        return False
