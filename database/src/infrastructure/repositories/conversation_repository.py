"""
PostgreSQL implementation of ConversationRepository
"""

from typing import Optional, List
from uuid import UUID
import asyncpg

from ...domain.interfaces import ConversationRepository
from shared.src.domain.models import Conversation

# Import shared modules
import sys
sys.path.append('/app/shared')
from shared.utils.logger import setup_logger


class PostgreSQLConversationRepository(ConversationRepository):
    """PostgreSQL implementation of ConversationRepository"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
        self.logger = setup_logger("conversation_repository")
    
    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation"""
        try:
            query = """
                INSERT INTO conversations (
                    id, user_id, instance_id, title, status, context, 
                    last_message_at, created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    conversation.id,
                    conversation.user_id,
                    conversation.instance_id,
                    conversation.title,
                    conversation.status,
                    conversation.context,
                    conversation.last_message_at,
                    conversation.created_at,
                    conversation.updated_at,
                    conversation.is_active
                )
                
                if row:
                    self.logger.info(f"Conversation created successfully: {conversation.id}")
                    return Conversation(**dict(row))
                else:
                    raise Exception("Failed to create conversation")
                    
        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            raise
    
    async def get_by_id(self, conversation_id: UUID) -> Optional[Conversation]:
        """Get conversation by ID"""
        try:
            query = "SELECT * FROM conversations WHERE id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, conversation_id)
                
                if row:
                    return Conversation(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting conversation by ID: {str(e)}")
            raise
    
    async def get_by_user_id(self, user_id: UUID) -> List[Conversation]:
        """Get conversations for a user"""
        try:
            query = """
                SELECT * FROM conversations 
                WHERE user_id = $1 AND is_active = true 
                ORDER BY last_message_at DESC NULLS LAST, created_at DESC
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, user_id)
                
                return [Conversation(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting conversations by user ID: {str(e)}")
            raise
    
    async def get_by_user_phone(self, phone: str, instance_id: str) -> Optional[Conversation]:
        """Get active conversation by user phone and instance"""
        try:
            query = """
                SELECT c.* FROM conversations c
                INNER JOIN users u ON c.user_id = u.id
                WHERE u.phone_number = $1 
                AND c.instance_id = $2
                AND c.status = 'active'
                AND c.is_active = true
                ORDER BY c.last_message_at DESC NULLS LAST
                LIMIT 1
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, phone, instance_id)
                
                if row:
                    return Conversation(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting conversation by phone: {str(e)}")
            raise
    
    async def update(self, conversation: Conversation) -> Conversation:
        """Update conversation"""
        try:
            query = """
                UPDATE conversations SET
                    title = $2,
                    status = $3,
                    context = $4,
                    last_message_at = $5,
                    updated_at = $6,
                    is_active = $7
                WHERE id = $1
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    conversation.id,
                    conversation.title,
                    conversation.status,
                    conversation.context,
                    conversation.last_message_at,
                    conversation.updated_at,
                    conversation.is_active
                )
                
                if row:
                    self.logger.info(f"Conversation updated successfully: {conversation.id}")
                    return Conversation(**dict(row))
                else:
                    raise Exception("Failed to update conversation")
                    
        except Exception as e:
            self.logger.error(f"Error updating conversation: {str(e)}")
            raise
    
    async def delete(self, conversation_id: UUID) -> None:
        """Soft delete conversation"""
        try:
            query = """
                UPDATE conversations SET 
                    is_active = false,
                    status = 'deleted',
                    updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, conversation_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"Conversation deleted successfully: {conversation_id}")
                else:
                    raise Exception("Conversation not found or already deleted")
                    
        except Exception as e:
            self.logger.error(f"Error deleting conversation: {str(e)}")
            raise
    
    async def get_recent_conversations(self, limit: int = 50) -> List[Conversation]:
        """Get recent conversations"""
        try:
            query = """
                SELECT * FROM conversations 
                WHERE is_active = true 
                ORDER BY last_message_at DESC NULLS LAST, created_at DESC
                LIMIT $1
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, limit)
                
                return [Conversation(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting recent conversations: {str(e)}")
            raise
    
    async def close_conversation(self, conversation_id: UUID) -> None:
        """Close a conversation"""
        try:
            query = """
                UPDATE conversations SET 
                    status = 'closed',
                    updated_at = NOW()
                WHERE id = $1 AND is_active = true
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, conversation_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"Conversation closed successfully: {conversation_id}")
                else:
                    raise Exception("Conversation not found")
                    
        except Exception as e:
            self.logger.error(f"Error closing conversation: {str(e)}")
            raise