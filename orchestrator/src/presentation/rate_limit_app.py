"""
Rate limiting enabled FastAPI application wrapper.
"""
from .main import create_app
from ..infrastructure.rate_limiter import RateLimitMiddleware


def create_rate_limited_app():
    """Create FastAPI app with rate limiting middleware."""
    base_app = create_app()

    # We need to add rate limiting after the app is created
    # but before it starts handling requests
    original_startup = base_app.router.lifespan_context

    async def enhanced_lifespan(app):
        async with original_startup(app) as state:
            # Get the rate limiter from app state
            if "rate_limiter" in state:
                # Add rate limiting middleware
                rate_limit_middleware = RateLimitMiddleware(app, state["rate_limiter"])
                app.user_middleware.insert(0, (rate_limit_middleware, {}))

            yield state

    base_app.router.lifespan_context = enhanced_lifespan
    return base_app


# Create the rate-limited app instance
app = create_rate_limited_app()