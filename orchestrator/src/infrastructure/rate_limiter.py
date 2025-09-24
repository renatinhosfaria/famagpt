"""
Rate limiting implementation for FamaGPT Orchestrator.
Provides cost protection and request throttling.
"""
import asyncio
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimitType(Enum):
    """Rate limit types for different operations."""
    GLOBAL = "global"
    USER = "user"
    COST_PROTECTION = "cost"
    OPENAI_API = "openai"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 100
    cost_limit_per_day_brl: float = 500.0
    burst_allowance: int = 20
    enabled: bool = True

    # OpenAI specific limits
    openai_requests_per_minute: int = 60
    openai_cost_per_request_brl: float = 0.50  # Estimated average


class RateLimiter:
    """Redis-based rate limiter with cost protection."""

    def __init__(self, redis_client: aioredis.Redis, config: RateLimitConfig):
        self.redis = redis_client
        self.config = config

    async def check_rate_limit(
        self,
        key: str,
        limit_type: RateLimitType,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if request is within rate limits.

        Returns:
            Dict with status, remaining, reset_time
        """
        if not self.config.enabled:
            return {
                "allowed": True,
                "remaining": float("inf"),
                "reset_time": 0,
                "limit_type": limit_type.value
            }

        current_time = int(time.time())

        if limit_type == RateLimitType.GLOBAL:
            return await self._check_global_limit(key, current_time)
        elif limit_type == RateLimitType.USER:
            return await self._check_user_limit(key, user_id, current_time)
        elif limit_type == RateLimitType.COST_PROTECTION:
            return await self._check_cost_limit(key, current_time)
        elif limit_type == RateLimitType.OPENAI_API:
            return await self._check_openai_limit(key, current_time)

        return {"allowed": True, "remaining": 0, "reset_time": 0}

    async def _check_global_limit(self, key: str, current_time: int) -> Dict[str, Any]:
        """Check global rate limit (requests per minute)."""
        window_start = current_time - (current_time % 60)  # Start of current minute
        redis_key = f"rate_limit:global:{key}:{window_start}"

        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, 60)  # Expire after 1 minute
        results = await pipe.execute()

        current_count = results[0]
        limit = self.config.requests_per_minute + self.config.burst_allowance

        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_time = window_start + 60

        logger.info(
            "Global rate limit check",
            key=key,
            current_count=current_count,
            limit=limit,
            allowed=allowed,
            remaining=remaining
        )

        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "limit_type": "global",
            "current_count": current_count
        }

    async def _check_user_limit(self, key: str, user_id: str, current_time: int) -> Dict[str, Any]:
        """Check per-user rate limit."""
        if not user_id:
            # Fallback to global limit if no user ID
            return await self._check_global_limit(key, current_time)

        window_start = current_time - (current_time % 60)
        redis_key = f"rate_limit:user:{user_id}:{window_start}"

        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, 60)
        results = await pipe.execute()

        current_count = results[0]
        # Per-user limit is typically lower than global
        limit = min(self.config.requests_per_minute // 4, 25) + 5  # Burst allowance

        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_time = window_start + 60

        logger.info(
            "User rate limit check",
            key=key,
            user_id=user_id,
            current_count=current_count,
            limit=limit,
            allowed=allowed
        )

        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "limit_type": "user",
            "user_id": user_id
        }

    async def _check_cost_limit(self, key: str, current_time: int) -> Dict[str, Any]:
        """Check daily cost protection limit."""
        # Use daily window (86400 seconds)
        window_start = current_time - (current_time % 86400)  # Start of current day
        redis_key = f"rate_limit:cost:{key}:{window_start}"

        # Get current cost from Redis
        current_cost_str = await self.redis.get(redis_key)
        current_cost = float(current_cost_str) if current_cost_str else 0.0

        # Add estimated cost for this request
        estimated_cost = self.config.openai_cost_per_request_brl
        new_cost = current_cost + estimated_cost

        allowed = new_cost <= self.config.cost_limit_per_day_brl
        remaining_cost = max(0, self.config.cost_limit_per_day_brl - new_cost)
        reset_time = window_start + 86400  # Next day

        if allowed:
            # Update cost counter
            await self.redis.setex(redis_key, 86400, str(new_cost))

        logger.info(
            "Cost protection check",
            key=key,
            current_cost_brl=current_cost,
            estimated_cost_brl=estimated_cost,
            new_cost_brl=new_cost,
            limit_brl=self.config.cost_limit_per_day_brl,
            allowed=allowed,
            remaining_cost_brl=remaining_cost
        )

        return {
            "allowed": allowed,
            "remaining": remaining_cost,
            "reset_time": reset_time,
            "limit_type": "cost_protection",
            "current_cost_brl": current_cost,
            "estimated_cost_brl": estimated_cost,
            "limit_brl": self.config.cost_limit_per_day_brl
        }

    async def _check_openai_limit(self, key: str, current_time: int) -> Dict[str, Any]:
        """Check OpenAI API specific rate limit."""
        window_start = current_time - (current_time % 60)
        redis_key = f"rate_limit:openai:{key}:{window_start}"

        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, 60)
        results = await pipe.execute()

        current_count = results[0]
        limit = self.config.openai_requests_per_minute

        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_time = window_start + 60

        logger.info(
            "OpenAI API rate limit check",
            key=key,
            current_count=current_count,
            limit=limit,
            allowed=allowed
        )

        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "limit_type": "openai_api"
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(self, app, rate_limiter: RateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to requests."""
        # Extract user identification
        user_id = self._extract_user_id(request)
        client_ip = self._get_client_ip(request)

        # Create rate limit key
        key = f"{client_ip}:{user_id}" if user_id else client_ip

        # Check multiple rate limits
        checks = [
            ("global", RateLimitType.GLOBAL),
            ("cost", RateLimitType.COST_PROTECTION)
        ]

        if user_id:
            checks.append(("user", RateLimitType.USER))

        # Apply OpenAI specific limits for certain endpoints
        if self._is_ai_endpoint(request):
            checks.append(("openai", RateLimitType.OPENAI_API))

        for check_name, limit_type in checks:
            result = await self.rate_limiter.check_rate_limit(
                key=key,
                limit_type=limit_type,
                user_id=user_id
            )

            if not result.get("allowed", True):
                logger.warning(
                    "Rate limit exceeded",
                    check_type=check_name,
                    key=key,
                    user_id=user_id,
                    path=request.url.path,
                    result=result
                )

                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit_type": result.get("limit_type"),
                        "remaining": result.get("remaining"),
                        "reset_time": result.get("reset_time"),
                        "retry_after": max(1, result.get("reset_time", 0) - int(time.time()))
                    }
                )

        # Add rate limit headers to response
        response = await call_next(request)

        # Add headers for the most restrictive limit
        final_check = await self.rate_limiter.check_rate_limit(
            key=key,
            limit_type=RateLimitType.GLOBAL,
            user_id=user_id
        )

        response.headers["X-RateLimit-Remaining"] = str(final_check.get("remaining", 0))
        response.headers["X-RateLimit-Reset"] = str(final_check.get("reset_time", 0))
        response.headers["X-RateLimit-Type"] = final_check.get("limit_type", "global")

        return response

    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request."""
        # Try multiple sources for user identification

        # 1. Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # Could decode JWT token here
            return auth_header[7:20]  # Use part of token as user ID

        # 2. Query parameter
        user_id = request.query_params.get("user_id")
        if user_id:
            return user_id

        # 3. Header
        user_id = request.headers.get("x-user-id")
        if user_id:
            return user_id

        return None

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Try X-Forwarded-For first (for proxy setups)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Try X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback to direct client
        return getattr(request.client, "host", "unknown")

    def _is_ai_endpoint(self, request: Request) -> bool:
        """Check if this is an AI/LLM endpoint that needs special limits."""
        ai_paths = [
            "/api/v1/workflows/execute",
            "/api/v1/orchestration/process",
            "/api/v1/agents/chat"
        ]

        return any(request.url.path.startswith(path) for path in ai_paths)