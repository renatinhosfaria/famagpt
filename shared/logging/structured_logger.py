"""
Sistema de logs estruturados com correlation IDs para FamaGPT
"""

import logging
import json
import sys
from datetime import datetime
from contextvars import ContextVar
from typing import Any, Dict, Optional
import traceback
import uuid

# Context variables for correlation
trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar('span_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
conversation_id_var: ContextVar[Optional[str]] = ContextVar('conversation_id', default=None)
wa_message_id_var: ContextVar[Optional[str]] = ContextVar('wa_message_id', default=None)
instance_id_var: ContextVar[Optional[str]] = ContextVar('instance_id', default=None)

class StructuredFormatter(logging.Formatter):
    """Formatador JSON para logs estruturados"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'service': record.name.split('.')[0],
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add correlation IDs
        if trace_id := trace_id_var.get():
            log_data['trace_id'] = trace_id
        if span_id := span_id_var.get():
            log_data['span_id'] = span_id
        if user_id := user_id_var.get():
            log_data['user_id'] = user_id
        if conversation_id := conversation_id_var.get():
            log_data['conversation_id'] = conversation_id
        if wa_message_id := wa_message_id_var.get():
            log_data['wa_message_id'] = wa_message_id
        if instance_id := instance_id_var.get():
            log_data['instance_id'] = instance_id
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields') and record.extra_fields:
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': ''.join(traceback.format_exception(*record.exc_info))
            }
        
        return json.dumps(log_data, ensure_ascii=False)

class CorrelatedLogger:
    """Logger com contexto de correlação"""
    
    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        
        # Remove handlers existentes para evitar duplicatas
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Adicionar handler estruturado
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
        
        # Configurar nível
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        
        # Evitar propagação para loggers pais
        self.logger.propagate = False
    
    def with_context(
        self,
        trace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        wa_message_id: Optional[str] = None,
        instance_id: Optional[str] = None
    ) -> 'CorrelatedLogger':
        """Criar logger com contexto de correlação"""
        if trace_id:
            trace_id_var.set(trace_id)
        if user_id:
            user_id_var.set(user_id)
        if conversation_id:
            conversation_id_var.set(conversation_id)
        if wa_message_id:
            wa_message_id_var.set(wa_message_id)
        if instance_id:
            instance_id_var.set(instance_id)
        return self
    
    def info(self, message: str, **kwargs):
        """Log info com campos extras"""
        self.logger.info(message, extra={'extra_fields': kwargs})
    
    def warning(self, message: str, **kwargs):
        """Log warning com campos extras"""
        self.logger.warning(message, extra={'extra_fields': kwargs})
    
    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error com campos extras"""
        self.logger.error(message, exc_info=exc_info, extra={'extra_fields': kwargs})
    
    def debug(self, message: str, **kwargs):
        """Log debug com campos extras"""
        self.logger.debug(message, extra={'extra_fields': kwargs})
    
    def critical(self, message: str, exc_info: bool = False, **kwargs):
        """Log critical com campos extras"""
        self.logger.critical(message, exc_info=exc_info, extra={'extra_fields': kwargs})

def get_logger(name: str, level: str = "INFO") -> CorrelatedLogger:
    """Factory para criar loggers correlacionados"""
    return CorrelatedLogger(name, level)

# Middleware para FastAPI
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware para injetar correlation IDs nas requisições"""
    
    async def dispatch(self, request: Request, call_next):
        # Extract or generate trace ID
        trace_id = request.headers.get('X-Trace-ID') or str(uuid.uuid4())
        trace_id_var.set(trace_id)
        
        # Generate span ID
        span_id = str(uuid.uuid4())[:8]
        span_id_var.set(span_id)
        
        # Extract user context from headers if available
        if user_id := request.headers.get('X-User-ID'):
            user_id_var.set(user_id)
        
        if conversation_id := request.headers.get('X-Conversation-ID'):
            conversation_id_var.set(conversation_id)
        
        # Process request
        response = await call_next(request)
        
        # Add trace ID to response
        if isinstance(response, Response):
            response.headers['X-Trace-ID'] = trace_id
            response.headers['X-Span-ID'] = span_id
        
        return response

def extract_context_from_webhook_data(data: Dict[str, Any]) -> Dict[str, str]:
    """Extrair contexto de dados de webhook"""
    context = {}
    
    # WhatsApp message ID
    if wa_msg_id := data.get("key", {}).get("id"):
        context["wa_message_id"] = wa_msg_id
    
    # Instance ID
    if instance_id := data.get("instance"):
        context["instance_id"] = instance_id
    
    # User phone as user_id
    if remote_jid := data.get("key", {}).get("remoteJid"):
        user_phone = remote_jid.replace("@s.whatsapp.net", "")
        context["user_id"] = user_phone
    
    # Create conversation ID from instance + phone
    if "instance_id" in context and "user_id" in context:
        context["conversation_id"] = f"{context['instance_id']}:{context['user_id']}"
    
    return context

def set_correlation_context(**context):
    """Definir contexto de correlação manualmente"""
    if trace_id := context.get("trace_id"):
        trace_id_var.set(trace_id)
    if span_id := context.get("span_id"):
        span_id_var.set(span_id)
    if user_id := context.get("user_id"):
        user_id_var.set(user_id)
    if conversation_id := context.get("conversation_id"):
        conversation_id_var.set(conversation_id)
    if wa_message_id := context.get("wa_message_id"):
        wa_message_id_var.set(wa_message_id)
    if instance_id := context.get("instance_id"):
        instance_id_var.set(instance_id)

def get_correlation_context() -> Dict[str, Optional[str]]:
    """Obter contexto atual de correlação"""
    return {
        "trace_id": trace_id_var.get(),
        "span_id": span_id_var.get(),
        "user_id": user_id_var.get(),
        "conversation_id": conversation_id_var.get(),
        "wa_message_id": wa_message_id_var.get(),
        "instance_id": instance_id_var.get()
    }

# Export main components
__all__ = [
    'get_logger',
    'CorrelationMiddleware',
    'extract_context_from_webhook_data',
    'set_correlation_context',
    'get_correlation_context',
    'CorrelatedLogger'
]