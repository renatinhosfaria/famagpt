"""
PostgreSQL implementation of DocumentRepository
"""

from typing import Optional, List
from uuid import UUID
import asyncpg

from ...domain.interfaces import DocumentRepository
from shared.src.domain.models import Document

# Import shared modules
import sys
sys.path.append('/app/shared')
from shared.utils.logger import setup_logger


class PostgreSQLDocumentRepository(DocumentRepository):
    """PostgreSQL implementation of DocumentRepository"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
        self.logger = setup_logger("document_repository")
    
    async def create(self, document: Document) -> Document:
        """Create a new document"""
        try:
            query = """
                INSERT INTO documents (
                    id, title, content, content_type, file_path, file_size,
                    metadata, embedding, tags, created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    document.id,
                    document.title,
                    document.content,
                    document.content_type,
                    document.file_path,
                    document.file_size,
                    document.metadata,
                    document.embedding,
                    document.tags,
                    document.created_at,
                    document.updated_at,
                    document.is_active
                )
                
                if row:
                    self.logger.info(f"Document created successfully: {document.id}")
                    return Document(**dict(row))
                else:
                    raise Exception("Failed to create document")
                    
        except Exception as e:
            self.logger.error(f"Error creating document: {str(e)}")
            raise
    
    async def get_by_id(self, document_id: UUID) -> Optional[Document]:
        """Get document by ID"""
        try:
            query = "SELECT * FROM documents WHERE id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, document_id)
                
                if row:
                    return Document(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting document by ID: {str(e)}")
            raise
    
    async def get_by_file_path(self, file_path: str) -> Optional[Document]:
        """Get document by file path"""
        try:
            query = "SELECT * FROM documents WHERE file_path = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, file_path)
                
                if row:
                    return Document(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting document by file path: {str(e)}")
            raise
    
    async def search_by_embedding(
        self, 
        embedding: List[float], 
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Document]:
        """Search documents by embedding similarity using PGVector"""
        try:
            # Using cosine similarity with PGVector
            query = """
                SELECT *, 
                    (1 - (embedding <=> $1::vector)) AS similarity_score
                FROM documents 
                WHERE is_active = true
                AND embedding IS NOT NULL
                AND (1 - (embedding <=> $1::vector)) >= $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, embedding, min_similarity, limit)
                
                documents = []
                for row in rows:
                    row_dict = dict(row)
                    # Remove similarity_score as it's not part of Document model
                    similarity = row_dict.pop('similarity_score', None)
                    doc = Document(**row_dict)
                    documents.append(doc)
                
                return documents
                
        except Exception as e:
            self.logger.error(f"Error searching documents by embedding: {str(e)}")
            raise
    
    async def search_by_content(
        self, 
        query_text: str, 
        limit: int = 20
    ) -> List[Document]:
        """Search documents by content using full-text search"""
        try:
            query = """
                SELECT * FROM documents 
                WHERE is_active = true
                AND (title ILIKE $1 OR content ILIKE $1)
                ORDER BY created_at DESC
                LIMIT $2
            """
            
            search_pattern = f"%{query_text}%"
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, search_pattern, limit)
                
                return [Document(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error searching documents by content: {str(e)}")
            raise
    
    async def search_by_tags(self, tags: List[str], limit: int = 50) -> List[Document]:
        """Search documents by tags"""
        try:
            query = """
                SELECT * FROM documents 
                WHERE is_active = true
                AND tags && $1::text[]
                ORDER BY created_at DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, tags, limit)
                
                return [Document(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error searching documents by tags: {str(e)}")
            raise
    
    async def get_by_content_type(
        self, 
        content_type: str, 
        limit: int = 50
    ) -> List[Document]:
        """Get documents by content type"""
        try:
            query = """
                SELECT * FROM documents 
                WHERE content_type = $1 
                AND is_active = true
                ORDER BY created_at DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, content_type, limit)
                
                return [Document(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting documents by content type: {str(e)}")
            raise
    
    async def update(self, document: Document) -> Document:
        """Update document"""
        try:
            query = """
                UPDATE documents SET
                    title = $2,
                    content = $3,
                    content_type = $4,
                    file_path = $5,
                    file_size = $6,
                    metadata = $7,
                    embedding = $8,
                    tags = $9,
                    updated_at = $10,
                    is_active = $11
                WHERE id = $1
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    document.id,
                    document.title,
                    document.content,
                    document.content_type,
                    document.file_path,
                    document.file_size,
                    document.metadata,
                    document.embedding,
                    document.tags,
                    document.updated_at,
                    document.is_active
                )
                
                if row:
                    self.logger.info(f"Document updated successfully: {document.id}")
                    return Document(**dict(row))
                else:
                    raise Exception("Failed to update document")
                    
        except Exception as e:
            self.logger.error(f"Error updating document: {str(e)}")
            raise
    
    async def delete(self, document_id: UUID) -> None:
        """Soft delete document"""
        try:
            query = """
                UPDATE documents SET 
                    is_active = false,
                    updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, document_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"Document deleted successfully: {document_id}")
                else:
                    raise Exception("Document not found or already deleted")
                    
        except Exception as e:
            self.logger.error(f"Error deleting document: {str(e)}")
            raise
    
    async def get_all_documents(self, limit: int = 100) -> List[Document]:
        """Get all active documents"""
        try:
            query = """
                SELECT * FROM documents 
                WHERE is_active = true
                ORDER BY created_at DESC
                LIMIT $1
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, limit)
                
                return [Document(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting all documents: {str(e)}")
            raise
    
    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        limit: int = 10,
        text_weight: float = 0.3,
        embedding_weight: float = 0.7
    ) -> List[Document]:
        """Perform hybrid search combining text and vector similarity"""
        try:
            # This is a simplified hybrid search
            # In production, you might want more sophisticated ranking
            query = """
                SELECT *, 
                    (1 - (embedding <=> $2::vector)) AS vector_score,
                    CASE 
                        WHEN title ILIKE $3 THEN 1.0
                        WHEN content ILIKE $3 THEN 0.8
                        ELSE 0.0
                    END AS text_score,
                    ($4 * (1 - (embedding <=> $2::vector)) + $5 * 
                     CASE 
                        WHEN title ILIKE $3 THEN 1.0
                        WHEN content ILIKE $3 THEN 0.8
                        ELSE 0.0
                     END) AS combined_score
                FROM documents 
                WHERE is_active = true
                AND embedding IS NOT NULL
                ORDER BY combined_score DESC
                LIMIT $6
            """
            
            search_pattern = f"%{query_text}%"
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(
                    query, 
                    query_text,
                    query_embedding, 
                    search_pattern,
                    embedding_weight,
                    text_weight,
                    limit
                )
                
                documents = []
                for row in rows:
                    row_dict = dict(row)
                    # Remove scoring fields as they're not part of Document model
                    for score_field in ['vector_score', 'text_score', 'combined_score']:
                        row_dict.pop(score_field, None)
                    doc = Document(**row_dict)
                    documents.append(doc)
                
                return documents
                
        except Exception as e:
            self.logger.error(f"Error performing hybrid search: {str(e)}")
            raise