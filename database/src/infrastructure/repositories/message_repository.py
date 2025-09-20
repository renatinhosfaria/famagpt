"""
PostgreSQL implementation of MessageRepository
"""

from typing import Optional, List
from uuid import UUID
import asyncpg

from ...domain.interfaces import MessageRepository
from shared.src.domain.models import Message

# Import shared modules
import sys
sys.path.append('/app/shared')
from shared.utils.logger import setup_logger


class PostgreSQLMessageRepository(MessageRepository):
    """PostgreSQL implementation of MessageRepository"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
        self.logger = setup_logger("message_repository")
    
    async def create(self, message: Message) -> Message:
        """Create a new message"""
        try:
            query = """
                INSERT INTO messages (
                    id, conversation_id, whatsapp_message_id, sender_type, content,
                    message_type, metadata, timestamp, created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    message.id,
                    message.conversation_id,
                    message.whatsapp_message_id,
                    message.sender_type,
                    message.content,
                    message.message_type,
                    message.metadata,
                    message.timestamp,
                    message.created_at,
                    message.updated_at,
                    message.is_active
                )
                
                if row:
                    self.logger.info(f"Message created successfully: {message.id}")
                    return Message(**dict(row))
                else:
                    raise Exception("Failed to create message")
                    
        except Exception as e:
            self.logger.error(f"Error creating message: {str(e)}")
            raise
    
    async def get_by_id(self, message_id: UUID) -> Optional[Message]:
        """Get message by ID"""
        try:
            query = "SELECT * FROM messages WHERE id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, message_id)
                
                if row:
                    return Message(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting message by ID: {str(e)}")
            raise
    
    async def get_by_whatsapp_id(self, whatsapp_message_id: str) -> Optional[Message]:
        """Get message by WhatsApp message ID"""
        try:
            query = "SELECT * FROM messages WHERE whatsapp_message_id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, whatsapp_message_id)
                
                if row:
                    return Message(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting message by WhatsApp ID: {str(e)}")
            raise
    
    async def get_by_conversation_id(self, conversation_id: UUID, limit: int = 100) -> List[Message]:
        """Get messages for a conversation"""
        try:
            query = """
                SELECT * FROM messages 
                WHERE conversation_id = $1 AND is_active = true 
                ORDER BY timestamp DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, conversation_id, limit)
                
                # Return in chronological order (oldest first)
                return [Message(**dict(row)) for row in reversed(rows)]
                
        except Exception as e:
            self.logger.error(f"Error getting messages by conversation ID: {str(e)}")
            raise
    
    async def get_conversation_context(self, conversation_id: UUID, limit: int = 10) -> List[Message]:
        """Get recent messages for conversation context"""
        try:
            query = """
                SELECT * FROM messages 
                WHERE conversation_id = $1 AND is_active = true 
                ORDER BY timestamp DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, conversation_id, limit)
                
                # Return in chronological order for context
                return [Message(**dict(row)) for row in reversed(rows)]
                
        except Exception as e:
            self.logger.error(f"Error getting conversation context: {str(e)}")
            raise
    
    async def update(self, message: Message) -> Message:
        """Update message"""
        try:
            query = """
                UPDATE messages SET
                    content = $2,
                    message_type = $3,
                    metadata = $4,
                    updated_at = $5,
                    is_active = $6
                WHERE id = $1
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    message.id,
                    message.content,
                    message.message_type,
                    message.metadata,
                    message.updated_at,
                    message.is_active
                )
                
                if row:
                    self.logger.info(f"Message updated successfully: {message.id}")
                    return Message(**dict(row))
                else:
                    raise Exception("Failed to update message")
                    
        except Exception as e:
            self.logger.error(f"Error updating message: {str(e)}")
            raise
    
    async def delete(self, message_id: UUID) -> None:
        """Soft delete message"""
        try:
            query = """
                UPDATE messages SET 
                    is_active = false,
                    updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, message_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"Message deleted successfully: {message_id}")
                else:
                    raise Exception("Message not found or already deleted")
                    
        except Exception as e:
            self.logger.error(f"Error deleting message: {str(e)}")
            raise
    
    async def search_by_content(self, query_text: str, limit: int = 50) -> List[Message]:
        """Search messages by content"""
        try:
            query = """
                SELECT * FROM messages 
                WHERE content ILIKE $1 AND is_active = true 
                ORDER BY timestamp DESC
                LIMIT $2
            """
            
            search_pattern = f"%{query_text}%"
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, search_pattern, limit)
                
                return [Message(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error searching messages by content: {str(e)}")
            raise
    
    async def get_user_message_count(self, conversation_id: UUID) -> int:
        """Get count of user messages in conversation"""
        try:
            query = """
                SELECT COUNT(*) FROM messages 
                WHERE conversation_id = $1 
                AND sender_type = 'user' 
                AND is_active = true
            """
            
            async with self.pool.acquire() as connection:
                count = await connection.fetchval(query, conversation_id)
                
                return count or 0
                
        except Exception as e:
            self.logger.error(f"Error getting user message count: {str(e)}")
            raise
    
    async def get_messages_by_type(
        self, 
        conversation_id: UUID, 
        message_type: str,
        limit: int = 50
    ) -> List[Message]:
        """Get messages by type for a conversation"""
        try:
            query = """
                SELECT * FROM messages 
                WHERE conversation_id = $1 
                AND message_type = $2 
                AND is_active = true 
                ORDER BY timestamp DESC
                LIMIT $3
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, conversation_id, message_type, limit)
                
                return [Message(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting messages by type: {str(e)}")
            raise