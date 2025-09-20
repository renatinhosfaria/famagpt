"""
PostgreSQL implementation of MemoryRepository
"""

from typing import List
from uuid import UUID
import asyncpg

from ...domain.interfaces import MemoryRepository
from shared.src.domain.models import MemoryEntry

# Import shared modules
import sys
sys.path.append('/app/shared')
from shared.utils.logger import setup_logger


class PostgreSQLMemoryRepository(MemoryRepository):
    """PostgreSQL implementation of MemoryRepository"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
        self.logger = setup_logger("memory_repository")
    
    async def create(self, memory: MemoryEntry) -> MemoryEntry:
        """Create a new memory entry"""
        try:
            query = """
                INSERT INTO memory_entries (
                    id, user_id, content, content_type, importance_score,
                    tags, metadata, embedding, created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    memory.id,
                    memory.user_id,
                    memory.content,
                    memory.content_type,
                    memory.importance_score,
                    memory.tags,
                    memory.metadata,
                    memory.embedding,
                    memory.created_at,
                    memory.updated_at,
                    memory.is_active
                )
                
                if row:
                    self.logger.info(f"Memory entry created successfully: {memory.id}")
                    return MemoryEntry(**dict(row))
                else:
                    raise Exception("Failed to create memory entry")
                    
        except Exception as e:
            self.logger.error(f"Error creating memory entry: {str(e)}")
            raise
    
    async def get_by_user_id(self, user_id: UUID, limit: int = 100) -> List[MemoryEntry]:
        """Get memory entries for a user"""
        try:
            query = """
                SELECT * FROM memory_entries 
                WHERE user_id = $1 AND is_active = true 
                ORDER BY importance_score DESC, created_at DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, user_id, limit)
                
                return [MemoryEntry(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting memory entries by user ID: {str(e)}")
            raise
    
    async def get_by_user_id_and_type(
        self, 
        user_id: UUID, 
        content_type: str,
        limit: int = 50
    ) -> List[MemoryEntry]:
        """Get memory entries by user and content type"""
        try:
            query = """
                SELECT * FROM memory_entries 
                WHERE user_id = $1 
                AND content_type = $2 
                AND is_active = true 
                ORDER BY importance_score DESC, created_at DESC
                LIMIT $3
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, user_id, content_type, limit)
                
                return [MemoryEntry(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting memory entries by type: {str(e)}")
            raise
    
    async def search_by_content(
        self, 
        user_id: UUID, 
        query: str,
        limit: int = 20
    ) -> List[MemoryEntry]:
        """Search memory entries by content using full-text search"""
        try:
            search_query = """
                SELECT * FROM memory_entries 
                WHERE user_id = $1 
                AND is_active = true
                AND (content ILIKE $2 OR $2 = ANY(tags))
                ORDER BY importance_score DESC, created_at DESC
                LIMIT $3
            """
            
            search_pattern = f"%{query}%"
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(search_query, user_id, search_pattern, limit)
                
                return [MemoryEntry(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error searching memory entries by content: {str(e)}")
            raise
    
    async def search_by_embedding(
        self,
        user_id: UUID,
        query_embedding: List[float],
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[MemoryEntry]:
        """Search memory entries by embedding similarity using PGVector"""
        try:
            # Using cosine similarity with PGVector
            search_query = """
                SELECT *, 
                    (embedding <=> $2::vector) AS similarity_score
                FROM memory_entries 
                WHERE user_id = $1 
                AND is_active = true
                AND embedding IS NOT NULL
                AND (1 - (embedding <=> $2::vector)) >= $3
                ORDER BY embedding <=> $2::vector
                LIMIT $4
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(
                    search_query, 
                    user_id, 
                    query_embedding, 
                    min_similarity,
                    limit
                )
                
                memories = []
                for row in rows:
                    row_dict = dict(row)
                    # Remove similarity_score as it's not part of MemoryEntry model
                    similarity = row_dict.pop('similarity_score', None)
                    memory = MemoryEntry(**row_dict)
                    memories.append(memory)
                
                return memories
                
        except Exception as e:
            self.logger.error(f"Error searching memory entries by embedding: {str(e)}")
            raise
    
    async def update(self, memory: MemoryEntry) -> MemoryEntry:
        """Update memory entry"""
        try:
            query = """
                UPDATE memory_entries SET
                    content = $2,
                    content_type = $3,
                    importance_score = $4,
                    tags = $5,
                    metadata = $6,
                    embedding = $7,
                    updated_at = $8,
                    is_active = $9
                WHERE id = $1
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    memory.id,
                    memory.content,
                    memory.content_type,
                    memory.importance_score,
                    memory.tags,
                    memory.metadata,
                    memory.embedding,
                    memory.updated_at,
                    memory.is_active
                )
                
                if row:
                    self.logger.info(f"Memory entry updated successfully: {memory.id}")
                    return MemoryEntry(**dict(row))
                else:
                    raise Exception("Failed to update memory entry")
                    
        except Exception as e:
            self.logger.error(f"Error updating memory entry: {str(e)}")
            raise
    
    async def delete(self, memory_id: UUID) -> None:
        """Soft delete memory entry"""
        try:
            query = """
                UPDATE memory_entries SET 
                    is_active = false,
                    updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, memory_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"Memory entry deleted successfully: {memory_id}")
                else:
                    raise Exception("Memory entry not found or already deleted")
                    
        except Exception as e:
            self.logger.error(f"Error deleting memory entry: {str(e)}")
            raise
    
    async def get_by_tags(
        self, 
        user_id: UUID, 
        tags: List[str],
        limit: int = 50
    ) -> List[MemoryEntry]:
        """Get memory entries by tags"""
        try:
            query = """
                SELECT * FROM memory_entries 
                WHERE user_id = $1 
                AND is_active = true
                AND tags && $2::text[]
                ORDER BY importance_score DESC, created_at DESC
                LIMIT $3
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, user_id, tags, limit)
                
                return [MemoryEntry(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting memory entries by tags: {str(e)}")
            raise
    
    async def get_most_important(
        self, 
        user_id: UUID,
        limit: int = 20
    ) -> List[MemoryEntry]:
        """Get most important memory entries for a user"""
        try:
            query = """
                SELECT * FROM memory_entries 
                WHERE user_id = $1 
                AND is_active = true
                AND importance_score > 0.7
                ORDER BY importance_score DESC, created_at DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, user_id, limit)
                
                return [MemoryEntry(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting most important memories: {str(e)}")
            raise
    
    async def cleanup_old_memories(self, user_id: UUID, days_old: int = 30) -> int:
        """Clean up old, low-importance memories"""
        try:
            query = """
                UPDATE memory_entries SET 
                    is_active = false,
                    updated_at = NOW()
                WHERE user_id = $1
                AND is_active = true
                AND importance_score < 0.3
                AND created_at < NOW() - INTERVAL '%s days'
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query % days_old, user_id)
                
                # Extract number from result like "UPDATE 5"
                count = int(result.split()[-1]) if result.startswith("UPDATE") else 0
                
                self.logger.info(f"Cleaned up {count} old memories for user {user_id}")
                return count
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old memories: {str(e)}")
            raise