import asyncio
import fnmatch
import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Pattern, Union

import aiofiles


async def calculate_file_checksum(file_path: str, chunk_size: int = 65536) -> str:
    """Calculate SHA-256 checksum of a file asynchronously with larger chunks."""
    sha256_hash = hashlib.sha256()
    try:
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(chunk_size):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except OSError:
        return ""


def calculate_file_checksum_sync(file_path: str, chunk_size: int = 65536) -> str:
    """Calculate SHA-256 checksum of a file synchronously with larger chunks."""
    sha256_hash = hashlib.sha256()
    try:
        file_obj = Path(file_path)
        with file_obj.open("rb") as f:
            while chunk := f.read(chunk_size):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except OSError:
        return ""


async def calculate_file_checksum_fast(file_path: str) -> str:
    """Calculate file checksum using xxhash for better performance."""
    try:
        # Try to use xxhash if available, fallback to SHA-256
        try:
            import xxhash

            hasher = xxhash.xxh64()
            async with aiofiles.open(file_path, "rb") as f:
                while chunk := await f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except ImportError:
            return await calculate_file_checksum(file_path)
    except OSError:
        return ""


async def get_file_info(
    file_path: str, fast_checksum: bool = False
) -> Optional[Dict[str, Union[str, int, datetime, bool]]]:
    """Get file information including size, modified time, and checksum asynchronously."""
    try:
        path = Path(file_path)
        if not path.exists():
            return None

        stat = path.stat()

        # Calculate checksum asynchronously
        if path.is_dir():
            checksum = ""
        elif fast_checksum:
            checksum = await calculate_file_checksum_fast(file_path)
        else:
            checksum = await calculate_file_checksum(file_path)

        return {
            "path": str(path),
            "size": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime),
            "is_directory": path.is_dir(),
            "checksum": checksum,
        }
    except OSError:
        return None


def get_file_info_sync(
    file_path: str,
) -> Optional[Dict[str, Union[str, int, datetime, bool]]]:
    """Get file information synchronously (for backward compatibility)."""
    try:
        path = Path(file_path)
        if not path.exists():
            return None

        stat = path.stat()
        return {
            "path": str(path),
            "size": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime),
            "is_directory": path.is_dir(),
            "checksum": ""
            if path.is_dir()
            else calculate_file_checksum_sync(file_path),
        }
    except OSError:
        return None


# Keep original function for backward compatibility
# get_file_info = get_file_info_sync  # Commented out to avoid redefinition


# Global cache for compiled patterns
_compiled_patterns_cache: Dict[str, Pattern[str]] = {}


def _compile_pattern(pattern: str) -> Pattern[str]:
    """Compile fnmatch pattern to regex, with caching."""
    if pattern not in _compiled_patterns_cache:
        # Convert fnmatch pattern to regex
        regex_pattern = fnmatch.translate(pattern)
        _compiled_patterns_cache[pattern] = re.compile(regex_pattern)
    return _compiled_patterns_cache[pattern]


def should_ignore_file(file_path: str, ignore_patterns: List[str]) -> bool:
    """Check if a file should be ignored based on patterns (optimized with compiled regex)."""
    file_name = os.path.basename(file_path)
    relative_path = file_path

    for pattern in ignore_patterns:
        compiled_pattern = _compile_pattern(pattern)
        if compiled_pattern.match(file_name) or compiled_pattern.match(relative_path):
            return True
    return False


def normalize_path(path: str) -> str:
    """Normalize file path for cross-platform compatibility."""
    return str(Path(path).as_posix())


async def copy_file_async(src: str, dst: str, chunk_size: int = 65536) -> None:
    """Copy file asynchronously with better performance."""
    ensure_directory(str(Path(dst).parent))

    async with aiofiles.open(src, "rb") as src_file:
        async with aiofiles.open(dst, "wb") as dst_file:
            while chunk := await src_file.read(chunk_size):
                await dst_file.write(chunk)


def ensure_directory(directory: str) -> None:
    """Ensure directory exists, create if it doesn't."""
    Path(directory).mkdir(parents=True, exist_ok=True)


async def ensure_directory_async(directory: str) -> None:
    """Ensure directory exists asynchronously."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        await loop.run_in_executor(executor, ensure_directory, directory)


def get_relative_path(file_path: str, base_path: str) -> str:
    """Get relative path from base directory."""
    try:
        return str(Path(file_path).relative_to(Path(base_path)))
    except ValueError:
        return file_path


async def batch_get_file_info(
    file_paths: List[str], max_workers: int = 4, fast_checksum: bool = False
) -> List[Optional[Dict[str, Union[str, int, datetime, bool]]]]:
    """Get file information for multiple files concurrently."""
    semaphore = asyncio.Semaphore(max_workers)

    async def get_file_info_with_semaphore(
        file_path: str,
    ) -> Optional[Dict[str, Union[str, int, datetime, bool]]]:
        async with semaphore:
            return await get_file_info_async(file_path, fast_checksum)

    tasks = [get_file_info_with_semaphore(file_path) for file_path in file_paths]
    return await asyncio.gather(*tasks, return_exceptions=False)


# Rename async version to avoid confusion
get_file_info_async = get_file_info
