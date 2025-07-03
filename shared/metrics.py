"""Performance metrics collection and monitoring utilities."""

import asyncio
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psutil


@dataclass
class PerformanceMetric:
    """Individual performance metric."""

    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class SystemStats:
    """System performance statistics."""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_bytes_sent: float
    network_bytes_recv: float
    timestamp: float


class MetricsCollector:
    """Centralized metrics collection system."""

    def __init__(self, max_metrics: int = 10000):
        self._metrics: deque = deque(maxlen=max_metrics)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._system_stats: List[SystemStats] = []
        self._lock = threading.Lock()
        self._process = psutil.Process()
        self._last_disk_io = None
        self._last_network_io = None
        self._collection_interval = 60  # seconds
        self._collection_task: Optional[asyncio.Task] = None

    def start_collection(self) -> None:
        """Start automatic metrics collection."""
        if self._collection_task is None or self._collection_task.done():
            self._collection_task = asyncio.create_task(self._collect_system_metrics())

    def stop_collection(self) -> None:
        """Stop automatic metrics collection."""
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()

    async def _collect_system_metrics(self) -> None:
        """Collect system metrics periodically."""
        while True:
            try:
                await asyncio.sleep(self._collection_interval)
                stats = self._get_system_stats()

                with self._lock:
                    self._system_stats.append(stats)
                    # Keep only last 100 system stats
                    if len(self._system_stats) > 100:
                        self._system_stats = self._system_stats[-100:]

            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue collection
                pass

    def _get_system_stats(self) -> SystemStats:
        """Get current system statistics."""
        # CPU and memory
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()

        # Disk I/O
        disk_io = psutil.disk_io_counters()
        disk_read_mb = 0.0
        disk_write_mb = 0.0

        if disk_io and self._last_disk_io:
            disk_read_mb = (disk_io.read_bytes - self._last_disk_io.read_bytes) / (
                1024 * 1024
            )
            disk_write_mb = (disk_io.write_bytes - self._last_disk_io.write_bytes) / (
                1024 * 1024
            )

        self._last_disk_io = disk_io

        # Network I/O
        network_io = psutil.net_io_counters()
        network_sent = 0.0
        network_recv = 0.0

        if network_io and self._last_network_io:
            network_sent = network_io.bytes_sent - self._last_network_io.bytes_sent
            network_recv = network_io.bytes_recv - self._last_network_io.bytes_recv

        self._last_network_io = network_io

        return SystemStats(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_available_mb=memory.available / (1024 * 1024),
            disk_io_read_mb=disk_read_mb,
            disk_io_write_mb=disk_write_mb,
            network_bytes_sent=network_sent,
            network_bytes_recv=network_recv,
            timestamp=time.time(),
        )

    def record_metric(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a performance metric."""
        metric = PerformanceMetric(
            name=name, value=value, timestamp=time.time(), tags=tags or {}
        )

        with self._lock:
            self._metrics.append(metric)

    def increment_counter(
        self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Increment a counter metric."""
        with self._lock:
            self._counters[name] += value
        self.record_metric(f"{name}_total", self._counters[name], tags)

    def set_gauge(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Set a gauge metric."""
        with self._lock:
            self._gauges[name] = value
        self.record_metric(name, value, tags)

    def record_histogram(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a histogram value."""
        with self._lock:
            self._histograms[name].append(value)
            # Keep only last 1000 values per histogram
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]

        self.record_metric(name, value, tags)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get statistics for a histogram."""
        with self._lock:
            values = self._histograms.get(name, [])

        if not values:
            return {}

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "mean": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p90": sorted_values[int(count * 0.9)],
            "p95": sorted_values[int(count * 0.95)],
            "p99": sorted_values[int(count * 0.99)],
        }

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all collected metrics."""
        with self._lock:
            recent_metrics = list(self._metrics)[-100:]  # Last 100 metrics
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            system_stats = self._system_stats[-10:] if self._system_stats else []

        # Calculate histogram summaries
        histogram_summaries = {}
        for name in self._histograms:
            histogram_summaries[name] = self.get_histogram_stats(name)

        return {
            "recent_metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "timestamp": m.timestamp,
                    "tags": m.tags,
                }
                for m in recent_metrics
            ],
            "counters": counters,
            "gauges": gauges,
            "histograms": histogram_summaries,
            "system_stats": [
                {
                    "cpu_percent": s.cpu_percent,
                    "memory_percent": s.memory_percent,
                    "memory_used_mb": s.memory_used_mb,
                    "memory_available_mb": s.memory_available_mb,
                    "disk_io_read_mb": s.disk_io_read_mb,
                    "disk_io_write_mb": s.disk_io_write_mb,
                    "network_bytes_sent": s.network_bytes_sent,
                    "network_bytes_recv": s.network_bytes_recv,
                    "timestamp": s.timestamp,
                }
                for s in system_stats
            ],
            "collection_info": {
                "total_metrics": len(self._metrics),
                "collection_interval": self._collection_interval,
                "is_collecting": self._collection_task is not None
                and not self._collection_task.done(),
            },
        }

    def clear_metrics(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._system_stats.clear()


class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(
        self,
        metrics_collector: MetricsCollector,
        metric_name: str,
        tags: Optional[Dict[str, str]] = None,
    ):
        self.collector = metrics_collector
        self.metric_name = metric_name
        self.tags = tags or {}
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.collector.record_histogram(
            f"{self.metric_name}_duration_seconds", duration, self.tags
        )

        # Also record success/error
        if exc_type is None:
            self.collector.increment_counter(
                f"{self.metric_name}_success_total", tags=self.tags
            )
        else:
            self.collector.increment_counter(
                f"{self.metric_name}_error_total", tags=self.tags
            )


# Global metrics collector instance
_global_collector: Optional[MetricsCollector] = None


def get_global_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def start_global_collection() -> None:
    """Start global metrics collection."""
    collector = get_global_collector()
    collector.start_collection()


def stop_global_collection() -> None:
    """Stop global metrics collection."""
    global _global_collector
    if _global_collector:
        _global_collector.stop_collection()


def record_metric(
    name: str, value: float, tags: Optional[Dict[str, str]] = None
) -> None:
    """Record a metric using the global collector."""
    collector = get_global_collector()
    collector.record_metric(name, value, tags)


def increment_counter(
    name: str, value: int = 1, tags: Optional[Dict[str, str]] = None
) -> None:
    """Increment a counter using the global collector."""
    collector = get_global_collector()
    collector.increment_counter(name, value, tags)


def set_gauge(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Set a gauge using the global collector."""
    collector = get_global_collector()
    collector.set_gauge(name, value, tags)


def record_histogram(
    name: str, value: float, tags: Optional[Dict[str, str]] = None
) -> None:
    """Record a histogram value using the global collector."""
    collector = get_global_collector()
    collector.record_histogram(name, value, tags)


def timer(metric_name: str, tags: Optional[Dict[str, str]] = None) -> PerformanceTimer:
    """Create a performance timer using the global collector."""
    collector = get_global_collector()
    return PerformanceTimer(collector, metric_name, tags)
