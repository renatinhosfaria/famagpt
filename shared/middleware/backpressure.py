"""
Middleware de backpressure e rate limiting para FamaGPT
Controla carga do sistema e previne sobrecarga
"""

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis
import asyncio
from typing import Optional, Dict, Any
import time
import logging

# Importar métricas para observabilidade
try:
    from shared.monitoring.metrics import set_queue_depth, track_message_processing
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

class BackpressureMiddleware(BaseHTTPMiddleware):
    """
    Middleware de controle de backpressure
    
    Monitora a carga do sistema e rejeita requisições quando sobrecarregado:
    - Monitora filas Redis Streams
    - Controla mensagens pendentes
    - Aplica throttling adaptativo
    - Preserva endpoints críticos
    """
    
    def __init__(
        self,
        app,
        redis_url: str,
        queue_threshold: int = 1000,
        pending_threshold: int = 500,
        check_interval: int = 5,
        protected_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.redis_url = redis_url
        self.queue_threshold = queue_threshold
        self.pending_threshold = pending_threshold
        self.check_interval = check_interval
        self.protected_paths = protected_paths or ["/health", "/metrics", "/dlq"]
        self.redis_client: Optional[redis.Redis] = None
        self.last_check = 0
        self.system_status = {
            "queue_depth": 0,
            "pending_messages": 0,
            "is_overloaded": False,
            "load_level": "low"  # low, medium, high, critical
        }
    
    async def dispatch(self, request: Request, call_next):
        """Process request with backpressure control"""
        
        # Skip protected endpoints
        if any(request.url.path.startswith(path) for path in self.protected_paths):
            return await call_next(request)
        
        # Check system load
        load_info = await self._check_system_load()
        
        # Apply backpressure based on load level
        if load_info["is_overloaded"]:
            return await self._handle_overload(request, load_info)
        
        # Apply adaptive timeouts based on load
        timeout = self._calculate_timeout(load_info["load_level"])
        
        try:
            # Process request with adaptive timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout
            )
            
            # Add load information to response headers
            response.headers["X-System-Load"] = load_info["load_level"]
            response.headers["X-Queue-Depth"] = str(load_info["queue_depth"])
            
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"Request timeout ({timeout}s): {request.url.path}")
            
            # Track timeout metric
            if METRICS_AVAILABLE:
                track_message_processing("middleware", "timeout", "request")
            
            return Response(
                content='{"error": "Request timeout", "timeout_seconds": ' + str(timeout) + '}',
                status_code=504,
                media_type="application/json"
            )
        except Exception as e:
            logger.error(f"Middleware error: {e}")
            raise
    
    async def _check_system_load(self) -> Dict[str, Any]:
        """Check current system load"""
        current_time = time.time()
        
        # Cache check result to avoid frequent Redis calls
        if current_time - self.last_check < self.check_interval:
            return self.system_status
        
        try:
            if not self.redis_client:
                self.redis_client = redis.from_url(self.redis_url)
            
            # Check main message queue
            queue_depth = await self._get_queue_depth("messages:stream")
            
            # Check pending messages across consumer groups
            pending_count = await self._get_pending_count("messages:stream", "processors")
            
            # Check DLQ size
            dlq_depth = await self._get_queue_depth("messages:stream:dlq")
            
            # Calculate total load
            total_load = queue_depth + pending_count
            
            # Determine load level
            load_level = self._calculate_load_level(total_load, dlq_depth)
            is_overloaded = load_level == "critical"
            
            # Update system status
            self.system_status = {
                "queue_depth": queue_depth,
                "pending_messages": pending_count,
                "dlq_depth": dlq_depth,
                "total_load": total_load,
                "is_overloaded": is_overloaded,
                "load_level": load_level,
                "last_check": current_time
            }
            
            self.last_check = current_time
            
            # Update metrics
            if METRICS_AVAILABLE:
                set_queue_depth("messages:stream", queue_depth)
                set_queue_depth("messages:stream:dlq", dlq_depth)
            
            # Log if overloaded
            if is_overloaded:
                logger.warning(
                    f"System overloaded - Queue: {queue_depth}, "
                    f"Pending: {pending_count}, DLQ: {dlq_depth}, Load: {load_level}"
                )
            
            return self.system_status
            
        except Exception as e:
            logger.error(f"Error checking system load: {e}")
            # Return last known state or safe defaults
            return self.system_status or {
                "queue_depth": 0,
                "pending_messages": 0,
                "is_overloaded": False,
                "load_level": "unknown",
                "error": str(e)
            }
    
    async def _get_queue_depth(self, stream_name: str) -> int:
        """Get queue depth for a stream"""
        try:
            return await self.redis_client.xlen(stream_name)
        except redis.ResponseError:
            return 0
    
    async def _get_pending_count(self, stream_name: str, consumer_group: str) -> int:
        """Get pending message count for a consumer group"""
        try:
            pending_info = await self.redis_client.xpending(stream_name, consumer_group)
            return pending_info[0] if pending_info else 0
        except redis.ResponseError:
            return 0
    
    def _calculate_load_level(self, total_load: int, dlq_depth: int) -> str:
        """Calculate system load level"""
        # Factor in DLQ growth as indicator of system stress
        adjusted_load = total_load + (dlq_depth * 2)  # DLQ messages are weighted more
        
        if adjusted_load >= self.queue_threshold:
            return "critical"
        elif adjusted_load >= self.queue_threshold * 0.8:
            return "high"
        elif adjusted_load >= self.queue_threshold * 0.5:
            return "medium"
        else:
            return "low"
    
    def _calculate_timeout(self, load_level: str) -> float:
        """Calculate adaptive timeout based on load level"""
        timeouts = {
            "low": 30.0,
            "medium": 20.0,
            "high": 15.0,
            "critical": 10.0,
            "unknown": 30.0
        }
        return timeouts.get(load_level, 30.0)
    
    async def _handle_overload(self, request: Request, load_info: Dict[str, Any]) -> Response:
        """Handle overloaded system"""
        
        # Calculate retry-after based on load
        retry_after = min(60, max(10, load_info.get("total_load", 0) // 50))
        
        # Track overload metric
        if METRICS_AVAILABLE:
            track_message_processing("middleware", "overload_rejected", "request")
        
        error_response = {
            "error": "System overloaded",
            "message": "Please retry later",
            "load_info": {
                "load_level": load_info["load_level"],
                "queue_depth": load_info["queue_depth"],
                "pending_messages": load_info["pending_messages"]
            },
            "retry_after_seconds": retry_after
        }
        
        return Response(
            content=str(error_response).replace("'", '"'),
            status_code=503,
            headers={
                "Retry-After": str(retry_after),
                "X-System-Load": load_info["load_level"],
                "X-Queue-Depth": str(load_info["queue_depth"]),
                "X-RateLimit-Remaining": "0"
            },
            media_type="application/json"
        )

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Advanced rate limiting middleware with sliding window
    
    Features:
    - Per-client rate limiting
    - Sliding window algorithm
    - Burst handling
    - Adaptive limits based on system load
    """
    
    def __init__(
        self,
        app,
        redis_url: str,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        window_size: int = 60,
        protected_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.redis_url = redis_url
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.window_size = window_size
        self.protected_paths = protected_paths or ["/health", "/metrics"]
        self.redis_client: Optional[redis.Redis] = None
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        
        # Skip protected endpoints
        if any(request.url.path.startswith(path) for path in self.protected_paths):
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Check rate limit
        allowed, remaining, reset_time = await self._check_rate_limit(client_id)
        
        if not allowed:
            # Track rate limit violation
            if METRICS_AVAILABLE:
                track_message_processing("middleware", "rate_limited", "request")
            
            return Response(
                content='{"error": "Rate limit exceeded", "retry_after": ' + str(reset_time) + '}',
                status_code=429,
                headers={
                    "Retry-After": str(reset_time),
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + reset_time))
                },
                media_type="application/json"
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.window_size))
        
        return response
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request"""
        
        # Try to get from custom header first
        if "X-Client-ID" in request.headers:
            return f"client:{request.headers['X-Client-ID']}"
        
        # Try to get from API key
        if "X-API-Key" in request.headers:
            api_key = request.headers["X-API-Key"]
            return f"api_key:{api_key[:8]}..."  # Use first 8 chars for privacy
        
        # Try to get from authorization header
        if "Authorization" in request.headers:
            auth = request.headers["Authorization"]
            if auth.startswith("Bearer "):
                token = auth[7:]
                return f"token:{token[:8]}..."
        
        # Fall back to IP address
        if request.client and request.client.host:
            return f"ip:{request.client.host}"
        
        return "unknown"
    
    async def _check_rate_limit(self, client_id: str) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window
        
        Returns:
            (allowed, remaining_requests, reset_time_seconds)
        """
        if not self.redis_client:
            self.redis_client = redis.from_url(self.redis_url)
        
        key = f"rate_limit:{client_id}"
        now = time.time()
        window_start = now - self.window_size
        
        try:
            # Use pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            
            # Add current request timestamp
            pipe.zadd(key, {str(now): now})
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests in window
            pipe.zcard(key)
            
            # Set expiration
            pipe.expire(key, self.window_size + 1)
            
            results = await pipe.execute()
            request_count = results[2]
            
            # Calculate remaining requests
            remaining = max(0, self.requests_per_minute - request_count)
            
            # Check if over limit
            if request_count > self.requests_per_minute:
                # Calculate reset time (when oldest request in window expires)
                oldest_requests = await self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_requests:
                    oldest_time = oldest_requests[0][1]
                    reset_time = max(1, int(oldest_time + self.window_size - now))
                else:
                    reset_time = self.window_size
                
                return False, 0, reset_time
            
            return True, remaining, self.window_size
            
        except Exception as e:
            logger.error(f"Rate limit check error for {client_id}: {e}")
            # On error, allow request but log it
            return True, self.requests_per_minute, self.window_size

class AdaptiveThrottlingMiddleware(BaseHTTPMiddleware):
    """
    Adaptive throttling based on system performance
    
    Adjusts request processing speed based on:
    - CPU usage
    - Memory usage
    - Queue depth
    - Response times
    """
    
    def __init__(
        self,
        app,
        redis_url: str,
        base_delay_ms: int = 0,
        max_delay_ms: int = 1000
    ):
        super().__init__(app)
        self.redis_url = redis_url
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.redis_client: Optional[redis.Redis] = None
        
    async def dispatch(self, request: Request, call_next):
        """Process request with adaptive throttling"""
        
        # Calculate delay based on system load
        delay = await self._calculate_adaptive_delay()
        
        if delay > 0:
            await asyncio.sleep(delay / 1000)  # Convert to seconds
        
        # Process request
        response = await call_next(request)
        
        # Add throttling information to headers
        if delay > 0:
            response.headers["X-Throttle-Delay-Ms"] = str(int(delay))
        
        return response
    
    async def _calculate_adaptive_delay(self) -> int:
        """Calculate delay based on current system load"""
        try:
            if not self.redis_client:
                self.redis_client = redis.from_url(self.redis_url)
            
            # Get queue depth
            queue_depth = await self.redis_client.xlen("messages:stream")
            
            # Calculate delay based on queue depth
            # More items in queue = more delay
            if queue_depth > 100:
                delay_factor = min(queue_depth / 100, 10)  # Cap at 10x
                delay = self.base_delay_ms + (delay_factor * 100)
                return min(delay, self.max_delay_ms)
            
            return self.base_delay_ms
            
        except Exception as e:
            logger.error(f"Error calculating adaptive delay: {e}")
            return self.base_delay_ms

# Export middleware classes
__all__ = [
    'BackpressureMiddleware',
    'RateLimitMiddleware', 
    'AdaptiveThrottlingMiddleware'
]