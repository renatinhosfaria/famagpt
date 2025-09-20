"""
Métricas Prometheus para observabilidade do sistema FamaGPT
"""

from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
from functools import wraps
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)

# Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Estado atual do circuit breaker (0=closed, 1=open, 2=half_open)',
    ['service', 'function']
)

circuit_breaker_failures = Counter(
    'circuit_breaker_failures_total',
    'Total de falhas do circuit breaker',
    ['service', 'function']
)

circuit_breaker_successes = Counter(
    'circuit_breaker_successes_total', 
    'Total de sucessos do circuit breaker',
    ['service', 'function']
)

# Message Processing Metrics
message_processing_duration = Histogram(
    'message_processing_duration_seconds',
    'Tempo de processamento de mensagens',
    ['message_type', 'status']
)

message_processing_total = Counter(
    'message_processing_total',
    'Total de mensagens processadas',
    ['message_type', 'status', 'instance_id']
)

# Lock Metrics
conversation_lock_duration = Histogram(
    'conversation_lock_duration_seconds',
    'Tempo de aquisição de locks de conversação',
    ['message_type']
)

conversation_lock_failures = Counter(
    'conversation_lock_failures_total',
    'Falhas na aquisição de locks de conversação',
    ['message_type']
)

# Idempotency Metrics
duplicate_messages_total = Counter(
    'duplicate_messages_total',
    'Total de mensagens duplicadas detectadas',
    ['instance_id']
)

out_of_order_messages_total = Counter(
    'out_of_order_messages_total', 
    'Total de mensagens fora de ordem detectadas',
    ['instance_id']
)

class MetricsCollector:
    """Coletor centralizado de métricas"""
    
    @staticmethod
    def record_circuit_breaker_state(service: str, function: str, state: str):
        """Registrar estado do circuit breaker"""
        state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, 0)
        circuit_breaker_state.labels(service=service, function=function).set(state_value)
        logger.info(f"Circuit breaker {service}:{function} state changed to {state}")
    
    @staticmethod
    def record_circuit_breaker_failure(service: str, function: str):
        """Registrar falha do circuit breaker"""
        circuit_breaker_failures.labels(service=service, function=function).inc()
    
    @staticmethod
    def record_circuit_breaker_success(service: str, function: str):
        """Registrar sucesso do circuit breaker"""
        circuit_breaker_successes.labels(service=service, function=function).inc()
    
    @staticmethod
    def record_duplicate_message(instance_id: str):
        """Registrar mensagem duplicada"""
        duplicate_messages_total.labels(instance_id=instance_id).inc()
    
    @staticmethod
    def record_out_of_order_message(instance_id: str):
        """Registrar mensagem fora de ordem"""
        out_of_order_messages_total.labels(instance_id=instance_id).inc()
    
    @staticmethod
    def record_lock_failure(message_type: str):
        """Registrar falha na aquisição de lock"""
        conversation_lock_failures.labels(message_type=message_type).inc()

def timed_metric(metric: Histogram, labels: Optional[dict] = None):
    """Decorator para medir tempo de execução de funções"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                labels_dict = labels or {}
                labels_dict["status"] = status
                metric.labels(**labels_dict).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                labels_dict = labels or {}
                labels_dict["status"] = status
                metric.labels(**labels_dict).observe(duration)
        
        # Return appropriate wrapper based on function type
        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

def start_metrics_server(port: int = 8000):
    """Iniciar servidor de métricas Prometheus"""
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")

# Exportar métricas principais
__all__ = [
    'MetricsCollector',
    'circuit_breaker_state',
    'message_processing_duration',
    'message_processing_total',
    'conversation_lock_duration',
    'timed_metric',
    'start_metrics_server'
]