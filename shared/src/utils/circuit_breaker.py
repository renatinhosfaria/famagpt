"""
Circuit Breaker e Retry utilities para o sistema FamaGPT
"""

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import TypeVar, Callable
import asyncio
import random
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Importar métricas se disponível
try:
    from .metrics import MetricsCollector
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("Metrics not available, continuing without metrics collection")

T = TypeVar('T')

class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass

class CircuitBreaker:
    """
    Circuit breaker pattern implementation com estados: closed, open, half_open
    """
    def __init__(self, failure_threshold=5, recovery_timeout=30, expected_exception=Exception, service_name="unknown", function_name="unknown"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
        self.service_name = service_name
        self.function_name = function_name
        
        # Registrar estado inicial nas métricas
        if METRICS_AVAILABLE:
            MetricsCollector.record_circuit_breaker_state(
                self.service_name, self.function_name, self.state
            )
    
    def call(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "open":
                if asyncio.get_event_loop().time() - self.last_failure_time > self.recovery_timeout:
                    self._change_state("half_open")
                    logger.info(f"Circuit breaker half-open for {func.__name__}")
                else:
                    raise CircuitBreakerError(f"Circuit breaker open for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                if self.state == "half_open":
                    self._change_state("closed")
                    self.failure_count = 0
                    logger.info(f"Circuit breaker closed for {func.__name__}")
                
                # Registrar sucesso
                if METRICS_AVAILABLE:
                    MetricsCollector.record_circuit_breaker_success(
                        self.service_name, self.function_name
                    )
                return result
            except self.expected_exception as e:
                self.failure_count += 1
                self.last_failure_time = asyncio.get_event_loop().time()
                
                # Registrar falha
                if METRICS_AVAILABLE:
                    MetricsCollector.record_circuit_breaker_failure(
                        self.service_name, self.function_name
                    )
                
                if self.failure_count >= self.failure_threshold:
                    self._change_state("open")
                    logger.error(f"Circuit breaker opened for {func.__name__}")
                raise e
        
        return wrapper
    
    def _change_state(self, new_state: str):
        """Alterar estado e registrar métricas"""
        old_state = self.state
        self.state = new_state
        
        if METRICS_AVAILABLE:
            MetricsCollector.record_circuit_breaker_state(
                self.service_name, self.function_name, new_state
            )
        
        logger.info(f"Circuit breaker {self.service_name}:{self.function_name} changed from {old_state} to {new_state}")

# Retry with exponential backoff and jitter
def resilient_call(
    stop_attempts=3,
    wait_min=2,
    wait_max=10,
    exceptions=(Exception,)
):
    """
    Decorator para chamadas resilientes com retry exponencial e jitter
    """
    def decorator(func):
        @retry(
            stop=stop_after_attempt(stop_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            retry=retry_if_exception_type(exceptions),
            before_sleep=lambda retry_state: logger.warning(
                f"Retrying {func.__name__} (attempt {retry_state.attempt_number})"
            )
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Add jitter
            if hasattr(wrapper, 'retry_count') and wrapper.retry_count > 0:
                await asyncio.sleep(random.uniform(0, 1))
            return await func(*args, **kwargs)
        return wrapper
    return decorator