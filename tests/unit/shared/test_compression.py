"""Unit tests for compression utilities."""

import gzip
import zlib
from unittest.mock import Mock, patch

import pytest

from shared.compression import CompressionType, CompressionUtil


class TestCompressionType:
    """Test CompressionType enum."""

    def test_compression_type_values(self):
        """Test CompressionType enum values."""
        assert CompressionType.NONE == "none"
        assert CompressionType.GZIP == "gzip"
        assert CompressionType.ZLIB == "zlib"
        assert CompressionType.LZ4 == "lz4"


class TestCompressionUtil:
    """Test CompressionUtil class."""

    def test_compress_data_none(self):
        """Test compression with NONE type."""
        data = b"Hello, World!"
        compressed, comp_type = CompressionUtil.compress_data(
            data, CompressionType.NONE
        )

        assert compressed == data
        assert comp_type == CompressionType.NONE

    def test_compress_data_gzip(self):
        """Test compression with GZIP."""
        data = b"Hello, World! This is a test string for compression."
        compressed, comp_type = CompressionUtil.compress_data(
            data, CompressionType.GZIP
        )

        assert comp_type == CompressionType.GZIP
        assert len(compressed) < len(data)  # Should be smaller

        # Verify it's valid gzip
        decompressed = gzip.decompress(compressed)
        assert decompressed == data

    def test_compress_data_zlib(self):
        """Test compression with ZLIB."""
        data = b"Hello, World! This is a test string for compression."
        compressed, comp_type = CompressionUtil.compress_data(
            data, CompressionType.ZLIB
        )

        assert comp_type == CompressionType.ZLIB
        assert len(compressed) < len(data)  # Should be smaller

        # Verify it's valid zlib
        decompressed = zlib.decompress(compressed)
        assert decompressed == data

    def test_compress_data_lz4_available(self):
        """Test compression with LZ4 when available."""
        data = b"Hello, World! This is a test string for compression."

        # Mock lz4 module
        with patch("shared.compression.lz4") as mock_lz4:
            mock_lz4.frame.compress.return_value = b"compressed_data"

            compressed, comp_type = CompressionUtil.compress_data(
                data, CompressionType.LZ4
            )

            assert comp_type == CompressionType.LZ4
            assert compressed == b"compressed_data"
            mock_lz4.frame.compress.assert_called_once_with(data)

    def test_compress_data_lz4_fallback(self):
        """Test LZ4 compression fallback to ZLIB."""
        data = b"Hello, World! This is a test string for compression."

        # Mock ImportError for lz4
        with patch("shared.compression.lz4.frame.compress", side_effect=ImportError):
            compressed, comp_type = CompressionUtil.compress_data(
                data, CompressionType.LZ4
            )

            assert comp_type == CompressionType.ZLIB
            # Should be valid zlib compressed data
            decompressed = zlib.decompress(compressed)
            assert decompressed == data

    def test_decompress_data_none(self):
        """Test decompression with NONE type."""
        data = b"Hello, World!"
        decompressed = CompressionUtil.decompress_data(data, CompressionType.NONE)

        assert decompressed == data

    def test_decompress_data_gzip(self):
        """Test decompression with GZIP."""
        original_data = b"Hello, World! This is a test string for decompression."
        compressed_data = gzip.compress(original_data)

        decompressed = CompressionUtil.decompress_data(
            compressed_data, CompressionType.GZIP
        )

        assert decompressed == original_data

    def test_decompress_data_zlib(self):
        """Test decompression with ZLIB."""
        original_data = b"Hello, World! This is a test string for decompression."
        compressed_data = zlib.compress(original_data)

        decompressed = CompressionUtil.decompress_data(
            compressed_data, CompressionType.ZLIB
        )

        assert decompressed == original_data

    def test_decompress_data_lz4_available(self):
        """Test decompression with LZ4 when available."""
        compressed_data = b"compressed_data"
        expected_data = b"original_data"

        # Mock lz4 module
        with patch("shared.compression.lz4") as mock_lz4:
            mock_lz4.frame.decompress.return_value = expected_data

            decompressed = CompressionUtil.decompress_data(
                compressed_data, CompressionType.LZ4
            )

            assert decompressed == expected_data
            mock_lz4.frame.decompress.assert_called_once_with(compressed_data)

    def test_decompress_data_lz4_fallback(self):
        """Test LZ4 decompression fallback to ZLIB."""
        original_data = b"Hello, World!"
        compressed_data = zlib.compress(original_data)

        # Mock ImportError for lz4
        with patch("shared.compression.lz4.frame.decompress", side_effect=ImportError):
            decompressed = CompressionUtil.decompress_data(
                compressed_data, CompressionType.LZ4
            )

            assert decompressed == original_data

    def test_should_compress_small_files(self):
        """Test compression decision for small files."""
        # Very small file
        assert CompressionUtil.should_compress(100) is False

        # Below threshold
        assert CompressionUtil.should_compress(511) is False

        # At threshold
        assert CompressionUtil.should_compress(512) is True

    def test_should_compress_compressed_formats(self):
        """Test compression decision for already compressed formats."""
        # Image formats
        assert CompressionUtil.should_compress(10000, "image.jpg") is False
        assert CompressionUtil.should_compress(10000, "image.png") is False
        assert CompressionUtil.should_compress(10000, "image.gif") is False
        assert CompressionUtil.should_compress(10000, "image.webp") is False

        # Video formats
        assert CompressionUtil.should_compress(10000, "video.mp4") is False
        assert CompressionUtil.should_compress(10000, "video.avi") is False
        assert CompressionUtil.should_compress(10000, "video.mkv") is False

        # Audio formats
        assert CompressionUtil.should_compress(10000, "audio.mp3") is False
        assert CompressionUtil.should_compress(10000, "audio.flac") is False

        # Archive formats
        assert CompressionUtil.should_compress(10000, "archive.zip") is False
        assert CompressionUtil.should_compress(10000, "archive.gz") is False
        assert CompressionUtil.should_compress(10000, "archive.7z") is False

        # Document formats
        assert CompressionUtil.should_compress(10000, "document.pdf") is False
        assert CompressionUtil.should_compress(10000, "document.docx") is False

        # Executable formats
        assert CompressionUtil.should_compress(10000, "program.exe") is False
        assert CompressionUtil.should_compress(10000, "library.dll") is False

    def test_should_compress_text_formats(self):
        """Test compression decision for text formats."""
        # Small text files should be compressed if >= 256 bytes
        assert CompressionUtil.should_compress(255, "file.txt") is False
        assert CompressionUtil.should_compress(256, "file.txt") is True

        # Various text formats
        text_extensions = [
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
        ]

        for ext in text_extensions:
            assert CompressionUtil.should_compress(1000, f"file{ext}") is True

    def test_should_compress_unknown_formats(self):
        """Test compression decision for unknown formats."""
        # Unknown extension, use default threshold
        assert CompressionUtil.should_compress(1023) is False
        assert CompressionUtil.should_compress(1024) is True

        # No extension
        assert CompressionUtil.should_compress(2000, "README") is True
        assert CompressionUtil.should_compress(2000, None) is True

    def test_should_compress_case_insensitive(self):
        """Test case-insensitive file extension checking."""
        # Uppercase extensions
        assert CompressionUtil.should_compress(10000, "IMAGE.JPG") is False
        assert CompressionUtil.should_compress(10000, "VIDEO.MP4") is False
        assert CompressionUtil.should_compress(10000, "ARCHIVE.ZIP") is False

        # Mixed case
        assert CompressionUtil.should_compress(10000, "File.TxT") is True
        assert CompressionUtil.should_compress(10000, "Data.JSON") is True

    def test_get_compression_ratio(self):
        """Test compression ratio calculation."""
        # Normal compression ratio
        ratio = CompressionUtil.get_compression_ratio(1000, 500)
        assert ratio == 0.5

        # No compression
        ratio = CompressionUtil.get_compression_ratio(1000, 1000)
        assert ratio == 1.0

        # Perfect compression
        ratio = CompressionUtil.get_compression_ratio(1000, 100)
        assert ratio == 0.1

        # Zero original size
        ratio = CompressionUtil.get_compression_ratio(0, 100)
        assert ratio == 0.0

    def test_choose_best_compression_small_data(self):
        """Test best compression choice for small data."""
        small_data = b"small"

        compressed, comp_type = CompressionUtil.choose_best_compression(small_data)

        assert compressed == small_data
        assert comp_type == CompressionType.NONE

    def test_choose_best_compression_large_data(self):
        """Test best compression choice for large data."""
        # Create data that compresses well
        large_data = b"A" * 2000

        with patch("shared.compression.lz4") as mock_lz4:
            # Mock LZ4 to return better compression
            mock_lz4.frame.compress.return_value = b"LZ4_compressed_small"

            compressed, comp_type = CompressionUtil.choose_best_compression(large_data)

            assert comp_type in [
                CompressionType.LZ4,
                CompressionType.ZLIB,
                CompressionType.GZIP,
            ]
            assert len(compressed) < len(large_data)

    def test_choose_best_compression_no_benefit(self):
        """Test best compression when compression doesn't help."""
        # Random-like data that doesn't compress well
        random_data = bytes(range(256)) * 5  # 1280 bytes of varied data

        # Mock all compression methods to return larger data
        with patch.multiple("shared.compression", lz4=Mock(), gzip=Mock(), zlib=Mock()):
            # Make all compression methods return larger data
            with patch.object(CompressionUtil, "compress_data") as mock_compress:

                def side_effect(data, comp_type):
                    if comp_type == CompressionType.NONE:
                        return data, comp_type
                    # Return larger data to simulate poor compression
                    return data + b"extra", comp_type

                mock_compress.side_effect = side_effect

                # Should return original data with NONE type
                compressed, comp_type = CompressionUtil.choose_best_compression(
                    random_data
                )

                assert compressed == random_data
                assert comp_type == CompressionType.NONE

    def test_choose_best_compression_exception_handling(self):
        """Test best compression with exceptions."""
        data = b"test data for compression" * 50

        # Mock compression methods to raise exceptions
        with patch.object(CompressionUtil, "compress_data") as mock_compress:

            def side_effect(data, comp_type):
                if comp_type == CompressionType.NONE:
                    return data, comp_type
                raise Exception("Compression failed")

            mock_compress.side_effect = side_effect

            # Should fallback to no compression
            compressed, comp_type = CompressionUtil.choose_best_compression(data)

            assert compressed == data
            assert comp_type == CompressionType.NONE


class TestCompressionRoundTrip:
    """Test compression/decompression round trips."""

    @pytest.mark.parametrize(
        "comp_type",
        [
            CompressionType.GZIP,
            CompressionType.ZLIB,
        ],
    )
    def test_compression_round_trip(self, comp_type):
        """Test round trip compression/decompression."""
        original_data = b"This is test data for compression. " * 100

        # Compress
        compressed, returned_type = CompressionUtil.compress_data(
            original_data, comp_type
        )
        assert returned_type == comp_type

        # Decompress
        decompressed = CompressionUtil.decompress_data(compressed, comp_type)
        assert decompressed == original_data

    def test_lz4_round_trip_with_mock(self):
        """Test LZ4 round trip with mocked library."""
        original_data = b"This is test data for LZ4 compression. " * 100
        compressed_data = b"mock_compressed_lz4_data"

        with patch("shared.compression.lz4") as mock_lz4:
            mock_lz4.frame.compress.return_value = compressed_data
            mock_lz4.frame.decompress.return_value = original_data

            # Compress
            compressed, comp_type = CompressionUtil.compress_data(
                original_data, CompressionType.LZ4
            )
            assert comp_type == CompressionType.LZ4
            assert compressed == compressed_data

            # Decompress
            decompressed = CompressionUtil.decompress_data(
                compressed, CompressionType.LZ4
            )
            assert decompressed == original_data

    def test_binary_data_compression(self):
        """Test compression of binary data."""
        # Create binary data
        binary_data = bytes(range(256)) + b"\\x00\\x01\\x02" * 100

        compressed, comp_type = CompressionUtil.compress_data(
            binary_data, CompressionType.ZLIB
        )
        assert comp_type == CompressionType.ZLIB

        decompressed = CompressionUtil.decompress_data(compressed, CompressionType.ZLIB)
        assert decompressed == binary_data

    def test_empty_data_compression(self):
        """Test compression of empty data."""
        empty_data = b""

        compressed, comp_type = CompressionUtil.compress_data(
            empty_data, CompressionType.GZIP
        )
        decompressed = CompressionUtil.decompress_data(compressed, CompressionType.GZIP)

        assert decompressed == empty_data

    def test_large_data_compression(self):
        """Test compression of large data."""
        # 1MB of repetitive data
        large_data = b"abcdefghijklmnopqrstuvwxyz" * (1024 * 40)

        compressed, comp_type = CompressionUtil.compress_data(
            large_data, CompressionType.ZLIB
        )
        assert comp_type == CompressionType.ZLIB
        assert len(compressed) < len(large_data) * 0.1  # Should compress very well

        decompressed = CompressionUtil.decompress_data(compressed, CompressionType.ZLIB)
        assert decompressed == large_data


class TestCompressionEdgeCases:
    """Test edge cases in compression."""

    def test_invalid_compression_type(self):
        """Test handling of invalid compression type."""
        data = b"test data"

        # Should return original data for unknown type
        compressed, comp_type = CompressionUtil.compress_data(data, "invalid")  # type: ignore
        assert compressed == data
        assert comp_type == CompressionType.NONE

    def test_decompression_with_invalid_data(self):
        """Test decompression with invalid compressed data."""
        invalid_data = b"this is not compressed data"

        # Should raise appropriate exceptions
        with pytest.raises(Exception):
            CompressionUtil.decompress_data(invalid_data, CompressionType.GZIP)

        with pytest.raises(Exception):
            CompressionUtil.decompress_data(invalid_data, CompressionType.ZLIB)

    def test_compression_ratio_edge_cases(self):
        """Test compression ratio edge cases."""
        # Division by zero protection
        ratio = CompressionUtil.get_compression_ratio(0, 0)
        assert ratio == 0.0

        # Expansion (compressed larger than original)
        ratio = CompressionUtil.get_compression_ratio(100, 150)
        assert ratio == 1.5

    def test_file_extension_edge_cases(self):
        """Test file extension edge cases."""
        # Multiple extensions
        assert CompressionUtil.should_compress(2000, "file.tar.gz") is False
        assert CompressionUtil.should_compress(2000, "backup.sql.gz") is False

        # No extension
        assert CompressionUtil.should_compress(2000, "Makefile") is True
        assert CompressionUtil.should_compress(2000, "README") is True

        # Hidden files
        assert CompressionUtil.should_compress(2000, ".gitignore") is True
        assert CompressionUtil.should_compress(2000, ".env") is True

        # Weird extensions
        assert CompressionUtil.should_compress(2000, "file.weird_ext") is True
