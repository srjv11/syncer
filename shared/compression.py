"""File compression utilities for efficient transfers."""

import gzip
import zlib
from enum import Enum
from typing import Optional, Tuple

import lz4.frame  # type: ignore


class CompressionType(str, Enum):
    NONE = "none"
    GZIP = "gzip"
    ZLIB = "zlib"
    LZ4 = "lz4"


class CompressionUtil:
    """Utility class for file compression operations."""

    @staticmethod
    def compress_data(
        data: bytes, compression_type: CompressionType = CompressionType.LZ4
    ) -> Tuple[bytes, CompressionType]:
        """Compress data using specified algorithm."""
        if compression_type == CompressionType.NONE:
            return data, CompressionType.NONE

        if compression_type == CompressionType.GZIP:
            return gzip.compress(data, compresslevel=6), CompressionType.GZIP

        if compression_type == CompressionType.ZLIB:
            return zlib.compress(data, level=6), CompressionType.ZLIB

        if compression_type == CompressionType.LZ4:
            try:
                return lz4.frame.compress(data), CompressionType.LZ4
            except ImportError:
                # Fallback to zlib if lz4 not available
                return zlib.compress(data, level=6), CompressionType.ZLIB

        return data, CompressionType.NONE

    @staticmethod
    def decompress_data(
        compressed_data: bytes, compression_type: CompressionType
    ) -> bytes:
        """Decompress data using specified algorithm."""
        if compression_type == CompressionType.NONE:
            return compressed_data

        if compression_type == CompressionType.GZIP:
            return gzip.decompress(compressed_data)

        if compression_type == CompressionType.ZLIB:
            return zlib.decompress(compressed_data)

        if compression_type == CompressionType.LZ4:
            try:
                return lz4.frame.decompress(compressed_data)
            except ImportError:
                # Fallback to zlib
                return zlib.decompress(compressed_data)

        return compressed_data

    @staticmethod
    def should_compress(data_size: int, file_type: Optional[str] = None) -> bool:
        """Determine if data should be compressed based on size and type (enhanced)."""
        # Handle file type specific logic first
        if file_type:
            file_lower = file_type.lower()

            # Don't compress already compressed formats
            compressed_extensions = {
                # Archives
                ".zip",
                ".gz",
                ".bz2",
                ".xz",
                ".7z",
                ".rar",
                ".tar",
                ".tgz",
                # Images
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".avif",
                ".heic",
                # Videos
                ".mp4",
                ".avi",
                ".mkv",
                ".mov",
                ".webm",
                ".flv",
                ".wmv",
                # Audio
                ".mp3",
                ".aac",
                ".ogg",
                ".flac",
                ".m4a",
                ".wma",
                # Documents (already compressed)
                ".pdf",
                ".docx",
                ".xlsx",
                ".pptx",
                ".odt",
                ".ods",
                # Executables and binaries
                ".exe",
                ".dll",
                ".so",
                ".dylib",
                # Other compressed formats
                ".lz4",
                ".zst",
                ".br",
            }
            if any(file_lower.endswith(ext) for ext in compressed_extensions):
                return False

            # Highly compressible text formats - allow compression at lower threshold
            text_extensions = {
                ".txt",
                ".log",
                ".json",
                ".xml",
                ".html",
                ".css",
                ".js",
                ".py",
                ".java",
                ".cpp",
                ".c",
                ".h",
                ".sql",
                ".md",
                ".rst",
                ".csv",
                ".tsv",
                ".yaml",
                ".yml",
                ".ini",
                ".conf",
                ".cfg",
            }
            if any(file_lower.endswith(ext) for ext in text_extensions):
                return data_size >= 256  # Even smaller text files benefit

            # For known but unknown file types, use higher threshold
            return data_size >= 1024  # 1KB

        # For files with no type info, use basic threshold
        if data_size < 512:  # 512 bytes
            return False

        return data_size >= 512  # Compress if >= 512 bytes

    @staticmethod
    def get_compression_ratio(original_size: int, compressed_size: int) -> float:
        """Calculate compression ratio."""
        if original_size == 0:
            return 0.0
        return compressed_size / original_size

    @staticmethod
    def choose_best_compression(data: bytes) -> Tuple[bytes, CompressionType]:
        """Choose the best compression algorithm for the given data."""
        if len(data) < 1024:  # Don't compress small data
            return data, CompressionType.NONE

        # Test different compression algorithms
        results = []

        for comp_type in [
            CompressionType.LZ4,
            CompressionType.ZLIB,
            CompressionType.GZIP,
        ]:
            try:
                compressed, _ = CompressionUtil.compress_data(data, comp_type)
                ratio = CompressionUtil.get_compression_ratio(
                    len(data), len(compressed)
                )
                results.append((compressed, comp_type, ratio))
            except Exception:
                continue

        if not results:
            return data, CompressionType.NONE

        # Choose the algorithm with the best compression ratio
        best_compressed, best_type, best_ratio = min(results, key=lambda x: x[2])

        # Only use compression if it provides at least 10% reduction
        if best_ratio < 0.9:
            return best_compressed, best_type
        else:
            return data, CompressionType.NONE
