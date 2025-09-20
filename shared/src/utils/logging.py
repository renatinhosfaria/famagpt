"""
Centralized logging configuration.
"""
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        
        # Base log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add service information if available
        if hasattr(record, 'service_name'):
            log_entry["service"] = record.service_name
        
        # Add correlation ID if available
        if hasattr(record, 'correlation_id'):
            log_entry["correlation_id"] = record.correlation_id
        
        # Add user ID if available
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = str(record.user_id)
        
        # Add conversation ID if available
        if hasattr(record, 'conversation_id'):
            log_entry["conversation_id"] = str(record.conversation_id)
        
        # Add extra fields
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        
        # Add exception information
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class StructuredLogger:
    """Structured logger with context support."""
    
    def __init__(self, name: str, service_name: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.service_name = service_name
        self._setup_logger()
    
    def _setup_logger(self):
        """Setup logger with JSON formatter."""
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JSONFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def _add_context(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Add service context to extra fields."""
        if self.service_name:
            extra["service_name"] = self.service_name
        return extra
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        extra = self._add_context(kwargs)
        self.logger.debug(message, extra=extra)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        extra = self._add_context(kwargs)
        self.logger.info(message, extra=extra)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        extra = self._add_context(kwargs)
        self.logger.warning(message, extra=extra)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        extra = self._add_context(kwargs)
        # Remover campos reservados que conflitam com LogRecord
        for reserved in ("exc_info",):
            extra.pop(reserved, None)
        self.logger.error(message, extra=extra)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        extra = self._add_context(kwargs)
        self.logger.critical(message, extra=extra)
    
    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        extra = self._add_context(kwargs)
        for reserved in ("exc_info",):
            extra.pop(reserved, None)
        self.logger.exception(message, extra=extra)


class LoggerAdapter:
    """Logger adapter with automatic context injection."""
    
    def __init__(
        self, 
        logger: StructuredLogger, 
        correlation_id: Optional[str] = None,
        user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None
    ):
        self.logger = logger
        self.correlation_id = correlation_id
        self.user_id = user_id
        self.conversation_id = conversation_id
    
    def _add_context(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Add context to extra fields."""
        if self.correlation_id:
            extra["correlation_id"] = self.correlation_id
        if self.user_id:
            extra["user_id"] = self.user_id
        if self.conversation_id:
            extra["conversation_id"] = self.conversation_id
        return extra
    
    def debug(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.debug(message, **extra)
    
    def info(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.info(message, **extra)
    
    def warning(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.warning(message, **extra)
    
    def error(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.error(message, **extra)
    
    def critical(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.critical(message, **extra)
    
    def exception(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.exception(message, **extra)


def get_logger(name: str, service_name: Optional[str] = None) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name, service_name)


def get_logger_adapter(
    logger: StructuredLogger,
    correlation_id: Optional[str] = None,
    user_id: Optional[UUID] = None,
    conversation_id: Optional[UUID] = None
) -> LoggerAdapter:
    """Get a logger adapter with context."""
    return LoggerAdapter(logger, correlation_id, user_id, conversation_id)


def setup_logging(service_name: str, log_level: str = "INFO"):
    """Setup logging for a service."""
    
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add JSON handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
    
    # Log startup message
    logger = get_logger(__name__, service_name)
    logger.info(f"Logging configured for {service_name}", log_level=log_level)
