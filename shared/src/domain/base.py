"""
Base entities and value objects for the domain layer.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Entity(BaseModel):
    """Base entity class with common attributes."""
    
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


class AggregateRoot(Entity):
    """Base aggregate root for DDD."""
    
    version: int = Field(default=1)
    

class ValueObject(BaseModel):
    """Base value object class."""
    
    class Config:
        frozen = True


class DomainEvent(BaseModel):
    """Base domain event."""
    
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    aggregate_id: UUID
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


class Repository(ABC):
    """Base repository interface."""
    
    @abstractmethod
    async def save(self, entity: Entity) -> None:
        """Save an entity."""
        pass
    
    @abstractmethod
    async def find_by_id(self, entity_id: UUID) -> Optional[Entity]:
        """Find entity by ID."""
        pass
    
    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        """Delete entity by ID."""
        pass


class UseCase(ABC):
    """Base use case interface."""
    
    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        """Execute the use case."""
        pass


class DomainService(ABC):
    """Base domain service interface."""
    pass
