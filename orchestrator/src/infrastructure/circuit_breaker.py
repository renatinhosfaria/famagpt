"""
Circuit breaker implementation for external API resilience.
Provides automatic failure detection and recovery for OpenAI, Evolution API, etc.
"""
import asyncio
import time
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass
from enum import Enum
import httpx

from aiobreaker import CircuitBreaker
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


class ServiceType(Enum):
    """Types of external services."""
    OPENAI = "openai"
    EVOLUTION_API = "evolution"
    LANGSMITH = "langsmith"
    INTERNAL_SERVICE = "internal"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes to close from half-open
    timeout_seconds: int = 60           # Time to wait before half-open
    expected_exception: type = Exception

    # Retry configuration
    max_retry_attempts: int = 3
    retry_wait_base: float = 1.0        # Base seconds for exponential backoff
    retry_wait_max: float = 60.0        # Max seconds to wait


class EnhancedCircuitBreaker:
    """Enhanced circuit breaker with retry logic and observability."""

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config

        # Create the underlying circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.failure_threshold,
            success_threshold=config.success_threshold,
            timeout=config.timeout_seconds,
            expected_exception=config.expected_exception,
            name=name
        )

        # State tracking
        self._last_failure_time: Optional[float] = None
        self._failure_count = 0
        self._success_count = 0

        # Register event listeners
        self.circuit_breaker.add_listener(self._on_circuit_open)
        self.circuit_breaker.add_listener(self._on_circuit_close)
        self.circuit_breaker.add_listener(self._on_circuit_half_open)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call a function with circuit breaker protection and retry logic.
        """
        return await self._call_with_retry(func, *args, **kwargs)

    @retry(
        stop=stop_after_attempt(3),  # Will be overridden by instance config
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError))
    )
    async def _call_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Internal method with retry decoration."""
        # Update retry configuration dynamically
        self._call_with_retry.retry.stop = stop_after_attempt(self.config.max_retry_attempts)
        self._call_with_retry.retry.wait = wait_exponential(
            multiplier=self.config.retry_wait_base,
            max=self.config.retry_wait_max
        )

        start_time = time.time()

        try:
            # Call through circuit breaker
            if asyncio.iscoroutinefunction(func):
                result = await self.circuit_breaker.call(func, *args, **kwargs)
            else:
                result = self.circuit_breaker.call(func, *args, **kwargs)

            # Record success
            duration = time.time() - start_time
            self._record_success(duration)

            return result

        except Exception as e:
            # Record failure
            duration = time.time() - start_time
            self._record_failure(e, duration)

            logger.warning(
                "Circuit breaker call failed",
                name=self.name,
                error=str(e),
                duration=duration,
                state=self.circuit_breaker.current_state
            )

            raise

    def _record_success(self, duration: float):
        """Record successful call."""
        self._success_count += 1

        logger.debug(
            "Circuit breaker call succeeded",
            name=self.name,
            duration=duration,
            success_count=self._success_count,
            state=self.circuit_breaker.current_state
        )

        # Import here to avoid circular imports
        try:
            from .observability import get_observability
            obs = get_observability()
            if obs:
                obs.record_request("circuit_breaker", self.name, 200, duration)
        except ImportError:
            pass

    def _record_failure(self, error: Exception, duration: float):
        """Record failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        logger.error(
            "Circuit breaker call failed",
            name=self.name,
            error=str(error),
            error_type=type(error).__name__,
            duration=duration,
            failure_count=self._failure_count,
            state=self.circuit_breaker.current_state
        )

        # Import here to avoid circular imports
        try:
            from .observability import get_observability
            obs = get_observability()
            if obs:
                obs.record_request("circuit_breaker", self.name, 500, duration)
        except ImportError:
            pass

    def _on_circuit_open(self, circuit_breaker):
        """Handle circuit breaker opening."""
        logger.warning(
            "Circuit breaker opened",
            name=self.name,
            failure_threshold=self.config.failure_threshold,
            failure_count=self._failure_count
        )

    def _on_circuit_close(self, circuit_breaker):
        """Handle circuit breaker closing."""
        logger.info(
            "Circuit breaker closed",
            name=self.name,
            success_count=self._success_count
        )

        # Reset counters
        self._failure_count = 0
        self._success_count = 0

    def _on_circuit_half_open(self, circuit_breaker):
        """Handle circuit breaker half-open state."""
        logger.info(
            "Circuit breaker half-open",
            name=self.name,
            timeout_seconds=self.config.timeout_seconds
        )

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        return self.circuit_breaker.current_state

    @property
    def is_available(self) -> bool:
        """Check if the circuit breaker allows calls."""
        return self.state in ["closed", "half-open"]

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
            "is_available": self.is_available,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds
            }
        }


class CircuitBreakerManager:
    """Manages circuit breakers for different services."""

    def __init__(self):
        self._circuit_breakers: Dict[str, EnhancedCircuitBreaker] = {}
        self._service_configs = {
            ServiceType.OPENAI: CircuitBreakerConfig(
                failure_threshold=3,        # OpenAI is critical, fail fast
                success_threshold=2,
                timeout_seconds=60,
                expected_exception=(httpx.HTTPError, ConnectionError),
                max_retry_attempts=2,       # Limited retries for cost control
                retry_wait_base=2.0
            ),
            ServiceType.EVOLUTION_API: CircuitBreakerConfig(
                failure_threshold=5,        # WhatsApp can be more tolerant
                success_threshold=3,
                timeout_seconds=30,
                expected_exception=(httpx.HTTPError, ConnectionError),
                max_retry_attempts=3,
                retry_wait_base=1.0
            ),
            ServiceType.LANGSMITH: CircuitBreakerConfig(
                failure_threshold=10,       # Observability failures shouldn't break system
                success_threshold=5,
                timeout_seconds=120,
                expected_exception=(httpx.HTTPError, ConnectionError),
                max_retry_attempts=1,       # Don't retry observability too much
                retry_wait_base=0.5
            ),
            ServiceType.INTERNAL_SERVICE: CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                timeout_seconds=30,
                expected_exception=(httpx.HTTPError, ConnectionError),
                max_retry_attempts=3,
                retry_wait_base=1.5
            )
        }

    def get_circuit_breaker(self, service_name: str, service_type: ServiceType) -> EnhancedCircuitBreaker:
        """Get or create a circuit breaker for a service."""
        if service_name not in self._circuit_breakers:
            config = self._service_configs.get(service_type, CircuitBreakerConfig())
            self._circuit_breakers[service_name] = EnhancedCircuitBreaker(service_name, config)

            logger.info(
                "Created circuit breaker",
                service_name=service_name,
                service_type=service_type.value,
                config=config.__dict__
            )

        return self._circuit_breakers[service_name]

    async def call_with_circuit_breaker(
        self,
        service_name: str,
        service_type: ServiceType,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Call a function with circuit breaker protection."""
        circuit_breaker = self.get_circuit_breaker(service_name, service_type)
        return await circuit_breaker.call(func, *args, **kwargs)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {
            name: cb.get_stats()
            for name, cb in self._circuit_breakers.items()
        }

    def reset_circuit_breaker(self, service_name: str):
        """Reset a specific circuit breaker."""
        if service_name in self._circuit_breakers:
            # Remove and recreate
            old_cb = self._circuit_breakers[service_name]
            service_type = self._get_service_type_from_name(service_name)
            config = self._service_configs.get(service_type, CircuitBreakerConfig())

            self._circuit_breakers[service_name] = EnhancedCircuitBreaker(service_name, config)

            logger.info(
                "Reset circuit breaker",
                service_name=service_name,
                old_state=old_cb.state
            )

    def _get_service_type_from_name(self, service_name: str) -> ServiceType:
        """Infer service type from service name."""
        name_lower = service_name.lower()

        if "openai" in name_lower or "gpt" in name_lower:
            return ServiceType.OPENAI
        elif "evolution" in name_lower or "whatsapp" in name_lower:
            return ServiceType.EVOLUTION_API
        elif "langsmith" in name_lower or "langchain" in name_lower:
            return ServiceType.LANGSMITH
        else:
            return ServiceType.INTERNAL_SERVICE


# Global circuit breaker manager
_circuit_breaker_manager: Optional[CircuitBreakerManager] = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get the global circuit breaker manager."""
    global _circuit_breaker_manager

    if _circuit_breaker_manager is None:
        _circuit_breaker_manager = CircuitBreakerManager()

    return _circuit_breaker_manager


# Convenience decorators
def with_circuit_breaker(service_name: str, service_type: ServiceType):
    """Decorator to add circuit breaker protection to a function."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            manager = get_circuit_breaker_manager()
            return await manager.call_with_circuit_breaker(
                service_name, service_type, func, *args, **kwargs
            )
        return wrapper
    return decorator


# Common circuit breakers for FamaGPT services
def openai_circuit_breaker(service_name: str = "openai"):
    """Circuit breaker specifically for OpenAI API calls."""
    return with_circuit_breaker(service_name, ServiceType.OPENAI)


def evolution_circuit_breaker(service_name: str = "evolution_api"):
    """Circuit breaker specifically for Evolution API calls."""
    return with_circuit_breaker(service_name, ServiceType.EVOLUTION_API)


def internal_service_circuit_breaker(service_name: str):
    """Circuit breaker for internal FamaGPT services."""
    return with_circuit_breaker(service_name, ServiceType.INTERNAL_SERVICE)