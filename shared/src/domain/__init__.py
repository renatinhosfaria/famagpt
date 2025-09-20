"""
Shared domain module.
"""
from .base import Entity, AggregateRoot, ValueObject, DomainEvent, Repository, UseCase, DomainService
from .exceptions import (
    DomainException,
    ValidationError,
    NotFoundError,
    BusinessRuleViolationError,
    ConcurrencyError,
    AuthorizationError,
    RateLimitExceededError,
    ExternalServiceError,
    ConfigurationError
)
from .models import (
    MessageType,
    MessageStatus,
    ConversationStatus,
    AgentType,
    Priority,
    ContactInfo,
    Location,
    User,
    Message,
    Conversation,
    Task,
    Property,
    MemoryEntry,
    Document
)

__all__ = [
    # Base classes
    "Entity",
    "AggregateRoot", 
    "ValueObject",
    "DomainEvent",
    "Repository",
    "UseCase",
    "DomainService",
    
    # Exceptions
    "DomainException",
    "ValidationError",
    "NotFoundError",
    "BusinessRuleViolationError",
    "ConcurrencyError",
    "AuthorizationError",
    "RateLimitExceededError",
    "ExternalServiceError",
    "ConfigurationError",
    
    # Enums
    "MessageType",
    "MessageStatus",
    "ConversationStatus",
    "AgentType",
    "Priority",
    
    # Value Objects
    "ContactInfo",
    "Location",
    
    # Entities/Aggregates
    "User",
    "Message",
    "Conversation",
    "Task",
    "Property",
    "MemoryEntry",
    "Document"
]
