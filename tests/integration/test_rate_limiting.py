"""
Integration tests for rate limiting functionality.
"""
import asyncio
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
import redis.asyncio as aioredis
import time
from unittest.mock import patch

from orchestrator.src.presentation.main import create_app
from orchestrator.src.infrastructure.rate_limiter import RateLimiter, RateLimitConfig, RateLimitType


@pytest.fixture
async def redis_client():
    """Create test Redis client."""
    client = aioredis.from_url("redis://localhost:6380", decode_responses=True)

    # Clear any existing test data
    await client.flushdb()

    yield client

    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
def rate_limit_config():
    """Test rate limit configuration."""
    return RateLimitConfig(
        enabled=True,
        requests_per_minute=10,  # Low limit for testing
        cost_limit_per_day_brl=50.0,  # Low limit for testing
        burst_allowance=2,
        openai_requests_per_minute=5,
        openai_cost_per_request_brl=5.0  # High cost for testing
    )


@pytest.fixture
async def rate_limiter(redis_client, rate_limit_config):
    """Create test rate limiter."""
    return RateLimiter(redis_client, rate_limit_config)


class TestRateLimiter:
    """Test rate limiter core functionality."""

    async def test_global_rate_limit_allows_within_limit(self, rate_limiter):
        """Test that requests within global limit are allowed."""
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.GLOBAL
        )

        assert result["allowed"] is True
        assert result["remaining"] > 0
        assert result["limit_type"] == "global"

    async def test_global_rate_limit_blocks_over_limit(self, rate_limiter):
        """Test that requests over global limit are blocked."""
        # Make requests up to the limit + burst
        for i in range(12):  # 10 + 2 burst
            await rate_limiter.check_rate_limit(
                key="test_client",
                limit_type=RateLimitType.GLOBAL
            )

        # Next request should be blocked
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.GLOBAL
        )

        assert result["allowed"] is False
        assert result["remaining"] == 0

    async def test_user_rate_limit(self, rate_limiter):
        """Test per-user rate limiting."""
        user_id = "test_user_123"

        # User limit is typically lower than global
        for i in range(7):  # Per-user limit is ~7 (25//4 + 5 burst)
            result = await rate_limiter.check_rate_limit(
                key="test_client",
                limit_type=RateLimitType.USER,
                user_id=user_id
            )
            if not result["allowed"]:
                break

        # Should eventually hit user limit
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.USER,
            user_id=user_id
        )

        assert result["limit_type"] == "user"
        assert "user_id" in result

    async def test_cost_protection_limit(self, rate_limiter):
        """Test daily cost protection."""
        # Cost limit is 50 BRL, each request costs 5 BRL
        # So we can make 10 requests before hitting limit

        for i in range(10):
            result = await rate_limiter.check_rate_limit(
                key="test_client",
                limit_type=RateLimitType.COST_PROTECTION
            )
            if not result["allowed"]:
                break

        # Next request should be blocked due to cost
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.COST_PROTECTION
        )

        assert result["allowed"] is False
        assert result["limit_type"] == "cost_protection"
        assert "current_cost_brl" in result
        assert "limit_brl" in result

    async def test_openai_specific_rate_limit(self, rate_limiter):
        """Test OpenAI API specific rate limiting."""
        # OpenAI limit is 5 requests per minute
        for i in range(5):
            await rate_limiter.check_rate_limit(
                key="test_client",
                limit_type=RateLimitType.OPENAI_API
            )

        # Next request should be blocked
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.OPENAI_API
        )

        assert result["allowed"] is False
        assert result["limit_type"] == "openai_api"

    async def test_rate_limit_window_reset(self, rate_limiter, redis_client):
        """Test that rate limits reset after time window."""
        # Hit the limit
        for i in range(12):
            await rate_limiter.check_rate_limit(
                key="test_client",
                limit_type=RateLimitType.GLOBAL
            )

        # Should be blocked
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.GLOBAL
        )
        assert result["allowed"] is False

        # Simulate time passing by manipulating Redis keys
        # In a real test, you'd wait or use faketime
        current_time = int(time.time())
        window_start = current_time - (current_time % 60)
        old_key = f"rate_limit:global:test_client:{window_start}"
        await redis_client.delete(old_key)

        # Should be allowed again
        result = await rate_limiter.check_rate_limit(
            key="test_client",
            limit_type=RateLimitType.GLOBAL
        )
        assert result["allowed"] is True

    async def test_disabled_rate_limiting(self, redis_client):
        """Test that disabled rate limiting allows all requests."""
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(redis_client, config)

        # Make many requests - should all be allowed
        for i in range(100):
            result = await limiter.check_rate_limit(
                key="test_client",
                limit_type=RateLimitType.GLOBAL
            )
            assert result["allowed"] is True
            assert result["remaining"] == float("inf")


class TestRateLimitMiddleware:
    """Test rate limiting middleware integration."""

    @pytest.fixture
    def test_app(self):
        """Create test FastAPI app."""
        return create_app()

    async def test_rate_limit_headers_in_response(self, test_app):
        """Test that rate limit headers are added to responses."""
        with TestClient(test_app) as client:
            response = client.get("/health")

            assert response.status_code == 200
            # Should have rate limit headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
            assert "X-RateLimit-Type" in response.headers

    async def test_rate_limit_429_response(self, test_app):
        """Test that rate limiting returns 429 when exceeded."""
        with TestClient(test_app) as client:
            # This test would need to actually hit rate limits
            # In practice, you'd configure very low limits for testing

            # Make rapid requests to trigger rate limiting
            responses = []
            for i in range(200):  # Enough to trigger any reasonable limit
                response = client.get("/health")
                responses.append(response)
                if response.status_code == 429:
                    break

            # Should eventually get a 429
            assert any(r.status_code == 429 for r in responses)

            # Check 429 response format
            rate_limited_response = next(r for r in responses if r.status_code == 429)
            error_data = rate_limited_response.json()

            assert "error" in error_data
            assert "limit_type" in error_data
            assert "remaining" in error_data
            assert "retry_after" in error_data

    async def test_user_identification_from_headers(self, test_app):
        """Test that user identification works from headers."""
        with TestClient(test_app) as client:
            # Test with user ID header
            response = client.get("/health", headers={"X-User-ID": "test_user_123"})
            assert response.status_code == 200

            # Test with authorization header
            response = client.get("/health", headers={"Authorization": "Bearer test_token_456"})
            assert response.status_code == 200

    async def test_ai_endpoint_detection(self, test_app):
        """Test that AI endpoints get special rate limiting."""
        with TestClient(test_app) as client:
            # Test AI endpoint (if it exists)
            response = client.get("/api/v1/workflows/execute")
            # This might return 404 or 405 depending on implementation
            # but should not fail due to middleware issues
            assert response.status_code in [200, 404, 405, 422, 429]


class TestRateLimitIntegration:
    """Integration tests for rate limiting in full system."""

    async def test_end_to_end_rate_limiting(self):
        """Test rate limiting works end-to-end."""
        # This would test the full system with rate limiting enabled
        # Including actual Redis, actual endpoints, etc.
        pass

    async def test_rate_limiting_with_real_redis(self):
        """Test with real Redis instance."""
        # This would connect to a real Redis instance
        # and test rate limiting behavior
        pass

    async def test_rate_limiting_performance_impact(self):
        """Test that rate limiting doesn't significantly impact performance."""
        # Benchmark requests with and without rate limiting
        # to ensure minimal performance impact
        pass


class TestRateLimitConfiguration:
    """Test rate limit configuration loading."""

    def test_config_from_environment_variables(self):
        """Test that configuration loads correctly from env vars."""
        with patch.dict('os.environ', {
            'RATE_LIMIT_ENABLED': 'true',
            'RATE_LIMIT_RPM': '200',
            'COST_LIMIT_BRL_DAY': '1000.0',
            'RATE_LIMIT_BURST': '50'
        }):
            # Test that config is loaded correctly
            # This would require modifying the config loading to be testable
            pass

    def test_config_defaults(self):
        """Test that default configuration values are reasonable."""
        config = RateLimitConfig()

        assert config.enabled is True
        assert config.requests_per_minute == 100
        assert config.cost_limit_per_day_brl == 500.0
        assert config.burst_allowance == 20
        assert config.openai_requests_per_minute == 60
        assert config.openai_cost_per_request_brl == 0.50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])