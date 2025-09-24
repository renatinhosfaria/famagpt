"""
Performance validation tests for Infrastructure Hardening Sprint.
Tests rate limiting, observability, and circuit breaker performance impact.
"""
import asyncio
import time
import pytest
import httpx
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

import redis.asyncio as aioredis
from fastapi.testclient import TestClient

from orchestrator.src.presentation.main import create_app
from orchestrator.src.infrastructure.rate_limiter import RateLimiter, RateLimitConfig
from orchestrator.src.infrastructure.circuit_breaker import CircuitBreakerManager, ServiceType
from orchestrator.src.infrastructure.observability import FamaGPTObservability, ObservabilityConfig


class PerformanceTestConfig:
    """Configuration for performance tests."""

    BASELINE_RESPONSE_TIME_MS = 50      # Target: <50ms baseline
    RATE_LIMITING_OVERHEAD_MS = 10      # Max overhead: <10ms
    OBSERVABILITY_OVERHEAD_MS = 5       # Max overhead: <5ms
    CIRCUIT_BREAKER_OVERHEAD_MS = 2     # Max overhead: <2ms

    LOAD_TEST_REQUESTS = 1000           # Load test volume
    CONCURRENT_REQUESTS = 50            # Concurrent requests

    TARGET_THROUGHPUT_RPS = 500         # Target: 500 RPS
    MAX_RESPONSE_TIME_P95_MS = 100      # P95 target: <100ms
    MAX_ERROR_RATE_PERCENT = 0.1        # Max error rate: 0.1%


@pytest.fixture
async def redis_client():
    """Test Redis client for performance tests."""
    client = aioredis.from_url("redis://localhost:6380", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.close()


@pytest.fixture
def performance_app():
    """Create test app with all infrastructure hardening enabled."""
    app = create_app()
    return TestClient(app)


class TestRateLimitingPerformance:
    """Test rate limiting performance impact."""

    async def test_rate_limiter_overhead(self, redis_client):
        """Test that rate limiting adds minimal overhead."""
        config = RateLimitConfig(
            enabled=True,
            requests_per_minute=1000,  # High limit to avoid actual limiting
            burst_allowance=100
        )
        rate_limiter = RateLimiter(redis_client, config)

        # Baseline test - no rate limiting
        start_time = time.time()
        for _ in range(100):
            pass  # Simulate basic operation
        baseline_duration = time.time() - start_time

        # Rate limiting test
        start_time = time.time()
        for _ in range(100):
            await rate_limiter.check_rate_limit("test_key", rate_limiter.RateLimitType.GLOBAL)
        rate_limited_duration = time.time() - start_time

        # Calculate overhead
        overhead_ms = (rate_limited_duration - baseline_duration) * 1000
        overhead_per_request_ms = overhead_ms / 100

        print(f"Rate limiting overhead: {overhead_per_request_ms:.2f}ms per request")

        # Assert performance target
        assert overhead_per_request_ms < PerformanceTestConfig.RATE_LIMITING_OVERHEAD_MS, \
            f"Rate limiting overhead too high: {overhead_per_request_ms:.2f}ms > {PerformanceTestConfig.RATE_LIMITING_OVERHEAD_MS}ms"

    async def test_rate_limiting_throughput(self, redis_client):
        """Test rate limiting throughput under load."""
        config = RateLimitConfig(
            enabled=True,
            requests_per_minute=10000,  # Very high limit
            burst_allowance=1000
        )
        rate_limiter = RateLimiter(redis_client, config)

        # Measure throughput
        start_time = time.time()
        requests = 1000

        tasks = []
        for i in range(requests):
            task = rate_limiter.check_rate_limit(f"test_key_{i}", rate_limiter.RateLimitType.GLOBAL)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        total_duration = time.time() - start_time

        # Calculate metrics
        throughput_rps = requests / total_duration
        avg_latency_ms = (total_duration / requests) * 1000

        print(f"Rate limiting throughput: {throughput_rps:.0f} RPS")
        print(f"Average latency: {avg_latency_ms:.2f}ms")

        # All requests should succeed (within limit)
        successful_requests = sum(1 for result in results if result["allowed"])
        success_rate = (successful_requests / requests) * 100

        assert success_rate > 99, f"Too many requests failed: {success_rate:.1f}% success rate"
        assert throughput_rps > 500, f"Throughput too low: {throughput_rps:.0f} RPS"


class TestCircuitBreakerPerformance:
    """Test circuit breaker performance impact."""

    def test_circuit_breaker_overhead(self):
        """Test circuit breaker overhead on normal operations."""
        manager = CircuitBreakerManager()

        # Baseline test
        def dummy_function():
            return "success"

        start_time = time.time()
        for _ in range(1000):
            dummy_function()
        baseline_duration = time.time() - start_time

        # Circuit breaker test
        start_time = time.time()
        for _ in range(1000):
            circuit_breaker = manager.get_circuit_breaker("test_service", ServiceType.INTERNAL_SERVICE)
            circuit_breaker.circuit_breaker.call(dummy_function)
        cb_duration = time.time() - start_time

        # Calculate overhead
        overhead_ms = (cb_duration - baseline_duration) * 1000
        overhead_per_request_ms = overhead_ms / 1000

        print(f"Circuit breaker overhead: {overhead_per_request_ms:.2f}ms per request")

        assert overhead_per_request_ms < PerformanceTestConfig.CIRCUIT_BREAKER_OVERHEAD_MS, \
            f"Circuit breaker overhead too high: {overhead_per_request_ms:.2f}ms"

    async def test_circuit_breaker_concurrent_load(self):
        """Test circuit breaker performance under concurrent load."""
        manager = CircuitBreakerManager()

        async def successful_operation():
            await asyncio.sleep(0.001)  # Simulate small amount of work
            return "success"

        # Test concurrent operations
        start_time = time.time()
        tasks = []

        for i in range(500):
            circuit_breaker = manager.get_circuit_breaker(f"service_{i % 10}", ServiceType.INTERNAL_SERVICE)
            task = circuit_breaker.call(successful_operation)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        total_duration = time.time() - start_time

        # Calculate metrics
        throughput_rps = len(tasks) / total_duration
        success_rate = (len([r for r in results if r == "success"]) / len(results)) * 100

        print(f"Circuit breaker concurrent throughput: {throughput_rps:.0f} RPS")
        print(f"Success rate: {success_rate:.1f}%")

        assert success_rate > 99, f"Too many circuit breaker failures: {success_rate:.1f}%"
        assert throughput_rps > 200, f"Concurrent throughput too low: {throughput_rps:.0f} RPS"


class TestObservabilityPerformance:
    """Test observability performance impact."""

    def test_observability_tracing_overhead(self):
        """Test OpenTelemetry tracing overhead."""
        config = ObservabilityConfig()
        config.enabled = True
        observability = FamaGPTObservability(config)
        observability.initialize()

        # Baseline test - no tracing
        start_time = time.time()
        for _ in range(1000):
            # Simulate work
            result = {"data": "test", "number": 42}
        baseline_duration = time.time() - start_time

        # Tracing test
        start_time = time.time()
        for i in range(1000):
            with observability.trace_operation("test_operation", iteration=i):
                # Same work
                result = {"data": "test", "number": 42}
        traced_duration = time.time() - start_time

        # Calculate overhead
        overhead_ms = (traced_duration - baseline_duration) * 1000
        overhead_per_operation_ms = overhead_ms / 1000

        print(f"Observability tracing overhead: {overhead_per_operation_ms:.2f}ms per operation")

        assert overhead_per_operation_ms < PerformanceTestConfig.OBSERVABILITY_OVERHEAD_MS, \
            f"Observability overhead too high: {overhead_per_operation_ms:.2f}ms"

    def test_metrics_recording_performance(self):
        """Test metrics recording performance."""
        config = ObservabilityConfig()
        config.enabled = True
        observability = FamaGPTObservability(config)
        observability.initialize()

        # Test metrics recording performance
        start_time = time.time()
        for i in range(10000):
            observability.record_request("GET", "/test", 200, 0.1)
            observability.record_cost(0.5, "test_operation")
            observability.record_llm_tokens(100, 50, "gpt-4")

        duration = time.time() - start_time
        metrics_per_second = 30000 / duration  # 3 metrics per iteration

        print(f"Metrics recording performance: {metrics_per_second:.0f} metrics/second")

        # Should be able to record thousands of metrics per second
        assert metrics_per_second > 10000, f"Metrics recording too slow: {metrics_per_second:.0f} metrics/sec"


class TestIntegratedPerformance:
    """Test integrated performance with all hardening features enabled."""

    def test_full_system_performance(self, performance_app):
        """Test full system performance with all infrastructure hardening."""
        # Warm up
        for _ in range(10):
            response = performance_app.get("/health")

        # Measure baseline performance
        response_times = []
        start_time = time.time()

        for _ in range(100):
            request_start = time.time()
            response = performance_app.get("/health")
            request_duration = (time.time() - request_start) * 1000
            response_times.append(request_duration)

            assert response.status_code == 200

        total_duration = time.time() - start_time

        # Calculate metrics
        avg_response_time = sum(response_times) / len(response_times)
        p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
        throughput_rps = 100 / total_duration

        print(f"Integrated performance metrics:")
        print(f"  Average response time: {avg_response_time:.2f}ms")
        print(f"  P95 response time: {p95_response_time:.2f}ms")
        print(f"  Throughput: {throughput_rps:.0f} RPS")

        # Assert performance targets
        assert avg_response_time < PerformanceTestConfig.BASELINE_RESPONSE_TIME_MS, \
            f"Average response time too high: {avg_response_time:.2f}ms"

        assert p95_response_time < PerformanceTestConfig.MAX_RESPONSE_TIME_P95_MS, \
            f"P95 response time too high: {p95_response_time:.2f}ms"

    def test_enhanced_monitoring_endpoints_performance(self, performance_app):
        """Test performance of new monitoring endpoints."""
        endpoints = [
            "/api/v1/monitoring/health/detailed",
            "/api/v1/monitoring/metrics/summary",
            "/api/v1/monitoring/circuit-breakers",
            "/api/v1/monitoring/observability/trace-test",
            "/api/v1/monitoring/performance/benchmark",
            "/api/v1/monitoring/config/infrastructure"
        ]

        for endpoint in endpoints:
            start_time = time.time()
            response = performance_app.get(endpoint)
            duration_ms = (time.time() - start_time) * 1000

            print(f"{endpoint}: {duration_ms:.2f}ms")

            assert response.status_code == 200, f"Endpoint {endpoint} failed: {response.status_code}"
            assert duration_ms < 200, f"Endpoint {endpoint} too slow: {duration_ms:.2f}ms"

    def test_concurrent_load_with_hardening(self, performance_app):
        """Test system performance under concurrent load."""
        def make_request():
            return performance_app.get("/health")

        # Run concurrent requests
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(200)]
            responses = [future.result() for future in futures]

        total_duration = time.time() - start_time

        # Analyze results
        successful_requests = sum(1 for r in responses if r.status_code == 200)
        success_rate = (successful_requests / len(responses)) * 100
        throughput_rps = len(responses) / total_duration

        print(f"Concurrent load test:")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Throughput: {throughput_rps:.0f} RPS")
        print(f"  Total duration: {total_duration:.2f}s")

        assert success_rate > 99, f"Too many failures under load: {success_rate:.1f}%"
        assert throughput_rps > 50, f"Throughput too low under load: {throughput_rps:.0f} RPS"


class TestPerformanceRegression:
    """Test for performance regressions compared to baseline."""

    def test_memory_usage_baseline(self):
        """Test that infrastructure hardening doesn't significantly increase memory usage."""
        import psutil
        import os

        # Get current process
        process = psutil.Process(os.getpid())

        # Get baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Initialize all hardening components
        from orchestrator.src.infrastructure.observability import initialize_observability
        from orchestrator.src.infrastructure.circuit_breaker import get_circuit_breaker_manager
        from orchestrator.src.infrastructure.rate_limiter import RateLimitConfig

        initialize_observability()
        get_circuit_breaker_manager()
        RateLimitConfig()

        # Measure memory after initialization
        hardened_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = hardened_memory - baseline_memory

        print(f"Memory usage:")
        print(f"  Baseline: {baseline_memory:.1f} MB")
        print(f"  With hardening: {hardened_memory:.1f} MB")
        print(f"  Increase: {memory_increase:.1f} MB")

        # Should not increase memory by more than 50MB
        assert memory_increase < 50, f"Memory increase too high: {memory_increase:.1f} MB"

    def test_startup_time_impact(self):
        """Test that infrastructure hardening doesn't significantly impact startup time."""
        import time

        # Measure startup time
        start_time = time.time()

        # Import and initialize (simulating app startup)
        from orchestrator.src.presentation.main import create_app
        app = create_app()

        startup_duration = time.time() - start_time

        print(f"Startup time with hardening: {startup_duration:.2f}s")

        # Should start up in under 5 seconds
        assert startup_duration < 5.0, f"Startup too slow: {startup_duration:.2f}s"


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])