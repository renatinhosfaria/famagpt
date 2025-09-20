"""
RAG Application Service - coordinates RAG operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from shared.src.utils.logging import get_logger

from ..use_cases.rag_pipeline import RAGPipelineUseCase
from ...domain.entities.document import (
    DocumentIngestRequest, Document, RAGResponse, DocumentType
)
from ...infrastructure.services.database_client import DatabaseClient


logger = get_logger("rag.application_service")


class RAGService:
    """Application service for RAG operations"""
    
    def __init__(self, rag_pipeline: RAGPipelineUseCase, database_client: Optional[DatabaseClient] = None):
        self.rag_pipeline = rag_pipeline
        self.database_client = database_client
    
    async def ingest_document(
        self, 
        title: str, 
        content: str,
        document_type: str = "text",
        source_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Document:
        """
        Ingest a document into the RAG system
        
        Args:
            title: Document title
            content: Document content
            document_type: Type of document
            source_url: Source URL if applicable
            metadata: Additional metadata
            
        Returns:
            Processed document
        """
        try:
            # Convert document_type string to enum if needed
            doc_type = document_type
            if isinstance(doc_type, str):
                try:
                    doc_type = DocumentType(doc_type.upper())
                except ValueError:
                    doc_type = DocumentType.TEXT  # Default fallback
                    logger.warning(f"Unknown document type '{document_type}', using TEXT as default")
                    
            # Create ingestion request
            request = DocumentIngestRequest(
                title=title,
                content=content,
                document_type=doc_type,
                source_url=source_url,
                metadata=metadata or {}
            )
            
            # Process through pipeline
            document = await self.rag_pipeline.ingest_document(request)
            
            # Store metadata in central database if client available
            if self.database_client:
                try:
                    await self.database_client.store_document_metadata(document)
                except Exception as e:
                    logger.warning(f"Failed to store document metadata in central DB: {str(e)}")
            
            logger.info(f"Successfully ingested document: {title}")
            return document
            
        except Exception as e:
            logger.error(f"Failed to ingest document {title}: {str(e)}")
            raise
    
    async def query_rag(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> RAGResponse:
        """
        Query the RAG system for information
        
        Args:
            query: User query
            top_k: Number of chunks to retrieve
            min_similarity: Minimum similarity threshold
            filters: Additional filters
            use_cache: Whether to use cache
            system_prompt: Custom system prompt
            temperature: Generation temperature
            
        Returns:
            RAG response with generated text and sources
        """
        try:
            response = await self.rag_pipeline.query_documents(
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
                filters=filters,
                use_cache=use_cache,
                system_prompt=system_prompt,
                temperature=temperature
            )
            
            logger.info(f"Successfully processed RAG query: {query[:50]}...")
            return response
            
        except Exception as e:
            logger.error(f"Failed to process RAG query: {str(e)}")
            raise
    
    async def search_documents(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search documents without generation (retrieval only)
        
        Args:
            query: Search query
            top_k: Number of results
            min_similarity: Minimum similarity threshold
            filters: Additional filters
            
        Returns:
            List of search results
        """
        try:
            results = await self.rag_pipeline.search_documents(
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
                filters=filters
            )
            
            # Convert to serializable format
            serializable_results = []
            for result in results:
                serializable_results.append({
                    "chunk_id": result.chunk.id,
                    "document_id": result.chunk.document_id,
                    "content": result.chunk.content,
                    "similarity_score": result.similarity_score,
                    "document_title": result.document_title,
                    "document_metadata": result.document_metadata,
                    "chunk_metadata": result.chunk.metadata
                })
            
            logger.info(f"Successfully searched documents: found {len(results)} results")
            return serializable_results
            
        except Exception as e:
            logger.error(f"Failed to search documents: {str(e)}")
            raise
    
    async def delete_document(self, document_id: str) -> bool:
        """
        Delete a document from the RAG system
        
        Args:
            document_id: ID of document to delete
            
        Returns:
            Success status
        """
        try:
            await self.rag_pipeline.delete_document(document_id)
            
            # Delete metadata from central database if client available
            if self.database_client:
                try:
                    await self.database_client.delete_document_metadata(document_id)
                except Exception as e:
                    logger.warning(f"Failed to delete document metadata from central DB: {str(e)}")
            
            logger.info(f"Successfully deleted document: {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {str(e)}")
            return False
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics"""
        try:
            stats = await self.rag_pipeline.get_system_stats()
            logger.debug("Retrieved RAG system stats")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get system stats: {str(e)}")
            return {"error": str(e), "status": "error"}
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for RAG service"""
        try:
            stats = await self.get_system_stats()
            
            health_status = {
                "service": "rag",
                "status": "healthy" if stats.get("rag_system") == "operational" else "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "total_documents": stats.get("total_documents", 0),
                    "total_chunks": stats.get("total_chunks", 0),
                    "cache_enabled": stats.get("cache_enabled", False),
                    "embedding_dimension": stats.get("embedding_dimension", 0)
                }
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"RAG health check failed: {str(e)}")
            return {
                "service": "rag",
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }