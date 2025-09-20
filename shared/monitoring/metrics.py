"""
Sistema de métricas Prometheus centralizado para FamaGPT
"""

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time
import asyncio
from functools import wraps
from typing import Callable

# Create registry
registry = CollectorRegistry()

# Define metrics
messages_total = Counter(
    'famagpt_messages_total',
    'Total messages processed',
    ['service', 'status', 'message_type'],
    registry=registry
)

processing_duration = Histogram(
    'famagpt_processing_duration_seconds',
    'Processing duration in seconds',
    ['service', 'workflow', 'operation'],
    registry=registry,
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
)

active_conversations = Gauge(
    'famagpt_active_conversations',
    'Number of active conversations',
    ['service'],
    registry=registry
)

llm_tokens_used = Counter(
    'famagpt_llm_tokens_total',
    'Total LLM tokens used',
    ['service', 'model', 'token_type'],
    registry=registry
)

queue_depth = Gauge(
    'famagpt_queue_depth',
    'Current queue depth',
    ['queue_name'],
    registry=registry
)

error_total = Counter(
    'famagpt_errors_total',
    'Total errors',
    ['service', 'error_type', 'operation'],
    registry=registry
)

service_info = Info(
    'famagpt_service',
    'Service information',
    registry=registry
)

# Circuit breaker metrics (integração com sistema existente)
circuit_breaker_state_gauge = Gauge(
    'famagpt_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['service', 'function'],
    registry=registry
)

webhook_events = Counter(
    'famagpt_webhook_events_total',
    'Total webhook events received',
    ['instance_id', 'event_type', 'status'],
    registry=registry
)

memory_operations = Counter(
    'famagpt_memory_operations_total',
    'Memory operations performed',
    ['service', 'operation_type', 'status'],
    registry=registry
)

rag_queries = Counter(
    'famagpt_rag_queries_total',
    'RAG queries performed',
    ['service', 'query_type', 'status'],
    registry=registry
)

web_searches = Counter(
    'famagpt_web_searches_total',
    'Web searches performed',
    ['service', 'search_type', 'status'],
    registry=registry
)

transcription_requests = Counter(
    'famagpt_transcription_requests_total',
    'Transcription requests processed',
    ['service', 'audio_format', 'status'],
    registry=registry
)

# Decorator for timing functions
def track_duration(service: str, operation: str, workflow: str = "default"):
    """Decorator para rastrear duração de operações"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                processing_duration.labels(
                    service=service,
                    workflow=workflow,
                    operation=operation
                ).observe(time.time() - start_time)
                return result
            except Exception as e:
                error_total.labels(
                    service=service,
                    error_type=type(e).__name__,
                    operation=operation
                ).inc()
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                processing_duration.labels(
                    service=service,
                    workflow=workflow,
                    operation=operation
                ).observe(time.time() - start_time)
                return result
            except Exception as e:
                error_total.labels(
                    service=service,
                    error_type=type(e).__name__,
                    operation=operation
                ).inc()
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

def track_message_processing(service: str, status: str, message_type: str):
    """Rastrear processamento de mensagens"""
    messages_total.labels(
        service=service,
        status=status,
        message_type=message_type
    ).inc()

def track_llm_tokens(service: str, model: str, token_type: str, count: int):
    """Rastrear uso de tokens LLM"""
    llm_tokens_used.labels(
        service=service,
        model=model,
        token_type=token_type
    ).inc(count)

def set_queue_depth(queue_name: str, depth: int):
    """Definir profundidade da fila"""
    queue_depth.labels(queue_name=queue_name).set(depth)

def set_active_conversations(service: str, count: int):
    """Definir número de conversações ativas"""
    active_conversations.labels(service=service).set(count)

def track_webhook_event(instance_id: str, event_type: str, status: str):
    """Rastrear eventos de webhook"""
    webhook_events.labels(
        instance_id=instance_id,
        event_type=event_type,
        status=status
    ).inc()

def track_memory_operation(service: str, operation_type: str, status: str):
    """Rastrear operações de memória"""
    memory_operations.labels(
        service=service,
        operation_type=operation_type,
        status=status
    ).inc()

def track_rag_query(service: str, query_type: str, status: str):
    """Rastrear consultas RAG"""
    rag_queries.labels(
        service=service,
        query_type=query_type,
        status=status
    ).inc()

def track_web_search(service: str, search_type: str, status: str):
    """Rastrear pesquisas web"""
    web_searches.labels(
        service=service,
        search_type=search_type,
        status=status
    ).inc()

def track_transcription(service: str, audio_format: str, status: str):
    """Rastrear transcrições de áudio"""
    transcription_requests.labels(
        service=service,
        audio_format=audio_format,
        status=status
    ).inc()

def set_circuit_breaker_state(service: str, function: str, state: str):
    """Definir estado do circuit breaker"""
    state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, 0)
    circuit_breaker_state_gauge.labels(
        service=service,
        function=function
    ).set(state_value)

def set_service_info(name: str, version: str, environment: str):
    """Definir informações do serviço"""
    service_info.info({
        'name': name,
        'version': version,
        'environment': environment
    })

# FastAPI endpoint for metrics
async def metrics_endpoint():
    """Endpoint para exposição de métricas"""
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST
    )

# Export main functions
__all__ = [
    'metrics_endpoint',
    'track_duration',
    'track_message_processing',
    'track_llm_tokens',
    'set_queue_depth',
    'set_active_conversations',
    'track_webhook_event',
    'track_memory_operation',
    'track_rag_query',
    'track_web_search',
    'track_transcription',
    'set_circuit_breaker_state',
    'set_service_info',
    'messages_total',
    'processing_duration',
    'active_conversations',
    'llm_tokens_used',
    'queue_depth',
    'error_total',
    'service_info'
]