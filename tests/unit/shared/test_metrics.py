"""Unit tests for metrics collection utilities."""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest

from shared.metrics import (
    MetricsCollector,
    PerformanceMetric,
    PerformanceTimer,
    SystemStats,
    get_global_collector,
    increment_counter,
    record_histogram,
    record_metric,
    set_gauge,
    timer,
)


class TestPerformanceMetric:
    """Test PerformanceMetric dataclass."""

    def test_performance_metric_creation(self):
        """Test PerformanceMetric creation."""
        metric = PerformanceMetric(
            name="test_metric",
            value=42.5,
            timestamp=time.time(),
            tags={"env": "test", "service": "sync"},
        )

        assert metric.name == "test_metric"
        assert metric.value == 42.5
        assert isinstance(metric.timestamp, float)
        assert metric.tags["env"] == "test"
        assert metric.tags["service"] == "sync"

    def test_performance_metric_default_tags(self):
        """Test PerformanceMetric with default tags."""
        metric = PerformanceMetric(
            name="simple_metric", value=100.0, timestamp=time.time()
        )

        assert metric.name == "simple_metric"
        assert metric.value == 100.0
        assert metric.tags == {}


class TestSystemStats:
    """Test SystemStats dataclass."""

    def test_system_stats_creation(self):
        """Test SystemStats creation."""
        stats = SystemStats(
            cpu_percent=45.6,
            memory_percent=60.2,
            memory_used_mb=4096.0,
            memory_available_mb=4096.0,
            disk_io_read_mb=10.5,
            disk_io_write_mb=5.2,
            network_bytes_sent=1024.0,
            network_bytes_recv=2048.0,
            timestamp=time.time(),
        )

        assert stats.cpu_percent == 45.6
        assert stats.memory_percent == 60.2
        assert stats.memory_used_mb == 4096.0
        assert stats.memory_available_mb == 4096.0
        assert stats.disk_io_read_mb == 10.5
        assert stats.disk_io_write_mb == 5.2
        assert stats.network_bytes_sent == 1024.0
        assert stats.network_bytes_recv == 2048.0
        assert isinstance(stats.timestamp, float)


class TestMetricsCollector:
    """Test MetricsCollector class."""

    def test_metrics_collector_initialization(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()

        assert len(collector._metrics) == 0
        assert len(collector._counters) == 0
        assert len(collector._gauges) == 0
        assert len(collector._histograms) == 0
        assert collector._collection_task is None

    def test_metrics_collector_custom_max_metrics(self):
        """Test MetricsCollector with custom max metrics."""
        collector = MetricsCollector(max_metrics=5000)
        assert collector._metrics.maxlen == 5000

    def test_record_metric(self):
        """Test recording a metric."""
        collector = MetricsCollector()

        collector.record_metric("test_metric", 42.5, {"tag": "value"})

        assert len(collector._metrics) == 1
        metric = collector._metrics[0]
        assert metric.name == "test_metric"
        assert metric.value == 42.5
        assert metric.tags["tag"] == "value"
        assert isinstance(metric.timestamp, float)

    def test_increment_counter(self):
        """Test incrementing a counter."""
        collector = MetricsCollector()

        # Increment by default amount (1)
        collector.increment_counter("requests")
        assert collector._counters["requests"] == 1

        # Increment by custom amount
        collector.increment_counter("requests", 5)
        assert collector._counters["requests"] == 6

        # Should also record metric
        assert len(collector._metrics) >= 2

    def test_set_gauge(self):
        """Test setting a gauge value."""
        collector = MetricsCollector()

        collector.set_gauge("temperature", 23.5)
        assert collector._gauges["temperature"] == 23.5

        # Update gauge
        collector.set_gauge("temperature", 24.0)
        assert collector._gauges["temperature"] == 24.0

        # Should record metrics
        assert len(collector._metrics) >= 2

    def test_record_histogram(self):
        """Test recording histogram values."""
        collector = MetricsCollector()

        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for value in values:
            collector.record_histogram("response_time", value)

        assert len(collector._histograms["response_time"]) == 5
        assert collector._histograms["response_time"] == values

        # Should record metrics
        assert len(collector._metrics) == 5

    def test_get_histogram_stats(self):
        """Test histogram statistics calculation."""
        collector = MetricsCollector()

        # Record values
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for value in values:
            collector.record_histogram("test_histogram", value)

        stats = collector.get_histogram_stats("test_histogram")

        assert stats["count"] == 5
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["mean"] == 3.0
        assert stats["p50"] == 3.0
        assert "p90" in stats
        assert "p95" in stats
        assert "p99" in stats

    def test_get_histogram_stats_empty(self):
        """Test histogram statistics for non-existent histogram."""
        collector = MetricsCollector()
        stats = collector.get_histogram_stats("nonexistent")
        assert stats == {}

    def test_get_metrics_summary(self):
        """Test getting metrics summary."""
        collector = MetricsCollector()

        # Add various metrics
        collector.record_metric("test", 1.0)
        collector.increment_counter("requests", 5)
        collector.set_gauge("active_users", 100)
        collector.record_histogram("latency", 0.5)

        summary = collector.get_metrics_summary()

        assert "recent_metrics" in summary
        assert "counters" in summary
        assert "gauges" in summary
        assert "histograms" in summary
        assert "system_stats" in summary
        assert "collection_info" in summary

        assert summary["counters"]["requests"] == 5
        assert summary["gauges"]["active_users"] == 100
        assert "latency" in summary["histograms"]

    def test_clear_metrics(self):
        """Test clearing all metrics."""
        collector = MetricsCollector()

        # Add metrics
        collector.record_metric("test", 1.0)
        collector.increment_counter("requests")
        collector.set_gauge("users", 50)
        collector.record_histogram("time", 1.0)

        # Verify metrics exist
        assert len(collector._metrics) > 0
        assert len(collector._counters) > 0
        assert len(collector._gauges) > 0
        assert len(collector._histograms) > 0

        # Clear all
        collector.clear_metrics()

        # Verify cleared
        assert len(collector._metrics) == 0
        assert len(collector._counters) == 0
        assert len(collector._gauges) == 0
        assert len(collector._histograms) == 0

    @patch("shared.metrics.psutil")
    def test_get_system_stats(self, mock_psutil):
        """Test system statistics collection."""
        # Mock psutil responses
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.used = 4 * 1024 * 1024 * 1024  # 4GB
        mock_memory.available = 4 * 1024 * 1024 * 1024  # 4GB
        mock_psutil.virtual_memory.return_value = mock_memory

        mock_disk_io = Mock()
        mock_disk_io.read_bytes = 1000000
        mock_disk_io.write_bytes = 500000
        mock_psutil.disk_io_counters.return_value = mock_disk_io

        mock_net_io = Mock()
        mock_net_io.bytes_sent = 2000000
        mock_net_io.bytes_recv = 3000000
        mock_psutil.net_io_counters.return_value = mock_net_io

        collector = MetricsCollector()
        stats = collector._get_system_stats()

        assert stats.cpu_percent == 50.0
        assert stats.memory_percent == 60.0
        assert stats.memory_used_mb == 4096.0
        assert stats.memory_available_mb == 4096.0
        assert isinstance(stats.timestamp, float)

    def test_histogram_size_limit(self):
        """Test histogram size limiting."""
        collector = MetricsCollector()

        # Add more values than the limit (1000)
        for i in range(1200):
            collector.record_histogram("large_histogram", i)

        # Should be limited to 1000 values
        assert len(collector._histograms["large_histogram"]) == 1000

        # Should keep the most recent values
        histogram_values = collector._histograms["large_histogram"]
        assert histogram_values[0] == 200  # First value after truncation
        assert histogram_values[-1] == 1199  # Last value added


class TestPerformanceTimer:
    """Test PerformanceTimer class."""

    def test_performance_timer_context_manager(self):
        """Test PerformanceTimer as context manager."""
        collector = MetricsCollector()

        with PerformanceTimer(collector, "test_operation"):
            time.sleep(0.01)  # 10ms

        # Should have recorded duration histogram
        assert "test_operation_duration_seconds" in collector._histograms
        duration = collector._histograms["test_operation_duration_seconds"][0]
        assert duration > 0.005  # Should be at least 5ms

        # Should have recorded success counter
        assert collector._counters["test_operation_success_total"] == 1

    def test_performance_timer_with_exception(self):
        """Test PerformanceTimer with exception."""
        collector = MetricsCollector()

        try:
            with PerformanceTimer(collector, "failing_operation"):
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Should have recorded duration
        assert "failing_operation_duration_seconds" in collector._histograms

        # Should have recorded error counter
        assert collector._counters["failing_operation_error_total"] == 1
        assert "failing_operation_success_total" not in collector._counters

    def test_performance_timer_with_tags(self):
        """Test PerformanceTimer with tags."""
        collector = MetricsCollector()
        tags = {"service": "sync", "endpoint": "/api/upload"}

        with PerformanceTimer(collector, "upload", tags):
            time.sleep(0.005)

        # Check that metrics were recorded with tags
        metrics = list(collector._metrics)
        histogram_metric = next(m for m in metrics if "duration_seconds" in m.name)
        assert histogram_metric.tags == tags


class TestGlobalFunctions:
    """Test global convenience functions."""

    def test_get_global_collector(self):
        """Test getting global collector."""
        collector1 = get_global_collector()
        collector2 = get_global_collector()

        # Should return the same instance
        assert collector1 is collector2
        assert isinstance(collector1, MetricsCollector)

    def test_global_record_metric(self):
        """Test global record_metric function."""
        # Clear any existing metrics
        collector = get_global_collector()
        collector.clear_metrics()

        record_metric("global_test", 123.45, {"global": "true"})

        assert len(collector._metrics) == 1
        metric = collector._metrics[0]
        assert metric.name == "global_test"
        assert metric.value == 123.45
        assert metric.tags["global"] == "true"

    def test_global_increment_counter(self):
        """Test global increment_counter function."""
        collector = get_global_collector()
        collector.clear_metrics()

        increment_counter("global_counter", 3)

        assert collector._counters["global_counter"] == 3

    def test_global_set_gauge(self):
        """Test global set_gauge function."""
        collector = get_global_collector()
        collector.clear_metrics()

        set_gauge("global_gauge", 99.9)

        assert collector._gauges["global_gauge"] == 99.9

    def test_global_record_histogram(self):
        """Test global record_histogram function."""
        collector = get_global_collector()
        collector.clear_metrics()

        record_histogram("global_histogram", 2.5)

        assert collector._histograms["global_histogram"] == [2.5]

    def test_global_timer(self):
        """Test global timer function."""
        collector = get_global_collector()
        collector.clear_metrics()

        with timer("global_timer"):
            time.sleep(0.005)

        assert "global_timer_duration_seconds" in collector._histograms
        assert collector._counters["global_timer_success_total"] == 1


class TestMetricsIntegration:
    """Integration tests for metrics functionality."""

    def test_realistic_metrics_scenario(self):
        """Test realistic application metrics scenario."""
        collector = MetricsCollector()

        # Simulate web server metrics
        for i in range(10):
            # Record request
            collector.increment_counter("http_requests_total")

            # Record response time
            response_time = 0.1 + (i * 0.05)  # Increasing response times
            collector.record_histogram("http_request_duration_seconds", response_time)

            # Record active connections
            collector.set_gauge("http_active_connections", 5 + i)

        # Check collected metrics
        assert collector._counters["http_requests_total"] == 10
        assert collector._gauges["http_active_connections"] == 14  # Last value
        assert len(collector._histograms["http_request_duration_seconds"]) == 10

        # Check histogram stats
        stats = collector.get_histogram_stats("http_request_duration_seconds")
        assert stats["count"] == 10
        assert stats["min"] == 0.1
        assert stats["max"] == 0.55
        assert 0.2 < stats["mean"] < 0.4

    @pytest.mark.asyncio
    async def test_async_metrics_collection(self):
        """Test metrics collection in async context."""
        collector = MetricsCollector()

        async def async_operation():
            with PerformanceTimer(collector, "async_op"):
                await asyncio.sleep(0.01)
                collector.increment_counter("async_operations")
            return "completed"

        # Run multiple async operations
        tasks = [async_operation() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(r == "completed" for r in results)

        # Check metrics
        assert collector._counters["async_operations"] == 5
        assert collector._counters["async_op_success_total"] == 5
        assert len(collector._histograms["async_op_duration_seconds"]) == 5

    def test_large_scale_metrics(self):
        """Test metrics collection with large number of data points."""
        collector = MetricsCollector()

        # Simulate high-frequency metrics
        for i in range(1000):
            collector.increment_counter("high_freq_counter")
            collector.record_histogram("high_freq_histogram", i % 100)

            # Only record gauge occasionally to avoid too many metrics
            if i % 10 == 0:
                collector.set_gauge("current_value", i)

        # Check results
        assert collector._counters["high_freq_counter"] == 1000
        assert collector._gauges["current_value"] == 990

        # Histogram should be limited
        assert len(collector._histograms["high_freq_histogram"]) == 1000

        # Get summary should work with large datasets
        summary = collector.get_metrics_summary()
        assert summary["counters"]["high_freq_counter"] == 1000
        assert "high_freq_histogram" in summary["histograms"]

    def test_concurrent_metrics_access(self):
        """Test concurrent access to metrics collector."""
        collector = MetricsCollector()

        import threading

        def worker(worker_id):
            for i in range(100):
                collector.increment_counter(f"worker_{worker_id}")
                collector.record_histogram("worker_histogram", i)
                collector.set_gauge(f"worker_{worker_id}_gauge", i)

        # Start multiple workers
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify results
        for i in range(5):
            assert collector._counters[f"worker_{i}"] == 100
            assert collector._gauges[f"worker_{i}_gauge"] == 99  # Last value

        # Histogram should have all values
        assert (
            len(collector._histograms["worker_histogram"]) == 500
        )  # 5 workers * 100 values each
